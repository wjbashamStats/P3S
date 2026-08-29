#!/usr/bin/env python3
"""
backtest.py — join model projections + closing-line props + actual results,
and score the model.

Three inputs, one row per (player, week, market) after the join:
  - model projection  : from build.py's projection engine (re-run here so it's
                         always current with config.py's tuning constants)
  - closing line       : the flattened historical props CSV (from
                          historical_pull.R / historical_pull.py + a flattener)
  - actual result       : player_game_logs.csv (the 2025 weekly game logs)

Matches on normalized player name + week; market keys map to the stat column
the market resolves to (see config.MARKETS).

CAVEATS (read before trusting the numbers this prints):
  - Without --use-prior-year, projections are built from
    player_season_totals.csv, derived from the FULL 2025 season --
    including week 1 itself. That's lookahead bias: the "prior-year rate"
    input for week 1 already contains week 1's own result. Those numbers
    are a calibration/sanity check on the heuristic's shape, not evidence
    of real predictive edge.
  - --use-prior-year sources rates from player_prior_totals.csv (real 2024
    data, matched by player_id so transfers carry their history to their
    new team) instead, removing that bias -- this is the legitimate
    backtest. It falls back to current-season totals for any player with
    no 2024 record (true freshmen, JUCO transfers, etc.) -- watch the
    printed match-rate; a low one means the result still leans on biased
    fallback data for a chunk of the roster.
  - Only the closing snapshot was pulled (PROJECT_STATE.md's scope decision),
    so closing-line value (CLV) isn't computable -- that needs an opening
    snapshot too. This script reports hit rate and calibration only.

Run:  python3 backtest.py --props hist_props_closing_wk1.csv --week 1 --use-prior-year
  or: python3 backtest.py --props hist_props_closing_wk1-5.csv --week-start 1 --week-end 5 --use-prior-year
"""
import argparse, csv, statistics as stats
from collections import defaultdict

