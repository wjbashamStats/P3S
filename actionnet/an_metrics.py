#!/usr/bin/env python3
"""
an_metrics.py -- Python port of MetricRankingCode, reading the Action Network
season workbook and writing the ranked metrics CSV.

Replaces the R script's nine googlesheets4 reads with one .xlsx. Standard
library only (see xlsx_read.py for why) so the weekly scheduled run has no
install step.

Sheet mapping (old Google Sheet -> workbook tab):
    stats          sheet1        -> CFBData{yy}
    ratings        2025 PR       -> {season} PR
    rp             Sheet1        -> TARP {yy}
    tempo          TOTALS        -> TOTALS
    projwinTotals  WinTotals     -> {season} Win Total   (per-team subtotal rows)
    Names          AllNames      -> TeamID
    info           info          -> TeamID + Twitter     (partial, see below)
    records        Sheet1        -> PFF                  (partial, see below)
    odds           CombinedOdds  -> NOT IN THE WORKBOOK  (--odds-csv)
    records        Sheet1        -> TeamRankings          (--trends-dir)

WHAT THE WORKBOOK DOES NOT HAVE
  1. CombinedOdds. No per-team futures prices in the workbook ('{season}
     Futures' has Win Total Feb/MAR/Jul columns but they are empty). Comes from
     the futures pipeline instead -- AllTeamsFuturesWorkingFinal.R's
     CombinedOdds tab, or this repo's build_futures_from_html.py, which parses
     the same VegasInsider pages into the same schema (Team, Conference, Nat_*,
     Conf_*, Win_*). Auto-detected as futures_{season}.csv, or pass --odds-csv.
  2. VI is NOT needed. The old script joined odds on the VegasInsider spelling
     because the scrape carried raw VI names; the futures export is keyed on our
     naming instead. futures_2026.csv matches '2026 PR'!Team on 136 of 138
     straight across -- the two misses (North Dakota State, Sacramento State)
     are new to the 2026 PR and had no 2025 futures.
  3. Mascot. Derived here from TeamID's ESPN name by stripping the school off
     the front; resolves 129 of 138.
  4. Records come from TeamRankings, not the workbook. Save the three trends
     pages (win_trends.html, ats_trends.html, ou_trends.html from
     teamrankings.com/ncf/trends/) into one directory and pass --trends-dir;
     they carry win/loss, against-the-spread and over/under records together.
     Without it this falls back to parsing PFF's RECORD ("1 - 1"), whose own
     spellings only match 130 of 138 -- the fallback is reported in the log so
     a silent downgrade is visible.
  5. Logos. Not in an info sheet; taken from Twitter column D, 132 of 138.

THINGS IN THE WORKBOOK THAT LOOK WRONG (flagged at runtime, not fixed)
  A. TOTALS has two columns headed 'Tempo' and neither is tempo -- both equal
     '{season} PR'!Team Total for 136 of 138 teams. Tempo here comes from
     PlaysPG (offensive plays per game) and is ranked descending.
  A2. TOTALS' own 'SPP RANK' does not rank the SPP beside it (r = 0.02). We
     compute rank_SPP from SPP and carry theirs as SPP_RANK_SHEET.
  B. TeamID has Arizona and Arizona State swapped in the ESPN column.
  C. '{season} Win Total' carries #N/A for some teams' TAN WIN.

Run:  python3 actionnet/an_metrics.py --xlsx <workbook.xlsx> --out <out.csv>
"""
import argparse
import csv
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlsx_read import Workbook, to_num, to_str
from teamrankings import TEAMRANKINGS_ALIASES, load_trends_dir


# --------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------
def rank(values, descending=False):
    """R's rank() with ties.method='average' and na.last='keep'.

    Average ties because that is what the R script produced and the workbook's
    own rank columns agree with it. None stays None rather than being sorted to
    the bottom with a real rank -- base R's default (na.last=TRUE) would hand a
    team with a broken #N/A source a legitimate-looking rank.
    """
    idx = [i for i, v in enumerate(values) if v is not None]
    order = sorted(idx, key=lambda i: -values[i] if descending else values[i])
    out = [None] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1          # 1-based, averaged over the tie block
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def add_rank(rows, source_col, rank_col, descending):
    vals = [to_num(r.get(source_col)) for r in rows]
    for r, v in zip(rows, rank(vals, descending)):
        r[rank_col] = v


