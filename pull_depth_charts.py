#!/usr/bin/env python3
"""
pull_depth_charts.py — scrape ourlads.com's NCAA football depth charts for
every FBS team, for use as a starter/role signal in weeks 1-3 (where the
model has nothing but last year's raw per-game rate to go on -- a player
who's now QB1 but was a backup in 2025 won't show that in his box score).

Run LOCALLY -- this sandbox has no network access to ourlads.com. Needs
`requests` (pip install requests if you don't have it).

Output: depth_charts.csv, one row per (team, side, position, depth_rank):
  team, side, position, depth_rank, player_name, class_year, jersey, ourlads_id

Politeness: sequential requests with a delay, a real User-Agent, and a
requests.Session for connection reuse -- ~139 teams at the default delay
takes a few minutes, not a burst.

Run:  python3 pull_depth_charts.py
  or: python3 pull_depth_charts.py --delay 1.5 --out depth_charts.csv
  or: python3 pull_depth_charts.py --team army    (single team, for testing)
"""
import argparse, csv, html, re, sys, time

BASE = "https://www.ourlads.com/ncaa-football-depth-charts/depth-chart"

# (slug, ourlads_team_id, team_name) -- from ourlads' own team-picker
# dropdown, captured 2026-08-29. Re-derive via --refresh-teams if this goes
# stale (a team renames/relocates, a new team gets added, etc).
TEAMS = [
    ("air-force", 89877, "Air Force Falcons"), ("akron", 89900, "Akron Zips"),
    ("alabama", 89923, "Alabama Crimson Tide"), ("appalacian-state", 92913, "Appalachian State Mountaineers"),
    ("arizona", 89946, "Arizona Wildcats"), ("arizona-state", 89969, "Arizona State Sun Devils"),
    ("arkansas", 89992, "Arkansas Razorbacks"), ("arkansas-state", 90015, "Arkansas State Red Wolves"),
    ("army", 90038, "Army Black Knights"), ("auburn", 90061, "Auburn Tigers"),
    ("ball-state", 90084, "Ball State Cardinals"), ("baylor", 90107, "Baylor Bears"),
    ("boise-state", 90130, "Boise State Broncos"), ("boston-college", 90153, "Boston College Eagles"),
    ("bowling-green", 90176, "Bowling Green Falcons"), ("buffalo", 90199, "Buffalo Bulls"),
    ("brigham-young", 90222, "BYU Cougars"), ("california", 90245, "California Golden Bears"),
    ("central-florida", 92200, "Central Florida Knights"), ("central-michigan", 90268, "Central Michigan Chippewas"),
    ("charlotte", 92936, "Charlotte 49ers"), ("cincinnati", 90291, "Cincinnati Bearcats"),
    ("clemson", 90314, "Clemson Tigers"), ("coastal-carolina", 92959, "Coastal Carolina Chanticleers"),
    ("colorado", 90337, "Colorado Buffaloes"), ("colorado-state", 90360, "Colorado State Rams"),
    ("connecticut", 90383, "Connecticut Huskies"), ("delaware", 93097, "Delaware Fightin' Blue Hens"),
    ("duke", 90406, "Duke Blue Devils"), ("east-carolina", 90452, "East Carolina Pirates"),
    ("eastern-michigan", 90429, "Eastern Michigan Eagles"), ("florida", 90498, "Florida Gators"),
    ("florida-atlantic", 90521, "Florida Atlantic Owls"), ("florida-international", 90475, "Florida International Panthers"),
    ("florida-state", 90544, "Florida State Seminoles"), ("fresno-state", 90567, "Fresno State Bulldogs"),
    ("georgia", 90590, "Georgia Bulldogs"), ("georgia-southern", 92890, "Georgia Southern Eagles"),
    ("georgia-state", 92752, "Georgia State Panthers"), ("georgia-tech", 90613, "Georgia Tech Yellow Jackets"),
    ("hawaii", 90636, "Hawaii Rainbow Warriors"), ("houston", 90659, "Houston Cougars"),
    ("illinois", 90705, "Illinois Fighting Illini"), ("indiana", 90728, "Indiana Hoosiers"),
    ("iowa", 90751, "Iowa Hawkeyes"), ("iowa-state", 90774, "Iowa State Cyclones"),
    ("jacksonville-state", 93028, "Jacksonville State Gamecocks"), ("james-madison", 93005, "James Madison Dukes"),
    ("kansas", 90797, "Kansas Jayhawks"), ("kansas-state", 90820, "Kansas State Wildcats"),
    ("kennesaw-state", 93074, "Kennesaw State Owls"), ("kent-state", 90843, "Kent State Golden Flashes"),
    ("kentucky", 90866, "Kentucky Wildcats"), ("liberty", 92982, "Liberty Flames"),
    ("louisiana", 90912, "Louisiana Ragin' Cajuns"), ("louisiana-tech", 90889, "Louisiana Tech Bulldogs"),
    ("louisiana-monroe", 90935, "Louisiana-Monroe Warhawks"), ("louisville", 90958, "Louisville Cardinals"),
    ("lsu", 90981, "LSU Tigers"), ("marshall", 91004, "Marshall Thundering Herd"),
    ("maryland", 91027, "Maryland Terrapins"), ("umass", 92706, "Massachusetts Minutemen"),
    ("memphis", 91050, "Memphis Tigers"), ("miami", 91073, "Miami Hurricanes"),
    ("miami-university", 91096, "Miami (Ohio) RedHawks"), ("michigan", 91119, "Michigan Wolverines"),
    ("michigan-state", 91142, "Michigan State Spartans"), ("middle-tennessee", 91165, "Middle Tennessee Blue Raiders"),
    ("minnesota", 91188, "Minnesota Golden Gophers"), ("ole-miss", 91602, "Mississippi Rebels"),
    ("mississippi-state", 91211, "Mississippi State Bulldogs"), ("missouri", 91234, "Missouri Tigers"),
    ("missouri-state", 93120, "Missouri State Bears"), ("navy", 91257, "Navy Midshipmen"),
    ("nebraska", 91303, "Nebraska Cornhuskers"), ("nevada", 91326, "Nevada Wolf Pack"),
    ("new-mexico", 91349, "New Mexico Lobos"), ("new-mexico-state", 91372, "New Mexico State Aggies"),
    ("north-carolina", 91395, "North Carolina Tar Heels"), ("nc-state", 91280, "North Carolina State Wolfpack"),
    ("north-dakota-state", 93143, "North Dakota State Bison"), ("north-texas", 92660, "North Texas Mean Green"),
    ("northern-illinois", 91441, "Northern Illinois Huskies"), ("northwestern", 91464, "Northwestern Wildcats"),
    ("notre-dame", 91487, "Notre Dame Fighting Irish"), ("ohio", 91510, "Ohio Bobcats"),
    ("ohio-state", 91533, "Ohio State Buckeyes"), ("oklahoma", 91556, "Oklahoma Sooners"),
    ("oklahoma-state", 91579, "Oklahoma State Cowboys"), ("old-dominion", 92867, "Old Dominion Monarchs"),
    ("oregon", 91625, "Oregon Ducks"), ("oregon-state", 91648, "Oregon State Beavers"),
    ("penn-state", 91671, "Penn State Nittany Lions"), ("pittsburgh", 91694, "Pittsburgh Panthers"),
    ("purdue", 91717, "Purdue Boilermakers"), ("rice", 91740, "Rice Owls"),
    ("rutgers", 91763, "Rutgers Scarlet Knights"), ("sacramento-state", 93166, "Sacramento State Hornets"),
    ("sam-houston", 93051, "Sam Houston Bearkats"), ("san-diego-state", 91786, "San Diego State Aztecs"),
    ("san-jose-state", 92729, "San Jose State Spartans"), ("smu", 91809, "SMU Mustangs"),
    ("south-alabama", 92798, "South Alabama Jaguars"), ("south-carolina", 91832, "South Carolina Gamecocks"),
    ("south-florida", 91855, "South Florida Bulls"), ("southern-miss", 91878, "Southern Miss Golden Eagles"),
    ("stanford", 91901, "Stanford Cardinal"), ("syracuse", 91924, "Syracuse Orange"),
    ("tcu", 91947, "TCU Horned Frogs"), ("temple", 91970, "Temple Owls"),
    ("tennessee", 91993, "Tennessee Volunteers"), ("texas", 92016, "Texas Longhorns"),
    ("texas-am", 92039, "Texas A&M Aggies"), ("texas-state", 92821, "Texas State Bobcats"),
    ("texas-tech", 92062, "Texas Tech Red Raiders"), ("toledo", 92085, "Toledo Rockets"),
    ("troy", 92108, "Troy Trojans"), ("tulane", 92131, "Tulane Green Wave"),
    ("tulsa", 92154, "Tulsa Golden Hurricane"), ("uab", 92177, "UAB Blazers"),
    ("ucla", 92223, "UCLA Bruins"), ("unlv", 92246, "UNLV Rebels"),
    ("usc", 92269, "USC Trojans"), ("utah", 92292, "Utah Utes"),
    ("utah state", 92315, "Utah State Aggies"), ("utep", 92338, "UTEP Miners"),
    ("utsa", 92683, "UTSA Roadrunners"), ("vanderbilt", 92361, "Vanderbilt Commodores"),
    ("virginia", 92384, "Virginia Cavaliers"), ("virginia-tech", 92407, "Virginia Tech Hokies"),
    ("wake-forest", 92430, "Wake Forest Demon Deacons"), ("washington", 92453, "Washington Huskies"),
    ("washington-state", 92476, "Washington State Cougars"), ("west-virginia", 92499, "West Virginia Mountaineers"),
    ("wku", 92775, "Western Kentucky Hilltoppers"), ("western-michigan", 92522, "Western Michigan Broncos"),
    ("wisconsin", 92545, "Wisconsin Badgers"), ("wyoming", 92568, "Wyoming Cowboys"),
]

