#!/usr/bin/env python3
"""
build_fantasy_draft_data.py — one-off: take Yahoo's own CFB fantasy draft
rankings as a base, and lay our own signals on top to flag situations
Yahoo's rank may not fully reflect: confirmed starter vs. buried on the
depth chart, and the team's own pace/run-pass split/success rate.

Yahoo export format (messy, copy-pasted from their site): each player is
~9 physical CSV rows -- "[Name]", "Name" again, blank, Position, Team
code, "Bye N", blank, then ONE data row of 17 comma fields. The data
row's field order was reverse-engineered by cross-checking known values
(Jeremiah Smith/OSU projecting #1 overall with 1,041 rec yds; Arch
Manning/TEX projecting 3,148 pass yds) against field position -- see
_parse_yahoo() for the confirmed mapping. Blank-line count between
blocks varies, so parsing is state-machine-driven off field CONTENT
(a bracketed name, a known position code, "Bye N", a 17-field numeric
row), not fixed line offsets.

"Situation Score" (0-100) is a percentile-ranked, position-group-specific
combination of three team-level signals, each ranked against the other
67 P4 teams (P4 = SEC/Big Ten/ACC/Big 12; Notre Dame and any non-P4 team
in Yahoo's list is dropped, per this being a P4-only build):
  - pace        : team_ratings' Tempo (lower raw value = more snaps/game
                  = more fantasy opportunity, so this is INVERTED before
                  ranking -- see _pct())
  - volume rate : off_rush_rate for RB, off_pass_rate for QB/WR/TE
  - success rate: off_rush_sr for RB, off_pass_sr for QB/WR/TE
Equal-weighted average of the three percentiles. This is a transparent,
un-fitted comparison -- same philosophy as the rest of this project --
not a competing fantasy-points projection (Yahoo's own Proj Pts column
is left untouched); it's an ENVIRONMENT overlay meant to catch cases
where Yahoo's rank and the underlying situation disagree.

UNVALIDATED: no backtest exists for this scoring (no historical Yahoo
draft-rank file to check it against), same caveat as several of this
project's newer adjustments (TARP_ADJ_STRENGTH, DEPTH_RANK_MULT).

Depth-chart join is by (team, position bucket, last name, first initial)
since Yahoo only gives "F. Last" -- scoped to one team's roster this is
reliable; a true ambiguous case (two same-initial same-last-name players
at the same position on the same team) is vanishingly rare and would
just take the lower depth_rank.

Run:  python3 build_fantasy_draft_data.py --out fantasy_draft_2026.json
"""
import argparse, csv, json
import data_load as DL

P4_CONFERENCES = {"SEC", "Big Ten", "ACC", "Big 12"}

# Yahoo's team code -> this project's canonical team display name
# (team_averages_2025.json / depth_charts.csv). Hand-built from standard
# CFB abbreviations, not fuzzy-matched -- see module docstring on why
# fuzzy team-name matching is unsafe (build_pff_team_map.py's history).
YAHOO_TEAM_MAP = {
    "ALA": "Alabama", "ARIZ": "Arizona", "ARK": "Arkansas", "ASU": "Arizona State",
    "AUB": "Auburn", "BAY": "Baylor", "BC": "Boston College", "BYU": "BYU",
    "CAL": "California", "CIN": "Cincinnati", "CLEM": "Clemson", "COLO": "Colorado",
    "DUKE": "Duke", "FLA": "Florida", "FSU": "Florida State", "GT": "Georgia Tech",
    "HOU": "Houston", "ILL": "Illinois", "IND": "Indiana", "IOWA": "Iowa",
    "ISU": "Iowa State", "KSU": "Kansas State", "KU": "Kansas", "LOU": "Louisville",
    "LSU": "LSU", "MIA": "Miami", "MICH": "Michigan", "MINN": "Minnesota",
    "MISS": "Ole Miss", "MIZZ": "Missouri", "MSST": "Mississippi State",
    "MSU": "Michigan State", "NCST": "NC State", "ND": "Notre Dame", "NEB": "Nebraska",
    "NW": "Northwestern", "OKST": "Oklahoma State", "ORE": "Oregon", "OSU": "Ohio State",
    "OU": "Oklahoma", "PITT": "Pittsburgh", "PSU": "Penn State", "PUR": "Purdue",
    "RUTG": "Rutgers", "SC": "South Carolina", "SMU": "SMU", "STAN": "Stanford",
    "SYR": "Syracuse", "TAMU": "Texas A&M", "TCU": "TCU", "TENN": "Tennessee",
    "TEX": "Texas", "TTU": "Texas Tech", "UCF": "UCF", "UCLA": "UCLA",
    "UGA": "Georgia", "UK": "Kentucky", "UMD": "Maryland", "UNC": "North Carolina",
    "USC": "USC", "UTAH": "Utah", "UVA": "Virginia", "UW": "Washington",
    "VAN": "Vanderbilt", "VT": "Virginia Tech", "WAKE": "Wake Forest", "WIS": "Wisconsin",
    "WVU": "West Virginia",
}

