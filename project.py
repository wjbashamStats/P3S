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
            "targets", "receptions", "rec_yds")


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
        script = (1 + C.SCRIPT_ADJ_STRENGTH * z) if side == "rush" else (1 - C.SCRIPT_ADJ_STRENGTH * z)

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
                          def_index, opp_tkey, vol_adj=1.0):
    """
    Produce one projection row for a player + market.
    vol_adj: optional extra volume multiplier from this week's specific
    game context (see game_context_adj) -- defaults to 1.0 (no effect).
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

    per_game_vol = (total_vol / games) * vol_adj
    adj = opponent_adj(def_index, opp_tkey, mdef["def_unit"])

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
