"""
Fetch FIFA fantasy player list, enrich with FBref club/international stats,
and calculate position-specific Moneyball value scores.
"""

import json
import sys
import os
import pandas as pd
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
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
            "id":          str(p["id"]),
            "name":        name,
            "country":     squad_map.get(p.get("squadId"), "UNK"),
            "position":    p.get("position", ""),
            "price":       float(p.get("price") or 0),
            "status":      p.get("status", ""),
            "total_pts":   float(stats.get("totalPoints") or 0),
            "avg_pts":     float(stats.get("avgPoints") or 0),
            "form":        float(stats.get("form") or 0),
            "last_round":  float(stats.get("lastRoundPoints") or 0),
            "ownership":   float(p.get("percentSelected") or 0),
            "one_to_watch": bool(p.get("oneToWatch")),
        })

    df = pd.DataFrame(rows)
    df = df[df["price"] > 0]
    df = df[df["position"].isin(["GK", "DEF", "MID", "FWD"])]
    return df.reset_index(drop=True)


def enrich_with_external_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Outfield stats: understat.com (xG, xA, goals, assists, minutes — Big 5 leagues)
    GK stats:       FBref (save%, clean sheets, PSxG — gracefully skipped on 403)
    Both are fuzzy-matched onto the FIFA player list by name + nationality.
    """
    from scrapers.understat import fetch_all_leagues
    from scrapers.fbref import fetch_gk_stats
    from match_players import build_fbref_lookup, match

    print("Fetching understat outfield stats (Big 5 leagues)...")
    outfield_df = fetch_all_leagues()

    print("Fetching FBref GK stats...")
    gk_df = fetch_gk_stats()

    print("Building combined lookup...")
    # build_fbref_lookup expects outfield + gk DataFrames; pass empty frames for
    # intl_out/intl_gk (understat doesn't have international data)
    empty = pd.DataFrame()
    lookup = build_fbref_lookup(
        outfield=outfield_df,
        goalkeep=gk_df if not gk_df.empty else empty,
        intl_out=empty,
        intl_gk=empty,
    )

    print(f"Matching {len(df)} FIFA players against {len(lookup)} stat rows...")
    df = match(df, lookup)

    matched = (df["match_score"] > 0).sum()
    print(f"  Matched: {matched}/{len(df)} players ({matched/len(df)*100:.1f}%)")
    return df


def enrich_value_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute position-specific Moneyball value scores.

    GK  : (save_pct * 0.4 + cs_per90 * 0.4 + psxg_diff_p90_norm * 0.2) / price
    DEF : (clean_sheets/90 * 0.3 + prog_passes/90 * 0.3 + xag/90 * 0.2 + goals+assists/90 * 0.2) / price
    MID : (xg_per90 * 0.3 + xa_per90 * 0.3 + prog_passes/90 * 0.2 + prog_carries/90 * 0.2) / price
    FWD : (xg_per90 * 0.5 + xa_per90 * 0.25 + shots_on_tgt/90 * 0.25) / price

    Pre-tournament fallback (when all fbref stats = 0):
    blends ownership and one_to_watch so the optimizer still picks recognisable names.
    """
    df = df.copy()

    has_stats = df.get("xg_per90") is not None

    if has_stats:
        def safe(col):
            if col in df.columns:
                s = pd.to_numeric(df[col], errors="coerce").fillna(0)
                m = s.max()
                return s / m if m > 0 else s
            return pd.Series(0, index=df.index)

        gk_mask  = df["position"] == "GK"
        def_mask = df["position"] == "DEF"
        mid_mask = df["position"] == "MID"
        fwd_mask = df["position"] == "FWD"

        score = pd.Series(0.0, index=df.index)

        # GK
        score[gk_mask] = (
            safe("save_pct")[gk_mask]       * 0.40 +
            safe("cs_per90")[gk_mask]       * 0.40 +
            safe("psxg_diff_p90")[gk_mask]  * 0.20
        )

        # DEF
        score[def_mask] = (
            safe("cs_per90")[def_mask]    * 0.30 +
            safe("xa_per90")[def_mask]    * 0.25 +
            safe("xg_per90")[def_mask]    * 0.20 +
            safe("prog_passes")[def_mask] * 0.15 +
            safe("prog_carries")[def_mask]* 0.10
        )

        # MID
        score[mid_mask] = (
            safe("xg_per90")[mid_mask]     * 0.30 +
            safe("xa_per90")[mid_mask]     * 0.30 +
            safe("prog_passes")[mid_mask]  * 0.20 +
            safe("prog_carries")[mid_mask] * 0.20
        )

        # FWD
        score[fwd_mask] = (
            safe("xg_per90")[fwd_mask]        * 0.50 +
            safe("xa_per90")[fwd_mask]         * 0.25 +
            safe("shots_on_tgt")[fwd_mask]     * 0.25
        )

        # Blend: 70% statistical score, 30% crowd wisdom (ownership)
        # — so elite players with no Big5 data aren't totally invisible
        max_own = df["ownership"].max() or 1
        crowd = df["ownership"] / max_own

        df["stat_score"]  = score / df["price"].replace(0, pd.NA)
        df["crowd_score"] = crowd / df["price"].replace(0, pd.NA)
        df["value_score"] = (0.70 * df["stat_score"].fillna(0) +
                             0.30 * df["crowd_score"].fillna(0))

    else:
        # No FBref data available — fall back to ownership only
        max_own = df["ownership"].max() or 1
        df["value_score"] = (
            0.7 * df["ownership"] / max_own +
            0.3 * df["one_to_watch"].astype(float)
        ) / df["price"].replace(0, pd.NA)

    df["pts_per_m"] = df["total_pts"] / df["price"].replace(0, pd.NA)
    return df.fillna(0)


