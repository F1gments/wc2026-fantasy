"""
Export pipeline — generates JSON files in public/data/ for the static site.

Outputs:
  public/data/meta.json      last updated, coverage stats
  public/data/players.json   all 1481 players with stats + trend fields
  public/data/squad.json     optimized 15-player squad + transfer suggestions
  public/data/rounds.json    gameweek schedule from FIFA API
"""

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

PUBLIC_DATA = Path(__file__).parent.parent / "public" / "data"


def _safe(val):
    """Convert numpy/pandas types to plain Python for JSON."""
    if hasattr(val, "item"):
        return val.item()
    if hasattr(val, "tolist"):
        return val.tolist()
    return val


def export_players(df) -> list[dict]:
    records = []
    for _, row in df.iterrows():
        records.append({
            "id":           str(row.get("id", "")),
            "name":         str(row.get("name", "")),
            "country":      str(row.get("country", "")),
            "position":     str(row.get("position", "")),
            "price":        round(float(row.get("price", 0)), 1),
            "ownership":    round(float(row.get("ownership", 0)), 1),
            "status":       str(row.get("status", "")),
            # Pre-tournament estimates
            "xpts":         round(float(row.get("xpts", 0)), 1),
            "value_score":  round(float(row.get("value_score", 0)), 3),
            # Understat stats (0 until matched)
            "xg_per90":     round(float(row.get("xg_per90", 0)), 3),
            "xa_per90":     round(float(row.get("xa_per90", 0)), 3),
            "goals":        int(float(row.get("goals", 0))),
            "assists":      int(float(row.get("assists", 0))),
            "minutes":      int(float(row.get("minutes", 0))),
            # GK stats
            "save_pct":     round(float(row.get("save_pct", 0)), 1),
            "cs_per90":     round(float(row.get("cs_per90", 0)), 3),
            # Live WC stats (populated after games start)
            "wc_pts":       int(float(row.get("total_pts", 0))),
            "wc_form":      round(float(row.get("form", 0)), 1),
            "last_round":   int(float(row.get("last_round", 0))),
            # Matching metadata
            "has_stats":    bool(row.get("match_score", 0) > 0),
            "match_score":  int(float(row.get("match_score", 0))),
            "fbref_name":   str(row.get("fbref_name", "") or ""),
            "one_to_watch": bool(row.get("one_to_watch", False)),
        })
    return records


def export_squad(result: dict) -> dict:
    def fmt_player(row):
        return {
            "id":       str(row.get("id", "")),
            "name":     str(row.get("name", "")),
            "country":  str(row.get("country", "")),
            "position": str(row.get("position", "")),
            "price":    round(float(row.get("price", 0)), 1),
            "xpts":     round(float(row.get("xpts", 0)), 1),
            "wc_pts":   int(float(row.get("total_pts", 0))),
            "ownership":round(float(row.get("ownership", 0)), 1),
        }

    xi    = [fmt_player(r) for _, r in result["starting_xi"].iterrows()]
    bench = [fmt_player(r) for _, r in result["bench"].iterrows()]

    return {
        "starting_xi":   xi,
        "bench":         bench,
        "captain":       result.get("captain", ""),
        "vice_captain":  result.get("vice_captain", ""),
        "total_cost":    round(result.get("total_cost", 0), 1),
        "total_xpts":    round(result.get("total_xpts", 0), 1),
        "budget_left":   round(100 - result.get("total_cost", 0), 1),
    }


def export_meta(df) -> dict:
    total = len(df)
    matched = int((df.get("match_score", 0) > 0).sum()) if "match_score" in df.columns else 0
    return {
        "last_updated":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "total_players":  total,
        "matched_stats":  matched,
        "coverage_pct":   round(matched / total * 100, 1) if total else 0,
        "tournament_started": False,  # flip to True once MD1 kicks off
        "current_round":  0,
    }


def export_all_squads(squad_results: list[dict]) -> list[dict]:
    """Export all strategy squads to a single JSON array."""
    out = []
    for result in squad_results:
        s = export_squad(result)
        s["strategy_id"]          = result.get("strategy_id", "")
        s["strategy_name"]        = result.get("strategy_name", "")
        s["strategy_description"] = result.get("strategy_description", "")
        out.append(s)
    return out


def run(df, squad_result, rounds_data=None, all_squads=None):
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)

    players = export_players(df)
    (PUBLIC_DATA / "players.json").write_text(
        json.dumps(players, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  exported {len(players)} players -> public/data/players.json")

    squad = export_squad(squad_result)
    (PUBLIC_DATA / "squad.json").write_text(
        json.dumps(squad, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  exported squad ({len(squad['starting_xi'])} starters, "
          f"{len(squad['bench'])} bench) -> public/data/squad.json")

    meta = export_meta(df)
    (PUBLIC_DATA / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  exported meta -> public/data/meta.json")

    if all_squads:
        squads_export = export_all_squads(all_squads)
        (PUBLIC_DATA / "squads.json").write_text(
            json.dumps(squads_export, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  exported {len(squads_export)} strategy squads -> public/data/squads.json")

    if rounds_data:
        (PUBLIC_DATA / "rounds.json").write_text(
            json.dumps(rounds_data, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  exported rounds -> public/data/rounds.json")

    print(f"\n  Coverage: {meta['coverage_pct']}% of players have external stats")
    print(f"  Last updated: {meta['last_updated']}")
