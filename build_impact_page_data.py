#!/usr/bin/env python3
"""
build_impact_page_data.py — one-off: build a season-long player-profile
dataset (season totals, usage share, PFF grades, national/conference rank,
this-week's props + our projection, per-game trend) for the Impact tab's
player-card page.

Unlike build_props_page_data.py this isn't tied to a single week for its
core profile -- it's a season-to-date snapshot, so every skill player with
meaningful volume gets a card. It DOES reuse build_props_page_data's week
join for the "this week" props/projection section, since that's genuinely
week-specific (config.py's data only covers 2025 weeks 1-15 for now; once
the 2026 season starts this should point --week at the current week).

Run:  python3 build_impact_page_data.py --week 14 --out impact_players.json
"""
import argparse, csv, json, os
import config as C
import data_load as DL
import project as P
import build_props_page_data as BPD

SKILL_POSITIONS = {"QB", "HB", "WR", "TE", "FB"}

# Loose inclusion floor -- half of config.MIN_PRIOR_VOLUME, since this is a
# browsable profile page, not a betting-volume gate.
MIN_VOLUME = dict(pass_att=30, rush_att=15, targets=10)

GRADE_FIELDS = (
    "off_grade_off", "off_grade_pass", "off_grade_run", "off_grade_recv",
    "off_grade_pblk", "off_grade_rblk",
    "def_grade_def", "def_grade_rdef", "def_grade_prush", "def_grade_cov",
)

# (key, label, "season"|"rate"|"usage"|"grade") -- drives both the
# conditionally-formatted table and the percentile pools below. Rate/usage
# values are stored already scaled for display (catch_rate, shares -> %).
METRIC_SPECS = [
    ("pass_att", "Pass Att", "season"), ("pass_yds", "Pass Yds", "season"),
    ("pass_td", "Pass TD", "season"),
    ("rush_att", "Rush Att", "season"), ("rush_yds", "Rush Yds", "season"),
    ("rush_td", "Rush TD", "season"),
    ("targets", "Targets", "season"), ("receptions", "Receptions", "season"),
    ("rec_yds", "Rec Yds", "season"), ("rec_td", "Rec TD", "season"),
    ("ypa", "Yards / Att", "rate"), ("ypc", "Yards / Carry", "rate"),
    ("ypt", "Yards / Target", "rate"), ("catch_rate", "Catch Rate %", "rate"),
    ("rush_share_pct", "Rush Share %", "usage"), ("target_share_pct", "Target Share %", "usage"),
    ("off_grade_off", "PFF Overall", "grade"), ("off_grade_pass", "PFF Pass", "grade"),
    ("off_grade_run", "PFF Run", "grade"), ("off_grade_recv", "PFF Receiving", "grade"),
    ("off_grade_pblk", "PFF Pass Blk", "grade"), ("off_grade_rblk", "PFF Run Blk", "grade"),
    ("def_grade_def", "PFF Def Overall", "grade"), ("def_grade_rdef", "PFF Run Def", "grade"),
    ("def_grade_prush", "PFF Pass Rush", "grade"), ("def_grade_cov", "PFF Coverage", "grade"),
]

PRIMARY_STAT = {"QB": "pass_yds", "HB": "rush_yds", "FB": "rush_yds", "WR": "rec_yds", "TE": "rec_yds"}

