#!/usr/bin/env python3
"""
pull_live_week.py — pull LIVE (not-yet-played) player props + game lines
for an upcoming week, in the same CSV shape historical_pull.R produces for
past weeks. Run this LOCALLY (this sandbox has no network access to the
Odds API) with ODDS_API_KEY set in your .env.

Why this instead of historical_pull.R: that script calls the Odds API's
HISTORICAL snapshot endpoint, which only has data for odds that have
already closed -- it can't see a game that hasn't been played yet. This
script uses the plain LIVE endpoints (same ones build.py already uses for
--no-odds=False runs), which only show CURRENT, not-yet-closed lines.
Run it as close to kickoff as you want your "closing-ish" snapshot to be;
run it again later in the week if lines move and you want a fresher pull.

Credit-safety mirrors historical_pull.R: --dry-run costs nothing (the
/events endpoint is free) and reports how many games are on the slate;
game lines are ONE cheap call for the whole slate; player props are
per-event (the expensive part) -- use --prop-cap to limit how many games
you pull props for while testing.

Run:
  python3 pull_live_week.py --week 1 --dry-run
  python3 pull_live_week.py --week 1 --prop-cap 5      # test on 5 games
  python3 pull_live_week.py --week 1                   # full slate
"""
import argparse, csv
import config as C
import odds as O


def write_lines_csv(path, rows, week, events_by_id):
    """
    events_by_id: game_id -> event dict (from O.pull_events(), has
    commence_time) -- pull_game_lines() itself doesn't carry a date, and
    the Odds API's /odds endpoint returns the WHOLE upcoming slate, not
    just this week, so without a date a lines file silently mixes weeks
    (a team can appear more than once, e.g. its week-1 AND week-2 games).
    Stamping commence_time here lets anything reading this file filter to
    an actual week by date instead of trusting the --week label alone.
    """
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["game_id", "week", "home_team", "away_team",
                                          "home_spread", "total", "commence_time"])
        w.writeheader()
        for r in rows:
            ev = events_by_id.get(r["game_id"], {})
            w.writerow(dict(game_id=r["game_id"], week=week, home_team=r["home_team"],
                            away_team=r["away_team"], home_spread=r["home_spread"], total=r["total"],
                            commence_time=ev.get("commence_time", "")))


def write_props_csv(path, consensus_rows, events_by_id, week):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["game_id", "week", "home_team", "away_team",
                                          "commence_time", "market", "player", "book_line",
                                          "over_price", "under_price", "n_books"])
        w.writeheader()
        for r in consensus_rows:
            ev = events_by_id.get(r["game_id"], {})
            w.writerow(dict(
                game_id=r["game_id"], week=week, home_team=r["home"], away_team=r["away"],
                commence_time=ev.get("commence_time", ""), market=r["market"], player=r["player"],
                book_line=r["book_line"], over_price=r["over_price"], under_price=r["under_price"],
                n_books=r["n_books"],
            ))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True, help="CFB week number for this slate")
    ap.add_argument("--season", type=int, default=C.SEASON)
    ap.add_argument("--out-props", default=None)
    ap.add_argument("--out-lines", default=None)
    ap.add_argument("--prop-cap", type=int, default=None,
                    help="max games to pull player props for (credit control)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list the slate and exit -- no odds calls, no credits spent")
    args = ap.parse_args()

    out_props = args.out_props or f"hist_props_live_{args.season}wk{args.week}.csv"
    out_lines = args.out_lines or f"hist_lines_live_{args.season}wk{args.week}.csv"

    if not C.ODDS_API_KEY:
        print("ODDS_API_KEY is not set -- add it to .env")
        return

    print("Pulling event list (free) ...")
    events = O.pull_events()
    print(f"  {len(events)} events on the board for {C.ODDS_SPORT}")
    for ev in events[:10]:
        print(f"    {ev['away']} @ {ev['home']}  ({ev['commence_time']})")
    if len(events) > 10:
        print(f"    ... and {len(events) - 10} more")

    if args.dry_run:
        n_prop_events = len(events) if args.prop_cap is None else min(args.prop_cap, len(events))
        print(f"\nDry run only -- nothing pulled. A real run would:")
        print(f"  - 1 call for game lines (spreads+totals), whole slate at once")
        print(f"  - {n_prop_events} calls for player props "
              f"({len(C.MARKETS)} markets each) -- the expensive part")
        print("Run again without --dry-run when ready; watch the printed "
              "'credits remaining' after each call.")
        return

    events_by_id = {ev["game_id"]: ev for ev in events}

    print("\nPulling game lines (spreads + totals, one call for the whole slate) ...")
    lines = O.pull_game_lines()
    print(f"  {len(lines)} games with a spread + total")
    write_lines_csv(out_lines, lines, args.week, events_by_id)
    print(f"  wrote {out_lines}")

    print(f"\nPulling player props ({len(C.MARKETS)} markets/event"
          + (f", capped at {args.prop_cap} events" if args.prop_cap else ", full slate") + ") ...")
    prop_rows = O.pull_props(events, list(C.MARKETS.keys()), cap=args.prop_cap)
    print(f"  {len(prop_rows)} raw quotes")
    consensus = O.consensus_props(prop_rows)
    print(f"  {len(consensus)} (game, market, player) consensus rows")
    write_props_csv(out_props, consensus, events_by_id, args.week)
    print(f"  wrote {out_props}")

    print(f"\nDone. Send {out_props} and {out_lines} back and I'll rebuild "
          f"the Props/Impact/DFS pages against week {args.week}, {args.season}.")


if __name__ == "__main__":
    main()