SIDES = [("ctl00_phContent_dcTBody", "offense"), ("ctl00_phContent_dcTBody2", "defense"),
         ("ctl00_phContent_dcTBody3", "special_teams")]

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
PLAYER_RE = re.compile(
    r"<a href='https://www\.ourlads\.com/ncaa-football-depth-charts/player/([^/]*)/(\d+)'[^>]*>([^<]*)</a>")


def parse_player_cell(cell_html):
    m = PLAYER_RE.search(cell_html)
    if not m or not m.group(3).strip():
        return None
    slug, pid, label = m.groups()
    label = html.unescape(label.strip())
    # "LastName, FirstName [RS] YR" (YR e.g. SR, JR, SO, FR, SR/TR; RS =
    # redshirt, a separate token BEFORE the class year, not part of the
    # name -- e.g. "Hall, Benjamin RS JR/TR"). Missing this the first time
    # around left "RS" stuck in the middle of ~two-thirds of all names.
    m2 = re.match(r"^(.*?),\s*(\S+(?:\s+\S+)*?)\s+(RS\s+)?([A-Z]{2}(?:/[A-Z]{2})?)$", label)
    if m2:
        last, first, rs, yr = m2.groups()
        name = f"{first} {last}"
        if rs:
            yr = "RS-" + yr
    else:
        name, yr = label, ""
    return dict(name=name, class_year=yr, ourlads_id=pid)