# --------------------------------------------------------------------------
# CFBData ranking spec: (column, rank name, rank descending?)
# descending=True means "big number is good, so it gets rank 1".
# Transcribed 1:1 from the R script's rank(-x) / rank(x) calls.
# --------------------------------------------------------------------------
def stat_spec():
    off_hi = ["Plays", "Drives", "Ppa", "TotalPPA", "SuccessRate", "Explosiveness",
              "PowerSuccess", "LineYards", "LineYardsTotal", "SecondLevelYards",
              "SecondLevelYardsTotal", "OpenFieldYards", "OpenFieldYardsTotal",
              "TotalOpportunies", "PointsPerOpportunity"]
    spec = []
    for s in off_hi:
        spec.append((f"Offense {s}", f"rank_Offense_{s[0].lower() + s[1:]}", True))
    spec += [
        ("Offense StuffRate", "rank_Offense_stuffRate", False),
        ("Offense FieldPosition AverageStart", "rank_Offense_fieldPosition_averageStart", False),
        ("Offense FieldPosition AveragePredictedPoints", "rank_Offense_fieldPosition_averagePredictedPoints", True),
        ("Offense Havoc Total", "rank_Offense_havoc_total", False),
        ("Offense Havoc FrontSeven", "rank_Offense_havoc_frontSeven", False),
        ("Offense Havoc Db", "rank_Offense_havoc_db", False),
        ("Offense StandardDowns Rate", "rank_Offense_standardDowns_rate", True),
        ("Offense StandardDowns Ppa", "rank_Offense_standardDowns_ppa", True),
        ("Offense StandardDowns SuccessRate", "rank_Offense_standardDowns_successRate", True),
        ("Offense StandardDowns Explosiveness", "rank_Offense_standardDowns_explosiveness", True),
        ("Offense PassingDowns Rate", "rank_Offense_passingDowns_rate", False),
        ("Offense PassingDowns Ppa", "rank_Offense_passingDowns_ppa", True),
        ("Offense PassingDowns SuccessRate", "rank_Offense_passingDowns_successRate", True),
        ("Offense PassingDowns Explosiveness", "rank_Offense_passingDowns_explosiveness", True),
    ]
    for fam in ("RushingPlays", "PassingPlays"):
        for s in ("Rate", "Ppa", "TotalPPA", "SuccessRate", "Explosiveness"):
            spec.append((f"Offense {fam} {s}", f"rank_Offense_{fam[0].lower() + fam[1:]}_{s[0].lower() + s[1:]}", True))

    # Defense: low is good for nearly everything, so the sense flips.
    def_lo = ["Plays", "Drives", "Ppa", "TotalPPA", "SuccessRate", "Explosiveness",
              "PowerSuccess", "LineYards", "LineYardsTotal", "SecondLevelYards",
              "SecondLevelYardsTotal", "OpenFieldYards", "OpenFieldYardsTotal",
              "TotalOpportunies", "PointsPerOpportunity"]
    for s in def_lo:
        spec.append((f"Defense {s}", f"rank_defense_{s[0].lower() + s[1:]}", False))
    spec += [
        ("Defense StuffRate", "rank_defense_stuffRate", True),
        ("Defense FieldPosition AverageStart", "rank_defense_fieldPosition_averageStart", True),
        ("Defense FieldPosition AveragePredictedPoints", "rank_defense_fieldPosition_averagePredictedPoints", False),
        ("Defense Havoc Total", "rank_defense_havoc_total", True),
        ("Defense Havoc FrontSeven", "rank_defense_havoc_frontSeven", True),
        ("Defense Havoc Db", "rank_defense_havoc_db", True),
        ("Defense StandardDowns Rate", "rank_defense_standardDowns_rate", False),
        ("Defense StandardDowns Ppa", "rank_defense_standardDowns_ppa", False),
        ("Defense StandardDowns SuccessRate", "rank_defense_standardDowns_successRate", False),
        ("Defense StandardDowns Explosiveness", "rank_defense_standardDowns_explosiveness", False),
        ("Defense PassingDowns Rate", "rank_defense_passingDowns_rate", True),
        ("Defense PassingDowns Ppa", "rank_defense_passingDowns_ppa", False),
        ("Defense PassingDowns TotalPPA", "rank_defense_passingDowns_totalPPA", False),
        ("Defense PassingDowns SuccessRate", "rank_defense_passingDowns_successRate", False),
        ("Defense PassingDowns Explosiveness", "rank_defense_passingDowns_explosiveness", False),
    ]
    for s in ("Rate", "Ppa", "TotalPPA", "SuccessRate", "Explosiveness"):
        spec.append((f"Defense RushingPlays {s}", f"rank_defense_rushingPlays_{s[0].lower() + s[1:]}", False))
    # PassingPlays TotalPPA is ADDED relative to the R script -- it was the only
    # stat column in the sheet that came out unranked, while the offense block
    # ranks its equivalent.
    for s in ("Rate", "Ppa", "TotalPPA", "SuccessRate", "Explosiveness"):
        spec.append((f"Defense PassingPlays {s}", f"rank_defense_passingPlays_{s[0].lower() + s[1:]}", False))
    return spec


