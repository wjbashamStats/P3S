"""
data_load.py — load PFF grades, prior-year stats, and the team crosswalk;
normalize names so everything joins.

The three naming systems (PFF display, CFBD, Odds API) are reconciled here via
team_map.csv so no downstream module has to think about it.
"""
import csv, os
import config as C


def norm(s):
    """Normalize a name/team for fuzzy joins."""
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def load_team_map():
    """
    team_map.csv: columns cfbd_name, odds_name (same file historical_pull.py
    reads for schedule<->odds event matching).
    pff_team_map.csv: columns pff_team, cfbd_team (build_pff_team_map.py) --
    PFF crosswalk team strings are heavily abbreviated ("S JOSE ST", "GA
    TECH") and don't reliably normalize to a CFBD-style name, so this is a
    hand-verified explicit table, not a fuzzy match at load time.
    Returns dicts to translate any system -> canonical (cfbd) team.
    If a file is absent, its dict is empty (identity fallback elsewhere).
    """
    pff2c, odds2c = {}, {}
    if os.path.exists(C.TEAM_MAP):
        for r in csv.DictReader(open(C.TEAM_MAP)):
            c = r.get("cfbd_name", r.get("cfbd_team", "")).strip()
            if not c:
                continue
            o = r.get("odds_name", r.get("odds_team", c)).strip()
            odds2c[norm(o)] = c
    if os.path.exists(C.PFF_TEAM_MAP):
        for r in csv.DictReader(open(C.PFF_TEAM_MAP)):
            c = r.get("cfbd_team", "").strip()
            if c:
                pff2c[norm(r.get("pff_team", ""))] = c
    return pff2c, odds2c


def resolve_tkey(raw_team, pff2c):
    """Same PFF-team-string -> canonical tkey translation load_pff() uses inline,
    factored out for callers that need it for a record OTHER than a PFF
    crosswalk row (e.g. a prior-year totals record's own "team" field)."""
    team_c = pff2c.get(norm(raw_team), raw_team)
    return norm(team_c)


def load_pff(pff2c):
    """
    Load master_crosswalk.csv (the enriched file we built).
    Returns list of player dicts keyed for joining, team normalized to CFBD.
    """
    players = []
    if not os.path.exists(C.PFF_CROSSWALK):
        print(f"  [warn] PFF crosswalk not found at {C.PFF_CROSSWALK}")
        return players
    for r in csv.DictReader(open(C.PFF_CROSSWALK)):
        team_c = pff2c.get(norm(r["team"]), r["team"])
        players.append({
            **r,
            "team_cfbd": team_c,
            "pkey": norm(r["name"]),
            "tkey": norm(team_c),
        })
    return players


# PFF's own offense position labels for the four skill-position groups
# (master_crosswalk.csv's "RB", not this project's "HB" -- see
# build_dfs_page_data.py's DK_SLOT for where that renaming happens
# downstream). No "FB" observed in the crosswalk (too rare to be graded
# separately), included anyway for parity with SKILL_POSITIONS elsewhere.
PFF_SKILL_POSITIONS = {"QB", "RB", "WR", "TE", "FB"}


def load_pff_skill_by_pkey(pff2c):
    """
    load_pff(), narrowed to offense skill positions and keyed by pkey --
    the form every "what team is this skill player on THIS year"
    resolution needs (backtest.py/build.py's canon_tkey, and the DFS/props
    page builders' displayed team). Plain name-only pkey matching against
    the FULL crosswalk (all ~2500 players, every position) risks a same-
    name collision with an unrelated player at another position -- found
    for real: a defensive back "Jordan Allen" at Houston was overriding a
    Georgia Tech WR of the same name. Restricting to skill positions here
    doesn't fully eliminate same-position collisions, but removes the
    much larger cross-position collision surface (~2100 non-skill rows).
    Only use load_pff() directly (unfiltered) for something that
    genuinely needs every position, like build_def_index.
    """
    return {p["pkey"]: p for p in load_pff(pff2c) if p.get("position") in PFF_SKILL_POSITIONS}


def _to_float(x):
    try:
        return float(str(x).replace(",", ""))
    except (ValueError, TypeError):
        return None


