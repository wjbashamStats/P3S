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


def pull_events():
    data = _get(f"/sports/{C.ODDS_SPORT}/events", {})
    if not data:
        return []
    return [dict(game_id=e["id"], commence_time=e["commence_time"],
                 home=e["home_team"], away=e["away_team"]) for e in data]


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
