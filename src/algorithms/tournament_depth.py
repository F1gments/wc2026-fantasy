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


def expected_games(team_abbr: str, fixture_scores: dict, rounds_played: int = 0) -> float:
    """
    Calculate expected total games for a team's players in the tournament.

    WC 2026 format: 48 teams in 16 groups of 3. Best 8 third-placed teams also
    advance, meaning top teams will rest stars in Game 3 once qualification is
    secured — often after just 2 group games.

    Group stage: 3 games, but game 3 is discounted for elite teams (rest risk).
    R32 to Final: each round adds P(team reaches that round).
    """
    rank = FIFA_RANKINGS.get(team_abbr, DEFAULT_RANK)

    # --- Game 3 rest risk ---
    # WC 2026: even 3rd place can qualify (best 8 of 16 groups). Top teams
    # typically clinch top-2 after 2 wins and rotate heavily in game 3.
    if rank <= 8:
        game3_play_prob = 0.55   # ARG/BRA/FRA/ENG — heavy rotation expected
    elif rank <= 16:
        game3_play_prob = 0.72   # ESP/NED/POR/GER — moderate rest risk
    elif rank <= 24:
        game3_play_prob = 0.88   # Solid teams, some rotation possible
    else:
        game3_play_prob = 1.0    # Weaker teams can't afford to rotate

    # Group expected total: games 1+2 are full intensity; game 3 carries rest risk
    # Formula holds regardless of rounds_played (2 certain + 1 uncertain)
    games_played = min(rounds_played, 3)
    if games_played >= 3:
        base = 3.0
    else:
        base = 2.0 + game3_play_prob

    # --- Estimate P(qualify from group) ---
    # Top 2 from each group advance; best 8 third-placed also qualify
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


def build_depth_table(all_abbrs: list[str], fixture_scores: dict, rounds_played: int = 0) -> dict[str, float]:
    """Build expected games lookup for all team abbreviations."""
    return {abbr: expected_games(abbr, fixture_scores, rounds_played) for abbr in all_abbrs}


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from fixture_difficulty import load_fixture_scores
    fs = load_fixture_scores()
    teams = list(FIFA_RANKINGS.keys())
    table = build_depth_table(teams, fs, rounds_played=0)
    ranked = sorted(table.items(), key=lambda x: -x[1])
    print("Expected tournament games by team:")
    for abbr, games in ranked[:20]:
        rank = FIFA_RANKINGS.get(abbr, DEFAULT_RANK)
        print(f"  {abbr:4s}  rank {rank:3d}  expected {games:.2f} games")