def load_season_totals():
    """
    player_season_totals.csv — one row per player, prior year.
    Expected (flexible) columns; missing ones are tolerated:
      player, team, games,
      pass_att, pass_yds, pass_td,
      rush_att, rush_yds, rush_td,
      targets, receptions, rec_yds, rec_td
    Returns dict keyed by (pkey, tkey) -> stat dict.
    """
    out = {}
    if not os.path.exists(C.SEASON_TOTALS):
        print(f"  [warn] season totals not found at {C.SEASON_TOTALS}")
        return out
    for r in csv.DictReader(open(C.SEASON_TOTALS)):
        pkey = norm(r.get("player", ""))
        tkey = norm(r.get("team", ""))
        rec = {k: _to_float(v) for k, v in r.items()
               if k not in ("player", "team", "player_id", "position")}
        rec["player_id"] = r.get("player_id")  # keep as string -- it's a join key, not a stat
        rec["position"] = r.get("position")
        rec["games"] = rec.get("games") or 1
        out[(pkey, tkey)] = rec
    return out


def load_prior_totals(season=None):
    """
    Real prior-year rates, keyed by player_id ONLY (not (pkey, tkey)): a
    transferred player's prior-year team isn't their current one, so team
    can't be part of this join key. Callers match a current-roster player
    to their prior-year record via player_id, and keep the CURRENT team/
    roster from the current season's side.

    Which file counts as "prior year" depends on season (config.
    PRIOR_TOTALS_BY_SEASON) -- 2025's backtest uses real 2024 data;
    2026's live projections reuse 2025's own season totals (this year's
    finished numbers become next year's prior-year input). Falls back to
    config.PRIOR_SEASON_TOTALS (the 2024 file) for any season not listed.
    Returns {} if the resolved file doesn't exist.
    """
    path = C.PRIOR_TOTALS_BY_SEASON.get(season, C.PRIOR_SEASON_TOTALS)
    out = {}
    if not os.path.exists(path):
        return out
    for r in csv.DictReader(open(path)):
        pid = r.get("player_id")
        if not pid:
            continue
        rec = {k: _to_float(v) for k, v in r.items()
               if k not in ("player", "team", "player_id", "position")}
        rec["games"] = rec.get("games") or 1
        rec["team"] = r.get("team")  # raw PFF-style string, kept for team-share volume (project.team_share_volume)
        out[pid] = rec
    return out


def load_game_logs():
    """
    player_game_logs.csv — one row per player-game, prior year.
    Used for per-stat variance (floor/ceiling), not just means.
    Returns dict (pkey, tkey) -> list of per-game stat dicts.
    """
    from collections import defaultdict
    out = defaultdict(list)
    if not os.path.exists(C.GAME_LOGS):
        print(f"  [warn] game logs not found at {C.GAME_LOGS}")
        return out
    for r in csv.DictReader(open(C.GAME_LOGS)):
        pkey = norm(r.get("player", ""))
        tkey = norm(r.get("team", ""))
        rec = {k: _to_float(v) for k, v in r.items()
               if k not in ("player", "team", "player_id", "position", "opponent", "date")}
        rec["player_id"] = r.get("player_id")  # keep as string, not a stat
        rec["position"] = r.get("position")
        out[(pkey, tkey)].append(rec)
    return out


def load_game_lines(path):
    """
    hist_lines_closing_wkN.csv (from historical_pull.R --game-lines) --
    one row per game: game_id, week, home_team, away_team, home_spread,
    total. home_spread is the HOME team's own signed spread (negative =
    home favored, per the Odds API convention).

    Returns {week: [rows]}, each row carrying the raw Odds API team name
    strings (WITH mascot, e.g. "Kansas State Wildcats" -- these do NOT
    equal our norm()'d crosswalk team keys, which drop the mascot; use
    find_team_game_line() below to match, not a dict lookup) plus the
    derived home_implied/away_implied team totals.
    """
    from collections import defaultdict
    out = defaultdict(list)
    if not os.path.exists(path):
        return out
    for r in csv.DictReader(open(path)):
        week = r.get("week")
        home_spread = _to_float(r.get("home_spread"))
        total = _to_float(r.get("total"))
        if week is None or home_spread is None or total is None:
            continue
        out[week].append(dict(
            home_team=r.get("home_team", ""), away_team=r.get("away_team", ""),
            home_spread=home_spread, total=total,
            home_implied=total / 2 - home_spread / 2,
            away_implied=total / 2 + home_spread / 2,
        ))
    return out


