"""
project.py — the projection engine.

For each player + market, project the stat as:

    projection = expected_volume  x  efficiency_rate  x  opponent_adjustment

- expected_volume  : prior-year per-game rate (attempts / targets / carries)
- efficiency_rate  : prior-year yds-per-unit, shrunk toward the position mean
                     so small samples don't produce extreme numbers
- opponent_adj     : scales the projection by the opponent defensive unit's
                     strength (COV for pass markets, RDEF for rush), using the
                     PFF grades from the crosswalk

Game logs (if present) add a variance estimate per projection so a boom/bust
player is flagged differently from a steady one at the same mean.

This module is deliberately transparent and tunable — no black-box fit. Every
constant lives in config.py.
"""
import statistics as stats
import config as C


# ---------- efficiency helpers ----------

def _rate(numer, denom):
    if not numer or not denom or denom == 0:
        return None
    return numer / denom


def compute_player_rates(tot):
    """Derive per-unit efficiency rates from a season-totals dict."""
    return {
        "ypa":        _rate(tot.get("pass_yds"), tot.get("pass_att")),   # yds/attempt
        "ypc":        _rate(tot.get("rush_yds"), tot.get("rush_att")),   # yds/carry
        "ypt":        _rate(tot.get("rec_yds"),  tot.get("targets")),    # yds/target
        "catch_rate": _rate(tot.get("receptions"), tot.get("targets")),  # rec/target
    }


STAT_COLS = ("pass_att", "pass_yds", "rush_att", "rush_yds",
            "targets", "receptions", "rec_yds",
            "pass_td", "rush_td", "rec_td")

# Which TD column shares a market's volume column -- e.g. pass_td happens on
# pass attempts, so its rate is pass_td / pass_att. Used for DK-style
# fantasy-point projections (see build_dfs_page_data.py), not the betting
# projections themselves.
TD_COL_BY_VOL = {"pass_att": "pass_td", "rush_att": "rush_td", "targets": "rec_td"}


def blend_prior_and_current(prior_tot, current_games_list):
    """
    Week 4+ design (config.PRIOR_ONLY_UNTIL_WEEK): blend real prior-year
    (2024) totals with this season's own games played so far, weighted by
    how many current-season games have accumulated -- more current-season
    games means more weight on current-season signal (config.
    CURRENT_SEASON_BLEND_GAMES controls how fast).

    Returns a totals-shaped dict (games + the raw stat-total columns) so
    compute_player_rates/shrink/project_player_market consume it exactly
    like any other totals record -- the stat columns hold TOTALS scaled to
    an "effective games" count (prior_games + current_games), not real
    per-game counts, so that dividing by that games figure recovers the
    correctly-blended per-game rate elsewhere in the pipeline.
    """
    current_games_list = current_games_list or []
    n_cur = len(current_games_list)
    w = n_cur / (n_cur + C.CURRENT_SEASON_BLEND_GAMES) if n_cur else 0.0

    prior_games = (prior_tot or {}).get("games") or 0
    effective_games = max(prior_games + n_cur, 1)

    out = {"games": effective_games}
    for col in STAT_COLS:
        cur_total = sum((g.get(col) or 0) for g in current_games_list)
        cur_per_game = (cur_total / n_cur) if n_cur else None
        prior_val = (prior_tot or {}).get(col)
        prior_per_game = (prior_val / prior_games) if (prior_val is not None and prior_games) else None

        if cur_per_game is None and prior_per_game is None:
            continue
        elif cur_per_game is None:
            blended_per_game = prior_per_game
        elif prior_per_game is None:
            blended_per_game = cur_per_game
        else:
            blended_per_game = w * cur_per_game + (1 - w) * prior_per_game
        out[col] = blended_per_game * effective_games
    return out


# Volume columns a team's roster genuinely competes for -- rush carries
# among running backs, targets among receivers. Pass attempts aren't
# included: a team doesn't really have a "shared pool" of pass attempts
# the way it has one pool of carries or targets (QB competitions are a
# real thing, but not a volume-split problem the way a backfield or WR
# room is).
SHARE_VOL_COLS = ("rush_att", "targets")