STAT_FIELDS = ["_blank", "xrank", "adp", "bye", "proj_pts", "pass_yds", "pass_td", "ints",
               "rush_att", "rush_yds", "rush_td", "rec", "rec_yds", "rec_td", "ret_td",
               "two_pt", "fum_lost"]

KNOWN_POS = {"QB", "RB", "WR", "TE", "K", "DEF"}
FANTASY_POS = {"QB", "RB", "WR", "TE"}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_yahoo(path):
    rows = list(csv.reader(open(path)))
    players = []
    cur = None
    for r in rows:
        c0 = (r[0] or "").strip()
        if c0.startswith("[") and c0.endswith("]"):
            cur = dict(name=c0[1:-1], position=None, team_code=None, bye=None)
            continue
        if cur is None:
            continue
        if cur["position"] is None and c0 in KNOWN_POS:
            cur["position"] = c0
            continue
        if cur["position"] and cur["team_code"] is None and c0 and not c0.startswith("Bye") \
                and c0.isupper() and len(c0) <= 6 and c0 != cur["name"].upper():
            cur["team_code"] = c0
            continue
        if c0.startswith("Bye"):
            parts = c0.split()
            cur["bye"] = parts[1] if len(parts) > 1 else None
            continue
        if cur["team_code"] and len(r) >= 17 and _f(r[1]) is not None:
            for i, key in enumerate(STAT_FIELDS):
                if key == "_blank":
                    continue
                cur[key] = _f(r[i])
            players.append(cur)
            cur = None
    return players


# ourlads position label -> Yahoo/roster position bucket (mirrors
# data_load._DEPTH_POS_MAP, duplicated here since that dict is keyed to
# this project's own HB/WR/TE/QB codes which already match Yahoo's).
def load_depth_by_team(path):
    """team display name (via substring match) -> list of offense rows."""
    from collections import defaultdict
    out = defaultdict(list)
    for r in csv.DictReader(open(path)):
        if r.get("side") != "offense":
            continue
        bucket = DL._DEPTH_POS_MAP.get((r.get("position") or "").strip())
        if not bucket:
            continue
        try:
            rank = int(r.get("depth_rank"))
        except (TypeError, ValueError):
            continue
        out[r["team"]].append(dict(position=bucket, depth_rank=rank, name=r.get("name", "")))
    return out


# ourlads' own mascot-suffixed name doesn't substring-match every P4
# team's canonical display name (same class of gap as data_load's
# _TEAM_GRADE_ALIASES) -- hand-verified against the 3 P4 misses found
# when building this.
DEPTH_TEAM_ALIASES = {
    "NC State": "North Carolina State",
    "Ole Miss": "Mississippi",
    "UCF": "Central Florida",
}

NAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


def _true_last(tokens):
    """Last real surname token, skipping a trailing Jr./Sr./II/III/IV."""
    t = list(tokens)
    while t and t[-1].lower().strip(".") in {s.strip(".") for s in NAME_SUFFIXES}:
        t.pop()
    return t[-1] if t else (tokens[-1] if tokens else "")


