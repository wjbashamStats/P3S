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
  `clean_pff_stats.py`, the cleaning script.
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
