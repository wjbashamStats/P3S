#!/usr/bin/env python3
"""
clean_pff_stats.py — clean the PFF weekly + season-total exports.

What it does:
  1. Drops exact-duplicate rows (the receiving file had 1,755 of them).
  2. Enforces one row per (player_id, week) for weekly files, and one row per
     player_id for season files, keeping the fullest record on any residual dupe.
  3. Writes *_clean.csv for each input.

The only file with duplicates in the source set was receiving_weekly; the others
pass through unchanged but are re-emitted clean for a uniform pipeline.

Usage:  python3 clean_pff_stats.py <input_dir> <output_dir>
"""
import sys, os
import pandas as pd

WEEKLY = {
    'passing':   'passing_summary_combined.csv',
    'rushing':   'rushing_summary_combined.csv',
    'receiving': 'receiving_summary_combined.csv',
    'defense':   'defense_summary_combined.csv',
}
SEASON = {
    'passing':   'passing_summarySeasonTotal.csv',
    'rushing':   'rushing_summarySeasonTotal.csv',
    'receiving': 'receiving_summarySeasonTotal.csv',
    'defense':   'defense_summarySeasonTotal.csv',
    'blocking':  'offense_blockingSeasonTotal.csv',
}


def clean(df, keycols):
    df = df.drop_duplicates()
    if df.duplicated(keycols).any():
        sortcol = 'player_game_count' if 'player_game_count' in df.columns else keycols[0]
        df = df.sort_values(sortcol, ascending=False).drop_duplicates(keycols, keep='first')
    return df


def main():
    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    print(f"{'file':24s} {'raw':>7s} {'removed':>8s} {'clean':>7s}")
    print("-" * 50)
    for name, f in WEEKLY.items():
        p = os.path.join(indir, f)
        if not os.path.exists(p):
            continue
        df = pd.read_csv(p, low_memory=False)
        n0 = len(df)
        df = clean(df, ['player_id', 'week'])
        df.to_csv(os.path.join(outdir, f"{name}_weekly_clean.csv"), index=False)
        print(f"{name+' (weekly)':24s} {n0:7d} {n0-len(df):8d} {len(df):7d}")
    for name, f in SEASON.items():
        p = os.path.join(indir, f)
        if not os.path.exists(p):
            continue
        df = pd.read_csv(p, low_memory=False)
        n0 = len(df)
        df = clean(df, ['player_id'])
        df.to_csv(os.path.join(outdir, f"{name}_season_clean.csv"), index=False)
        print(f"{name+' (season)':24s} {n0:7d} {n0-len(df):8d} {len(df):7d}")


if __name__ == "__main__":
    main()
