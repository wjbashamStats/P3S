# PFF Stats — Cleaning & Exploratory Analysis

Prior-year (2025) PFF exports: weekly game logs + season totals for passing,
rushing, receiving, defense, plus season-total offensive line blocking. Two
schedule files: 2026 and 2025.

## File inventory

| File | Grain | Rows (raw) | Players | Weeks |
|---|---|---|---|---|
| passing_summary_combined | player-week | 2,517 | 541 | 0–15 |
| rushing_summary_combined | player-week | 8,714 | 1,687 | 0–16 |
| receiving_summary_combined | player-week | 15,789 | 2,341 | 0–14 |
| defense_summary_combined | player-week | 41,429 | 5,652 | 0–16 |
| passing_summarySeasonTotal | player | 541 | 541 | — |
| rushing_summarySeasonTotal | player | 1,687 | 1,687 | — |
| receiving_summarySeasonTotal | player | 2,344 | 2,344 | — |
| defense_summarySeasonTotal | player | 5,652 | 5,652 | — |
| offense_blockingSeasonTotal | player | 5,894 | 5,894 | — |
| download.csv | game | 1,204 | — | 2026 sched, wk 1–15 |
| download_1_.csv | game | 1,780 | — | 2025 sched, wk 1–16 |

`_combined` = per-player-per-week game logs. `SeasonTotal` = year aggregate,
one row per player. Both carry `player_id` — the reliable join/dedup key
(names alone collide).

## Duplicates found & fixed

**Receiving weekly had 1,755 exact-duplicate rows** — entire rows repeated
(e.g. Joe Royer, CINCINNATI, week 6 appeared twice with identical stats). Every
duplicate was a perfect copy, so dropping them loses nothing.

- receiving weekly: 15,789 → **14,034** rows after dedup.
- passing, rushing, defense weekly: **no duplicates** — one clean row per
  player-week already. Your hunch that the problem was specifically in
  receiving was correct.

## Data-quality checks (weekly sums vs season totals)

A strong integrity test: do a player's weekly rows sum to their season total?

- **Rushing: 1,687 / 1,687 players reconcile exactly.** Clean.
- **Passing: 539 / 541 reconcile** (2 minor diffs).
- **Receiving: 2,268 / 2,341 reconcile after dedup** — 73 remaining mismatches.

### Why the 73 receiving mismatches remain (and it's not a cleaning bug)
The receiving **weekly** file stops at **week 14**, while passing (15), rushing
(16), and defense (16) run later. 69 of the 73 mismatches are cases where the
season total exceeds the weekly sum — i.e., bowl/playoff receiving games that
exist in the season total but were never included in the weekly export. This is
a **source truncation**, not something cleaning can repair.

Implication for modeling: for variance/usage from receiving game logs, those 73
players (mostly high-volume WRs — Shazz Preston, Malik Benson, Deion Burks,
Mario Craver…) will be slightly under-counted on late-season games. Two options:
(a) use season totals for their means and weekly only for variance, or (b)
re-pull the receiving weekly export through week 16. Recommend (b) if easy.

The other 4 mismatches are trivial (2–8 yard differences; one negative-yardage
edge case, Darius Copeland at −1). Ignore.

## Key distributions (2025 season totals, ≥5 games)

| Stat | n | median yds | 90th pct | max | league yds/unit |
|---|---|---|---|---|---|
| Passing | 214 | 1,558 | 3,045 | 3,837 | 7.39 /att |
| Rushing | 1,162 | 104 | 645 | 1,572 | 5.09 /att |
| Receiving | 1,833 | 108 | 533 | 1,299 | 7.91 /tgt |

These league yds/unit rates are the shrinkage targets the projection engine
regresses small-sample players toward.

## Cleaned outputs
`*_weekly_clean.csv` and `*_season_clean.csv` for every stat group, written by
`clean_pff_stats.py`. Re-run any time with:
```
python3 clean_pff_stats.py <input_dir> <output_dir>
```

## Next: historical odds + modeling
With clean weekly logs (for volume/variance) and season totals (for rates), the
next step is a historical prop pull from the Odds API to (1) validate the
projection model against lines that actually posted and (2) calibrate the
opponent-adjustment and shrinkage constants against realized results.
Note: the Odds API historical endpoint is a paid add-on and is snapshot-based
(odds as of a timestamp) — see the modeling step for how many credits a
season-long backtest costs before running it.
