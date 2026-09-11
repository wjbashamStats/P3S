#!/usr/bin/env python3
"""
export_futures_csv.py -- pull just the futures/market-odds columns out of
team_ratings_2025.csv into their own CSV (Team, Conference.y, national
championship per-book prices, conference championship per-book prices,
win-totals per-book line/price/over-under). Drops Nat_X/Conf_X/Win_X7_*
-- confirmed-empty leftover columns from the old R script's unnamed-
header fallback (see build_futures_from_html.py).

Usage:
  python3 export_futures_csv.py
  python3 export_futures_csv.py --team-ratings team_ratings_2025.csv --out futures_2025.csv
"""
import argparse
import csv

DROP_COLS = {"Nat_X", "Conf_X", "Win_X7_TotalLine", "Win_X7_Odds",
             "Win_X7_OverUnder", "Win_X7_Line"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team-ratings", default="team_ratings_2025.csv")
    ap.add_argument("--out", default="futures_2025.csv")
    args = ap.parse_args()

    with open(args.team_ratings, newline="") as f:
        reader = csv.DictReader(f)
        all_cols = list(reader.fieldnames)
        rows = list(reader)

    def group(prefix):
        return sorted(c for c in all_cols
                      if c not in DROP_COLS and c.startswith(prefix))

    futures_cols = (["Team", "Conference.y"] + group("Nat_") + group("Conf_") + group("Win_"))

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=futures_cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in futures_cols})

    print(f"Wrote {args.out}: {len(rows)} teams x {len(futures_cols)} columns")


if __name__ == "__main__":
    main()
