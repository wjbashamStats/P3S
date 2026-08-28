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
  - No true prior-year data exists in this repo yet (only 2025). The model
    projections used here are built from player_season_totals.csv, which is
    derived from the FULL 2025 season -- including week 1 itself. That's
    lookahead bias: the "prior-year rate" input for week 1 already contains
    week 1's own result. These numbers are a calibration/sanity check on the
    heuristic's shape, not evidence of real predictive edge. A legitimate
    week-1 backtest needs real 2024 prior-year stats.
  - Only the closing snapshot was pulled (PROJECT_STATE.md's scope decision),
    so closing-line value (CLV) isn't computable -- that needs an opening
    snapshot too. This script reports hit rate and calibration only.

Run:  python3 backtest.py --props hist_props_closing_wk1.csv --week 1
"""
import argparse, csv, statistics as stats
from collections import defaultdict

import config as C
import data_load as DL
import project as P


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def build_projections(week):
    """Re-run the same projection logic build.py uses, keyed by (norm(player), market)."""
    pff2c, _ = DL.load_team_map()
    pff = DL.load_pff(pff2c)
    totals = DL.load_season_totals()
    logs = DL.load_game_logs()
    pos_means = P.position_means(totals)
    def_index = P.build_def_index(pff)

    pff_by_key = {}
    for p in pff:
        pff_by_key.setdefault((p["pkey"], p["tkey"]), p)

    out = {}
    for (pkey, tkey), tot in totals.items():
        rates = P.compute_player_rates(tot)
        rates_shrunk = {k: P.shrink(rates.get(k), pos_means.get(k, 0.0), tot.get("games"))
                        for k in ("ypa", "ypc", "ypt", "catch_rate")}
        grades = pff_by_key.get((pkey, tkey), {})
        player_name = grades.get("name") or pkey
        for mkey, mdef in C.MARKETS.items():
            proj = P.project_player_market(tot, logs.get((pkey, tkey)), rates_shrunk,
                                           mkey, mdef, def_index, opp_tkey=None)
            if proj is None:
                continue
            out[(norm(player_name), mkey)] = dict(player=player_name, **proj)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--props", required=True, help="flattened closing-line props CSV")
    ap.add_argument("--week", type=int, required=True)
    args = ap.parse_args()

    print(f"Building week-{args.week} projections ...")
    projections = build_projections(args.week)
    print(f"  {len(projections)} (player, market) projections")

    print("Loading actuals ...")
    actuals = load_actuals(args.week)
    print(f"  {len(actuals)} players with a week-{args.week} game log")

    print(f"Loading props from {args.props} ...")
    props = load_props(args.props)
    props = [r for r in props if str(r.get("week")) == str(args.week)]
    print(f"  {len(props)} prop rows for week {args.week}")

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
            player=r["player"], week=args.week, market=market, stat=mdef["stat"],
            projection=proj["projection"], book_line=book_line, actual=actual_val,
            edge=edge, lean=lean, flagged=flagged, hit=hit, n_books=r.get("n_books"),
        ))

    print(f"\nJoined {len(rows)} rows "
          f"(unmatched: {unmatched_proj} no model projection, {unmatched_actual} no actual result)")

    _write_joined(rows)
    _report(rows)


def _write_joined(rows):
    cols = ["player", "week", "market", "stat", "projection", "book_line",
            "actual", "edge", "lean", "flagged", "hit", "n_books"]
    with open("backtest_week1.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("Wrote backtest_week1.csv")


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
