"""
FBref scraper — GK stats only (save%, clean sheets, PSxG).
Outfield stats come from understat.py instead.

FBref GK page is smaller and less aggressively cached/blocked than the full stats page.
"""

import time
import re
import json
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

GK_URL = (
    "https://fbref.com/en/comps/Big5/2024-2025/keepers/players/"
    "2024-2025-Big-5-European-Leagues-Stats"
)
GK_TABLE_ID = "stats_keeper"


def _parse_gk_table(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")

    # FBref wraps some tables in HTML comments — unwrap
    commented = re.findall(r"<!--(.*?)-->", html, re.DOTALL)
    for block in commented:
        if GK_TABLE_ID in block:
            soup = BeautifulSoup(block, "lxml")
            break

    table = soup.find("table", {"id": GK_TABLE_ID})
    if table is None:
        return pd.DataFrame()

    df = pd.read_html(str(table), header=[0, 1])[0]

    # Flatten multi-level columns
    df.columns = [
        "_".join(str(c).strip() for c in col if "Unnamed" not in str(c)).strip("_")
        or f"col_{i}"
        for i, col in enumerate(df.columns)
    ]

    if "Player" in df.columns:
        df = df[df["Player"] != "Player"].reset_index(drop=True)

    return df


def _clean_gk(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    col_map = {c.lower().replace(" ", "_").replace("%", "pct").replace("-", "_"): c
               for c in df.columns}

    def g(name):
        return col_map.get(name)

    def safe(key, fallback=""):
        c = g(key) or g(fallback)
        if c and c in df.columns:
            return pd.to_numeric(df[c], errors="coerce").fillna(0)
        return pd.Series(0, index=df.index)

    out = pd.DataFrame()
    for name_key in ("player", "Player"):
        if name_key in df.columns:
            out["fbref_name"] = df[name_key]
            break
    if "fbref_name" not in out.columns:
        out["fbref_name"] = df.iloc[:, 0]

    # FBref nationality column
    for nat_key in ("Nation", "nation"):
        if nat_key in df.columns:
            out["nationality"] = df[nat_key]
            break
    if "nationality" not in out.columns:
        out["nationality"] = ""

    out["minutes"]      = safe("min", "90s")
    out["clean_sheets"] = safe("cs")
    out["save_pct"]     = safe("save_pct", "savepct")
    out["psxg"]         = safe("psxg")
    out["goals_against"]= safe("ga")
    out["psxg_diff"]    = out["psxg"] - out["goals_against"]

    n90 = (out["minutes"] / 90).replace(0, pd.NA)
    out["cs_per90"]      = out["clean_sheets"] / n90
    out["psxg_diff_p90"] = out["psxg_diff"]    / n90

    out = out[out["fbref_name"].notna() & (out["fbref_name"] != "")]
    out = out[out["minutes"] > 0]
    return out.fillna(0).reset_index(drop=True)


def fetch_gk_stats() -> pd.DataFrame:
    cache_path = CACHE_DIR / "fbref_gk.json"
    if cache_path.exists():
        print("  [cache] fbref/gk")
        return pd.read_json(cache_path)

    print(f"  [fetch] {GK_URL}")
    try:
        resp = requests.get(GK_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        time.sleep(4)
    except Exception as e:
        print(f"  WARNING: FBref GK fetch failed ({e}) — GK scoring will use ownership only")
        return pd.DataFrame()

    df = _parse_gk_table(resp.text)
    if df.empty:
        print("  WARNING: GK table not parsed — check table ID")
        return pd.DataFrame()

    cleaned = _clean_gk(df)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cleaned.to_json(cache_path, orient="records", force_ascii=False)
    print(f"  fbref/gk: {len(cleaned)} rows")
    return cleaned


def clear_cache():
    p = CACHE_DIR / "fbref_gk.json"
    if p.exists():
        p.unlink()
        print(f"  deleted {p.name}")


if __name__ == "__main__":
    df = fetch_gk_stats()
    if not df.empty:
        print(df.sort_values("save_pct", ascending=False).head(10)[
            ["fbref_name", "nationality", "minutes", "clean_sheets", "save_pct", "psxg_diff"]
        ].to_string(index=False))
