"""
FIFA Play fantasy API client.
Public data:  https://play.fifa.com/json/fantasy/  (no auth)
Auth data:    https://play.fifa.com/api/en/fantasy/  (session cookie)
"""
import json
import time
import requests
from pathlib import Path

JSON_URL = "https://play.fifa.com/json/fantasy"
API_URL  = "https://play.fifa.com/api/en/fantasy"
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

    def _get_json(self, path: str, cache_key: str = None) -> dict:
        """Fetch from the public /json/fantasy/ CDN (no auth needed)."""
        if cache_key:
            cache_path = CACHE_DIR / f"{cache_key}.json"
            if cache_path.exists():
                return json.loads(cache_path.read_text())
        resp = self.session.get(f"{JSON_URL}{path}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if cache_key:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data, indent=2))
        time.sleep(0.3)
        return data

    def _get_api(self, path: str) -> dict:
        """Fetch from the auth-required /api/en/fantasy/ endpoint."""
        resp = self.session.get(f"{API_URL}{path}", timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _post_api(self, path: str, payload: dict) -> dict:
        resp = self.session.post(f"{API_URL}{path}", json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    # --- Public data (no auth) ---

    def get_players(self) -> list[dict]:
        data = self._get_json("/players.json", cache_key="players")
        return data.get("data", data) if isinstance(data, dict) else data

    def get_rounds(self) -> list[dict]:
        return self._get_json("/rounds.json", cache_key="rounds")

    def get_squads(self) -> list[dict]:
        return self._get_json("/squads.json", cache_key="squads")

    # --- Auth-required ---

    def get_my_team(self) -> dict:
        return self._get_api("/team")

    def get_user(self) -> dict:
        return self._get_api("/user")

    def join_league(self, league_code: str) -> dict:
        return self._post_api("/leagues/join", {"code": league_code})


def explore_api():
    """Confirm known endpoints are live."""
    client = FifaFantasyClient()
    public = ["/players.json", "/rounds.json", "/squads.json"]
    auth   = ["/user", "/team"]
    for path in public:
        url = f"{JSON_URL}{path}"
        try:
            r = client.session.get(url, timeout=10)
            print(f"  {r.status_code}  {len(r.content):>8} bytes  {url}")
        except Exception as e:
            print(f"  ERR  {url}  ({e})")
    for path in auth:
        url = f"{API_URL}{path}"
        try:
            r = client.session.get(url, timeout=10)
            print(f"  {r.status_code}  {len(r.content):>8} bytes  {url}  (auth)")
        except Exception as e:
            print(f"  ERR  {url}  ({e})")


if __name__ == "__main__":
    print("Probing FIFA Play API endpoints...")
    explore_api()
