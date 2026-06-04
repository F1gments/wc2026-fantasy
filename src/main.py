"""
Entry point. Usage:
  python src/main.py explore        # probe API endpoints
  python src/main.py fetch          # download & cache player data
  python src/main.py build          # run optimizer and print team
  python src/main.py join <CODE>    # join work league
"""
import os, sys
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from fifa_client import FifaFantasyClient, explore_api
from data_fetcher import fetch_players, enrich_value_metrics
from optimizer import build_squad, print_squad, DEFAULT_RULES


def get_client():
    token = os.getenv("FIFA_SESSION_TOKEN")
    if not token:
        print("WARNING: FIFA_SESSION_TOKEN not set — unauthenticated requests may fail.")
        print("Set it in .env or as an environment variable.")
    return FifaFantasyClient(session_token=token)


def cmd_explore(_args):
    explore_api()


def cmd_fetch(_args):
    client = get_client()
    df = fetch_players(client)
    df = enrich_value_metrics(df)
    print(f"Fetched {len(df)} players across positions:")
    print(df.groupby("position").agg(count=("id","count"), avg_price=("price","mean")).to_string())
    print("\nTop 10 by value score:")
    print(df.sort_values("value_score", ascending=False).head(10)[
        ["name", "country", "position", "price", "total_pts", "value_score"]
    ].to_string(index=False))


def cmd_build(_args):
    client = get_client()
    from data_fetcher import load_or_fetch
    df = load_or_fetch(client)
    result = build_squad(df)
    print_squad(result)


def cmd_join(args):
    if not args:
        print("Usage: python src/main.py join <LEAGUE_CODE>")
        return
    client = get_client()
    result = client.join_league(args[0])
    print(result)


COMMANDS = {
    "explore": cmd_explore,
    "fetch": cmd_fetch,
    "build": cmd_build,
    "join": cmd_join,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    args = sys.argv[2:]
    if cmd not in COMMANDS:
        print(f"Unknown command '{cmd}'. Options: {list(COMMANDS)}")
        sys.exit(1)
    COMMANDS[cmd](args)
