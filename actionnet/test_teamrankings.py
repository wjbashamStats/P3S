#!/usr/bin/env python3
"""Checks for the TeamRankings trends parser and its name resolution.

Two things are verified:

  1. Parsing, against a fixture cut from a real saved page -- HTML entities,
     the data-sort full-precision values, W-L-T splitting, and the team slug.
  2. Name resolution, against the full 138-team slate as the live page spells
     it. This is the part that silently rots: TeamRankings abbreviates, the
     workbook's TeamID column is stale for a handful, and a name that fails to
     resolve drops that team's records without anything looking broken.

Run:  python3 actionnet/test_teamrankings.py [workbook.xlsx]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from teamrankings import TEAMRANKINGS_ALIASES, load_trends          # noqa: E402
from an_metrics import _norm_team                                    # noqa: E402
from xlsx_read import Workbook, to_str                               # noqa: E402

# Every team name as the trends table rendered it on 2026-09-18.
SLATE = """Tulsa|SMU|Notre Dame|Vanderbilt|Georgia|South Carolina|Florida|Tennessee|LSU|Alabama|Auburn|
Mississippi|Mississippi St|Indiana|Northwestern|Michigan St|Michigan|Penn St|Iowa|Kansas St|Missouri|
Colorado|Nebraska|Texas|Texas A&M|Texas Tech|Cincinnati|Houston|S Florida|Troy|New Mexico|Utah|BYU|
Colorado St|Washington|USC|UCLA|Miami|Virginia|Wake Forest|Duke|North Carolina|Maryland|Virginia Tech|
Pittsburgh|West Virginia|UMass|App State|J Madison|North Dakota State|Georgia St|UTSA|San Jose St|
Memphis|W Michigan|Ball St|Toledo|C Michigan|Miami OH|Ohio|Akron|Buffalo|Marshall|UCF|Kent St|Nevada|
Boise St|Rice|Louisiana Tech|UTEP|Fresno St|Navy|Kentucky|Arkansas|Wisconsin|Ohio St|Minnesota|Purdue|
Illinois|Iowa St|Kansas|Oklahoma|Baylor|Oklahoma St|TCU|UAB|Army|Louisville|Southern Miss|Tulane|
Louisiana|Middle Tenn|N Texas|Arkansas St|Air Force|Wyoming|San Diego St|Stanford|Arizona St|California|
Arizona|Oregon|Clemson|Florida St|NC State|Temple|Boston College|UConn|Delaware|Florida Intl|
Florida Atlantic|Georgia So|Liberty|Coastal Car|Missouri St|S Alabama|Old Dominion|Kennesaw St|
E Michigan|Hawai'i|New Mexico St|UNLV|Syracuse|Sacramento State|Jacksonville St|N Illinois|Bowling Green|
E Carolina|UL Monroe|Utah St|Washington St|Oregon St|Georgia Tech|Rutgers|Texas St|W Kentucky|
Sam Houston|Charlotte"""


def test_parse():
    rows = load_trends(os.path.join(HERE, "testdata", "win_trends_sample.html"), "TR_win")
    by = {r["team"]: r for r in rows}
    checks = [
        (len(rows) == 7, f"expected 7 rows, got {len(rows)}"),
        ("Texas A&M" in by, "HTML entity &amp; not decoded in team name"),
        ("Hawai'i" in by, "numeric entity &#039; not decoded in team name"),
        (by["Tulsa"]["team_slug"] == "tulsa-golden-hurricane", "team slug not taken from the href"),
        (by["Tulsa"]["TR_win_win_loss_record"] == "2-0-0", "record should keep its display text"),
        (by["Hawai'i"]["TR_win_win_loss_record_W"] == 1
         and by["Hawai'i"]["TR_win_win_loss_record_L"] == 2, "W-L-T not split correctly"),
        # the page shows +10.3; data-sort carries 10.25 and that is what we want
        (by["Tulsa"]["TR_win_ats_plus_minus"] == 10.25, "ATS +/- not read at full precision"),
        (by["USC"]["TR_win_mov"] == 24.666666666666668, "MOV not read at full precision"),
        ("TR_win_win_pct" in by["Tulsa"], "'Win %' column lost its pct suffix"),
        ("TR_win_ats_plus_minus" in by["Tulsa"], "'ATS +/-' column lost its plus_minus suffix"),
    ]
    fails = [msg for ok, msg in checks if not ok]
    for f in fails:
        print(f"  FAIL {f}")
    print(f"  parsing: {len(checks) - len(fails)}/{len(checks)} checks passed")
    return not fails


def test_resolution(xlsx):
    """Same chain as an_metrics.build(): alias, our name, TeamID, normalised."""
    wb = Workbook(xlsx)
    by_team = {to_str(r[0]) for r in wb.grid("2026 PR", 2, None, 1, 1) if to_str(r[0])}
    xw = {}
    for row in wb.grid("TeamID", 2, None, 1, 9):
        cw = to_str(row[0])
        if cw and cw not in xw:
            xw[cw] = to_str(row[1])
    tr_name = {v: k for k, v in xw.items() if v}
    norm_pr = {_norm_team(t): t for t in by_team}
    norm_tr = {_norm_team(v): k for k, v in xw.items() if v}

    names = [n.strip() for n in SLATE.replace("\n", "").split("|") if n.strip()]
    unresolved, hits = [], {}
    for raw in names:
        team = (TEAMRANKINGS_ALIASES.get(raw)
                or (raw if raw in by_team else None)
                or tr_name.get(raw)
                or norm_pr.get(_norm_team(raw))
                or norm_tr.get(_norm_team(raw)))
        (hits.setdefault(team, []).append(raw) if team else unresolved.append(raw))

    dupes = {t: v for t, v in hits.items() if len(v) > 1}
    print(f"  resolution: {len(names) - len(unresolved)}/{len(names)} names resolved")
    for u in unresolved:
        print(f"    UNRESOLVED {u!r}")
    for t, v in dupes.items():
        print(f"    COLLISION  {v} all resolved to {t!r}")
    return not unresolved and not dupes


def main():
    xlsx = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "input", "AN_season.xlsx")
    ok = test_parse()
    if os.path.exists(xlsx):
        ok = test_resolution(xlsx) and ok
    else:
        print(f"  resolution: skipped, no workbook at {xlsx}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
