"""
Expected points model based on the official WC2026 Fantasy scoring system.

Scoring rules:
  All:   appearance <60min +1, 60+min +2, assist +3, yellow -1, red -2
  GK:    clean sheet +5, pen save +3, every 3 saves +1, goal +9
  DEF:   clean sheet +5, each extra goal conceded -1, goal +7
  MID:   clean sheet +1, goal +6, every 3 tackles +1, every 2 chances created +1
  FWD:   goal +5, every 2 shots on target +1

Because we have no WC-specific stats yet, we use:
  - Ownership % as the crowd's WC-specific quality signal
  - Defensive tier per country as a proxy for clean-sheet probability
  - Price as a proxy for attacking output (FIFA prices reflect expected scoring)
"""

import pandas as pd

# Rough clean-sheet probability tiers for group stage
# Based on WC qualifying defensive records and squad quality
# Scale: 0.0 (open/weak) → 1.0 (elite defence)
DEFENSIVE_TIER: dict[str, float] = {
    # Elite
    "FRA": 0.85, "ESP": 0.82, "ENG": 0.80, "ARG": 0.80,
    "BRA": 0.78, "POR": 0.78, "GER": 0.76, "NED": 0.74,
    # Strong
    "ITA": 0.72, "URU": 0.70, "CRO": 0.70, "SUI": 0.68,
    "BEL": 0.67, "DEN": 0.66, "AUT": 0.65, "USA": 0.63,
    "CAN": 0.62, "MEX": 0.62, "MOR": 0.62, "SEN": 0.60,
    "JPN": 0.60, "KOR": 0.58, "AUS": 0.57, "POL": 0.57,
    "TUR": 0.56, "SCO": 0.55, "NOR": 0.55, "SWE": 0.54,
    # Average
    "NGA": 0.50, "CIV": 0.50, "CMR": 0.49, "GHA": 0.48,
    "COL": 0.52, "VEN": 0.50, "CHI": 0.48, "PER": 0.47,
    "ECU": 0.47, "PAR": 0.46, "BOL": 0.44,
    "IRN": 0.52, "SAU": 0.48, "QAT": 0.45,
}
DEFAULT_DEF_TIER = 0.45


# How many matches expected per player (group = 3 guaranteed, favs go deeper)
# Simple proxy: use price as depth-of-run indicator (FIFA priced strong nations higher)
def matches_expected(price: float) -> float:
    """Rough expected matches based on price tier (proxy for team quality)."""
    if price >= 9.0:
        return 5.5   # elite: expect QF+
    elif price >= 7.0:
        return 4.5   # strong: expect R16
    elif price >= 5.5:
        return 3.8   # solid: expect R32
    else:
        return 3.0   # group stage minimum


def expected_points(row: pd.Series) -> float:
    """
    Estimate total tournament points for a player row.
    Returns a float used as the optimisation objective.
    """
    pos     = row.get("position", "")
    price   = float(row.get("price", 0) or 0)
    country = str(row.get("country", ""))
    own     = float(row.get("ownership", 0) or 0)  # 0-100 %

    def_tier = DEFENSIVE_TIER.get(country, DEFAULT_DEF_TIER)
    n_games  = matches_expected(price)

    # Appearance points: assume starters play 90 min → +2/game
    app_pts = 2 * n_games

    # Ownership normalised to 0-1 (crowd quality signal)
    own_norm = min(own / 40.0, 1.0)  # 40% ownership = maxed signal

    if pos == "GK":
        # Clean sheet: +5, ~def_tier probability per game
        cs_pts    = 5 * def_tier * n_games
        # Saves bonus: avg ~3.5 saves/game → ~1 bonus point/game for good keepers
        save_pts  = own_norm * 1.0 * n_games
        total = app_pts + cs_pts + save_pts

    elif pos == "DEF":
        # Clean sheet: +5 per game with def probability
        cs_pts    = 5 * def_tier * n_games
        # Goals: attacking DEFs (high price) score more — proxy with price
        goal_rate = max(0, (price - 4.0) / 6.0) * 0.12   # goals per game
        goal_pts  = 7 * goal_rate * n_games
        # Assists
        ast_pts   = 3 * goal_rate * 0.8 * n_games
        total = app_pts + cs_pts + goal_pts + ast_pts

    elif pos == "MID":
        # Goals: high price = more attacking MID
        goal_rate = max(0, (price - 5.0) / 5.0) * 0.20
        goal_pts  = 6 * goal_rate * n_games
        # Assists
        ast_pts   = 3 * goal_rate * 1.2 * n_games
        # Chances created bonus: ~0.5 pts/game for attacking MIDs
        cc_pts    = own_norm * 0.5 * n_games
        # Mild CS bonus
        cs_pts    = 1 * def_tier * n_games * 0.3
        total = app_pts + goal_pts + ast_pts + cc_pts + cs_pts

    elif pos == "FWD":
        # Goals: price heavily predicts FWD output
        goal_rate = max(0, (price - 4.5) / 6.0) * 0.35
        goal_pts  = 5 * goal_rate * n_games
        # Shots on target bonus (~1 SOT bonus/2 games for regular starters)
        sot_pts   = own_norm * 0.5 * n_games
        ast_pts   = 3 * goal_rate * 0.4 * n_games
        total = app_pts + goal_pts + sot_pts + ast_pts

    else:
        total = app_pts

    return round(total, 3)


def add_expected_points(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["xpts"] = df.apply(expected_points, axis=1)
    df["value_score"] = df["xpts"] / df["price"].replace(0, pd.NA)
    return df.fillna(0)
