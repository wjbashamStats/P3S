#!/usr/bin/env python3
"""check_card_conditions.py -- the two pre-kickoff checks the card's own data
cannot make: is every prop player still a listed starter, and what is the
weather at each venue at kickoff.

    python3 check_card_conditions.py --week 7

Reads articles/build/content.json, so it checks the card as built rather than
a list retyped by hand.

Why this exists. The eight prop screens include an availability test, but it
only compares a player's game count against his team's, so it catches a player
who has already missed time and cannot see a scratch announced this morning.
Week 5 lost a prop to exactly that: Adam Mohammed's screen was clean at posting
time, California played, he did not, and it graded as a void. A depth chart
pulled the morning of the game is the closest thing to a real answer.

Sources, both free and keyless:

  ourlads.com       depth charts, via pull_depth_charts.py. A player listed
                    second or third at his position on the morning of the game
                    is the signal; he may still play, but the role the
                    projection assumed is gone.
  api.weather.gov   hourly forecast at the venue, matched to kickoff. NWS only
                    covers the United States, which is every FBS venue except
                    Hawaii.

ESPN is deliberately not used for injuries. Its college-football injury feed
returns zero rows for every team tested -- 24 on the week 7 card plus five
others -- so an empty result there means the feed is empty, not that the team
is healthy. Reporting that as a clean bill of health would be worse than not
checking.

Venue coordinates are kept here rather than looked up: ESPN's venue records
carry a city but no latitude or longitude, and stadiums do not move. Each
lookup prints the city NWS resolved the coordinate to, so a wrong one is
visible rather than silent.
"""
import argparse, csv, datetime as dt, json, os, re, subprocess, sys, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "P3S-card-conditions"}
ET = dt.timezone(dt.timedelta(hours=-4))

# stadium -> (lat, lon). The city NWS returns is printed so a bad pair shows up.
VENUES = {
    # week 7
    "Buffalo": (43.0005, -78.7895), "BYU": (40.2577, -111.6546),
    "LSU": (30.4119, -91.1839), "Ole Miss": (34.3617, -89.5346),
    "Wyoming": (41.3114, -105.5690), "UCLA": (34.1613, -118.1676),
    "Oregon": (44.0582, -123.0681), "Houston": (29.7216, -95.3496),
    "Virginia Tech": (37.2199, -80.4184), "West Virginia": (39.6494, -79.9550),
    "Oregon State": (44.5593, -123.2820), "Michigan": (42.2658, -83.7487),
    # week 8
    "Clemson": (34.6788, -82.8432), "Mississippi State": (33.4560, -88.7940),
    "South Carolina": (33.9731, -81.0193), "Toledo": (41.6586, -83.6079),
    "Georgia Tech": (33.7725, -84.3928), "Auburn": (32.6025, -85.4892),
    "Oklahoma State": (36.1269, -97.0655), "Kansas": (38.9631, -95.2459),
    "Alabama": (33.2083, -87.5504),
}

# PFF team name -> ourlads slug, for the teams a prop can name
SLUGS = {
    "W VIRGINIA": "west-virginia", "LSU": "lsu", "OREGON ST": "oregon-state",
    "PENN STATE": "penn-state", "OLE MISS": "ole-miss", "MISS STATE": "mississippi-state",
    "MICHIGAN": "michigan", "HOUSTON": "houston", "OKLA STATE": "oklahoma-state",
    "GA TECH": "georgia-tech", "INDIANA": "indiana", "BAYLOR": "baylor",
    "ALABAMA": "alabama", "KANSAS": "kansas", "COLORADO": "colorado",
    "BOSTON COL": "boston-college", "AUBURN": "auburn",
}

WIND_WARN = 20          # mph: below this, passing and kicking are not meaningfully affected
PRECIP_WARN = 50        # percent


SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


def surname(full):
    """The last name, ignoring a generational suffix.

    'Kevin Roche Jr.'.split()[-1] is 'Jr.', and matching that against a depth
    chart hits every other Jr. on the roster. That bug reported a tight end
    listed 4th as a 1st-string left guard, which is the opposite of what this
    tool exists to do, so the suffix comes off before anything is compared.
    """
    parts = [w for w in full.replace(",", " ").split() if w.strip()]
    while len(parts) > 1 and parts[-1].lower().strip(".") in {s.strip(".") for s in SUFFIXES}:
        parts.pop()
    return parts[-1] if parts else full


def match_player(name, rows):
    """Offensive depth-chart rows for this player, most specific match first.

    An exact full-name match wins outright. Failing that, a surname match is
    narrowed by first initial, because two players on one roster can share a
    surname. Anything still ambiguous is returned in full so the caller can
    report it rather than silently pick one.
    """
    off = [r for r in rows if r["side"] == "offense"]
    exact = [r for r in off if r["name"].strip().lower() == name.strip().lower()]
    if exact:
        return exact
    ln, fi = surname(name).lower(), name.strip()[:1].lower()
    by_last = [r for r in off if surname(r["name"]).lower() == ln]
    if len(by_last) > 1:
        narrowed = [r for r in by_last if r["name"].strip()[:1].lower() == fi]
        if narrowed:
            return narrowed
    return by_last