# Position-specific "advanced" metrics, sourced from PFF's own raw season
# exports (pff_passing_advanced.csv / pff_rushing_advanced.csv /
# pff_receiving_advanced.csv -- copies of the reference files the column
# coverage in rank_pff_stats.py was aligned against) rather than the
# season-totals/crosswalk data everything else on this page comes from.
# Joined by player_id, which is the same PFF numeric ID space in both
# player_season_totals.csv and these exports (verified: e.g. Caden
# Veltkamp is 156642 in both) -- far more reliable than a name/team match.
# (field, label, decimals). Percent fields are already 0-100 in the source
# (btt_rate=4.5 means 4.5%), not 0-1, so no rescaling.
ADV_CONFIG = {
    "QB": dict(path="pff_passing_advanced.csv", fields=[
        ("avg_depth_of_target", "aDOT (air yds/throw)", 1),
        ("avg_time_to_throw", "Time to Throw (sec)", 2),
        ("accuracy_percent", "Accuracy %", 1),
        ("big_time_throws", "Big-Time Throws", 0),
        ("btt_rate", "Big-Time Throw %", 1),
        ("turnover_worthy_plays", "Turnover-Worthy Plays", 0),
        ("twp_rate", "Turnover-Worthy %", 1),
        ("sack_percent", "Sack %", 1),
        ("qb_rating", "PFF QB Rating", 1),
    ]),
    "HB": dict(path="pff_rushing_advanced.csv", fields=[
        ("yco_attempt", "Yards After Contact / Att", 2),
        ("breakaway_percent", "Breakaway Yards %", 1),
        ("elusive_rating", "Elusive Rating", 1),
        ("avoided_tackles", "Avoided Tackles", 0),
        ("explosive", "Explosive Runs", 0),
        ("longest", "Longest Run", 0),
    ]),
    "WR": dict(path="pff_receiving_advanced.csv", fields=[
        ("yprr", "Yards / Route Run", 2),
        ("avg_depth_of_target", "aDOT (air yds/target)", 1),
        ("contested_catch_rate", "Contested Catch %", 1),
        ("drop_rate", "Drop %", 1),
        ("yards_after_catch_per_reception", "YAC / Reception", 1),
        ("route_rate", "Route Participation %", 1),
        ("longest", "Longest Catch", 0),
    ]),
}
ADV_CONFIG["FB"] = ADV_CONFIG["HB"]
ADV_CONFIG["TE"] = ADV_CONFIG["WR"]


def load_advanced_stats(path):
    """path -> {player_id: {field: float}} using every numeric column in
    that position's ADV_CONFIG fields list. Returns {} if the file isn't
    there (advanced section just doesn't appear rather than erroring)."""
    out = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            pid = r.get("player_id")
            if not pid:
                continue
            out[pid] = r
    return out


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def _to_float(x):
    try:
        return float(str(x).replace(",", ""))
    except (ValueError, TypeError):
        return None


def meets_volume_floor(tot):
    return (
        (tot.get("pass_att") or 0) >= MIN_VOLUME["pass_att"]
        or (tot.get("rush_att") or 0) >= MIN_VOLUME["rush_att"]
        or (tot.get("targets") or 0) >= MIN_VOLUME["targets"]
    )


def load_conferences(path):
    """team_ratings_2025.csv -> {tkey: conference name}. Conference.y is the
    complete column (Conference.x is ~75% blank in this file); Team is
    already CFBD-style, same key space as everything else here."""
    out = {}
    try:
        f = open(path)
    except OSError:
        return out
    for r in csv.DictReader(f):
        team = r.get("Team", "")
        if not team:
            continue
        conf = r.get("Conference.y") or r.get("Conference.x") or ""
        if conf:
            out[norm(team)] = conf
    return out


def percentile_rank(value, values):
    """Fraction of `values` this value beats (ties split), 0..1. 1.0 if
    there's no real pool (nothing to compare against)."""
    n = len(values)
    if n <= 1:
        return 1.0
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return (below + 0.5 * equal) / n


