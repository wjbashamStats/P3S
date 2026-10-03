#!/usr/bin/env python3
"""QA a built card against the committed data. From the repo root:

    python3 articles/build/qa_card.py --week 5

Six checks, each of which has caught a real defect at least once:

  kickoffs   every pick is Saturday in Eastern time and had not started. A late
             West Coast game reads Sunday in UTC, so UTC alone is not enough.
  ties       a five-factor rank ending in .5 is a tie. If the card cites that
             number as a plain "126th" rather than "tied 126th" it is flagged.
  grades     every "NN.N ... grade" in a write-up must exist either in that
             game's own team grade dicts or in the cited player's PFF row.
  numbers    book line, model number, gap, residual and points check must match
             what recompute.py derives, to the digit.
  scoring    every per-game scoring figure and W-L / ATS / Over record must match
             the grades file and the board. Per-game rounds half UP: 18.25 is
             18.3, which is what the prose uses and what Python's own %.1f does
             NOT do (it rounds half to even and gives 18.2).
  log        every pick on the card has a matching row in picks_log.csv.

Exit status is 1 if anything fails, so it can gate a commit.
"""
import argparse, csv, datetime, decimal, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import recompute  # noqa: E402

MET = {"success_rate": "Success Rate", "explosiveness": "Explosiveness", "havoc": "Havoc",
       "finishing_drives": "Finishing Drives", "field_position": "Field Position"}


def half_up(x, places=1):
    q = decimal.Decimal(10) ** -places
    return float(decimal.Decimal(repr(x)).quantize(q, rounding=decimal.ROUND_HALF_UP))


def fmt(x, places=1):
    return f"{half_up(x, places):.{places}f}"