def depth_above(rows, row):
    """Who is listed ahead of this player at his position."""
    same = [r for r in rows if r["position"] == row["position"] and r["side"] == row["side"]
            and r["depth_rank"].isdigit() and int(r["depth_rank"]) < int(row["depth_rank"])]
    same.sort(key=lambda r: int(r["depth_rank"]))
    return ", ".join(r["name"] for r in same) or "nobody listed"


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))


def player_team(name, season=2026):
    """Find a prop player's PFF row so the depth chart is pulled for the right team."""
    for kind in ("receiving", "rushing"):
        path = os.path.join(ROOT, f"{season}_{kind}_season_clean.csv")
        for r in csv.DictReader(open(path, newline="", encoding="utf-8-sig")):
            if r["player"] == name:
                return r["team_name"], kind
    return None, None


def check_starters(content, scratch):
    print("\n--- prop players against this morning's depth chart ---")
    bad = 0
    for it in content["props"]:
        name = re.split(r"\s+(?:Over|Under)\s", it["pick"])[0].strip()
        team, _ = player_team(name)
        if team is None:
            print(f"  FAIL {name:22} not in the PFF files"); bad += 1; continue
        slug = SLUGS.get(team)
        if slug is None:
            print(f"  --   {name:22} no ourlads slug for {team!r}; add one to SLUGS"); continue
        out = os.path.join(scratch, f"dc_{slug}.csv")
        if not os.path.exists(out):
            subprocess.run([sys.executable, os.path.join(ROOT, "pull_depth_charts.py"),
                            "--team", slug, "--out", out, "--delay", "1.0"],
                           check=True, capture_output=True)
        rows = list(csv.DictReader(open(out)))
        hits = match_player(name, rows)
        if not hits:
            print(f"  FAIL {name:22} NOT ON THE DEPTH CHART at {team}"); bad += 1; continue
        if len(hits) > 1:
            print(f"  WARN {name:22} matches {len(hits)} rows: "
                  + "; ".join(f"{r['position']} {r['depth_rank']} {r['name']}" for r in hits))
            bad += 1
            continue
        row = hits[0]
        alias = "" if row["name"].lower() == name.lower() else f"  (listed as {row['name']})"
        if row["depth_rank"] == "1":
            print(f"  ok   {name:22} {row['position']:8} 1st string, #{row['jersey']}{alias}")
        else:
            print(f"  WARN {name:22} {row['position']:8} listed {row['depth_rank']} deep"
                  f", behind {depth_above(rows, row)}{alias}")
            bad += 1
    return bad


def check_weather(content, board):
    print("\n--- kickoff weather, from the National Weather Service ---")
    seen, bad = set(), 0
    # a card may omit a whole category -- week 8 ran no totals
    for sec in ("spreads", "totals", "props"):
        for it in content.get(sec, []):
            away, home = [s.strip() for s in it["game"].split(" @ ")]
            # longest key first: "Oregon State Beavers" must not match "Oregon"
            key = next((k for k in sorted(VENUES, key=len, reverse=True)
                        if home.startswith(k) or k in home), None)
            if key is None:
                print(f"  --   {it['game'][:46]:46} no venue coordinates; add {home!r} to VENUES")
                continue
            if key in seen:
                continue
            seen.add(key)
            g = board.get((away, home))
            kick = dt.datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00")) if g else None
            lat, lon = VENUES[key]
            try:
                pts = get(f"https://api.weather.gov/points/{lat},{lon}")
                city = pts["properties"]["relativeLocation"]["properties"]["city"]
                fc = get(pts["properties"]["forecastHourly"])
                p = min(fc["properties"]["periods"],
                        key=lambda q: abs(dt.datetime.fromisoformat(q["startTime"]) - kick)) if kick \
                    else fc["properties"]["periods"][0]
            except Exception as ex:
                print(f"  FAIL {key:16} lookup failed: {type(ex).__name__}: {ex}"); bad += 1; continue
            mph = int(re.search(r"\d+", p["windSpeed"]).group())
            pop = p["probabilityOfPrecipitation"]["value"] or 0
            flag = "WARN" if (mph >= WIND_WARN or pop >= PRECIP_WARN) else "ok  "
            if flag.strip() == "WARN":
                bad += 1
            when = f"{kick.astimezone(ET):%a %H:%M ET}" if kick else "kickoff unknown"
            print(f"  {flag} {key:16} {when}  [{city}]  {p['temperature']}F  "
                  f"wind {mph} mph {p['windDirection']}  precip {pop}%  {p['shortForecast']}")
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--scratch", default=os.path.join(ROOT, ".conditions_cache"))
    args = ap.parse_args()
    os.makedirs(args.scratch, exist_ok=True)

    content = json.load(open(os.path.join(ROOT, "articles", "build", "content.json")))
    board = {(g["away_team"], g["home_team"]): g
             for g in json.load(open(os.path.join(
                 ROOT, f"diversions_{args.season}wk{args.week}.json")))["games"]}
    # the card writes display names; the board uses full ones
    board.update({(k[0].split()[0], k[1]): v for k, v in list(board.items())})
    board.update({(" ".join(k[0].split()[:-1]) or k[0], " ".join(k[1].split()[:-1]) or k[1]): v
                  for k, v in list(board.items())})

    bad = check_starters(content, args.scratch) + check_weather(content, board)
    print("\n" + "=" * 64)
    print("nothing to act on" if not bad else f"{bad} thing(s) to look at before kickoff")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