import config as C
import data_load as DL
import project as P


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def build_projections(week, use_prior_year=False, lines_by_week=None, team_ratings=None,
                      team_grades=None, season=2025, use_tarp=False):
    """Re-run the same projection logic build.py uses, keyed by (norm(player), market).

    use_prior_year=True sources volume/efficiency from the prior-year file for
    `season` (config.PRIOR_TOTALS_BY_SEASON -- real 2024 data for 2025, 2025's
    own totals for 2026) instead of this year's own totals -- the fix for the
    lookahead bias described in this module's docstring. Falls back to
    current-season totals for any player_id with no prior-year record.

    lines_by_week: optional dict from DL.load_game_lines(), nudging volume by
    this week's implied team total / spread (see project.game_context_adj).
    Also used to resolve each player's actual opponent for this week (via
    DL.find_opponent_tkey) -- without it, opp_tkey is always None and BOTH
    opponent adjustments (PFF-grade and team_ratings) are inert, same as
    every backtest run before this one.

    team_ratings: optional dict from DL.load_team_ratings(), a second,
    independent opponent adjustment (see project.success_rate_adj).
    team_grades: optional dict from DL.load_team_grades(), a matchup
    adjustment using PFF's own team-level grades (see project.matchup_grade_adj).
    """
    pff2c, _ = DL.load_team_map()
    pff = DL.load_pff(pff2c)
    totals = DL.load_season_totals()
    logs = DL.load_game_logs()
    prior = DL.load_prior_totals(season=season) if use_prior_year else {}
    pos_means = P.position_means(prior if (use_prior_year and prior) else totals)
    def_index = P.build_def_index(pff)
    sr_index = P.build_success_rate_index(team_ratings) if team_ratings else {}
    grade_index = P.build_matchup_grade_index(team_grades) if team_grades else {}
    tarp_index = P.build_tarp_index(team_ratings) if (use_tarp and team_ratings) else {}
    canonical_tkeys = set(def_index) | set(sr_index) | set(grade_index) | set(tarp_index)

    lines_by_week = lines_by_week or {}
    week_avg_implied = DL.league_avg_implied(lines_by_week, str(week)) if lines_by_week else None
    if lines_by_week:
        n_lines = len(lines_by_week.get(str(week), []))
        print(f"  --game-lines: {n_lines} games loaded for week {week}"
              + (f" | league avg implied total: {week_avg_implied:.1f}" if week_avg_implied else " | none for this week"))
    if team_ratings:
        print(f"  --team-ratings: {len(team_ratings)} teams loaded")
    if team_grades:
        print(f"  --team-grades: {len(team_grades)} teams loaded")

    if use_prior_year:
        prior_year_label = season - 1
        n_with_prior = sum(1 for tot in totals.values() if tot.get("player_id") in prior)
        mode = ("blended with weeks < %d" % week if week > C.PRIOR_ONLY_UNTIL_WEEK
                else f"pure {prior_year_label} (no current-season games exist yet to blend)")
        print(f"  --use-prior-year: {len(prior)} players with a {prior_year_label} record | "
              f"{n_with_prior}/{len(totals)} of this year's roster matched to one | mode: {mode}")

    # Team volume pools (rush_att/targets), for share-based volume in pure
    # prior-year weeks (see project.team_share_volume / build.py's identical
    # wiring for the full rationale).
    team_totals_prior = P.build_team_volume_totals(
        ((DL.resolve_tkey(rec.get("team"), pff2c), rec) for rec in prior.values()),
    ) if prior else {}

    pff_by_key = {}
    for p in pff:
        pff_by_key.setdefault((p["pkey"], p["tkey"]), p)

    out = {}
    for (pkey, tkey), tot in totals.items():
        source = None
        prior_rec = None
        n_cur_games = None
        if use_prior_year:
            prior_rec = prior.get(tot.get("player_id"))
            if week > C.PRIOR_ONLY_UNTIL_WEEK:
                current_games = [g for g in logs.get((pkey, tkey), [])
                                 if g.get("week") is not None and g["week"] < week]
                n_cur_games = len(current_games)
                source = P.blend_prior_and_current(prior_rec, current_games)
            else:
                source = prior_rec
        if source is None:
            source = tot
        rates = P.compute_player_rates(source)
        rates_shrunk = {k: P.shrink(rates.get(k), pos_means.get(k, 0.0), source.get("games"))
                        for k in ("ypa", "ypc", "ypt", "catch_rate")}
        # tkey is season_totals' own raw team key (e.g. "ntexas" from "N
        # TEXAS") -- find_team_game_line/find_opponent_tkey/grade_index/
        # tarp_index all key off the CANONICAL CFBD-style name ("North
        # Texas" -> "northtexas"). Resolve once so a team whose raw
        # abbreviation isn't already identical to its canonical form after
        # norm() still gets game context, an opponent, and PFF matchup
        # grade/TARP adjustments instead of silently falling back to inert.
        canon_tkey = DL.resolve_tkey(tkey, pff2c)
        grades = pff_by_key.get((pkey, canon_tkey), {}) or pff_by_key.get((pkey, tkey), {})
        player_name = grades.get("name") or pkey

        team_implied, team_spread = (DL.find_team_game_line(canon_tkey, str(week), lines_by_week)
                                     if lines_by_week else (None, None))
        opp_tkey = (DL.find_opponent_tkey(canon_tkey, str(week), lines_by_week, canonical_tkeys)
                   if lines_by_week else None)

        share_source_team = (DL.resolve_tkey(prior_rec.get("team"), pff2c)
                             if (week <= C.PRIOR_ONLY_UNTIL_WEEK and prior_rec) else None)

        for mkey, mdef in C.MARKETS.items():
            vol_adj = P.game_context_adj(team_implied, week_avg_implied, team_spread, mdef["side"])
            sr_component = P.success_rate_adj(sr_index, opp_tkey, mdef["side"], mdef["stat"]) if sr_index else 1.0
            mg_component = P.matchup_grade_adj(grade_index, canon_tkey, opp_tkey, mkey) if grade_index else 1.0
            tarp_component = P.tarp_adj(tarp_index, canon_tkey, opp_tkey) if tarp_index else 1.0
            extra_adj = sr_component * mg_component * tarp_component
            vol_col = mdef["volume"]
            per_game_vol_override = None
            vol_source = None
            if share_source_team and vol_col in P.SHARE_VOL_COLS:
                per_game_vol_override = P.team_share_volume(
                    source.get(vol_col), team_totals_prior.get(share_source_team, {}).get(vol_col),
                    team_totals_prior.get(canon_tkey, {}), vol_col)
                vol_source = f"team-share of {share_source_team}'s 2024 {vol_col} pool, applied to {canon_tkey}'s 2025 pool"
            elif not use_prior_year:
                vol_source = f"{tot.get('games')} 2025 games (in-season)"
            elif week <= C.PRIOR_ONLY_UNTIL_WEEK:
                vol_source = f"{prior_rec.get('games') if prior_rec else 0} 2024 games (pure prior-year, week <= {C.PRIOR_ONLY_UNTIL_WEEK})"
            else:
                vol_source = f"blended: {n_cur_games} 2025 games + {prior_rec.get('games') if prior_rec else 0} 2024 games"
            proj = P.project_player_market(source, logs.get((pkey, tkey)), rates_shrunk,
                                           mkey, mdef, def_index, opp_tkey=opp_tkey,
                                           vol_adj=vol_adj, extra_adj=extra_adj,
                                           per_game_vol_override=per_game_vol_override)
            if proj is None:
                continue
            breakdown = dict(
                volume_source=vol_source,
                pace_script_adj=round(vol_adj, 3),
                team_implied=round(team_implied, 1) if team_implied is not None else None,
                league_avg_implied=round(week_avg_implied, 1) if week_avg_implied is not None else None,
                team_spread=team_spread,
                opponent=opp_tkey,
                pff_def_grade_adj=round(P.opponent_adj(def_index, opp_tkey, mdef["def_unit"]), 3),
                pff_def_grade_adj_active=C.OPP_ADJ_STRENGTH != 0,
                success_rate_adj=round(sr_component, 3) if sr_index else None,
                matchup_grade_adj=round(mg_component, 3) if grade_index else None,
                tarp_adj=round(tarp_component, 3) if tarp_index else None,
            )
            out[(norm(player_name), mkey)] = dict(player=player_name, breakdown=breakdown, **proj)
    return out


