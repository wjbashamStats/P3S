#!/usr/bin/env python3
"""
build_impact_page_data.py — one-off: build a season-long player-profile
dataset (season totals, usage share, PFF grades, per-game trend) for the
Impact tab's player-card page.

Unlike build_props_page_data.py this isn't tied to a single week or to
props/book lines -- it's a season-to-date snapshot, so every skill player
with meaningful volume gets a card.

Run:  python3 build_impact_page_data.py --out impact_players.json
"""
import argparse, csv, json
import config as C
import data_load as DL
import project as P

SKILL_POSITIONS = {"QB", "HB", "WR", "TE", "FB"}

# Loose inclusion floor -- half of config.MIN_PRIOR_VOLUME, since this is a
# browsable profile page, not a betting-volume gate.
MIN_VOLUME = dict(pass_att=30, rush_att=15, targets=10)

GRADE_FIELDS = (
    "off_grade_off", "off_grade_pass", "off_grade_run", "off_grade_recv",
    "off_grade_pblk", "off_grade_rblk",
    "def_grade_def", "def_grade_rdef", "def_grade_prush", "def_grade_cov",
    "off_snaps_off", "off_snaps_pass", "off_snaps_run", "off_snaps_recv",
    "off_snaps_pblk", "off_snaps_rblk",
    "def_snaps_def", "def_snaps_rdef", "def_snaps_prush", "def_snaps_cov",
)


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def meets_volume_floor(tot):
    return (
        (tot.get("pass_att") or 0) >= MIN_VOLUME["pass_att"]
        or (tot.get("rush_att") or 0) >= MIN_VOLUME["rush_att"]
        or (tot.get("targets") or 0) >= MIN_VOLUME["targets"]
    )


def build():
    pff2c, _ = DL.load_team_map()
    pff = DL.load_pff(pff2c)
    totals = DL.load_season_totals()      # 2025 season-to-date, keyed (pkey, tkey)
    prior = DL.load_prior_totals(season=2025)  # real 2024, keyed player_id
    logs = DL.load_game_logs()            # 2025 per-game, keyed (pkey, tkey)

    # load_season_totals() drops the raw "player"/"team" strings from its
    # dict (they're join keys, not stats) -- re-read them directly for display.
    raw_by_key = {}
    for r in csv.DictReader(open(C.SEASON_TOTALS)):
        raw_by_key[(norm(r.get("player", "")), norm(r.get("team", "")))] = \
            (r.get("player", ""), r.get("team", ""))

    pff_by_key = {}
    for p in pff:
        pff_by_key.setdefault((p["pkey"], p["tkey"]), p)

    # Team volume pools (this season) for usage-share -- every player
    # counts toward the pool, not just the ones that clear MIN_VOLUME.
    team_totals = P.build_team_volume_totals(
        ((tkey, tot) for (pkey, tkey), tot in totals.items()),
        vol_cols=("rush_att", "targets"),
    )

    players = []
    for (pkey, tkey), tot in totals.items():
        if tot.get("position") not in SKILL_POSITIONS:
            continue
        if not meets_volume_floor(tot):
            continue

        grades = pff_by_key.get((pkey, tkey), {})
        player_id = tot.get("player_id")
        prior_tot = prior.get(player_id) if player_id else None

        rates_2025 = P.compute_player_rates(tot)
        rates_2024 = P.compute_player_rates(prior_tot) if prior_tot else {}

        team_pool = team_totals.get(tkey, {})
        rush_share = None
        if team_pool.get("rush_att") and tot.get("rush_att") is not None:
            rush_share = round(tot["rush_att"] / team_pool["rush_att"] * 100, 1)
        target_share = None
        if team_pool.get("targets") and tot.get("targets") is not None:
            target_share = round(tot["targets"] / team_pool["targets"] * 100, 1)

        game_log = sorted(
            [g for g in logs.get((pkey, tkey), []) if g.get("week") is not None],
            key=lambda g: g["week"],
        )
        game_log_out = []
        for g in game_log:
            row = dict(week=int(g["week"]), pass_yds=g.get("pass_yds"), rush_yds=g.get("rush_yds"),
                       rec_yds=g.get("rec_yds"), receptions=g.get("receptions"),
                       pass_att=g.get("pass_att"), rush_att=g.get("rush_att"), targets=g.get("targets"))
            game_log_out.append({k: v for k, v in row.items() if v is not None})

        raw_name, raw_team = raw_by_key.get((pkey, tkey), ("", ""))
        team_c = pff2c.get(norm(raw_team), raw_team)

        players.append(dict(
            name=grades.get("name") or raw_name or pkey,
            player_id=player_id,
            team=team_c,
            position=tot.get("position") or grades.get("position") or "",
            height=grades.get("height") or "",
            weight=grades.get("weight") or "",
            season_2025=dict(
                games=tot.get("games"),
                pass_att=tot.get("pass_att"), pass_yds=tot.get("pass_yds"), pass_td=tot.get("pass_td"),
                rush_att=tot.get("rush_att"), rush_yds=tot.get("rush_yds"), rush_td=tot.get("rush_td"),
                targets=tot.get("targets"), receptions=tot.get("receptions"),
                rec_yds=tot.get("rec_yds"), rec_td=tot.get("rec_td"),
            ),
            season_2024=dict(
                games=prior_tot.get("games") if prior_tot else None,
                pass_att=prior_tot.get("pass_att") if prior_tot else None,
                pass_yds=prior_tot.get("pass_yds") if prior_tot else None,
                pass_td=prior_tot.get("pass_td") if prior_tot else None,
                rush_att=prior_tot.get("rush_att") if prior_tot else None,
                rush_yds=prior_tot.get("rush_yds") if prior_tot else None,
                rush_td=prior_tot.get("rush_td") if prior_tot else None,
                targets=prior_tot.get("targets") if prior_tot else None,
                receptions=prior_tot.get("receptions") if prior_tot else None,
                rec_yds=prior_tot.get("rec_yds") if prior_tot else None,
                rec_td=prior_tot.get("rec_td") if prior_tot else None,
            ) if prior_tot else None,
            rates_2025={k: (round(v, 2) if v is not None else None) for k, v in rates_2025.items()},
            rates_2024={k: (round(v, 2) if v is not None else None) for k, v in rates_2024.items()},
            usage=dict(rush_share_pct=rush_share, target_share_pct=target_share),
            grades={f: grades.get(f) for f in GRADE_FIELDS if grades.get(f) not in (None, "")},
            game_log=game_log_out,
        ))

    players.sort(key=lambda p: (p["team"], p["position"], p["name"]))
    return players


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="impact_players.json")
    args = ap.parse_args()

    players = build()
    payload = dict(season=2025, generated_players=len(players), players=players)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"Wrote {args.out}: {len(players)} player cards")


if __name__ == "__main__":
    main()
