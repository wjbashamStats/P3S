# Weekly articles

Three `.docx` write-ups per week — spreads, totals, player props — built from
the same data the betting hub renders.

The spread and total documents embed screenshots taken from the built
Line Diversions page itself (Five Factors radars + power ratings, and the
unit-matchup tables), so the figures in the prose and the figures in the
images cannot drift apart.

Rebuild:

```bash
python3 pages/build_pages.py --season 2026 --week <N>    # diversions_page.html
# then, in the scratchpad harness:
node shoot.cjs          # screenshots each game's modal from the built page
node build_docs.cjs     # writes articles/*.docx from content.json + shots
```

`shoot.cjs` drives the page's own search box to isolate one game at a time and
clips two ranges out of the detail modal (Five Factors -> Power Ratings, and
Unit Matchups -> Starter Matchups) at 2x device scale.

Note: LibreOffice in this sandbox cannot convert any file to PDF (it fails on
a plain .txt), so these are verified with the docx XSD validator and by
reading the unpacked document.xml rather than by rendering.
