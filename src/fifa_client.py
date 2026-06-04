"""
FIFA Play fantasy API client.
Handles auth via session cookie and all data fetches.
"""
import json
import time
import os
import requests
from pathlib import Path

BASE_URL = "https://api.play.fifa.com/api/v1"
CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"


class FifaFantasyClient:
    def __init__(self, session_token: str | None = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Origin": "https://play.fifa.com",
            "Referer": "https://play.fifa.com/",
        })
        if session_token:
            self.session.cookies.set("session", session_token)

    def _get(self, path: str, params: dict = None, cache_key: str = None) -> dict:
        if cache_key:
            cache_path = CACHE_DIR / f"{cache_key}.json"
            if cache_path.exists():
                return json.loads(cache_path.read_text())

        url = f"{BASE_URL}{path}"
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if cache_key:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data, indent=2))

        time.sleep(0.3)  # polite rate limiting
        return data

    # --- Player data ---

    def get_players(self) -> list[dict]:
        """All available players with price, position, team."""
        data = self._get("/players", cache_key="players")
        return data.get("data", data) if isinstance(data, dict) else data

    def get_player_stats(self, player_id: str) -> dict:
        return self._get(f"/players/{player_id}/stats", cache_key=f"stats_{player_id}")

    # --- Game config ---

    def get_game_config(self) -> dict:
        """Budget, squad rules, scoring system."""
        return self._get("/game-config", cache_key="game_config")

    def get_fixtures(self) -> list[dict]:
        return self._get("/fixtures", cache_key="fixtures")

    # --- Team management ---

    def get_my_team(self) -> dict:
        return self._get("/team")

    def get_league(self, league_code: str) -> dict:
        return self._get(f"/leagues/{league_code}")

    def join_league(self, league_code: str) -> dict:
        resp = self.session.post(
            f"{BASE_URL}/leagues/join",
            json={"code": league_code},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


def explore_api():
    """Probe the API to discover live endpoints — run this first."""
    probe_paths = [
        "/players",
        "/fantasy/players",
        "/fantasy/game-config",
        "/competition/17/players",  # 17 = FIFA WC competition ID
        "/game",
        "/game/config",
    ]
    client = FifaFantasyClient()
    for path in probe_paths:
        url = f"{BASE_URL}{path}"
        try:
            r = client.session.get(url, timeout=10)
            print(f"  {r.status_code}  {path}")
        except Exception as e:
            print(f"  ERR  {path}  ({e})")


if __name__ == "__main__":
    print("Probing FIFA Play API endpoints...")
    explore_api()