def build_team_volume_totals(records, vol_cols=SHARE_VOL_COLS):
    """
    Sum vol_cols across all players sharing the same team, from any
    totals-shaped record set -- e.g. the `prior` dict grouped by each
    player's OWN prior-year team (not their current one), or the current
    `totals` dict grouped by tkey. `records` is an iterable of
    (team_key, record) pairs so the caller controls which "team" a record
    counts toward (this matters for a transfer: their history counts
    toward the OLD team's total, not the new one).

    "games" per team is the max games among its players (a team plays a
    fixed schedule; the most-used player's game count is the best proxy
    available from season-level data alone).
    Returns {team_key: {vol_col: total, "games": n}}.
    """
    from collections import defaultdict
    sums = defaultdict(lambda: defaultdict(float))
    games = defaultdict(list)
    for team_key, rec in records:
        if not team_key or not rec:
            continue
        for c in vol_cols:
            v = rec.get(c)
            if v:
                sums[team_key][c] += v
        g = rec.get("games")
        if g:
            games[team_key].append(g)
    out = {}
    for team_key, cols in sums.items():
        out[team_key] = dict(cols)
        out[team_key]["games"] = max(games[team_key]) if games[team_key] else 1
    return out


def team_share_volume(player_total, source_team_total, target_team_totals, vol_col):
    """
    A player's projected per-game volume as their historical SHARE of a
    team's total pool, rather than their own raw total/games -- ties
    volume to a team-level total (more stable than any one player's raw
    count) and, for a transfer, correctly re-bases their earned share
    onto their NEW team's pool instead of assuming their old raw count
    carries over unchanged into a different offense.

    player_total   : this player's own season total for vol_col.
    source_team_total: the TEAM TOTAL for vol_col on the team the player
                       actually earned player_total on (their prior team,
                       which for a transfer differs from their current one).
    target_team_totals: build_team_volume_totals()'s record for the team
                       being projected FOR (their current team).
    Returns None (caller falls back to raw total/games) if any input is
    missing or zero -- e.g. a true freshman with no prior team total.
    """
    if not player_total or not source_team_total or not target_team_totals:
        return None
    team_vol = target_team_totals.get(vol_col)
    team_games = target_team_totals.get("games")
    if not team_vol or not team_games:
        return None
    share = player_total / source_team_total
    return (team_vol / team_games) * share


def position_means(all_totals):
    """
    League-wide VOLUME-WEIGHTED mean of each efficiency rate, for shrinkage
    targets: sum(yards) / sum(units), not mean(yards/units) per player.

    Weighted on purpose -- an unweighted average-of-ratios lets a backup
    with 3 garbage-time targets skew the target exactly as much as a
    100-target starter, and small samples run noisy. Measured effect on
    the 2024 prior-year pool: unweighted understated ypt (yds/target) by
    ~0.99 and ypc (yds/carry) by ~0.27, which was the direct cause of the
    model's systematic under-projection on reception_yds/rush_yds in the
    week 1-15 backtest -- shrinking a well-sampled player's real
    efficiency toward an artificially low target pulls it down regardless
    of how good the player actually is.
    """
    pairs = {"ypa": ("pass_yds", "pass_att"), "ypc": ("rush_yds", "rush_att"),
             "ypt": ("rec_yds", "targets")}
    out = {}
    for key, (num_col, den_col) in pairs.items():
        num = sum((tot.get(num_col) or 0) for tot in all_totals.values() if tot.get(den_col))
        den = sum((tot.get(den_col) or 0) for tot in all_totals.values() if tot.get(den_col))
        out[key] = (num / den) if den else 0.0
    num = sum((tot.get("receptions") or 0) for tot in all_totals.values() if tot.get("targets"))
    den = sum((tot.get("targets") or 0) for tot in all_totals.values() if tot.get("targets"))
    out["catch_rate"] = (num / den) if den else 0.0
    return out


def shrink(player_rate, pos_mean, games):
    """
    Regress a player's rate toward the position mean based on sample size.
    weight = games / (games + SHRINKAGE_GAMES).
    """
    if player_rate is None:
        return pos_mean
    g = games or 0
    w = g / (g + C.SHRINKAGE_GAMES)
    return w * player_rate + (1 - w) * pos_mean


# ---------- opponent adjustment ----------