def _resolve_raw_team(raw_name, known_tkeys):
    """
    Given a normalized raw team name from a game line (WITH mascot, e.g.
    "texasamaggies"), return the single canonical tkey it actually
    represents: the LONGEST key in known_tkeys that's a PREFIX match with
    it (either direction). Prefix, not "appears anywhere" substring --
    the mascot always comes after the school name once norm() strips
    spaces, so the school name is always a genuine prefix of the raw
    string, but an unrelated team's mascot can coincidentally CONTAIN a
    different short team's name mid-string (norm("Duquesne Dukes") ==
    "duquesnedukes" contains "duke" starting at index 8 -- an anywhere
    substring check misidentified Duquesne's game as Duke's). Longest, not
    first or closest-length, because a shorter cousin school's key is
    routinely ALSO a genuine prefix of a raw name that really belongs to a
    longer/more specific team ("texas" prefixes "texasamaggies" too, but
    "texasam" is the real, more specific answer) -- and closest-length
    isn't safe either, since an unrelated cousin's mascot can coincidentally
    be short enough to beat the real team's own mascot on length ("Texas
    A&M Aggies" is shorter than "Texas Longhorns", so a length-heuristic
    picked Texas A&M for a Texas player). Only the longest-known-team-name
    prefix match is unambiguous.
    """
    candidates = [ck for ck in known_tkeys if ck and (raw_name.startswith(ck) or ck.startswith(raw_name))]
    return max(candidates, key=len) if candidates else None


def _best_team_side(tkey, week, lines_by_week, canonical_tkeys):
    """
    Find tkey's (our normalized, no-mascot team key) game this week among
    Odds API game lines (WITH mascot) -- same approach historical_pull.R's
    team matcher uses, since Odds names routinely aren't exact matches for
    ours (see load_team_map's docstring on the same issue).

    For each raw team name in the slate, resolves which SPECIFIC real team
    it represents via _resolve_raw_team (longest known-team match, not a
    plain substring/length heuristic -- see that function's docstring for
    why cheaper heuristics misfire on cousin schools like Texas / Texas
    A&M / Texas State / Texas Tech, or Washington / Washington State),
    then checks that resolution against tkey. tkey itself is always added
    to the known-team universe for this check, in case it's missing from
    canonical_tkeys (e.g. an FCS opponent absent from team_ratings).

    Returns (game_dict, side) for tkey's game, or (None, None) if tkey
    isn't in this week's lines at all (bye week, or a mismatch worth
    adding to team_map.csv).
    """
    if not tkey:
        return None, None
    known = set(canonical_tkeys) | {tkey}
    for g in lines_by_week.get(week, []):
        h, a = norm(g["home_team"]), norm(g["away_team"])
        if _resolve_raw_team(h, known) == tkey:
            return g, "home"
        if _resolve_raw_team(a, known) == tkey:
            return g, "away"
    return None, None


def find_team_game_line(tkey, week, lines_by_week, canonical_tkeys):
    """
    Returns (implied_total, own_spread) for tkey's game this week, or
    (None, None) if it isn't in this week's lines. See _best_team_side for
    the matching rule.
    """
    g, side = _best_team_side(tkey, week, lines_by_week, canonical_tkeys)
    if g is None:
        return None, None
    return (g["home_implied"], g["home_spread"]) if side == "home" else (g["away_implied"], -g["home_spread"])


def find_opponent_tkey(tkey, week, lines_by_week, canonical_tkeys):
    """
    Like find_team_game_line, but resolves the OPPONENT to one of
    canonical_tkeys (e.g. def_index.keys()) instead of returning implied
    total/spread -- def_index and the success-rate index are keyed by our
    own canonical (CFBD-style) tkeys, not the raw Odds API name string.
    Uses the same longest-known-team resolution as _best_team_side (see
    _resolve_raw_team's docstring) so the opponent side isn't vulnerable
    to the same cousin-school ambiguity as tkey's own side.
    """
    g, side = _best_team_side(tkey, week, lines_by_week, canonical_tkeys)
    if g is None:
        return None
    opp_raw = norm(g["away_team"]) if side == "home" else norm(g["home_team"])
    return _resolve_raw_team(opp_raw, canonical_tkeys)


