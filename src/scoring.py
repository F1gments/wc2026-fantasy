"""
Expected points model — official WC2026 Fantasy scoring system.

Incorporates four algorithms:
  1. Penalty taker bonus      — extra goal/pen probability for known takers
  2. Transfermarkt market value — quality signal for non-Big5 players
  3. Fixture difficulty        — opponent-adjusted CS and attack modifiers
  4. Tournament depth          — expected total games based on FIFA rankings

Scoring rules:
  All:  appearance <60min +1, 60+min +2, assist +3, yellow -1, red -2
  GK:   clean sheet +5, pen save +3, every 3 saves +1, goal +9
  DEF:  clean sheet +5, each extra goal conceded -1, goal +7
  MID:  clean sheet +1, goal +6, every 3 tackles +1, every 2 chances created +1
  FWD:  goal +5, every 2 shots on target +1
  Bonus: pen taker wins pen +2, scouting bonus +2
"""

from __future__ import annotations
import unicodedata
import re
import pandas as pd

# Lazy-loaded singletons — invalidated when rounds_played changes
_fixture_scores: dict | None = None
_depth_table:    dict | None = None
_loaded_rounds_played: int = -1


def _norm(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s))
    return re.sub(r"[^a-z0-9 ]", "", nfkd.encode("ascii", "ignore").decode().lower()).strip()


def _load_singletons(rounds_played: int = 0):
    global _fixture_scores, _depth_table, _loaded_rounds_played
    if _fixture_scores is not None and _loaded_rounds_played == rounds_played:
        return

    from algorithms.fixture_difficulty import load_fixture_scores, FIFA_RANKINGS
    from algorithms.tournament_depth import build_depth_table

    _fixture_scores = load_fixture_scores(rounds_completed=rounds_played)
    all_abbrs = list(set(list(FIFA_RANKINGS.keys()) + list(_fixture_scores.keys())))
    _depth_table = build_depth_table(all_abbrs, _fixture_scores, rounds_played=rounds_played)
    _loaded_rounds_played = rounds_played


# --- Defensive tier (base clean sheet probability before fixture adjustment) ---
DEFENSIVE_TIER: dict[str, float] = {
    "FRA": 0.85, "ESP": 0.82, "ENG": 0.80, "ARG": 0.80,
    "BRA": 0.78, "POR": 0.78, "GER": 0.76, "NED": 0.74,
    "ITA": 0.72, "URU": 0.70, "CRO": 0.70, "SUI": 0.68,
    "BEL": 0.67, "DEN": 0.66, "AUT": 0.65, "USA": 0.63,
    "CAN": 0.62, "MEX": 0.62, "MOR": 0.62, "MAR": 0.62,
    "SEN": 0.60, "JPN": 0.60, "KOR": 0.58, "AUS": 0.57,
    "POL": 0.57, "TUR": 0.56, "SCO": 0.55, "NOR": 0.55,
    "SWE": 0.54, "NGA": 0.50, "CIV": 0.50, "CMR": 0.49,
    "GHA": 0.48, "COL": 0.52, "VEN": 0.50, "CHI": 0.48,
    "PER": 0.47, "ECU": 0.47, "PAR": 0.46, "BOL": 0.44,
    "IRN": 0.52, "SAU": 0.48, "KSA": 0.48, "QAT": 0.45,
    "COD": 0.48, "ALG": 0.47, "TUN": 0.46, "EGY": 0.45,
    "CZE": 0.56, "BIH": 0.44, "RSA": 0.42, "HAI": 0.38,
    "PAN": 0.42, "CRC": 0.44, "JOR": 0.40, "CPV": 0.38,
    "NZL": 0.40, "IRQ": 0.40, "CUW": 0.36, "UZB": 0.42,
}
DEFAULT_DEF_TIER = 0.45