def match_depth(depth_by_team, team_display, position, last_raw, first_initial):
    # team_display ("Ohio State") -> ourlads' own full mascot name via
    # substring match, same trick used throughout this project for
    # Odds-API-style team strings.
    search_name = DEPTH_TEAM_ALIASES.get(team_display, team_display)
    yahoo_pos = "RB" if position == "RB" else position
    last = _true_last(last_raw.split())
    candidates = []
    for team_full, rows in depth_by_team.items():
        n = DL.norm(team_full)
        td = DL.norm(search_name)
        if not (td in n or n in td):
            continue
        for row in rows:
            if row["position"] != ("HB" if yahoo_pos == "RB" else yahoo_pos):
                continue
            parts = row["name"].split()
            if not parts:
                continue
            row_last = _true_last(parts).lower()
            row_first_initial = parts[0][0].lower() if parts[0] else ""
            if row_last == last.lower() and row_first_initial == first_initial.lower():
                candidates.append(row["depth_rank"])
    return min(candidates) if candidates else None


def pct_rank(values_by_team, invert=False):
    """Rank teams by value -> percentile 0-100 (100 = best). invert=True
    means a LOWER raw value is better (e.g. Tempo: fewer seconds/play)."""
    items = sorted(values_by_team.items(), key=lambda kv: kv[1], reverse=not invert)
    n = len(items)
    out = {}
    for i, (team, _) in enumerate(items):
        out[team] = round(100 * (n - 1 - i) / (n - 1), 1) if n > 1 else 50.0
    return out


