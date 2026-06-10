"""
Transfermarkt scraper — player market values for WC 2026 squads.

Market value is the best single-number quality signal available:
- Community-sourced by thousands of analysts, updated continuously
- Reflects current form AND projected future performance
- Directly exposes Moneyball opportunities: high market value + low FIFA price = undervalued

Strategy: scrape each participating nation's squad page, extract names + market values.
We only need the ~700 players who made national squads, not all 1,481 in FIFA fantasy.
"""

import re
import time
import json
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Transfermarkt national team IDs for WC 2026 squads
# Format: "FIFA_ABBR": ("tm-slug", tm_id)
NATIONAL_TEAMS = {
    "USA": ("vereins-usa",  3633),
    "MEX": ("mexiko",        163),
    "CAN": ("kanada",       3437),
    "ARG": ("argentinien",  3381),
    "BRA": ("brasilien",    3439),
    "FRA": ("frankreich",   3377),
    "ESP": ("spanien",      3375),
    "ENG": ("england",         3),
    "GER": ("deutschland",  3376),
    "POR": ("portugal",     3378),
    "NED": ("niederlande",  3379),
    "BEL": ("belgien",      3382),
    "ITA": ("italien",      3380),
    "URU": ("uruguay",      3383),
    "COL": ("kolumbien",    3384),
    "MOR": ("marokko",      3694),
    "SEN": ("senegal",      3685),
    "NGA": ("nigeria",      3686),
    "JPN": ("japan",        3462),
    "KOR": ("suedkorea",    3464),
    "AUS": ("australien",   3461),
    "CRO": ("kroatien",     3385),
    "SUI": ("schweiz",      3386),
    "DEN": ("daenemark",    3387),
}

TM_BASE = "https://www.transfermarkt.com"


def _parse_market_value(text: str) -> float:
    """Convert '€45.00m', '€500k', '€1.20bn' etc. to float millions."""
    if not text:
        return 0.0
    text = text.strip().replace(",", ".")
    m = re.search(r"[\$€£]?([\d.]+)\s*(k|m|bn)?", text, re.I)
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = (m.group(2) or "").lower()
    if unit == "k":
        val /= 1000
    elif unit == "bn":
        val *= 1000
    return round(val, 2)


def _scrape_team(slug: str, tm_id: int) -> list[dict]:
    url = f"{TM_BASE}/{slug}/kader/verein/{tm_id}/plus/1"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"    WARN: {slug} failed — {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    rows = []

    for tr in soup.select("table.items tbody tr"):
        name_el  = tr.select_one("td.hauptlink a")
        pos_el   = tr.select_one("td:nth-child(5)")
        val_el   = tr.select_one("td.rechts.hauptlink")

        if not name_el:
            continue

        name  = name_el.get_text(strip=True)
        pos   = pos_el.get_text(strip=True) if pos_el else ""
        mv    = _parse_market_value(val_el.get_text(strip=True) if val_el else "")

        rows.append({"tm_name": name, "tm_position": pos, "market_value_m": mv})

    time.sleep(3)
    return rows


def fetch_market_values(teams: dict = None) -> pd.DataFrame:
    """
    Scrape market values for the given teams dict {FIFA_ABBR: (slug, id)}.
    Defaults to NATIONAL_TEAMS above.
    """
    teams = teams or NATIONAL_TEAMS
    cache_path = CACHE_DIR / "transfermarkt_mv.json"

    if cache_path.exists():
        print("  [cache] transfermarkt market values")
        return pd.read_json(cache_path)

    all_rows = []
    for abbr, (slug, tm_id) in teams.items():
        print(f"  [fetch] transfermarkt/{abbr}")
        rows = _scrape_team(slug, tm_id)
        for r in rows:
            r["country"] = abbr
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    if df.empty:
        return df

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_json(cache_path, orient="records", force_ascii=False)
    print(f"  transfermarkt: {len(df)} players across {len(teams)} teams")
    return df


def clear_cache():
    p = CACHE_DIR / "transfermarkt_mv.json"
    if p.exists():
        p.unlink()
        print(f"  deleted {p.name}")


if __name__ == "__main__":
    # Test with a single team first
    test = {"ENG": ("england", 3)}
    df = fetch_market_values(test)
    if not df.empty:
        print(df.sort_values("market_value_m", ascending=False).head(15).to_string(index=False))
