#!/usr/bin/env python3
"""
refresh_week.py -- the whole weekly refresh in one command.

    python3 refresh_week.py --week 5

Runs every step in order, stops on the first real failure, and ends with a
readiness report naming anything still stale or missing. Each stage prints
the command it ran, so a failure can be reproduced on its own.

Stages, in dependency order:

  1. trends     pull_trends.py -- the three TeamRankings pages (free, network)
  2. pff        clean + rank new PFF exports from --pff-dir, if given
  3. tables     build_player_tables.py
  4. ratings    build_team_ratings_2026.py (needs 1 and 2 to be current)
  5. odds       pull_live_week.py -- SPENDS ODDS API CREDITS, so it is opt-in
                via --pull-odds and never runs by default
  6. board      diversions / props / dfs / impact page data
  7. pages      pages/build_pages.py + pages/build_hub.py

The slate window is read out of the lines file rather than assumed: it takes
the day with the most kickoffs (the Saturday) and spans one day either side.
A live pull labels two weekends with the same week number, so trusting the
--week label alone has silently carried already-played games onto a board
before. Override with --date-start / --date-end.

Network stages degrade rather than abort: this sandbox blocks teamrankings.com
and the Odds API, so stage 1 failing is a warning and the run continues on the
files already on disk. Stage 1 refusing to overwrite a good page with a worse
one is also a warning, not a stop, for the same reason.

Examples:
  python3 refresh_week.py --week 5
  python3 refresh_week.py --week 5 --pff-dir ~/Downloads --pull-odds
  python3 refresh_week.py --week 5 --only board pages
  python3 refresh_week.py --week 5 --skip trends odds --dry-run
"""
import argparse
import collections
import csv
import datetime as dt
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES = ["trends", "pff", "tables", "ratings", "odds", "board", "pages"]
# Stages whose failure is reported but does not stop the run: both need network
# this sandbox does not have, and both leave the previous week's files usable.
SOFT = {"trends", "odds"}

# PFF export filename stem -> our kind. The uploads arrive with a random
# prefix and a trailing number (passing_summary22.csv), so match on the stem.
PFF_KINDS = {"passing_summary": "passing", "rushing_summary": "rushing",
             "receiving_summary": "receiving", "defense_summary": "defense",
             "offense_blocking": "blocking"}
ET = dt.timezone(dt.timedelta(hours=-4))


class Runner:
    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.log = []

    def run(self, cmd, stage, soft=False):
        print(f"  $ {' '.join(cmd)}")
        if self.dry_run:
            return True
        p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
        out = (p.stdout or "") + (p.stderr or "")
        for line in out.strip().splitlines():
            print(f"    {line}")
        if p.returncode != 0:
            self.log.append((stage, soft, out.strip().splitlines()[-1] if out.strip() else
                             f"exit {p.returncode}"))
        return p.returncode == 0


def slate_window(lines_path, week):
    """The Saturday with the most kickoffs, plus a day either side."""
    days = collections.Counter()
    for r in csv.DictReader(open(lines_path)):
        if str(r.get("week")) != str(week):
            continue
        ct = r.get("commence_time")
        if not ct:
            continue
        days[dt.datetime.fromisoformat(ct.replace("Z", "+00:00")).astimezone(ET).date()] += 1
    if not days:
        return None, None, days
    peak = days.most_common(1)[0][0]
    return peak - dt.timedelta(days=1), peak + dt.timedelta(days=1), days


def clean_and_rank(pff_dir, runner):
    """Dedupe each raw export into 2026_<kind>_season_clean.csv, then rank it."""
    found = {}
    for path in glob.glob(os.path.join(os.path.expanduser(pff_dir), "*.csv")):
        base = os.path.basename(path)
        for stem, kind in PFF_KINDS.items():
            if stem in base:
                # newest wins if several exports of the same kind are sitting there
                if kind not in found or os.path.getmtime(path) > os.path.getmtime(found[kind]):
                    found[kind] = path
    if not found:
        print(f"    no PFF exports matching {sorted(PFF_KINDS)} in {pff_dir}")
        return False
    ok = True
    for kind, path in sorted(found.items()):
        rows = list(csv.DictReader(open(path)))
        if not rows:
            print(f"    [skip] {kind}: {os.path.basename(path)} is empty")
            ok = False
            continue
        hdr = list(rows[0])
        seen, dedup = set(), []
        for r in rows:
            t = tuple(r.get(c) for c in hdr)
            if t in seen:
                continue
            seen.add(t)
            dedup.append(r)
        best = {}
        for r in dedup:
            pid = r.get("player_id")
            g = float(r.get("player_game_count") or 0)
            if pid not in best or g > best[pid][0]:
                best[pid] = (g, r)
        out = [v[1] for v in best.values()]
        dest = os.path.join(HERE, f"2026_{kind}_season_clean.csv")
        print(f"    {kind:10} {os.path.basename(path):34} {len(rows):5} -> {len(out):5} rows")
        if not runner.dry_run:
            with open(dest, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=hdr)
                w.writeheader()
                w.writerows(out)
        ok = runner.run([sys.executable, "rank_pff_stats.py", dest,
                         "--out", os.path.join(HERE, f"2026_{kind}_season_ranked.csv")],
                        "pff") and ok
    return ok


