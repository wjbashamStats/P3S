#!/usr/bin/env python3
"""rank_team_grades.py -- rank every column of team_pff_grades_2026.csv.

The grades file carries one rank, on grade_over. Everything else -- coverage,
run defense, pass block, points scored and allowed -- is a bare number, so
"is 86.2 tackling good?" needs the whole column in front of you to answer.
This writes a companion file with a rank_<col> beside each one.

Conventions match rank_pff_stats.py, deliberately:

  * standard competition ranking, so ties share a rank and the next rank
    skips (two teams tied 4th are both 4th and the next is 6th);
  * the whole 138-team field, with no sample floor -- a team with five games
    and a team with seven are both ranked, because the per-game figures below
    already divide the difference out.

Teams play a different number of games by this point in the season (week 7:
five for 47 teams, six for 87, seven for 4), so the raw pf/pa totals are not
comparable across the field. Three per-game columns are derived and ranked
instead, and those are the ones to quote:

  ppg      points scored per game
  papg     points allowed per game
  margin   (pf - pa) per game

Lower is better for pa and papg; higher for everything else.

  python3 rank_team_grades.py
  python3 rank_team_grades.py --in team_pff_grades_2026.csv --out ranked.csv
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOWER_IS_BETTER = {"pa", "papg"}
SKIP = {"rank", "team", "record"}


def games(row):
    """Games played, from the W - L record."""
    parts = [p.strip() for p in row["record"].split("-")]
    return sum(int(p) for p in parts if p.lstrip("-").isdigit())


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def rank_column(rows, col):
    """Standard competition ranking over the whole field; ties share a rank."""
    entries = [(i, to_float(r.get(col))) for i, r in enumerate(rows)]
    entries = [(i, v) for i, v in entries if v is not None]
    entries.sort(key=lambda e: e[1], reverse=col not in LOWER_IS_BETTER)
    ranks, rank, prev = {}, 0, None
    for idx, (i, v) in enumerate(entries):
        if v != prev:
            rank = idx + 1
        ranks[i] = rank
        prev = v
    return ranks


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src",
                    default=os.path.join(HERE, "team_pff_grades_2026.csv"))
    ap.add_argument("--out", dest="dest",
                    default=os.path.join(HERE, "team_pff_grades_ranked_2026.csv"))
    args = ap.parse_args()

    with open(args.src, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        sys.exit(f"{args.src} is empty")

    for r in rows:
        g = games(r)
        r["games"] = g
        pf, pa = float(r["pf"]), float(r["pa"])
        r["ppg"] = f"{pf / g:.1f}"
        r["papg"] = f"{pa / g:.1f}"
        r["margin"] = f"{(pf - pa) / g:+.1f}"

    src_cols = [c for c in rows[0] if c not in SKIP and c not in ("games", "ppg", "papg", "margin")]
    derived = ["games", "ppg", "papg", "margin"]
    ranked = [c for c in src_cols + derived if c != "games"]

    out_rows = []
    rank_maps = {c: rank_column(rows, c) for c in ranked}
    for i, r in enumerate(rows):
        out = {"team": r["team"], "record": r["record"], "games": r["games"]}
        for c in ranked:
            out[c] = r[c]
            out[f"rank_{c}"] = rank_maps[c].get(i, "")
        out_rows.append(out)

    out_rows.sort(key=lambda r: int(r["rank_grade_over"] or 10**6))
    fieldnames = ["team", "record", "games"]
    for c in ranked:
        fieldnames += [c, f"rank_{c}"]

    with open(args.dest, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    print(f"wrote {args.dest}: {len(out_rows)} teams, {len(ranked)} ranked columns")
    print(f"  games played: " + ", ".join(
        f"{g}g x{sum(1 for r in out_rows if r['games'] == g)}"
        for g in sorted({r["games"] for r in out_rows})))
    print("  lower-is-better: " + ", ".join(sorted(LOWER_IS_BETTER)))


if __name__ == "__main__":
    main()
