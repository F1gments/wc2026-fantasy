"""
Moneyball squad optimizer using linear programming (PuLP).

Objective: maximise expected tournament points (xpts) for the starting XI,
using the official WC2026 Fantasy scoring system as the model.
"""
import pandas as pd
import pulp


# Official WC2026 Fantasy squad rules
DEFAULT_RULES = {
    "budget":      100.0,
    "squad":       {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3},
    "starting":    {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2},  # 4-4-2 default
    "max_per_country": 3,
}


def build_squad(
    df: pd.DataFrame,
    rules: dict = None,
    locked_in: list[str] = None,
    excluded: list[str] = None,
) -> dict:
    """
    Returns {
      "starting_xi": DataFrame,
      "bench": DataFrame,
      "captain": str (player name),
      "vice_captain": str,
      "total_cost": float,
      "total_xpts": float,
    }
    locked_in: list of player IDs forced into the squad
    excluded:  list of player IDs to ignore
    """
    rules = {**DEFAULT_RULES, **(rules or {})}
    locked_in = set(locked_in or [])
    excluded  = set(excluded or [])

    df = df[~df["id"].isin(excluded)].copy()

    squad_need   = rules["squad"]
    starting_need = rules["starting"]
    budget       = rules["budget"]
    max_country  = rules["max_per_country"]

    positions  = list(squad_need.keys())
    bench_need = {p: squad_need[p] - starting_need[p] for p in positions}

    df = df[df["position"].isin(positions)]

    # Filter out near-certain non-starters using price floor + ownership threshold
    # Ownership < threshold almost always means a backup who won't see minutes
    price_floors   = rules.get("price_floors",   {"GK": 4.5, "DEF": 4.0, "MID": 4.5, "FWD": 4.5})
    min_ownership  = rules.get("min_ownership",  {"GK": 1.0, "DEF": 0.0, "MID": 0.0, "FWD": 0.0})
    def is_eligible(r):
        return (r["price"]     >= price_floors.get(r["position"], 0) and
                r["ownership"] >= min_ownership.get(r["position"], 0))
    df = df[df.apply(is_eligible, axis=1)].reset_index(drop=True)

    # Use xpts if available, fall back to value_score * price (same shape)
    obj_col = "xpts" if "xpts" in df.columns else "value_score"

    prob = pulp.LpProblem("FantasySquad", pulp.LpMaximize)

    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(len(df))]
    b = [pulp.LpVariable(f"b_{i}", cat="Binary") for i in range(len(df))]

    # Objective: maximise starting XI xpts; bench weighted 10% (bench scores but doesn't count)
    prob += pulp.lpSum(
        df.loc[i, obj_col] * x[i] + 0.10 * df.loc[i, obj_col] * b[i]
        for i in range(len(df))
    )

    # Budget constraint
    prob += pulp.lpSum(df.loc[i, "price"] * (x[i] + b[i]) for i in range(len(df))) <= budget

    # Position counts
    for pos in positions:
        idx = df.index[df["position"] == pos].tolist()
        prob += pulp.lpSum(x[i] for i in idx) == starting_need[pos]
        prob += pulp.lpSum(b[i] for i in idx) == bench_need[pos]

    # Each player can only be starter OR bench
    for i in range(len(df)):
        prob += x[i] + b[i] <= 1

    # Max players per country
    for country in df["country"].unique():
        idx = df.index[df["country"] == country].tolist()
        prob += pulp.lpSum(x[i] + b[i] for i in idx) <= max_country

    # Force locked-in players
    for pid in locked_in:
        matches = df.index[df["id"] == pid].tolist()
        if matches:
            prob += x[matches[0]] + b[matches[0]] == 1

    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"Optimizer failed: {pulp.LpStatus[prob.status]}")

    xi    = df[[pulp.value(x[i]) == 1 for i in range(len(df))]].copy()
    bench = df[[pulp.value(b[i]) == 1 for i in range(len(df))]].copy()

    # Captain = most expensive in squad (game default; we confirm best pick)
    squad = pd.concat([xi, bench])
    captain      = squad.loc[squad["price"].idxmax(), "name"]
    vice_captain = squad.loc[squad["price"].nlargest(2).index[-1], "name"]

    # Suggest better captain: highest xpts in starting XI
    best_xi_xpts = xi.loc[xi[obj_col].idxmax(), "name"] if obj_col in xi.columns else captain

    return {
        "starting_xi":   xi.sort_values(["position", obj_col], ascending=[True, False]),
        "bench":         bench.sort_values(["position", obj_col], ascending=[True, False]),
        "captain":       captain,
        "vice_captain":  vice_captain,
        "captain_note":  best_xi_xpts,
        "total_cost":    squad["price"].sum(),
        "total_xpts":    xi[obj_col].sum(),
    }


def print_squad(result: dict):
    xi    = result["starting_xi"]
    bench = result["bench"]

    base  = ["name", "country", "position", "price"]
    extra = [c for c in ["xpts", "value_score", "ownership"] if c in xi.columns]
    cols  = base + extra

    def fmt(df, label):
        available = [c for c in cols if c in df.columns]
        print(f"\n{'='*12} {label} {'='*12}")
        print(df[available].to_string(index=False, float_format=lambda f: f"{f:.2f}"))

    fmt(xi, "STARTING XI")
    fmt(bench, "BENCH")

    print(f"\n  Total cost     : ${result['total_cost']:.1f}m  (budget $100m)")
    print(f"  Budget left    : ${100 - result['total_cost']:.1f}m")
    print(f"  Total XI xpts  : {result['total_xpts']:.1f} est. pts")
    print(f"\n  Captain (auto) : {result['captain']}  (most expensive)")
    if result['captain_note'] != result['captain']:
        print(f"  Best xpts pick : {result['captain_note']}  ** consider this as captain instead **")
    print(f"  Vice-Captain   : {result['vice_captain']}")