def build(yahoo_path, team_averages_path, team_ratings_path, depth_chart_path):
    players = parse_yahoo(yahoo_path)

    team_avg = {t["team"]: t for t in json.load(open(team_averages_path))["teams"]}
    tempo_raw = {}
    for r in csv.DictReader(open(team_ratings_path)):
        t = r.get("Team", "")
        if t and r.get("Tempo"):
            tempo_raw[t] = float(r["Tempo"])

    p4_teams = [name for name, code in YAHOO_TEAM_MAP.items()]  # placeholder, real filter below
    p4_team_names = sorted({name for name in YAHOO_TEAM_MAP.values()
                            if name in team_avg and team_avg[name].get("conference") in P4_CONFERENCES})
    print(f"P4 teams resolved: {len(p4_team_names)} / {len(YAHOO_TEAM_MAP)} Yahoo codes "
          f"(dropped: {sorted(set(YAHOO_TEAM_MAP.values()) - set(p4_team_names))})")

    rush_rate = {t: team_avg[t]["advanced"]["off_rush_rate"] for t in p4_team_names if team_avg[t]["advanced"]}
    pass_rate = {t: team_avg[t]["advanced"]["off_pass_rate"] for t in p4_team_names if team_avg[t]["advanced"]}
    rush_sr = {t: team_avg[t]["advanced"]["off_rush_sr"] for t in p4_team_names if team_avg[t]["advanced"]}
    pass_sr = {t: team_avg[t]["advanced"]["off_pass_sr"] for t in p4_team_names if team_avg[t]["advanced"]}
    tempo = {t: tempo_raw[t] for t in p4_team_names if t in tempo_raw}

    rush_rate_pct, pass_rate_pct = pct_rank(rush_rate), pct_rank(pass_rate)
    rush_sr_pct, pass_sr_pct = pct_rank(rush_sr), pct_rank(pass_sr)
    pace_pct = pct_rank(tempo, invert=True)

    rb_situation, pass_situation = {}, {}
    for t in p4_team_names:
        parts_rb = [v for v in (pace_pct.get(t), rush_rate_pct.get(t), rush_sr_pct.get(t)) if v is not None]
        parts_pass = [v for v in (pace_pct.get(t), pass_rate_pct.get(t), pass_sr_pct.get(t)) if v is not None]
        rb_situation[t] = round(sum(parts_rb) / len(parts_rb), 1) if parts_rb else None
        pass_situation[t] = round(sum(parts_pass) / len(parts_pass), 1) if parts_pass else None

    depth_by_team = load_depth_by_team(depth_chart_path)

    out_players = []
    for p in players:
        if p["position"] not in FANTASY_POS:
            continue
        team_display = YAHOO_TEAM_MAP.get(p["team_code"])
        if team_display is None or team_display not in p4_team_names:
            continue
        name_parts = p["name"].split(".", 1)
        first_initial = name_parts[0].strip() if name_parts else ""
        last = name_parts[1].strip() if len(name_parts) > 1 else p["name"]
        depth_rank = match_depth(depth_by_team, team_display, p["position"], last, first_initial)

        situation = rb_situation.get(team_display) if p["position"] == "RB" else pass_situation.get(team_display)

        out_players.append(dict(
            name=p["name"], position=p["position"], team=team_display, team_code=p["team_code"],
            conference=team_avg[team_display]["conference"], bye=p.get("bye"),
            xrank=p.get("xrank"), adp=p.get("adp"), proj_pts=p.get("proj_pts"),
            pass_yds=p.get("pass_yds"), pass_td=p.get("pass_td"), rush_att=p.get("rush_att"),
            rush_yds=p.get("rush_yds"), rush_td=p.get("rush_td"), rec=p.get("rec"),
            rec_yds=p.get("rec_yds"), rec_td=p.get("rec_td"),
            depth_rank=depth_rank,
            situation_score=situation,
            pace_pct=pace_pct.get(team_display),
            volume_pct=(rush_rate_pct if p["position"] == "RB" else pass_rate_pct).get(team_display),
            success_pct=(rush_sr_pct if p["position"] == "RB" else pass_sr_pct).get(team_display),
        ))

    # Position-group XRank percentile, for the undervalued/risk flags.
    by_pos = {}
    for p in out_players:
        by_pos.setdefault(p["position"], []).append(p)
    for pos, plist in by_pos.items():
        ranked = sorted([p for p in plist if p["xrank"] is not None], key=lambda p: p["xrank"])
        n = len(ranked)
        for i, p in enumerate(ranked):
            p["xrank_pct_in_pos"] = round(100 * (n - 1 - i) / (n - 1), 1) if n > 1 else 50.0

    for p in out_players:
        xp = p.get("xrank_pct_in_pos")
        sit = p.get("situation_score")
        p["flag"] = None
        if xp is not None and sit is not None:
            if p["depth_rank"] == 1 and sit >= 66 and xp < 66:
                p["flag"] = "undervalued"
            elif xp >= 66 and p["depth_rank"] is not None and p["depth_rank"] > 1:
                p["flag"] = "risk"

    out_players.sort(key=lambda p: (p["position"], p["xrank"] if p["xrank"] is not None else 9999))

    # Stacks: P4 teams with >=2 fantasy-relevant players here where at
    # least one is a QB or the pass-game situation grades well.
    by_team = {}
    for p in out_players:
        by_team.setdefault(p["team"], []).append(p)
    stacks = []
    for team, plist in by_team.items():
        if len(plist) < 2:
            continue
        has_qb = any(p["position"] == "QB" for p in plist)
        sit = pass_situation.get(team)
        if not (has_qb and sit is not None and sit >= 60):
            continue
        stacks.append(dict(
            team=team, conference=team_avg[team]["conference"],
            pass_situation_score=sit, rush_situation_score=rb_situation.get(team),
            players=[dict(name=p["name"], position=p["position"], xrank=p["xrank"],
                          depth_rank=p["depth_rank"]) for p in plist],
        ))
    stacks.sort(key=lambda s: -s["pass_situation_score"])

    return out_players, stacks, p4_team_names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yahoo", default="yahoo_fantasy_rankings_2026.csv")
    ap.add_argument("--team-averages", default="team_averages_2025.json")
    ap.add_argument("--team-ratings", default="team_ratings_2025.csv")
    ap.add_argument("--depth-chart", default="depth_charts.csv")
    ap.add_argument("--out", default="fantasy_draft_2026.json")
    args = ap.parse_args()

    players, stacks, p4_teams = build(args.yahoo, args.team_averages, args.team_ratings, args.depth_chart)
    n_matched = sum(1 for p in players if p["depth_rank"] is not None)
    payload = dict(players=players, stacks=stacks, p4_teams=p4_teams)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"Wrote {args.out}: {len(players)} P4 fantasy players "
          f"({n_matched} matched to a depth-chart row), {len(stacks)} suggested stacks")
    print(f"  undervalued: {sum(1 for p in players if p['flag']=='undervalued')} | "
          f"risk: {sum(1 for p in players if p['flag']=='risk')}")


if __name__ == "__main__":
    main()
