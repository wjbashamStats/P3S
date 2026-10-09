#!/usr/bin/env python3
"""
dump_futures_html.py -- render VegasInsider's National Championship,
win-totals and conference-championship futures pages (JS-rendered odds
tables) and save each one's HTML to a local folder.

RUN THIS LOCALLY. The sandbox's network policy denies CONNECT to
vegasinsider.com (the proxy answers 403, logged as a policy denial), so
the fetch itself cannot happen there. Everything after the fetch -- the
parse, the merge, the export -- runs anywhere.

Each page is validated with the build's OWN parser (parse_futures_html)
before anything is written. A consent wall, a bot-check page or a layout
change renders fine and contains no odds table, so writing first and
parsing later produces a file that silently merges zero prices and leaves
last week's numbers in place for that market. Instead:

  * a page that parses to no team rows is written to <name>.html.rejected
    and the previous good file, if any, is left alone;
  * a page that parses to fewer rows than the floor below is written but
    flagged loudly, since a conference race legitimately shrinks as teams
    are eliminated and only you can tell that from a half-rendered page;
  * the row count for every page is printed, so a bad pull is obvious
    here rather than three steps later.

One-time setup:
  pip install playwright
  playwright install chromium

Run:
  python3 dump_futures_html.py --week 6
  python3 dump_futures_html.py --week 6 --wait 12 --only win_totals
  python3 dump_futures_html.py --week 6 --dry-run      # fetch + validate, write nothing
  python3 dump_futures_html.py --validate futures_html/week6   # check saved pages, no network

Then, back in the repo:
  python3 refresh_futures.py --week 6

Saves into futures_html/week<N>/ so each pull is its own dated snapshot,
matching how the weekly live pulls are kept (hist_lines_live_2026wk<N>.csv).
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from parse_futures_html import parse_winner_table            # noqa: E402

PAGES = {
    "national_futures": "https://www.vegasinsider.com/college-football/odds/futures/",
    "win_totals": "https://www.vegasinsider.com/college-football/odds/win-totals/",
    "SEC_championship": "https://www.vegasinsider.com/college-football/odds/sec-championship/",
    "ACC_championship": "https://www.vegasinsider.com/college-football/odds/acc-championship/",
    "BigTen_championship": "https://www.vegasinsider.com/college-football/odds/big-ten-championship/",
    "Big12_championship": "https://www.vegasinsider.com/college-football/odds/big-12-championship/",
    "AAC_championship": "https://www.vegasinsider.com/college-football/odds/aac-championship/",
    "MWC_championship": "https://www.vegasinsider.com/college-football/odds/mountain-west-championship/",
    "SunBelt_championship": "https://www.vegasinsider.com/college-football/odds/sun-belt-championship/",
    "CUSA_championship": "https://www.vegasinsider.com/college-football/odds/cusa-championship/",
    "MAC_championship": "https://www.vegasinsider.com/college-football/odds/mac-championship/",
}

# What week 1 actually parsed to, which is what "this page rendered" looks like.
# The floor is set below the observed count because a conference field shrinks
# through the season; it is a tripwire for a half-rendered page, not a schema.
WEEK1_ROWS = {
    "national_futures": 138, "win_totals": 138, "SEC_championship": 16,
    "ACC_championship": 17, "BigTen_championship": 18, "Big12_championship": 16,
    "AAC_championship": 14, "MWC_championship": 10, "SunBelt_championship": 14,
    "CUSA_championship": 10, "MAC_championship": 13,
}
FLOORS = {k: (100 if v > 100 else 6) for k, v in WEEK1_ROWS.items()}


def validate_dir(dirpath):
    """Report what each saved page parses to. No network, no browser."""
    import glob
    paths = sorted(glob.glob(os.path.join(dirpath, "*.html")))
    if not paths:
        print(f"no *.html in {dirpath}")
        return 1
    missing = [k for k in PAGES if not os.path.exists(os.path.join(dirpath, k + ".html"))]
    bad = []
    for path in paths:
        key = os.path.basename(path)[: -len(".html")]
        rows = parse_winner_table(open(path, encoding="utf-8", errors="replace").read())
        baseline = WEEK1_ROWS.get(key)
        floor = FLOORS.get(key, 1)
        if not rows:
            state = "FAIL  no odds table -- a consent wall or bot check looks exactly like this"
            bad.append(key)
        elif baseline and len(rows) < floor:
            state = f"warn  {len(rows)} rows against {baseline} in week 1 -- check it rendered in full"
            bad.append(key)
        else:
            state = (f"ok    {len(rows)} rows"
                     + (f" (week 1: {baseline})" if baseline else "")
                     + f", best {rows[0]['team']} {rows[0]['consensus_price']:+g}")
        print(f"  {key:24} {state}")
    if missing:
        print(f"\n[warn] not in this folder: {', '.join(missing)}")
        print("       refresh_futures.py merges only the pages it finds, so a market with no")
        print("       page here silently keeps the prices it already had.")
    print(f"\n{len(paths) - len(bad)}/{len(paths)} pages usable")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=int, help="CFB week number for this pull")
    ap.add_argument("--validate", metavar="DIR", default=None,
                    help="parse every *.html in DIR with the build's parser and report, "
                         "fetching nothing. Use this when the pages were saved by hand "
                         "(Save Page As) instead of rendered by this script.")
    ap.add_argument("--out-dir", default=None,
                    help="override the default futures_html/week<N>/ location")
    ap.add_argument("--wait", type=float, default=8.0,
                    help="seconds to let each page's JS render before grabbing HTML")
    ap.add_argument("--only", default=None,
                    help="comma-separated subset of page keys, e.g. win_totals,national_futures")
    ap.add_argument("--retries", type=int, default=1,
                    help="re-render a page that parsed to zero rows, this many times")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and validate, write nothing")
    args = ap.parse_args()

    if args.validate:
        return validate_dir(args.validate)
    if args.week is None:
        ap.error("--week is required unless --validate DIR is given")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright is not installed here:  pip install playwright && playwright install chromium")

    out_dir = args.out_dir or os.path.join("futures_html", f"week{args.week}")
    os.makedirs(out_dir, exist_ok=True)
    keys = args.only.split(",") if args.only else list(PAGES)

    written, rejected, thin = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for key in keys:
            url = PAGES.get(key)
            if not url:
                print(f"  [skip] unknown page key: {key} (valid: {sorted(PAGES)})")
                continue
            html, rows = "", []
            for attempt in range(args.retries + 1):
                print(f"Fetching {key}{'' if attempt == 0 else f' (retry {attempt})'} <- {url}")
                try:
                    page.goto(url, timeout=60000)
                    page.wait_for_timeout(int(args.wait * 1000))
                    html = page.content()
                except Exception as e:
                    print(f"  [error] {type(e).__name__}: {e}")
                    continue
                rows = parse_winner_table(html)
                if rows:
                    break
                print(f"  parsed 0 team rows from {len(html):,} bytes "
                      f"-- a consent wall or bot check renders exactly like this")
            dest = os.path.join(out_dir, f"{key}.html")
            baseline = WEEK1_ROWS.get(key)
            note = f" (week 1 had {baseline})" if baseline else ""
            if not rows:
                rejected.append(key)
                if not args.dry_run:
                    with open(dest + ".rejected", "w", encoding="utf-8") as f:
                        f.write(html)
                    print(f"  [FAIL] wrote {dest}.rejected and kept any existing {key}.html")
                else:
                    print(f"  [FAIL] would reject {key}")
                continue
            print(f"  {len(rows)} team rows{note}; best price "
                  f"{rows[0]['team']} {rows[0]['consensus_price']:+g} across {rows[0]['n_books']} books")
            if baseline and len(rows) < FLOORS[key]:
                thin.append((key, len(rows), baseline))
                print(f"  [warn] only {len(rows)} rows against {baseline} in week 1 -- "
                      f"check this page rendered in full before merging")
            if args.dry_run:
                print("  --dry-run, not written")
            else:
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"  saved {dest} ({len(html):,} bytes)")
            written.append(key)
        browser.close()

    print()
    for key, n, base in thin:
        print(f"[warn] {key}: {n} rows against week 1's {base}")
    for key in rejected:
        print(f"[FAIL] {key}: no odds table in the rendered page")
    print(f"{len(written)}/{len(keys)} pages validated"
          + ("" if args.dry_run else f" into {out_dir}/"))
    if written and not args.dry_run:
        print(f"\nNext:  python3 refresh_futures.py --week {args.week}")
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
