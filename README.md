# CFB Prop Model & Player Impact Page

College-football betting analytics: PFF grades + prior-year stats + The Odds API
→ player prop projections, model-vs-market edges, and a searchable Player Impact
page.

**Start here:** read `PROJECT_STATE.md` for full context, all decisions, data
quirks, and next steps. To continue in Claude Code, paste
`CLAUDE_CODE_HANDOFF_PROMPT.txt` as your first message.

## Layout
Everything lives flat at the repo root (no `impact_backend/` or `clean_data/`
subfolders):
- `config.py`, `data_load.py`, `project.py`, `odds.py`, `build.py`,
  `historical_pull.py`, `build_player_tables.py` — the model backend.
- `*_season_clean.csv` / `*_weekly_clean.csv` — cleaned & deduped 2025 PFF
  stats per market (passing/rushing/receiving/defense/blocking), and
  `clean_pff_stats.py`, the cleaning script. `2024_*_season_clean.csv` is the
  prior season; `2026_*_season_clean.csv` is **this** season to date (the
  weekly drop — see "Weekly PFF refresh" below).
- `master_crosswalk.csv` / `master_players.csv` / `unique_teams.csv` — PFF grade
  crosswalk across all 12 positions (2,547 players).
- `team_map.csv` — `cfbd_name,odds_name` overrides for teams the fuzzy matcher
  can't bridge on its own.
- `hist_raw/` and `output/` are created at runtime and gitignored.

## Before first push
1. Move API keys into a gitignored `.env` (do NOT commit `config.py` with keys).
2. Rotate the CFBD + Odds API keys — they were exposed during development.
3. `hist_raw/` is created when you run the historical pull locally; it's
   gitignored (bulk data).

## Weekly futures + lines refresh
Both pulls need network and run on **your** machine, not the sandbox.

```bash
# Game lines + player props for the upcoming slate (Odds API, costs credits)
python3 pull_live_week.py --week <N> --dry-run     # free, reports the slate size
python3 pull_live_week.py --week <N>               # -> hist_lines_live_<SEASON>wk<N>.csv
                                                   #    hist_props_live_<SEASON>wk<N>.csv

# Futures (VegasInsider, needs playwright + chromium; free)
python3 dump_futures_html.py --week <N>            # -> futures_html/week<N>/
python3 refresh_futures.py --week <N>              # -> team_ratings_2025.csv + futures_2026.csv
```

`refresh_futures.py` is a wrapper: it finds every page in the dump, assembles
the eleven `build_futures_from_html.py` flags, and runs `export_futures_csv.py`
after. `--dry-run` prints the commands without running them.

The futures export is named for the season the odds are **on**
(`futures_2026.csv`), not the ratings file they live in
(`team_ratings_2025.csv`) — `actionnet/an_metrics.py` looks it up by season and
silently drops its odds columns if the name doesn't match.

## Weekly PFF refresh
Export the five season-summary files from PFF (passing, rushing, receiving,
defense, offense blocking) **before** the week you are about to project, save
them as `2026_{passing,rushing,receiving,defense,blocking}_season_clean.csv`,
then:

```bash
python3 build_player_tables.py     # rebuilds player_current_totals.csv
```

Those files are this season to date, keyed by `player_id`. From there
`project.blend_prior_and_current` weights each player's 2026 rate against his
2025 one by how many 2026 games he has played
(`config.CURRENT_SEASON_BLEND_GAMES`), and players with no 2025 record at all
(true freshmen, FCS/JUCO arrivals) enter the projection pool off their 2026
numbers alone. Export *before* the slate, not after it: the file is a running
total with no week column, so nothing downstream can filter out a week that has
already been played, and a late export leaves the blend reading the results it
is meant to be predicting.

Do **not** overwrite the bare `*_season_clean.csv` files with an in-season
export: those are 2025's finished season, which is what a 2026 run uses as its
prior year (`config.PRIOR_TOTALS_BY_SEASON`).

## Quick start
```bash
# derive player_season_totals.csv + player_game_logs.csv from the per-market
# *_clean.csv files (gitignored outputs; rerun whenever the clean files change)
python3 build_player_tables.py

# projections only, no API spend
python3 build.py --week 1 --season 2025 --no-odds

# historical props pull (spends credits — dry-run first!)
python3 historical_pull.py --schedule 2025_schedule.csv --season 2025 --week 1 --dry-run
```

## Weekly refresh

One command:

```bash
python3 refresh_week.py --week 5
```

It pulls the TeamRankings trends pages, rebuilds the player tables and team
ratings, builds the four page-data files and the hub, then prints a readiness
report naming anything still stale. The slate window is read out of the lines
file (the day with the most kickoffs, plus a day either side) rather than
assumed from the week number, because a live odds pull labels two weekends
with the same week.

Add `--pff-dir ~/Downloads` on a week with new PFF exports to clean and rank
them on the way through. Add `--pull-odds` to pull fresh lines and props --
that one spends Odds API credits, so it never runs by default.

`--only board pages` re-runs just the tail end; `--dry-run` prints the
commands without running them.

What still arrives by hand each week: the Action Network workbook
(`actionnet/input/AN_season.xlsx`), the PFF team-grades page
(`team_pff_grades_2026.csv`), and the FanDuel salary export
(`fanduel_salaries_<season>wk<N>.csv`). The readiness report names each one if
it is behind.
