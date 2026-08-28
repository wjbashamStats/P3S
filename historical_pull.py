#!/usr/bin/env python3
"""
historical_pull.py — pull 2025 CFB player props from The Odds API historical
endpoint for a season-long backtest.

COST MODEL (from the docs, non-negotiable):
  historical event-odds = 10 credits  x  regions  x  markets  x  event  x  snapshot
  With 6 markets, 1 region, 2 snapshots/game => 120 credits per game.
  ~750 games => ~90,000 credits.

This script is built to NOT waste that budget:
  * --dry-run counts games and prints projected credits BEFORE spending anything.
  * Every response is checkpointed to disk; a completed game is never re-pulled.
    Crash at week 9 -> rerun resumes, doesn't re-spend.
  * A hard CREDIT_CEILING stops the run if projected spend exceeds it.
  * The live x-requests-remaining header is checked after each call; if it drops
    below a floor, the run halts gracefully with progress saved.

WORKFLOW PER WEEK:
  1. historical events endpoint (cheap: 1 credit) -> event ids + commence times
     for a snapshot timestamp near that week's games.
  2. for each event, pull historical event-odds at TWO timestamps:
       - opening : earliest props snapshot (~36h before commence)
       - closing : last snapshot before commence_time
  3. write raw json per (event, snapshot) to disk; flatten later.

Snapshots for CFB props: books post props ~1-2 days out, so "opening" here means
earliest-available near T-36h and "closing" means the snapshot just before kick.
The API returns the closest snapshot <= the requested timestamp.
"""
import os, json, time, argparse, datetime as dt
import urllib.request, urllib.parse, urllib.error

# ----------------- CONFIG -----------------
# Set via .env (gitignored) -- see .env.example. No hardcoded fallback.
API_KEY   = os.environ.get("ODDS_API_KEY")
SPORT     = "americanfootball_ncaaf"
REGION    = "us"
MARKETS   = ["player_pass_yds", "player_pass_attempts",
             "player_rush_yds", "player_rush_attempts",
             "player_reception_yds", "player_receptions"]
ODDS_FMT  = "american"

HIST_COST_PER = 10                      # credits per region per market per event per snapshot
CREDIT_CEILING = 100000                 # hard stop: never let a run exceed this
CREDIT_FLOOR   = 2000                   # halt if remaining drops below this
BASE = "https://api.the-odds-api.com/v4"

CKPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hist_raw")
# Snapshots to pull per game. Closing-only for the first backtest (sharpest
# lines, ~half the cost). Add "opening" back to this tuple for line-movement.
SNAPSHOTS = ("closing",)

# Hours-before-commence to target for each snapshot label.
SNAPSHOT_OFFSETS = {"opening": 36, "closing": 1}


# ----------------- HTTP -----------------
def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            remaining = r.headers.get("x-requests-remaining")
            used = r.headers.get("x-requests-last")
            body = json.loads(r.read().decode())
            return body, (int(remaining) if remaining is not None else None), used
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {e.read().decode()[:200]}")
        return None, None, None
    except Exception as e:
        print(f"    error: {e}")
        return None, None, None


def hist_events(date_iso):
    """Historical events endpoint (cheap) -> list of events at that snapshot."""
    q = urllib.parse.urlencode(dict(apiKey=API_KEY, date=date_iso))
    url = f"{BASE}/historical/sports/{SPORT}/events?{q}"
    body, remaining, _ = _get(url)
    if not body:
        return [], remaining
    data = body.get("data", body) if isinstance(body, dict) else body
    return data, remaining


def hist_event_odds(event_id, date_iso):
    """Historical event-odds for one event at one snapshot (the expensive call)."""
    q = urllib.parse.urlencode(dict(
        apiKey=API_KEY, date=date_iso, regions=REGION,
        markets=",".join(MARKETS), oddsFormat=ODDS_FMT))
    url = f"{BASE}/historical/sports/{SPORT}/events/{event_id}/odds?{q}"
    return _get(url)


# ----------------- CHECKPOINT -----------------
def ckpt_path(event_id, label):
    return os.path.join(CKPT_DIR, f"{event_id}_{label}.json")


