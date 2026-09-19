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

Everything is flat at the repo root — there is no `impact_backend/` or
`clean_data/` subfolder (earlier drafts of this doc described a nested
layout that never matched what actually got committed; corrected 2026-08-28).

```
config.py               model constants, market defs, API keys via env var (.env, gitignored)
data_load.py            loads PFF crosswalk + stats, normalizes names
project.py              projection engine (rate × volume × opponent)
odds.py                 live Odds API puller (spreads/totals + props)
build.py                orchestrator -> prop_edges.csv + impact.json  [TESTED --no-odds, real data]
build_player_tables.py  adapter: per-market *_clean.csv -> player_season_totals.csv /
                         player_game_logs.csv / player_prior_totals.csv /
                         player_current_totals.csv (gitignored, generated -- rerun after clean-file changes)
historical_pull.py      2025 historical props puller  [TESTED via dry-run]
team_map.csv            cfbd_name,odds_name overrides (3 entries so far)
2025_schedule.csv       CFBD 2025 schedule (download_1_.csv)
diagnose_names.py       one-off: compare schedule vs API team names
check_coverage.py       one-off: confirm event coverage per game
hist_raw/               (created at runtime) raw historical odds JSON, one file per game-snapshot
output/                 (created at runtime) prop_edges.csv + impact.json

clean_pff_stats.py       reusable dedup/cleaner for PFF exports
EDA_report.md            full findings
*_weekly_clean.csv       passing/rushing/receiving/defense game logs (deduped)
*_season_clean.csv       2025 season totals for all + blocking (the prior year for a 2026 run)
2024_*_season_clean.csv  2024 season totals (the prior year for the 2025 backtest)
2026_*_season_clean.csv  2026 season to date -- the weekly PFF drop; feeds
                         player_current_totals.csv and the prior/current blend
                         (README "Weekly PFF refresh")

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
6. **ATS and over/under records in the power table are current-season now,
   but only because the TeamRankings pages are saved.** They used to come from
   `X2022_ATS_Percent` / `X2022_OU_Percent` in team_ratings_2025.csv, which
   despite that file's name really are the 2022 season -- a 2026 betting page
   quoting 2022 cover rates, which did mislead a week-3 write-up before it was
   caught. build_diversions_page_data now reads actionnet/input/trends
   (ats_trends.html / ou_trends.html, parsed by actionnet/teamrankings.py),
   ranks the percentages itself since those pages carry no rank column, and
   falls back to the 2022 columns when the pages are missing. The row relabels
   itself either way, so the page always says which vintage it is showing --
   check that label before quoting the number. Note the current-season sample
   is tiny in September (a 2-0 team shows as 100%, first nationally, tied with
   45 others), which is why the page prints the record next to the percentage.
   build_team_preview_data.py still reads the 2022 columns; nothing renders
   them today, but it would need the same treatment if that page comes back.
7. **team_ratings_2025.csv is the frozen preseason board, not a live rating.**
   Despite the name it is a 2026 file, but it is a one-off snapshot and its SP /
   TAN columns never move. The workbook's '2026 PR' sheet is the live one and is
   refreshed weekly; by week 3 they disagreed on all 136 shared teams (Clemson
   12.8 vs 8.1, Western Kentucky -5.3 vs -13.3, Houston 8.2 vs 11.6), always in
   the direction of results. Reading the frozen file made the diversions an
   artifact: the model held a preseason opinion while the book priced two games,
   so the biggest "edges" landed on exactly the teams whose season had gone
   differently than expected. Measured on the 54 rated week-3 games, the old
   model's lean agreed with 2026 margin of victory 31% of the time, correlation
   -0.57 (-0.62 on ATS +/-). On the live rating that is -0.02 and 50%.
   build_team_ratings_2026.py writes team_ratings_<season>.csv from the
   workbook; pass it with --team-ratings. The five-factor rank_ columns come
   across as CFBData26, so the radars become current-season too. Run it every
   week the workbook is refreshed, or the page silently goes stale again.
8. **Team Total needs regressing early in the season.** It is each team's own
   points per game, so two games in it is a schedule artifact, not a rating:
   raw, it had Mississippi State at 45.9 and South Carolina at 41.2 and
   projected their game at 87.1 against a book total of 58.5.
   build_diversions_page_data.shrink_team_totals regresses it toward the slate
   mean by games played (w = n/(n+4), the same shrinkage the player projections
   use), which is on by default; --no-shrink-totals turns it off.
9. **The workbook's TeamID sheet had Arizona and Arizona State's ESPN names
   swapped.** an_metrics derives Mascot by stripping the school off the front of
   the ESPN name, so Arizona's row produced the mascot "State Sun Devils", which
   collides with Arizona State on the norm(Team + Mascot) key every page builder
   joins on: one school gets the other's ratings. an_metrics now detects an ESPN
   value that starts with a longer team name also present in the file, nulls the
   mascot and reports it; build_team_ratings_2026.py fills the blank from the old
   snapshot. Fix it in the workbook; nine other teams have no derivable mascot at
   all and are filled the same way.
10. **The date window is a weekend, so the board can carry games already played.**
    build_diversions_page_data filters on a date range, and on a Saturday morning
    that range still contains Thursday and Friday night. Week 3 2026 had Miami at
    Wake Forest on the board with an 8.7-point total "edge" in a game that had
    kicked off the night before, and it was picked before a web search caught it.
    Every game now carries a `started` flag; --drop-started removes them, and pick
    selection should always use it.
11. **PFF team grades are a per-season export.** team_pff_grades_<season>.csv,
    picked by config.team_grades_for(season) from TEAM_GRADES_BY_SEASON. The page
    builders take --season and resolve it; an unmapped season falls back to 2025
    so the backtest keeps reading what it was validated on. The 2026 file came
    from premium.pff.com/ncaa/teams/2026/REGPO -- note the page renders its table
    from an API call after load, so saving the HTML gets nothing; copy the table
    itself. Rank is computed here (grade_over descending), not taken from the page.
12. **Home-field edge is applied unconditionally, including at neutral sites.**
   build_diversions_page_data adds each team's HFACW to the home side of every
   game, and the Odds API feed names one team "home" even for a neutral-site
   game. Week 3 2026 has Kansas vs Arizona State at Wembley Stadium in London:
   the feed lists Arizona State as home, the book lists the game as Arizona
   State @ Kansas, and our predicted spread carries a home edge neither side
   actually has. The spread magnitude and both implied team totals are still
   right (the favorite is the favorite either way), so props built off implied
   totals are unaffected -- but any predicted-spread diversion for a
   neutral-site game is off by roughly one HFA, and the "home"/"away" labels
   on it may be backwards. No flag for this exists in the data; check the
   venue by hand before betting a neutral-site diversion.

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

## Housekeeping — DONE (2026-08-28)
- Moved API keys out of config.py / historical_pull.py into a gitignored
  `.env` (`.env.example` documents the two vars); no more hardcoded fallback
  values in source. **Still rotate both keys** (CFBD + Odds) if you haven't —
  they were committed in plaintext in this repo's initial commit on GitHub,
  which is more exposed than the original chat-thread leak.
- Reconciled the repo-layout docs to the actual flat layout (see above).
- `config.SEASON` was `2026` (stale/wrong); fixed to `2025` to match the
  data in this repo, and `build.py` now takes `--season` to override it
  per-run instead of requiring a code edit.
- Built `build_player_tables.py`, the adapter from the per-market
  `*_season_clean.csv` / `*_weekly_clean.csv` files to the generic
  `player_season_totals.csv` / `player_game_logs.csv` `data_load.py`
  expects, merging on `player_id` per quirk #5. `build.py --no-odds` now
  runs end-to-end against real 2025 data (3,040 projection rows, week 1).
- Fixed `data_load.load_team_map()`: it expected `team_map.csv` columns
  `pff_team,cfbd_team,odds_team`, but the file (and historical_pull.py's own
  loader) actually uses `cfbd_name,odds_name` — this was a hard crash on
  any `build.py` run. Now reads the real schema; PFF team strings still
  translate to themselves (identity norm) since there's no PFF-specific
  column in the file yet — a genuine PFF/CFBD name mismatch (beyond what
  team_map.csv already overrides for Odds<->CFBD) isn't handled. Worth
  revisiting if projection rows silently disappear for a team once live
  odds are wired in.
- Fixed `historical_pull.py`'s dry-run "cached" count, which was dead code
  (`if False`, always 0). It now reports snapshot files already on disk in
  `hist_raw/` (not scoped to the current run's games — dry-run still makes
  zero API calls, so it can't resolve event ids to check precisely).
