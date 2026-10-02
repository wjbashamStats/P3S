#!/usr/bin/env python3
"""Run the eight prop screens against a week's committed props file. From the repo root:

    python3 articles/build/screen_props.py --week 5

Prints the survivor list. The card is picked from this, so a card pick that is not
on this list is either a bug or a disclosed exception.

The screens, in the order they were added:
  1. model edge >= 20%
  2. the player's own 2026 production agrees with the side by >= 20%
  3. a real role: 12+ carries A GAME for backs, 20+ targets on the season for receivers
  4. 4+ targets a game for any receiving Over
  5. pace/script multiplier inside 0.6 to 1.6
  6. |spread| < 28 and both teams rated
  7. at least two books posting the number
  8. availability: the player's game count is level with his own team's maximum

Quarterback rushing props are dropped before any of that. PFF excludes sack yardage
from rushing and official college stats charge it to the quarterback, so the model is
projecting a stat the book is not pricing (PROJECT_STATE, and confirmed every week:
week 5 mean edge +53.6% for QBs against +3.0% for backs).
"""
import argparse, collections, csv, datetime, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--show-near-misses", action="store_true",
                    help="also list rows that fail exactly one screen")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    P = json.load(open(os.path.join(ROOT, f"props_{args.season}wk{args.week}.json")))["games"]
    DIV = {(g["away_team"], g["home_team"]): g
           for g in json.load(open(os.path.join(ROOT, f"diversions_{args.season}wk{args.week}.json")))["games"]}
    rush, recv = {}, {}
    for r in csv.DictReader(open(os.path.join(ROOT, f"{args.season}_rushing_season_ranked.csv"))):
        rush[r["player"]] = r
    for r in csv.DictReader(open(os.path.join(ROOT, f"{args.season}_receiving_season_ranked.csv"))):
        recv[r["player"]] = r
    team_games = collections.defaultdict(int)
    for src in (rush, recv):
        for r in src.values():
            team_games[r["team_name"]] = max(team_games[r["team_name"]], int(r["player_game_count"]))

    tz = datetime.timezone(datetime.timedelta(hours=-4))
    rows = []
    for g in P:
        t = datetime.datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00")).astimezone(tz)
        d = DIV.get((g["away_team"], g["home_team"]))
        for p in g["players"]:
            for m in p["markets"].values():
                stat = m["stat"]
                if stat not in ("rush_yds", "rec_yds"):
                    continue
                if stat == "rush_yds" and p["position"] == "QB":
                    continue
                src = rush.get(p["name"]) if stat == "rush_yds" else recv.get(p["name"])
                if not src:
                    continue
                gp = int(src["player_game_count"])
                ypg = float(src["yards"]) / gp
                line, e, bd = m["book_line"], m["edge_pct"], m["breakdown"]
                vol = float(src["attempts"]) if stat == "rush_yds" else float(src["targets"])
                prod_edge = (ypg - line) / line * 100.0
                fails = []
                if abs(e) < 20: fails.append("edge")
                if (e > 0) != (prod_edge > 0) or abs(prod_edge) < 20: fails.append("production")
                if stat == "rush_yds" and vol / gp < 12: fails.append("role")
                if stat == "rec_yds" and vol < 20: fails.append("role")
                if stat == "rec_yds" and e > 0 and vol / gp < 4: fails.append("targets/gm")
                if not (0.6 <= bd["pace_script_adj"] <= 1.6): fails.append("multiplier")
                if d is None or not (d["home_rated"] and d["away_rated"]): fails.append("unrated")
                elif abs(d["book_spread"]) >= 28: fails.append("spread")
                if int(m["n_books"]) < 2: fails.append("books")
                if gp < team_games[src["team_name"]]:
                    fails.append(f"avail {gp}<{team_games[src['team_name']]}")
                if t.weekday() != 5: fails.append("not Saturday")
                rows.append(dict(name=p["name"], pos=p["position"], team=src["team_name"], stat=stat,
                                 line=line, proj=m["projection"], edge=e, ypg=round(ypg, 1),
                                 prod_edge=round(prod_edge, 1), vol=vol, gp=gp,
                                 game=f"{g['away_team']} @ {g['home_team']}", fails=fails))

    surv = [r for r in rows if not r["fails"]]
    print(f"{len(rows)} candidate rows (QB rushing already dropped) -> {len(surv)} survive all eight screens\n")
    for r in sorted(surv, key=lambda r: -abs(r["edge"])):
        side = "Over" if r["edge"] > 0 else "Under"
        print(f"{abs(r['edge']):5.1f}% {side:<5} {r['name']:<22}{r['pos']:>3} {r['stat']:<8} "
              f"line{r['line']:6.1f} proj{r['proj']:6.1f} own{r['ypg']:6.1f}/gm "
              f"prod{r['prod_edge']:+6.1f}% vol{r['vol']:5.0f} | {r['game']}")
    if args.show_near_misses:
        print("\n--- fails exactly one screen ---")
        for r in sorted((r for r in rows if len(r["fails"]) == 1), key=lambda r: -abs(r["edge"]))[:25]:
            print(f"{r['edge']:+6.1f}% {r['name']:<22}{r['stat']:<9} line{r['line']:6.1f} "
                  f"own{r['ypg']:6.1f}/gm  fails: {r['fails'][0]}")
    if args.json_out:
        json.dump(surv, open(args.json_out, "w"), indent=1)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
