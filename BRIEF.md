# FIFA WC2026 Fantasy — Project Brief & Statistical Learnings

## What This Project Does

Moneyball optimizer for play.fifa.com/fantasy. Fetches live player data from the
FIFA Play API, enriches it with external stats, and runs a linear programming
optimizer to select the statistically best 15-player squad within budget/position rules.

---

## What's Already Built and Working

```
src/
  fifa_client.py      — Live FIFA Play API client (no auth needed for player data)
  data_fetcher.py     — Player data pipeline: FIFA + external stats + scoring
  scoring.py          — Expected points model using official WC2026 scoring rules
  optimizer.py        — PuLP LP optimizer: selects squad, recommends captain
  match_players.py    — Fuzzy name+nationality matching (rapidfuzz) for joining sources
  main.py             — CLI: fetch / build / join <CODE> / clear-cache
  scrapers/
    understat.py      — xG/xA/goals/assists via understatapi package (Big 5 leagues)
    fbref.py          — GK stats: save%, PSxG, clean sheets
    transfermarkt.py  — Market values per national team squad
```

**CLI commands:**
```
python src/main.py build          # run optimizer, print squad
python src/main.py build --no-fbref   # skip external stats (faster, ownership-only)
python src/main.py fetch          # refresh player data + stats
python src/main.py clear-cache    # wipe all cached JSON, force re-fetch
python src/main.py join <CODE>    # join work league (needs FIFA_SESSION_TOKEN in .env)
```

**Confirmed live API endpoints:**
- `https://play.fifa.com/json/fantasy/players.json` — 1,481 players, public
- `https://play.fifa.com/json/fantasy/squads.json` — 48 nations
- `https://play.fifa.com/json/fantasy/rounds.json` — gameweek schedule
- `https://play.fifa.com/api/en/fantasy/team` — user team (needs session cookie)

---

## Statistical Discoveries Made During Build

### 1. The Backup GK Problem
**What happened:** The optimizer picked Brice Samba (France, £4.5m) as starting GK.
France has an 0.85 defensive tier → high expected clean sheets → high xpts/£m.
But Samba is France's backup keeper. He won't play. Zero actual points.

**Why it matters:** The model had no way to distinguish a starting keeper from a
backup keeper using price alone — backup GKs from elite nations look brilliant on paper.

**Solution implemented:** Added `min_ownership` threshold per position in `optimizer.py`.
GKs below 1% ownership are excluded from selection. Ownership % is the best available
proxy for "will this player actually start at the World Cup" — fans and experts are
selecting based on WC-specific knowledge, not just club form.

**Lesson for future:** Any time the optimizer picks an unknown player from a strong nation
at low price, check their ownership %. If it's under 1-2%, they're almost certainly a backup.

---

### 2. Defensive Tier Weighting Changes Everything
**The scoring rule:** GK and DEF both get **+5 for a clean sheet** (60+ min played).
This is the same as a midfielder scoring a goal (+6 minus the base +1 appearance = +5 net extra).

**Implication:** A £5.5m defender from France/Spain/Argentina who keeps a clean sheet
scores ~7 points (2 appearance + 5 CS). That's more points-per-pound than most forwards.

**How it changed the team:** The optimizer naturally loaded up on defenders from strong
defensive nations (Kimmich GER, Gabriel BRA, Laporte ESP, Porro ESP) and spent heavily
on premium midfielders/forwards — not premium defenders. The budget allocation was
roughly: 4 × £5.5m DEF + 1 × £5.0m GK = £27m on defence, £73m on attack.

---

### 3. Attacking Defenders are Disproportionately Valuable
**The scoring rule:** DEF goal = **+7 points**. MID goal = +6. FWD goal = +5.
A scoring defender gets MORE points per goal than a forward.

**Implication for selection:** An attacking DEF like Kimmich (who scores/assists from
set pieces) has a higher ceiling than his price suggests. In future rounds: filter for
defenders with high set-piece involvement or goals-per-90 from club data.

---

### 4. Captain Assignment Is Mechanical — But Can Be Gamed
**The rule:** The game auto-assigns captain to your most expensive player.
Captain scores double points.

**Implication:** Your single most expensive player choice matters enormously — you want
the highest ceiling player, not just the highest average. Mbappé at £10.5m is the right
captain: he scores in big tournaments and is France's penalty taker.

