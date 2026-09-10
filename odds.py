"""
odds.py — pull spreads/totals + player props from The Odds API.

Same credit math as before: props cost markets x regions PER GAME. The slate
of events is fetched once, then props are pulled per event.
"""
import json
import urllib.request, urllib.parse
import config as C


def _get(path, params):
    params = {**params, "apiKey": C.ODDS_API_KEY}
    url = f"https://api.the-odds-api.com/v4{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            remaining = resp.headers.get("x-requests-remaining")
            if remaining is not None:
                print(f"  [Odds API] credits remaining: {remaining}")
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [Odds API error] {path}: {e}")
        return None


def pull_sports(all_sports=True):
    """List every sport key The Odds API currently offers. Futures-only
    "sports" (season win totals, championship/conference outrights) each
    live under their OWN sport key, separate from americanfootball_ncaaf,
    and won't show up unless all_sports=True -- pull_futures.py --discover
    uses this to find them rather than guessing key names."""
    data = _get("/sports", dict(all="true" if all_sports else "false"))
    return data or []


def pull_outrights(sport_key):
    """Futures/outright odds for a sport key whose market is 'outrights'
    (season-long winner-style bets: national champion, conference winner,
    possibly team win totals if offered this way). Different response
    shape from pull_game_lines: one row per team/competitor with a
    consensus price across books, not one row per game."""
    data = _get(f"/sports/{sport_key}/odds",
               dict(regions=C.ODDS_REGION, markets="outrights", oddsFormat=C.ODDS_FORMAT))
    if not data:
        return []
    import statistics as st
    from collections import defaultdict
    by_team = defaultdict(list)
    for ev in data:
        for bk in ev.get("bookmakers", []):
            for m in bk.get("markets", []):
                if m["key"] != "outrights":
                    continue
                for oc in m.get("outcomes", []):
                    if oc.get("name") and oc.get("price") is not None:
                        by_team[oc["name"]].append(oc["price"])
    rows = []
    for team, prices in by_team.items():
        rows.append(dict(team=team, consensus_price=st.median(prices), n_books=len(prices)))
    rows.sort(key=lambda r: r["consensus_price"])
    return rows


def pull_events():
    data = _get(f"/sports/{C.ODDS_SPORT}/events", {})
    if not data:
        return []
    return [dict(game_id=e["id"], commence_time=e["commence_time"],
                 home=e["home_team"], away=e["away_team"]) for e in data]


def pull_game_lines():
    """
    Live spreads + totals for the WHOLE upcoming slate in one call (the
    general /sports/{sport}/odds endpoint returns every event's odds at
    once) -- unlike pull_props, this is NOT per-event, so it's cheap
    regardless of how many games are on the slate.
    Returns one row per event with a spreads market present, in the same
    shape historical_pull.R's --game-lines writes to hist_lines_closing_
    wkN.csv (see data_load.load_game_lines): home_team, away_team,
    home_spread (home team's own signed spread), total.
    """
    data = _get(f"/sports/{C.ODDS_SPORT}/odds",
               dict(regions=C.ODDS_REGION, markets="spreads,totals", oddsFormat=C.ODDS_FORMAT))
    if not data:
        return []
    import statistics as st
    rows = []
    for ev in data:
        home, away = ev["home_team"], ev["away_team"]
        home_spreads, totals = [], []
        for bk in ev.get("bookmakers", []):
            for m in bk.get("markets", []):
                if m["key"] == "spreads":
                    for oc in m.get("outcomes", []):
                        if oc.get("name") == home and oc.get("point") is not None:
                            home_spreads.append(oc["point"])
                elif m["key"] == "totals":
                    for oc in m.get("outcomes", []):
                        if oc.get("name") == "Over" and oc.get("point") is not None:
                            totals.append(oc["point"])
        if not home_spreads or not totals:
            continue
        rows.append(dict(
            game_id=ev["id"], home_team=home, away_team=away,
            home_spread=st.median(home_spreads), total=st.median(totals),
        ))
    return rows


def pull_props(events, markets, cap=None):
    """One call per event. Returns flat list of prop quotes."""
    rows = []
    n = len(events) if cap is None else min(cap, len(events))
    mkt = ",".join(markets)
    for ev in events[:n]:
        data = _get(f"/sports/{C.ODDS_SPORT}/events/{ev['game_id']}/odds",
                    dict(regions=C.ODDS_REGION, markets=mkt, oddsFormat=C.ODDS_FORMAT))
        if not data or "bookmakers" not in data:
            continue
        for bk in data["bookmakers"]:
            for m in bk.get("markets", []):
                for oc in m.get("outcomes", []):
                    rows.append(dict(
                        game_id=ev["game_id"], home=ev["home"], away=ev["away"],
                        book=bk["key"], market=m["key"],
                        player=oc.get("description"), side=oc.get("name"),
                        line=oc.get("point"), price=oc.get("price"),
                    ))
    return rows


def consensus_props(prop_rows):
    """Median line + prices per (game, market, player)."""
    from collections import defaultdict
    import statistics as st
    grp = defaultdict(list)
    for r in prop_rows:
        if r["player"]:
            grp[(r["game_id"], r["home"], r["away"], r["market"], r["player"])].append(r)
    out = []
    for (gid, home, away, market, player), rs in grp.items():
        lines = [r["line"] for r in rs if r["line"] is not None]
        overs = [r["price"] for r in rs if r["side"] == "Over" and r["price"] is not None]
        unders = [r["price"] for r in rs if r["side"] == "Under" and r["price"] is not None]
        out.append(dict(
            game_id=gid, home=home, away=away, market=market, player=player,
            book_line=(st.median(lines) if lines else None),
            over_price=(st.median(overs) if overs else None),
            under_price=(st.median(unders) if unders else None),
            n_books=len({r["book"] for r in rs}),
        ))
    return out
