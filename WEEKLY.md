# The weekly update

Who runs what, in order. The short version: you send four things, Claude does
the rest. Nothing here has to happen in one sitting — send each piece as you
get it and Claude processes what has arrived.

The only ordering rule that matters: **the ratings are rebuilt once the team
grades, the workbook and the futures are all in.** Rebuilding earlier produces
a file whose inputs are from different weeks.

---

## What Claude can and cannot reach

Settled by testing, not assumption. Re-test if the environment changes.

| Source | Claude | Why |
|---|---|---|
| TeamRankings trends | **yes** | allowed host |
| ESPN scores and box scores | **yes** | allowed host |
| ourlads depth charts | **yes** | allowed host |
| National Weather Service | **yes** | allowed host |
| The Odds API (live lines) | **no** | host reachable, but no `ODDS_API_KEY` in the container |
| Vegas Insider (futures) | **no** | needs a real browser; headless Chromium does not trust the proxy CA |
| PFF | **no** | no API; the exports are downloads |

Adding `ODDS_API_KEY` as an environment secret would move the live lines to
Claude's side permanently and leave you with only futures and the PFF drops.

---

## Your side

### 1. Live lines  (Friday evening or Saturday morning, not earlier)

```bash
python3 pull_live_week.py --week N --dry-run   # free: lists the slate, spends nothing
python3 pull_live_week.py --week N             # ~2 credits for lines, ~6 per game for props
```

Writes `hist_lines_live_2026wkN.csv` and `hist_props_live_2026wkN.csv` — exactly
the names the build looks for.

Timing matters more than anything else here. The pull captures lines as they are
at that moment, and `qa_card.py` warns if the file is more than six hours old.

### 2. Futures

```bash
python3 dump_futures_html.py --week N
python3 dump_futures_html.py --validate futures_html/weekN    # want 11/11
python3 refresh_futures.py --week N
```

`win_totals` has failed four weeks running — it renders without an odds table,
so `refresh_futures.py` finds no page and silently keeps the prices it had. If
`--validate` says 10/11, retry just that page:

```bash
python3 dump_futures_html.py --week N --only win_totals --wait 20
```

If it fails again, push anyway and tell Claude; the Win_* columns stay stale and
the card's source note says so.

### 3. The PFF drops

Download the five player exports (passing, rushing, receiving, blocking,
defense) and attach them to the chat. Paste the team grades table — the team
list and then the value rows, as you have been.

### 4. The Action Network workbook

Attach the `.xlsx`.

### 5. Push

```bash
git add -A
git commit -m "Week N lines, props and futures"
git push origin claude/college-football-betting-handoff-mhf2nh
```

`git add -A` catches `futures_html/weekN/` too, which is worth having: without
the raw pages Claude cannot run `--validate` to confirm the pull was complete.

**If git says the branches have diverged**, merge — never rebase, it would
rewrite your commits:

```bash
git config pull.rebase false      # once, then pull normally
git pull origin claude/college-football-betting-handoff-mhf2nh
```

A conflict in `team_ratings_2026.csv` or `team_ratings_2025.csv` does not need
resolving by hand. They are generated. Take either side, commit, and Claude
regenerates them:

```bash
git checkout --ours team_ratings_2026.csv && git add team_ratings_2026.csv && git commit
```

---

## Claude's side

In this order, on the data as it arrives:

1. **Grade last week** from ESPN finals and box scores, as soon as the games
   are played — the PFF drop is not needed for this.
2. **Team grades** — validated (team set, no points backwards, no idle team
   moving), installed, and the slate reconciled against the delta, which also
   double-checks the ESPN grading.
3. **Player drop** — validated, cleaned, deduped, ranked. Settles any prop
   where the player was missing from a box score: a game count that went up
   means he played, which is a loss, not a void.
4. **Workbook** — sheets checked, installed.
5. **Trends** — pulled from TeamRankings. No action from you.
6. **Ratings rebuilt**, once 2, 4 and the futures are all in:

   ```bash
   python3 build_team_ratings_2026.py --season 2026
   python3 rank_team_grades.py
   ```

   Expect every workbook join at `unmatched: 0`. The futures join always shows
   `unmatched: 2` — North Dakota State and Sacramento State are in the grade set
   because they played FBS opponents and Vegas posts no futures on them. That is
   permanent and not a fault.

7. **Board and pages**:

   ```bash
   python3 refresh_week.py --week N --only board pages
   ```

8. **Card** — recompute, screens, depth charts, weather, QA, build, push.

---

## Checks that must pass before a card ships

- `python3 articles/build/qa_card.py --week N` — all checks, no failures.
- `python3 check_card_conditions.py --week N` — every prop player first string,
  every venue's forecast read.
- `python3 test_prop_screens.py` and `python3 test_depth_chart_names.py`.

The game-count distributions in the PFF grades and the TeamRankings trends
should match. When they do, every input is on the same week; when they do not,
something is a week behind.