def load_actuals(week):
    """player_game_logs.csv rows for this week, keyed by norm(player)."""
    out = defaultdict(list)
    for r in csv.DictReader(open(C.GAME_LOGS)):
        if str(r.get("week")) != str(week):
            continue
        out[norm(r.get("player", ""))].append(r)
    return out


def load_props(path):
    return list(csv.DictReader(open(path)))


def join_week(week, all_props, use_prior_year, lines_by_week=None, team_ratings=None,
              team_grades=None, season=2025, use_tarp=False):
    """Build projections, load actuals, and join to this week's props. Returns rows."""
    print(f"\n--- week {week} "
          f"({'2024 prior-year' if use_prior_year else 'in-season (has lookahead bias)'}) ---")
    projections = build_projections(week, use_prior_year=use_prior_year, lines_by_week=lines_by_week,
                                    team_ratings=team_ratings, team_grades=team_grades,
                                    season=season, use_tarp=use_tarp)
    print(f"  {len(projections)} (player, market) projections")

    actuals = load_actuals(week)
    print(f"  {len(actuals)} players with a week-{week} game log")

    props = [r for r in all_props if str(r.get("week")) == str(week)]
    print(f"  {len(props)} prop rows for week {week}")

    rows = []
    unmatched_proj, unmatched_actual = 0, 0
    for r in props:
        pkey = norm(r["player"])
        market = r["market"]
        mdef = C.MARKETS.get(market)
        if mdef is None:
            continue
        proj = projections.get((pkey, market))
        if proj is None:
            unmatched_proj += 1
            continue
        actual_logs = actuals.get(pkey)
        if not actual_logs:
            unmatched_actual += 1
            continue
        actual_val = None
        for log in actual_logs:
            v = log.get(mdef["stat"])
            if v not in (None, ""):
                actual_val = float(v)
                break
        if actual_val is None:
            unmatched_actual += 1
            continue

        book_line = float(r["book_line"]) if r.get("book_line") not in (None, "", "NA") else None
        edge = round(proj["projection"] - book_line, 1) if book_line is not None else None
        lean = None
        if edge is not None:
            lean = "Over" if edge > 0 else ("Under" if edge < 0 else "Push")
        thr = C.EDGE_FLAG.get(mdef["stat"])
        flagged = bool(edge is not None and thr and abs(edge) >= thr)
        hit = None
        if lean in ("Over", "Under") and book_line is not None:
            if actual_val == book_line:
                hit = None  # push, excluded from hit rate
            else:
                actual_side = "Over" if actual_val > book_line else "Under"
                hit = (actual_side == lean)

        rows.append(dict(
            player=r["player"], week=week, market=market, stat=mdef["stat"],
            projection=proj["projection"], book_line=book_line, actual=actual_val,
            edge=edge, lean=lean, flagged=flagged, hit=hit, n_books=r.get("n_books"),
        ))

    print(f"  joined {len(rows)} rows "
          f"(unmatched: {unmatched_proj} no model projection, {unmatched_actual} no actual result)")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--props", required=True, help="flattened closing-line props CSV")
    ap.add_argument("--week", type=int, help="a single week")
    ap.add_argument("--week-start", type=int, help="first week of a range (with --week-end)")
    ap.add_argument("--week-end", type=int, help="last week of a range (with --week-start)")
    ap.add_argument("--use-prior-year", action="store_true",
                    help="project off real 2024 rates (player_prior_totals.csv) instead "
                         "of this year's own totals -- removes the lookahead bias noted "
                         "in this file's docstring. Requires player_prior_totals.csv "
                         "(built by build_player_tables.py from 2024_*_season_clean.csv).")
    ap.add_argument("--game-lines", default=None,
                    help="path to a hist_lines_closing_wkN.csv (from historical_pull.R "
                         "--game-lines) -- nudges volume by each week's implied team "
                         "total (pace) and spread (rush/pass script), and (combined with "
                         "--team-ratings) resolves each player's real opponent so BOTH "
                         "opponent adjustments (PFF-grade and team-ratings) activate -- "
                         "without it opp_tkey is always None, as in every backtest before "
                         "this option existed. No effect if omitted.")
    ap.add_argument("--team-ratings", default=None,
                    help="path to team_ratings_2025.csv (CFBD rush/pass rate + success "
                         "rate, offense/defense) -- adds a second, independent opponent "
                         "adjustment alongside the PFF-grade one. Needs --game-lines too "
                         "to resolve opponents. No effect if omitted.")
    ap.add_argument("--team-grades", default=None,
                    help="path to team_pff_grades_2025.csv (PFF's own team-level "
                         "grades) -- a matchup adjustment (config.MATCHUP_UNITS). "
                         "Needs --game-lines too to resolve opponents. No effect if omitted.")
    ap.add_argument("--season", type=int, default=2025,
                    help="which season's prior-year file to use (config.PRIOR_TOTALS_BY_SEASON) "
                         "-- 2025 (default) uses real 2024 data, 2026 reuses 2025's own totals.")
    ap.add_argument("--tarp", action="store_true",
                    help="apply the 2026 coaching/returning-production adjustment "
                         "(team_ratings' OffAdj/DefAdj -- see project.tarp_adj). "
                         "Requires --team-ratings. ONLY meaningful for --season 2026 "
                         "(UNVALIDATED -- no 2026 games exist yet to tune against).")
    args = ap.parse_args()

    if args.week is not None:
        weeks = [args.week]
    elif args.week_start is not None and args.week_end is not None:
        weeks = list(range(args.week_start, args.week_end + 1))
    else:
        ap.error("pass --week, or --week-start/--week-end together")

    print(f"Loading props from {args.props} ...")
    all_props = load_props(args.props)
    team_ratings = DL.load_team_ratings(args.team_ratings) if args.team_ratings else {}
    team_grades = DL.load_team_grades(args.team_grades) if args.team_grades else {}
    lines_by_week = DL.load_game_lines(args.game_lines) if args.game_lines else {}

    rows = []
    for week in weeks:
        rows.extend(join_week(week, all_props, args.use_prior_year, lines_by_week, team_ratings,
                              team_grades, season=args.season, use_tarp=args.tarp))

    print(f"\nTotal joined across weeks {weeks[0]}-{weeks[-1]}: {len(rows)} rows")

    suffix = "_prior" if args.use_prior_year else "_inseason"
    wk_label = weeks[0] if len(weeks) == 1 else f"{weeks[0]}-{weeks[-1]}"
    out_name = f"backtest_week{wk_label}{suffix}.csv"
    _write_joined(rows, out_name)

    if len(weeks) > 1:
        for week in weeks:
            print(f"\n########## WEEK {week} ##########")
            _report([r for r in rows if r["week"] == week])
        print("\n########## ALL WEEKS COMBINED ##########")
    _report(rows)


