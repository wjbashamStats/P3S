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

Each game also gets a plain-language REASON for its biggest diffs, built
from the same underlying components already computed (never a separate
guess): SP+ gap direction/size, home-field edge, and -- because SP+ alone
is backward-looking (2025 season only) -- whether the 2026-forward
OffAdj/DefAdj (coaching change + returning production, team_ratings'
own continuity metric) points the SAME or OPPOSITE direction, which is
often exactly why a spread and a power rating disagree (a team lost a
lot of production, or gained a good portion back, in a way the prior
season's box scores don't reflect). Total reasons cite whichever side's
pass/rush rate + success rate is driving the total, plus tempo.

"How we got here" detail, added for the matchup-preview modal:
  - five_factors: rank_Offense_*/rank_defense_* (Success Rate, Explosive-
    ness, Havoc, Finishing Drives i.e. PointsPerOpportunity, plus
    rank_TARP as a 5th axis) for both sides of both teams -- these feed
    two radar comparisons per game (each team's offense vs the
    opponent's defense), same "1 = best" rank convention as every other
    rank_ column in team_ratings.csv.
  - power_table: TAN/SP/NetRP/2022 ATS%/2022 Over%/pace, each with a
    rank. NetRP has no native rank column in the source file, so one is
    computed here the same way (sort all 136 teams descending, rank
    1..136) -- see rank_by_value().
  - qb: each team's depth-chart-confirmed starter (depth_rank==1),
    joined to their PFF grade (master_crosswalk.csv) and real 2025
    season stats (player_season_totals.csv) by name -- same name-only
    join pattern used throughout this project (data_load.load_pff's
    pkey), since PFF's team strings don't reliably match a QB's CURRENT
    team for a transfer. None if the depth chart has no confirmed QB1
    for a team, or the name doesn't resolve to a PFF/season-totals row
    (true freshman with no 2025 college record).

No team logos: the artifact sandbox's CSP blocks hotlinked external
images (ESPN's logo CDN included), and this environment has no internet
access to download and embed them as data URIs -- so the page uses text
badges instead, not real logos.

DATA CAVEAT, now fixed but worth remembering: hist_lines_live_*.csv used
to carry no per-row date, so a team could appear twice (its week-1 AND
week-2 game) with no way to tell which was which -- pull_live_week.py was
patched to stamp commence_time on every line (not just props), and this
script now filters directly on that date range instead of the old
props-file cross-reference (which only covered the 8 games with a posted
prop). Default window is Sept 2-7, 2026 (Wed-Mon) -- the actual week-1
slate; pass --date-start/--date-end to point at a different week.

Run:  python3 build_diversions_page_data.py --out diversions_2026wk1.json
"""
import argparse, csv, json
import data_load as DL


def norm(s):
    return DL.norm(s)


# Odds API's own naming quirk for this one team ("Miami (OH)" vs our
# "Miami Ohio") -- found while building this; every other FBS team's
# Team+Mascot concatenation matched the Odds API string exactly.
ODDS_NAME_ALIASES = {"miamiohredhawks": "miamiohioredhawks"}

FIVE_FACTOR_RANK_COLS = [
    ("success_rate", "Success Rate", "rank_Offense_successRate", "rank_defense_successRate"),
    ("explosiveness", "Explosiveness", "rank_Offense_explosiveness", "rank_defense_explosiveness"),
    ("havoc", "Havoc", "rank_Offense_havoc_total", "rank_defense_havoc_total"),
    ("finishing_drives", "Finishing Drives", "rank_Offense_pointsPerOpportunity", "rank_defense_pointsPerOpportunity"),
    ("tarp", "TARP", "rank_TARP", "rank_TARP"),  # TARP isn't split off/def -- same team-wide rank both sides
]


def load_ratings_raw(path):
    """EXACT match only (norm(Team+Mascot) -> row), not substring.
    Substring matching was tried first and is unsafe here: "North
    Carolina A&T Aggies" (FCS -- correctly NOT in this file) contains
    "North Carolina" (IS in this file) as a genuine literal substring,
    so a substring match confidently returned the WRONG team and
    produced a nonsense 55-point "diversion" that was really just a
    data bug. team_ratings.csv's own Mascot column lets Team+Mascot be
    compared for an exact match against the Odds API's "Team Mascot"
    naming instead -- ~70% of Week 1's slate matches this way (the
    other ~30% are genuine FCS buy games, correctly left unrated rather
    than than guessed at)."""
    out = {}
    for r in csv.DictReader(open(path)):
        team, mascot = r.get("Team", ""), r.get("Mascot", "")
        if team and mascot:
            out[norm(team + mascot)] = r
    return out


def match_team(ratings_raw, raw_team):
    n = ODDS_NAME_ALIASES.get(norm(raw_team), norm(raw_team))
    return ratings_raw.get(n)


def match_team_avg(team_avg, raw_team):
    """team_avg is keyed by canonical display name (no mascot) -- rebuild
    the same exact Team+Mascot lookup from it via each entry's own
    'mascot' field, same safety rationale as match_team above."""
    n = ODDS_NAME_ALIASES.get(norm(raw_team), norm(raw_team))
    for t in team_avg.values():
        if t.get("mascot") and norm(t["team"] + t["mascot"]) == n:
            return t
    return None


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def rank_by_value(ratings_raw, field, reverse=True):
    """Compute a 1..N rank across all rows on a field with no native
    rank_ column in the source file (NetRP) -- same 'sort descending,
    rank 1..N' convention the file's own rank_SP/rank_TAN presumably used."""
    items = sorted(ratings_raw.items(), key=lambda kv: _f(kv[1].get(field)), reverse=reverse)
    return {k: i + 1 for i, (k, _) in enumerate(items)}


def five_factors(rh, ra):
    home_off, home_def, away_off, away_def = {}, {}, {}, {}
    for key, label, off_col, def_col in FIVE_FACTOR_RANK_COLS:
        home_off[key] = _f(rh.get(off_col), None)
        home_def[key] = _f(rh.get(def_col), None)
        away_off[key] = _f(ra.get(off_col), None)
        away_def[key] = _f(ra.get(def_col), None)
    return dict(home_off=home_off, home_def=home_def, away_off=away_off, away_def=away_def)


def power_table_entry(r, net_rp_rank):
    return dict(
        tan=_f(r.get("TAN")), tan_rank=_f(r.get("rank_TAN"), None),
        sp=_f(r.get("SP")), sp_rank=_f(r.get("rank_SP"), None),
        net_rp=_f(r.get("NetRP")), net_rp_rank=net_rp_rank,
        ats_pct=_f(r.get("X2022_ATS_Percent"), None), ats_rank=_f(r.get("Rank_2022_ATS_Percent"), None),
        over_pct=_f(r.get("X2022_OU_Percent"), None), over_rank=_f(r.get("Rank_2022_OU_Percent"), None),
        seconds_per_play=_f(r.get("Tempo")), tempo_rank=_f(r.get("rank_Tempo"), None),
    )


# Position groups shown per game, beyond the team-wide comparison.
# bucket: this project's own _DEPTH_POS_MAP code (see data_load.py).
# primary_stat: the season-totals column used to pick "the" starter when
# ourlads lists more than one depth_rank==1 at a bucket (WR-X, WR-Z, and
# WR-SL are each their own slot with their own #1) -- highest real 2025
# production wins, not slot order.
POSITION_GROUPS = [
    dict(key="qb", label="QB", bucket="QB", primary_stat="pass_yds", pff_col="off_grade_pass"),
    dict(key="rb", label="RB", bucket="HB", primary_stat="rush_yds", pff_col="off_grade_run"),
    dict(key="wr", label="WR", bucket="WR", primary_stat="rec_yds", pff_col="off_grade_recv"),
    dict(key="te", label="TE", bucket="TE", primary_stat="rec_yds", pff_col="off_grade_recv"),
]


def load_depth_rows_by_team(depth_chart_path):
    """team display name (ourlads' own, WITH mascot) -> list of offense
    rows -- raw, not aggregated, since a position bucket can have more
    than one legitimate depth_rank==1 (separate WR-X/WR-Z/WR-SL slots)."""
    from collections import defaultdict
    out = defaultdict(list)
    for r in csv.DictReader(open(depth_chart_path)):
        if r.get("side") != "offense":
            continue
        bucket = DL._DEPTH_POS_MAP.get((r.get("position") or "").strip())
        if not bucket:
            continue
        try:
            rank = int(r.get("depth_rank"))
        except (TypeError, ValueError):
            continue
        out[r["team"]].append(dict(bucket=bucket, depth_rank=rank, name=r.get("name", "")))
    return out


def build_position_player(depth_rows_by_team, team_display, group, pff_by_pkey, season_by_pkey):
    """Best depth_rank==1 candidate at group['bucket'] for this team, by
    real 2025 production (see POSITION_GROUPS docstring), joined to PFF
    grade + season stats by name."""
    candidates = []
    for depth_team, rows in depth_rows_by_team.items():
        n, td = norm(depth_team), norm(team_display)
        if not (td in n or n in td):
            continue
        for row in rows:
            if row["bucket"] == group["bucket"] and row["depth_rank"] == 1:
                candidates.append(row["name"])
    if not candidates:
        return None
    def volume(name):
        s = season_by_pkey.get(norm(name))
        return _f(s.get(group["primary_stat"]), 0) if s else 0
    name = max(candidates, key=volume)
    pkey = norm(name)
    pff = pff_by_pkey.get(pkey)
    season = season_by_pkey.get(pkey)
    return dict(
        name=name,
        pff_off_grade=_f(pff.get("off_grade_off"), None) if pff else None,
        pff_group_grade=_f(pff.get(group["pff_col"]), None) if pff else None,
        pass_att=_f(season.get("pass_att"), None) if season else None,
        pass_yds=_f(season.get("pass_yds"), None) if season else None,
        pass_td=_f(season.get("pass_td"), None) if season else None,
        rush_att=_f(season.get("rush_att"), None) if season else None,
        rush_yds=_f(season.get("rush_yds"), None) if season else None,
        rush_td=_f(season.get("rush_td"), None) if season else None,
        targets=_f(season.get("targets"), None) if season else None,
        receptions=_f(season.get("receptions"), None) if season else None,
        rec_yds=_f(season.get("rec_yds"), None) if season else None,
        rec_td=_f(season.get("rec_td"), None) if season else None,
        games=_f(season.get("games"), None) if season else None,
    ) if pff or season else dict(
        name=name, pff_off_grade=None, pff_group_grade=None, pass_att=None, pass_yds=None,
        pass_td=None, rush_att=None, rush_yds=None, rush_td=None, targets=None, receptions=None,
        rec_yds=None, rec_td=None, games=None,
    )


def match_team_grades(grades_by_team, team_display):
    n = norm(team_display)
    return grades_by_team.get(n)


def spread_reason(home_team, away_team, book_spread, pred_spread, spread_diff,
                   home_sp, away_sp, hfa, home_adj, away_adj):
    """home_adj/away_adj: (off_adj, def_adj, rank_tarp) 2026-forward continuity, or None."""
    lean_team, lean_amt = (home_team, -spread_diff) if spread_diff < 0 else (away_team, spread_diff)
    parts = []
    if abs(spread_diff) < 1.5:
        parts.append(f"Book and SP+ are basically in agreement here ({abs(spread_diff):.1f} pt gap) -- "
                      f"SP+ has {home_team} {'+' if home_sp>=away_sp else ''}{(home_sp-away_sp):.1f} over "
                      f"{away_team} before the {hfa:.1f}-pt home edge.")
    else:
        parts.append(f"The book leans {lean_amt:.1f} pts more toward {lean_team} than SP+ + "
                     f"home-field alone would put them (SP+ gap {home_sp - away_sp:+.1f} for {home_team}, "
                     f"+{hfa:.1f} home edge).")
    if home_adj and away_adj:
        fwd_diff = (home_adj[0] - away_adj[1]) - (away_adj[0] - home_adj[1])
        sp_diff = home_sp - away_sp
        if (fwd_diff > 0) != (sp_diff > 0) and abs(fwd_diff) > 1:
            favored_fwd = home_team if fwd_diff > 0 else away_team
            parts.append(f"Worth noting: the 2026-forward continuity metric (coaching change + returning "
                        f"production) actually favors {favored_fwd} more than 2025 SP+ alone does -- "
                        f"rank_TARP {home_adj[2]:.0f} ({home_team}) vs {away_adj[2]:.0f} ({away_team}). "
                        f"Could explain some of the book's lean if the market is pricing in personnel "
                        f"changes SP+'s season-long number can't see yet.")
    return " ".join(parts)


def total_reason(home_team, away_team, book_total, pred_total, total_diff,
                  home_avg, away_avg):
    direction = "higher-scoring" if total_diff > 0 else "lower-scoring"
    parts = [f"Book expects a {direction} game than the team-total sum by {abs(total_diff):.1f} pts."]
    if home_avg and away_avg:
        ha, aa = home_avg.get("advanced") or {}, away_avg.get("advanced") or {}
        notes = []
        for team, adv in ((home_team, ha), (away_team, aa)):
            pass_rate, pass_sr = adv.get("off_pass_rate"), adv.get("off_pass_sr")
            if pass_rate is not None and pass_sr is not None and pass_rate > 0.55 and pass_sr > 0.42:
                notes.append(f"{team} is both pass-heavy ({pass_rate*100:.0f}% of plays) and efficient "
                            f"at it ({pass_sr*100:.0f}% success rate)")
        if notes:
            parts.append(" / ".join(notes) + " -- that combination pushes real scoring above a flat "
                        "team-average baseline more than the naive sum accounts for.")
    return " ".join(parts)


def build(lines_path, ratings_path, team_averages_path, depth_chart_path,
          pff_crosswalk_path, season_totals_path, team_grades_path, team_map_path, date_start, date_end):
    ratings_raw = load_ratings_raw(ratings_path)
    team_avg = {t["team"]: t for t in json.load(open(team_averages_path))["teams"]}
    net_rp_rank = rank_by_value(ratings_raw, "NetRP")

    depth_rows_by_team = load_depth_rows_by_team(depth_chart_path)
    grades_by_team = DL.load_team_grades(team_grades_path)
    pff2c, _ = DL.load_team_map()
    pff_rows = DL.load_pff(pff2c)
    pff_by_pkey = {}
    for p in pff_rows:
        pff_by_pkey.setdefault(p["pkey"], p)
    season_by_pkey = {}
    for r in csv.DictReader(open(season_totals_path)):
        season_by_pkey[norm(r.get("player", ""))] = r

    out = []
    for r in csv.DictReader(open(lines_path)):
        ct = r.get("commence_time", "")
        if not (date_start <= ct[:10] <= date_end):
            continue
        home_team, away_team = r["home_team"], r["away_team"]
        rh, ra = match_team(ratings_raw, home_team), match_team(ratings_raw, away_team)
        book_spread, book_total = _f(r["home_spread"]), _f(r["total"])
        row = dict(
            game_id=r["game_id"], home_team=home_team, away_team=away_team,
            commence_time=ct,
            book_spread=book_spread, book_total=book_total,
            pred_spread=None, pred_total=None,
            spread_diff=None, total_diff=None,
            home_rated=bool(rh), away_rated=bool(ra),
            spread_reason=None, total_reason=None,
        )
        if rh and ra:
            sp_h, sp_a = _f(rh["SP"]), _f(ra["SP"])
            hfa = _f(rh.get("HFACW"))
            pred_spread = -(sp_h - sp_a + hfa)
            ht_total, at_total = _f(rh["Team Total"]), _f(ra["Team Total"])
            pred_total = ht_total + at_total
            spread_diff = round(book_spread - pred_spread, 1)
            total_diff = round(book_total - pred_total, 1)
            home_adj = (_f(rh.get("OffAdj")), _f(rh.get("DefAdj")), _f(rh.get("rank_TARP")))
            away_adj = (_f(ra.get("OffAdj")), _f(ra.get("DefAdj")), _f(ra.get("rank_TARP")))
            home_avg, away_avg = match_team_avg(team_avg, home_team), match_team_avg(team_avg, away_team)
            # NetRP rank was keyed off ratings_raw's own norm(Team+Mascot) --
            # rebuild the SAME key from rh/ra's own fields, not by
            # re-concatenating the raw Odds API string (which already has
            # the mascot in it, so re-appending it again never matches).
            home_key = norm(rh.get("Team", "") + rh.get("Mascot", ""))
            away_key = norm(ra.get("Team", "") + ra.get("Mascot", ""))
            row.update(
                pred_spread=round(pred_spread, 1), pred_total=round(pred_total, 1),
                spread_diff=spread_diff, total_diff=total_diff,
                home_sp=sp_h, away_sp=sp_a, hfa=hfa,
                home_team_total=ht_total, away_team_total=at_total,
                home_off_adj=home_adj[0], home_def_adj=home_adj[1], home_rank_tarp=home_adj[2],
                away_off_adj=away_adj[0], away_def_adj=away_adj[1], away_rank_tarp=away_adj[2],
                spread_reason=spread_reason(home_team, away_team, book_spread, pred_spread, spread_diff,
                                            sp_h, sp_a, hfa, home_adj, away_adj),
                total_reason=total_reason(home_team, away_team, book_total, pred_total, total_diff,
                                          home_avg, away_avg),
                home_display=rh.get("Team", home_team), away_display=ra.get("Team", away_team),
                five_factors=five_factors(rh, ra),
                home_power=power_table_entry(rh, net_rp_rank.get(home_key)),
                away_power=power_table_entry(ra, net_rp_rank.get(away_key)),
                home_grades=match_team_grades(grades_by_team, rh.get("Team", home_team)),
                away_grades=match_team_grades(grades_by_team, ra.get("Team", away_team)),
                home_positions={g["key"]: build_position_player(depth_rows_by_team, home_team, g, pff_by_pkey, season_by_pkey) for g in POSITION_GROUPS},
                away_positions={g["key"]: build_position_player(depth_rows_by_team, away_team, g, pff_by_pkey, season_by_pkey) for g in POSITION_GROUPS},
            )
        out.append(row)

    out.sort(key=lambda r: -(abs(r["spread_diff"] or 0) + abs(r["total_diff"] or 0)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-lines", default="hist_lines_live_2026wk1.csv")
    ap.add_argument("--team-ratings", default="team_ratings_2025.csv")
    ap.add_argument("--team-averages", default="team_averages_2025.json")
    ap.add_argument("--depth-chart", default="depth_charts.csv")
    ap.add_argument("--pff-crosswalk", default="master_crosswalk.csv")
    ap.add_argument("--season-totals", default="player_season_totals.csv")
    ap.add_argument("--team-grades", default="team_pff_grades_2025.csv")
    ap.add_argument("--team-map", default="team_map.csv")
    ap.add_argument("--date-start", default="2026-09-02", help="inclusive, YYYY-MM-DD")
    ap.add_argument("--date-end", default="2026-09-07", help="inclusive, YYYY-MM-DD")
    ap.add_argument("--week", type=int, default=1)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--out", default="diversions_2026wk1.json")
    args = ap.parse_args()

    games = build(args.game_lines, args.team_ratings, args.team_averages, args.depth_chart,
                  args.pff_crosswalk, args.season_totals, args.team_grades, args.team_map,
                  args.date_start, args.date_end)
    n_full = sum(1 for g in games if g["pred_spread"] is not None)
    n_grades = sum(1 for g in games if g.get("home_grades") or g.get("away_grades"))
    payload = dict(week=args.week, season=args.season, date_start=args.date_start,
                   date_end=args.date_end, games=games)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"Wrote {args.out}: {len(games)} games in [{args.date_start}, {args.date_end}], "
          f"{n_full} with both teams rated, {n_grades} with at least one team's PFF grades matched")


if __name__ == "__main__":
    main()
