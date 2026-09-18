#!/usr/bin/env python3
"""
refresh_futures.py -- one command for the weekly futures refresh: take a
saved futures_html/week<N>/ dump, merge every page in it into
team_ratings_2025.csv, and export the futures-only CSV.

This is a wrapper, not new logic. It runs exactly what you would type by
hand, and prints each command before running it:

  python3 build_futures_from_html.py --team-ratings team_ratings_2025.csv \
      --national   futures_html/week<N>/national_futures.html \
      --win-totals futures_html/week<N>/win_totals.html \
      --conf SEC=futures_html/week<N>/SEC_championship.html \
      ... (one --conf per conference page found in the dump) ...
      --out team_ratings_2025.csv
  python3 export_futures_csv.py --season <SEASON>

It exists because the conference flags are assembled by hand otherwise --
eleven of them, each of which has to name a label AND a path, and a
forgotten one silently leaves last week's prices in place for that
conference rather than erroring.

Conference labels come from the filenames the dump writes
(SEC_championship.html -> SEC), so a page added to dump_futures_html.PAGES
is picked up here with no change.

The dump itself needs network + a real browser and so runs on YOUR
machine, not in the sandbox:

  python3 dump_futures_html.py --week <N>       # writes futures_html/week<N>/
  python3 refresh_futures.py --week <N>         # this script
"""
import argparse
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    print("\n$ " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode != 0:
        sys.exit(f"failed ({r.returncode}): {' '.join(cmd)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=int, required=True,
                    help="which futures_html/week<N>/ dump to merge")
    ap.add_argument("--season", type=int, default=2026,
                    help="season these futures are FOR -- names the export "
                         "(futures_<season>.csv). Default 2026.")
    ap.add_argument("--html-dir", default=None,
                    help="override futures_html/week<N>/")
    ap.add_argument("--team-ratings", default="team_ratings_2025.csv")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the commands and the pages found, run nothing")
    args = ap.parse_args()

    html_dir = args.html_dir or os.path.join("futures_html", f"week{args.week}")
    abs_dir = os.path.join(HERE, html_dir)
    if not os.path.isdir(abs_dir):
        sys.exit(f"no such dump: {html_dir} -- run dump_futures_html.py --week {args.week} first")

    national = os.path.join(html_dir, "national_futures.html")
    win_totals = os.path.join(html_dir, "win_totals.html")
    confs = sorted(glob.glob(os.path.join(abs_dir, "*_championship.html")))

    cmd = [sys.executable, "build_futures_from_html.py",
           "--team-ratings", args.team_ratings]
    if os.path.exists(os.path.join(HERE, national)):
        cmd += ["--national", national]
    else:
        print(f"  [warn] {national} missing -- national championship prices not refreshed")
    if os.path.exists(os.path.join(HERE, win_totals)):
        cmd += ["--win-totals", win_totals]
    else:
        print(f"  [warn] {win_totals} missing -- win totals not refreshed")
    for path in confs:
        label = os.path.basename(path)[: -len("_championship.html")]
        cmd += ["--conf", f"{label}={os.path.join(html_dir, os.path.basename(path))}"]
    # Written back over the same file: the futures columns are part of
    # team_ratings_2025.csv, and build_futures_from_html only ever touches
    # the Nat_/Conf_/Win_ ones (the model's own Win Total/TAN_WIN/SP._WIN
    # are left alone -- see its docstring).
    cmd += ["--out", args.team_ratings]

    export = [sys.executable, "export_futures_csv.py",
              "--team-ratings", args.team_ratings, "--season", str(args.season)]

    print(f"{html_dir}: {len(confs)} conference pages "
          f"({', '.join(os.path.basename(p)[: -len('_championship.html')] for p in confs)})")
    if args.dry_run:
        print("\n$ " + " ".join(cmd))
        print("\n$ " + " ".join(export))
        print("\n(--dry-run: nothing written)")
        return
    run(cmd)
    run(export)
    print(f"\nDone. futures_{args.season}.csv and {args.team_ratings} are refreshed.")


if __name__ == "__main__":
    main()
