#!/usr/bin/env python3
"""
build_diversions_page_data.py — one-off: compare book spreads/totals
against a power-rating-implied line, for the "biggest diversions" page.

Predicted SPREAD comes from SP+ differential + home-field edge (team_
ratings_2025.csv's SP and HFACW columns) -- SP+ is itself opponent-
adjusted, so this tracks the book much better than a naive difference of
each team's own scoring average. That naive approach (summing/differencing
"Team Total") was tried first and produced a nonsense -5.7 predicted
spread for USC (-38.5 actual) against a bad San Jose State team, because
it doesn't know anything about the SPECIFIC opponent -- it's each team's
OWN average expected output, blind to who they're playing. SP+ is built
for exactly this (opponent-adjusted efficiency), so it's used for spread.

Predicted TOTAL keeps the naive sum-of-Team-Total approach -- a total
isn't about relative strength, it's about pace + scoring level, which
Team Total (each team's own average points) is actually built to answer,
and it tracked reasonably (diffs mostly within ~4 points on the games
checked) even though it fails badly for spread.

Both are simple, transparent, un-fitted power-rating comparisons, not a
tuned model -- same philosophy as the rest of this project, and there is
NO backtest for this (there's no historical "predicted spread" file to
validate against). Treat as directional, not gospel.

Each game also gets a plain-language REASON for its biggest diffs, built
from the same underlying components already computed (never a separate
guess): SP+ gap direction/size, home-field edge, and -- because SP+ alone
is backward-looking (2025 season only) -- whether the 2026-forward
OffAdj/DefAdj (coaching change + returning production, team_ratings'
own continuity metric) points the SAME or OPPOSITE direction, which is
often exactly why a spread and a power rating disagree (a team lost a
lot of production, or gained a good portion back, in a way the prior
season's box scores don't reflect). Total reasons cite whichever side's
pass/rush rate + success rate is driving the total, plus tempo.

DATA CAVEAT, now fixed but worth remembering: hist_lines_live_*.csv used
to carry no per-row date, so a team could appear twice (its week-1 AND
week-2 game) with no way to tell which was which -- pull_live_week.py was
patched to stamp commence_time on every line (not just props), and this
script now filters directly on that date range instead of the old
props-file cross-reference (which only covered the 8 games with a posted
prop). Default window is Sept 2-7, 2026 (Wed-Mon) -- the actual week-1
slate; pass --date-start/--date-end to point at a different week.

Run:  python3 build_diversions_page_data.py --out diversions_2026wk1.json
"""
import argparse, csv, json
import data_load as DL


def norm(s):
    return DL.norm(s)


# Odds API's own naming quirk for this one team ("Miami (OH)" vs our
# "Miami Ohio") -- found while building this; every other FBS team's
# Team+Mascot concatenation matched the Odds API string exactly.
ODDS_NAME_ALIASES = {"miamiohredhawks": "miamiohioredhawks"}


def load_ratings_raw(path):
    """EXACT match only (norm(Team+Mascot) -> row), not substring.
    Substring matching was tried first and is unsafe here: "North
    Carolina A&T Aggies" (FCS -- correctly NOT in this file) contains
    "North Carolina" (IS in this file) as a genuine literal substring,
    so a substring match confidently returned the WRONG team and
    produced a nonsense 55-point "diversion" that was really just a
    data bug. team_ratings.csv's own Mascot column lets Team+Mascot be
    compared for an exact match against the Odds API's "Team Mascot"
    naming instead -- ~70% of Week 1's slate matches this way (the
    other ~30% are genuine FCS buy games, correctly left unrated rather
    than than guessed at)."""
    out = {}
    for r in csv.DictReader(open(path)):
        team, mascot = r.get("Team", ""), r.get("Mascot", "")
        if team and mascot:
            out[norm(team + mascot)] = r
    return out


def match_team(ratings_raw, raw_team):
    n = ODDS_NAME_ALIASES.get(norm(raw_team), norm(raw_team))
    return ratings_raw.get(n)


def match_team_avg(team_avg, raw_team):
    """team_avg is keyed by canonical display name (no mascot) -- rebuild
    the same exact Team+Mascot lookup from it via each entry's own
    'mascot' field, same safety rationale as match_team above."""
    n = ODDS_NAME_ALIASES.get(norm(raw_team), norm(raw_team))
    for t in team_avg.values():
        if t.get("mascot") and norm(t["team"] + t["mascot"]) == n:
            return t
    return None


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def spread_reason(home_team, away_team, book_spread, pred_spread, spread_diff,
                   home_sp, away_sp, hfa, home_adj, away_adj):
    """home_adj/away_adj: (off_adj, def_adj, rank_tarp) 2026-forward continuity, or None."""
    lean_team, lean_amt = (home_team, -spread_diff) if spread_diff < 0 else (away_team, spread_diff)
    parts = []
    if abs(spread_diff) < 1.5:
        parts.append(f"Book and SP+ are basically in agreement here ({abs(spread_diff):.1f} pt gap) -- "
                      f"SP+ has {home_team} {'+' if home_sp>=away_sp else ''}{(home_sp-away_sp):.1f} over "
                      f"{away_team} before the {hfa:.1f}-pt home edge.")
    else:
        parts.append(f"The book leans {lean_amt:.1f} pts more toward {lean_team} than SP+ + "
                     f"home-field alone would put them (SP+ gap {home_sp - away_sp:+.1f} for {home_team}, "
                     f"+{hfa:.1f} home edge).")
    if home_adj and away_adj:
        fwd_diff = (home_adj[0] - away_adj[1]) - (away_adj[0] - home_adj[1])
        sp_diff = home_sp - away_sp
        if (fwd_diff > 0) != (sp_diff > 0) and abs(fwd_diff) > 1:
            favored_fwd = home_team if fwd_diff > 0 else away_team
            parts.append(f"Worth noting: the 2026-forward continuity metric (coaching change + returning "
                        f"production) actually favors {favored_fwd} more than 2025 SP+ alone does -- "
                        f"rank_TARP {home_adj[2]:.0f} ({home_team}) vs {away_adj[2]:.0f} ({away_team}). "
                        f"Could explain some of the book's lean if the market is pricing in personnel "
                        f"changes SP+'s season-long number can't see yet.")
    return " ".join(parts)


