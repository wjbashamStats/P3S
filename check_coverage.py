#!/usr/bin/env python3
"""Check: (1) what the API calls the 3 unmatched teams, (2) how many week-1
games actually have a matching event at their closing snapshot. Costs ~a few
credits (events calls only, no odds)."""
import os, csv, json, datetime as dt, urllib.request, urllib.parse

API_KEY = os.environ.get("ODDS_API_KEY","")
SPORT="americanfootball_ncaaf"
def get(u):
    try:
        with urllib.request.urlopen(u,timeout=40) as r:
            return json.loads(r.read().decode()), r.headers.get("x-requests-remaining")
    except Exception as e: print("err",e); return None,None

# 1. find the 3 teams in the saved API list
api = [l.strip() for l in open("api_team_names.txt") if l.strip()]
print("=== candidates for the 3 unmatched ===")
for want,hint in [("App State","app"),("Massachusetts","mass"),("San José State","jose")]:
    hits=[t for t in api if hint in t.lower().replace("é","e")]
    print(f"  {want:18s} -> {hits}")

# 2. coverage: for each week-1 FBS game, is there an event at closing snapshot?
FBS={"SEC","Big Ten","Big 12","ACC","American Athletic","Mountain West",
     "Sun Belt","Conference USA","Mid-American","Pac-12","FBS Independents"}
games=[]
for r in csv.DictReader(open("2025_schedule.csv",encoding="utf-8-sig")):
    r={k.strip().strip('"'):v for k,v in r.items()}
    if r.get("Season")!="2025" or r.get("Week")!="1": continue
    if r.get("HomeConference") in FBS and r.get("AwayConference") in FBS:
        st=r.get("StartTime","")
        try: cdt=dt.datetime.fromisoformat(st.replace("Z","+00:00"))
        except: continue
        games.append((cdt,r["HomeTeam"],r["AwayTeam"]))

def norm(s): return "".join(c for c in (s or "").lower().replace("é","e") if c.isalnum())
# cache event lists by snapshot date to avoid repeat calls
snap_cache={}
def events_at(iso):
    if iso in snap_cache: return snap_cache[iso]
    q=urllib.parse.urlencode(dict(apiKey=API_KEY,date=iso))
    body,rem=get(f"https://api.the-odds-api.com/v4/historical/sports/{SPORT}/events?{q}")
    data=(body.get("data",body) if body else []) or []
    snap_cache[iso]=data
    return data

matched=0; nomatch=[]
for cdt,h,a in games:
    iso=(cdt-dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    evs=events_at(iso)
    hit=any((norm(h) in norm(e.get("home_team")) or norm(e.get("home_team")) in norm(h))
            and (norm(a) in norm(e.get("away_team")) or norm(e.get("away_team")) in norm(a))
            for e in evs)
    if hit: matched+=1
    else: nomatch.append((h,a,iso,len(evs)))
print(f"\n=== week-1 FBS games: {len(games)} | matched an event: {matched} | no match: {len(nomatch)} ===")
for h,a,iso,ne in nomatch[:25]:
    print(f"  {a} @ {h}  (snapshot {iso}, {ne} events in snapshot)")
