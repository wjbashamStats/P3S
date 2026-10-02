#!/usr/bin/env python3
"""Rebuild a week's slate numbers from the committed data, with one explicit
definition for every quantity a card quotes. Run it from the repo root:

    python3 articles/build/recompute.py --week 5

It reads diversions_2026wk<N>.json and team_pff_grades_2026.csv and prints the
spread and totals candidate tables. Nothing here reads the draft write-up, which
is the point: the card is checked against this, not the other way round.

Definitions, fixed here so they stop drifting between weeks:

  slate          Saturday in Eastern time, both teams rated, not yet started,
                 with a book spread and total. Week 5: 49 games.
  slate level    the mean of (model - book) across the slate. Each gap is quoted
                 raw and net of this.
  points check   each team's expected points is the mean of what it scores per
                 game and what its opponent allows per game. Summed, that is the
                 totals check; differenced and plus home field, the spread check.
                 Per-game uses each team's OWN game count (3, 4 or 5 this week),
                 taken from its record in the grades file.
  residual       what is left of (model total - book total) after fitting it on
                 the game's average defensive Success Rate rank. The model's team
                 totals are opponent-blind and the market is not, so that fit is
                 most of the raw gap. Average DEFENSIVE SUCCESS RATE RANK is the
                 predictor -- not the mean of all five factors, which gives a
                 different and wrong answer.

The points check is reported, never used to reorder the totals card: week 4
tested that and it cost 3.10 units (PROJECT_STATE quirk 16).
"""
import argparse, csv, datetime, json, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def load(week, season):
    games = json.load(open(os.path.join(ROOT, f"diversions_{season}wk{week}.json")))["games"]
    # (pf, pa, overall grade) identifies a team in the grades file uniquely
    # (138/138 this season), which is how a game's inline grades dict is tied
    # back to a record -- the display names do not match on their own.
    by_grades = {}
    for r in csv.DictReader(open(os.path.join(ROOT, f"team_pff_grades_{season}.csv"))):
        by_grades[(float(r["pf"]), float(r["pa"]), float(r["grade_over"]))] = r
    return games, by_grades


def games_played(row):
    w, l = [int(x) for x in row["record"].split(" - ")[:2]]
    return w + l


def build(week, season, tz_hours=-4):
    games, by_grades = load(week, season)
    tz = datetime.timezone(datetime.timedelta(hours=tz_hours))
    rows, skipped = [], []
    for g in games:
        t = datetime.datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00")).astimezone(tz)
        if t.weekday() != 5 or g["started"]:
            continue
        if not (g["home_rated"] and g["away_rated"]):
            continue
        if g["book_spread"] is None or g["book_total"] is None:
            continue
        hrow = by_grades.get((g["home_grades"]["pf"], g["home_grades"]["pa"], g["home_grades"]["grade_over"]))
        arow = by_grades.get((g["away_grades"]["pf"], g["away_grades"]["pa"], g["away_grades"]["grade_over"]))
        if not hrow or not arow:
            skipped.append(f"{g['away_display']} @ {g['home_display']}")
            continue
        hgp, agp = games_played(hrow), games_played(arow)
        hpf, hpa = g["home_grades"]["pf"] / hgp, g["home_grades"]["pa"] / hgp
        apf, apa = g["away_grades"]["pf"] / agp, g["away_grades"]["pa"] / agp
        h_exp, a_exp = (hpf + apa) / 2.0, (apf + hpa) / 2.0
        ff = g["five_factors"]
        rows.append(dict(
            away=g["away_display"], home=g["home_display"],
            away_full=g["away_team"], home_full=g["home_team"],
            book_spread=g["book_spread"], pred_spread=g["pred_spread"],
            book_total=g["book_total"], pred_total=g["pred_total"],
            spread_gap=g["pred_spread"] - g["book_spread"],
            total_gap=g["pred_total"] - g["book_total"],
            # negative = home favored, the same sign convention as book_spread
            pts_margin=-(h_exp - a_exp + g["hfa"]),
            pts_total=h_exp + a_exp,
            avg_def_sr=(ff["home_def"]["success_rate"] + ff["away_def"]["success_rate"]) / 2.0,
            hgp=hgp, agp=agp, hpf=hpf, hpa=hpa, apf=apf, apa=apa, hfa=g["hfa"],
            hrec=hrow["record"].replace(" ", ""), arec=arow["record"].replace(" ", ""),
            kick=t.strftime("%a %H:%M"),
        ))
    for r in rows:
        r["pts_check_total"] = r["pts_total"] - r["book_total"]
        r["pts_check_spread"] = r["pts_margin"] - r["book_spread"]
    return rows, skipped


