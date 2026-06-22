"""
Fixture difficulty algorithm.

Parses rounds.json group stage fixtures and builds per-team difficulty scores.

Outputs:
  team_fixture_scores[abbr] = {
      "avg_opponent_rank": float,     # lower = harder opponents
      "cs_modifier":       float,     # multiplier on clean sheet probability (>1 easier, <1 harder)
      "attack_modifier":   float,     # multiplier on expected goals (>1 easier opposition)
      "fixtures":          list[dict] # individual match info
  }

Logic:
  - Use FIFA ranking as proxy for opponent strength
  - Teams ranked 1-10 = very hard (cs_modifier 0.6), 11-20 = hard (0.75),
    21-32 = medium (0.9), 33-48 = easy (1.1)
  - Attack modifier is inverse: easy opposition → more likely to score
"""

import json
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"

# FIFA World Rankings (approximate, June 2026)
# Source: FIFA ranking data + known tournament seeding
FIFA_RANKINGS: dict[str, int] = {
    "FRA": 2,   "BRA": 3,   "ENG": 4,   "ARG": 1,   "POR": 6,
    "ESP": 7,   "NED": 8,   "BEL": 9,   "GER": 11,  "ITA": 10,
    "CRO": 12,  "URU": 13,  "COL": 14,  "USA": 15,  "MEX": 16,
    "MOR": 17,  "SEN": 18,  "DEN": 19,  "SUI": 20,  "JPN": 21,
    "AUT": 22,  "AUS": 23,  "KOR": 24,  "NOR": 25,  "POL": 26,
    "TUR": 27,  "SWE": 28,  "SCO": 29,  "NGA": 30,  "CAN": 31,
    "CIV": 32,  "GHA": 33,  "CMR": 34,  "MAR": 35,  "EGY": 36,
    "ALG": 37,  "TUN": 38,  "CZE": 39,  "HUN": 40,  "SRB": 41,
    "IRN": 42,  "SAU": 43,  "QAT": 44,  "UZB": 45,  "JOR": 46,
    "CPV": 47,  "NZL": 48,  "HAI": 56,  "RSA": 58,  "PAN": 62,
    "BOL": 65,  "PAR": 63,  "ECU": 50,  "VEN": 55,  "CHI": 57,
    "PER": 53,  "CRC": 54,  "HON": 72,  "GTM": 73,  "JAM": 61,
    "TRI": 68,  "BIH": 64,  "COD": 49,  "CUW": 80,  "IRQ": 60,
    "KSA": 43,
}
DEFAULT_RANK = 55


def _rank_to_difficulty(rank: int) -> tuple[float, float]:
    """Returns (cs_modifier, attack_modifier) based on opponent FIFA rank."""
    if rank <= 10:
        return 0.60, 0.70   # very hard opponent: fewer CS, fewer goals
    elif rank <= 20:
        return 0.78, 0.85
    elif rank <= 32:
        return 0.92, 0.95
    elif rank <= 45:
        return 1.08, 1.10
    else:
        return 1.20, 1.25   # easy opponent: more CS, more goals


def build_fixture_scores(rounds_data: list[dict], rounds_completed: int = 0) -> dict[str, dict]:
    """
    Build per-team fixture difficulty from group stage rounds (rounds 1-3).
    rounds_completed: skip rounds already played — only model remaining games.
    Returns dict keyed by team abbr.
    """
    team_fixtures: dict[str, list[dict]] = {}

    for rnd in rounds_data:
        rnd_id = rnd.get("id", 99)
        # WC 2026: rounds 1-3 = group stage (MD1/MD2/MD3), rounds 4+ = KO
        if rnd_id > 3:
            continue
        # Skip already-completed rounds — actual points cover those games
        if rnd_id <= rounds_completed:
            continue
        for match in rnd.get("tournaments", []):
            home = match.get("homeSquadAbbr", "")
            away = match.get("awaySquadAbbr", "")
            date = match.get("date", "")[:10]

            for team, opp in [(home, away), (away, home)]:
                if not team:
                    continue
                if team not in team_fixtures:
                    team_fixtures[team] = []
                opp_rank = FIFA_RANKINGS.get(opp, DEFAULT_RANK)
                cs_mod, att_mod = _rank_to_difficulty(opp_rank)
                team_fixtures[team].append({
                    "opponent":      opp,
                    "opponent_rank": opp_rank,
                    "date":          date,
                    "cs_modifier":   cs_mod,
                    "attack_modifier": att_mod,
                })

    scores = {}
    for team, fixtures in team_fixtures.items():
        if not fixtures:
            continue
        avg_rank   = sum(f["opponent_rank"]   for f in fixtures) / len(fixtures)
        avg_cs     = sum(f["cs_modifier"]     for f in fixtures) / len(fixtures)
        avg_att    = sum(f["attack_modifier"] for f in fixtures) / len(fixtures)
        scores[team] = {
            "avg_opponent_rank": round(avg_rank, 1),
            "cs_modifier":       round(avg_cs, 3),
            "attack_modifier":   round(avg_att, 3),
            "n_group_fixtures":  len(fixtures),
            "fixtures":          fixtures,
        }

    return scores


def load_fixture_scores(rounds_completed: int = 0) -> dict[str, dict]:
    """Load from cached rounds.json, filtering to remaining group fixtures."""
    rounds_path = CACHE_DIR / "rounds.json"
    if not rounds_path.exists():
        return {}
    rounds_data = json.loads(rounds_path.read_text())
    return build_fixture_scores(rounds_data, rounds_completed=rounds_completed)


if __name__ == "__main__":
    scores = load_fixture_scores()
    # Print hardest and easiest fixtures
    ranked = sorted(scores.items(), key=lambda x: x[1]["avg_opponent_rank"])
    print("HARDEST group draws (highest ranked opponents):")
    for abbr, s in ranked[:10]:
        print(f"  {abbr:4s}  avg opp rank {s['avg_opponent_rank']:4.0f}  "
              f"CS mod {s['cs_modifier']:.2f}  Att mod {s['attack_modifier']:.2f}")
    print("\nEASIEST group draws:")
    for abbr, s in ranked[-10:]:
        print(f"  {abbr:4s}  avg opp rank {s['avg_opponent_rank']:4.0f}  "
              f"CS mod {s['cs_modifier']:.2f}  Att mod {s['attack_modifier']:.2f}")
