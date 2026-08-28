#!/usr/bin/env python3
"""
build_pff_team_map.py — one-off: derive pff_team_map.csv (pff_team,cfbd_team)
by matching master_crosswalk.csv's PFF-abbreviated team strings ("APP
STATE", "S JOSE ST", "GA TECH") against a CFBD-style team list. Needed
because those two naming conventions routinely don't share a normalized
substring relationship, and even where they do, it's often ambiguous
(e.g. "ARIZONA ST" normalizes to a substring of BOTH "Arizona" and
"Arizona State" -- guessing wrong here silently misattributes a team's
data). Explicit aliases below were verified against the actual target
team list, not guessed.

Regenerate if master_crosswalk.csv's team roster changes:
  python3 build_pff_team_map.py path/to/some_cfbd_team_list.csv
(the second file just needs a "Team" column of CFBD-style names; any
file with a full FBS team list works, e.g. a CFBD team-ratings export.)
"""
import csv, sys

def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())

# Hand-verified aliases for every PFF team string that doesn't exactly
# equal (case/spacing aside) a target team name. Deliberately NOT using
# fuzzy substring matching for anything beyond exact match -- an earlier
# version of this script did, and it silently merged real, DIFFERENT
# teams: "S ALABAMA" -> Alabama, "W VIRGINIA" -> Virginia, "N TEXAS" ->
# Texas, "SM HOUSTON" -> Houston, "W KENTUCKY" -> Kentucky, and all
# three of C/E/W MICHIGAN -> Michigan (a short team name that happens to
# be a substring of a compass-direction-prefixed one is a common trap,
# not an edge case). Every non-exact-match team must be listed here,
# checked against the real target list -- no guessing.
EXPLICIT = {
    "APP STATE": "Appalachian State", "ARIZONA ST": "Arizona State",
    "ARK STATE": "Arkansas State", "BALL ST": "Ball State",
    "BOISE ST": "Boise State", "BOSTON COL": "Boston College",
    "BOWL GREEN": "Bowling Green", "C MICHIGAN": "Central Michigan",
    "CAL": "California", "COAST CAR": "Coastal Carolina",
    "COLO STATE": "Colorado State", "DOMINION": "Old Dominion",
    "E CAROLINA": "East Carolina", "E MICHIGAN": "Eastern Michigan",
    "FAU": "Florida Atlantic", "FIU": "Florida International",
    "FLORIDA ST": "Florida State", "FRESNO ST": "Fresno State",
    "GA SOUTHRN": "Georgia Southern", "GA STATE": "Georgia State",
    "GA TECH": "Georgia Tech", "JAMES MAD": "James Madison",
    "JVILLE ST": "Jacksonville State", "KANSAS ST": "Kansas State",
    "KENNESAW": "Kennesaw State", "LA LAFAYET": "Louisiana",
    "LA MONROE": "ULM", "LA TECH": "Louisiana Tech",
    "MIAMI FL": "Miami", "MIAMI OH": "Miami Ohio",
    "MICH STATE": "Michigan State", "MIDDLE TN": "Middle Tennessee",
    "MISS STATE": "Mississippi State", "MO STATE": "Missouri State",
    "N CAROLINA": "North Carolina", "N ILLINOIS": "Northern Illinois",
    "N TEXAS": "North Texas", "NEW MEX ST": "New Mexico State",
    "NORTHWESTN": "Northwestern", "OKLA STATE": "Oklahoma State",
    "OREGON ST": "Oregon State", "S ALABAMA": "South Alabama",
    "S CAROLINA": "South Carolina", "S DIEGO ST": "San Diego State",
    "S JOSE ST": "San Jose State", "SM HOUSTON": "Sam Houston",
    "SO MISS": "Southern Miss", "TEXAS ST": "Texas State",
    "USF": "South Florida", "UTAH ST": "Utah State",
    "VA TECH": "Virginia Tech", "W KENTUCKY": "Western Kentucky",
    "W MICHIGAN": "Western Michigan", "W VIRGINIA": "West Virginia",
    "WAKE": "Wake Forest", "WASH STATE": "Washington State",
    # NWESTERN has no confirmed target -- master_crosswalk.csv has both
    # "NWESTERN" and "NORTHWESTN" as distinct team strings (137 unique
    # teams vs 136 real FBS programs), which looks like a data artifact
    # (a scraping/labeling error for a subset of players) rather than two
    # real teams. Left unmapped rather than guessed; those specific
    # players' rows won't get the ratings signal until this is resolved
    # by checking master_crosswalk.csv's source export directly.
}


def build(target_csv, out_path="pff_team_map.csv"):
    cw_teams = sorted(set(r["team"] for r in csv.DictReader(open("master_crosswalk.csv"))))
    targets = [r["Team"] for r in csv.DictReader(open(target_csv))]
    t_norm = {norm(t): t for t in targets}

    # Exact match or EXPLICIT only -- no fuzzy substring fallback. A short
    # team name is routinely a substring of an unrelated, longer one
    # (Michigan/W Michigan, Houston/Sam Houston, Alabama/South Alabama),
    # so "matches as a substring" is not evidence of being the same team.
    rows, unresolved = [], []
    for t in cw_teams:
        if t in EXPLICIT:
            rows.append((t, EXPLICIT[t])); continue
        n = norm(t)
        if n in t_norm:
            rows.append((t, t_norm[n])); continue
        unresolved.append(t)

    print(f"resolved: {len(rows)}/{len(cw_teams)}")
    if unresolved:
        print(f"  unresolved (add to EXPLICIT, verified against the real target list): {unresolved}")

    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pff_team", "cfbd_team"])
        w.writerows(sorted(rows))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 build_pff_team_map.py <csv with a 'Team' column of CFBD-style names>")
        sys.exit(1)
    build(sys.argv[1])
