"""
Fuzzy matching between FIFA fantasy player list and FBref stats rows.

Strategy:
  1. Normalise names (strip accents, lowercase, drop punctuation)
  2. Match on normalised name + nationality prefix (first 3 chars of FIFA country abbr)
  3. Use rapidfuzz token_sort_ratio for fuzzy scoring
  4. Accept matches above THRESHOLD; flag low-confidence matches
"""

import unicodedata
import re
import pandas as pd
from rapidfuzz import process, fuzz

THRESHOLD = 75  # minimum fuzzy score to accept a match

# FIFA country abbr -> FBref nation prefix (first 2 chars of "eng ENG", "fra FRA" etc.)
# FBref stores nationality as e.g. "eng ENG", "fra FRA" — we compare the 3-letter suffix
COUNTRY_MAP = {
    # FIFA abbr : FBref 3-letter upper
    "ENG": "ENG", "FRA": "FRA", "GER": "GER", "ESP": "ESP",
    "ITA": "ITA", "POR": "POR", "NED": "NED", "BEL": "BEL",
    "ARG": "ARG", "BRA": "BRA", "URU": "URU", "COL": "COL",
    "MEX": "MEX", "USA": "USA", "CAN": "CAN", "MOR": "MAR",
    "SEN": "SEN", "NGA": "NGA", "GHA": "GHA", "CMR": "CMR",
    "CIV": "CIV", "EGY": "EGY", "TUN": "TUN", "MAR": "MAR",
    "ALG": "ALG", "JPN": "JPN", "KOR": "KOR", "AUS": "AUS",
    "IRN": "IRN", "SAU": "KSA", "QAT": "QAT", "CRO": "CRO",
    "SUI": "SUI", "AUT": "AUT", "DEN": "DEN", "SWE": "SWE",
    "NOR": "NOR", "SCO": "SCO", "POL": "POL", "CZE": "CZE",
    "HUN": "HUN", "SRB": "SRB", "SVK": "SVK", "ROU": "ROU",
    "UKR": "UKR", "TUR": "TUR", "GRE": "GRE", "WAL": "WAL",
    "VEN": "VEN", "CHI": "CHI", "PER": "PER", "ECU": "ECU",
    "BOL": "BOL", "PAR": "PAR", "PAN": "PAN", "CRC": "CRC",
    "HON": "HON", "GTM": "GUA", "JAM": "JAM", "TRI": "TRI",
    "NZL": "NZL", "NIG": "NGA",
}


def _normalise(name: str) -> str:
    """Strip accents, lowercase, remove punctuation."""
    if not isinstance(name, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_ = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]", "", ascii_.lower()).strip()


def _fbref_nation(raw: str) -> str:
    """Extract 3-letter upper code from FBref nationality string like 'eng ENG'."""
    if not isinstance(raw, str):
        return ""
    parts = raw.strip().split()
    return parts[-1].upper() if parts else ""


def build_fbref_lookup(
    outfield: pd.DataFrame,
    goalkeep: pd.DataFrame,
    intl_out: pd.DataFrame,
    intl_gk: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge all FBref frames into one lookup table, deduplicating by keeping the
    row with the most minutes (club stats preferred over international).
    """
    def tag(df, source):
        if df is None or df.empty:
            return pd.DataFrame()
        d = df.copy()
        d["source"] = source
        # Ensure required columns exist
        for col in ("fbref_name", "nationality", "minutes"):
            if col not in d.columns:
                d[col] = "" if col != "minutes" else 0
        return d

    frames = [tag(outfield, "club_out"), tag(goalkeep, "club_gk"),
              tag(intl_out, "intl_out"), tag(intl_gk,  "intl_gk")]
    frames = [f for f in frames if not f.empty]

    if not frames:
        return pd.DataFrame(columns=["fbref_name", "nationality", "norm_name", "nation3", "minutes", "source"])

    all_frames = pd.concat(frames, ignore_index=True)

    all_frames["norm_name"] = all_frames["fbref_name"].apply(_normalise)
    all_frames["nation3"]   = all_frames.get("nationality", pd.Series("", index=all_frames.index)).apply(_fbref_nation)
    all_frames["minutes"]   = pd.to_numeric(all_frames.get("minutes", 0), errors="coerce").fillna(0)

    # Keep highest-minutes row per (norm_name, nation3)
    all_frames = (
        all_frames
        .sort_values("minutes", ascending=False)
        .drop_duplicates(subset=["norm_name", "nation3"])
        .reset_index(drop=True)
    )
    return all_frames


def match(fifa_df: pd.DataFrame, fbref_lookup: pd.DataFrame) -> pd.DataFrame:
    """
    For each FIFA player, find the best FBref match.
    Returns fifa_df with FBref stat columns joined on.
    """
    fbref_lookup = fbref_lookup.copy()
    fbref_lookup["norm_name"] = fbref_lookup["fbref_name"].apply(_normalise)
    fbref_lookup["nation3"]   = fbref_lookup["nationality"].apply(_fbref_nation)

    # Build per-nationality candidate lists for faster matching
    nation_groups: dict[str, list[tuple[str, int]]] = {}
    for idx, row in fbref_lookup.iterrows():
        n3 = row["nation3"]
        if n3 not in nation_groups:
            nation_groups[n3] = []
        nation_groups[n3].append((row["norm_name"], idx))

    stat_cols = [
        "goals", "assists", "xg", "xag", "g_per90", "a_per90", "xg_per90", "xa_per90",
        "prog_carries", "prog_passes", "shots_on_tgt", "minutes",
        "clean_sheets", "save_pct", "psxg", "goals_against", "psxg_diff",
        "cs_per90", "psxg_diff_p90", "source",
    ]

    results = []
    for _, player in fifa_df.iterrows():
        norm = _normalise(player["name"])
        # Map FIFA country abbr to FBref nation code
        n3 = COUNTRY_MAP.get(player["country"], player["country"])

        candidates = nation_groups.get(n3, [])
        # Also try without nationality filter (catches mapping gaps)
        if not candidates:
            candidates = [(r["norm_name"], i) for i, r in fbref_lookup.iterrows()]

        if not candidates:
            results.append({c: None for c in stat_cols} | {"match_score": 0, "fbref_name": None})
            continue

        names_only = [c[0] for c in candidates]
        best = process.extractOne(norm, names_only, scorer=fuzz.token_sort_ratio)

        if best and best[1] >= THRESHOLD:
            fbref_idx = candidates[names_only.index(best[0])][1]
            row = fbref_lookup.loc[fbref_idx]
            entry = {c: row.get(c) for c in stat_cols}
            entry["match_score"] = best[1]
            entry["fbref_name"]  = row["fbref_name"]
        else:
            entry = {c: None for c in stat_cols} | {"match_score": best[1] if best else 0, "fbref_name": None}

        results.append(entry)

    stats_df = pd.DataFrame(results, index=fifa_df.index)

    # Fill numeric NaNs with 0
    num_cols = [c for c in stat_cols if c not in ("source", "fbref_name")]
    stats_df[num_cols] = stats_df[num_cols].apply(pd.to_numeric, errors="coerce").fillna(0)

    return pd.concat([fifa_df.reset_index(drop=True), stats_df.reset_index(drop=True)], axis=1)


if __name__ == "__main__":
    # Quick smoke test on normalisation
    names = ["Kylian Mbappé", "Vinícius Júnior", "João Félix", "Erling Haaland"]
    for n in names:
        print(f"{n!r:30} -> {_normalise(n)!r}")
