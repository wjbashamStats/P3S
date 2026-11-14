"""Pins the venue-key matcher. A bare prefix match once put a San Marcos
kickoff in Austin and printed a forecast for the wrong stadium."""
import sys
sys.path.insert(0, ".")
from check_card_conditions import venue_key_matches as m

CASES = [
    # key,                home team,                      expected
    ("Texas",             "Texas Longhorns",              True),
    ("Texas",             "Texas State Bobcats",          False),
    ("Texas",             "Texas Tech Red Raiders",       False),
    ("Texas State",       "Texas State Bobcats",          True),
    ("Washington",        "Washington Huskies",           True),
    ("Washington",        "Washington State Cougars",     False),
    ("Washington State",  "Washington State Cougars",     True),
    ("Miami",             "Miami Hurricanes",             True),
    ("Michigan",          "Michigan State Spartans",      False),
    ("NC State",          "NC State Wolfpack",            True),
    ("TCU",               "TCU Horned Frogs",             True),
    ("Mississippi State", "Mississippi State Bulldogs",   True),
    ("Syracuse",          "Syracuse Orange",              True),
    ("Oregon",            "Oregon State Beavers",         False),
    ("Fresno State",      "Fresno State Bulldogs",        True),
    # not a prefix at all
    ("LSU",               "TCU Horned Frogs",             False),
    # exact match with no mascot
    ("TCU",               "TCU",                          True),
]

fails = 0
for key, home, want in CASES:
    got = m(key, home)
    if got != want:
        print(f"  FAIL {key!r} vs {home!r}: got {got}, want {want}")
        fails += 1
print(f"  venue key match: {len(CASES)-fails}/{len(CASES)} checks passed")
print("PASS" if not fails else "FAIL")
sys.exit(1 if fails else 0)
