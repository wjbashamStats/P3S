"""
config.py — central settings for the player prop model + impact page backend.

Everything downstream reads from here: file paths, API keys, model tuning
constants, and the market definitions that tie a prop type to the stat it
projects and the defensive unit that adjusts it.
"""
import os

# ---------------- SEASON / WEEK ----------------
SEASON = 2026
# Weeks 1-3 lean on prior-year rates only (no current-season signal yet);
# week 4+ can blend in current-season game logs as they accumulate.
PRIOR_ONLY_UNTIL_WEEK = 3

# ---------------- API KEYS ----------------
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "0d3e64aacda40042d78ce34c80417125")
CFBD_API_KEY = os.environ.get("CFBD_API_KEY",
                              "Qxp0ObiPl4OXqqhG3Htf1lje5AfzU5UEWTFgw9qrrWzNmdBs5pJ1I2Iay98dCR3a")

ODDS_SPORT  = "americanfootball_ncaaf"
ODDS_REGION = "us"
ODDS_FORMAT = "american"

# ---------------- FILE PATHS ----------------
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DATA_DIR      = os.path.join(BASE_DIR, "data")          # your stat inputs live here
OUTPUT_DIR    = os.path.join(BASE_DIR, "output")        # generated tables + json
PFF_CROSSWALK = os.path.join(DATA_DIR, "master_crosswalk.csv")  # the file we just built
TEAM_MAP      = os.path.join(DATA_DIR, "team_map.csv")   # pff_team -> cfbd_team -> odds_team

# Prior-year stat inputs (you have both granularities):
SEASON_TOTALS = os.path.join(DATA_DIR, "player_season_totals.csv")  # one row per player
GAME_LOGS     = os.path.join(DATA_DIR, "player_game_logs.csv")      # one row per player-game

# ---------------- MARKET DEFINITIONS ----------------
# Each Odds API prop market maps to: the stat we project, the volume + efficiency
# columns it decomposes into, and which defensive grade adjusts it.
# def_unit is a column family in the PFF crosswalk (def_grade_cov, def_grade_rdef...).
MARKETS = {
    "player_pass_yds": dict(stat="pass_yds", volume="pass_att", eff="ypa",
                            def_unit="def_grade_cov",  side="pass"),
    "player_pass_attempts": dict(stat="pass_att", volume="pass_att", eff=None,
                            def_unit="def_grade_cov",  side="pass"),
    "player_rush_yds": dict(stat="rush_yds", volume="rush_att", eff="ypc",
                            def_unit="def_grade_rdef", side="rush"),
    "player_rush_attempts": dict(stat="rush_att", volume="rush_att", eff=None,
                            def_unit="def_grade_rdef", side="rush"),
    "player_reception_yds": dict(stat="rec_yds", volume="targets", eff="ypt",
                            def_unit="def_grade_cov",  side="pass"),
    "player_receptions": dict(stat="receptions", volume="targets", eff="catch_rate",
                            def_unit="def_grade_cov",  side="pass"),
}

# ---------------- MODEL TUNING ----------------
# Regression-to-mean weight: how hard to pull a player's efficiency toward the
# position average when their prior-year sample is small. Higher = more shrinkage.
SHRINKAGE_GAMES = 6      # a player with this many prior games is ~half-regressed

# Opponent adjustment strength: how much a 1-SD defensive grade moves a projection.
# 0.15 means an elite (worst) pass defense scales pass projections by ~±15% at 1 SD.
OPP_ADJ_STRENGTH = 0.15

# Minimum prior-year volume to project a player at all (filters noise).
MIN_PRIOR_VOLUME = dict(pass_att=100, rush_att=30, targets=20)

# Edge thresholds for flagging (in the stat's own units).
EDGE_FLAG = dict(pass_yds=20, rush_yds=12, rec_yds=12,
                 pass_att=3, rush_att=3, receptions=1.0)
