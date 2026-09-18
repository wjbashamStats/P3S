# TeamRankings trends pages

Save these three pages here each week, alongside the workbook. Right-click →
Save Page As (HTML only is fine — the parser only reads the results table):

| file | page |
|---|---|
| `win_trends.html` | https://www.teamrankings.com/ncf/trends/win_trends/ |
| `ats_trends.html` | https://www.teamrankings.com/ncf/trends/ats_trends/ |
| `ou_trends.html`  | https://www.teamrankings.com/ncf/trends/ou_trends/ |

Set the Range filter to the current season before saving. `an_metrics.py`
finds this directory on its own; a page that isn't here is reported as
`[miss]` and its columns are simply absent, so saving two of three still
works. With none of them present, records fall back to the PFF tab.

Columns are read from each page's own `<thead>`, so the ATS and O/U pages need
no configuration, and a column TeamRankings adds later appears on its own.
Values come from each cell's `data-sort` attribute rather than its visible
text, because the page rounds for display (ATS +/- renders `+10.3` where
`data-sort` holds `10.25`).