# --------------------------------------------------------------------------
def dicts(grid, names):
    return [dict(zip(names, row)) for row in grid]


def _norm_team(name):
    """Loose team-name key: lowercase alphanumerics, with TeamRankings' 'St.'
    abbreviation expanded so 'Ohio St.' meets 'Ohio State'."""
    if not name:
        return ""
    s = str(name).lower().replace("&", " and ")
    s = s.replace(" st.", " state").replace(" st ", " state ")
    if s.endswith(" st"):
        s = s[:-3] + " state"
    return "".join(ch for ch in s if ch.isalnum())


def _parse_record(rec):
    """'1 - 1' / '1-1' -> (1, 1); anything else -> (None, None)."""
    if not rec:
        return None, None
    parts = str(rec).split("-")
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0].strip()), int(parts[1].strip())
    except ValueError:
        return None, None


def report_join(rows, key, label, log):
    missing = [r["Team"] for r in rows if r.get(key) is None]
    log(f"[join] {label:<22} unmatched: {len(missing):>3}"
        + (f"  -> {', '.join(missing[:8])}" if missing else ""))


def build(xlsx_path, season, odds_csv=None, trends_dir=None, log=print):
    # Print the input's age: the weekly job reads whatever sits at the fixed
    # input path, so a workbook nobody refreshed still produces a clean run with
    # last week's numbers. This is the line that makes that visible.
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(xlsx_path))
    age = (datetime.datetime.now() - mtime).days
    log(f"workbook: {os.path.basename(xlsx_path)}  modified {mtime:%Y-%m-%d %H:%M} "
        f"({age} day{'s' if age != 1 else ''} old)"
        + ("   <-- STALE, was this week's export committed?" if age > 7 else ""))
    wb = Workbook(xlsx_path)
    yy = season % 100

    def sheet(*cands):
        for c in cands:
            if c in wb.sheets:
                return c
        raise KeyError(f"none of {cands} in workbook (have: {sorted(wb.sheets)[:6]}...)")

    s_pr    = sheet(f"{season} PR")
    s_tarp  = sheet(f"TARP {yy}", f"TARP{yy}")
    s_stats = sheet(f"CFBData{yy}")
    s_win   = sheet(f"{season} Win Total")

    # -- ratings: {season} PR ------------------------------------------------
    hdr = [to_str(c) for c in wb.grid(s_pr, 1, 1, 1, 14)[0]]
    pr = dicts(wb.grid(s_pr, 2, None, 1, 14), hdr)
    ratings = []
    for r in pr:
        if not to_str(r.get("Team")):
            continue
        ratings.append({
            "Team": to_str(r["Team"]), "SP": to_num(r["SP+"]), "TAN": to_num(r[f"TAN {yy}"]),
            "HFACW": to_num(r["HFACW"]), "TEAM_ID": r["TEAM_ID"], "Team Total": to_num(r["Team Total"]),
            "HC": to_str(r["HC"]), "OC": to_str(r["OC"]), "DC": to_str(r["DC"]),
        })
    log(f"ratings: {len(ratings)} teams from '{s_pr}'")
    for col, name in (("TAN", "rank_TAN"), ("SP", "rank_SP"), ("HFACW", "rank_HFACW")):
        add_rank(ratings, col, name, descending=True)
    by_team = {r["Team"]: r for r in ratings}

    # -- rp: TARP {yy} -------------------------------------------------------
    # Columns A and B carry no header and row 2 is a second header band, so the
    # team rows start at row 3. Read the block by position.
    rp_rows = []
    for row in wb.grid(s_tarp, 3, None, 1, 8):
        team = to_str(row[0])
        if not team:
            continue
        rp_rows.append({"Team": team, "NetRP": to_num(row[2]), "OffAdj": to_num(row[3]),
                        "DefAdj": to_num(row[4]), "RPOffense": to_num(row[6]),
                        "RPDefense": to_num(row[7])})
    for col, name in (("NetRP", "rank_TARP"), ("OffAdj", "rank_OffAdj"), ("DefAdj", "rank_DefAdj")):
        add_rank(rp_rows, col, name, descending=True)
    rp = {r["Team"]: r for r in rp_rows}
    for r in ratings:
        r.update({k: v for k, v in rp.get(r["Team"], {}).items() if k != "Team"})
    report_join(ratings, "NetRP", s_tarp, log)

    # -- tempo: TOTALS -------------------------------------------------------
    # Two problems in this sheet, both worked around rather than trusted.
    #
    # The columns headed 'Tempo' (T and V) hold Team Total, not tempo: they
    # equal '{season} PR'!Team Total for 136 of 138 teams. Tempo here comes from
    # PlaysPG (col P), offensive plays per game, ranked descending.
    #
    # And the sheet's own rank columns do not rank the SPP beside them. Col E
    # ('SPP RANK') and col AF ('Rank') are both clean 1..138 permutations, but
    # against the SPP values in the same rows they correlate r = 0.02 -- they
    # are ranks of a differently ordered list, not of this SPP. So rank_SPP is
    # computed from SPP here (ascending, low seconds per play = fast = rank 1),
    # the sheet's column is carried through as SPP_RANK_SHEET so both are
    # visible, and the disagreement count is reported rather than asserted away.
    # This is the same upstream oddity noted for rank_SPP in team_ratings_2025.
    thdr = [to_str(c) for c in wb.grid("TOTALS", 1, 1, 1, 16)[0]]
    tempo_rows, seen = [], set()
    for row in dicts(wb.grid("TOTALS", 2, None, 1, 16), thdr):
        team = to_str(row.get("Name"))
        if not team or team in seen:
            continue
        seen.add(team)
        tempo_rows.append({"Team": team, "SPP": to_num(row["SPP"]),
                           "Tempo": to_num(row["PlaysPG"]),
                           "SPP_RANK_SHEET": to_num(row["SPP RANK"])})
    add_rank(tempo_rows, "SPP", "rank_SPP", descending=False)
    add_rank(tempo_rows, "Tempo", "rank_Tempo", descending=True)
    disagree = [t["Team"] for t in tempo_rows
                if t["SPP_RANK_SHEET"] is not None and t["rank_SPP"] != t["SPP_RANK_SHEET"]]
    log(f"[note] sheet 'SPP RANK' disagrees with rank(SPP) for {len(disagree)}/"
        f"{len(tempo_rows)} teams -- expected, see the tempo comment; "
        f"rank_SPP is ours, SPP_RANK_SHEET is theirs")
    tempo = {t["Team"]: t for t in tempo_rows}
    for r in ratings:
        t = tempo.get(r["Team"], {})
        r.update({k: v for k, v in t.items() if k != "Team"})
    report_join(ratings, "SPP", "TOTALS", log)

    # -- projwinTotals: {season} Win Total ----------------------------------
    # One row per GAME, but each team's block ends with a subtotal row holding
    # the season numbers in columns J:M. Column J is NOT a reliable marker on
    # its own -- on matchup rows it doubles as a conference-game flag holding
    # "c". What marks a subtotal is column B (the team's TAN Rating) being
    # EMPTY while J is filled. And do not sum column L yourself: the subtotal
    # sits in that same column, so every team comes out at twice its win total.
    win = {}
    for row in wb.grid(s_win, 3, None, 1, 13):
        team = to_str(row[9])
        if not team or row[1] is not None:
            continue
        win[team] = {"TAN_CONF": to_num(row[10]), "TAN_WIN": to_num(row[11]),
                     "SP._WIN": to_num(row[12])}
    log(f"projwinTotals: {len(win)} team subtotal rows from '{s_win}'")
    for r in ratings:
        r.update(win.get(r["Team"], {}))
    report_join(ratings, "TAN_WIN", s_win, log)
    na_win = [r["Team"] for r in ratings if r["Team"] in win and r.get("TAN_WIN") is None]
    if na_win:
        log(f"[warn] TAN WIN is #N/A in the workbook for: {', '.join(na_win)}")
    add_rank(ratings, "TAN_WIN", "rank_TAN_WIN", descending=True)
    add_rank(ratings, "SP._WIN", "rank_SP_WIN", descending=True)

    # -- Names: TeamID -------------------------------------------------------
    xw, seen = {}, set()
    for row in wb.grid("TeamID", 2, None, 1, 9):
        cw = to_str(row[0])
        if not cw or cw in seen:
            continue
        seen.add(cw)
        xw[cw] = {"TR": to_str(row[1]), "SPplus_name": to_str(row[2]), "CFBD": to_str(row[3]),
                  "SSA": to_str(row[4]), "CFBStats": to_str(row[5]), "ESPN": to_str(row[6]),
                  "SIS": to_str(row[7]), "TEAM_ID_XW": row[8]}
    for r in ratings:
        r.update(xw.get(r["Team"], {}))
    report_join(ratings, "CFBD", "TeamID", log)

    # -- stats: CFBData{yy}, joined on the CFBData spelling ------------------
    shdr = [to_str(c) for c in wb.grid(s_stats, 1, 1, 1, 183)[0]]
    stats = dicts(wb.grid(s_stats, 2, None, 1, 183), shdr)
    stats = [s for s in stats if to_str(s.get("Team"))]
    spec = stat_spec()
    missing_cols = [c for c, _, _ in spec if c not in shdr]
    if missing_cols:
        raise SystemExit(f"'{s_stats}' is missing expected columns: {missing_cols[:6]}")
    for col, name, desc in spec:
        add_rank(stats, col, name, desc)
    log(f"stats: {len(stats)} teams, {len(spec)} ranked columns from '{s_stats}'")
    by_cfbd = {to_str(s["Team"]): s for s in stats}
    for r in ratings:
        s = by_cfbd.get(r.get("CFBD"))
        if s:
            r.update({k: v for k, v in s.items() if k != "Team"})
    report_join(ratings, "Offense Plays", s_stats, log)

    # -- odds: not in the workbook, joined on Team (no VI step, see item 2) ---
    if odds_csv and os.path.exists(odds_csv):
        drop = {"Team", "Conference", "Conference.y", "Conf"}
        with open(odds_csv, newline="", encoding="utf-8") as fh:
            odds = {to_str(row.get("Team")): row for row in csv.DictReader(fh)}
        for r in ratings:
            o = odds.get(r["Team"])
            if o:
                r.update({k: (v if v != "" else None) for k, v in o.items() if k not in drop})
        # Report on whether the TEAM matched, not whether some column is
        # populated: the books are sparse (Bet365 prices 40 of 136 teams to win
        # it all), so keying the check on a column would call a clean join a
        # failure.
        unmatched = [r["Team"] for r in ratings if r["Team"] not in odds]
        log(f"[join] {'futures odds':<22} from {os.path.basename(odds_csv)}, "
            f"unmatched: {len(unmatched)}"
            + (f"  -> {', '.join(unmatched[:8])}" if unmatched else ""))
    else:
        want = f"futures_{season}.csv"
        others = sorted(f for f in os.listdir(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if f.startswith("futures_") and f.endswith(".csv"))
        log(f"[skip] {'futures odds':<22} no {want}"
            + (f" (found {', '.join(others)} -- different season, not used)" if others else "")
            + " -- run build_futures_from_html.py, or pass --odds-csv")

    # -- info: logos from Twitter, mascot derived from the ESPN name ---------
    logos = {}
    for row in wb.grid("Twitter", 1, None, 1, 4):
        team = to_str(row[0])
        if team and team not in logos:
            logos[team] = to_str(row[3])
    for r in ratings:
        r["logo"] = logos.get(r["Team"])
    report_join(ratings, "logo", "Twitter (logos)", log)

    for r in ratings:
        espn, team = r.get("ESPN"), r["Team"]
        r["Mascot"] = (espn[len(team):].strip()
                       if espn and espn.startswith(team) and len(espn) > len(team) else None)
    unresolved = [r["Team"] for r in ratings if not r["Mascot"]]
    log(f"[derive] Mascot from ESPN name: {len(ratings) - len(unresolved)} resolved, "
        f"{len(unresolved)} not ({', '.join(unresolved[:8])})")

    # -- trends: TeamRankings win / ATS / over-under, falling back to PFF ----
    # TeamRankings abbreviates its team names ("N Texas", "Miami OH"), so
    # resolution goes: the hand-verified alias table for the five the other two
    # steps miss, then TeamID's own TeamRankings column, then a normalised form
    # that expands "St" to "State" and drops punctuation. That covers all 138.
    recs = {}
    if trends_dir and os.path.isdir(trends_dir):
        tr_name = {v.get("TR"): k for k, v in xw.items() if v.get("TR")}
        norm_pr = {_norm_team(t): t for t in by_team}
        # Normalised TeamID.TeamRankings matters on its own: "Miami OH" is not
        # our team name and not an exact TeamID hit, but TeamID stores
        # "Miami (OH)", which normalises to the same key. Normalising only
        # against our own names would drop it.
        norm_tr = {_norm_team(v["TR"]): k for k, v in xw.items() if v.get("TR")}
        merged = load_trends_dir(trends_dir, log)
        unresolved_tr = []
        for raw, cols in merged.items():
            team = (TEAMRANKINGS_ALIASES.get(raw)
                    or (raw if raw in by_team else None)
                    or tr_name.get(raw)
                    or norm_pr.get(_norm_team(raw))
                    or norm_tr.get(_norm_team(raw)))
            if not team:
                unresolved_tr.append(raw)
                continue
            recs[team] = {k: v for k, v in cols.items() if k != "team"}
        log(f"[join] {'trends (TeamRankings)':<22} {len(recs)} teams resolved"
            + (f", UNRESOLVED: {', '.join(unresolved_tr)}" if unresolved_tr else ""))
        probe = "TR_win_win_loss_record"
    else:
        log(f"[fall] {'trends':<22} no --trends-dir -- parsing PFF's RECORD instead")
        for row in wb.grid("PFF", 3, None, 1, 6):
            team, rec = to_str(row[0]), to_str(row[5])
            if not team or not rec or team in recs:
                continue
            w, l = _parse_record(rec)
            recs[team] = {"RECORD": rec, "W": w, "L": l}
        probe = "RECORD"
    for r in ratings:
        r.update(recs.get(r["Team"], {}))
    report_join(ratings, probe, "records", log)

    return ratings


def write_csv(rows, path):
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})
    return cols