def _write_joined(rows, out_name):
    cols = ["player", "week", "market", "stat", "projection", "book_line",
            "actual", "edge", "lean", "flagged", "hit", "n_books"]
    with open(out_name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"Wrote {out_name}")


def _report(rows):
    print("\n=== Calibration + hit rate by market ===")
    by_market = defaultdict(list)
    for r in rows:
        by_market[r["market"]].append(r)

    for market, rs in sorted(by_market.items()):
        errs = [r["projection"] - r["actual"] for r in rs]
        mae = stats.mean(abs(e) for e in errs)
        bias = stats.mean(errs)
        flagged = [r for r in rs if r["flagged"] and r["hit"] is not None]
        hits = [r for r in flagged if r["hit"]]
        hit_rate = (len(hits) / len(flagged)) if flagged else None
        all_scored = [r for r in rs if r["hit"] is not None]
        all_hits = [r for r in all_scored if r["hit"]]
        overall_rate = (len(all_hits) / len(all_scored)) if all_scored else None
        print(f"\n{market}  (n={len(rs)})")
        print(f"  MAE: {mae:.1f}  |  bias (proj-actual): {bias:+.1f}")
        print(f"  lean hit rate, all scored props: "
              f"{overall_rate*100:.1f}% ({len(all_hits)}/{len(all_scored)})" if overall_rate is not None
              else "  lean hit rate: n/a (no non-push props)")
        print(f"  lean hit rate, FLAGGED edges only: "
              f"{hit_rate*100:.1f}% ({len(hits)}/{len(flagged)})" if hit_rate is not None
              else "  lean hit rate, flagged edges: n/a (no flagged edges this week)")


if __name__ == "__main__":
    main()
