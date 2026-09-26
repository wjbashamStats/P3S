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

The betting hub reads this directory too. `build_diversions_page_data.py`
takes the ATS W/L% and Over W/L% rows of its power table from `ats_trends.html`
and `ou_trends.html` (ranking the percentages itself, since the pages carry no
rank column). Without those two files the hub silently falls back to
team_ratings_2025.csv's `X2022_*` columns, which really are the 2022 season --
the page relabels that row "2022 ATS W/L%" so a reader can tell, but the fix
is to save the pages. Pasting the page source into the session works as well
as Save Page As; the parser only wants the results table.

Columns are read from each page's own `<thead>`, so the ATS and O/U pages need
no configuration, and a column TeamRankings adds later appears on its own.
Values come from each cell's `data-sort` attribute rather than its visible
text, because the page rounds for display (ATS +/- renders `+10.3` where
`data-sort` holds `10.25`).

## Pasting just the table

If only the table comes across -- select the rows in the browser, copy, and
save them as `ats_trends.txt` (or `.tsv`) -- the parser reads that too. Keep
the header line; the columns are named off it. Tabs are the separator, and
runs of two or more spaces work as well, since a team name never carries more
than one. Two things are lost relative to the saved page: the values are the
rounded display numbers rather than `data-sort`'s full precision, and there
are no links, so `team_slug` is empty. The `.html` wins when both are present,
so delete the stale one or the refresh does nothing.

| saved page | paste |
|---|---|
| `ats_trends.html` | `ats_trends.txt` |
| `ou_trends.html` | `ou_trends.txt` |
| `win_trends.html` | `win_trends.txt` |
