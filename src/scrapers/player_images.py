"""
Fetch player headshot URLs from Transfermarkt search.
Returns a dict {normalised_name: image_url} cached to disk.

Only fetches images for players in the squad (15 players) to stay polite.
Full player list images can be added later per-request.
"""

import re
import time
import json
import requests
from pathlib import Path
from bs4 import BeautifulSoup

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_FILE = CACHE_DIR / "player_images.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

import unicodedata

def _norm(s):
    nfkd = unicodedata.normalize("NFKD", str(s))
    return re.sub(r"[^a-z0-9 ]", "", nfkd.encode("ascii","ignore").decode().lower()).strip()


def _search_tm(name: str) -> str | None:
    """Search Transfermarkt for a player and return their headshot URL."""
    # Use normalised (accent-stripped) name for robust search
    ascii_name = _norm(name).title()
    url = f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={requests.utils.quote(ascii_name)}&Spieler_page=0"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # Player portrait image: class "bilderrahmen-fixed", src (not data-src)
    img = soup.select_one("table.items tr img.bilderrahmen-fixed")
    if img:
        src = img.get("src", "")
        # Upgrade from small to medium portrait
        src = src.replace("/small/", "/medium/")
        if src.startswith("http") and "portrait" in src:
            return src

    return None


def fetch_images(player_names: list[str], force: bool = False) -> dict[str, str]:
    """
    Fetch images for a list of player names.
    Returns {normalised_name: image_url}.
    """
    cache = {}
    if CACHE_FILE.exists() and not force:
        cache = json.loads(CACHE_FILE.read_text())

    missing = [n for n in player_names if _norm(n) not in cache]
    if not missing:
        return cache

    print(f"  Fetching {len(missing)} player images from Transfermarkt...")
    for name in missing:
        key = _norm(name)
        url = _search_tm(name)
        if url:
            cache[key] = url
            print(f"    {name}: {url[:60]}...")
        else:
            cache[key] = ""
            print(f"    {name}: not found")
        time.sleep(2)  # polite delay

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    return cache


def inject_images(players: list[dict], image_cache: dict) -> list[dict]:
    """Add img_url field to player dicts from cache."""
    for p in players:
        key = _norm(p.get("name", ""))
        p["img_url"] = image_cache.get(key, "")
    return players


if __name__ == "__main__":
    test = ["Kylian Mbappé", "Lamine Yamal", "Harry Kane", "Emiliano Martínez", "Joshua Kimmich"]
    imgs = fetch_images(test, force=True)
    for name in test:
        print(f"{name}: {imgs.get(_norm(name), 'N/A')}")
