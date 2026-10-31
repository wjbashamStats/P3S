#!/usr/bin/env python3
"""Checks for the depth-chart name matcher in check_card_conditions.py.

This matcher has now broken twice, both times silently:

  week 8  it took name.split()[-1] as the surname, so "Kevin Roche Jr."
          matched on "Jr." and reported a 4th-string tight end as a
          1st-string left guard.
  week 9  ourlads changed its format from "Kevin Roche Jr." to
          "Roche Jr., Kevin", and every lookup became NOT ON THE CHART --
          eight of eight on the first run.

The second failure was safe, in that it flagged rather than passed, but it
would have emptied the card. The first was not safe at all. A matcher with
that record gets its own checks, and both historical formats are pinned here
so a third change is caught by a test run rather than on a Saturday morning.

Run:  python3 test_depth_chart_names.py
"""
import csv
import io
import sys

sys.path.insert(0, "/home/user/P3S")
from check_card_conditions import match_player, normalize_name, surname

NAMES = [
    # (as written somewhere, normalized, surname)
    ("Caleb Hawkins",      "Caleb Hawkins",      "Hawkins"),
    ("Hawkins, Caleb",     "Caleb Hawkins",      "Hawkins"),
    ("Kevin Roche Jr.",    "Kevin Roche Jr.",    "Roche"),
    ("Roche Jr., Kevin",   "Kevin Roche Jr.",    "Roche"),
    ("Harris II, Rodney",  "Rodney Harris II",   "Harris"),
    ("Mosley V, Emmett",   "Emmett Mosley V",    "Mosley"),
    ("Williams, J'Koby",   "J'Koby Williams",    "Williams"),
    ("  Small,   Ed  ",    "Ed Small",           "Small"),
]

CHART = """team,side,position,depth_rank,name,class_year,jersey,ourlads_id
X,offense,RB,1,"Hawkins, Caleb",,24,1
X,offense,RB,2,"Hawkins, Darius",,25,2
X,offense,TE,4,"Roche Jr., Kevin",,86,3
X,offense,LG,1,"Peay Jr., Kevin",,52,4
X,offense,WR-SL,1,"Small, Ed",,18,5
X,defense,CB,1,"Small, Ed",,18,6
"""


def main():
    bad = 0
    for raw, want_norm, want_last in NAMES:
        n, l = normalize_name(raw), surname(raw)
        ok = (n == want_norm and l == want_last)
        bad += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {raw!r:22} -> {n!r:22} surname {l!r}"
              f"{'' if ok else f'   expected {want_norm!r} / {want_last!r}'}")

    rows = list(csv.DictReader(io.StringIO(CHART)))

    cases = [
        # (lookup, expected position, expected depth, note)
        ("Caleb Hawkins", "RB", "1", "exact match beats the surname twin"),
        ("Kevin Roche Jr.", "TE", "4", "the Jr. bug: must NOT match Kevin Peay Jr."),
        ("Ed Small", "WR-SL", "1", "defense rows are ignored"),
    ]
    for name, pos, depth, note in cases:
        hits = match_player(name, rows)
        ok = len(hits) == 1 and hits[0]["position"] == pos and hits[0]["depth_rank"] == depth
        bad += not ok
        got = [(h["position"], h["depth_rank"]) for h in hits]
        print(f"  {'ok  ' if ok else 'FAIL'} {name:18} -> {got}   {note}")

    # Two players share a surname and neither initial narrows to one: the
    # caller must be told, not handed a guess.
    hits = match_player("Hawkins", rows)
    ok = len(hits) == 2
    bad += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} bare surname stays ambiguous ({len(hits)} rows), never guessed")

    print(f"\n{'all checks passed' if not bad else f'{bad} FAILURES'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
