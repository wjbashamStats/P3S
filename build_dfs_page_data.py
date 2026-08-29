#!/usr/bin/env python3
"""
build_dfs_page_data.py — one-off: build DraftKings-style fantasy-point
projections for a single week, for the DFS tab's lineup-generator page.

Salaries are NOT included here -- DK salaries are per-slate and change
week to week, and we don't have a live feed for them. The page itself
takes a pasted/uploaded DK salary export client-side and joins it to the
projections embedded here by normalized player name.

Fantasy scoring (DraftKings Classic CFB, confirmed from the user's own
contest rules screenshot):
  Passing yards      0.04 pt/yd   (1 pt / 25 yds)
  Passing TD         4 pts
  Rushing yards       0.1 pt/yd   (1 pt / 10 yds)
  Rushing TD          6 pts
  Receiving yards     0.1 pt/yd   (1 pt / 10 yds)
  Receiving TD        6 pts
  Reception            0.5 pt     (half-PPR)
Not modeled (assumed 0 -- too rare/noisy to project from season rates):
  interceptions (-1), fumbles lost (-2), 2-point conversions (2),
  kick/punt-return TDs (6). A players' true DK score can exceed this
  page's projection on a pick-six or a punt-return house call; those are
  real but unpredictable, not a hole in the yardage/TD math below.

Expected TDs come from project.TD_COL_BY_VOL's per-market rate (see
backtest.build_projections) -- pass_td/pass_att applied to the model's own
(already game-context-adjusted) projected attempts, etc. Same philosophy
as the rest of this project: transparent arithmetic, no fitted regression.

Run:  python3 build_dfs_page_data.py --week 14 --out dfs_wk14.json
"""
import argparse, csv, json
import config as C
import data_load as DL
import project as P
import backtest as BT

SKILL_POSITIONS = {"QB", "HB", "WR", "TE", "FB"}
DK_SLOT = {"QB": "QB", "HB": "RB", "FB": "RB", "WR": "WR", "TE": "TE"}

# DK Classic CFB scoring -- see module docstring.
DK_SCORING = dict(
    pass_yds=0.04, pass_td=4, rush_yds=0.1, rush_td=6,
    rec_yds=0.1, rec_td=6, reception=0.5,
)

MIN_VOLUME = dict(pass_att=15, rush_att=8, targets=5)


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def dk_points(pass_yds, pass_td, rush_yds, rush_td, rec_yds, rec_td, receptions):
    return round(
        (pass_yds or 0) * DK_SCORING["pass_yds"] + (pass_td or 0) * DK_SCORING["pass_td"]
        + (rush_yds or 0) * DK_SCORING["rush_yds"] + (rush_td or 0) * DK_SCORING["rush_td"]
        + (rec_yds or 0) * DK_SCORING["rec_yds"] + (rec_td or 0) * DK_SCORING["rec_td"]
        + (receptions or 0) * DK_SCORING["reception"], 2)