def parse_table(tbody_html):
    rows = []
    for row_html in ROW_RE.findall(tbody_html):
        cells = CELL_RE.findall(row_html)
        if len(cells) < 3:
            continue
        position = re.sub(r"<[^>]+>", "", cells[0]).strip()
        if not position:
            continue
        # cells[1], cells[2] = jersey#, player 1 ; cells[3], cells[4] = jersey#, player 2 ; ...
        depth_rank = 0
        i = 1
        while i + 1 < len(cells):
            jersey = re.sub(r"<[^>]+>", "", cells[i]).strip()
            player = parse_player_cell(cells[i + 1])
            i += 2
            if not player:
                continue
            depth_rank += 1
            yield dict(position=position, depth_rank=depth_rank, jersey=jersey, **player)


def fetch_team(session, slug, team_id, delay):
    url = f"{BASE}/{slug}/{team_id}"
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    time.sleep(delay)
    return resp.text


def parse_team_page(html_text, team_name):
    out = []
    for tbody_id, side in SIDES:
        m = re.search(rf"<tbody id=\"{tbody_id}\"[^>]*>(.*?)</tbody>", html_text, re.S)
        if not m:
            continue
        for row in parse_table(m.group(1)):
            out.append(dict(team=team_name, side=side, **row))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="depth_charts.csv")
    ap.add_argument("--delay", type=float, default=1.2, help="seconds between requests")
    ap.add_argument("--team", default=None, help="single team slug, for testing (e.g. army)")
    args = ap.parse_args()

    try:
        import requests
    except ImportError:
        print("Needs the `requests` package: pip install requests")
        sys.exit(1)

    teams = TEAMS if not args.team else [t for t in TEAMS if t[0] == args.team]
    if not teams:
        print(f"No team matching slug '{args.team}'")
        sys.exit(1)

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; P3S-depth-chart-pull/1.0; personal research use)")

    rows = []
    for i, (slug, team_id, name) in enumerate(teams, 1):
        print(f"[{i}/{len(teams)}] {name} ...")
        try:
            html_text = fetch_team(session, slug, team_id, args.delay)
        except Exception as e:
            print(f"  [warn] failed: {e}")
            continue
        team_rows = parse_team_page(html_text, name)
        print(f"  {len(team_rows)} depth-chart rows")
        rows.extend(team_rows)

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["team", "side", "position", "depth_rank",
                                          "name", "class_year", "jersey", "ourlads_id"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\nWrote {args.out}: {len(rows)} rows across {len(teams)} teams")


if __name__ == "__main__":
    main()