class QA:
    def __init__(self, week, season):
        self.week, self.season = week, season
        self.fails, self.checks = [], 0
        self.content = json.load(open(os.path.join(HERE, "content.json")))
        self.board = {(g["away_team"], g["home_team"]): g
                      for g in json.load(open(os.path.join(ROOT, f"diversions_{season}wk{week}.json")))["games"]}
        self.grades = {}
        for r in csv.DictReader(open(os.path.join(ROOT, f"team_pff_grades_{season}.csv"))):
            self.grades[(float(r["pf"]), float(r["pa"]), float(r["grade_over"]))] = r
        self.rush = {r["player"]: r for r in csv.DictReader(open(os.path.join(ROOT, f"{season}_rushing_season_ranked.csv")))}
        self.recv = {r["player"]: r for r in csv.DictReader(open(os.path.join(ROOT, f"{season}_receiving_season_ranked.csv")))}
        rows, _ = recompute.build(week, season)
        recompute.fit_residual(rows)
        import statistics
        self.level = statistics.mean(r["spread_gap"] for r in rows)
        self.calc = {(r["away_full"], r["home_full"]): r for r in rows}
        self.log = [r for r in csv.DictReader(open(os.path.join(ROOT, "picks_log.csv")))
                    if r["week"] == str(week) and r["season"] == str(season)]

    def ok(self, cond, label, detail=""):
        self.checks += 1
        if not cond:
            self.fails.append(f"{label}: {detail}")
        return cond

    def game_of(self, item):
        away, home = item["game"].split(" @ ")
        g = self.board.get((away, home))
        self.ok(g is not None, "game not on the board", item["game"])
        return g

    @staticmethod
    def text(item):
        """Everything a reader sees for this pick, the heading included -- the full
        player name lives only in the heading, and the grade check keys on it."""
        return (item["pick"] + " || " + item["game"] + " || "
                + " ".join(v for _, v in item["facts"]) + " || " + " || ".join(item["paras"]))

    def fact(self, item, label):
        for k, v in item["facts"]:
            if k == label:
                return v
        return None

    # ---------------------------------------------------------------- kickoffs
    def check_kickoffs(self):
        print("\n--- kickoffs (Eastern) ---")
        tz = datetime.timezone(datetime.timedelta(hours=-4))
        now = datetime.datetime.now(datetime.timezone.utc)
        for f in (f"hist_lines_live_{self.season}wk{self.week}.csv",
                  f"diversions_{self.season}wk{self.week}.json"):
            age = (now - datetime.datetime.fromtimestamp(
                os.path.getmtime(os.path.join(ROOT, f)), datetime.timezone.utc)).total_seconds() / 3600
            print(f"  note {f} is {age:.1f} h old"
                  + ("   <-- lines will have moved; check the number before betting" if age > 6 else ""))
        for sec in ("spreads", "totals", "props"):
            for it in self.content[sec]:
                g = self.game_of(it)
                if not g:
                    continue
                u = datetime.datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
                e = u.astimezone(tz)
                sat = e.weekday() == 5
                self.ok(sat, "not Saturday in ET", f"{it['pick']} {e:%a %Y-%m-%d %H:%M}")
                # the board's own `started` flag is frozen at build time, so a game
                # that kicked off after the build still reads False. The live test is
                # the kickoff timestamp against the clock.
                ahead = (u - datetime.datetime.now(datetime.timezone.utc)).total_seconds() / 3600
                self.ok(ahead > 0, "kickoff is in the past", f"{it['pick']} {u:%Y-%m-%d %H:%M}Z")
                self.ok(not g["started"], "flagged started on the board", it["pick"])
                note = "  (reads Sunday in UTC)" if u.weekday() == 6 else ""
                print(f"  {'ok  ' if sat and ahead > 0 else 'FAIL'} {it['pick']:<46}"
                      f"{e:%a %H:%M ET}  UTC {u:%a %H:%M}  in {ahead:5.1f}h{note}")

    # -------------------------------------------------------------------- ties
    def check_ties(self):
        print("\n--- ranks that are ties must be written 'tied Nth' ---")
        flagged = 0
        for sec in ("spreads", "totals", "props"):
            for it in self.content[sec]:
                g = self.game_of(it)
                if not g:
                    continue
                exact, halves = set(), {}
                for side in ("home", "away"):
                    for unit in ("off", "def"):
                        for k, v in g["five_factors"][f"{side}_{unit}"].items():
                            (exact.add(int(v)) if v == int(v)
                             else halves.setdefault(int(v), []).append(f"{g[side+'_display']} {unit} {MET[k]}={v:g}"))
                    for key in ("sp_rank", "tempo_rank"):
                        v = g[side + "_power"][key]
                        (exact.add(int(v)) if v == int(v)
                         else halves.setdefault(int(v), []).append(f"{g[side+'_display']} {key}={v:g}"))
                for m in re.finditer(r'(?<!tied )\b(\d+)(st|nd|rd|th)\b', self.text(it)):
                    n = int(m.group(1))
                    if n in halves and n not in exact:
                        flagged += 1
                        self.ok(False, "tie cited as a plain rank",
                                f"{it['pick']}: '{m.group(0)}' -> {halves[n]}")
                        print(f"  FAIL {it['pick']:<40}'{m.group(0)}' is really {halves[n]}")
        if not flagged:
            print("  ok   every tie on the card uses the 'tied Nth' form")
        self.checks += 1

    # ------------------------------------------------------------------ grades
    def check_grades(self):
        print("\n--- grade values ---")
        bad = 0
        for sec in ("spreads", "totals", "props"):
            for it in self.content[sec]:
                g = self.game_of(it)
                if not g:
                    continue
                pool = {round(v, 1) for side in ("home", "away")
                        for k, v in g[side + "_grades"].items() if k.startswith("grade_")}
                # a prop write-up may also quote the player's own PFF grades, and
                # those of a named alternative it was taken ahead of
                for src in (self.rush, self.recv):
                    for nm, row in src.items():
                        if nm in self.text(it):
                            for col in ("grades_run", "grades_pass_route", "grades_offense"):
                                if row.get(col):
                                    pool.add(round(float(row[col]), 1))
                GRADEWORD = (r'(?:run defense |pass block |run block |pass rush |coverage |'
                             r'tackling |passing |receiving |offense |offensive |defensive |'
                             r'route |run |special teams )?')
                for m in re.finditer(r'(\d{2}\.\d)\s' + GRADEWORD + r'grade', self.text(it)):
                    v = float(m.group(1))
                    if v not in pool:
                        bad += 1
                        self.ok(False, "grade not found in any source for this pick",
                                f"{it['pick']}: {m.group(0)!r}")
                        print(f"  FAIL {it['pick']:<40}{m.group(0)!r}")
        if not bad:
            print("  ok   every grade quoted traces to a team grade dict or a player's PFF row")
        self.checks += 1

    # ----------------------------------------------------------------- numbers
    def check_numbers(self):
        print("\n--- model numbers against recompute.py ---")
        for it in self.content["spreads"]:
            g = self.game_of(it)
            r = self.calc[(g["away_team"], g["home_team"])]
            home_side = (r["spread_gap"] - self.level) < 0
            book = r["book_spread"] if home_side else -r["book_spread"]
            model = r["pred_spread"] if home_side else -r["pred_spread"]
            pts = r["pts_margin"] if home_side else -r["pts_margin"]
            net = r["spread_gap"] - self.level
            parts = [(f"{fmt(abs(book))}", "Book line"),
                     (f"{fmt(abs(model))}", "Model number"),
                     (f"{fmt(abs(r['spread_gap']))} pts, {fmt(abs(net))}", "Gap"),
                     (f"{fmt(abs(pts))}", "Points check")]
            allok = True
            for want, label in parts:
                got = self.fact(it, label) or ""
                if not self.ok(want in got, f"{label} mismatch", f"{it['pick']}: want {want} in {got!r}"):
                    allok = False
            print(f"  {'ok  ' if allok else 'FAIL'} {it['pick']:<22}book {book:+6.1f} model {model:+6.1f} "
                  f"gap {r['spread_gap']:+5.1f} net {net:+5.1f} points {pts:+6.1f}")
        for it in self.content["totals"]:
            g = self.game_of(it)
            r = self.calc[(g["away_team"], g["home_team"])]
            want = [(fmt(abs(r["pred_total"])), "Model number"),
                    (fmt(abs(r["resid"])), "Residual"),
                    (fmt(r["pts_total"]), "Points check")]
            allok = True
            for w, label in want:
                got = self.fact(it, label) or ""
                if not self.ok(w in got, f"{label} mismatch", f"{it['pick']}: want {w} in {got!r}"):
                    allok = False
            bt = self.fact(it, "Book total") or ""
            consensus = fmt(r["book_total"], 2).rstrip("0").rstrip(".")
            if not re.match(r'^\d+(\.\d+)?', bt):
                self.ok(False, "Book total unparseable", f"{it['pick']}: {bt!r}")
            else:
                written = float(re.match(r'^\d+(\.\d+)?', bt).group())
                if written != r["book_total"]:
                    # a consensus line that is not bettable may be moved, but only
                    # against the pick, and the real number has to be disclosed
                    worse = (written < r["book_total"]) if it["pick"].startswith("Under") else (written > r["book_total"])
                    self.ok(worse, "book total moved in the pick's favour",
                            f"{it['pick']}: wrote {written}, feed says {r['book_total']}")
                    self.ok(consensus in bt, "moved book total does not disclose the feed number",
                            f"{it['pick']}: {bt!r} should mention {consensus}")
            print(f"  {'ok  ' if allok else 'FAIL'} {it['pick']:<22}book {r['book_total']:6.2f} "
                  f"model {r['pred_total']:6.1f} resid {r['resid']:+5.1f} points {r['pts_total']:6.1f}")

    # ----------------------------------------------------------------- scoring
    def check_scoring(self):
        print("\n--- per-game scoring and records (rounding half up) ---")
        bad = 0
        for sec in ("spreads", "totals"):
            for it in self.content[sec]:
                g = self.game_of(it)
                t = self.text(it)
                for side in ("home", "away"):
                    gr = g[side + "_grades"]
                    row = self.grades[(gr["pf"], gr["pa"], gr["grade_over"])]
                    w, l = [int(x) for x in row["record"].split(" - ")[:2]]
                    n = w + l
                    disp = g[side + "_display"]
                    # if a per-game figure for this team is quoted, it must be the
                    # half-up value, and the half-down value must NOT appear
                    for pts, what in ((gr["pf"] / n, "for"), (gr["pa"] / n, "against")):
                        up, down = fmt(pts), f"{pts:.1f}"
                        if up != down and down in t and up not in t:
                            bad += 1
                            self.ok(False, "per-game figure rounded the wrong way",
                                    f"{it['pick']} {disp} {what}: wrote {down}, should be {up}")
                            print(f"  FAIL {it['pick']:<22}{disp:<16}{what:<8}wrote {down}, should be {up}")
                # every W-L token in the text must be one of the four real
                # records in this game. A proximity rule cannot tell a team's
                # straight-up record from the other team's ATS record, so check
                # membership instead: a wrong record is a token that matches none.
                legit = set()
                for side2 in ("home", "away"):
                    gr2 = g[side2 + "_grades"]
                    row2 = self.grades[(gr2["pf"], gr2["pa"], gr2["grade_over"])]
                    for rec in (row2["record"].replace(" ", ""),
                                g[side2 + "_power"]["ats_record"],
                                g[side2 + "_power"]["over_record"]):
                        legit.add(rec)
                        legit.add(rec[:-2] if rec.endswith("-0") else rec)
                facts_only = " ".join(v for _, v in it["facts"])
                for m in re.finditer(r'\b\d-\d(?:-\d)?\b', facts_only):
                    if m.group(0) not in legit:
                        bad += 1
                        self.ok(False, "record not held by either team in this game",
                                f"{it['pick']}: '{m.group(0)}' not in {sorted(legit)}")
                        print(f"  FAIL {it['pick']:<22}record '{m.group(0)}' matches neither team")
                print(f"  ok   {it['pick']:<22}{g['away_display']:<14}"
                      f"ATS {g['away_power']['ats_record']:<8}O/U {g['away_power']['over_record']:<8}| "
                      f"{g['home_display']:<16}ATS {g['home_power']['ats_record']:<8}O/U {g['home_power']['over_record']}")
        if not bad:
            print("  ok   no per-game figure is rounded the wrong way")
        self.checks += 1

    # -------------------------------------------------------------------- prop
    def check_props(self):
        print("\n--- prop production ---")
        for it in self.content["props"]:
            name = None
            for nm in list(self.rush) + list(self.recv):
                if it["pick"].startswith(nm) and (name is None or len(nm) > len(name)):
                    name = nm
            if not self.ok(name is not None, "prop player not found in the PFF files", it["pick"]):
                continue
            kind = "rush" if "Rushing" in it["pick"] else "recv"
            row = (self.rush if kind == "rush" else self.recv)[name]
            gp = int(row["player_game_count"])
            t = self.text(it)
            want = {"season yards": row["yards"], "yds/gm": fmt(float(row["yards"]) / gp),
                    "long": row["longest"]}
            if kind == "rush":
                want.update({"attempts": row["attempts"], "att/gm": fmt(float(row["attempts"]) / gp),
                             "ypa": row["ypa"], "avoided tackles": row["avoided_tackles"],
                             "yds after contact": row["yards_after_contact"],
                             "breakaway%": row["breakaway_percent"], "run grade": row["grades_run"]})
            else:
                want.update({"targets": row["targets"], "tgt/gm": fmt(float(row["targets"]) / gp),
                             "routes": row["routes"], "yprr": row["yprr"],
                             "aDOT": row["avg_depth_of_target"], "receptions": row["receptions"],
                             "route grade": row["grades_pass_route"]})
            miss = [f"{k}={v}" for k, v in want.items() if str(v) not in t]
            self.ok(not miss, "prop figure missing or wrong", f"{it['pick']}: {miss}")
            print(f"  {'ok  ' if not miss else 'FAIL'} {name:<20}{gp}g  " +
                  "  ".join(f"{k} {v}" for k, v in list(want.items())[:5]) +
                  (f"   MISSING {miss}" if miss else ""))
            # availability: the screen that was added after a void
            team_max = max([int(r["player_game_count"]) for r in self.rush.values() if r["team_name"] == row["team_name"]] +
                           [int(r["player_game_count"]) for r in self.recv.values() if r["team_name"] == row["team_name"]])
            self.ok(gp == team_max, "player is behind his team's game count",
                    f"{name}: {gp} vs {team_max}")

    # ----------------------------------------------------------- superlatives
    # A superlative is a claim about a SET, and the set is never the one memory
    # reaches for. Week 5 drafted five false ones -- "the slowest on this card"
    # when two teams on the same card were slower, "the fourth largest on the
    # board" when it was sixth, "the thinnest cushion" when another pick had
    # less, "the best defensive number in this game" when the opponent's run
    # defense was higher, and "the widest unit gap in this game" when tackling
    # was twice as wide. So every scoped superlative must be registered here
    # with a predicate that computes it. An unregistered one fails.
    #
    # Cross-card comparisons are not written at all any more: which of five picks
    # has the biggest gap ranks the card against itself and says nothing about the
    # game. "on this card" therefore stays in SCOPE with nothing registered behind
    # it, so reintroducing one fails the run rather than shipping unverified.
    # Slate-wide ("on the board", all 49 games), within-game and national claims
    # are real and stay registered.
    SUP = (r'(largest|smallest|most|least|widest|biggest|highest|lowest|weakest|strongest|'
           r'hardest|easiest|best|worst|fastest|slowest|tightest|thinnest|only|'
           r'second-largest|third-slowest|dead last)')
    SCOPE = (r'(on this card|on the card|on this prop card|on the board|on the slate|'
             r'in this game|in this matchup|in the country|of any team|of any back|'
             r'of any receiver|of any player|of the ten teams|nationally)')

    def card_rows(self, sec):
        out = []
        for it in self.content[sec]:
            g = self.game_of(it)
            out.append((it, g, self.calc[(g["away_team"], g["home_team"])]))
        return out

    def cushions(self):
        """Spread card: how far the points check sits past the market, per pick."""
        out = {}
        for it, g, r in self.card_rows("spreads"):
            net = r["spread_gap"] - self.level
            out[it["pick"]] = -r["pts_check_spread"] if net < 0 else r["pts_check_spread"]
        return out

    def card_teams(self, sec, key):
        vals = []
        for it, g, r in self.card_rows(sec):
            for side in ("home", "away"):
                vals.append((g[side + "_display"], g[side + "_power"][key]))
        return sorted(set(vals), key=lambda x: x[1])

    def implied(self, sec):
        out = []
        for it, g, r in self.card_rows(sec):
            tot, sp = r["book_total"], r["book_spread"]
            out += [(g["away_display"], (tot + sp) / 2), (g["home_display"], (tot - sp) / 2)]
        return sorted(set(out), key=lambda x: x[1])

    def prop_rows(self):
        out = []
        for it in self.content["props"]:
            name = max((nm for nm in list(self.rush) + list(self.recv) if it["pick"].startswith(nm)),
                       key=len, default=None)
            kind = "rush" if "Rushing" in it["pick"] else "recv"
            out.append((it, name, kind, (self.rush if kind == "rush" else self.recv)[name]))
        return out

    def check_superlatives(self):
        print("\n--- scoped superlatives, each computed rather than recalled ---")
        cu = self.cushions()
        nets = {abs(r["spread_gap"] - self.level) for r in self.calc.values()}
        resids = {abs(r["resid"]) for r in self.calc.values()}
        sp_tempo = self.card_teams("spreads", "tempo_rank")
        to_tempo = self.card_teams("totals", "tempo_rank")
        pr_imp = self.implied("props")
        props = self.prop_rows()

        def gap_to_line(row, it):
            line = float(next(v for k, v in it["facts"] if k == "Book line"))
            gp = int(row["player_game_count"])
            return abs(float(row["yards"]) / gp - line)

        shares = {}
        for it, name, kind, row in props:
            if kind == "rush":
                team = row["team_name"]
                tot = sum(float(r["attempts"] or 0) for r in self.rush.values() if r["team_name"] == team)
                shares[name] = float(row["attempts"]) / tot * 100
        covs = {}
        for it, g, r in self.card_rows("props"):
            name = max((nm for nm in list(self.rush) + list(self.recv) if it["pick"].startswith(nm)), key=len)
            row = self.rush.get(name) or self.recv.get(name)
            # the opponent is the side whose PFF team name is not the player's
            for side in ("home", "away"):
                other = "away" if side == "home" else "home"
                if g[side + "_display"].upper().startswith(row["team_name"].split()[0][:4]):
                    covs[it["pick"]] = g[other + "_grades"]["grade_cov"]
            covs.setdefault(it["pick"], None)

        REG = {
          "the slowest tempo in the country at 138th":
            lambda: self.board[("Eastern Michigan Eagles", "UMass Minutemen")]
                        ["home_power"]["tempo_rank"] == 138.0,
          "the slowest pace in the country, 138th of 138":
            lambda: self.board[("Eastern Michigan Eagles", "UMass Minutemen")]
                        ["home_power"]["tempo_rank"] == 138.0,
          "the better passing offence in the game":
            lambda: (self.board[("Virginia Cavaliers", "Florida State Seminoles")]["away_grades"]["grade_pass"]
                     > self.board[("Virginia Cavaliers", "Florida State Seminoles")]["home_grades"]["grade_pass"]),
          "the weak unit on the field":
            lambda: (self.board[("Syracuse Orange", "UConn Huskies")]["home_grades"]["grade_def"]
                     < self.board[("Syracuse Orange", "UConn Huskies")]["away_grades"]["grade_def"]),
          "comfortably the better offense on the field":
            lambda: (self.board[("Stanford Cardinal", "Wake Forest Demon Deacons")]["home_grades"]["grade_off"]
                     > self.board[("Stanford Cardinal", "Wake Forest Demon Deacons")]["away_grades"]["grade_off"]),
          "+7.1, the largest on the board": lambda: 7.1 == round(max(resids), 1),
        }
        seen = set()
        for sec in ("spreads", "totals", "props"):
            for it in self.content[sec]:
                for src in [v for _, v in it["facts"]] + it["paras"]:
                    for sent in re.split(r'(?<=[.;:])\s+', src):
                        if not (re.search(self.SUP, sent, re.I) and re.search(self.SCOPE, sent, re.I)):
                            continue
                        key = next((k for k in REG if k in sent), None)
                        if key is None:
                            self.ok(False, "UNREGISTERED superlative -- verify it or rewrite it",
                                    f"{it['pick']}: {sent.strip()[:110]}")
                            print(f"  FAIL {it['pick'][:24]:<25}unregistered: {sent.strip()[:80]}")
                            continue
                        seen.add(key)
                        try:
                            good = bool(REG[key]())
                        except Exception as e:
                            good = False
                            key = f"{key} (predicate raised {type(e).__name__}: {e})"
                        self.ok(good, "FALSE superlative", f"{it['pick']}: {key}")
                        print(f"  {'ok  ' if good else 'FAIL'} {it['pick'][:24]:<25}{key[:86]}")
        unused = [k for k in REG if k not in seen]
        if unused:
            print(f"  note: {len(unused)} registered claims no longer appear in the card")

    # ------------------------------------------------------------------ history
    def check_history(self):
        """The Purdue/Illinois Under argues from week 4's grading. Those figures are
        in PROJECT_STATE quirk 16 and, for the four that were bet, in picks_log."""
        print("\n--- the week 4 claims the card argues from ---")
        prior = [r for r in csv.DictReader(open(os.path.join(ROOT, "picks_log.csv")))
                 if r["week"] == str(self.week - 1) and r["category"] == "total"]
        tally = {"WIN": 0, "LOSS": 0, "PUSH": 0}
        for r in prior:
            tally[r["result"].strip().upper()] = tally.get(r["result"].strip().upper(), 0) + 1
        kept = f"{tally['WIN']}-{tally['LOSS']}-{tally['PUSH']}"
        import html as _html, re as _re, zipfile as _zip
        _z = _zip.ZipFile(os.path.join(ROOT, "articles", "Week5_Totals.docx"))
        text = _html.unescape(_re.sub(r"<[^>]+>", " ",
                 _z.read("word/document.xml").decode("utf-8")))
        self.ok(kept in text, "the kept-totals record does not match picks_log",
                f"log says {kept}")
        print(f"  {'ok  ' if kept in text else 'FAIL'} week {self.week-1} totals in picks_log: {kept}")
        state = open(os.path.join(ROOT, "PROJECT_STATE.md")).read()
        for claim in ("3-1", "1-2-1", "3.10"):
            inboth = claim in text and claim in state
            self.ok(inboth, "claim not corroborated by PROJECT_STATE", claim)
            print(f"  {'ok  ' if inboth else 'FAIL'} '{claim}' appears in both the card and PROJECT_STATE")

    # --------------------------------------------------------------------- log
    def check_log(self):
        print("\n--- picks_log coverage ---")
        n = 0
        for sec, cat in (("spreads", "spread"), ("totals", "total"), ("props", "prop")):
            for it in self.content[sec]:
                n += 1
                m = re.search(r'([+-]?\d+(?:\.\d+)?)\s*$' if cat == "spread" else r'(\d+(?:\.\d+)?)',
                              it["pick"].split(" Rushing")[0].split(" Receiving")[0])
                line = m.group(1) if m else None
                hit = [r for r in self.log if r["category"] == cat and line and
                       abs(abs(float(r["line"])) - abs(float(line))) < 1e-9]
                self.ok(bool(hit), "no picks_log row", f"{it['pick']} (line {line})")
                print(f"  {'ok  ' if hit else 'FAIL'} {cat:<7}{it['pick']:<46}line {line}")
        self.ok(len(self.log) == n, "picks_log row count",
                f"card has {n} picks, log has {len(self.log)} rows for week {self.week}")
        print(f"  {'ok  ' if len(self.log)==n else 'FAIL'} {n} picks on the card, {len(self.log)} rows in the log")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", type=int, default=2026)
    args = ap.parse_args()
    qa = QA(args.week, args.season)
    qa.check_kickoffs()
    qa.check_ties()
    qa.check_grades()
    qa.check_numbers()
    qa.check_scoring()
    qa.check_props()
    qa.check_superlatives()
    qa.check_history()
    qa.check_log()
    print("\n" + "=" * 72)
    if qa.fails:
        print(f"{len(qa.fails)} FAILURES out of {qa.checks} checks:")
        for f in qa.fails:
            print("  -", f)
        return 1
    print(f"all {qa.checks} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
