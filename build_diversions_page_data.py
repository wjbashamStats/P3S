#!/usr/bin/env python3
"""
build_diversions_page_data.py — one-off: compare book spreads/totals
against a power-rating-implied line, for the "biggest diversions" page.

Predicted SPREAD comes from SP+ differential + home-field edge (team_
ratings_2025.csv's SP and HFACW columns) -- SP+ is itself opponent-
adjusted, so this tracks the book much better than a naive difference of
each team's own scoring average. That naive approach (summing/differencing
"Team Total") was tried first and produced a nonsense -5.7 predicted
spread for USC (-38.5 actual) against a bad San Jose State team, because
it doesn't know anything about the SPECIFIC opponent -- it's each team's
OWN average expected output, blind to who they're playing. SP+ is built
for exactly this (opponent-adjusted efficiency), so it's used for spread.

Predicted TOTAL keeps the naive sum-of-Team-Total approach -- a total
isn't about relative strength, it's about pace + scoring level, which
Team Total (each team's own average points) is actually built to answer,
and it tracked reasonably (diffs mostly within ~4 points on the games
checked) even though it fails badly for spread.

Both are simple, transparent, un-fitted power-rating comparisons, not a
tuned model -- same philosophy as the rest of this project, and there is
NO backtest for this (there's no historical "predicted spread" file to
validate against). Treat as directional, not gospel.

DATA CAVEAT (important): the live game-lines pull (hist_lines_live_*.csv)
has no per-row date before the fix in this same commit -- the Odds API's
/odds endpoint returns the WHOLE upcoming slate, not just one week, so a
team can appear more than once (its week-1 AND week-2 game, e.g.). Only
games that also appear in the props pull (which DOES carry commence_time)
can be safely confirmed as this week's -- this script only uses those.
Re-pull with pull_live_week.py (now patched to stamp commence_time on
every line, not just props) for full week-1 coverage next time.

Run:  python3 build_diversions_page_data.py --out diversions_2026wk1.json
"""
import argparse, csv, json
import data_load as DL


def norm(s):
    return DL.norm(s)


def load_ratings_raw(path):
    out = {}
    for r in csv.DictReader(open(path)):
        t = r.get("Team", "")
        if t:
            out[norm(t)] = r
    return out


def match_team(ratings_raw, raw_team):
    """Longest-substring match, same trick as data_load.find_opponent_tkey
    -- Odds API names carry a mascot ('TCU Horned Frogs'), team_ratings'
    own 'Team' column doesn't ('TCU')."""
    n = norm(raw_team)
    cands = [k for k in ratings_raw if k and (k in n or n in k)]
    if not cands:
        return None
    return ratings_raw[max(cands, key=len)]


def build(props_path, lines_path, ratings_path):
    ratings_raw = load_ratings_raw(ratings_path)

    lines_by_gid = {}
    for r in csv.DictReader(open(lines_path)):
        lines_by_gid[r["game_id"]] = r

    # Only games confirmed by the props pull (has a real commence_time) --
    # see module docstring on why the full lines file can't be trusted
    # week-by-week yet.
    games = {}
    for r in csv.DictReader(open(props_path)):
        games[r["game_id"]] = dict(
            home_team=r["home_team"], away_team=r["away_team"],
            commence_time=r.get("commence_time", ""),
        )

    out = []
    for gid, g in games.items():
        ln = lines_by_gid.get(gid)
        if not ln:
            continue
        rh, ra = match_team(ratings_raw, g["home_team"]), match_team(ratings_raw, g["away_team"])
        book_spread = float(ln["home_spread"])
        book_total = float(ln["total"])
        row = dict(
            game_id=gid, home_team=g["home_team"], away_team=g["away_team"],
            commence_time=g["commence_time"],
            book_spread=book_spread, book_total=book_total,
            pred_spread=None, pred_total=None,
            spread_diff=None, total_diff=None,
            home_rated=bool(rh), away_rated=bool(ra),
        )
        if rh and ra:
            sp_h, sp_a = float(rh["SP"]), float(ra["SP"])
            hfa = float(rh["HFACW"]) if rh.get("HFACW") else 0.0
            pred_spread = -(sp_h - sp_a + hfa)
            ht_total, at_total = float(rh["Team Total"]), float(ra["Team Total"])
            pred_total = ht_total + at_total
            row.update(
                pred_spread=round(pred_spread, 1), pred_total=round(pred_total, 1),
                spread_diff=round(book_spread - pred_spread, 1),
                total_diff=round(book_total - pred_total, 1),
                home_sp=sp_h, away_sp=sp_a, hfa=hfa,
                home_team_total=ht_total, away_team_total=at_total,
            )
        out.append(row)

    out.sort(key=lambda r: -(abs(r["spread_diff"] or 0) + abs(r["total_diff"] or 0)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--props", default="hist_props_live_2026wk1.csv")
    ap.add_argument("--game-lines", default="hist_lines_live_2026wk1.csv")
    ap.add_argument("--team-ratings", default="team_ratings_2025.csv")
    ap.add_argument("--week", type=int, default=1)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--out", default="diversions_2026wk1.json")
    args = ap.parse_args()

    games = build(args.props, args.game_lines, args.team_ratings)
    n_full = sum(1 for g in games if g["pred_spread"] is not None)
    payload = dict(week=args.week, season=args.season, games=games)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"Wrote {args.out}: {len(games)} confirmed week-{args.week} games, "
          f"{n_full} with both teams rated")


if __name__ == "__main__":
    main()
