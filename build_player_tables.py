#!/usr/bin/env python3
"""
build_player_tables.py — adapter: per-market PFF clean files -> the two
generic tables data_load.py expects (player_season_totals.csv,
player_game_logs.csv).

Why this exists: PFF exports come split by market (passing/rushing/
receiving), one file for season totals and one for weekly game logs each.
A player who both passes and rushes (dual-threat QB) or both rushes and
catches (receiving back) has rows in more than one file. This script merges
those per-market files on player_id (the reliable join key -- see
PROJECT_STATE.md quirk #5, names collide) into one row per player
(season totals) or per player-week (game logs), in the column names
project.py / data_load.py already read.

Season totals are read from the *_season_clean.csv files directly (not
summed from weekly), which sidesteps the week-14 receiving-weekly
truncation quirk (PROJECT_STATE.md quirk #1) for rate calculations --
those files carry the real season totals. The truncation still leaves
~73 WRs with fewer weekly rows than games played, which affects the
variance estimate for those players; the fix documented in
PROJECT_STATE.md (season file is source of truth for the mean) is
enough for now.

Also builds player_prior_totals.csv from the 2024 season files (2024_
passing/rushing/receiving_season_clean.csv), if present -- the real
prior-year data that removes the lookahead bias 2025-derived "prior"
totals had (see PROJECT_STATE.md). Keyed by player_id ONLY (no team),
because a transferred player's 2024 team isn't their 2025 team --
build.py resolves current team/roster from the 2025 side and looks up
2024 rates by player_id, so a transfer's history follows the player,
not the old school. player_id is a reliable cross-season key: spot
checked at ~99.5-100% stable for the same person year over year (the
handful of exceptions are genuine same-name-different-player
collisions, quirk #5).

Run:  python3 build_player_tables.py
Regenerate any time the *_clean.csv files change; outputs are gitignored.
"""
import csv, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# (source file, {source column -> destination column})
SEASON_SOURCES = [
    ("passing_season_clean.csv",   {"attempts": "pass_att", "yards": "pass_yds",
                                     "touchdowns": "pass_td"}),
    ("rushing_season_clean.csv",   {"attempts": "rush_att", "yards": "rush_yds",
                                     "touchdowns": "rush_td"}),
    ("receiving_season_clean.csv", {"targets": "targets", "receptions": "receptions",
                                     "yards": "rec_yds", "touchdowns": "rec_td"}),
]
PRIOR_SEASON_SOURCES = [
    ("2024_passing_season_clean.csv",   {"attempts": "pass_att", "yards": "pass_yds",
                                          "touchdowns": "pass_td"}),
    ("2024_rushing_season_clean.csv",   {"attempts": "rush_att", "yards": "rush_yds",
                                          "touchdowns": "rush_td"}),
    ("2024_receiving_season_clean.csv", {"targets": "targets", "receptions": "receptions",
                                          "yards": "rec_yds", "touchdowns": "rec_td"}),
]
WEEKLY_SOURCES = [
    ("passing_weekly_clean.csv",   {"attempts": "pass_att", "yards": "pass_yds",
                                     "touchdowns": "pass_td"}),
    ("rushing_weekly_clean.csv",   {"attempts": "rush_att", "yards": "rush_yds",
                                     "touchdowns": "rush_td"}),
    ("receiving_weekly_clean.csv", {"targets": "targets", "receptions": "receptions",
                                     "yards": "rec_yds", "touchdowns": "rec_td"}),
]

SEASON_COLS = ["player", "team", "player_id", "position", "games",
               "pass_att", "pass_yds", "pass_td",
               "rush_att", "rush_yds", "rush_td",
               "targets", "receptions", "rec_yds", "rec_td"]
WEEKLY_COLS = ["player", "team", "player_id", "week",
               "pass_att", "pass_yds", "pass_td",
               "rush_att", "rush_yds", "rush_td",
               "targets", "receptions", "rec_yds", "rec_td"]


def _read(fname):
    path = os.path.join(BASE_DIR, fname)
    if not os.path.exists(path):
        print(f"  [warn] {fname} not found, skipping")
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _identity(row, out):
    out.setdefault("player", row.get("player", ""))
    out.setdefault("team", row.get("team_name", ""))
    out.setdefault("player_id", row.get("player_id", ""))
    out.setdefault("position", row.get("position", ""))


def build_season_totals(sources=SEASON_SOURCES):
    merged = {}
    games_seen = {}
    for fname, colmap in sources:
        for r in _read(fname):
            pid = r.get("player_id")
            if not pid:
                continue
            out = merged.setdefault(pid, {})
            _identity(r, out)
            for src, dst in colmap.items():
                v = r.get(src)
                if v not in (None, ""):
                    out[dst] = v
            g = r.get("player_game_count")
            if g not in (None, ""):
                games_seen.setdefault(pid, []).append(float(g))

    rows = []
    for pid, out in merged.items():
        out["games"] = max(games_seen.get(pid, [1]))
        rows.append(out)
    return rows


def build_game_logs():
    merged = {}
    for fname, colmap in WEEKLY_SOURCES:
        for r in _read(fname):
            pid = r.get("player_id")
            wk = r.get("week")
            if not pid or wk is None or wk == "":
                continue
            key = (pid, wk)
            out = merged.setdefault(key, {})
            _identity(r, out)
            out.setdefault("week", wk)
            for src, dst in colmap.items():
                v = r.get(src)
                if v not in (None, ""):
                    out[dst] = v
    return list(merged.values())


def _write(rows, cols, out_name):
    path = os.path.join(BASE_DIR, out_name)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"  wrote {out_name}: {len(rows)} rows")


def main():
    print("Building player_season_totals.csv ...")
    _write(build_season_totals(), SEASON_COLS, "player_season_totals.csv")
    print("Building player_game_logs.csv ...")
    _write(build_game_logs(), WEEKLY_COLS, "player_game_logs.csv")

    if any(os.path.exists(os.path.join(BASE_DIR, f)) for f, _ in PRIOR_SEASON_SOURCES):
        print("Building player_prior_totals.csv (2024, keyed by player_id only) ...")
        _write(build_season_totals(PRIOR_SEASON_SOURCES), SEASON_COLS, "player_prior_totals.csv")
    else:
        print("No 2024_*_season_clean.csv files found -- skipping player_prior_totals.csv")


if __name__ == "__main__":
    main()
