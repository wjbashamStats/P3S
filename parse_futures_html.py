#!/usr/bin/env python3
"""
parse_futures_html.py -- extract conference/championship futures odds and
win-totals from a saved VegasInsider odds page (e.g. vegasinsider.com/
college-football/odds/sec-championship/, .../win-totals/, .../futures/).

This project's sandbox can't reach vegasinsider.com directly (network
policy blocks it), so the workflow is: save the page's HTML (view-source,
or paste it) to a file, then run this script against that file. Pure
stdlib (re + html.unescape) -- no bs4/lxml dependency, matching the rest
of this project's convention.

Handles two page shapes:
  1. A "winner" odds table: rows like
     <tr ... data-name="georgia"> ... <span class="data-value"> +250 </span> ...
     One row per team, one data-value per sportsbook column. Consensus
     price is the median across books.
  2. A plain win-totals list: <h2>...WIN TOTALS...</h2> followed by
     <ul class="wp-block-list"><li>Alabama 8.5</li>...</ul>

Usage:
  python3 parse_futures_html.py sec_championship.html --out sec_championship_odds.csv
  python3 parse_futures_html.py sec_championship.html --win-totals --out sec_win_totals.csv
"""
import argparse
import csv
import html
import re
import statistics as st


ROW_RE = re.compile(
    r'<tr[^>]*data-name="([^"]+)"[^>]*>(.*?)</tr>',
    re.DOTALL | re.IGNORECASE,
)
DATA_VALUE_RE = re.compile(r'data-value">\s*([+-]?\d+)\s*<', re.IGNORECASE)
TEAM_NAME_RE = re.compile(
    r'class="team-name[^"]*"[^>]*aria-label="([^"]+)"', re.IGNORECASE
)


def parse_winner_table(html_text):
    """Returns [{team, consensus_price, n_books, all_prices}]."""
    rows = []
    for m in ROW_RE.finditer(html_text):
        _slug, block = m.group(1), m.group(2)
        name_m = TEAM_NAME_RE.search(block)
        if not name_m:
            continue
        team = html.unescape(name_m.group(1)).strip()
        prices = [int(p) for p in DATA_VALUE_RE.findall(block)]
        if not prices:
            continue
        rows.append(dict(
            team=team,
            consensus_price=st.median(prices),
            n_books=len(prices),
            all_prices=prices,
        ))
    rows.sort(key=lambda r: r["consensus_price"])
    return rows


def parse_win_totals(html_text, heading_pattern=r"WIN TOTALS"):
    """Finds the <h2>...heading_pattern...</h2> then the next <ul> of
    "<li>Team X.X</li>" entries. Returns [{team, win_total}]."""
    heading_re = re.compile(
        r'<h2[^>]*>[^<]*' + heading_pattern + r'[^<]*</h2>', re.IGNORECASE
    )
    m = heading_re.search(html_text)
    if not m:
        return []
    rest = html_text[m.end():]
    ul_m = re.search(r'<ul[^>]*>(.*?)</ul>', rest, re.DOTALL | re.IGNORECASE)
    if not ul_m:
        return []
    li_re = re.compile(r'<li[^>]*>\s*([^<]+?)\s*</li>', re.IGNORECASE)
    out = []
    for li in li_re.findall(ul_m.group(1)):
        text = html.unescape(li).strip()
        num_m = re.search(r'([\d.]+)\s*$', text)
        if not num_m:
            continue
        team = text[:num_m.start()].strip()
        out.append(dict(team=team, win_total=float(num_m.group(1))))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html_path", help="saved VegasInsider page HTML")
    ap.add_argument("--win-totals", action="store_true",
                    help="parse the win-totals list instead of the winner odds table")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.html_path, encoding="utf-8") as f:
        html_text = f.read()

    if args.win_totals:
        rows = parse_win_totals(html_text)
        print(f"{len(rows)} win-total rows found")
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["team", "win_total"])
            w.writeheader()
            w.writerows(rows)
    else:
        rows = parse_winner_table(html_text)
        print(f"{len(rows)} team rows found")
        for r in rows[:10]:
            print(f"  {r['team']:20s} {r['consensus_price']:>+6}  ({r['n_books']} books)")
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["team", "consensus_price", "n_books"])
            w.writeheader()
            for r in rows:
                w.writerow({k: r[k] for k in ("team", "consensus_price", "n_books")})
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
