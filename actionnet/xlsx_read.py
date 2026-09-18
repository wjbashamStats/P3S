#!/usr/bin/env python3
"""
xlsx_read.py -- minimal read-only .xlsx reader, standard library only.

The rest of this repo is stdlib-only and this runs on a schedule with nobody
watching, so it deliberately avoids openpyxl/pandas: a weekly job that has to
pip install before it can read its input is a job that fails silently the
first week the network policy changes. An .xlsx is a zip of XML, and all we
need is "give me the cell values of a sheet as rows", which is ~100 lines.

Formula cells are read as their CACHED value (what openpyxl calls
data_only=True) -- the workbook is an export, so every formula already has a
stored result. Error cells (#N/A, #REF!) come back as their literal string so
callers can tell "the source is broken" apart from "the cell is empty"; see
to_num() for turning those into None.

Validated against openpyxl on every sheet this pipeline reads: identical
values, cell for cell (actionnet/test_xlsx_read.py).
"""
import re
import xml.etree.ElementTree as ET
import zipfile

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_CELL_RE = re.compile(r"^([A-Z]+)(\d+)$")


def _col_index(ref):
    """'A'->0, 'Z'->25, 'AA'->26. Takes a cell ref like 'BD12' or just 'BD'."""
    m = _CELL_RE.match(ref)
    letters = m.group(1) if m else ref
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


class Workbook:
    def __init__(self, path):
        self.zf = zipfile.ZipFile(path)
        self._shared = self._read_shared_strings()
        self.sheets = self._read_sheet_index()   # {name: zip path}

    # -- setup -------------------------------------------------------------
    def _read_shared_strings(self):
        if "xl/sharedStrings.xml" not in self.zf.namelist():
            return []
        root = ET.fromstring(self.zf.read("xl/sharedStrings.xml"))
        out = []
        for si in root.findall("m:si", NS):
            # a string can be split across several runs (<r><t>..</t></r>)
            out.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        return out

    def _read_sheet_index(self):
        rels = {}
        root = ET.fromstring(self.zf.read("xl/_rels/workbook.xml.rels"))
        for rel in root.findall("pr:Relationship", NS):
            rels[rel.get("Id")] = rel.get("Target")
        out = {}
        root = ET.fromstring(self.zf.read("xl/workbook.xml"))
        for sh in root.find("m:sheets", NS).findall("m:sheet", NS):
            target = rels[sh.get(f"{{{NS['r']}}}id")]
            if target.startswith("/"):
                target = target[1:]
            elif not target.startswith("xl/"):
                target = "xl/" + target
            out[sh.get("name")] = target
        return out

    # -- reading -----------------------------------------------------------
    def _cell_value(self, c):
        t = c.get("t")
        if t == "inlineStr":
            is_el = c.find("m:is", NS)
            return "".join(x.text or "" for x in is_el.iter(f"{{{NS['m']}}}t")) if is_el is not None else None
        v = c.find("m:v", NS)
        if v is None or v.text is None:
            return None
        raw = v.text
        if t == "s":
            return self._shared[int(raw)]
        if t in ("str", "e"):
            # "str" = cached string result of a formula; "e" = error literal
            return raw
        if t == "b":
            return raw == "1"
        try:
            f = float(raw)
        except ValueError:
            return raw
        return int(f) if f.is_integer() and abs(f) < 1e15 else f

    def rows(self, sheet, max_col=None):
        """Yield each row as a list of values, left-padded for sparse cells."""
        path = self.sheets[sheet]
        with self.zf.open(path) as fh:
            row = None
            row_no = 0
            for event, el in ET.iterparse(fh, events=("start", "end")):
                tag = el.tag.split("}", 1)[-1]
                if event == "start" and tag == "row":
                    row = []
                    row_no = int(el.get("r") or row_no + 1)
                elif event == "end" and tag == "c" and row is not None:
                    idx = _col_index(el.get("r") or "")
                    if max_col is not None and idx >= max_col:
                        el.clear()
                        continue
                    while len(row) < idx:
                        row.append(None)
                    row.append(self._cell_value(el))
                    el.clear()
                elif event == "end" and tag == "row":
                    if max_col is not None:
                        while len(row) < max_col:
                            row.append(None)
                    yield row_no, row
                    row = None
                    el.clear()

    def grid(self, sheet, first_row=1, last_row=None, first_col=1, last_col=None):
        """Rows first_row..last_row as lists spanning first_col..last_col (1-based,
        inclusive) -- the same idea as readxl's cell_limits()."""
        width = (last_col - first_col + 1) if last_col else None
        out = []
        for row_no, row in self.rows(sheet, max_col=last_col):
            if row_no < first_row:
                continue
            if last_row is not None and row_no > last_row:
                break
            cells = row[first_col - 1:last_col] if last_col else row[first_col - 1:]
            if width:
                cells += [None] * (width - len(cells))
            out.append(cells)
        return out


def to_num(x):
    """Numeric value, or None for blanks, text and Excel errors (#N/A, #REF!)."""
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def to_str(x):
    return None if x is None else str(x).strip() or None