def build(week, lines_path, ratings_path, grades_path, season=2025):
    pff2c, _ = DL.load_team_map()
    lines_by_week = DL.load_game_lines(lines_path)
    team_ratings = DL.load_team_ratings(ratings_path)
    team_grades = DL.load_team_grades(grades_path)

    print(f"Building week-{week} DK projections (season {season}) ...")
    projections = BT.build_projections(week, use_prior_year=True, lines_by_week=lines_by_week,
                                       team_ratings=team_ratings, team_grades=team_grades, season=season)

    # Team/position context, same source + fixes as the Impact page
    # (player_season_totals.csv has far wider coverage than the PFF
    # crosswalk; see build_impact_page_data.py's history on this).
    totals_by_pkey = {}
    for r in csv.DictReader(open(C.SEASON_TOTALS)):
        totals_by_pkey.setdefault(norm(r.get("player", "")), r)

    # Matchup context straight from the full game-lines file (66 games),
    # NOT from the props join (only 41 games have a posted prop) -- a DFS
    # pool needs every playable team's opponent, not just the subset with
    # a book market. Kickoff time isn't in hist_lines_closing_*.csv, so
    # this omits it (props_wk*.json has it for the props/impact pages).
    wk_lines = lines_by_week.get(str(week), [])

    def matchup_for_tkey(tkey):
        for g in wk_lines:
            h, a = DL.norm(g["home_team"]), DL.norm(g["away_team"])
            if tkey in h or h in tkey:
                return f"{g['away_team']} @ {g['home_team']}"
            if tkey in a or a in tkey:
                return f"{g['away_team']} @ {g['home_team']}"
        return ""

    matchup_cache = {}

    players = []
    seen = set()
    for (pkey, market), proj in projections.items():
        r = totals_by_pkey.get(pkey)
        if not r or r.get("position") not in SKILL_POSITIONS:
            continue
        if pkey in seen:
            continue
        seen.add(pkey)
        position = r.get("position")

        def mkt(name):
            return projections.get((pkey, name))

        pass_m = mkt("player_pass_yds")
        rush_m = mkt("player_rush_yds")
        rec_m = mkt("player_receptions")
        recy_m = mkt("player_reception_yds")

        pass_att_m = mkt("player_pass_attempts")
        if not any([pass_m, rush_m, rec_m, recy_m]):
            continue
        pass_att = (pass_att_m or pass_m or {}).get("components", {}).get("volume") if (pass_att_m or pass_m) else None
        rush_att_m = mkt("player_rush_attempts")
        rush_att = (rush_att_m or rush_m or {}).get("components", {}).get("volume") if (rush_att_m or rush_m) else None

        if (pass_att or 0) < MIN_VOLUME["pass_att"] and (rush_att or 0) < MIN_VOLUME["rush_att"] \
                and ((rec_m or {}).get("components", {}).get("volume") or 0) < MIN_VOLUME["targets"]:
            continue

        pass_yds = pass_m["projection"] if pass_m else 0
        pass_td = pass_m["expected_td"] if pass_m else 0
        rush_yds = rush_m["projection"] if rush_m else 0
        rush_td = rush_m["expected_td"] if rush_m else 0
        rec_yds = recy_m["projection"] if recy_m else 0
        rec_td = rec_m["expected_td"] if rec_m else (recy_m["expected_td"] if recy_m else 0)
        receptions = rec_m["projection"] if rec_m else 0

        fp = dk_points(pass_yds, pass_td, rush_yds, rush_td, rec_yds, rec_td, receptions)
        if fp <= 0:
            continue

        raw_name = r.get("player") or pkey
        canon_tkey = DL.resolve_tkey(r.get("team", ""), pff2c)
        team_c = pff2c.get(norm(r.get("team", "")), r.get("team", ""))
        if canon_tkey not in matchup_cache:
            matchup_cache[canon_tkey] = matchup_for_tkey(canon_tkey)

        any_mkt = pass_m or rush_m or rec_m or recy_m
        bd = any_mkt.get("breakdown", {}) if any_mkt else {}

        players.append(dict(
            name=raw_name,
            team=team_c,
            position=position,
            dk_slot=DK_SLOT.get(position, "FLEX"),
            matchup=matchup_cache[canon_tkey],
            opponent=bd.get("opponent"),
            team_implied=bd.get("team_implied"),
            team_spread=bd.get("team_spread"),
            proj_fp=fp,
            proj=dict(
                pass_yds=round(pass_yds, 1) if pass_m else None,
                pass_td=round(pass_td, 2) if pass_m else None,
                rush_yds=round(rush_yds, 1) if rush_m else None,
                rush_td=round(rush_td, 2) if rush_m else None,
                rec_yds=round(rec_yds, 1) if recy_m else None,
                rec_td=round(rec_td, 2) if (rec_m or recy_m) else None,
                receptions=round(receptions, 1) if rec_m else None,
            ),
        ))

    players.sort(key=lambda p: -p["proj_fp"])
    return players


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=14)
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--game-lines", default="hist_lines_closing_wk1-15.csv")
    ap.add_argument("--team-ratings", default="team_ratings_2025.csv")
    ap.add_argument("--team-grades", default="team_pff_grades_2025.csv")
    ap.add_argument("--out", default="dfs_wk14.json")
    args = ap.parse_args()

    players = build(args.week, args.game_lines, args.team_ratings, args.team_grades, season=args.season)
    payload = dict(season=args.season, week=args.week, scoring=DK_SCORING, players=players)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"Wrote {args.out}: {len(players)} players with a DK projection")


if __name__ == "__main__":
    main()
