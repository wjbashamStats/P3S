#!/usr/bin/env python3
"""
pull_futures.py — pull season-long futures odds (national championship,
conference winners, team win totals) from The Odds API. Run this LOCALLY
(this sandbox has no network access to the Odds API -- confirmed: even the
docs site at the-odds-api.com is blocked here, not just the API path) with
ODDS_API_KEY set in your .env.

UNTESTED from my side, by necessity -- I can't reach The Odds API to
confirm exact sport keys, so this is written from their documented
conventions (each futures market is its OWN sport key, separate from
americanfootball_ncaaf -- e.g. NFL's Super Bowl futures live under
americanfootball_nfl_super_bowl_winner) rather than verified against a
live response. Team win totals in particular may not be offered as a
structured outrights market at all -- I'm not certain The Odds API carries
that market for college football.

Start with --discover: a free call (doesn't touch your odds-call quota)
that lists every sport key currently offered, including futures-only ones.
Send me its output and I'll wire up whichever keys actually exist --
--sport-key below is a placeholder param, not a confirmed working value.

Run:
  python3 pull_futures.py --discover                              # free, start here
  python3 pull_futures.py --sport-key <key> --dry-run              # see what a market has
  python3 pull_futures.py --sport-key <key> --out futures_<key>.csv
"""
import argparse, csv
import config as C
import odds as O


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--discover", action="store_true",
                    help="list every sport key The Odds API currently offers (free) and exit -- "
                         "look for NCAAF-related keys beyond the main americanfootball_ncaaf one")
    ap.add_argument("--sport-key", default=None,
                    help="a futures sport key found via --discover, e.g. "
                         "americanfootball_ncaaf_championship_winner")
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and print what the market returns, don't write a file")
    args = ap.parse_args()

    if not C.ODDS_API_KEY:
        print("ODDS_API_KEY is not set -- add it to .env")
        return

    if args.discover:
        print("Fetching full sport list (free call) ...")
        sports = O.pull_sports(all_sports=True)
        print(f"  {len(sports)} total sport keys returned")
        ncaaf = [s for s in sports if "ncaa" in s.get("key", "").lower()
                 or "college" in s.get("title", "").lower()
                 or "ncaaf" in s.get("group", "").lower()]
        print(f"\n{len(ncaaf)} college-football-related sport keys:")
        for s in ncaaf:
            print(f"  {s['key']:50s} {s.get('title',''):35s} active={s.get('active')}")
        if not ncaaf:
            print("  (none found by name filter -- the futures market you want may not "
                  "exist for NCAAF, or use a name this filter missed. Full list has "
                  f"{len(sports)} entries; check it directly if needed.)")
        print("\nPick one of these for --sport-key, then re-run with --dry-run first.")
        return

    if not args.sport_key:
        print("Pass --sport-key (see --discover), or --discover to list options first.")
        return

    print(f"Pulling outrights for {args.sport_key} ...")
    rows = O.pull_outrights(args.sport_key)
    print(f"  {len(rows)} teams/outcomes with a consensus price")
    for r in rows[:15]:
        print(f"    {r['team']:30s} {r['consensus_price']:>8}  ({r['n_books']} books)")
    if len(rows) > 15:
        print(f"    ... and {len(rows) - 15} more")
    if not rows:
        print("  no outrights data -- this sport key may not publish an 'outrights' "
              "market, or the season for it hasn't opened yet")

    if args.dry_run:
        print("\nDry run -- nothing written.")
        return

    out = args.out or f"futures_{args.sport_key}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["team", "consensus_price", "n_books"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {out}")
    print("Send it back and I'll fold it into team_ratings_2025.csv / the team preview page.")


if __name__ == "__main__":
    main()
