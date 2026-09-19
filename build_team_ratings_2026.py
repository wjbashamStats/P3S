#!/usr/bin/env python3
"""
build_team_ratings_2026.py -- write team_ratings_<season>.csv from the workbook.

The hub's spread and total model read team_ratings_2025.csv. Despite the name
that file is a one-off snapshot, and its SP / TAN columns never move: it is the
preseason 2026 board, frozen. The workbook's '2026 PR' sheet is the live one and
is refreshed weekly, so by week 3 the two disagree on every team -- Clemson 12.8
vs 8.1, Western Kentucky -5.3 vs -13.3, Houston 8.2 vs 11.6 -- always in the
direction of what has actually happened on the field.

Reading the stale file made every "diversion" partly an artifact: the model was
holding a preseason number while the book priced two games of results, so the
biggest disagreements clustered on exactly the teams whose season had gone
differently than expected. Measured across the 54 rated week-3 games, the old
model's lean agreed with 2026 margin of victory 31% of the time (correlation
-0.57), which is not a market edge, it is a stale input.

This writes the workbook's own ratings out in the same shape the page builders
already expect, so build_diversions_page_data.py --team-ratings team_ratings_2026.csv
runs on current numbers. The five-factor rank_ columns come across too, and in
the workbook those are CFBData26, so the radars become current-season as well.

The X2022_* columns have no workbook equivalent. They are carried over from
team_ratings_2025.csv purely as the fallback for the power table's ATS / Over
rows when the TeamRankings trends pages have not been saved; nothing else reads
them.

Run:  python3 build_team_ratings_2026.py --season 2026
"""
import argparse, csv, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "actionnet"))
from an_metrics import build, write_csv  # noqa: E402

# Carried over from the old snapshot. The 2022 columns are the power table's
# fallback when actionnet/input/trends is empty (see the module docstring).
# Everything else comes from the workbook.
LEGACY_COLS = ("X2022_ATS_Percent", "X2022_OU_Percent",
               "Rank_2022_ATS_Percent", "Rank_2022_OU_Percent")

# Mascot is different: it is filled from the workbook when an_metrics can derive
# it from the ESPN name, and left blank for the nine it cannot (Arizona State,
# Miami Ohio, San Jose State, UMass, ULM and friends). Blank is not cosmetic --
# load_ratings_raw keys on norm(Team + Mascot) and drops any row missing either,
# so those nine teams would silently lose their ratings, their games would fall
# out of the diversions board, and the TeamRankings trends join would miss them
# too. The old snapshot has all of them, so fill only the gaps.
LEGACY_FILL = ("Mascot",)


def _norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def carry_legacy(rows, legacy_path, log=print):
    if not os.path.exists(legacy_path):
        log(f"[miss] {os.path.basename(legacy_path)} absent; no 2022 ATS/OU fallback columns")
        return 0
    legacy = {_norm(r.get("Team")): r for r in csv.DictReader(open(legacy_path))}
    hit, filled = 0, []
    for r in rows:
        src = legacy.get(_norm(r.get("Team")))
        if not src:
            continue
        hit += 1
        for c in LEGACY_COLS:
            r[c] = src.get(c, "")
        for c in LEGACY_FILL:
            if not (r.get(c) or "").strip():
                r[c] = src.get(c, "")
                filled.append(f"{r.get('Team')} ({c})")
    log(f"[join] {'2022 ATS/OU fallback':<22} {hit}/{len(rows)} teams")
    if filled:
        log(f"[fill] {'from old snapshot':<22} {len(filled)}: {', '.join(filled)}")
    return hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=os.path.join(HERE, "actionnet", "input", "AN_season.xlsx"))
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--odds", default=None, help="futures CSV; defaults to futures_<season>.csv when present")
    ap.add_argument("--trends-dir", default=os.path.join(HERE, "actionnet", "input", "trends"))
    ap.add_argument("--legacy", default=os.path.join(HERE, "team_ratings_2025.csv"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    odds = args.odds
    if odds is None:
        guess = os.path.join(HERE, f"futures_{args.season}.csv")
        odds = guess if os.path.exists(guess) else None
    trends = args.trends_dir if os.path.isdir(args.trends_dir) else None

    rows = build(args.xlsx, args.season, odds, trends)
    carry_legacy(rows, args.legacy)
    out = args.out or os.path.join(HERE, f"team_ratings_{args.season}.csv")
    cols = write_csv(rows, out)
    print(f"\nwrote {out}: {len(rows)} teams, {len(cols)} columns")


if __name__ == "__main__":
    main()
