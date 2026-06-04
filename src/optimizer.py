"""
Moneyball-style squad optimizer using linear programming (PuLP).

Selects an 11-player starting XI + 4 bench players that maximises
value_score subject to budget, position, and per-country constraints.
"""
import pandas as pd
import pulp


# Squad rules from play.fifa.com: $100m budget, 15 players (2GK 5DEF 5MID 3FWD)
# Starting XI selection is flexible within those 15 — optimizer picks best 11
DEFAULT_RULES = {
    "budget": 100.0,
    "squad": {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3},
    "starting": {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2},  # default 4-4-2
    "max_per_country": 3,
}


def build_squad(
    df: pd.DataFrame,
    rules: dict = None,
    locked_in: list[str] = None,
    excluded: list[str] = None,
) -> dict:
    """
    Returns {"starting_xi": DataFrame, "bench": DataFrame, "total_cost": float, "total_score": float}

    locked_in:  list of player IDs that must be included
    excluded:   list of player IDs to exclude
    """
    rules = {**DEFAULT_RULES, **(rules or {})}
    locked_in = set(locked_in or [])
    excluded = set(excluded or [])

    df = df[~df["id"].isin(excluded)].copy()

    squad_need   = rules["squad"]      # total per position (e.g. GK:2, DEF:5 ...)
    starting_need = rules["starting"]  # starters per position (e.g. GK:1, DEF:4 ...)
    budget = rules["budget"]
    max_country = rules["max_per_country"]

    positions = list(squad_need.keys())
    bench_need = {p: squad_need[p] - starting_need[p] for p in positions}

    # Only keep players in known positions
    df = df[df["position"].isin(positions)].reset_index(drop=True)

    prob = pulp.LpProblem("FantasySquad", pulp.LpMaximize)

    # x[i] = 1 if player i is in starting XI
    # b[i] = 1 if player i is on bench
    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(len(df))]
    b = [pulp.LpVariable(f"b_{i}", cat="Binary") for i in range(len(df))]

    # Objective: maximise starting XI value_score (bench weighted less)
    prob += pulp.lpSum(
        df.loc[i, "value_score"] * x[i] + 0.1 * df.loc[i, "value_score"] * b[i]
        for i in range(len(df))
    )

    # Budget
    prob += pulp.lpSum((df.loc[i, "price"]) * (x[i] + b[i]) for i in range(len(df))) <= budget

    # Position counts
    for pos in positions:
        idx = df.index[df["position"] == pos].tolist()
        prob += pulp.lpSum(x[i] for i in idx) == starting_need[pos]
        prob += pulp.lpSum(b[i] for i in idx) == bench_need[pos]

    # A player can only be starter OR bench, not both
    for i in range(len(df)):
        prob += x[i] + b[i] <= 1

    # Max players per country
    countries = df["country"].unique()
    for country in countries:
        idx = df.index[df["country"] == country].tolist()
        prob += pulp.lpSum(x[i] + b[i] for i in idx) <= max_country

    # Lock in required players
    for pid in locked_in:
        matches = df.index[df["id"] == pid].tolist()
        if matches:
            i = matches[0]
            prob += x[i] + b[i] == 1

    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"Optimizer failed: {pulp.LpStatus[prob.status]}")

    xi_mask = [pulp.value(x[i]) == 1 for i in range(len(df))]
    bn_mask = [pulp.value(b[i]) == 1 for i in range(len(df))]

    xi = df[xi_mask].copy()
    bench = df[bn_mask].copy()

    return {
        "starting_xi": xi.sort_values("position"),
        "bench": bench.sort_values("position"),
        "total_cost": float(pulp.value(
            pulp.lpSum((df.loc[i, "price"]) * (x[i] + b[i]) for i in range(len(df)))
        )),
        "total_score": float(pulp.value(prob.objective)),
    }


def print_squad(result: dict):
    cols = ["name", "country", "position", "price", "total_pts", "value_score"]

    def fmt(df):
        return df[cols].to_string(index=False, float_format=lambda f: f"{f:.2f}")

    print("\n=== STARTING XI ===")
    print(fmt(result["starting_xi"]))
    print(f"\n=== BENCH ===")
    print(fmt(result["bench"]))
    cost = result["starting_xi"]["price"].sum() + result["bench"]["price"].sum()
    print(f"\nTotal cost : {cost:.1f}")
    print(f"Budget remaining: {DEFAULT_RULES['budget'] - cost:.1f}")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from data_fetcher import load_or_fetch
    from fifa_client import FifaFantasyClient

    token = os.getenv("FIFA_SESSION_TOKEN")
    client = FifaFantasyClient(session_token=token)
    df = load_or_fetch(client)
    result = build_squad(df)
    print_squad(result)