def league_avg_implied(lines_by_week, week):
    """Mean implied team total across the whole week's slate -- the pace
    multiplier's denominator (a team's own implied total relative to a
    typical team's, that week)."""
    import statistics as stats
    vals = []
    for g in lines_by_week.get(week, []):
        vals.append(g["home_implied"])
        vals.append(g["away_implied"])
    return stats.mean(vals) if vals else None


_TEAM_GRADE_ALIASES = {
    "miamifl": "miami", "mississippi": "olemiss", "usf": "southflorida",
    "connecticut": "uconn", "miamioh": "miamiohio",
    "northcarolinastate": "ncstate", "louisianamonroe": "ulm",
    "samhoustonstate": "samhouston", "massachusetts": "umass",
}


def load_team_grades(path):
    """
    team_pff_grades_2025.csv -- PFF's own TEAM-level grades (not
    aggregated from individual players the way build_def_index is),
    one row per team: record/pf/pa plus grade_{over,off,pass,pblk,recv,
    run,rblk,def,rdef,tack,prsh,cov,spec}. Season-long aggregate, same
    lookahead caveat as everything else team-level in this repo.

    Keyed by tkey. 9 of 136 team names needed an alias (Miami (FL) ->
    Miami, Mississippi -> Ole Miss, etc, verified against pff_team_map.csv's
    existing canonical names) -- _TEAM_GRADE_ALIASES, checked by norm()
    equality only (no fuzzy substring matching -- see build_pff_team_map.py
    on why that's unsafe for team names).
    """
    out = {}
    if not os.path.exists(path):
        return out
    grade_cols = ["grade_over", "grade_off", "grade_pass", "grade_pblk", "grade_recv",
                 "grade_run", "grade_rblk", "grade_def", "grade_rdef", "grade_tack",
                 "grade_prsh", "grade_cov", "grade_spec"]
    for r in csv.DictReader(open(path)):
        team = r.get("team", "")
        if not team:
            continue
        n = norm(team)
        n = _TEAM_GRADE_ALIASES.get(n, n)
        rec = {c: _to_float(r.get(c)) for c in grade_cols}
        rec["pf"] = _to_float(r.get("pf"))
        rec["pa"] = _to_float(r.get("pa"))
        out[n] = rec
    return out


def load_team_ratings(path):
    """
    team_ratings_2025.csv (CFBD-style team advanced stats, "Team" column
    plus "Offense/Defense RushingPlays/PassingPlays Rate/SuccessRate", and
    OffAdj/DefAdj/RPOffense/RPDefense/rank_TARP -- despite the filename,
    these last five describe continuity INTO 2026 (2026 coaching +
    returning production already applied), not into 2025: confirmed
    OffAdj is a monotonic function of RPOffense, roughly -6..+6. See
    project.tarp_adj -- ONLY meaningful for --season 2026 runs.
    Season-long aggregate -- same lookahead caveat as the existing PFF-
    grade opponent adjustment (both are full-2025-season snapshots used
    regardless of week; a truly no-lookahead version would need weekly
    CFBD advanced stats, which isn't available here yet).

    Keyed by tkey (norm of the CFBD-style name) -- this file's own "Team"
    column is already CFBD-style, and load_pff()'s p["tkey"] is too now
    that pff_team_map.csv fills in pff2c, so both sides land in the same
    key space without any translation needed here.
    """
    out = {}
    if not os.path.exists(path):
        return out
    for r in csv.DictReader(open(path)):
        team = r.get("Team", "")
        if not team:
            continue
        rec = {}
        for dst, col in [
            ("off_rush_rate", "Offense RushingPlays Rate"), ("off_pass_rate", "Offense PassingPlays Rate"),
            ("off_rush_sr", "Offense RushingPlays SuccessRate"), ("off_pass_sr", "Offense PassingPlays SuccessRate"),
            ("def_rush_rate", "Defense RushingPlays Rate"), ("def_pass_rate", "Defense PassingPlays Rate"),
            ("def_rush_sr", "Defense RushingPlays SuccessRate"), ("def_pass_sr", "Defense PassingPlays SuccessRate"),
            ("off_adj", "OffAdj"), ("def_adj", "DefAdj"),
            ("rp_offense", "RPOffense"), ("rp_defense", "RPDefense"), ("rank_tarp", "rank_TARP"),
        ]:
            rec[dst] = _to_float(r.get(col))
        out[norm(team)] = rec
    return out


