# WC2026 Fantasy Football Optimizer

A Moneyball-style squad optimizer and live stats dashboard for the [FIFA World Cup 2026 Fantasy](https://play.fifa.com/fantasy) game.

Fetches live player data from the FIFA Play API, enriches it with external football statistics, and uses linear programming to select statistically optimal squads across five distinct strategies. Outputs a static web dashboard suitable for deployment on Cloudflare Pages.

---

## Features

- **Live data** — pulls player prices, ownership, and tournament stats directly from the official FIFA Play API
- **External stats enrichment** — overlays 2025-26 club season xG/xA data from understat.com for Big 5 league players
- **Five strategic squads** — LP optimizer runs five different objective functions simultaneously, each representing a distinct fantasy approach
- **Moneyball value scoring** — four-algorithm model estimates expected tournament points per player
- **Player images** — headshots sourced from Transfermarkt
- **Static dashboard** — two-page site (`/myteam`, `/stats`) served as plain HTML/JS, no backend required
- **One-command sync** — `python src/main.py sync` refreshes all data and regenerates the site

---

## The Four Scoring Algorithms

### 1. Fixture Difficulty Weighting
Parses the official WC2026 fixture list and rates each team's group stage opponents using FIFA world rankings. A defender from Spain playing Panama has a materially higher clean sheet probability than one playing Argentina. Two modifiers are calculated per team: a clean sheet multiplier and an attacking output multiplier.

### 2. Tournament Depth Multiplier
A player on a team that reaches the final plays 7 games; one eliminated in the groups plays 3. Using an Elo-style win probability model against average opponent rankings at each knockout stage, expected total games per team are estimated. This multiplier has a larger impact on overall xpts than any individual match-level stat.

### 3. Penalty Taker Bonus
The WC2026 scoring system awards +2 points for winning a penalty (on top of the goal bonus). Confirmed first-choice international penalty takers receive an additional goal rate and a flat penalty-winning bonus applied across their expected games. Kane and Mbappé are the most significant beneficiaries.

### 4. Transfermarkt Market Value Fallback
Players outside the Big 5 European leagues (Messi at Inter Miami, Ronaldo at Al-Nasr, Saudi Pro League players) have no understat data. Their Transfermarkt market value is used as a quality proxy — scaled to 0–1 against a €100m ceiling — ensuring elite players who play in minor leagues are not systematically undervalued by the model.

---

## Squad Strategies

| # | Strategy | Objective |
|---|---|---|
| 1 | **Moneyball** | Pure xpts/£m — highest statistical value per pound spent |
| 2 | **Attack Heavy** | 1.5× weight on FWD/MID — premium attackers, cheaper defence |
| 3 | **Defensive Wall** | 1.6× weight on GK/DEF — maximise clean sheet accumulation |
| 4 | **Differentials** | Weight by `xpts × (1 − ownership)` — low-ownership picks that trigger the +2 scouting bonus when they perform |
| 5 | **Deep Run** | Blend xpts with ownership as a tournament-depth signal — backs favourites to go deepest |

Players marked **✓** on the site appear in multiple strategies — these are the consensus picks the model considers strong regardless of approach.

---

## Scoring Model

Based on the official WC2026 Fantasy scoring rules:

| Event | GK | DEF | MID | FWD |
|---|---|---|---|---|
| Appearance 60+ min | +2 | +2 | +2 | +2 |
| Clean sheet | +5 | +5 | +1 | — |
| Goal | +9 | +7 | +6 | +5 |
| Assist | +3 | +3 | +3 | +3 |
| Penalty save | +3 | — | — | — |
| Every 3 saves | +1 | — | — | — |
| Winning a penalty | — | +2 | +2 | +2 |
| Scouting bonus (<5% ownership, 4+ pts) | +2 | +2 | +2 | +2 |

Expected points per player = position-specific formula combining appearance points, clean sheet probability (fixture-adjusted), goal/assist rates (from understat xG/xA or price/market-value proxy), penalty taker bonus, all multiplied by expected tournament games.

---

## Project Structure

```
src/
  main.py                   CLI entry point
  fifa_client.py            FIFA Play API client
  data_fetcher.py           Player data pipeline
  scoring.py                Expected points model
  optimizer.py              PuLP LP optimizer + 5 strategies
  export.py                 JSON export for static site
  match_players.py          Fuzzy name matching (FIFA ↔ understat)
  algorithms/
    fixture_difficulty.py   Group stage opponent difficulty scores
    tournament_depth.py     Expected games via Elo-style elimination probs
    penalty_takers.py       Confirmed WC penalty taker registry
  scrapers/
    understat.py            2025-26 xG/xA via understatapi
    fbref.py                GK stats (save%, PSxG)
    transfermarkt.py        Market values for national team squads
    player_images.py        Player headshots from Transfermarkt search
public/
  myteam.html               Squad view — 5 strategy tabs, captain, trend arrows
  stats.html                Full 1481-player table with filtering and sorting
  data/                     Generated JSON (refreshed by sync command)
```

---

## Setup

```bash
git clone <repo-url>
cd FantasyFootball
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
```

Copy `.env.example` to `.env`. A session token is only required to submit your team or join a league — all data fetching works without authentication.

---

## Usage

```bash
# Full sync — fetch data, run optimizer, export site, fetch player images
python src/main.py sync

# Start local preview server at http://localhost:8000
python src/main.py serve

# Force re-download of FIFA player list (clears local cache)
python src/main.py sync --refresh

# Join a work league (requires FIFA_SESSION_TOKEN in .env)
python src/main.py join <LEAGUE_CODE>

# Wipe all cached data
python src/main.py clear-cache
```

---

## Data Sources

| Source | Data | Auth |
|---|---|---|
| [play.fifa.com](https://play.fifa.com/json/fantasy/players.json) | Player prices, positions, ownership, live WC stats | None |
| [understat.com](https://understat.com) | 2025-26 club season xG, xA, goals, assists | None |
| [transfermarkt.com](https://www.transfermarkt.com) | Market values, player headshots | None |

---

## Deployment

The `public/` directory is a self-contained static site. Deploy to any static host.

**Cloudflare Pages:** connect your GitHub repo, set publish directory to `public/`, no build command required.

To automate daily data refresh, a GitHub Actions workflow (`.github/workflows/sync.yml`) runs `python src/main.py sync` at 06:00 UTC, commits the updated `public/data/` JSON files, and triggers a Cloudflare Pages deployment.

---

## License

MIT
