"""
Entry point. Usage:
  python src/main.py explore           # probe API endpoints
  python src/main.py fetch             # download FIFA players + scrape FBref stats
  python src/main.py fetch --no-fbref  # fetch FIFA players only (faster, no FBref)
  python src/main.py build             # run Moneyball optimizer and print team
  python src/main.py join <CODE>       # join work league
  python src/main.py clear-cache       # delete all cached data and re-fetch fresh
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from fifa_client import FifaFantasyClient, explore_api
from data_fetcher import load_or_fetch
from optimizer import build_squad, print_squad


def get_client():
    token = os.getenv("FIFA_SESSION_TOKEN")
    if not token:
        print("WARNING: FIFA_SESSION_TOKEN not set — unauthenticated requests may fail.")
        print("Set it in .env or as an environment variable.")
    return FifaFantasyClient(session_token=token)


def cmd_explore(_args):
    explore_api()


def cmd_fetch(args):
    use_fbref = "--no-fbref" not in args
    client = get_client()

    # Force fresh FIFA data if --refresh flag present
    if "--refresh" in args:
        from pathlib import Path
        cache = Path(__file__).parent.parent / "data" / "raw" / "players_raw.json"
        if cache.exists():
            cache.unlink()
            print("Cleared FIFA player cache.")

    df = load_or_fetch(client, use_fbref=use_fbref)

    print(f"\nPlayers loaded: {len(df)}")
    agg = df.groupby("position").agg(
        count=("id", "count"),
        matched=("match_score", lambda x: (x > 0).sum()) if "match_score" in df.columns else ("id", "count"),
        avg_price=("price", "mean"),
    )
    print(agg.to_string())

    print("\nTop 20 by value score:")
    stat_cols = ["xg_per90", "xa_per90", "cs_per90"]
    base = ["name", "country", "position", "price", "ownership", "value_score"]
    cols = base + [c for c in stat_cols if c in df.columns]
    print(df.sort_values("value_score", ascending=False).head(20)[cols].to_string(index=False, float_format=lambda f: f"{f:.3f}"))


def cmd_build(args):
    use_fbref = "--no-fbref" not in args
    client = get_client()
    df = load_or_fetch(client, use_fbref=use_fbref)
    result = build_squad(df)
    print_squad(result)


def cmd_join(args):
    if not args:
        print("Usage: python src/main.py join <LEAGUE_CODE>")
        return
    client = get_client()
    result = client.join_league(args[0])
    print(result)


def cmd_clear_cache(_args):
    from scrapers.fbref import clear_cache
    from pathlib import Path
    clear_cache()
    for p in (Path(__file__).parent.parent / "data").rglob("*.json"):
        if p.name != ".gitkeep":
            p.unlink()
            print(f"  deleted {p}")


COMMANDS = {
    "explore":     cmd_explore,
    "fetch":       cmd_fetch,
    "build":       cmd_build,
    "join":        cmd_join,
    "clear-cache": cmd_clear_cache,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    args = sys.argv[2:]
    if cmd not in COMMANDS:
        print(f"Unknown command '{cmd}'. Options: {list(COMMANDS)}")
        sys.exit(1)
    COMMANDS[cmd](args)
