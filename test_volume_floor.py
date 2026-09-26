#!/usr/bin/env python3
"""Checks for the volume floor in project.project_player_market.

config.MIN_PRIOR_VOLUME is a FULL-SEASON total. It only reads as a per-game
bar when `games` is a full season, and since the blend started handing this
function current-season-only players (config.CURRENT_TOTALS_BY_SEASON) it
often isn't: week 4 of 2026 had first-year starters whose whole record was
three games, where 100 pass attempts is unreachable for anyone short of 33 a
game. Eight of the fourteen-game main slate's starting quarterbacks had no
projection at all.

The floor is therefore prorated to the games on hand, but only from
MIN_RATE_FLOOR_GAMES up -- one big game is not a rate, and that is the case
the floor is genuinely for. These checks pin both halves, plus the two
behaviours that must NOT change: a full prior season keeps the original bar,
and an explicit volume override skips the floor entirely.

Run:  python3 test_volume_floor.py
"""
import sys

import config as C
import project as P

MDEF = C.MARKETS["player_pass_attempts"]      # pure-volume market: no eff needed
FLOOR = C.MIN_PRIOR_VOLUME["pass_att"]         # 100 attempts over a season


def projected(total_vol, games, override=None):
    """True when the floor let this sample through."""
    out = P.project_player_market(
        tot={"games": games, "pass_att": total_vol},
        logs=[], rates_shrunk={}, market_key="player_pass_attempts", mdef=MDEF,
        def_index={}, opp_tkey=None, per_game_vol_override=override,
    )
    return out is not None


def main():
    g = C.MIN_RATE_FLOOR_GAMES
    checks = [
        # a full prior season is unchanged: the original bar, both sides of it
        (projected(FLOOR, 12), "a full season exactly at the floor was rejected"),
        (not projected(FLOOR - 1, 12), "a full season under the floor was let through"),
        # the case this exists for: a 3-game starter at 28 attempts a game
        (projected(84, 3), "a 3-game starter with 84 attempts (28/gm) was rejected"),
        # ...and the bar is still a bar at 3 games -- 24 attempts is 8/gm,
        # under the 8.3/gm the season floor works out to
        (not projected(24, 3), "8 attempts a game slipped past the prorated floor"),
        (projected(26, 3), "8.7 attempts a game was rejected by the prorated floor"),
        # one big game is not a rate: held to the unprorated season number
        (not projected(40, 1), "a 1-game 40-attempt sample was let through"),
        (not projected(FLOOR - 1, 1), "a 1-game sample was prorated when it should not be"),
        (projected(FLOOR, 1), "a 1-game sample clearing the FULL floor was rejected"),
        # the proration switches on exactly at MIN_RATE_FLOOR_GAMES
        (projected(FLOOR * g / C.FLOOR_SEASON_GAMES + 1, g),
         f"proration did not apply at {g} games"),
        (not projected(FLOOR * (g - 1) / C.FLOOR_SEASON_GAMES + 1, g - 1),
         f"proration applied below {g} games"),
        # never scale UP: prior year plus this one is past a full season
        (projected(FLOOR, 15), "a 15-game sample at the floor was rejected"),
        # an override replaces the player's own count, so the floor is moot
        (projected(0, 3, override=20.0), "a volume override did not skip the floor"),
        (projected(None, 3, override=20.0), "a volume override did not skip a missing count"),
        # no count at all is still no projection
        (not projected(None, 3), "a missing volume count was projected anyway"),
    ]
    fails = [m for ok, m in checks if not ok]
    for f in fails:
        print(f"  FAIL {f}")
    print(f"  volume floor: {len(checks) - len(fails)}/{len(checks)} checks passed")
    print("PASS" if not fails else "FAIL")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
