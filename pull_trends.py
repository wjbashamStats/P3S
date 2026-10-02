#!/usr/bin/env python3
"""
pull_trends.py -- fetch the three TeamRankings trends pages instead of saving
them by hand.

RUN THIS LOCALLY. This sandbox's network policy blocks teamrankings.com (the
agent proxy answers 403 to the CONNECT), which is why these pages have been
arriving as Save Page As files and pasted tables. Everything except the
fetch itself runs anywhere, so --from-cache below re-validates pages you
already have without touching the network.

What it does, per page:
  1. GET https://www.teamrankings.com/ncf/trends/<page>/?range=yearly_<season>
  2. Parse it with actionnet/teamrankings.py -- the SAME parser the build
     uses -- before anything is written. A redirect to a login wall, a block
     page, or a layout change fails here loudly instead of quietly writing a
     file that parses to zero teams.
  3. Refuse to overwrite a good file with a worse one: if the existing file
     parses to more teams than the new fetch, the new one is written to
     <name>.rejected and the old file is left alone.
  4. Report how deep each team's record is, so a stale fetch is obvious
     before it reaches the model rather than three steps later.

A paste saved as <stem>.txt is superseded once <stem>.html lands, because
load_trends_dir prefers .html. Rather than leave that trap set, the old
paste is renamed to <stem>.txt.superseded and the rename is reported.

Usage:
  python3 pull_trends.py                        # all three, current season
  python3 pull_trends.py --season 2026
  python3 pull_trends.py --pages ats ou         # just the ones that moved
  python3 pull_trends.py --dry-run              # fetch + validate, write nothing
  python3 pull_trends.py --from-cache some/dir  # validate files you already have
"""
import argparse
import collections
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "actionnet"))
from teamrankings import parse_trends, EXTS                      # noqa: E402

TRENDS_DIR = os.path.join(HERE, "actionnet", "input", "trends")
BASE = "https://www.teamrankings.com/ncf/trends/{page}/"

# page stem -> (url slug, parser prefix, the record column to report depth on)
PAGES = {
    "win": ("win_trends", "TR_win", "TR_win_win_loss_record"),
    "ats": ("ats_trends", "TR_ats", "TR_ats_ats_record"),
    "ou":  ("ou_trends", "TR_ou", "TR_ou_over_record"),
}

# TeamRankings serves a different (JS-shell) page to clients it does not
# recognise as a browser, and that shell has no results table in it, so the
# parse would fail with a confusing "no tr-table" rather than a block message.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch(slug, season, timeout=30):
    url = BASE.format(page=slug) + f"?range=yearly_{season}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return url, r.read().decode("utf-8", errors="replace")


def record_depth(rows, col):
    """{games played: how many teams} -- the freshness tell. A page saved
    before the weekend shows most teams a game behind the rest of the data."""
    depth = collections.Counter()
    for r in rows:
        n = sum(int(r.get(col + s) or 0) for s in ("_W", "_L", "_T"))
        if n:
            depth[n] += 1
    return dict(sorted(depth.items()))


def existing_team_count(path, prefix):
    if not os.path.exists(path):
        return 0
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return len(parse_trends(fh.read(), prefix))
    except Exception:
        return 0


def supersede_paste(stem, outdir, log):
    """An .html overrides a .txt paste for the same page. Get the paste out of
    the way so nobody later wonders which one the build read."""
    for ext in (".txt", ".tsv"):
        p = os.path.join(outdir, stem + ext)
        if os.path.exists(p):
            dest = p + ".superseded"
            os.replace(p, dest)
            log(f"         renamed {os.path.basename(p)} -> {os.path.basename(dest)} "
                f"(.html takes precedence)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=None,
                    help="range filter year; defaults to config.SEASON")
    ap.add_argument("--pages", nargs="*", choices=sorted(PAGES), default=sorted(PAGES),
                    help="which pages to pull (default: all three)")
    ap.add_argument("--out-dir", default=TRENDS_DIR)
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and validate, write nothing")
    ap.add_argument("--from-cache", default=None, metavar="DIR",
                    help="read <stem>_trends.html from DIR instead of fetching -- "
                         "validates pages saved by hand, and needs no network")
    args = ap.parse_args()

    season = args.season
    if season is None:
        try:
            import config as C
            season = C.SEASON
        except Exception:
            season = 2026

    os.makedirs(args.out_dir, exist_ok=True)
    ok, failed = 0, []
    for key in args.pages:
        slug, prefix, reccol = PAGES[key]
        dest = os.path.join(args.out_dir, slug + ".html")
        try:
            if args.from_cache:
                src = os.path.join(args.from_cache, slug + ".html")
                if not os.path.exists(src):
                    raise FileNotFoundError(src)
                html = open(src, encoding="utf-8", errors="replace").read()
                where = src
            else:
                where, html = fetch(slug, season)
            rows = parse_trends(html, prefix)
        except urllib.error.HTTPError as e:
            failed.append((slug, f"HTTP {e.code} {e.reason}")); continue
        except urllib.error.URLError as e:
            failed.append((slug, f"cannot reach the site ({e.reason}). This sandbox "
                                 f"blocks teamrankings.com -- run it on your machine")); continue
        except Exception as e:
            failed.append((slug, f"{type(e).__name__}: {e}")); continue

        if not rows:
            failed.append((slug, "parsed zero teams")); continue

        depth = record_depth(rows, reccol)
        print(f"[ok]   {slug:12} {len(rows):3} teams from {where}")
        print(f"         games played per team: {depth}")

        prior = existing_team_count(dest, prefix)
        if args.dry_run:
            print("         --dry-run, not written")
            ok += 1
            continue
        if prior > len(rows):
            rej = dest + ".rejected"
            open(rej, "w", encoding="utf-8").write(html)
            failed.append((slug, f"fetch has {len(rows)} teams but the file on disk has "
                                 f"{prior}; wrote {os.path.basename(rej)} and kept the old one"))
            continue
        open(dest, "w", encoding="utf-8").write(html)
        print(f"         wrote {dest}")
        supersede_paste(slug, args.out_dir, print)
        ok += 1

    print()
    for slug, why in failed:
        print(f"[FAIL] {slug:12} {why}")
    print(f"{ok}/{len(args.pages)} pages refreshed"
          + (" -- re-run build_team_ratings_2026.py to pick them up" if ok and not args.dry_run else ""))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
