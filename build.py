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
    ap.add_argument("--prop-cap", type=int, default=None,
                    help="max games to pull props for (credit control)")
    ap.add_argument("--no-odds", action="store_true",
                    help="build projections without calling the Odds API")
    args = ap.parse_args()

    os.makedirs(C.OUTPUT_DIR, exist_ok=True)

    print("Loading data ...")
    pff2c, odds2c = DL.load_team_map()
    pff = DL.load_pff(pff2c)
    totals = DL.load_season_totals()
    logs = DL.load_game_logs()
    print(f"  PFF players: {len(pff)} | season-total players: {len(totals)}")

    # Precompute league means + defensive index once.
    pos_means = P.position_means(totals)
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
        rates = P.compute_player_rates(tot)
        rates_shrunk = {k: P.shrink(rates.get(k), pos_means.get(k, 0.0), tot.get("games"))
                        for k in ("ypa", "ypc", "ypt", "catch_rate")}
        grades = pff_by_key.get((pkey, tkey), {})

        for mkey, mdef in C.MARKETS.items():
            proj = P.project_player_market(tot, logs.get((pkey, tkey)),
                                           rates_shrunk, mkey, mdef,
                                           def_index, opp_tkey)
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
