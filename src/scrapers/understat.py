"""
Understat scraper — xG, xA, goals, assists, minutes for Big 5 leagues.
Uses the `understatapi` package which handles the site's changing structure.
"""

import json
import pandas as pd
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"

# understatapi league names  →  season start year
LEAGUES = {
    "EPL":        "2025",
    "La_Liga":    "2025",
    "Bundesliga": "2025",
    "Serie_A":    "2025",
    "Ligue_1":    "2025",
}


def _fetch_league(league_key: str, season: str) -> list[dict]:
    cache_path = CACHE_DIR / f"understat_{league_key.replace(' ', '_')}.json"
    if cache_path.exists():
        print(f"  [cache] understat/{league_key}")
        return json.loads(cache_path.read_text())

    print(f"  [fetch] understat/{league_key} {season}")
    try:
        from understatapi import UnderstatClient
        with UnderstatClient() as client:
            players = client.league(league=league_key).get_player_data(season=season)
    except Exception as e:
        print(f"  WARNING: understat/{league_key} failed — {e}")
        return []

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(players, ensure_ascii=False))
    return players


def fetch_all_leagues() -> pd.DataFrame:
    all_rows = []
    for league_key, season in LEAGUES.items():
        players = _fetch_league(league_key, season)
        for p in players:
            minutes = int(p.get("time") or 0)
            if minutes < 90:
                continue
            n90 = minutes / 90
            all_rows.append({
                "fbref_name":   p.get("player_name", ""),
                "understat_id": str(p.get("id", "")),
                "league":       league_key,
                "team":         p.get("team_title", ""),
                "position":     p.get("position", ""),
                "minutes":      minutes,
                "goals":        float(p.get("goals") or 0),
                "assists":      float(p.get("assists") or 0),
                "xg":           float(p.get("xG") or 0),
                "xag":          float(p.get("xA") or 0),
                "shots":        float(p.get("shots") or 0),
                "key_passes":   float(p.get("key_passes") or 0),
                "npxg":         float(p.get("npxG") or 0),
                "g_per90":      float(p.get("goals") or 0) / n90,
                "a_per90":      float(p.get("assists") or 0) / n90,
                "xg_per90":     float(p.get("xG") or 0) / n90,
                "xa_per90":     float(p.get("xA") or 0) / n90,
                "shots_on_tgt": float(p.get("shots") or 0) / n90,
                "prog_carries": 0.0,
                "prog_passes":  float(p.get("key_passes") or 0),
            })

    if not all_rows:
        print("  understat: no data returned — using ownership-only scoring")
        return pd.DataFrame()

    df = (
        pd.DataFrame(all_rows)
        .sort_values("minutes", ascending=False)
        .drop_duplicates(subset=["fbref_name", "team"])
        .reset_index(drop=True)
    )
    print(f"  understat total: {len(df)} players across {len(LEAGUES)} leagues")
    return df


def clear_cache():
    for key in LEAGUES:
        p = CACHE_DIR / f"understat_{key.replace(' ', '_')}.json"
        if p.exists():
            p.unlink()
            print(f"  deleted {p.name}")


if __name__ == "__main__":
    df = fetch_all_leagues()
    if not df.empty:
        print(df.sort_values("xg_per90", ascending=False).head(10)[
            ["fbref_name", "team", "position", "minutes", "xg_per90", "xa_per90"]
        ].to_string(index=False))
