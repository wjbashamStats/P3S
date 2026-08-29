#!/usr/bin/env python3
"""
build_team_averages_page_data.py — one-off: real 2025 season, per-game team
averages (offense volume/yards from player_season_totals.csv, PFF team
grades, CFBD-derived advanced rates) for the Team Averages reference page.

Unlike the Props/Impact/DFS pages, this has no "this week" dimension --
it's last year's actual production, by team, meant as a sanity-check
reference (e.g. "is an 83-yard combined rush-yards book line plausible
for a team that averaged 116.7 rush yds/game last year") rather than a
projection.

Run:  python3 build_team_averages_page_data.py --out team_averages.json
"""
import argparse, csv, json
import data_load as DL

VOL_COLS = ("pass_att", "pass_yds", "pass_td", "rush_att", "rush_yds", "rush_td",
            "targets", "receptions", "rec_yds", "rec_td")


def _to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def build(season_totals_path, team_grades_path, team_ratings_path):
    pff2c, _ = DL.load_team_map()

    # ---- offense: aggregate player_season_totals.csv by canonical team ----
    teams = {}
    for r in csv.DictReader(open(season_totals_path)):
        raw_team = r.get("team", "")
        if not raw_team:
            continue
        canon_tkey = DL.resolve_tkey(raw_team, pff2c)
        d = teams.setdefault(canon_tkey, dict(games=[], **{c: 0.0 for c in VOL_COLS}))
        for c in VOL_COLS:
            v = _to_float(r.get(c))
            if v:
                d[c] += v
        g = _to_float(r.get("games"))
        if g:
            d["games"].append(g)

    # ---- PFF team grades (record/pf/pa/grades) -- direct read for the
    # cased display name + record string, which DL.load_team_grades()
    # (built for the opponent-adjustment lookups) doesn't carry. Same
    # alias table that loader uses (9 teams whose PFF-grade-file name
    # doesn't match its canonical tkey after norm()), so lookups by
    # canon_tkey land the same way here.
    grades_raw = {}
    if team_grades_path:
        for r in csv.DictReader(open(team_grades_path)):
            t = r.get("team", "")
            if not t:
                continue
            n = DL.norm(t)
            canon_key = DL._TEAM_GRADE_ALIASES.get(n, n)
            grades_raw[canon_key] = r
    grade_cols = ["grade_over", "grade_off", "grade_pass", "grade_pblk", "grade_recv",
                 "grade_run", "grade_rblk", "grade_def", "grade_rdef", "grade_tack",
                 "grade_prsh", "grade_cov", "grade_spec"]

    # ---- CFBD-derived advanced rates + conference/mascot -- direct read
    # for the same reason (DL.load_team_ratings() only keeps a numeric
    # subset for the opponent-adjustment math). ----
    ratings_raw = {}
    if team_ratings_path:
        for r in csv.DictReader(open(team_ratings_path)):
            t = r.get("Team", "")
            if t:
                ratings_raw[DL.norm(t)] = r

    out = []
    for tkey, d in teams.items():
        games = max(d["games"]) if d["games"] else None
        if not games:
            continue
        gr = grades_raw.get(tkey, {})
        rt = ratings_raw.get(tkey, {})
        display_name = rt.get("Team") or gr.get("team") or tkey.title()

        pf, pa = _to_float(gr.get("pf")), _to_float(gr.get("pa"))
        off = dict(
            rush_att=round(d["rush_att"] / games, 1), rush_yds=round(d["rush_yds"] / games, 1),
            rush_td=round(d["rush_td"] / games, 2),
            ypc=round(d["rush_yds"] / d["rush_att"], 2) if d["rush_att"] else None,
            pass_att=round(d["pass_att"] / games, 1), pass_yds=round(d["pass_yds"] / games, 1),
            pass_td=round(d["pass_td"] / games, 2),
            ypa=round(d["pass_yds"] / d["pass_att"], 2) if d["pass_att"] else None,
            targets=round(d["targets"] / games, 1), receptions=round(d["receptions"] / games, 1),
            rec_yds=round(d["rec_yds"] / games, 1),
            catch_rate=round(d["receptions"] / d["targets"], 3) if d["targets"] else None,
        )
        grades = {c: _to_float(gr.get(c)) for c in grade_cols} if gr else None
        advanced = None
        if rt:
            advanced = {}
            for dst, col in [
                ("off_rush_rate", "Offense RushingPlays Rate"), ("off_pass_rate", "Offense PassingPlays Rate"),
                ("off_rush_sr", "Offense RushingPlays SuccessRate"), ("off_pass_sr", "Offense PassingPlays SuccessRate"),
                ("def_rush_rate", "Defense RushingPlays Rate"), ("def_pass_rate", "Defense PassingPlays Rate"),
                ("def_rush_sr", "Defense RushingPlays SuccessRate"), ("def_pass_sr", "Defense PassingPlays SuccessRate"),
                ("off_adj", "OffAdj"), ("def_adj", "DefAdj"), ("rank_tarp", "rank_TARP"),
            ]:
                v = _to_float(rt.get(col))
                advanced[dst] = round(v, 3) if v is not None else None

        out.append(dict(
            team=display_name, tkey=tkey,
            conference=rt.get("Conference.y") or rt.get("Conference.x") or None,
            mascot=rt.get("Mascot") or None,
            record=gr.get("record") or None,
            games=int(games),
            ppg=round(pf / games, 1) if pf is not None else None,
            papg=round(pa / games, 1) if pa is not None else None,
            off=off, grades=grades, advanced=advanced,
        ))

    out.sort(key=lambda t: t["team"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season-totals", default="player_season_totals.csv")
    ap.add_argument("--team-grades", default="team_pff_grades_2025.csv")
    ap.add_argument("--team-ratings", default="team_ratings_2025.csv")
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--out", default="team_averages_2025.json")
    args = ap.parse_args()

    teams = build(args.season_totals, args.team_grades, args.team_ratings)
    payload = dict(season=args.season, teams=teams)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"Wrote {args.out}: {len(teams)} teams")


if __name__ == "__main__":
    main()