def already_have(event_id, label):
    p = ckpt_path(event_id, label)
    return os.path.exists(p) and os.path.getsize(p) > 2


def save_ckpt(event_id, label, payload):
    os.makedirs(CKPT_DIR, exist_ok=True)
    with open(ckpt_path(event_id, label), "w") as f:
        json.dump(payload, f)


# ----------------- SCHEDULE -> SNAPSHOT TIMESTAMPS -----------------
# FBS conferences — props exist essentially only for FBS-vs-FBS games.
FBS_CONF = {"SEC", "Big Ten", "Big 12", "ACC", "American Athletic",
            "Mountain West", "Sun Belt", "Conference USA", "Mid-American",
            "Pac-12", "FBS Independents"}


def load_schedule(sched_csv, season=2025, fbs_only=True, both_fbs=True,
                  season_type="regular"):
    """
    Read the CFBD schedule CSV, return list of (commence_dt, home, away, week).
    fbs_only + both_fbs filter out FCS/lower-div games that carry no props,
    so we don't burn 120 credits/game checking games that return nothing.

    CFBD numbers postseason (bowl/CFP) weeks starting back at 1, distinct
    from the regular season's own Week 1 -- so `--week 1` without a
    SeasonType filter pulls both, more than doubling scope/cost.
    season_type: "regular" (default), "postseason", or "all".
    """
    import csv
    games = []
    seen_ids = set()
    with open(sched_csv, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            r = {k.strip().strip('"'): v for k, v in r.items()}
            gid = r.get("Id")
            if gid is not None:
                if gid in seen_ids:
                    continue  # the schedule export has dup rows per game (one per outlet)
                seen_ids.add(gid)
            if str(r.get("Season")) != str(season):
                continue
            if season_type != "all" and r.get("SeasonType") != season_type:
                continue
            if fbs_only:
                h_fbs = r.get("HomeConference") in FBS_CONF
                a_fbs = r.get("AwayConference") in FBS_CONF
                if both_fbs and not (h_fbs and a_fbs):
                    continue
                if not both_fbs and not (h_fbs or a_fbs):
                    continue
            st = r.get("StartTime", "")
            if not st:
                continue
            try:
                cdt = dt.datetime.fromisoformat(st.replace("Z", "+00:00"))
            except ValueError:
                continue
            games.append((cdt, r.get("HomeTeam", ""), r.get("AwayTeam", ""), r.get("Week", "")))
    return games


def snapshot_iso(commence_dt, label):
    off = SNAPSHOT_OFFSETS[label]
    ts = commence_dt - dt.timedelta(hours=off)
    return ts.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------- MAIN -----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schedule", required=True, help="2025 CFBD schedule CSV")
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--dry-run", action="store_true",
                    help="count games + projected credits, spend nothing")
    ap.add_argument("--max-games", type=int, default=None,
                    help="cap games this run (for staged spending)")
    ap.add_argument("--week", type=int, default=None, help="restrict to one week")
    ap.add_argument("--include-one-fbs", action="store_true",
                    help="include games where only ONE team is FBS (more games, more credits)")
    ap.add_argument("--season-type", default="regular",
                    choices=["regular", "postseason", "all"],
                    help="CFBD SeasonType filter (default: regular). Postseason "
                         "weeks are numbered separately from the regular season's, "
                         "so --week without this pulls both.")
    args = ap.parse_args()

    games = load_schedule(args.schedule, args.season,
                          fbs_only=True, both_fbs=not args.include_one_fbs,
                          season_type=args.season_type)
    if args.week is not None:
        games = [g for g in games if str(g[3]) == str(args.week)]
    games.sort(key=lambda g: g[0])
    if args.max_games:
        games = games[:args.max_games]

    n_games = len(games)
    n_snaps = len(SNAPSHOTS)
    projected = n_games * n_snaps * len(MARKETS) * HIST_COST_PER

    print(f"Season {args.season}: {n_games} games in scope")
    print(f"Markets: {len(MARKETS)} | snapshots/game: {n_snaps} | region: {REGION}")
    print(f"Projected MAX credits (if none cached): "
          f"{n_games} x {n_snaps} x {len(MARKETS)} x {HIST_COST_PER} = {projected:,}")

    # Count snapshot files already on disk. This can't be matched to *this*
    # scope's games without hitting the (cheap) events endpoint to discover
    # event ids first, and dry-run spends zero credits by design -- so it's
    # a general "how much is already checkpointed" figure, not a precise
    # count of what this run would skip.
    cached = 0
    if os.path.isdir(CKPT_DIR):
        cached = sum(1 for fn in os.listdir(CKPT_DIR)
                     if any(fn.endswith(f"_{lbl}.json") for lbl in SNAPSHOTS))
    print(f"Checkpoint dir: {CKPT_DIR} ({cached} snapshot file(s) already on disk)")

    if projected > CREDIT_CEILING:
        print(f"\n*** PROJECTED {projected:,} EXCEEDS CEILING {CREDIT_CEILING:,} ***")
        print("Reduce scope (--max-games or --week) or raise CREDIT_CEILING deliberately.")
        if not args.dry_run:
            return

    if args.dry_run:
        print("\n[dry-run] No credits spent. Re-run without --dry-run to execute.")
        # Show a few sample snapshot timestamps so you can eyeball them
        for cdt, h, a, wk in games[:3]:
            print(f"  wk{wk} {a} @ {h} {cdt.isoformat()}")
            for lbl in SNAPSHOTS:
                print(f"      {lbl:8s} -> {snapshot_iso(cdt, lbl)}")
        return

    # ---- EXECUTE ----
    os.makedirs(CKPT_DIR, exist_ok=True)
    spent_calls = 0
    for i, (cdt, home, away, wk) in enumerate(games, 1):
        # discover event id near this game's closing snapshot
        disc_iso = snapshot_iso(cdt, "closing")
        evs, remaining = hist_events(disc_iso)
        # match our game by team names in the snapshot's event list
        ev = _match_event(evs, home, away)
        if not ev:
            print(f"[{i}/{n_games}] wk{wk} {away}@{home}: no event match at {disc_iso}")
            continue
        eid = ev["id"]

        for lbl in SNAPSHOTS:
            if already_have(eid, lbl):
                continue
            body, remaining, used = hist_event_odds(eid, snapshot_iso(cdt, lbl))
            if body is not None:
                save_ckpt(eid, lbl, body)
                spent_calls += 1
            if remaining is not None and remaining < CREDIT_FLOOR:
                print(f"\n*** remaining credits {remaining} < floor {CREDIT_FLOOR}. "
                      f"Halting with progress saved. ***")
                return
            time.sleep(0.25)

        if i % 10 == 0:
            print(f"[{i}/{n_games}] wk{wk} done | remaining credits: {remaining}")

    print(f"\nComplete. Pulled {spent_calls} new (event,snapshot) odds files into {CKPT_DIR}")


