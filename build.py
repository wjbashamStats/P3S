"""
build.py — orchestrator. Produces the one table everything else reads:

  player_projections : per player, per market, per game — projection, variance,
                       PFF grades, book line, and edge.

Then writes two views:
  - prop_edges.csv   : projection vs market, sorted by edge (the betting view)
  - impact.json      : searchable by team / position / week (the HTML page feed)

Run:  python3 build.py --week 1
Slate/opponent wiring: for weeks 1-3 the opponent for each player comes from the
Odds API event (home/away). This keeps the model runnable before schedule data
is fully wired; swap in CFBD /games for a full schedule join later.
"""
import argparse, csv, json, os
import config as C
import data_load as DL
import project as P
import odds as O


def resolve_opponent(player_tkey, events, odds2c):
    """
    Find the game a player's team is in this slate, return the OPPONENT tkey.
    Returns None if the team isn't playing this week's pulled slate.
    """
    for ev in events:
        home_c = odds2c.get(DL.norm(ev["home"]), ev["home"])
        away_c = odds2c.get(DL.norm(ev["away"]), ev["away"])
        if DL.norm(home_c) == player_tkey:
            return DL.norm(away_c), ev["game_id"]
        if DL.norm(away_c) == player_tkey:
            return DL.norm(home_c), ev["game_id"]
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", type=int, default=C.SEASON,
                    help="season the projections/backtest are for (default: config.SEASON)")
    ap.add_argument("--prop-cap", type=int, default=None,
                    help="max games to pull props for (credit control)")
    ap.add_argument("--no-odds", action="store_true",
                    help="build projections without calling the Odds API")
    ap.add_argument("--use-prior-year", action="store_true",
                    help="project off real prior-year (player_prior_totals.csv) rates "
                         "instead of the current season's own totals -- avoids the "
                         "lookahead bias of projecting week 1 from a total that "
                         "includes week 1. Falls back to current-season totals for "
                         "any player_id with no prior-year record (true freshmen, etc).")
    ap.add_argument("--game-lines", default=None,
                    help="path to a hist_lines_closing_wkN.csv (from historical_pull.R "
                         "--game-lines) -- nudges volume by this week's implied team "
                         "total (pace) and spread (rush/pass script). No effect if omitted.")
    ap.add_argument("--team-ratings", default=None,
                    help="path to team_ratings_2025.csv (CFBD rush/pass rate + success "
                         "rate, offense/defense) -- adds a second, independent opponent "
                         "adjustment alongside the PFF-grade one. No effect if omitted.")
    ap.add_argument("--team-grades", default=None,
                    help="path to team_pff_grades_2025.csv (PFF's own team-level "
                         "grades) -- a matchup adjustment (this team's own relevant "
                         "unit vs the opponent's complementary one, see config."
                         "MATCHUP_UNITS). No effect if omitted.")
    args = ap.parse_args()

    C.SEASON = args.season
    os.makedirs(C.OUTPUT_DIR, exist_ok=True)

    print("Loading data ...")
    pff2c, odds2c = DL.load_team_map()
    pff = DL.load_pff(pff2c)
    totals = DL.load_season_totals()
    logs = DL.load_game_logs()
    prior = DL.load_prior_totals() if args.use_prior_year else {}
    print(f"  PFF players: {len(pff)} | season-total players: {len(totals)}")
    if args.use_prior_year:
        n_with_prior = sum(1 for tot in totals.values() if tot.get("player_id") in prior)
        mode = ("blended with weeks < %d" % args.week if args.week > C.PRIOR_ONLY_UNTIL_WEEK
                else "pure 2024 (no current-season games exist yet to blend)")
        print(f"  --use-prior-year: {len(prior)} players with a 2024 record | "
              f"{n_with_prior}/{len(totals)} of this year's roster matched to one | mode: {mode}")

    lines_by_week = DL.load_game_lines(args.game_lines) if args.game_lines else {}
    week_avg_implied = DL.league_avg_implied(lines_by_week, str(args.week)) if lines_by_week else None
    if args.game_lines:
        n_lines = len(lines_by_week.get(str(args.week), []))
        print(f"  --game-lines: {n_lines} games loaded for week {args.week}"
              + (f" | league avg implied total: {week_avg_implied:.1f}" if week_avg_implied else " | none for this week"))

    team_ratings = DL.load_team_ratings(args.team_ratings) if args.team_ratings else {}
    sr_index = P.build_success_rate_index(team_ratings) if team_ratings else {}
    if args.team_ratings:
        print(f"  --team-ratings: {len(team_ratings)} teams loaded")

    team_grades = DL.load_team_grades(args.team_grades) if args.team_grades else {}
    grade_index = P.build_matchup_grade_index(team_grades) if team_grades else {}
    if args.team_grades:
        print(f"  --team-grades: {len(team_grades)} teams loaded")

    # Precompute league means + defensive index once. In prior-year mode, use
    # 2024-wide means so shrinkage targets are internally consistent with the
    # 2024 rates being shrunk toward them.
    pos_means = P.position_means(prior if (args.use_prior_year and prior) else totals)
    def_index = P.build_def_index(pff)
    print(f"  Defensive team index built for {len(def_index)} teams")

    # Slate / opponents
    events = [] if args.no_odds else O.pull_events()
    print(f"  Slate events: {len(events)}")

    # Index PFF grades by (pkey, tkey) so we can attach them to each projection.
    pff_by_key = {}
    for p in pff:
        pff_by_key.setdefault((p["pkey"], p["tkey"]), p)

    # ---------------- build the master projection table ----------------
    rows = []
    for (pkey, tkey), tot in totals.items():
        opp_tkey, game_id = resolve_opponent(tkey, events, odds2c)
        if opp_tkey is None and not args.no_odds:
            continue  # not playing this slate
        # source: real 2024 rates when available and requested, else this
        # year's own totals. Roster/team identity always comes from tot
        # (current, 2025) regardless -- only the volume/efficiency numbers
        # swap, so a transfer's history follows the player, not the school.
        source = None
        if args.use_prior_year:
            prior_rec = prior.get(tot.get("player_id"))
            if args.week > C.PRIOR_ONLY_UNTIL_WEEK:
                # week 4+: blend with this season's own games-to-date (weeks
                # < args.week only, so no lookahead) -- legitimate even for a
                # player with no 2024 record (prior_rec=None blends to pure
                # current-to-date, still no lookahead).
                current_games = [g for g in logs.get((pkey, tkey), [])
                                 if g.get("week") is not None and g["week"] < args.week]
                source = P.blend_prior_and_current(prior_rec, current_games)
            else:
                # weeks 1-3: no current-season signal exists yet to blend in,
                # so real 2024 is the only non-lookahead option; a player with
                # no 2024 record (true freshman) has no legitimate signal at
                # all here and falls back to this year's full totals.
                source = prior_rec
        if source is None:
            source = tot
        rates = P.compute_player_rates(source)
        rates_shrunk = {k: P.shrink(rates.get(k), pos_means.get(k, 0.0), source.get("games"))
                        for k in ("ypa", "ypc", "ypt", "catch_rate")}
        grades = pff_by_key.get((pkey, tkey), {})

        team_implied, team_spread = (DL.find_team_game_line(tkey, str(args.week), lines_by_week)
                                     if lines_by_week else (None, None))

        for mkey, mdef in C.MARKETS.items():
            vol_adj = P.game_context_adj(team_implied, week_avg_implied, team_spread, mdef["side"])
            extra_adj = P.success_rate_adj(sr_index, opp_tkey, mdef["side"], mdef["stat"]) if sr_index else 1.0
            if grade_index:
                extra_adj *= P.matchup_grade_adj(grade_index, tkey, opp_tkey, mkey)
            proj = P.project_player_market(source, logs.get((pkey, tkey)),
                                           rates_shrunk, mkey, mdef,
                                           def_index, opp_tkey, vol_adj=vol_adj, extra_adj=extra_adj)
            if proj is None:
                continue
            rows.append(dict(
                player=_orig_name(grades, tot, pkey),
                team=grades.get("team_cfbd", ""),
                position=grades.get("position", ""),
                side=grades.get("side", ""),
                opponent=opp_tkey or "",
                game_id=game_id or "",
                **proj,
                pff_grade=_lead_grade(grades),
            ))

    print(f"  Projection rows: {len(rows)}")

    # ---------------- join Odds API prop lines + edges ----------------
    if not args.no_odds and events:
        prop_rows = O.pull_props(events, list(C.MARKETS.keys()), cap=args.prop_cap)
        cons = {(DL.norm(c["player"]), c["market"]): c
                for c in O.consensus_props(prop_rows)}
        for r in rows:
            key = (DL.norm(r["player"]), r["market"])
            c = cons.get(key)
            if c:
                r["book_line"] = c["book_line"]
                r["over_price"] = c["over_price"]
                r["under_price"] = c["under_price"]
                r["n_books"] = c["n_books"]
                if c["book_line"] is not None:
                    r["edge"] = round(r["projection"] - c["book_line"], 1)
                    r["lean"] = ("Over" if r["edge"] > 0 else
                                 "Under" if r["edge"] < 0 else "Push")
                    thr = C.EDGE_FLAG.get(r["stat"])
                    r["flag"] = bool(thr and abs(r["edge"]) >= thr)

    _write_prop_edges(rows)
    _write_impact_json(rows, args.week)
    print("\nDone.")
    print(f"  {os.path.join(C.OUTPUT_DIR, 'prop_edges.csv')}")
    print(f"  {os.path.join(C.OUTPUT_DIR, 'impact.json')}")


