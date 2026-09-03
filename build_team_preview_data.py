#!/usr/bin/env python3
"""
build_team_preview_data.py -- ports the "Team Preview Dashboard" R Shiny
app (user-supplied app.R) to a static data JSON for an HTML page with the
same look. The R app read a live Google Sheet; this project already has
the SAME data baked into team_ratings_2025.csv (HC/OC/DC bios, scheme
notes, RPOffense/RPDefense, Win Total, Note1-4, HCRecSU/ATS, X2022_WL/ATS
_Percent, Mascot, logo, Conference.y) -- no new data pull needed, this is
a straight re-projection of columns already loaded elsewhere in this
project (same rank_ / grade_ conventions as build_diversions_page_data.py
and data_load.py).

Two sections of the R app could NOT be ported with real data and are
intentionally reshaped rather than faked:
  - "SCHEDULE" (full-season game-by-game with bye/hangover notes) needs a
    complete season's worth of weekly spreads -- this project only has
    ONE week of live lines (hist_lines_live_2026wk1.csv). Reshaped into a
    single "Week 1" matchup card instead of a season list.
  - "FUTURES / CONF WIN TOTALS" -- team_ratings_2025.csv DOES have Win
    Total / TAN_WIN / SP._WIN and Conference.y for every team, so this
    one ports with real data, just grouped fresh here rather than pulled
    from a separate futures sheet.
No logos: same sandbox constraint as every other page in this project
(hotlinked external images are blocked) -- initials badges stand in,
same as build_diversions_page_data.py's team_colors-lite approach.

Run:  python3 build_team_preview_data.py --out team_preview_2026.json
"""
import argparse, csv, json
import data_load as DL


def norm(s):
    return DL.norm(s)


def _f(x, default=0.0):
    try:
        v = float(x)
        if v != v:  # NaN
            return default
        return v
    except (TypeError, ValueError):
        return default


def _s(x):
    x = (x or "").strip()
    return x if x else None


FIVE_FACTOR_COLS = [
    ("success_rate", "Success Rate", "Offense SuccessRate", "rank_Offense_successRate",
     "Defense SuccessRate", "rank_defense_successRate", 1),
    ("explosiveness", "Explosiveness", "Offense Explosiveness", "rank_Offense_explosiveness",
     "Defense Explosiveness", "rank_defense_explosiveness", 2),
    ("points_per_opportunity", "Pts Per Opp.", "Offense PointsPerOpportunity", "rank_Offense_pointsPerOpportunity",
     "Defense PointsPerOpportunity", "rank_defense_pointsPerOpportunity", 1),
    ("havoc", "Havoc", "Offense Havoc Total", "rank_Offense_havoc_total",
     "Defense Havoc Total", "rank_defense_havoc_total", 3),
    ("field_position", "Avg Field Pos", "Offense FieldPosition AverageStart", "rank_Offense_fieldPosition_averageStart",
     "Defense FieldPosition AverageStart", "rank_defense_fieldPosition_averageStart", 1),
]


def five_factors_rows(r):
    rows = []
    for key, label, off_col, off_rank_col, def_col, def_rank_col, digits in FIVE_FACTOR_COLS:
        off_val = _f(r.get(off_col), None)
        def_val = _f(r.get(def_col), None)
        if key == "field_position":
            # R app's own transform: raw CFBD value is "yards to go" from
            # the opponent's end zone -- 100-minus turns it into the more
            # readable "started around your own NN" yard-line framing.
            if off_val is not None:
                off_val = round(100 - off_val, 1)
            if def_val is not None:
                def_val = round(100 - def_val, 1)
        else:
            off_val = round(off_val, digits) if off_val is not None else None
            def_val = round(def_val, digits) if def_val is not None else None
        rows.append(dict(
            key=key, label=label,
            off=off_val, off_rank=_f(r.get(off_rank_col), None),
            def_=def_val, def_rank=_f(r.get(def_rank_col), None),
        ))
    return rows