def load_or_fetch(client: FifaFantasyClient, use_fbref: bool = True) -> pd.DataFrame:
    raw_cache = RAW_DIR / "players_raw.json"
    if raw_cache.exists():
        print(f"Using cached FIFA player data")
        raw = json.loads(raw_cache.read_text())
        squad_map = _build_squad_map(client)
        rows = []
        for p in raw:
            stats = p.get("stats") or {}
            name = p.get("knownName") or f"{p.get('firstName','')} {p.get('lastName','')}".strip()
            rows.append({
                "id":          str(p["id"]),
                "name":        name,
                "country":     squad_map.get(p.get("squadId"), "UNK"),
                "position":    p.get("position", ""),
                "price":       float(p.get("price") or 0),
                "status":      p.get("status", ""),
                "total_pts":   float(stats.get("totalPoints") or 0),
                "avg_pts":     float(stats.get("avgPoints") or 0),
                "form":        float(stats.get("form") or 0),
                "last_round":  float(stats.get("lastRoundPoints") or 0),
                "ownership":   float(p.get("percentSelected") or 0),
                "one_to_watch": bool(p.get("oneToWatch")),
            })
        df = pd.DataFrame(rows)
        df = df[df["price"] > 0]
        df = df[df["position"].isin(["GK", "DEF", "MID", "FWD"])]
        df = df.reset_index(drop=True)
    else:
        df = fetch_players(client)

    if use_fbref:
        df = enrich_with_external_stats(df)

    # Build Transfermarkt market value lookup for non-Big5 players
    mv_lookup = _build_mv_lookup(df)

    # Apply scoring model with all four algorithms
    from scoring import add_expected_points
    df = add_expected_points(df, mv_lookup=mv_lookup)

    return df


def _build_mv_lookup(df: pd.DataFrame) -> dict[str, float]:
    """
    Fetch Transfermarkt market values for players missing understat stats.
    Caches aggressively — only fetches players not already in cache.
    Returns {normalised_name: market_value_m}.
    """
    import unicodedata, re
    from pathlib import Path

    cache_path = Path(__file__).parent.parent / "data" / "cache" / "transfermarkt_mv.json"

    # Load existing cache
    mv_cache: dict[str, float] = {}
    if cache_path.exists():
        import json
        try:
            raw = json.loads(cache_path.read_text())
            # Support both {name: value} and list-of-dicts formats
            if isinstance(raw, dict):
                mv_cache = raw
            elif isinstance(raw, list):
                for item in raw:
                    n = item.get("tm_name", "")
                    v = item.get("market_value_m", 0)
                    if n:
                        mv_cache[_norm_name(n)] = float(v or 0)
        except Exception:
            pass

    def _norm_name(s):
        nfkd = unicodedata.normalize("NFKD", str(s))
        return re.sub(r"[^a-z0-9 ]", "", nfkd.encode("ascii", "ignore").decode().lower()).strip()

    if mv_cache:
        print(f"  Using {len(mv_cache)} cached Transfermarkt market values")

    # Build lookup from cache
    lookup = {}
    for _, row in df.iterrows():
        key = _norm_name(str(row.get("name", "")))
        if key in mv_cache:
            lookup[key] = mv_cache[key]

    return lookup


if __name__ == "__main__":
    token = os.getenv("FIFA_SESSION_TOKEN")
    client = FifaFantasyClient(session_token=token)
    df = load_or_fetch(client)
    print("\nPosition breakdown:")
    print(df.groupby("position").agg(
        count=("id", "count"),
        matched=("match_score", lambda x: (x > 0).sum()),
        avg_price=("price", "mean"),
    ).to_string())
    print("\nTop 20 by value score:")
    cols = ["name", "country", "position", "price", "xg_per90", "xa_per90", "ownership", "value_score"]
    available = [c for c in cols if c in df.columns]
    print(df.sort_values("value_score", ascending=False).head(20)[available].to_string(index=False))
