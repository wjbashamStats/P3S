#!/usr/bin/env python3
"""
build_pages.py -- inject this week's data into the page templates.

pages/*_page.html are TEMPLATES, not deployable pages: each one carries its
markup, CSS and JS, but its data payload is an empty

    <script id="..." type="application/json" data-source="..."></script>

tag. The payload is injected here, at build time, from the data file named
in data-source. Without this split the committed page was a verbatim copy
of a JSON file that also lives in the repo -- impact_page.html was 3.4MB
of which 98.8% was impact_2026wk2.json -- so every weekly rebuild stored
the same data twice in git history.

data-source is resolved with {season} and {week} substituted, so one
template serves every week. data-encoding="json-string" wraps a non-JSON
source (the FanDuel salary CSV) as a JSON string literal, which is how the
page's own loader expects it.

Injection is done at build time rather than fetched at runtime because the
hub embeds each page into an iframe srcdoc, which has an opaque origin and
no base URL -- a page that fetched its own data file would render standalone
and then come up empty inside the hub.

Run:  python3 pages/build_pages.py --season 2026 --week 2
Out:  pages/build/*_page.html  (gitignored -- regenerate, don't commit)
"""
import argparse
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

TAG_RE = re.compile(
    r'(<script id="(?P<id>[^"]+)" type="application/json"'
    r'(?P<attrs>[^>]*?)></script>)')
SRC_RE = re.compile(r'data-source="([^"]+)"')
ENC_RE = re.compile(r'data-encoding="([^"]+)"')


def payload_for(path, encoding):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if encoding == "json-string":
        # the source isn't JSON (a CSV); hand the page the whole file as one
        # JSON string literal, which is what its loader parses.
        return json.dumps(text)
    return json.dumps(json.loads(text), separators=(",", ":"))


def build_page(template, out_dir, season, week, data_dir):
    with open(template, encoding="utf-8") as f:
        html = f.read()
    injected = []

    def sub(m):
        attrs = m.group("attrs")
        src_m = SRC_RE.search(attrs)
        if not src_m:
            return m.group(1)          # not a data tag; leave it alone
        rel = src_m.group(1).format(season=season, week=week)
        path = os.path.join(data_dir, rel)
        enc_m = ENC_RE.search(attrs)
        body = payload_for(path, enc_m.group(1) if enc_m else "json")
        injected.append((m.group("id"), rel, len(body)))
        return (f'<script id="{m.group("id")}" type="application/json"{attrs}>'
                f'{body}</script>')

    out_html = TAG_RE.sub(sub, html)
    if not injected:
        return None
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, os.path.basename(template))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out_html)
    return out_path, injected, len(html), len(out_html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--week", type=int, default=2)
    ap.add_argument("--data-dir", default=REPO, help="where the data files live")
    ap.add_argument("--out", default=os.path.join(HERE, "build"))
    args = ap.parse_args()

    for template in sorted(glob.glob(os.path.join(HERE, "*_page.html"))):
        result = build_page(template, args.out, args.season, args.week, args.data_dir)
        if result is None:
            print(f"{os.path.basename(template)}: no data tags, skipped")
            continue
        out_path, injected, tmpl_len, out_len = result
        srcs = ", ".join(f"{i} <- {s} ({n:,})" for i, s, n in injected)
        print(f"{os.path.basename(template)}: {tmpl_len:,} -> {out_len:,} bytes | {srcs}")
    print(f"\nWrote page builds to {args.out}")


if __name__ == "__main__":
    main()