def fit_residual(rows):
    xs = [r["avg_def_sr"] for r in rows]
    ys = [r["total_gap"] for r in rows]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    corr = b * statistics.stdev(xs) / statistics.stdev(ys)
    for r in rows:
        r["resid"] = r["total_gap"] - (a + b * r["avg_def_sr"])
    return a, b, corr


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json-out", default=None, help="write the full table here")
    args = ap.parse_args()

    rows, skipped = build(args.week, args.season)
    if not rows:
        print("no games in the slate window", file=sys.stderr)
        return 1
    print(f"slate: {len(rows)} games" + (f"   SKIPPED (no grades row): {skipped}" if skipped else "   (none skipped)"))
    sl_sp = statistics.mean(r["spread_gap"] for r in rows)
    sl_tot = statistics.mean(r["total_gap"] for r in rows)
    overs = sum(1 for r in rows if r["total_gap"] > 0)
    print(f"slate level: spread {sl_sp:+.3f} (toward home when negative)   "
          f"total {sl_tot:+.3f}, {overs}/{len(rows)} lean Over")
    a, b, corr = fit_residual(rows)
    print(f"residual fit: total_gap = {a:.3f} {b:+.4f} * avg_def_success_rate_rank   r={corr:+.3f}")
    for r in rows:
        r["adj_spread_gap"] = r["spread_gap"] - sl_sp

    print(f"\n--- spreads, top {args.top} by |gap net of slate level| ---")
    for r in sorted(rows, key=lambda r: -abs(r["adj_spread_gap"]))[:args.top]:
        home_side = r["adj_spread_gap"] < 0
        side = r["home"] if home_side else r["away"]
        num = r["book_spread"] if home_side else -r["book_spread"]
        agree = (r["pts_check_spread"] < 0) == (r["adj_spread_gap"] < 0)
        print(f"{r['away']:>17} @ {r['home']:<17} {side+' '+format(num,'+.1f'):<22}"
              f"gap{r['spread_gap']:+6.1f} net{r['adj_spread_gap']:+6.1f} | "
              f"points {r['pts_margin']:+6.1f} ({r['pts_check_spread']:+5.1f} vs line) "
              f"{'agree' if agree else 'DISAGREE'}")

    print(f"\n--- totals, top {args.top} by |residual| ---")
    for r in sorted(rows, key=lambda r: -abs(r["resid"]))[:args.top]:
        agree = (r["pts_check_total"] < 0) == (r["resid"] < 0)
        print(f"{r['away']:>17} @ {r['home']:<17} {'Under' if r['resid']<0 else 'Over ':<6}"
              f"{r['book_total']:6.2f} model{r['pred_total']:6.1f} gap{r['total_gap']:+6.1f} "
              f"resid{r['resid']:+5.1f} | points{r['pts_total']:6.1f} ({r['pts_check_total']:+5.1f}) "
              f"{'agree' if agree else 'DISAGREE':8} avgSRdef{r['avg_def_sr']:6.1f}")

    if args.json_out:
        json.dump(dict(slate_spread_level=sl_sp, slate_total_level=sl_tot,
                       fit=dict(intercept=a, slope=b, r=corr), games=rows),
                  open(args.json_out, "w"), indent=1)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
