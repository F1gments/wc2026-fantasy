"""
Entry point — run any time, as often as you like.

  python src/main.py sync             # MAIN COMMAND: fetch + build + export site data
  python src/main.py sync --refresh   # force re-download FIFA player list too
  python src/main.py serve            # start local web server at http://localhost:8000
  python src/main.py fetch            # fetch + enrich data (no site export)
  python src/main.py build            # print optimal squad to terminal
  python src/main.py explore          # probe API endpoints
  python src/main.py join <CODE>      # join work league
  python src/main.py clear-cache      # wipe all cached data for a full re-fetch
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
    return FifaFantasyClient(session_token=token)


def cmd_sync(args):
    """Full pipeline: fetch data, build squad, export JSON, fetch squad images."""
    use_fbref = "--no-fbref" not in args
    refresh   = "--refresh" in args
    client    = get_client()

    if refresh:
        from pathlib import Path
        cache = Path(__file__).parent.parent / "data" / "raw" / "players_raw.json"
        if cache.exists():
            cache.unlink()
            print("Cleared FIFA player cache — will re-download.")

    print("\n[1/4] Fetching player data...")
    df = load_or_fetch(client, use_fbref=use_fbref)

    print("\n[2/4] Running optimizer (5 strategies)...")
    from optimizer import build_top_n_squads
    all_squads = build_top_n_squads(df, n=5)
    result = all_squads[0]  # Moneyball squad = primary
    print_squad(result)

    print("\n[3/4] Fetching squad player images...")
    squad_names = (
        list(result["starting_xi"]["name"]) +
        list(result["bench"]["name"])
    )
    from scrapers.player_images import fetch_images, inject_images, _norm
    image_cache = fetch_images(squad_names)

    # Inject images into squad data
    xi_list    = result["starting_xi"].to_dict("records")
    bench_list = result["bench"].to_dict("records")
    inject_images(xi_list, image_cache)
    inject_images(bench_list, image_cache)

    # Rebuild result with image-enriched data
    import pandas as pd
    result["starting_xi"] = pd.DataFrame(xi_list)
    result["bench"]       = pd.DataFrame(bench_list)

    print("\n[4/4] Exporting site data...")
    from export import run as export_run
    rounds_data = None
    try:
        rounds_data = client.get_rounds()
    except Exception:
        pass
    export_run(df, result, rounds_data, all_squads=all_squads)

    print("\nDone. Run 'python src/main.py serve' to preview the site.")


def cmd_serve(_args):
    """Start local HTTP server for the site at http://localhost:8000"""
    import http.server
    import socketserver
    from pathlib import Path

    public_dir = Path(__file__).parent.parent / "public"
    if not public_dir.exists():
        print("public/ directory not found. Run 'python src/main.py sync' first.")
        return

    os.chdir(public_dir)
    PORT = 8000
    Handler = http.server.SimpleHTTPRequestHandler

    class QuietHandler(Handler):
        def log_message(self, fmt, *args):
            pass  # suppress per-request logging

    print(f"Serving site at http://localhost:{PORT}")
    print(f"  http://localhost:{PORT}/myteam.html")
    print(f"  http://localhost:{PORT}/stats.html")
    print("Press Ctrl+C to stop.\n")
    with socketserver.TCPServer(("", PORT), QuietHandler) as httpd:
        httpd.serve_forever()


def cmd_explore(_args):
    explore_api()


def cmd_fetch(args):
    use_fbref = "--no-fbref" not in args
    if "--refresh" in args:
        from pathlib import Path
        cache = Path(__file__).parent.parent / "data" / "raw" / "players_raw.json"
        if cache.exists():
            cache.unlink()

    client = get_client()
    df = load_or_fetch(client, use_fbref=use_fbref)
    print(f"\nLoaded {len(df)} players")
    stat_cols = ["xg_per90", "xa_per90"]
    base = ["name", "country", "position", "price", "xpts", "ownership"]
    cols = base + [c for c in stat_cols if c in df.columns]
    print(df.sort_values("value_score", ascending=False).head(20)[cols].to_string(
        index=False, float_format=lambda f: f"{f:.3f}"
    ))


def cmd_build(args):
    use_fbref = "--no-fbref" not in args
    df = load_or_fetch(get_client(), use_fbref=use_fbref)
    print_squad(build_squad(df))


def cmd_join(args):
    if not args:
        print("Usage: python src/main.py join <LEAGUE_CODE>")
        return
    print(get_client().join_league(args[0]))


def cmd_clear_cache(_args):
    from pathlib import Path
    removed = 0
    for p in (Path(__file__).parent.parent / "data").rglob("*.json"):
        if p.name != ".gitkeep":
            p.unlink()
            print(f"  deleted {p.name}")
            removed += 1
    print(f"Cleared {removed} cached files.")


COMMANDS = {
    "sync":        cmd_sync,
    "serve":       cmd_serve,
    "fetch":       cmd_fetch,
    "build":       cmd_build,
    "explore":     cmd_explore,
    "join":        cmd_join,
    "clear-cache": cmd_clear_cache,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sync"
    args = sys.argv[2:]
    if cmd not in COMMANDS:
        print(f"Unknown command '{cmd}'. Options: {list(COMMANDS)}")
        sys.exit(1)
    COMMANDS[cmd](args)