HERE_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--xlsx", required=True, help="Action Network season workbook (.xlsx)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--odds-csv", default=None,
                    help="futures export keyed on our team naming; defaults to "
                         "futures_<season>.csv beside the repo root if present")
    ap.add_argument("--trends-dir", default=None,
                    help="directory holding the saved TeamRankings trends pages "
                         "(win_trends.html / ats_trends.html / ou_trends.html); "
                         "without it, records fall back to the PFF tab")
    ap.add_argument("--out", default=None, help="output CSV (default: AN_<season>_<date>.csv)")
    args = ap.parse_args()

    if not os.path.exists(args.xlsx):
        raise SystemExit(f"workbook not found: {args.xlsx}")
    out = args.out or f"AN_{args.season}_{datetime.date.today():%Y%m%d}.csv"
    trends = args.trends_dir
    if trends is None:
        guess = os.path.join(HERE_REPO, "actionnet", "input", "trends")
        trends = guess if os.path.isdir(guess) else None
    odds = args.odds_csv
    if odds is None:
        guess = os.path.join(HERE_REPO, f"futures_{args.season}.csv")
        odds = guess if os.path.exists(guess) else None
    rows = build(args.xlsx, args.season, odds, trends)
    cols = write_csv(rows, out)
    print(f"\nwrote {out}: {len(rows)} teams, {len(cols)} columns")


if __name__ == "__main__":
    main()
