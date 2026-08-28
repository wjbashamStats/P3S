# PROJECT STATE — CFB Prop Model & Player Impact Page

Handoff doc for continuing this project in Claude Code. Captures what's built,
every decision made, known data quirks, and the ordered next steps.
Last updated: 2026-08-28.

---

## What this project is

Two connected systems for a college-football betting workflow, built on PFF
grades + prior-year stats + The Odds API:

1. **Prop projection models** — project passing / rushing / receiving yards &
   attempts per player per game, overlay on Odds API prop lines, surface edges.
2. **Player Impact page** — searchable HTML view (by team / position group /
   week's slate) showing PFF grades AND projected production. Backend first;
   UI to be designed later.

Both are views on ONE per-player-per-market projection table.

---

## Owner's modeling decisions (do not silently change these)

- **Heuristic, not regression.** Owner is wary of historicals given roster/
  coaching churn. Projection = rate × volume × opponent-adjustment, fully
  transparent and tunable. No fitted regression weights.
- **Five-factor team model tiers** (for the separate team spread/total model):
  Tier 1 = havoc, success rate, pts per opp (weight 1.0). Tier 2 = field
  position, explosiveness (weight 0.5). Applied to offense and defense.
- **Weeks 1–3 use TARP** (returning production); week 4+ uses current-season
  five-factor metrics. Auto-switched on CFBD week.
- **Prop projection method:** volume (prior-year per-game rate) × efficiency
  (prior-year yds/unit, regressed toward position mean) × opponent adj (PFF
  defensive grades: COV scales pass, RDEF scales rush). Game logs give variance.
- **Backtest scope decided:** all 6 prop markets, all FBS-vs-FBS games,
  **closing snapshot only** (sharpest lines, ~51k credits vs ~103k for two
  snapshots). Opening snapshot deferred — can add later for line-movement.

---

## Repo layout (what exists and is TESTED)

```
impact_backend/
  config.py            model constants, market defs, API keys via env var
  data_load.py         loads PFF crosswalk + stats, normalizes names
  project.py           projection engine (rate × volume × opponent)
  odds.py              live Odds API puller (spreads/totals + props)
  build.py             orchestrator -> prop_edges.csv + impact.json  [TESTED offline, --no-odds]
  historical_pull.py   2025 historical props puller  [TESTED via dry-run]
  team_map.csv         Odds<->CFBD name crosswalk (3 entries so far)
  2025_schedule.csv    CFBD 2025 schedule (download_1_.csv)
  diagnose_names.py    one-off: compare schedule vs API team names
  check_coverage.py    one-off: confirm event coverage per game
  hist_raw/            (created at runtime) raw historical odds JSON, one file per game-snapshot

clean_data/
  clean_pff_stats.py       reusable dedup/cleaner for PFF exports
  EDA_report.md            full findings
  *_weekly_clean.csv       passing/rushing/receiving/defense game logs (deduped)
  *_season_clean.csv       season totals for all + blocking

(PFF crosswalk from earlier phase)
  master_crosswalk.csv     2,547 player-position rows, enriched (off_/def_ prefixed grades+snaps)
  master_players.csv       one row per player, same enriched schema
  unique_teams.csv         137 distinct PFF team strings (for team_map building)
```

## PFF grade parsing (DONE — 12 positions, all clean)
QB 113, RB 180, WR 410, TE 175, C 102, OG 237, OT 99, CB 370, S 178, LB 183,
EDGE 250, DT 250 = 2,547 player-position rows.
- Offense parser: 18-field layout (parse_pff.py). Defense: 14-field (parse_pff_def.py).
- Defensive grade columns confirmed: DEF / RDEF / PRSH / COV (grades + snaps).

---

## KNOWN DATA QUIRKS (carry these forward)

1. **Receiving weekly truncated at week 14.** Passing goes to 15, rushing/
   defense to 16. Result: 73 high-volume WRs have season totals that exceed
   their weekly-sum (bowl/playoff catches missing from weekly). Rushing
   reconciles 100%, passing 539/541. For those 73 WRs, use season totals for
   rate means; weekly only for variance. OR re-pull receiving weekly through wk16.
2. **Receiving had 1,755 exact-duplicate rows** — already removed in
   receiving_weekly_clean.csv. Other files had none.
3. **A few OL source-data artifacts:** garbled name "Toimport" (Utah St OT),
   Cyrillic chars in "Kkot Bi Kim"/"Kolби Schutz" (UCLA/UConn), DJ Chester
   legitimately at both C and OT. Clean before name joins.
4. **Delaware players** show 0'0"/0 size (PFF incomplete data) — cosmetic.
5. **player_id is the reliable join key** across PFF files; names collide.

---

## Odds API — cost model (CRITICAL, don't burn the budget)

- Live odds: 1 credit × markets × regions × events.
- **Historical: 10 credits × markets × regions × events × snapshots** (10× live).
- Owner topped up to **100,000 credits this month; resets on the 1st.**
- Closing-only 2025 backtest: 858 FBS games × 6 markets × 10 = **~51,480 max**
  (actual less — empties/unposted props cost less). Dry-run confirmed.
- `historical_pull.py` safeguards: --dry-run (counts credits, spends nothing),
  per-game checkpointing to hist_raw/ (crash-safe resume, never re-spends),
  CREDIT_CEILING=100000 hard stop, CREDIT_FLOOR=2000 graceful halt, live meter.

## Name matching (SOLVED for week 1)
- Matcher normalizes accents (é→e) + uses team_map.csv + is orientation-
  agnostic (schedule and API disagree on home/away for neutral-site games).
- Week 1: 105/105 FBS games match after fixes. team_map.csv currently:
  App State→Appalachian State Mountaineers, Massachusetts→UMass Minutemen,
  San José State→San Jose State Spartans.
- Full season may surface a few more unmapped teams (teams not playing wk1,
  bowls). Add them to team_map.csv as `no event match` lines appear.

---

## IMMEDIATE NEXT STEPS (in order)

1. **Run week-1 historical pull** (owner does this; ~3k credits):
   `python3 historical_pull.py --schedule 2025_schedule.csv --season 2025 --week 1`
   Check hit rate (ls hist_raw/ | wc -l) and credit meter.
2. **Build the flattener** — turn hist_raw/*.json (nested snapshot JSON) into a
   clean per-player-per-market props table: game_id, player, market, book_line,
   over/under prices, consensus. Handle the snapshot wrapper structure.
3. **Join props to actual results** from *_weekly_clean.csv (the 2025 game
   logs) by player + week → each prop line gets its realized outcome.
4. **Backtest** — projection vs closing line vs actual. Metrics: hit rate on
   flagged edges, CLV, calibration by market. This tells us if the model has edge.
5. **Tune** OPP_ADJ_STRENGTH, SHRINKAGE_GAMES, MIN_PRIOR_VOLUME against results.
6. **Full-season pull** (~48k more credits) once week-1 validates coverage+model.
7. **Player Impact HTML page** — reads impact.json, searchable by team/pos/week.

## Housekeeping to do early in Claude Code
- Move API keys out of config.py / script headers into a .env (gitignored).
  **Rotate both keys** (CFBD + Odds) — they've been exposed in a chat thread.
- The env-var reads already exist (Sys.getenv / os.environ.get); just populate .env.
