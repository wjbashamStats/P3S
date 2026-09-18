#!/usr/bin/env python3
"""
export_futures_csv.py -- pull just the futures/market-odds columns out of
team_ratings_2025.csv into their own CSV (Team, Conference.y, national
championship per-book prices, conference championship per-book prices,
win-totals per-book line/price/over-under). Drops Nat_X/Conf_X/Win_X7_*
-- confirmed-empty leftover columns from the old R script's unnamed-
header fallback (see build_futures_from_html.py).

The output is named for the season the futures are FOR, not for the
ratings file they were merged into: team_ratings_2025.csv is the 2025
ratings table, but the Nat_/Conf_/Win_ columns on it are the market's
prices on the 2026 season. actionnet/an_metrics.py looks the export up as
futures_<season>.csv and silently skips its odds columns when the name
doesn't match the season it's building, so getting this right matters.

Usage:
  python3 export_futures_csv.py                       # -> futures_2026.csv
  python3 export_futures_csv.py --season 2027
  python3 export_futures_csv.py --team-ratings team_ratings_2025.csv --out custom.csv
"""
import argparse
import csv

DROP_COLS = {"Nat_X", "Conf_X", "Win_X7_TotalLine", "Win_X7_Odds",
             "Win_X7_OverUnder", "Win_X7_Line"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team-ratings", default="team_ratings_2025.csv")
    ap.add_argument("--season", type=int, default=2026,
                    help="the season these futures are ON -- names the output "
                         "futures_<season>.csv (default 2026)")
    ap.add_argument("--out", default=None,
                    help="override the futures_<season>.csv name")
    args = ap.parse_args()
    out_path = args.out or f"futures_{args.season}.csv"

    with open(args.team_ratings, newline="") as f:
        reader = csv.DictReader(f)
        all_cols = list(reader.fieldnames)
        rows = list(reader)

    def group(prefix):
        return sorted(c for c in all_cols
                      if c not in DROP_COLS and c.startswith(prefix))

    futures_cols = (["Team", "Conference.y"] + group("Nat_") + group("Conf_") + group("Win_"))

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=futures_cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in futures_cols})

    print(f"Wrote {out_path}: {len(rows)} teams x {len(futures_cols)} columns")


if __name__ == "__main__":
    main()