def build_def_index(pff_players):
    """
    Aggregate each team's defensive grade by unit into a z-scored index.
    Returns {tkey: {"def_grade_cov": z, "def_grade_rdef": z, ...}}.
    Higher z = STRONGER defense (suppresses the stat), so the adjustment
    multiplies projections DOWN against strong D and UP against weak D.
    """
    from collections import defaultdict
    unit_cols = ["def_grade_cov", "def_grade_rdef", "def_grade_prush", "def_grade_def"]
    team_vals = defaultdict(lambda: defaultdict(list))
    for p in pff_players:
        if p.get("side") != "Defense":
            continue
        for col in unit_cols:
            v = p.get(col, "")
            try:
                team_vals[p["tkey"]][col].append(float(v))
            except (ValueError, TypeError):
                pass
    # team-level mean grade per unit
    team_unit = {t: {c: (stats.mean(vs) if vs else None) for c, vs in units.items()}
                 for t, units in team_vals.items()}
    # z-score each unit across teams
    for col in unit_cols:
        vals = [tu[col] for tu in team_unit.values() if tu.get(col) is not None]
        if len(vals) < 2:
            continue
        m, sd = stats.mean(vals), (stats.pstdev(vals) or 1.0)
        for tu in team_unit.values():
            if tu.get(col) is not None:
                tu[col] = (tu[col] - m) / sd
    return team_unit


def build_success_rate_index(team_ratings):
    """
    Z-score each team's DEFENSE allowed success rate, rush and pass
    separately, across the league -- an independent (different data
    source/methodology) complement to build_def_index's PFF-grade z-score.
    Higher z = allows MORE successful plays = weaker defense (opposite
    sign convention from build_def_index's grade z, handled in
    success_rate_adj).
    """
    cols = ["def_rush_sr", "def_pass_sr"]
    vals = {c: [t[c] for t in team_ratings.values() if t.get(c) is not None] for c in cols}
    stat = {c: (stats.mean(vals[c]), stats.pstdev(vals[c]) or 1.0) for c in cols if vals[c]}
    out = {}
    for tkey, t in team_ratings.items():
        out[tkey] = {}
        for c in cols:
            if c in stat and t.get(c) is not None:
                m, sd = stat[c]
                out[tkey][c] = (t[c] - m) / sd
    return out


def success_rate_adj(sr_index, opp_tkey, side, stat):
    """
    Multiplier centered on 1.0, from the CFBD success-rate index (NOT the
    PFF-grade one -- see opponent_adj). High z (defense allows more
    successful plays than average) -> >1 (inflates); low z -> <1.

    Strength is keyed by stat (config.SUCCESS_RATE_STRENGTH_BY_STAT), not
    just side: pass_yds and the receiving markets are both side="pass"
    but respond in OPPOSITE directions to this knob (see config.py).
    """
    if side not in ("pass", "rush"):
        return 1.0
    tu = sr_index.get(opp_tkey)
    col = "def_rush_sr" if side == "rush" else "def_pass_sr"
    if not tu or tu.get(col) is None:
        return 1.0
    strength = C.SUCCESS_RATE_STRENGTH_BY_STAT.get(stat, C.SUCCESS_RATE_ADJ_STRENGTH)
    return 1.0 + strength * tu[col]


def build_matchup_grade_index(team_grades):
    """
    Z-score each of the grade columns config.MATCHUP_UNITS references,
    across the league -- for matchup_grade_adj's differential (this
    team's own unit grade vs the opponent's complementary one).
    """
    cols = sorted({c for pair in C.MATCHUP_UNITS.values() for c in pair})
    vals = {c: [t[c] for t in team_grades.values() if t.get(c) is not None] for c in cols}
    stat = {c: (stats.mean(vals[c]), stats.pstdev(vals[c]) or 1.0) for c in cols if vals[c]}
    out = {}
    for tkey, t in team_grades.items():
        out[tkey] = {}
        for c in cols:
            if c in stat and t.get(c) is not None:
                m, sd = stat[c]
                out[tkey][c] = (t[c] - m) / sd
    return out


