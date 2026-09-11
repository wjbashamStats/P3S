#!/usr/bin/env python3
"""
build_futures_from_html.py -- merge National Championship and conference-
championship futures odds (scraped/saved as VegasInsider page HTML) into
team_ratings_2025.csv, replacing the old R/chromote/Google-Sheets pipeline
(see AllTeamsFuturesWorkingFinal.R) with a version that writes straight
into this repo instead of a separate Google Sheet.

Does NOT touch "Win Total" / TAN_WIN / SP._WIN -- those are this
project's own model-projected win totals (decimals like 10.73), not a
market line, and build_team_preview_data.py already reads "Win Total" for
that purpose. Market win-total lines belong in the separate
Win_<Book>_TotalLine/Odds/OverUnder/Line columns (see --win-totals).

Per-book columns are named from the ACTUAL header labels found on the
page (Bet365, BetMGM, DraftKings, Caesars, FanDuel, RiversCasino, ...)
rather than positionally guessed -- the old R version silently lost a
book to a generic "X" column when a header didn't parse; this reads the
book name from each column's own <span class="hidden">BookName</span> and
zips it with that row's data-value in the same column position, so a
missing/reordered book can't silently misalign.

This sandbox can't reach vegasinsider.com directly (network policy), so
these HTML files have to be saved/uploaded rather than fetched live --
same constraint as parse_futures_html.py.

Usage:
  python3 build_futures_from_html.py \\
      --team-ratings team_ratings_2025.csv \\
      --national national_futures.html \\
      --conf SEC=sec_championship.html --conf ACC=acc_championship.html \\
      --win-totals win_totals.html \\
      --out team_ratings_2025.csv
"""
import argparse
import csv
import html
import re
import sys
from collections import OrderedDict

import data_load as DL

ROW_RE = re.compile(
    r'<tr[^>]*data-name="([^"]+)"[^>]*>(.*?)</tr>',
    re.DOTALL | re.IGNORECASE,
)
TEAM_NAME_RE = re.compile(
    r'class="team-name[^"]*"[^>]*aria-label="([^"]+)"', re.IGNORECASE
)
HEADER_BOOK_RE = re.compile(
    r'<th[^>]*class="[^"]*book-pinup[^"]*"[^>]*>.*?<span[^>]*class="hidden"[^>]*>([^<]+)</span>',
    re.DOTALL | re.IGNORECASE,
)
DATA_VALUE_RE = re.compile(r'data-value">\s*([+-]?\d+)\s*<', re.IGNORECASE)


def parse_book_headers(html_text):
    """Book display names in column order, from <span class="hidden">Name</span>
    inside each book-pinup <th>. Returns [] if the page shape doesn't match
    (caller falls back to book_1/book_2/... names)."""
    return [html.unescape(m).strip() for m in HEADER_BOOK_RE.findall(html_text)]


def parse_odds_table(html_text, label_prefix):
    """
    Returns {team_norm: {display_team, <prefix>_<Book>: price, ...}}.
    label_prefix: e.g. "Nat" or "Conf".
    """
    books = parse_book_headers(html_text)
    out = OrderedDict()
    for m in ROW_RE.finditer(html_text):
        _slug, block = m.group(1), m.group(2)
        name_m = TEAM_NAME_RE.search(block)
        if not name_m:
            continue
        team = html.unescape(name_m.group(1)).strip()
        prices = DATA_VALUE_RE.findall(block)
        row = dict(display_team=team)
        for i, price in enumerate(prices):
            book = books[i] if i < len(books) else f"book_{i+1}"
            row[f"{label_prefix}_{book}"] = price
        out[DL.norm(team)] = row
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team-ratings", required=True)
    ap.add_argument("--national", default=None, help="national championship futures page HTML")
    ap.add_argument("--conf", action="append", default=[], metavar="LABEL=path.html",
                    help="one conference championship page, e.g. SEC=sec_championship.html "
                         "(repeat for each conference)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.team_ratings, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    by_norm = {DL.norm(r["Team"]): r for r in rows if r.get("Team")}

    def merge_in(parsed, new_cols_seen):
        matched, unmatched = 0, []
        for tnorm, data in parsed.items():
            row = by_norm.get(tnorm)
            if row is None:
                unmatched.append(data["display_team"])
                continue
            matched += 1
            for k, v in data.items():
                if k == "display_team":
                    continue
                row[k] = v
                new_cols_seen.add(k)
        return matched, unmatched

    new_cols = []
    seen = set()

    if args.national:
        with open(args.national, encoding="utf-8") as f:
            text = f.read()
        parsed = parse_odds_table(text, "Nat")
        matched, unmatched = merge_in(parsed, seen)
        print(f"[national] {matched}/{len(parsed)} teams matched to team_ratings_2025.csv")
        if unmatched:
            print(f"  unmatched (no Team match found): {unmatched}")

    for spec in args.conf:
        if "=" not in spec:
            sys.exit(f"--conf must be LABEL=path.html, got: {spec}")
        label, path = spec.split("=", 1)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        parsed = parse_odds_table(text, "Conf")
        matched, unmatched = merge_in(parsed, seen)
        # stamp conference label for every matched team in this page
        for tnorm in parsed:
            row = by_norm.get(tnorm)
            if row is not None:
                row["Conference.y"] = row.get("Conference.y") or label
        print(f"[{label}] {matched}/{len(parsed)} teams matched to team_ratings_2025.csv")
        if unmatched:
            print(f"  unmatched (no Team match found): {unmatched}")

    new_cols = sorted(c for c in seen if c not in fieldnames)
    out_fieldnames = fieldnames + new_cols

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {args.out} ({len(new_cols)} new columns: {new_cols})")


if __name__ == "__main__":
    main()