# ourlads.com offense position labels -> this project's own skill-position
# codes (player_season_totals.csv's "position" column: QB, HB, WR, TE, FB).
# Everything not listed (OL: LT/LG/C/RG/RT/QG/QT/SG, ST) is excluded --
# depth rank has no meaningful volume-projection effect for those.
_DEPTH_POS_MAP = {
    "QB": "QB",
    "RB": "HB", "RB-A": "HB", "RB-B": "HB",
    "FB": "FB",
    "WR": "WR", "WR-X": "WR", "WR-Z": "WR", "WR-SL": "WR",
    "WR-H": "WR", "WR-F": "WR", "WR-Y": "WR",
    "SB": "WR", "SB-A": "WR", "SB-Z": "WR",
    "TE": "TE", "TE-Y": "TE", "TE-H": "TE",
}


def load_depth_chart_overrides(path="depth_chart_overrides.csv"):
    """
    depth_chart_overrides.csv -- hand-verified corrections to the ourlads
    scrape, keyed by norm(player_name). ourlads is pulled ONCE, before the
    season starts, so it can't see what a team actually did once games are
    played (e.g. a preseason RB1 who was actually used as the 3rd back in
    the real opener) -- this file exists to layer in those corrections
    without touching the raw scrape itself (pull_depth_charts.py's output
    stays exactly what ourlads said, auditable on its own). Every row
    needs a note + source; this is manually curated, not re-scraped.
    Returns {} if the file doesn't exist (fully opt-in, same pattern as
    every other optional file load in this module).
    """
    out = {}
    if not os.path.exists(path):
        return out
    for r in csv.DictReader(open(path)):
        bucket = _DEPTH_POS_MAP.get((r.get("position") or "").strip(), (r.get("position") or "").strip())
        try:
            rank = int(r.get("depth_rank"))
        except (TypeError, ValueError):
            continue
        key = norm(r.get("name", ""))
        if not key:
            continue
        out[key] = dict(position=bucket, depth_rank=rank, team=r.get("team", ""))
    return out


def load_depth_chart(path, overrides_path="depth_chart_overrides.csv"):
    """
    depth_charts.csv (pull_depth_charts.py, scraped from ourlads.com) --
    current-season offense starter/role data. Used ONLY to nudge pure-
    prior-year (week <= config.PRIOR_ONLY_UNTIL_WEEK) volume projections
    for a player whose role a stale prior-year rate can't see (a backup
    who won a starting job, a starter who lost one). See
    project.depth_rank_adj / config.DEPTH_RANK_MULT.

    Keyed by norm(player_name) ONLY, not by team: ourlads' team names
    ("North Carolina Tar Heels") don't cleanly resolve to this project's
    canonical CFBD-style team keys the way team_map.csv/pff_team_map.csv
    do (those are hand-verified exception tables built for ~140 specific
    names, not a general mascot-suffix stripper) -- a name-only join
    follows the same pattern already used elsewhere in this codebase
    (e.g. load_pff's pkey). A same-name collision across two teams is
    possible but rare for skill-position players.

    If a player appears on multiple qualifying rows, the LOWEST
    depth_rank (highest on the chart) wins. load_depth_chart_overrides()
    is applied last and always wins over the scrape -- see that
    function's docstring on why the scrape alone goes stale once games
    are actually played.
    """
    out = {}
    if not os.path.exists(path):
        return out
    for r in csv.DictReader(open(path)):
        if r.get("side") != "offense":
            continue
        bucket = _DEPTH_POS_MAP.get((r.get("position") or "").strip())
        if not bucket:
            continue
        try:
            rank = int(r.get("depth_rank"))
        except (TypeError, ValueError):
            continue
        key = norm(r.get("name", ""))
        if not key:
            continue
        prev = out.get(key)
        if prev is None or rank < prev["depth_rank"]:
            out[key] = dict(position=bucket, depth_rank=rank)
    for key, rec in load_depth_chart_overrides(overrides_path).items():
        out[key] = dict(position=rec["position"], depth_rank=rec["depth_rank"])
    return out
