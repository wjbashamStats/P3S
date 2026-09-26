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

A page can also arrive as a tab-delimited paste of just the table (copy the
rows out of the browser, save as ats_trends.txt beside the .html). Those rows
carry the rounded display values and no team slug, but they parse into the
same columns, so a week where only the text came across still refreshes. The
.html is preferred when both are present.
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


def _split_row(line):
    """Tabs when the paste has them, otherwise runs of two or more spaces --
    team names carry single spaces, so one space is never a separator."""
    if "\t" in line:
        return [c.strip() for c in line.split("\t")]
    return [c.strip() for c in re.split(r"\s{2,}", line.strip())]


def _text_value(raw):
    """Display text -> number, matching what data-sort gives on the page.

    Percentages are the one that matters: the page's data-sort holds a
    fraction (1.0 for a 100% cover rate) while the cell reads "100.0%", so a
    paste that kept the percent sign has to be divided down or every rank and
    label built off it comes out 100x high. Signed values ("+12.0") and
    thousands separators go through float() once stripped.
    """
    raw = (raw or "").strip()
    if not raw or raw in ("--", "-", "N/A"):
        return None
    pct = raw.endswith("%")
    txt = raw[:-1].strip() if pct else raw
    txt = txt.replace(",", "").lstrip("+")
    try:
        f = float(txt)
    except ValueError:
        return raw
    if pct:
        f /= 100.0
    return int(f) if f.is_integer() and abs(f) < 1e15 else f


def parse_trends_text(text, prefix, log=None):
    """[{team, team_slug, <prefix>_<col>...}] for a tab-delimited paste.

    Same output shape as parse_trends so callers cannot tell the two apart,
    except team_slug is None -- a paste has no links in it.

    A hand-made paste arrives messier than a saved page, and one already has:
    the table came through twice with the header repeated in the middle, the
    first copy cut off partway through a row ("Oregon\t3-0-"), and the tail of
    that severed row turned up later as a line of its own. So three things are
    tolerated, because none of them can be a real row:

      * a repeat of the header line, which would otherwise parse as a team
        called "Team";
      * a line whose first cell is a number or a W-L-T record, which is the
        tail of a row whose team name got cut off the front;
      * a team appearing twice, where the row with more cells parsed wins, so
        a truncated copy never displaces the complete one.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("empty trends paste")
    headers = _split_row(lines[0])
    if len(headers) < 2 or _RECORD_RE.match(headers[1] or ""):
        raise ValueError("first line is not a header row -- paste the column "
                         "headers along with the rows")
    names = [f"{prefix}_{_slug(h)}" for h in headers]
    head_key = headers[0].strip().lower()
    out, widths, dropped = {}, {}, 0
    for ln in lines[1:]:
        cells = _split_row(ln)
        team = cells[0] if cells else ""
        if not team or team.strip().lower() == head_key:
            continue
        if _RECORD_RE.match(team) or _text_value(team) != team:
            dropped += 1          # headless tail of a severed row
            continue
        if team in out and len(cells) <= widths[team]:
            dropped += 1          # a shorter duplicate; keep the one we have
            continue
        row = {"team": team, "team_slug": None}
        for i, raw in enumerate(cells[1:], start=1):
            if i >= len(names):
                break
            key = names[i]
            m = _RECORD_RE.match(raw)
            if m:
                row[key] = f"{int(m.group(1))}-{int(m.group(2))}-{int(m.group(3) or 0)}"
                row[key + "_W"] = int(m.group(1))
                row[key + "_L"] = int(m.group(2))
                row[key + "_T"] = int(m.group(3) or 0)
            else:
                row[key] = _text_value(raw)
        dropped += team in out
        out[team], widths[team] = row, len(cells)
    if not out:
        raise ValueError("no data rows in trends paste")
    if dropped and log:
        log(f"[note] trends paste: {len(out)} teams, {dropped} duplicate or "
            f"partial lines ignored")
    return list(out.values())


def load_trends(path, prefix, log=None):
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    if os.path.splitext(path)[1].lower() in (".txt", ".tsv"):
        return parse_trends_text(text, prefix, log=log)
    return parse_trends(text, prefix)


# Per page, the filenames tried in order: a saved page first, then a paste of
# the table on its own.
PAGES = (("win_trends", "TR_win"),
         ("ats_trends", "TR_ats"),
         ("ou_trends", "TR_ou"))
EXTS = (".html", ".txt", ".tsv")


def load_trends_dir(directory, log=print):
    """Merge whatever of the three pages is present, keyed by TeamRankings name.

    A missing page is reported, not fatal -- a week where only two of the three
    were saved still produces the columns for those two.
    """
    merged = {}
    for stem, prefix in PAGES:
        path = next((p for p in (os.path.join(directory, stem + e) for e in EXTS)
                     if os.path.exists(p)), None)
        if path is None:
            log(f"[miss] {'trends ' + stem:<22} not in {directory}")
            continue
        rows = load_trends(path, prefix, log=log)
        for r in rows:
            cols = merged.setdefault(r["team"], {})
            # A paste carries team_slug=None; don't let it wipe a slug an
            # earlier saved page already supplied for the same team.
            cols.update({k: v for k, v in r.items()
                         if v is not None or cols.get(k) is None})
        log(f"[read] {'trends ' + os.path.basename(path):<22} {len(rows)} teams")
    return merged