**Edge case:** The game allows changing captain during a live round (before their game
starts) as long as you haven't made other manual changes. This means you can react to
team news — if Mbappé is rested, switch captain to Yamal before Spain kick off.

---

### 5. The Transfer Structure Rewards a "Set and Forget" Group Stage
**The rule:** Unlimited transfers pre-tournament → 2 per MD2/MD3 → unlimited at R32.

**Strategic implication:** Getting the group stage team right matters less than
being optimally set up for the knockout rounds. The two best moments to rotate are:
- **Before MD2**: Make 2 transfers based on MD1 performance
- **Round of 32 reset**: Full unlimited refresh — this is the most important transfer window

The Wildcard booster cannot be used for MD1 or R32 (already unlimited). Save it for
R16 or QF when transfer allocation drops to 4.

---

### 6. External Stats Source Challenges (Technical)
Three attempts to get club season stats. Each failed differently:

| Source | Attempt | Result | Why |
|--------|---------|--------|-----|
| FBref Big5 stats | `requests.get()` | 403 Forbidden | Cloudflare |
| understat.com | regex on HTML | No match | Page no longer embeds JSON as JS var |
| understat via `understatapi` | async Python package | **Works** | Package handles current structure |
| Transfermarkt | `requests` + BeautifulSoup | TBD | Rated 2/5 difficulty, expected to work |

**Current state:** understat scraper rewritten to use `understatapi` package.
FBref GK scraper still attempts direct fetch — gracefully skips if 403.
Transfermarkt scraper built but not yet tested end-to-end (team IDs need verifying).

**Recommended next step:** Run `python src/scrapers/understat.py` to verify understatapi
works, then run `python src/scrapers/transfermarkt.py` to test the England squad scrape.

---

## The Full Vision — What to Build Next

### Phase 2: Live Transfer Optimizer (post-tournament start)

After each round, re-score players using a progressive blend:

```python
wc_weight = min(0.20 + 0.15 * rounds_played, 0.85)
final_score = wc_weight * wc_form_score + (1 - wc_weight) * pretournament_score
```

So: MD1 = 20% WC / 80% pre-tournament. By the final = 85% WC form.

The transfer recommender solves: given my current squad and N free transfers,
which swaps maximise expected points for the next round?
This is another LP problem: swap variables with cost = -3pts per transfer over allocation.

### Phase 3: Dashboard on hibsedit.com

**Hosting:** Cloudflare Pages (free) + GitHub. No server needed.

**Data flow:**
1. Laptop runs `python src/main.py fetch` after each gameweek (~5 min)
2. Script writes JSON files to `public/data/`
3. `git push` to GitHub
4. Cloudflare Pages auto-deploys static site in ~30 seconds

**Pages to build:**
- `/` — current squad, budget, captain recommendation
- `/transfers` — recommended swaps for next round with xpts delta
- `/players` — full player table sortable by value score / position / price
- `/league` — your work league standings (needs session cookie for API)

**Stack:** FastAPI not needed — pure static. Use Jinja2 to template HTML from Python,
or build a simple JSON-reading JS frontend. Chart.js for the points-over-rounds graph.

---

## Booster Strategy (based on scoring rules)

| Booster | When to use |
|---------|-------------|
| Wildcard | R16 or QF — after you know which teams are through, do a full reset |
| 12th Man | Semi-final or Final — pick a forward from a goal-heavy team likely to score |
| Max Captain | Any round where you have a prolific scorer with an easy fixture |
| Qualification Booster | R32 or R16 — pick players from teams likely to advance (+2 each) |
| Mystery Booster | Unknown until R32 opens |

---

## Remaining TODOs

- [ ] Verify `understatapi` fetch works end-to-end (run `python src/scrapers/understat.py`)
- [ ] Verify Transfermarkt scraper — correct team IDs for all 48 nations
- [ ] Wire market value into scoring: `value_score = f(xg, xa, market_value_m) / fifa_price`
- [ ] Add WC form scraper: after MD1, pull points from FIFA API and blend into scorer
- [ ] Build static dashboard pages (HTML + Chart.js)
- [ ] Set up GitHub repo + Cloudflare Pages deployment
- [ ] Add session token to .env to enable team submission and league join via CLI
