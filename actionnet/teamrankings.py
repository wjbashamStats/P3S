#!/usr/bin/env python3
"""
teamrankings.py -- parse a saved TeamRankings trends page into team rows.

Standard library only, same reasoning as xlsx_read.py: this runs unattended on
a schedule and must not depend on a pip install.

The three pages we use, all saved from teamrankings.com/ncf/trends/:

    win_trends.html   Win-Loss Record, Win %, MOV, ATS +/-
    ats_trends.html   against-the-spread record
    ou_trends.html    over/under record

Columns are read from the table's own <thead> rather than hardcoded, so the
ATS and O/U pages parse without anyone having to enumerate their headers here,
and a column TeamRankings adds later shows up on its own.

Values come from each cell's data-sort attribute, not its visible text: the
page rounds for display but keeps full precision in the attribute (ATS +/-
renders "+10.3" while data-sort says 10.25). Any cell holding a W-L-T record
is additionally split into numeric _W / _L / _T columns.
"""
import html as _html
import os
import re
from html.parser import HTMLParser

# TeamRankings' own spellings that neither match our TeamID.TeamRankings column
# nor survive normalisation. Hand-verified against '2026 PR' -- every target
# below is a real team in that sheet. The rest of the slate (133 of 138) needs
# no alias: 95 match TeamID exactly and 38 more match once "St" is expanded to
# "State" and punctuation dropped.
#
# Note these differ from TeamID's stored TeamRankings values, which are stale
# for exactly these five ("James Mad", "Central Mich", "GA Southern",
# "LA Monroe", "North Texas"). The live page is the authority here.
TEAMRANKINGS_ALIASES = {
    "J Madison": "James Madison",
    "C Michigan": "Central Michigan",
    "N Texas": "North Texas",
    "Georgia So": "Georgia Southern",
    "UL Monroe": "ULM",
}

_RECORD_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)(?:\s*-\s*(\d+))?\s*$")


class _TrendsTableParser(HTMLParser):
    """Pulls the first table carrying the tr-table class out of a page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.headers = []
        self.rows = []
        self._in_table = False
        self._done = False
        self._section = None          # "thead" | "tbody"
        self._cell = None             # {"text": [...], "sort": str|None}
        self._row = None
        self._href = None

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        a = dict(attrs)
        if tag == "table" and not self._in_table:
            if "tr-table" in (a.get("class") or ""):
                self._in_table = True
            return
        if not self._in_table:
            return
        if tag in ("thead", "tbody"):
            self._section = tag
        elif tag == "tr":
            self._row = []
        elif tag in ("th", "td"):
            self._cell = {"text": [], "sort": a.get("data-sort")}
        elif tag == "a" and self._cell is not None and self._href is None:
            self._href = a.get("href")

    def handle_endtag(self, tag):
        if self._done or not self._in_table:
            return
        if tag in ("th", "td") and self._cell is not None:
            text = _html.unescape("".join(self._cell["text"])).strip()
            cell = {"text": text, "sort": self._cell["sort"], "href": self._href}
            if self._row is not None:
                self._row.append(cell)
            self._cell = None
            self._href = None
        elif tag == "tr" and self._row is not None:
            if self._section == "thead" and not self.headers:
                self.headers = [c["text"] for c in self._row]
            elif self._section == "tbody" and self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._in_table = False
            self._done = True

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"].append(data)


def _slug(name):
    """Header -> column suffix. Symbols are spelled out BEFORE stripping
    punctuation, otherwise "Win %" and "ATS +/-" both collapse to bare words
    ("win", "ats") and a page with both a Win and a Win % column would collide.
    """
    s = (name or "").strip().lower()
    s = s.replace("+/-", " plus_minus ").replace("%", " pct ")
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s)
    return s.strip("_") or "col"


def _value(cell):
    """data-sort when it is numeric, else the visible text."""
    raw = cell["sort"] if cell["sort"] not in (None, "") else cell["text"]
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return cell["text"] or None
    return int(f) if f.is_integer() and abs(f) < 1e15 else f


def parse_trends(html_text, prefix):
    """[{team, team_slug, <prefix>_<col>...}] for one saved trends page."""
    p = _TrendsTableParser()
    p.feed(html_text)
    if not p.headers or not p.rows:
        raise ValueError("no tr-table found -- is this a TeamRankings trends page?")

    names = [f"{prefix}_{_slug(h)}" for h in p.headers]
    out = []
    for cells in p.rows:
        if not cells or not cells[0]["text"]:
            continue                    # spacer rows; the page emits a few
        row = {"team": cells[0]["text"]}
        href = cells[0]["href"] or ""
        row["team_slug"] = href.rstrip("/").rsplit("/", 1)[-1] if href else None
        for i, cell in enumerate(cells[1:], start=1):
            if i >= len(names):
                break
            key = names[i]
            m = _RECORD_RE.match(cell["text"])
            if m:
                # Keep the record as it reads ("2-0-0"). data-sort on these
                # cells is only the win count, which is already covered by _W.
                row[key] = cell["text"]
                row[key + "_W"] = int(m.group(1))
                row[key + "_L"] = int(m.group(2))
                row[key + "_T"] = int(m.group(3) or 0)
            else:
                row[key] = _value(cell)
        out.append(row)
    return out


def load_trends(path, prefix):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_trends(fh.read(), prefix)


PAGES = (("win_trends.html", "TR_win"),
         ("ats_trends.html", "TR_ats"),
         ("ou_trends.html", "TR_ou"))


def load_trends_dir(directory, log=print):
    """Merge whatever of the three pages is present, keyed by TeamRankings name.

    A missing page is reported, not fatal -- a week where only two of the three
    were saved still produces the columns for those two.
    """
    merged = {}
    for filename, prefix in PAGES:
        path = os.path.join(directory, filename)
        if not os.path.exists(path):
            log(f"[miss] {'trends ' + filename:<22} not in {directory}")
            continue
        rows = load_trends(path, prefix)
        for r in rows:
            merged.setdefault(r["team"], {}).update(r)
        log(f"[read] {'trends ' + filename:<22} {len(rows)} teams")
    return merged
