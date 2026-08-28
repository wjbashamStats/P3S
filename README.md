# CFB Prop Model & Player Impact Page

College-football betting analytics: PFF grades + prior-year stats + The Odds API
→ player prop projections, model-vs-market edges, and a searchable Player Impact
page.

**Start here:** read `impact_backend/PROJECT_STATE.md` for full context, all
decisions, data quirks, and next steps. To continue in Claude Code, paste
`impact_backend/CLAUDE_CODE_HANDOFF_PROMPT.txt` as your first message.

## Layout
- `impact_backend/` — the model backend (config, projection engine, odds pullers,
  orchestrator, historical backtest puller).
- `clean_data/` — cleaned & deduped 2025 PFF stats (weekly game logs + season
  totals) and the cleaning script.
- `master_crosswalk.csv` / `master_players.csv` / `unique_teams.csv` — PFF grade
  crosswalk across all 12 positions (2,547 players).

## Before first push
1. Move API keys into a gitignored `.env` (do NOT commit `config.py` with keys).
2. Rotate the CFBD + Odds API keys — they were exposed during development.
3. `hist_raw/` is created when you run the historical pull locally; it's
   gitignored (bulk data).

## Quick start
```bash
# projections only, no API spend
cd impact_backend && python3 build.py --week 1 --no-odds

# historical props pull (spends credits — dry-run first!)
python3 historical_pull.py --schedule 2025_schedule.csv --season 2025 --week 1 --dry-run
```
