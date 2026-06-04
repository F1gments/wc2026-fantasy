"""
Fetch and normalise player data from FIFA Play into a clean DataFrame.
"""
import json
import pandas as pd
from pathlib import Path
from fifa_client import FifaFantasyClient

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"


POSITION_MAP = {
    1: "GK", "GK": "GK",
    2: "DEF", "DF": "DEF",
    3: "MID", "MF": "MID",
    4: "FWD", "FW": "FWD",
}


def fetch_players(client: FifaFantasyClient) -> pd.DataFrame:
    raw = client.get_players()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "players_raw.json").write_text(json.dumps(raw, indent=2))

    rows = []
    for p in raw:
        pos_raw = p.get("position") or p.get("positionId") or p.get("pos")
        rows.append({
            "id":         str(p.get("id") or p.get("playerId", "")),
            "name":       p.get("name") or p.get("knownName") or p.get("lastName", "Unknown"),
            "country":    p.get("teamAbbr") or p.get("country") or p.get("team", ""),
            "position":   POSITION_MAP.get(pos_raw, str(pos_raw)),
            "price":      float(p.get("value") or p.get("price") or p.get("cost", 0)),
            "total_pts":  float(p.get("totalPoints") or p.get("points") or 0),
            "form":       float(p.get("form") or p.get("recentPoints") or 0),
            "selected_pct": float(p.get("selectedByPercent") or p.get("ownership") or 0),
            "goals":      int(p.get("goals") or p.get("goalsScored") or 0),
            "assists":    int(p.get("assists") or 0),
            "clean_sheets": int(p.get("cleanSheets") or 0),
            "yellow_cards": int(p.get("yellowCards") or 0),
            "red_cards":  int(p.get("redCards") or 0),
            "minutes":    int(p.get("minutesPlayed") or p.get("minutes") or 0),
        })

    df = pd.DataFrame(rows)
    df = df[df["price"] > 0]
    return df


def enrich_value_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["pts_per_m"] = df["total_pts"] / df["price"].replace(0, pd.NA)
    df["form_per_m"] = df["form"] / df["price"].replace(0, pd.NA)

    # Weighted score: blends season total and recent form
    max_pts = df["total_pts"].max() or 1
    max_form = df["form"].max() or 1
    df["value_score"] = (
        0.5 * df["total_pts"] / max_pts +
        0.5 * df["form"]     / max_form
    ) / df["price"].replace(0, pd.NA)

    return df


def load_or_fetch(client: FifaFantasyClient) -> pd.DataFrame:
    cache = RAW_DIR / "players_raw.json"
    if cache.exists():
        print(f"Using cached player data ({cache})")
        raw = json.loads(cache.read_text())
        df = fetch_players.__wrapped__(raw) if hasattr(fetch_players, "__wrapped__") else None
        if df is None:
            # Re-parse from cached raw
            client_mock = type("M", (), {"get_players": lambda s: raw})()
            df = fetch_players(client_mock)
    else:
        df = fetch_players(client)

    df = enrich_value_metrics(df)
    return df


if __name__ == "__main__":
    from fifa_client import FifaFantasyClient
    import os
    token = os.getenv("FIFA_SESSION_TOKEN")
    client = FifaFantasyClient(session_token=token)
    df = fetch_players(client)
    df = enrich_value_metrics(df)
    print(df.groupby("position").size())
    print(df.sort_values("value_score", ascending=False).head(20)[
        ["name", "country", "position", "price", "total_pts", "value_score"]
    ].to_string())
