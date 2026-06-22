"""
Transfer recommendation engine.

After each completed gameweek, generates per-position ranked lists of:
  - Top picks: best available players by blended xpts
  - Rising stars: players whose actual WC form exceeds pre-tournament model
  - Underperformers: players whose WC form is significantly below model

Exported to public/data/transfers.json for the Transfer Advisor tab.
"""

from __future__ import annotations
import pandas as pd


def _safe(val):
    if hasattr(val, "item"):
        return val.item()
    if hasattr(val, "tolist"):
        return val.tolist()
    return val


def _player_dict(row: pd.Series) -> dict:
    return {
        "id":             str(row.get("id", "")),
        "name":           str(row.get("name", "")),
        "country":        str(row.get("country", "")),
        "position":       str(row.get("position", "")),
        "price":          round(float(row.get("price", 0)), 1),
        "ownership":      round(float(row.get("ownership", 0)), 1),
        "xpts":           round(float(row.get("xpts", 0)), 1),
        "model_xpts":     round(float(row.get("model_xpts", row.get("xpts", 0))), 1),
        "remaining_xpts": round(float(row.get("remaining_xpts", row.get("xpts", 0))), 1),
        "wc_pts":         int(float(row.get("total_pts", 0))),
        "last_round":     int(float(row.get("last_round", 0))),
        "wc_form":        round(float(row.get("form", 0)), 1),
        "value":          round(float(row.get("value_score", 0)), 3),
        "one_to_watch":   bool(row.get("one_to_watch", False)),
    }


def generate_transfer_report(df: pd.DataFrame, rounds_played: int = 0) -> dict:
    """
    Build the transfer advisor payload for all positions.

    Returns {
      "rounds_played": int,
      "wc_blend_weight": float,
      "GK": {"top_picks": [...], "rising": [...], "falling": [...]},
      "DEF": {...},
      "MID": {...},
      "FWD": {...},
    }
    """
    wc_weight = round(min(0.20 + 0.15 * rounds_played, 0.85), 2) if rounds_played > 0 else 0.0

    positions = {
        "GK":  {"top_n": 6,  "price_floor": 4.5},
        "DEF": {"top_n": 10, "price_floor": 4.0},
        "MID": {"top_n": 10, "price_floor": 4.5},
        "FWD": {"top_n": 8,  "price_floor": 4.5},
    }

    out: dict = {
        "rounds_played":   rounds_played,
        "wc_blend_weight": wc_weight,
    }

    has_wc_data = rounds_played > 0 and "model_xpts" in df.columns

    for pos, cfg in positions.items():
        pos_df = df[
            (df["position"] == pos) &
            (df["price"] >= cfg["price_floor"])
        ].copy()

        if pos_df.empty:
            out[pos] = {"top_picks": [], "rising": [], "falling": []}
            continue

        # --- Top picks: best blended xpts ---
        top_picks = (
            pos_df
            .nlargest(cfg["top_n"], "xpts")
            .apply(_player_dict, axis=1)
            .tolist()
        )

        # --- Rising / falling: compare model vs actual WC form ---
        if has_wc_data:
            # Only for players who have played at least 1 game (wc_pts > 0)
            active = pos_df[pos_df["total_pts"] > 0].copy()
            if not active.empty:
                active["form_delta"] = active["xpts"] - active["model_xpts"]

                rising = (
                    active[active["form_delta"] > 0]
                    .nlargest(5, "form_delta")
                    .apply(_player_dict, axis=1)
                    .tolist()
                )
                # Add the delta to each record
                for r, row in zip(rising, active[active["form_delta"] > 0].nlargest(5, "form_delta").itertuples()):
                    r["form_delta"] = round(float(row.form_delta), 1)

                falling = (
                    active[active["form_delta"] < 0]
                    .nsmallest(5, "form_delta")
                    .apply(_player_dict, axis=1)
                    .tolist()
                )
                for r, row in zip(falling, active[active["form_delta"] < 0].nsmallest(5, "form_delta").itertuples()):
                    r["form_delta"] = round(float(row.form_delta), 1)
            else:
                rising, falling = [], []

            # --- Sell targets: players in squad who dropped the most vs model ---
            # (everyone could be in a squad, so just list the biggest underperformers)
            sell_targets = (
                pos_df[pos_df["total_pts"] == 0]   # didn't score = red flag
                .nlargest(5, "model_xpts")          # high pre-tournament expectation, 0 pts
                .apply(_player_dict, axis=1)
                .tolist()
            ) if has_wc_data else []
        else:
            rising, falling, sell_targets = [], [], []

        out[pos] = {
            "top_picks":    top_picks,
            "rising":       rising,
            "falling":      falling,
            "sell_targets": sell_targets,
        }

    return out
