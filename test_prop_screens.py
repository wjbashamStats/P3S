#!/usr/bin/env python3
"""Checks for prop screens 9 and 10 in articles/build/screen_props.py.

Neither screen could be demonstrated against a live board when they were
written: no receiving Under reached them on the week 8 slate, so a run proved
only that nothing crashed. Two checkers in this repo have already shipped bugs
that reported the wrong answer rather than no answer -- a surname matcher that
read "Jr." as a last name, and a rush/receive router that keyed on a capital R
-- so a screen that cannot be seen working gets a test instead of a shrug.

Screen 9 drops yardage Unders. Screen 10 drops a receiving Under whose average
depth of target is at or above --max-under-adot, default 12.0, and only bites
once screen 9 is lifted.

The three receiving Unders the card actually bet are the fixtures, with the
average depths of target they carried: Rico Scott 13.8 (lost 156 against 55.5),
Mazeo Bennett Jr. 7.0 (lost) and Andrew Rappleyea 5.9 (lost). Screen 10 is
expected to catch Scott and only Scott -- that is the limit of the rule and the
test pins it, so nobody later reads the screen as having covered all three.

Run:  python3 test_prop_screens.py
"""
import sys

MAX_UNDER_ADOT = 12.0


def fails_for(edge, stat, adot, allow_unders, max_under_adot=MAX_UNDER_ADOT):
    """Screens 9 and 10 exactly as screen_props.py applies them."""
    fails = []
    if edge < 0 and not allow_unders:
        fails.append("under")
    # screen 10 only when screen 9 is lifted, so a blocked row reports the one
    # reason actually deciding it
    if edge < 0 and stat == "rec_yds" and allow_unders:
        if adot is not None and float(adot) >= max_under_adot:
            fails.append(f"under aDOT {float(adot):.1f}>={max_under_adot:g}")
    return fails


CASES = [
    # (label, edge, stat, aDOT, allow_unders, expect_blocked_by)
    ("Over is untouched by either screen",        +41.1, "rec_yds", 17.0, False, []),
    ("Over with a high aDOT still passes",        +30.7, "rec_yds", 15.5, False, []),
    ("Under blocked by screen 9 by default",      -41.1, "rec_yds", 13.8, False, ["under"]),
    ("rushing Under blocked by screen 9 too",     -25.0, "rush_yds", None, False, ["under"]),
    ("Rico Scott 13.8: screen 10 catches him",    -41.1, "rec_yds", 13.8, True,  ["aDOT"]),
    ("Bennett 7.0: screen 10 lets him through",   -30.4, "rec_yds",  7.0, True,  []),
    ("Rappleyea 5.9: screen 10 lets him through", -48.5, "rec_yds",  5.9, True,  []),
    ("exactly at the threshold is blocked",       -20.0, "rec_yds", 12.0, True,  ["aDOT"]),
    ("just under the threshold is not",           -20.0, "rec_yds", 11.9, True,  []),
    ("rushing Under has no aDOT rule",            -25.0, "rush_yds", None, True, []),
    ("a missing aDOT cannot block",               -20.0, "rec_yds", None, True,  []),
]


def main():
    bad = 0
    for label, edge, stat, adot, allow, expect in CASES:
        got = fails_for(edge, stat, adot, allow)
        kinds = ["under" if f == "under" else "aDOT" for f in got]
        ok = kinds == expect
        if not ok:
            bad += 1
        print(f"  {'ok  ' if ok else 'FAIL'} {label:44} -> {kinds or 'passes'}"
              f"{'' if ok else f'   expected {expect or chr(39)+chr(39)}'}")

    # The rule's whole scope, stated as a check rather than a claim: of the
    # three receiving Unders the card bet and lost, screen 10 catches one.
    caught = sum(1 for adot in (13.8, 7.0, 5.9)
                 if fails_for(-30.0, "rec_yds", adot, True))
    ok = caught == 1
    bad += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} screen 10 catches {caught} of the 3 losing receiving Unders"
          f"{'' if ok else ' (expected 1)'}")

    print(f"\n{'all checks passed' if not bad else f'{bad} FAILURES'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
