#!/usr/bin/env python3
"""Checks for the TeamRankings trends parser and its name resolution.

Three things are verified:

  1. Parsing, against a fixture cut from a real saved page -- HTML entities,
     the data-sort full-precision values, W-L-T splitting, and the team slug.
  2. Parsing a tab-delimited paste of the table, which is what comes across
     on a week the saved page does not. The trap there is the percent column:
     the page's data-sort holds a fraction while the visible cell reads
     "100.0%", so a paste has to be divided down to line up with the .html.
  3. Name resolution, against the full 138-team slate as the live page spells
     it. This is the part that silently rots: TeamRankings abbreviates, the
     workbook's TeamID column is stale for a handful, and a name that fails to
     resolve drops that team's records without anything looking broken.

Run:  python3 actionnet/test_teamrankings.py [workbook.xlsx]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from teamrankings import (TEAMRANKINGS_ALIASES, load_trends,        # noqa: E402
                          parse_trends_text)
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


PASTE = """Team	ATS Record	Cover %	MOV	ATS +/-
Louisiana Tech 	3-0-0 	100.0% 	8.7 	+12.0
Toledo 	1-0-1 	100.0% 	21.5 	+8.8
Texas A&M 	2-1-0 	66.7% 	9.3 	-1.5
Old Dominion 	0-3-0 	0.0% 	-1.7 	-10.3"""

# Same four rows with the tabs collapsed to runs of spaces, which is what a
# copy out of some browsers produces. Team names keep their single spaces.
PASTE_SPACED = "\n".join("   ".join(c.strip() for c in ln.split("\t"))
                          for ln in PASTE.splitlines())


def test_parse_text():
    rows = parse_trends_text(PASTE, "TR_ats")
    by = {r["team"]: r for r in rows}
    spaced = {r["team"]: r for r in parse_trends_text(PASTE_SPACED, "TR_ats")}
    checks = [
        (len(rows) == 4, f"expected 4 rows, got {len(rows)}"),
        ("Louisiana Tech" in by, "trailing space not stripped from team name"),
        ("Texas A&M" in by, "'&' in a team name broke the split"),
        # 100.0% must land as the fraction the .html's data-sort gives, not 100
        (by["Louisiana Tech"]["TR_ats_cover_pct"] == 1, "100.0% did not become 1"),
        (abs(by["Texas A&M"]["TR_ats_cover_pct"] - 0.667) < 1e-9, "66.7% did not become 0.667"),
        (by["Old Dominion"]["TR_ats_cover_pct"] == 0, "0.0% did not become 0"),
        (by["Louisiana Tech"]["TR_ats_ats_plus_minus"] == 12, "leading + not stripped"),
        (by["Old Dominion"]["TR_ats_mov"] == -1.7, "negative value not read"),
        (by["Toledo"]["TR_ats_ats_record"] == "1-0-1", "record not kept as text"),
        (by["Toledo"]["TR_ats_ats_record_T"] == 1, "tie not split out of the record"),
        (by["Louisiana Tech"]["team_slug"] is None, "a paste has no slug to report"),
        ("TR_ats_cover_pct" in by["Toledo"], "'Cover %' column lost its pct suffix"),
        (spaced == by, "space-delimited paste parsed differently from tab-delimited"),
    ]
    # The O/U table arrived as the whole thing twice with the header repeated
    # partway, the first copy severed mid-record, and the tail of that severed
    # row on a line of its own. None of the three can be a real row.
    lines = PASTE.splitlines()
    messy = "\n".join([lines[0], lines[1], "Toledo \t1-0-", lines[0]]
                       + lines[1:] + ["0 \t66.7% \t9.3 \t-1.5"])
    recovered = {r["team"]: r for r in parse_trends_text(messy, "TR_ats")}
    checks += [
        (recovered == by, "duplicated/severed paste did not parse back to the clean rows"),
        ("Team" not in recovered, "a repeated header line parsed as a team"),
        ("0" not in recovered, "a severed row's tail parsed as a team"),
        (recovered["Toledo"]["TR_ats_ats_record"] == "1-0-1",
         "a truncated duplicate displaced the complete row"),
    ]
    for bad, msg in ((PASTE.split("\n", 1)[1], "header-less paste accepted"),
                     ("", "empty paste accepted")):
        try:
            parse_trends_text(bad, "TR_ats")
            checks.append((False, msg))
        except ValueError:
            checks.append((True, msg))
    fails = [msg for ok, msg in checks if not ok]
    for f in fails:
        print(f"  FAIL {f}")
    print(f"  paste parsing: {len(checks) - len(fails)}/{len(checks)} checks passed")
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
    ok = test_parse_text() and ok
    if os.path.exists(xlsx):
        ok = test_resolution(xlsx) and ok
    else:
        print(f"  resolution: skipped, no workbook at {xlsx}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
