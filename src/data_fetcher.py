"""
Fetch and normalise player data from FIFA Play into a clean DataFrame.
"""
import json
import pandas as pd
from pathlib import Path
from fifa_client import FifaFantasyClient

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"


def _build_squad_map(client: FifaFantasyClient) -> dict[int, str]:
    squads = client.get_squads()
    squads = squads.get("data", squads) if isinstance(squads, dict) else squads
    return {s["id"]: s["abbr"] for s in squads}


def fetch_players(client: FifaFantasyClient) -> pd.DataFrame:
    squad_map = _build_squad_map(client)
    raw = client.get_players()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "players_raw.json").write_text(json.dumps(raw, indent=2))

    rows = []
    for p in raw:
        stats = p.get("stats") or {}
        name = p.get("knownName") or f"{p.get('firstName','')} {p.get('lastName','')}".strip()
        rows.append({
            "id":           str(p["id"]),
            "name":         name,
            "country":      squad_map.get(p.get("squadId"), "UNK"),
            "position":     p.get("position", ""),
            "price":        float(p.get("price") or 0),
            "status":       p.get("status", ""),
            "total_pts":    float(stats.get("totalPoints") or 0),
            "avg_pts":      float(stats.get("avgPoints") or 0),
            "form":         float(stats.get("form") or 0),
            "last_round":   float(stats.get("lastRoundPoints") or 0),
            "ownership":    float(p.get("percentSelected") or 0),
            "one_to_watch": bool(p.get("oneToWatch")),
        })

    df = pd.DataFrame(rows)
    df = df[df["price"] > 0]
    df = df[df["position"].isin(["GK", "DEF", "MID", "FWD"])]
    return df.reset_index(drop=True)


def enrich_value_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["pts_per_m"] = df["total_pts"] / df["price"].replace(0, pd.NA)

    # Pre-tournament: no points yet, so rank on price as proxy for perceived quality,
    # then blend ownership (crowd wisdom) and one_to_watch flag.
    # When the tournament starts total_pts/form will dominate naturally.
    max_pts = df["total_pts"].max() or 1
    max_form = df["form"].max() or 1
    max_own  = df["ownership"].max() or 1

    df["value_score"] = (
        0.4 * df["total_pts"]  / max_pts  +
        0.3 * df["form"]       / max_form +
        0.2 * df["ownership"]  / max_own  +
        0.1 * df["one_to_watch"].astype(float)
    ) / df["price"]

    return df


def load_or_fetch(client: FifaFantasyClient) -> pd.DataFrame:
    cache = RAW_DIR / "players_raw.json"
    if cache.exists():
        print(f"Using cached player data ({cache})")
        # Re-parse from cache via a lightweight mock
        raw = json.loads(cache.read_text())
        squad_map = _build_squad_map(client)
        rows = []
        for p in raw:
            stats = p.get("stats") or {}
            name = p.get("knownName") or f"{p.get('firstName','')} {p.get('lastName','')}".strip()
            rows.append({
                "id":           str(p["id"]),
                "name":         name,
                "country":      squad_map.get(p.get("squadId"), "UNK"),
                "position":     p.get("position", ""),
                "price":        float(p.get("price") or 0),
                "status":       p.get("status", ""),
                "total_pts":    float((p.get("stats") or {}).get("totalPoints") or 0),
                "avg_pts":      float((p.get("stats") or {}).get("avgPoints") or 0),
                "form":         float((p.get("stats") or {}).get("form") or 0),
                "last_round":   float((p.get("stats") or {}).get("lastRoundPoints") or 0),
                "ownership":    float(p.get("percentSelected") or 0),
                "one_to_watch": bool(p.get("oneToWatch")),
            })
        df = pd.DataFrame(rows)
        df = df[df["price"] > 0]
        df = df[df["position"].isin(["GK", "DEF", "MID", "FWD"])]
        df = df.reset_index(drop=True)
    else:
        df = fetch_players(client)

    return enrich_value_metrics(df)


if __name__ == "__main__":
    import os
    token = os.getenv("FIFA_SESSION_TOKEN")
    client = FifaFantasyClient(session_token=token)
    df = fetch_players(client)
    df = enrich_value_metrics(df)
    print(df.groupby("position").agg(count=("id","count"), avg_price=("price","mean")).to_string())
    print("\nTop 15 by value score:")
    print(df.sort_values("value_score", ascending=False).head(15)[
        ["name", "country", "position", "price", "ownership", "value_score"]
    ].to_string(index=False))
