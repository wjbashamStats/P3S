#!/usr/bin/env python3
"""
rank_pff_stats.py — add within-position national rank columns to a raw PFF
weekly/season summary export (passing, rushing, receiving, defense, or
offense_blocking).

For every performance stat column, adds a rank_<col> column: 1 = best,
ranked only among players at the SAME position (a WR's yards rank never
competes against a TE's) who clear a minimum-sample floor for that file
kind (see MIN_SAMPLE below) -- with only 1-2 games played this early in
the season, a small-sample outlier (1 pass attempt, complete, for a
"100%" rate) would otherwise get a misleadingly great rank. Players below
the floor keep their stats but get a blank rank, not a dropped row --
nobody disappears from the file, they just aren't ranked yet.

Direction matters: most stats are "higher is better" (yards, grades,
touchdowns), but some are "lower is better" (interceptions thrown,
missed tackles, sacks allowed) -- see LOWER_IS_BETTER below, kept
explicit per file kind rather than guessed from the column name, since
that's a real judgment call worth being able to review/adjust.

Ties share the same rank (standard competition ranking): two players tied
for the best mark in their position both get rank 1, and the next-best
gets rank 3, not 2.

Pure stdlib (csv only) -- matches the rest of this project's convention;
no pandas/numpy dependency.

Usage:
  python3 rank_pff_stats.py passing_summary17.csv --out passing_summary17_ranked.csv
  python3 rank_pff_stats.py defense_summary20.csv --out defense_summary20_ranked.csv --min-sample 20

Auto-detects file kind (passing/rushing/receiving/defense/blocking) from
the filename; pass --kind to override if the filename doesn't match.
"""
import argparse
import csv
import re
import sys
from collections import defaultdict

# Columns never ranked: identifiers and team-crosswalk metadata only.
# (Confirmed against PFF's own ranked exports: player_game_count and
# declined_penalties DO get ranked there -- sample size and "penalty
# called, then declined" both turn out to be real signal worth ranking,
# just handled via lower_is_better below where that's true.)
COMMON_EXCLUDE = {"player", "player_id", "position", "team_name", "franchise_id",
                   "teamid", "Team", "2025 Team"}

# Per file kind: which column to use as the minimum-sample gate + a
# sensible early-season default threshold, and which stat columns are
# "lower is better" (everything else defaults to higher-is-better).
KIND_CONFIG = {
    "passing": dict(
        match=r"passing",
        sample_col="attempts", default_min_sample=10,
        lower_is_better={
            "interceptions", "turnover_worthy_plays", "twp_rate", "sacks",
            "sack_percent", "drops", "drop_rate", "penalties", "bats",
            "thrown_aways", "hit_as_threw", "pressure_to_sack_rate",
            "def_gen_pressures", "declined_penalties",
        },
    ),
    "rushing": dict(
        match=r"rushing",
        sample_col="attempts", default_min_sample=5,
        lower_is_better={"fumbles", "drops", "penalties", "declined_penalties"},
    ),
    "receiving": dict(
        match=r"receiving",
        sample_col="targets", default_min_sample=3,
        lower_is_better={"drops", "drop_rate", "fumbles", "interceptions", "penalties",
                          "declined_penalties"},
    ),
    "defense": dict(
        match=r"defense",
        sample_col="snap_counts_defense", default_min_sample=15,
        lower_is_better={
            "missed_tackles", "missed_tackle_rate", "penalties",
            "qb_rating_against", "yards", "yards_per_reception",
            "yards_after_catch", "touchdowns", "receptions", "declined_penalties",
        },
    ),
    "blocking": dict(
        match=r"blocking",
        sample_col="snap_counts_block", default_min_sample=15,
        lower_is_better={
            "sacks_allowed", "hits_allowed", "hurries_allowed",
            "pressures_allowed", "penalties", "declined_penalties",
        },
    ),
}