def load_week1_by_team(diversions_path):
    """team_ratings' own 'Team' string (home_display/away_display, set
    by build_diversions_page_data.py from the SAME file) -> that team's
    week-1 game, from THIS team's own perspective (spread/total sign
    flipped for the away side, same convention as every other page)."""
    out = {}
    try:
        games = json.load(open(diversions_path))["games"]
    except FileNotFoundError:
        return out
    for g in games:
        if g.get("pred_spread") is None and not g.get("home_display"):
            continue
        for side, team_key, opp_key, opp_full in (
            ("home", "home_display", "away_display", "away_team"),
            ("away", "away_display", "home_display", "home_team"),
        ):
            team = g.get(team_key)
            if not team:
                continue
            is_home = side == "home"
            spread = g["book_spread"] if is_home else (-g["book_spread"] if g["book_spread"] is not None else None)
            pred = g["pred_spread"] if is_home else (-g["pred_spread"] if g["pred_spread"] is not None else None)
            out[team] = dict(
                opponent=g.get(opp_key) or g[opp_full],
                is_home=is_home,
                spread=spread, pred_spread=pred,
                total=g["book_total"], pred_total=g.get("pred_total"),
                kickoff=g["commence_time"],
            )
    return out


def build(team_ratings_path, diversions_path):
    week1_by_team = load_week1_by_team(diversions_path)
    rows = list(csv.DictReader(open(team_ratings_path)))

    teams = []
    conf_totals = {}
    for r in rows:
        team = r.get("Team", "").strip()
        if not team:
            continue
        conf = _s(r.get("Conference.y")) or _s(r.get("Conference.x")) or "Independent"
        win_total = _f(r.get("Win Total"), None)
        entry = dict(
            team=team, mascot=_s(r.get("Mascot")) or "", conference=conf,
            win_total=win_total,
            tan_win=_f(r.get("TAN_WIN"), None), sp_win=_f(r.get("SP._WIN"), None),
            tan_conf=_f(r.get("TAN_CONF"), None),
            hc=_s(r.get("HC")), hc_rec_su=_s(r.get("HCRecSU")), hc_rec_ats=_s(r.get("HCRecATS")),
            oc=_s(r.get("OC")), oc_scheme=_s(r.get("OCScheme")), oc_notes=_s(r.get("OCNotes")),
            dc=_s(r.get("DC")), dc_scheme=_s(r.get("DCScheme")), dc_notes=_s(r.get("DCNotes")),
            rp_offense=_f(r.get("RPOffense"), None), rp_defense=_f(r.get("RPDefense"), None),
            tarp_rank=_f(r.get("rank_TARP"), None), off_adj_rank=_f(r.get("rank_OffAdj"), None),
            def_adj_rank=_f(r.get("rank_DefAdj"), None),
            five_factors=five_factors_rows(r),
            spp=_f(r.get("SPP"), None), spp_rank=_f(r.get("rank_SPP"), None),
            notes=[n for n in (_s(r.get(f"Note{i}")) for i in range(1, 5)) if n],
            wl_pct=_f(r.get("X2022_WL_Percent"), None), ats_pct=_f(r.get("X2022_ATS_Percent"), None),
            week1=week1_by_team.get(team),
        )
        teams.append(entry)
        if win_total is not None:
            conf_totals.setdefault(conf, []).append(dict(
                team=team, win_total=win_total,
                tan_win=entry["tan_win"], sp_win=entry["sp_win"],
            ))

    for conf in conf_totals:
        conf_totals[conf].sort(key=lambda t: -t["win_total"])

    teams.sort(key=lambda t: t["team"])
    return dict(teams=teams, conferences=conf_totals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--team-ratings", default="team_ratings_2025.csv")
    ap.add_argument("--diversions", default="diversions_2026wk1.json")
    ap.add_argument("--out", default="team_preview_2026.json")
    args = ap.parse_args()

    payload = build(args.team_ratings, args.diversions)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1)
    n_week1 = sum(1 for t in payload["teams"] if t["week1"])
    print(f"Wrote {args.out}: {len(payload['teams'])} teams, {len(payload['conferences'])} conferences, "
          f"{n_week1} with a week-1 game matched")


if __name__ == "__main__":
    main()
