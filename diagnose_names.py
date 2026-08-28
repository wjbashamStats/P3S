#!/usr/bin/env python3
"""
diagnose_names.py — compare CFBD schedule team names vs Odds API event team names
so we can build a proper crosswalk. Uses ONE cheap historical-events call
(1 credit) per sampled timestamp — does NOT pull odds.
"""
import os, csv, json, datetime as dt, urllib.request, urllib.parse

API_KEY = os.environ.get("ODDS_API_KEY", "")
SPORT = "americanfootball_ncaaf"

def get(url):
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            return json.loads(r.read().decode()), r.headers.get("x-requests-remaining")
    except Exception as e:
        print("err:", e); return None, None

# sample a few week-1 timestamps to collect the API's team-name universe
dates = ["2025-08-23T15:00:00Z", "2025-08-30T18:00:00Z", "2025-08-31T18:00:00Z",
         "2025-09-01T00:00:00Z"]
api_teams = set()
for d in dates:
    q = urllib.parse.urlencode(dict(apiKey=API_KEY, date=d))
    body, rem = get(f"https://api.the-odds-api.com/v4/historical/sports/{SPORT}/events?{q}")
    if body:
        data = body.get("data", body)
        for e in data:
            api_teams.add(e.get("home_team",""))
            api_teams.add(e.get("away_team",""))
    print(f"{d}: collected, credits remaining {rem}")

# schedule team names (FBS)
FBS_CONF = {"SEC","Big Ten","Big 12","ACC","American Athletic","Mountain West",
            "Sun Belt","Conference USA","Mid-American","Pac-12","FBS Independents"}
sched_teams = set()
for r in csv.DictReader(open("2025_schedule.csv", encoding="utf-8-sig")):
    r = {k.strip().strip('"'):v for k,v in r.items()}
    if r.get("Season")!="2025": continue
    for side,conf in [("HomeTeam","HomeConference"),("AwayTeam","AwayConference")]:
        if r.get(conf) in FBS_CONF:
            sched_teams.add(r.get(side,""))

def norm(s): return "".join(c for c in (s or "").lower() if c.isalnum())
api_norm = {norm(t): t for t in api_teams}

print(f"\nAPI teams: {len(api_teams)} | schedule FBS teams: {len(sched_teams)}")
print("\n=== schedule teams with NO normalized match in API ===")
unmatched = sorted(t for t in sched_teams if norm(t) not in api_norm
                   and not any(norm(t) in k or k in norm(t) for k in api_norm))
for t in unmatched:
    print(f"  {t}")
print(f"\n{len(unmatched)} unmatched. Full API team list saved to api_team_names.txt")
open("api_team_names.txt","w").write("\n".join(sorted(api_teams)))