def expected_points(row: pd.Series, mv_lookup: dict[str, float] | None = None, rounds_played: int = 0) -> float:
    """
    Estimate total tournament points for a single player row.

    mv_lookup: {normalised_name: market_value_millions} for Transfermarkt enrichment.
    rounds_played: completed fantasy rounds — adjusts fixture difficulty to remaining games.
    """
    _load_singletons(rounds_played)

    pos     = row.get("position", "")
    price   = float(row.get("price",     0) or 0)
    country = str(row.get("country",     ""))
    own     = float(row.get("ownership", 0) or 0)
    name    = str(row.get("name",        ""))
    norm    = _norm(name)

    # --- Understat stats (0 when not matched) ---
    xg90  = float(row.get("xg_per90",  0) or 0)
    xa90  = float(row.get("xa_per90",  0) or 0)
    sv_pct = float(row.get("save_pct", 0) or 0)
    cs90   = float(row.get("cs_per90", 0) or 0)

    has_stats = xg90 > 0 or sv_pct > 0

    # --- Algorithm 1: Penalty taker bonus ---
    from algorithms.penalty_takers import get_pen_bonus
    pen_conf = get_pen_bonus(norm)
    # Extra goals from penalties: ~1 pen/4 games for confirmed taker
    pen_goal_rate = pen_conf * 0.25  # additional goals/game from pens

    # --- Algorithm 2: Transfermarkt market value ---
    market_value = 0.0
    if mv_lookup:
        market_value = mv_lookup.get(norm, 0.0)

    # --- Algorithm 3: Fixture difficulty ---
    fix = _fixture_scores.get(country, {})
    cs_fix_mod  = fix.get("cs_modifier",     1.0)
    att_fix_mod = fix.get("attack_modifier", 1.0)

    # --- Algorithm 4: Tournament depth (expected total games) ---
    n_games = _depth_table.get(country, 3.5) if _depth_table else 3.5

    # --- Base metrics ---
    def_tier    = DEFENSIVE_TIER.get(country, DEFAULT_DEF_TIER)
    own_norm    = min(own / 40.0, 1.0)

    # Adjust defensive probability with fixture difficulty
    adj_cs_prob = def_tier * cs_fix_mod
    adj_cs_prob = max(0.05, min(0.95, adj_cs_prob))

    # Appearance points: assume starters play 90 min → +2/game
    app_pts = 2.0 * n_games

    # Market value as a quality boost for players without stats
    # €60m = elite player, scale 0-1 relative to €100m ceiling
    mv_quality = min(market_value / 100.0, 1.0) if market_value > 0 else 0.0

    if pos == "GK":
        cs_pts   = 5.0 * adj_cs_prob * n_games
        if has_stats and sv_pct > 0:
            save_pts = (sv_pct / 100) * 3.5 * n_games / 3   # ~3.5 saves/game, 1pt per 3
        else:
            save_pts = (own_norm * 0.8 + mv_quality * 0.5) * n_games
        total = app_pts + cs_pts + save_pts

    elif pos == "DEF":
        cs_pts   = 5.0 * adj_cs_prob * n_games
        if has_stats:
            # Use actual xg/xa from understat
            goal_pts = (7.0 * xg90 + 3.0 * xa90) * n_games * att_fix_mod
        else:
            # Price + market value proxy
            price_quality = max(0, (price - 4.0) / 6.0)
            mv_adj        = max(price_quality, mv_quality * 0.6)
            goal_rate     = mv_adj * 0.12
            goal_pts      = (7.0 * goal_rate + 3.0 * goal_rate * 0.8) * n_games * att_fix_mod
        # Penalty taker bonus (rare for DEF but possible)
        pen_pts  = pen_conf * 2.0 * 0.25 * n_games
        total = app_pts + cs_pts + goal_pts + pen_pts

    elif pos == "MID":
        if has_stats:
            goal_pts = (6.0 * xg90 + 3.0 * xa90) * n_games * att_fix_mod
            # Chance creation bonus (~1pt per 2 chances created, proxy from xa90)
            cc_pts   = (xa90 * 1.5) * n_games
        else:
            price_quality = max(0, (price - 5.0) / 5.0)
            mv_adj        = max(price_quality, mv_quality * 0.7)
            goal_rate     = mv_adj * 0.20
            goal_pts      = (6.0 * goal_rate + 3.0 * goal_rate * 1.2) * n_games * att_fix_mod
            cc_pts        = own_norm * 0.5 * n_games
        pen_pts  = pen_conf * (5.0 * pen_goal_rate + 2.0 * pen_conf * 0.3) * n_games
        cs_pts   = 1.0 * adj_cs_prob * n_games * 0.3   # mid CS is small bonus
        total = app_pts + goal_pts + cc_pts + pen_pts + cs_pts

    elif pos == "FWD":
        if has_stats:
            goal_pts = (5.0 * (xg90 + pen_goal_rate) + 1.0 * xg90 * 2) * n_games * att_fix_mod
            ast_pts  = 3.0 * xa90 * n_games
        else:
            price_quality = max(0, (price - 4.5) / 6.0)
            mv_adj        = max(price_quality, mv_quality * 0.8)
            goal_rate     = (mv_adj * 0.35) + pen_goal_rate
            goal_pts      = (5.0 * goal_rate + 1.0 * goal_rate * 2) * n_games * att_fix_mod
            ast_pts       = 3.0 * goal_rate * 0.4 * n_games
        # Penalty taker: +2 per pen won, ~0.3 pens won per game for confirmed taker
        pen_pts  = pen_conf * 2.0 * 0.3 * n_games
        sot_pts  = own_norm * 0.4 * n_games
        total = app_pts + goal_pts + ast_pts + pen_pts + sot_pts

    else:
        total = app_pts

    return round(total, 3)


def add_expected_points(
    df: pd.DataFrame,
    mv_lookup: dict[str, float] | None = None,
    rounds_played: int = 0,
) -> pd.DataFrame:
    df = df.copy()
    df["xpts"] = df.apply(lambda r: expected_points(r, mv_lookup, rounds_played), axis=1)
    df["value_score"] = df["xpts"] / df["price"].replace(0, pd.NA)
    return df.fillna(0)


def blend_wc_form(df: pd.DataFrame, rounds_played: int) -> pd.DataFrame:
    """
    After real WC games are played, blend actual performance into xpts.

    wc_weight grows with each completed round:
      MD1 done: 35%  real WC signal, 65% pre-tournament model
      MD2 done: 50%  real WC signal, 50% pre-tournament model
      MD3 done: 65%  real WC signal, 35% pre-tournament model

    The actual scoring rate (pts/round) is projected across the full
    expected tournament length (~4.5 games on average) and blended in.
    Players who didn't play (0 pts) are naturally penalised.
    """
    if rounds_played <= 0:
        return df

    wc_weight = min(0.20 + 0.15 * rounds_played, 0.85)

    # Project current WC scoring rate to full tournament
    EXPECTED_TOTAL_ROUNDS = 4.5   # 3 group (with rest risk) + ~1.5 KO avg
    pts_per_round = df["total_pts"] / rounds_played
    projected_wc = pts_per_round * EXPECTED_TOTAL_ROUNDS

    df = df.copy()
    df["model_xpts"] = df["xpts"]   # preserve pre-blend estimate
    df["xpts"] = (1 - wc_weight) * df["xpts"] + wc_weight * projected_wc
    df["xpts"] = df["xpts"].clip(lower=0)
    df["remaining_xpts"] = (df["xpts"] - df["total_pts"]).clip(lower=0)
    df["value_score"] = df["xpts"] / df["price"].replace(0, pd.NA)
    return df.fillna(0)
