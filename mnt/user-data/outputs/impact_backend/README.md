# Player Prop Model + Impact Page — Backend

Projects passing / rushing / receiving yards & attempts per player per game,
overlays them on Odds API prop lines to find edges, and emits a JSON feed for a
searchable Player Impact page.

## The one idea
Everything is a view on a single **per-player-per-market projection table**.
Build that well and the prop edges and the impact page are just two reads of it.

## Files (run order)
- `config.py` — paths, API keys, market definitions, model tuning. **Edit first.**
- `data_load.py` — loads PFF crosswalk + prior-year stats, normalizes team names.
- `project.py` — the projection engine (rate × volume × opponent).
- `odds.py` — pulls spreads/totals + player props from The Odds API.
- `build.py` — orchestrator. **Run this.** Writes `prop_edges.csv` + `impact.json`.

## The model (approach: transparent, tunable, no black box)
```
projection = expected_volume × efficiency_rate × opponent_adjustment
```
- **volume** — prior-year per-game attempts/targets/carries
- **efficiency** — prior-year yds-per-unit, regressed toward the position mean
  so small samples don't blow up (shrinkage weight in `config.py`)
- **opponent_adjustment** — your PFF defensive grades: COV scales pass markets,
  RDEF scales rush markets. Strong D pulls the projection down, weak D up.
- **variance** — std dev from prior-year game logs, so a boom/bust player is
  flagged differently from a steady one at the same mean.

Every constant is in `config.py`. Nothing is fit to a regression (per your call
on roster/coaching churn) — it's rate-based and adjustable.

## Setup
1. Put your inputs in `data/`:
   - `master_crosswalk.csv` — the PFF file we built (already the right shape).
   - `player_season_totals.csv` — one row per player, prior year. Columns:
     `player, team, games, pass_att, pass_yds, rush_att, rush_yds, targets,
     receptions, rec_yds` (missing columns tolerated).
   - `player_game_logs.csv` — one row per player-game (for variance). Columns:
     `player, team, week, pass_yds, rush_yds, rec_yds` (+ whatever else).
   - `team_map.csv` — `pff_team, cfbd_team, odds_team` to reconcile the three
     naming systems. Build this from `unique_teams.csv` (the 137 PFF teams).
2. Set API keys as env vars (`ODDS_API_KEY`, `CFBD_API_KEY`) or leave the
   fallbacks in `config.py`.

## Run
```bash
python3 build.py --week 1                 # full: projections + odds + edges
python3 build.py --week 1 --no-odds       # projections only (no API spend)
python3 build.py --week 1 --prop-cap 15   # limit prop pulls (credit control)
```

## Outputs
- `output/prop_edges.csv` — every player-market projection vs the book line,
  sorted by edge. `edge > 0` = model likes the Over; `flag` marks edges past the
  per-stat threshold in `config.py`. **This is the betting view.**
- `output/impact.json` — one entry per player carrying all their market
  projections (with the volume/efficiency/opp-adj breakdown), PFF grade,
  opponent, and any edges. **This feeds the HTML impact page** — searchable
  client-side by team, position, or game_id (the week's slate).

## What's stubbed / next
- **Opponent resolution** currently comes from the Odds API slate (home/away).
  For a full schedule (incl. teams without posted props yet), join CFBD `/games`
  by week — a small addition to `build.py`.
- **Prop projections are v1 rate-based.** Tune `OPP_ADJ_STRENGTH`,
  `SHRINKAGE_GAMES`, and `MIN_PRIOR_VOLUME` against early results.
- **The HTML page itself** is not built yet — this backend produces its data
  feed (`impact.json`). UI is the next step once you're happy with the numbers.
- **Weeks 1-3** use prior-year rates only; wire current-season game logs into
  `load_game_logs` + a blend weight once 2026 data accrues.
```
