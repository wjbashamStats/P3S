# Action Network weekly metrics

Port of `MetricRankingCode` from nine Google Sheets to the one Action Network
season workbook, plus the futures odds and TeamRankings records this repo
already produces. Runs every Sunday; writes one ranked CSV.

## The weekly drop

    actionnet/input/AN_season.xlsx        <- replace this each week
    actionnet/input/trends/*.html         <- and re-save these three

That is the only thing that has to change. Export the Action Network workbook,
overwrite that file, commit. The Sunday job reads whatever is sitting there, so
if it isn't refreshed the run still succeeds and just reproduces last week's
numbers -- the log prints the workbook's mtime so a stale input is visible.

## Running it by hand

    python3 actionnet/an_metrics.py --xlsx actionnet/input/AN_season.xlsx \
        --season 2026 --out actionnet/out/AN_2026_$(date +%Y%m%d).csv

Optional inputs, both auto-detected when present:

| flag | source | without it |
|---|---|---|
| `--odds-csv` | `futures_<season>.csv` from `build_futures_from_html.py` | odds columns omitted |
| `--trends-dir` | the three saved TeamRankings trends pages (see `input/trends/README.md`) | falls back to parsing the PFF tab, which matches 130 of 138 teams |

No third-party packages. `xlsx_read.py` is a small read-only .xlsx parser built
on `zipfile` + `xml.etree`, so a scheduled run can never fail on a pip install.
It is checked against openpyxl cell-for-cell by `test_xlsx_read.py`, which skips
itself when openpyxl isn't installed:

    python3 actionnet/test_xlsx_read.py actionnet/input/AN_season.xlsx
    python3 actionnet/test_teamrankings.py

## What the workbook doesn't have

- **Futures odds.** `2026 Futures` has Win Total Feb/MAR/Jul columns but they're
  empty. Comes from the futures pipeline instead, joined on `Team` -- the export
  already uses our naming, so the old `VI` crosswalk step is gone.
- **Records.** From TeamRankings, not the workbook: win/loss, against-the-spread
  and over/under, parsed from the saved trends pages. TeamRankings abbreviates
  its team names, so resolution runs alias table -> our name -> TeamID's
  TeamRankings column -> a normalised form; all 138 names on the 2026-09-18
  slate resolve, with no two mapping to the same team
  (`actionnet/test_teamrankings.py` asserts both).
- **Mascot.** Derived from `TeamID`'s ESPN name; resolves 129 of 138.
- **Logos.** Not in an `info` sheet; taken from the `Twitter` tab, 132 of 138.

## Known problems in the workbook itself

The script flags all of these at runtime rather than silently working around
them:

- `TOTALS` has two columns headed **Tempo** and neither is tempo -- both equal
  `2026 PR`!`Team Total` for 136 of 138 teams. Tempo comes from `PlaysPG`.
- `TOTALS`' own **SPP RANK** does not rank the SPP beside it: it's a clean
  1-138 permutation that correlates **r = 0.02** with those SPP values, so it's
  a rank of a differently ordered list. `rank_SPP` is computed here;
  `SPP_RANK_SHEET` carries theirs for comparison.
- `TeamID` has **Arizona and Arizona State swapped** in the ESPN column.
- `2026 Win Total` has **#N/A** for Indiana's and Ball State's TAN WIN.

## Two traps in `2026 Win Total`

Worth knowing if you ever touch that read. Column J is not just the subtotal
team name -- on matchup rows it doubles as a conference-game flag holding `"c"`,
so "column J is filled" picks up ~700 junk rows. The real marker is column B
(the team's TAN Rating) being **empty** while J is filled. And don't sum the
win% column: the subtotal sits in that same column, so every team comes out at
exactly twice its win total.
