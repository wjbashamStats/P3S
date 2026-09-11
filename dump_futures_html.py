#!/usr/bin/env python3
"""
dump_futures_html.py -- render VegasInsider's National Championship,
win-totals, and conference-championship futures pages (JS-rendered odds
tables, same pages AllTeamsFuturesWorkingFinal.R hit with chromote) and
save each one's HTML to a local folder.

Run this on YOUR machine (this sandbox has no network access to
vegasinsider.com), then send the futures_html_dump/ folder back --
build_futures_from_html.py parses these and merges into
team_ratings_2025.csv.

One-time setup:
  pip install playwright
  playwright install chromium

Run:
  python3 dump_futures_html.py
  python3 dump_futures_html.py --out-dir futures_html_dump --wait 10
"""
import argparse
import os

from playwright.sync_api import sync_playwright

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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default="futures_html_dump")
    ap.add_argument("--wait", type=float, default=8.0,
                    help="seconds to let each page's JS render before grabbing HTML")
    ap.add_argument("--only", default=None,
                    help="comma-separated subset of page keys to fetch, e.g. "
                         "win_totals,national_futures (default: all)")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    keys = args.only.split(",") if args.only else list(PAGES.keys())

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for key in keys:
            url = PAGES.get(key)
            if not url:
                print(f"  [skip] unknown page key: {key} (valid: {list(PAGES)})")
                continue
            print(f"Fetching {key} <- {url}")
            page.goto(url, timeout=60000)
            page.wait_for_timeout(int(args.wait * 1000))
            html = page.content()
            out_path = os.path.join(args.out_dir, f"{key}.html")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  saved {out_path} ({len(html):,} bytes)")
        browser.close()

    print(f"\nDone. Zip {args.out_dir}/ (or send the files individually).")


if __name__ == "__main__":
    main()