def detect_kind(path):
    for kind, cfg in KIND_CONFIG.items():
        if re.search(cfg["match"], path, re.IGNORECASE):
            return kind
    return None


def to_float(x):
    if x is None or x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def is_numeric_column(rows, col):
    """A column counts as numeric/rankable if at least one row has a
    parseable float value in it (blank/non-numeric cells are tolerated --
    ranked as missing, same as any other None)."""
    return any(to_float(r.get(col)) is not None for r in rows)


def rank_column(rows, col, ascending, meets_floor):
    """Standard competition ranking (ties share a rank; next rank skips),
    scoped to (same position, meets sample floor). Returns {row_index: rank}
    -- rows failing either condition, or with a missing value, get no entry."""
    by_pos = defaultdict(list)
    for i, r in enumerate(rows):
        if not meets_floor[i]:
            continue
        v = to_float(r.get(col))
        if v is None:
            continue
        by_pos[r["position"]].append((i, v))

    ranks = {}
    for pos, entries in by_pos.items():
        entries.sort(key=lambda e: e[1], reverse=not ascending)
        rank = 0
        prev_v = None
        for pos_idx, (i, v) in enumerate(entries):
            if v != prev_v:
                rank = pos_idx + 1
            ranks[i] = rank
            prev_v = v
    return ranks


def rank_file(rows, cfg, min_sample):
    sample_col = cfg["sample_col"]
    has_sample_col = rows and sample_col in rows[0]
    if not has_sample_col:
        print(f"  [warn] sample column '{sample_col}' not found -- ranking everyone, no floor applied", file=sys.stderr)
        meets_floor = [True] * len(rows)
    else:
        meets_floor = [(to_float(r.get(sample_col)) or 0) >= min_sample for r in rows]

    fieldnames = list(rows[0].keys()) if rows else []
    stat_cols = [c for c in fieldnames if c not in COMMON_EXCLUDE and is_numeric_column(rows, c)]

    rank_cols = {}
    for col in stat_cols:
        ascending = col in cfg["lower_is_better"]
        rank_cols[f"rank_{col}"] = rank_column(rows, col, ascending, meets_floor)

    out_rows = []
    for i, r in enumerate(rows):
        out = dict(r)
        for rc, ranks in rank_cols.items():
            out[rc] = ranks.get(i, "")
        out["meets_min_sample"] = meets_floor[i]
        out_rows.append(out)

    out_fieldnames = fieldnames + list(rank_cols.keys()) + ["meets_min_sample"]
    return out_rows, out_fieldnames, meets_floor


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path", help="raw PFF summary export")
    ap.add_argument("--kind", choices=sorted(KIND_CONFIG), default=None,
                    help="override filename-based auto-detection")
    ap.add_argument("--min-sample", type=int, default=None,
                    help="override this kind's default minimum-sample threshold")
    ap.add_argument("--out", required=True, help="output CSV path")
    args = ap.parse_args()

    kind = args.kind or detect_kind(args.csv_path)
    if kind is None:
        sys.exit(f"Couldn't detect file kind from '{args.csv_path}' -- pass --kind explicitly "
                  f"(one of {sorted(KIND_CONFIG)}).")
    cfg = KIND_CONFIG[kind]
    min_sample = args.min_sample if args.min_sample is not None else cfg["default_min_sample"]

    with open(args.csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or "position" not in rows[0]:
        sys.exit("Expected a 'position' column to rank within -- is this really a PFF summary export?")

    print(f"Kind: {kind} | sample gate: {cfg['sample_col']} >= {min_sample} | {len(rows)} rows")
    out_rows, out_fieldnames, meets_floor = rank_file(rows, cfg, min_sample)
    n_ranked = sum(meets_floor)
    print(f"  {n_ranked}/{len(rows)} rows meet the sample floor and got ranked; "
          f"{len(rows) - n_ranked} kept their stats but no rank (small sample)")

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