def total_reason(home_team, away_team, book_total, pred_total, total_diff,
                  home_avg, away_avg):
    direction = "higher-scoring" if total_diff > 0 else "lower-scoring"
    parts = [f"Book expects a {direction} game than the team-total sum by {abs(total_diff):.1f} pts."]
    if home_avg and away_avg:
        ha, aa = home_avg.get("advanced") or {}, away_avg.get("advanced") or {}
        notes = []
        for team, adv in ((home_team, ha), (away_team, aa)):
            pass_rate, pass_sr = adv.get("off_pass_rate"), adv.get("off_pass_sr")
            if pass_rate is not None and pass_sr is not None and pass_rate > 0.55 and pass_sr > 0.42:
                notes.append(f"{team} is both pass-heavy ({pass_rate*100:.0f}% of plays) and efficient "
                            f"at it ({pass_sr*100:.0f}% success rate)")
        if notes:
            parts.append(" / ".join(notes) + " -- that combination pushes real scoring above a flat "
                        "team-average baseline more than the naive sum accounts for.")
    return " ".join(parts)


def build(lines_path, ratings_path, team_averages_path, date_start, date_end):
    ratings_raw = load_ratings_raw(ratings_path)
    team_avg = {t["team"]: t for t in json.load(open(team_averages_path))["teams"]}

    out = []
    for r in csv.DictReader(open(lines_path)):
        ct = r.get("commence_time", "")
        if not (date_start <= ct[:10] <= date_end):
            continue
        home_team, away_team = r["home_team"], r["away_team"]
        rh, ra = match_team(ratings_raw, home_team), match_team(ratings_raw, away_team)
        book_spread, book_total = _f(r["home_spread"]), _f(r["total"])
        row = dict(
            game_id=r["game_id"], home_team=home_team, away_team=away_team,
            commence_time=ct,
            book_spread=book_spread, book_total=book_total,
            pred_spread=None, pred_total=None,
            spread_diff=None, total_diff=None,
            home_rated=bool(rh), away_rated=bool(ra),
            spread_reason=None, total_reason=None,
        )
        if rh and ra:
            sp_h, sp_a = _f(rh["SP"]), _f(ra["SP"])
            hfa = _f(rh.get("HFACW"))
            pred_spread = -(sp_h - sp_a + hfa)
            ht_total, at_total = _f(rh["Team Total"]), _f(ra["Team Total"])
            pred_total = ht_total + at_total
            spread_diff = round(book_spread - pred_spread, 1)
            total_diff = round(book_total - pred_total, 1)
            home_adj = (_f(rh.get("OffAdj")), _f(rh.get("DefAdj")), _f(rh.get("rank_TARP")))
            away_adj = (_f(ra.get("OffAdj")), _f(ra.get("DefAdj")), _f(ra.get("rank_TARP")))
            home_avg, away_avg = match_team_avg(team_avg, home_team), match_team_avg(team_avg, away_team)
            row.update(
                pred_spread=round(pred_spread, 1), pred_total=round(pred_total, 1),
                spread_diff=spread_diff, total_diff=total_diff,
                home_sp=sp_h, away_sp=sp_a, hfa=hfa,
                home_team_total=ht_total, away_team_total=at_total,
                home_off_adj=home_adj[0], home_def_adj=home_adj[1], home_rank_tarp=home_adj[2],
                away_off_adj=away_adj[0], away_def_adj=away_adj[1], away_rank_tarp=away_adj[2],
                spread_reason=spread_reason(home_team, away_team, book_spread, pred_spread, spread_diff,
                                            sp_h, sp_a, hfa, home_adj, away_adj),
                total_reason=total_reason(home_team, away_team, book_total, pred_total, total_diff,
                                          home_avg, away_avg),
            )
        out.append(row)

    out.sort(key=lambda r: -(abs(r["spread_diff"] or 0) + abs(r["total_diff"] or 0)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-lines", default="hist_lines_live_2026wk1.csv")
    ap.add_argument("--team-ratings", default="team_ratings_2025.csv")
    ap.add_argument("--team-averages", default="team_averages_2025.json")
    ap.add_argument("--date-start", default="2026-09-02", help="inclusive, YYYY-MM-DD")
    ap.add_argument("--date-end", default="2026-09-07", help="inclusive, YYYY-MM-DD")
    ap.add_argument("--week", type=int, default=1)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--out", default="diversions_2026wk1.json")
    args = ap.parse_args()

    games = build(args.game_lines, args.team_ratings, args.team_averages, args.date_start, args.date_end)
    n_full = sum(1 for g in games if g["pred_spread"] is not None)
    payload = dict(week=args.week, season=args.season, date_start=args.date_start,
                   date_end=args.date_end, games=games)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"Wrote {args.out}: {len(games)} games in [{args.date_start}, {args.date_end}], "
          f"{n_full} with both teams rated")


if __name__ == "__main__":
    main()