def readiness(week, season, lines, props, start, end):
    """What is still stale or missing, checked against the data rather than
    assumed. This is the part worth reading when the run finishes."""
    notes = []
    try:
        sys.path.insert(0, os.path.join(HERE, "actionnet"))
        from teamrankings import load_trends, EXTS
        import data_load as DL
        pff = DL.load_current_totals(season=season)
        pff_games = collections.Counter()
        for r in pff.values():
            pff_games[r.get("team")] = max(pff_games[r.get("team")], int(float(r.get("games") or 0)))
        pff_mode = collections.Counter(pff_games.values()).most_common(1)[0][0] if pff_games else 0
        tdir = os.path.join(HERE, "actionnet", "input", "trends")
        for stem, prefix, col in (("win_trends", "TR_win", "TR_win_win_loss_record"),
                                  ("ats_trends", "TR_ats", "TR_ats_ats_record"),
                                  ("ou_trends", "TR_ou", "TR_ou_over_record")):
            path = next((os.path.join(tdir, stem + e) for e in EXTS
                         if os.path.exists(os.path.join(tdir, stem + e))), None)
            if not path:
                notes.append(f"trends {stem}: missing")
                continue
            rows = load_trends(path, prefix)
            depth = collections.Counter(
                sum(int(r.get(col + s) or 0) for s in ("_W", "_L", "_T")) for r in rows)
            mode = depth.most_common(1)[0][0]
            if mode < pff_mode:
                notes.append(f"trends {stem}: most teams at {mode} games, PFF is at {pff_mode}")
    except Exception as e:
        notes.append(f"trends check could not run: {type(e).__name__}: {e}")
    try:
        import csv as _csv
        g = collections.Counter()
        for r in _csv.DictReader(open(os.path.join(HERE, "team_pff_grades_2026.csv"))):
            w, l = [int(x) for x in r["record"].replace(" ", "").split("-")][:2]
            g[w + l] += 1
        mode = g.most_common(1)[0][0]
        if mode < pff_mode:
            notes.append(f"team_pff_grades_2026.csv: most teams at {mode} games, PFF is at {pff_mode}")
    except Exception:
        notes.append("team_pff_grades_2026.csv: missing or unreadable")
    sal = os.path.join(HERE, f"fanduel_salaries_{season}wk{week}.csv")
    if not os.path.exists(sal):
        notes.append(f"{os.path.basename(sal)}: missing, the DFS lineup generator will be inert")
    for p in (lines, props):
        if not os.path.exists(os.path.join(HERE, p)):
            notes.append(f"{p}: missing")
    return notes


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--pff-dir", default=None,
                    help="directory holding new PFF exports to clean and rank")
    ap.add_argument("--pull-odds", action="store_true",
                    help="run pull_live_week.py -- SPENDS ODDS API CREDITS")
    ap.add_argument("--date-start", default=None, help="override the detected slate window")
    ap.add_argument("--date-end", default=None)
    ap.add_argument("--only", nargs="*", choices=STAGES, default=None)
    ap.add_argument("--skip", nargs="*", choices=STAGES, default=[])
    ap.add_argument("--dry-run", action="store_true", help="print the commands, run nothing")
    args = ap.parse_args()

    season = args.season
    if season is None:
        import config as C
        season = C.SEASON
    wk, py = args.week, sys.executable
    lines = f"hist_lines_live_{season}wk{wk}.csv"
    props = f"hist_props_live_{season}wk{wk}.csv"
    want = [s for s in (args.only or STAGES) if s not in args.skip]
    runner = Runner(args.dry_run)

    print(f"Week {wk}, season {season}. Stages: {', '.join(want)}\n")

    # Check this before spending four stages of work on a run that cannot
    # finish: the board needs a lines file and nothing upstream produces one
    # unless --pull-odds was passed.
    needs_lines = ("board" in want or "pages" in want) and not (
        "odds" in want and args.pull_odds)
    if needs_lines and not os.path.exists(os.path.join(HERE, lines)):
        print(f"{lines} is not here, and the board needs it.\n"
              f"  Pull it:   python3 refresh_week.py --week {wk} --pull-odds   (spends credits)\n"
              f"  Or commit it from the machine that pulled it, then re-run.")
        return 1

    if "trends" in want:
        print("[1/7] trends")
        runner.run([py, "pull_trends.py", "--season", str(season)], "trends", soft=True)
    if "pff" in want and args.pff_dir:
        print("[2/7] pff exports")
        clean_and_rank(args.pff_dir, runner)
    elif "pff" in want:
        print("[2/7] pff exports -- no --pff-dir given, using the files already in the repo")
    if "tables" in want:
        print("[3/7] player tables")
        if not runner.run([py, "build_player_tables.py"], "tables"):
            return fail(runner)
    if "ratings" in want:
        print("[4/7] team ratings")
        if not runner.run([py, "build_team_ratings_2026.py", "--season", str(season)], "ratings"):
            return fail(runner)
    if "odds" in want and args.pull_odds:
        print("[5/7] live odds -- this spends credits")
        runner.run([py, "pull_live_week.py", "--week", str(wk), "--season", str(season),
                    "--out-lines", lines, "--out-props", props], "odds", soft=True)
    elif "odds" in want:
        print("[5/7] live odds -- skipped (pass --pull-odds to pull; it spends credits)")

    start, end = args.date_start, args.date_end
    if "board" in want or "pages" in want:
        if not os.path.exists(os.path.join(HERE, lines)):
            print(f"\n{lines} is not here -- the odds pull did not produce it.")
            return 1
        if not (start and end):
            s, e, days = slate_window(os.path.join(HERE, lines), wk)
            if s is None:
                print(f"\nNo week-{wk} rows with a kickoff time in {lines}.")
                return 1
            start, end = start or s.isoformat(), end or e.isoformat()
            spread = ", ".join(f"{d:%a %m-%d} {n}" for d, n in sorted(days.items()))
            print(f"\n  slate window {start} to {end}  (kickoffs: {spread})")

    if "board" in want:
        print("\n[6/7] board")
        win = ["--date-start", start, "--date-end", end]
        if not runner.run([py, "build_diversions_page_data.py", "--game-lines", lines,
                           "--team-ratings", f"team_ratings_{season}.csv", "--week", str(wk),
                           "--season", str(season), *win,
                           "--out", f"diversions_{season}wk{wk}.json"], "board"):
            return fail(runner)
        for b in ("props", "dfs", "impact"):
            cmd = [py, f"build_{b}_page_data.py", "--week", str(wk), "--season", str(season),
                   "--game-lines", lines, "--team-ratings", f"team_ratings_{season}.csv", *win,
                   "--out", f"{b}_{season}wk{wk}.json"]
            if b != "dfs":
                cmd[6:6] = ["--props", props]
            if not runner.run(cmd, "board"):
                return fail(runner)

    if "pages" in want:
        print("\n[7/7] pages")
        if not runner.run([py, "pages/build_pages.py", "--season", str(season),
                           "--week", str(wk)], "pages"):
            return fail(runner)
        runner.run([py, "pages/build_hub.py"], "pages")

    print()
    soft_fails = [(s, m) for s, soft, m in runner.log if soft]
    for s, m in soft_fails:
        print(f"[warn] {s}: {m}")
    if not args.dry_run:
        notes = readiness(wk, season, lines, props, start, end)
        if notes:
            print("\nStill stale or missing:")
            for n in notes:
                print(f"  - {n}")
        else:
            print("\nEverything current: trends, team grades and salaries all match the PFF drop.")
    print(f"\nDone. pages/build/hub_page.html is the artifact.")
    return 0


def fail(runner):
    print("\nStopped. Last failure:")
    for s, soft, m in runner.log:
        print(f"  {s}: {m}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