def matchup_grade_adj(grade_index, own_tkey, opp_tkey, market_key):
    """
    Multiplier centered on 1.0 from the z-scored DIFFERENTIAL between this
    team's own relevant unit grade and the opponent's complementary one
    (config.MATCHUP_UNITS) -- e.g. for a rush market, this team's run-
    blocking z minus the opponent's run-defense z. Positive diff (this
    team's unit graded better than the matchup opponent's) -> >1.
    """
    pair = C.MATCHUP_UNITS.get(market_key)
    if not pair:
        return 1.0
    off_col, def_col = pair
    own, opp = grade_index.get(own_tkey), grade_index.get(opp_tkey)
    off_z = own.get(off_col) if own else None
    def_z = opp.get(def_col) if opp else None
    if off_z is None or def_z is None:
        return 1.0
    return 1.0 + C.MATCHUP_ADJ_STRENGTH * (off_z - def_z)


def build_tarp_index(team_ratings):
    """
    Z-score each team's off_adj / def_adj (team_ratings_2025.csv's OffAdj/
    DefAdj -- 2026 coaching + returning-production-adjusted strength)
    across the league. ONLY meaningful for --season 2026 (see
    load_team_ratings / tarp_adj).
    """
    cols = ["off_adj", "def_adj"]
    vals = {c: [t[c] for t in team_ratings.values() if t.get(c) is not None] for c in cols}
    stat = {c: (stats.mean(vals[c]), stats.pstdev(vals[c]) or 1.0) for c in cols if vals[c]}
    out = {}
    for tkey, t in team_ratings.items():
        out[tkey] = {}
        for c in cols:
            if c in stat and t.get(c) is not None:
                m, sd = stat[c]
                out[tkey][c] = (t[c] - m) / sd
    return out


def tarp_adj(tarp_index, own_tkey, opp_tkey):
    """
    Multiplier centered on 1.0 from the z-scored DIFFERENTIAL between this
    team's own off_adj and the opponent's def_adj -- a team whose offense
    returns strong (positive OffAdj) against a defense that doesn't
    (negative DefAdj) gets a boost. Applies uniformly across all markets
    (OffAdj/DefAdj aren't split by rush/pass, unlike matchup_grade_adj).

    UNVALIDATED (config.TARP_ADJ_STRENGTH) -- see that constant's comment.
    """
    own, opp = tarp_index.get(own_tkey), tarp_index.get(opp_tkey)
    off_z = own.get("off_adj") if own else None
    def_z = opp.get("def_adj") if opp else None
    if off_z is None or def_z is None:
        return 1.0
    return 1.0 + C.TARP_ADJ_STRENGTH * (off_z - def_z)


def depth_rank_adj(depth_rec):
    """
    Flat volume multiplier from a scraped ourlads.com depth-chart rank
    (see data_load.load_depth_chart) -- 1.0 (no-op) if depth_rec is None,
    i.e. no --depth-chart file was supplied, or this player didn't match
    one by name. Caller is responsible for only passing a real depth_rec
    during pure-prior-year weeks (week <= config.PRIOR_ONLY_UNTIL_WEEK) --
    once real current-season games exist, the player's own rate already
    reflects their role.

    UNVALIDATED (config.DEPTH_RANK_MULT) -- see that constant's comment.
    """
    if not depth_rec:
        return 1.0
    return C.DEPTH_RANK_MULT.get(depth_rec["depth_rank"], C.DEPTH_RANK_MULT_DEFAULT)


def opponent_adj(def_index, opp_tkey, def_unit):
    """
    Multiplier centered on 1.0. Strong defense (high z) -> <1 (suppresses);
    weak defense (low z) -> >1 (inflates).
    """
    tu = def_index.get(opp_tkey)
    if not tu or tu.get(def_unit) is None:
        return 1.0
    z = tu[def_unit]
    return 1.0 - C.OPP_ADJ_STRENGTH * z


# ---------- game context (this week's spread/total) ----------

