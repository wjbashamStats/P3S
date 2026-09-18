#!/usr/bin/env python3
"""Check the stdlib reader against openpyxl on every sheet the pipeline uses.

openpyxl is NOT a runtime dependency -- it is only used here, to prove the
hand-rolled reader agrees with a reference implementation. Skips itself if
openpyxl isn't installed.

Run:  python3 actionnet/test_xlsx_read.py <workbook.xlsx>
"""
import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xlsx_read

SHEETS = ["2026 PR", "TARP 26", "TOTALS", "2026 Win Total", "TeamID",
          "CFBData26", "Twitter", "PFF", "2026 Futures"]

# (sheet, 1-based column) pairs the pipeline actually reads. A date-formatted
# cell in one of these would be a real failure, not an accepted difference.
USED = {("2026 PR", c) for c in (1, 4, 5, 6, 9, 10, 11, 12, 13)} | \
       {("TARP 26", c) for c in (1, 2, 3, 4, 5, 7, 8)} | \
       {("TOTALS", c) for c in (1, 4, 5, 16)} | \
       {("2026 Win Total", c) for c in (2, 10, 11, 12, 13)} | \
       {("TeamID", c) for c in range(1, 10)} | \
       {("CFBData26", c) for c in range(1, 184)} | \
       {("Twitter", c) for c in (1, 4)} | \
       {("PFF", c) for c in (1, 6)}


def main(path):
    try:
        import openpyxl
    except ImportError:
        print("openpyxl not installed -- skipping (it is not a runtime dependency)")
        return 0
    ref = openpyxl.load_workbook(path, data_only=True)
    mine = xlsx_read.Workbook(path)

    if set(ref.sheetnames) != set(mine.sheets):
        print("FAIL: sheet name sets differ")
        return 1
    print(f"sheet names match ({len(ref.sheetnames)})")

    bad = 0
    for name in SHEETS:
        ws = ref[name]
        ref_rows = {i: list(r) for i, r in enumerate(ws.iter_rows(values_only=True), 1)}
        cells = diffs = dated = 0
        for row_no, row in mine.rows(name):
            exp = ref_rows.get(row_no, [])
            n = max(len(row), len(exp))
            for j in range(n):
                a = row[j] if j < len(row) else None
                b = exp[j] if j < len(exp) else None
                # openpyxl surfaces error cells as the literal string too, but
                # renders cached numerics as float where we may hold int
                cells += 1
                # Known, accepted difference: openpyxl applies the cell's
                # number format and turns date/duration-formatted serials into
                # datetime/timedelta. This reader returns the raw serial. It
                # only shows up in TOTALS' "Total Time"/"Time/G" columns, which
                # this pipeline does not read -- counted separately, not a
                # failure, and asserted below to never touch a used column.
                if isinstance(b, (datetime.datetime, datetime.date, datetime.timedelta)):
                    dated += 1
                    if (name, j + 1) in USED:
                        print(f"  FAIL {name} col {j+1} is date-formatted AND used by the pipeline")
                        diffs += 1
                    continue
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    same = abs(float(a) - float(b)) < 1e-9
                else:
                    same = (a == b) or (a is None and b is None)
                if not same:
                    diffs += 1
                    if diffs <= 3:
                        print(f"  {name} r{row_no}c{j+1}: mine={a!r} openpyxl={b!r}")
        status = "OK " if diffs == 0 else "DIFF"
        note = f", {dated} date-formatted (unused, see note)" if dated else ""
        print(f"  [{status}] {name:16s} {cells:>7,} cells, {diffs} differences{note}")
        bad += diffs
    print("\nPASS -- reader matches openpyxl" if bad == 0 else f"\nFAIL -- {bad} differing cells")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