def build(week, props_path, lines_path, ratings_path, grades_path, season=2025, depth_chart_path=None,
          date_start=None, date_end=None, include_departed=False):
    pff2c, _ = DL.load_team_map()
    # The season TABLE always compares the two most recent COMPLETE seasons
    # (2025 vs. real 2024), regardless of which season/week the "this week"
    # props section below targets -- there's no played-game data for a
    # season until it's actually underway, so a 2026 week-1 run still shows
    # 2025-vs-2024 here (the only meaningful season-long comparison that
    # exists yet), while `season` only steers the live props/projection join.
    totals = DL.load_season_totals()      # 2025 season-to-date, keyed (pkey, tkey)
    prior = DL.load_prior_totals(season=2025)  # real 2024, keyed player_id
    logs = DL.load_game_logs()            # 2025 per-game, keyed (pkey, tkey)
    conferences = load_conferences(ratings_path)

    # load_season_totals() drops the raw "player"/"team" strings from its
    # dict (they're join keys, not stats) -- re-read them directly for display.
    raw_by_key = {k: (r.get("player", ""), r.get("team", ""))
                  for k, r in DL.load_totals_rows(season).items()}

    # Keyed by name only (not (pkey, tkey)): master_crosswalk.csv's "team"
    # column tracks each player's CURRENT team, which for a transferred
    # player is already their 2026 destination, not the team their 2025
    # stats were earned on -- requiring a team match here silently dropped
    # PFF grades for every portal player. Skill-position-only (see
    # load_pff_skill_by_pkey) to avoid a same-name collision with an
    # unrelated player at another position -- found for real: a defensive
    # back "Jordan Allen" at Houston was overriding a Georgia Tech WR of
    # the same name.
    pff_by_pkey = DL.load_pff_skill_by_pkey(pff2c)
    depth_chart = DL.load_depth_chart(depth_chart_path) if depth_chart_path else {}
    canonical_tkeys = {p["tkey"] for p in pff_by_pkey.values()}
    team_display_by_tkey = {p["tkey"]: p["team_cfbd"] for p in pff_by_pkey.values()}

    # Advanced position-specific metrics (aDOT, BTT/TWP, YCO/att, YPRR,
    # etc), loaded once per source file and joined by player_id below.
    adv_cache = {}
    for cfg in {"QB": ADV_CONFIG["QB"], "HB": ADV_CONFIG["HB"], "WR": ADV_CONFIG["WR"]}.values():
        if cfg["path"] not in adv_cache:
            adv_cache[cfg["path"]] = load_advanced_stats(cfg["path"])

    # Team volume pools (this season) for usage-share -- every player
    # counts toward the pool, not just the ones that clear MIN_VOLUME.
    team_totals = P.build_team_volume_totals(
        ((tkey, tot) for (pkey, tkey), tot in totals.items()),
        vol_cols=("rush_att", "targets"),
    )

    print(f"Joining week-{week} props + projections for the 'this week' section ...")
    week_props = {}
    try:
        games = BPD.build_week(week, props_path, lines_path, ratings_path, grades_path, season=season,
                               depth_chart_path=depth_chart_path,
                               date_start=date_start, date_end=date_end)
        for g in games:
            for pl in g["players"]:
                week_props[norm(pl["name"])] = dict(
                    matchup=f"{g['away_team']} @ {g['home_team']}",
                    commence_time=g.get("commence_time", ""),
                    markets=pl["markets"],
                )
        print(f"  {len(week_props)} players with a week-{week} prop")
    except FileNotFoundError as e:
        print(f"  [warn] skipping this-week props: {e}")

    # Every card starts from a 2025 season-totals row, so by default the page
    # carries last year's whole skill-position population -- including the
    # ~40% who have since graduated or gone to the NFL (Diego Pavia, Ty
    # Simpson, Jeremiyah Love, Jalon Daniels and 668 others). They have no
    # 2026 team, so they render with a blank team and no "this week" section,
    # and they dilute every rank and filter on the page. Three independent
    # signals count as evidence a player is still on a 2026 roster, and any
    # one of them keeps the card:
    #   - master_crosswalk.csv (PFF's current-team assignment)
    #   - depth_charts.csv (the ourlads 2026 scrape)
    #   - a posted prop market for this week, which no book offers on a
    #     player who isn't on a roster -- this one matters because the first
    #     two have real gaps (it alone saves Nathan McNeil of Iowa).
    #   - a row in this season's own PFF totals (player_current_totals.csv),
    #     which is the strongest signal of the four: he has actually played
    #     a snap this year.
    # --include-departed restores the old, unfiltered population.
    cur_totals = DL.load_current_totals(season=season)
    on_2026_roster = (set(pff_by_pkey) | set(depth_chart) | set(week_props)
                      | {norm(r.get("player", "")) for r in cur_totals.values()})

    players = []
    n_departed = 0
    for (pkey, tkey), tot in totals.items():
        if tot.get("position") not in SKILL_POSITIONS:
            continue
        if not meets_volume_floor(tot):
            continue
        if not include_departed and pkey not in on_2026_roster:
            n_departed += 1
            continue

        grades = pff_by_pkey.get(pkey, {})
        player_id = tot.get("player_id")
        prior_tot = prior.get(player_id) if player_id else None

        rates_2025 = P.compute_player_rates(tot)
        rates_2024 = P.compute_player_rates(prior_tot) if prior_tot else {}

        team_pool = team_totals.get(tkey, {})
        rush_share = None
        if team_pool.get("rush_att") and tot.get("rush_att") is not None:
            rush_share = round(tot["rush_att"] / team_pool["rush_att"] * 100, 1)
        target_share = None
        if team_pool.get("targets") and tot.get("targets") is not None:
            target_share = round(tot["targets"] / team_pool["targets"] * 100, 1)

        game_log = sorted(
            [g for g in logs.get((pkey, tkey), []) if g.get("week") is not None],
            key=lambda g: g["week"],
        )
        game_log_out = []
        for g in game_log:
            row = dict(week=int(g["week"]), pass_yds=g.get("pass_yds"), rush_yds=g.get("rush_yds"),
                       rec_yds=g.get("rec_yds"), receptions=g.get("receptions"),
                       pass_att=g.get("pass_att"), rush_att=g.get("rush_att"), targets=g.get("targets"))
            game_log_out.append({k: v for k, v in row.items() if v is not None})

        raw_name, raw_team = raw_by_key.get((pkey, tkey), ("", ""))
        stats_team = pff2c.get(norm(raw_team), raw_team)
        # Display team: prefer the crosswalk's (current/2026) team when we
        # have one, since that's where this player actually is now; then the
        # current-season depth chart, which covers transfers the crosswalk
        # misses (Kenny Minchey was showing Notre Dame while starting for
        # Kentucky, Austin Simmons showing Ole Miss while at Missouri); fall
        # back to the 2025 team their stats below were earned on.
        display_team = grades.get("team_cfbd")
        if not display_team:
            dc_tkey = DL.resolve_depth_chart_team(
                (depth_chart.get(pkey) or {}).get("raw_team"), canonical_tkeys)
            if dc_tkey:
                display_team = team_display_by_tkey.get(dc_tkey, dc_tkey)
        display_team = display_team or stats_team
        conference = conferences.get(norm(stats_team)) or conferences.get(norm(display_team))

        rates_2025_r = {k: (round(v, 2) if v is not None else None) for k, v in rates_2025.items()}
        rates_2024_r = {k: (round(v, 2) if v is not None else None) for k, v in rates_2024.items()}
        catch_2025 = rates_2025_r.get("catch_rate")
        catch_2024 = rates_2024_r.get("catch_rate")

        raw_values = dict(
            pass_att=tot.get("pass_att"), pass_yds=tot.get("pass_yds"), pass_td=tot.get("pass_td"),
            rush_att=tot.get("rush_att"), rush_yds=tot.get("rush_yds"), rush_td=tot.get("rush_td"),
            targets=tot.get("targets"), receptions=tot.get("receptions"),
            rec_yds=tot.get("rec_yds"), rec_td=tot.get("rec_td"),
            ypa=rates_2025_r.get("ypa"), ypc=rates_2025_r.get("ypc"), ypt=rates_2025_r.get("ypt"),
            catch_rate=(round(catch_2025 * 100, 1) if catch_2025 is not None else None),
            rush_share_pct=rush_share, target_share_pct=target_share,
        )
        for f in GRADE_FIELDS:
            raw_values[f] = _to_float(grades.get(f))
        raw_values_2024 = dict(
            pass_att=prior_tot.get("pass_att") if prior_tot else None,
            pass_yds=prior_tot.get("pass_yds") if prior_tot else None,
            pass_td=prior_tot.get("pass_td") if prior_tot else None,
            rush_att=prior_tot.get("rush_att") if prior_tot else None,
            rush_yds=prior_tot.get("rush_yds") if prior_tot else None,
            rush_td=prior_tot.get("rush_td") if prior_tot else None,
            targets=prior_tot.get("targets") if prior_tot else None,
            receptions=prior_tot.get("receptions") if prior_tot else None,
            rec_yds=prior_tot.get("rec_yds") if prior_tot else None,
            rec_td=prior_tot.get("rec_td") if prior_tot else None,
            ypa=rates_2024_r.get("ypa"), ypc=rates_2024_r.get("ypc"), ypt=rates_2024_r.get("ypt"),
            catch_rate=(round(catch_2024 * 100, 1) if catch_2024 is not None else None),
        )

        this_week = week_props.get(pkey)

        position = tot.get("position") or grades.get("position") or ""
        adv_cfg = ADV_CONFIG.get(position)
        advanced = None
        if adv_cfg and player_id:
            adv_row = adv_cache.get(adv_cfg["path"], {}).get(player_id)
            if adv_row:
                advanced = [
                    dict(key=field, label=label, dec=dec,
                         value=round(v, dec) if (v := _to_float(adv_row.get(field))) is not None else None)
                    for field, label, dec in adv_cfg["fields"]
                ]
                advanced = [m for m in advanced if m["value"] is not None]
                if not advanced:
                    advanced = None

        players.append(dict(
            name=grades.get("name") or raw_name or pkey,
            player_id=player_id,
            team=display_team,
            stats_team=stats_team if stats_team != display_team else None,
            conference=conference,
            position=position,
            advanced=advanced,
            height=grades.get("height") or "",
            weight=grades.get("weight") or "",
            season_2025=dict(games=tot.get("games"), **{k: tot.get(k) for k in
                             ("pass_att", "pass_yds", "pass_td", "rush_att", "rush_yds", "rush_td",
                              "targets", "receptions", "rec_yds", "rec_td")}),
            games_2025=tot.get("games"),
            games_2024=prior_tot.get("games") if prior_tot else None,
            raw_values=raw_values,
            raw_values_2024=raw_values_2024,
            usage=dict(rush_share_pct=rush_share, target_share_pct=target_share),
            game_log=game_log_out,
            this_week=this_week,
        ))

    # ---- national + conference rank, and per-metric percentiles, within position ----
    by_pos = {}
    for p in players:
        by_pos.setdefault(p["position"], []).append(p)

    for pos, plist in by_pos.items():
        pstat = PRIMARY_STAT.get(pos)
        if pstat:
            ranked = sorted(plist, key=lambda p: (p["raw_values"].get(pstat) or 0), reverse=True)
            for i, p in enumerate(ranked):
                p["prod_nat_rank"] = dict(rank=i + 1, of=len(ranked))
            by_conf = {}
            for p in plist:
                by_conf.setdefault(p["conference"], []).append(p)
            for conf, clist in by_conf.items():
                if not conf:
                    continue
                cranked = sorted(clist, key=lambda p: (p["raw_values"].get(pstat) or 0), reverse=True)
                for i, p in enumerate(cranked):
                    p["prod_conf_rank"] = dict(rank=i + 1, of=len(cranked))

        # PFF-grade rank -- the page's PRIMARY rank/sort (see p3s Player
        # Impact redesign): only players PFF actually graded that season
        # are ranked (no 0-fill for the ungraded, which would misrank them
        # as worst-in-class rather than simply "no grade available").
        graded = [p for p in plist if p["raw_values"].get("off_grade_off") is not None]
        graded_ranked = sorted(graded, key=lambda p: p["raw_values"]["off_grade_off"], reverse=True)
        for i, p in enumerate(graded_ranked):
            p["grade_nat_rank"] = dict(rank=i + 1, of=len(graded_ranked))
        by_conf_g = {}
        for p in graded:
            by_conf_g.setdefault(p["conference"], []).append(p)
        for conf, clist in by_conf_g.items():
            if not conf:
                continue
            cranked = sorted(clist, key=lambda p: p["raw_values"]["off_grade_off"], reverse=True)
            for i, p in enumerate(cranked):
                p["grade_conf_rank"] = dict(rank=i + 1, of=len(cranked))

        for key, label, group in METRIC_SPECS:
            vals = [p["raw_values"][key] for p in plist if p["raw_values"].get(key) is not None]
            if not vals:
                continue
            for p in plist:
                v = p["raw_values"].get(key)
                if v is not None:
                    p.setdefault("percentiles", {})[key] = round(percentile_rank(v, vals), 3)

    # Build the final flat metric-row list per player now that percentiles exist.
    for p in players:
        pct = p.pop("percentiles", {})
        rv, rv24 = p.pop("raw_values"), p.pop("raw_values_2024")
        rows = []
        for key, label, group in METRIC_SPECS:
            v = rv.get(key)
            if v is None:
                continue
            rows.append(dict(key=key, label=label, group=group, v2025=v, v2024=rv24.get(key),
                             pct=pct.get(key)))
        p["metrics"] = rows
        p.setdefault("prod_nat_rank", None)
        p.setdefault("prod_conf_rank", None)
        p.setdefault("grade_nat_rank", None)
        p.setdefault("grade_conf_rank", None)

    players.sort(key=lambda p: (p["team"], p["position"], p["name"]))
    if n_departed:
        print(f"  dropped {n_departed} players with no 2026 roster evidence "
              f"(--include-departed keeps them)")
    return players


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=14)
    ap.add_argument("--season", type=int, default=2025,
                    help="season the 'this week' props/projection section targets "
                         "(the season TABLE always shows 2025 vs. real 2024 -- see build())")
    ap.add_argument("--props", default="hist_props_closing_wk1-15.csv")
    ap.add_argument("--game-lines", default="hist_lines_closing_wk1-15.csv")
    ap.add_argument("--team-ratings", default="team_ratings_2025.csv")
    ap.add_argument("--team-grades", default=None,
                    help="PFF team-grade export; defaults to the --season file "
                         "from config.TEAM_GRADES_BY_SEASON")
    ap.add_argument("--depth-chart", default=None,
                    help="path to depth_charts.csv (pull_depth_charts.py) -- nudges "
                         "volume by ourlads.com depth-chart rank for pure-prior-year "
                         "weeks only (UNVALIDATED, see config.DEPTH_RANK_MULT). "
                         "No effect if omitted.")
    ap.add_argument("--date-start", default=None,
                    help="inclusive kickoff-date bound, YYYY-MM-DD -- restricts the "
                         "game-lines file to one slate (a live pull labels two "
                         "weekends with the same week number). No filter if omitted.")
    ap.add_argument("--date-end", default=None, help="inclusive, YYYY-MM-DD")
    ap.add_argument("--include-departed", action="store_true",
                    help="keep 2025 players with no evidence of a 2026 roster spot "
                         "(graduated/NFL). Off by default -- see build().")
    ap.add_argument("--out", default="impact_players.json")
    args = ap.parse_args()
    if args.team_grades is None:
        args.team_grades = C.team_grades_for(args.season)

    players = build(args.week, args.props, args.game_lines, args.team_ratings, args.team_grades,
                    season=args.season, depth_chart_path=args.depth_chart,
                    date_start=args.date_start, date_end=args.date_end,
                    include_departed=args.include_departed)
    payload = dict(season=args.season, season_table_year=2025, week=args.week,
                   generated_players=len(players), players=players)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"Wrote {args.out}: {len(players)} player cards")


if __name__ == "__main__":
    main()
