"""
Tournament depth multiplier.

Estimates expected number of games a player will appear in over the whole
tournament, based on their team's probability of advancing through each round.

Replaces the crude price-based proxy in scoring.py.

Method:
  - Use FIFA ranking to estimate win probability in each knockout matchup
  - Simulate group stage: top 2 from each group advance (48 teams → 32)
  - Then R32 → R16 → QF → SF → Final
  - Expected games = sum over rounds of P(reach that round)

Group stage: all 3 group games guaranteed → 3 games minimum.
Knockout rounds: each adds 1 game weighted by P(advancing).
"""

from __future__ import annotations
try:
    from .fixture_difficulty import FIFA_RANKINGS, DEFAULT_RANK
except ImportError:
    from fixture_difficulty import FIFA_RANKINGS, DEFAULT_RANK

# Expected games contribution per round beyond group stage
# P(advance from groups) * P(win R32) * ... applied cumulatively
# Simplified: use Elo-style win probability based on ranking gap


def _win_prob(rank_a: int, rank_b: int) -> float:
    """
    Probability that team A (rank_a) beats team B (rank_b).
    Uses logistic function on rank difference.
    rank 1 = best team.
    """
    diff = rank_b - rank_a  # positive means A is better
    # Scale: 10-rank gap ≈ 65% win probability for better team
    import math
    return 1 / (1 + math.exp(-diff / 15))


def expected_games(team_abbr: str, fixture_scores: dict) -> float:
    """
    Calculate expected total games for a team's players in the tournament.

    Group stage: 3 guaranteed.
    R32 to Final: each round adds P(team reaches that round).
    """
    rank = FIFA_RANKINGS.get(team_abbr, DEFAULT_RANK)

    # --- Group stage: 3 guaranteed games ---
    base = 3.0

    # --- Estimate P(qualify from group) ---
    # Teams with rank <= 16 → high probability; weaker teams lower
    # Simplified: top 24 teams have very high (>80%) group stage survival
    if rank <= 8:
        p_qualify = 0.95
    elif rank <= 16:
        p_qualify = 0.85
    elif rank <= 24:
        p_qualify = 0.72
    elif rank <= 36:
        p_qualify = 0.55
    else:
        p_qualify = 0.38

    # --- Knockout rounds ---
    # Average opponent rank at each stage (gets harder each round)
    # Rough average opponent rank by stage for a team of given rank:
    round_probs = []
    p_current = p_qualify

    round_avg_opponents = {
        "R32": min(rank + 20, 40),   # R32: mixed opponents
        "R16": min(rank + 15, 35),   # R16: stronger field
        "QF":  min(rank + 10, 25),   # QF: elite teams
        "SF":  min(rank + 5,  15),   # SF: very strong
        "F":   min(rank + 3,  10),   # Final: best of the best
    }

    for stage, avg_opp_rank in round_avg_opponents.items():
        p_win = _win_prob(rank, avg_opp_rank)
        p_current *= p_win
        round_probs.append(p_current)

    # Expected games = base + sum of P(reaching each KO round)
    expected = base + sum(round_probs)
    return round(expected, 2)


def build_depth_table(all_abbrs: list[str], fixture_scores: dict) -> dict[str, float]:
    """Build expected games lookup for all team abbreviations."""
    return {abbr: expected_games(abbr, fixture_scores) for abbr in all_abbrs}


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from fixture_difficulty import load_fixture_scores
    fs = load_fixture_scores()
    teams = list(FIFA_RANKINGS.keys())
    table = build_depth_table(teams, fs)
    ranked = sorted(table.items(), key=lambda x: -x[1])
    print("Expected tournament games by team:")
    for abbr, games in ranked[:20]:
        rank = FIFA_RANKINGS.get(abbr, DEFAULT_RANK)
        print(f"  {abbr:4s}  rank {rank:3d}  expected {games:.2f} games")
