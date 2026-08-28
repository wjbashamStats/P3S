#!/usr/bin/env python3
"""
build_props_page_data.py — one-off: join projections + closing-line props
for a single week, grouped by game, for the Props comparison page.

Reuses backtest.py's projection engine (same --use-prior-year --game-lines
--team-ratings --team-grades stack validated in the week 1-15 backtest) but
also carries player position/team and game grouping, which backtest.py's
own join doesn't need for scoring but the page does for display.

Run:  python3 build_props_page_data.py --week 14 --out props_wk14.json
"""
import argparse, csv, json
import config as C
import data_load as DL
import project as P
import backtest as BT


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def build_week(week, props_path, lines_path, ratings_path, grades_path):
    pff2c, odds2c = DL.load_team_map()
    pff = DL.load_pff(pff2c)
    lines_by_week = DL.load_game_lines(lines_path)
    team_ratings = DL.load_team_ratings(ratings_path)
    team_grades = DL.load_team_grades(grades_path)

    print(f"Building week-{week} projections ...")
    projections = BT.build_projections(week, use_prior_year=True, lines_by_week=lines_by_week,
                                       team_ratings=team_ratings, team_grades=team_grades)
    print(f"  {len(projections)} (player, market) projections")

    # Team/position lookup: player_season_totals.csv has far wider roster
    # coverage than master_crosswalk.csv (the PFF grades file), since it's
    # built from every CFBD box score, not just graded PFF snaps. Prefer it;
    # fall back to the PFF crosswalk for anyone missing from season totals.
    totals_by_pkey = {}
    for r in csv.DictReader(open(C.SEASON_TOTALS)):
        totals_by_pkey.setdefault(norm(r.get("player", "")), r)

    pff_by_pkey = {}
    for p in pff:
        pff_by_pkey.setdefault(p["pkey"], p)

    def resolve_player_team_position(pkey):
        r = totals_by_pkey.get(pkey)
        if r is not None:
            tkey = DL.resolve_tkey(r.get("team", ""), pff2c)
            team_cfbd = pff2c.get(norm(r.get("team", "")), r.get("team", ""))
            return tkey, team_cfbd, (r.get("position") or "")
        p = pff_by_pkey.get(pkey)
        if p is not None:
            return p["tkey"], p["team_cfbd"], (p.get("position") or "")
        return None, "", ""

    all_props = BT.load_props(props_path)
    props = [r for r in all_props if str(r.get("week")) == str(week)]
    print(f"  {len(props)} prop rows for week {week}")

    games = {}
    for r in props:
        gid = r["game_id"]
        g = games.setdefault(gid, dict(
            game_id=gid, home_team=r["home_team"], away_team=r["away_team"],
            commence_time=r.get("commence_time", ""), players={},
            home_tkey=norm(odds2c.get(norm(r["home_team"]), r["home_team"])),
            away_tkey=norm(odds2c.get(norm(r["away_team"]), r["away_team"])),
        ))
        pkey = norm(r["player"])
        market = r["market"]
        mdef = C.MARKETS.get(market)
        if mdef is None:
            continue
        proj = projections.get((pkey, market))
        if proj is None:
            continue
        book_line = float(r["book_line"]) if r.get("book_line") not in (None, "", "NA") else None
        edge_pct = None
        if book_line not in (None, 0):
            edge_pct = round((proj["projection"] - book_line) / book_line * 100, 1)

        if r["player"] not in g["players"]:
            tkey, team_cfbd, position = resolve_player_team_position(pkey)
            if tkey == g["home_tkey"]:
                display_team = r["home_team"]
            elif tkey == g["away_tkey"]:
                display_team = r["away_team"]
            else:
                display_team = team_cfbd
            g["players"][r["player"]] = dict(
                name=r["player"], team=display_team, position=position, markets={},
            )
        player_entry = g["players"][r["player"]]
        player_entry["markets"][market] = dict(
            stat=mdef["stat"], book_line=book_line, projection=proj["projection"],
            edge_pct=edge_pct,
            over_price=(float(r["over_price"]) if r.get("over_price") not in (None, "", "NA") else None),
            under_price=(float(r["under_price"]) if r.get("under_price") not in (None, "", "NA") else None),
            n_books=r.get("n_books"),
        )

    out_games = []
    for g in games.values():
        players = sorted(g["players"].values(), key=lambda p: (p["team"], p["name"]))
        if players:
            out_games.append(dict(
                game_id=g["game_id"], home_team=g["home_team"], away_team=g["away_team"],
                commence_time=g["commence_time"], players=players,
            ))
    out_games.sort(key=lambda g: g["commence_time"])
    n_resolved = sum(1 for g in out_games for p in g["players"] if p["team"])
    n_total = sum(len(g["players"]) for g in out_games)
    print(f"  team/position resolved for {n_resolved}/{n_total} player rows")
    return out_games


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--props", default="hist_props_closing_wk1-15.csv")
    ap.add_argument("--game-lines", default="hist_lines_closing_wk1-15.csv")
    ap.add_argument("--team-ratings", default="team_ratings_2025.csv")
    ap.add_argument("--team-grades", default="team_pff_grades_2025.csv")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    games = build_week(args.week, args.props, args.game_lines, args.team_ratings, args.team_grades)
    payload = dict(week=args.week, season=2025, games=games)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1)
    n_players = sum(len(g["players"]) for g in games)
    print(f"Wrote {args.out}: {len(games)} games, {n_players} player rows")


if __name__ == "__main__":
    main()
