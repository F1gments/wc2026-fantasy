"""
Understat scraper — xG, xA, goals, assists, minutes for Big 5 leagues.
Data is embedded as JSON in the HTML — no Cloudflare, no API key required.
"""

import re
import json
import time
import pandas as pd
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# understat league keys for 2024-25 season (year = season start year)
LEAGUES = {
    "EPL":        "https://understat.com/league/EPL/2024",
    "La_liga":    "https://understat.com/league/La_liga/2024",
    "Bundesliga": "https://understat.com/league/Bundesliga/2024",
    "Serie_A":    "https://understat.com/league/Serie_A/2024",
    "Ligue_1":    "https://understat.com/league/Ligue_1/2024",
}


def _fetch_league(league_key: str, url: str) -> list[dict]:
    import requests

    cache_path = CACHE_DIR / f"understat_{league_key}.json"
    if cache_path.exists():
        print(f"  [cache] understat/{league_key}")
        return json.loads(cache_path.read_text())

    print(f"  [fetch] {url}")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    # Data is embedded as: var playersData = JSON.parse('...');
    match = re.search(r"var playersData\s*=\s*JSON\.parse\('(.+?)'\);", resp.text)
    if not match:
        print(f"  WARNING: playersData not found for {league_key}")
        return []

    # String is unicode-escaped
    raw = match.group(1).encode("utf-8").decode("unicode_escape")
    players = json.loads(raw)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(players, ensure_ascii=False))
    time.sleep(2)
    return players


def fetch_all_leagues() -> pd.DataFrame:
    """Fetch all Big 5 leagues and return a single combined DataFrame."""
    all_rows = []
    for league_key, url in LEAGUES.items():
        players = _fetch_league(league_key, url)
        for p in players:
            minutes = int(p.get("time") or 0)
            if minutes < 90:  # skip players with less than 1 full game
                continue
            n90 = minutes / 90

            all_rows.append({
                "fbref_name":    p.get("player_name", ""),
                "understat_id":  p.get("id", ""),
                "league":        league_key,
                "team":          p.get("team_title", ""),
                "position":      p.get("position", ""),
                "minutes":       minutes,
                "goals":         float(p.get("goals") or 0),
                "assists":       float(p.get("assists") or 0),
                "xg":            float(p.get("xG") or 0),
                "xag":           float(p.get("xA") or 0),
                "shots":         float(p.get("shots") or 0),
                "key_passes":    float(p.get("key_passes") or 0),
                "npxg":          float(p.get("npxG") or 0),
                "g_per90":       float(p.get("goals") or 0)  / n90,
                "a_per90":       float(p.get("assists") or 0) / n90,
                "xg_per90":      float(p.get("xG") or 0)    / n90,
                "xa_per90":      float(p.get("xA") or 0)    / n90,
                "shots_on_tgt":  float(p.get("shots") or 0) / n90,  # shots used as proxy
                "prog_carries":  0.0,  # not in understat
                "prog_passes":   float(p.get("key_passes") or 0),  # key passes as proxy
            })

    df = pd.DataFrame(all_rows)

    # De-duplicate: if a player appears in multiple leagues (unlikely but possible)
    # keep the one with more minutes
    df = (
        df.sort_values("minutes", ascending=False)
        .drop_duplicates(subset=["fbref_name", "team"])
        .reset_index(drop=True)
    )

    print(f"  understat total: {len(df)} outfield rows across {len(LEAGUES)} leagues")
    return df


def clear_cache():
    for key in LEAGUES:
        p = CACHE_DIR / f"understat_{key}.json"
        if p.exists():
            p.unlink()
            print(f"  deleted {p.name}")


if __name__ == "__main__":
    df = fetch_all_leagues()
    print(df.groupby("position").size())
    print(df.sort_values("xg_per90", ascending=False).head(10)[
        ["fbref_name", "team", "position", "minutes", "xg_per90", "xa_per90"]
    ].to_string(index=False))