# ---------- small helpers ----------

def _orig_name(grades, tot, pkey):
    return grades.get("name") or pkey


def _lead_grade(grades):
    if not grades:
        return None
    if grades.get("side") == "Offense":
        return grades.get("off_grade_off")
    return grades.get("def_grade_def")


def _write_prop_edges(rows):
    cols = ["player", "team", "position", "opponent", "market", "stat",
            "projection", "proj_sd", "book_line", "edge", "lean", "flag",
            "over_price", "under_price", "n_books", "pff_grade"]
    path = os.path.join(C.OUTPUT_DIR, "prop_edges.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: -abs(x.get("edge") or 0)):
            w.writerow(r)


def _write_impact_json(rows, week):
    """
    Group by player for the impact page: one entry per player carrying all their
    market projections, PFF grades, and any edges. Searchable client-side by
    team / position / game.
    """
    from collections import defaultdict
    by_player = defaultdict(lambda: dict(markets=[]))
    for r in rows:
        key = (r["player"], r["team"])
        e = by_player[key]
        e.update(player=r["player"], team=r["team"], position=r["position"],
                 side=r["side"], opponent=r["opponent"], game_id=r["game_id"],
                 pff_grade=r.get("pff_grade"))
        e["markets"].append({k: r.get(k) for k in
                             ("market", "stat", "projection", "proj_sd",
                              "book_line", "edge", "lean", "flag",
                              "over_price", "under_price", "components")})
    payload = dict(week=week, season=C.SEASON,
                   players=list(by_player.values()))
    path = os.path.join(C.OUTPUT_DIR, "impact.json")
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


if __name__ == "__main__":
    main()