def _norm(s):
    """Normalize for matching: strip accents, lowercase, keep alphanumerics."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))  # drop accents (é->e)
    return "".join(c for c in s.lower() if c.isalnum())


def load_team_map(path="team_map.csv"):
    """cfbd_name -> normalized odds_name, for explicit overrides."""
    import csv, os
    m = {}
    if os.path.exists(path):
        for r in csv.DictReader(open(path, encoding="utf-8-sig")):
            m[_norm(r["cfbd_name"])] = _norm(r["odds_name"])
    return m


_TEAM_MAP = load_team_map()


def _match_event(events, home, away):
    """
    Match a schedule game to an API event by team names.
    Uses accent-stripped normalization + an explicit crosswalk (team_map.csv)
    for names the fuzzy match can't bridge (App State -> Appalachian State, etc.).
    """
    # apply explicit override if present, else normalize the schedule name
    h = _TEAM_MAP.get(_norm(home), _norm(home))
    a = _TEAM_MAP.get(_norm(away), _norm(away))
    for e in events:
        eh, ea = _norm(e.get("home_team")), _norm(e.get("away_team"))
        # match orientation-agnostically: schedule and API sometimes disagree on
        # which team is home (neutral sites, data-entry differences), so accept
        # either arrangement as long as both teams are present.
        fwd = (h in eh or eh in h) and (a in ea or ea in a)
        rev = (h in ea or ea in h) and (a in eh or eh in a)
        if fwd or rev:
            return e
    return None


if __name__ == "__main__":
    main()
