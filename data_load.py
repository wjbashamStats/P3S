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


def load_prior_totals():
    """
    player_prior_totals.csv -- real prior-year (2024) rates, keyed by
    player_id ONLY (not (pkey, tkey)): a transferred player's 2024 team
    isn't their current one, so team can't be part of this join key.
    Callers match a current-roster player to their prior-year record via
    player_id, and keep the CURRENT team/roster from the 2025 side.
    Returns {} if the file doesn't exist (no 2024 data provided).
    """
    out = {}
    if not os.path.exists(C.PRIOR_SEASON_TOTALS):
        return out
    for r in csv.DictReader(open(C.PRIOR_SEASON_TOTALS)):
        pid = r.get("player_id")
        if not pid:
            continue
        rec = {k: _to_float(v) for k, v in r.items()
               if k not in ("player", "team", "player_id", "position")}
        rec["games"] = rec.get("games") or 1
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


def find_team_game_line(tkey, week, lines_by_week):
    """
    Substring-match tkey (our normalized, no-mascot team key) against a
    week's game lines (Odds API names, WITH mascot) -- same approach
    historical_pull.R's team matcher uses, since Odds names routinely
    aren't exact matches for ours (see load_team_map's docstring on the
    same issue). Returns (implied_total, own_spread) for whichever side
    tkey matched, or (None, None) if the team isn't in this week's lines
    (bye week, or a mismatch worth adding to team_map.csv).
    """
    if not tkey:
        return None, None
    for g in lines_by_week.get(week, []):
        h, a = norm(g["home_team"]), norm(g["away_team"])
        if tkey in h or h in tkey:
            return g["home_implied"], g["home_spread"]
        if tkey in a or a in tkey:
            return g["away_implied"], -g["home_spread"]
    return None, None


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