def game_context_adj(team_implied, league_avg_implied, team_spread, side):
    """
    Volume multiplier from this week's specific matchup, on top of the
    player's own season-average rate -- two independent effects:

      pace   : team_implied / league_avg_implied. A team implied for more
               points than a typical team that week is expected to run
               more offensive plays -- scales ALL volume (pass and rush
               alike) up or down. Clipped to +/- config.PACE_CLIP so one
               extreme projected blowout can't swing volume unrealistically.
      script : normalized spread. A big favorite tends to lean run-heavy
               (clock control, protecting a lead); a big underdog tends to
               lean pass-heavy (playing from behind). Only applied to the
               market's own side -- rush markets get the rush script,
               pass/receiving markets get the pass script.

    Returns 1.0 (no-op) if either input is missing, so this is silent and
    harmless when no game-lines data is loaded for a player's game.
    """
    if team_implied is None or not league_avg_implied:
        pace = 1.0
    else:
        pace = team_implied / league_avg_implied
        pace = max(1 - C.PACE_CLIP, min(1 + C.PACE_CLIP, pace))

    if team_spread is None or side not in ("pass", "rush"):
        script = 1.0
    else:
        z = max(-1.0, min(1.0, -team_spread / C.SPREAD_SCALE))  # favored -> positive z
        script = (1 + C.RUSH_SCRIPT_STRENGTH * z) if side == "rush" else (1 - C.PASS_SCRIPT_STRENGTH * z)

    return pace * script


# ---------- variance from game logs ----------

def stat_variance(logs, stat_col):
    """Std dev of a stat across a player's prior-year games (None if <3 games)."""
    if not logs:
        return None
    vals = [g.get(stat_col) for g in logs if g.get(stat_col) is not None]
    if len(vals) < 3:
        return None
    return stats.pstdev(vals)


# ---------- the projection ----------

def project_player_market(tot, logs, rates_shrunk, market_key, mdef,
                          def_index, opp_tkey, vol_adj=1.0, extra_adj=1.0,
                          per_game_vol_override=None):
    """
    Produce one projection row for a player + market.
    vol_adj: optional extra volume multiplier from this week's specific
    game context (see game_context_adj) -- defaults to 1.0 (no effect).
    extra_adj: optional extra opponent multiplier from a second, independent
    opponent signal (see success_rate_adj) -- combines with the PFF-grade
    opponent_adj() below rather than replacing it. Defaults to 1.0.
    per_game_vol_override: if given (see team_share_volume), replaces the
    tot[vol_col]/games calculation entirely -- e.g. a team-share-based
    volume estimate instead of the player's own raw rate.
    Returns dict with mean projection, variance, and the components (for the
    impact page to show its work), or None if the player lacks the volume.
    """
    games = tot.get("games") or 1
    vol_col = mdef["volume"]
    total_vol = tot.get(vol_col)

    # volume floor: skip players without enough prior sample for this side
    min_vol = C.MIN_PRIOR_VOLUME.get(vol_col)
    if total_vol is None or (min_vol and total_vol < min_vol):
        return None

    base_vol = per_game_vol_override if per_game_vol_override is not None else (total_vol / games)
    per_game_vol = base_vol * vol_adj
    adj = opponent_adj(def_index, opp_tkey, mdef["def_unit"]) * extra_adj
    # Clamp the TOTAL context multiplier (vol_adj x adj), not adj alone --
    # vol_adj can independently reach ~2.3x on its own, so bounding adj by
    # itself doesn't stop the product from still running away. Scale adj
    # only, so per_game_vol (the "volume" component shown in the impact
    # page's breakdown) keeps its own untouched meaning.
    lo, hi = C.TOTAL_ADJ_CLAMP
    total_mult = vol_adj * adj
    if total_mult > hi and total_mult > 0:
        adj *= hi / total_mult
    elif total_mult < lo:
        adj *= (lo / total_mult) if total_mult != 0 else 1.0

    eff_key = mdef["eff"]
    if eff_key is None:
        # pure-volume market (attempts): project volume itself
        proj = per_game_vol * adj
        components = dict(volume=round(per_game_vol, 2), efficiency=None,
                          opp_adj=round(adj, 3))
    else:
        eff = rates_shrunk.get(eff_key)
        if eff is None:
            return None
        proj = per_game_vol * eff * adj
        components = dict(volume=round(per_game_vol, 2),
                          efficiency=round(eff, 3), opp_adj=round(adj, 3))

    var = stat_variance(logs, mdef["stat"])
    return dict(
        market=market_key, stat=mdef["stat"],
        projection=round(proj, 1),
        proj_sd=(round(var, 1) if var is not None else None),
        components=components,
    )
