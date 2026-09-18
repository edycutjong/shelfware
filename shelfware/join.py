"""The join and the three counting rules. Pure functions over the four ledgers; no network.

    shelf(wrapper)            = status == "untracked"          CMC's own listing state, not price
    zero_tracked(underlying)  = every attached wrapper is untracked   (unresolved never counts)
    shelf_rate(issuer)        = untracked / attached            beside Σ market_cap of the tracked

`untracked` is CoinMarketCap's word. Their map documentation defines it as:
    "registered cryptocurrency projects that are listed but do not yet meet methodology
     requirements to have tracked markets"
On every surface it reads "listed, no CMC-tracked market" — never "never traded".
"""

import statistics
from datetime import UTC, datetime

from shelfware.client import KEYED_BASE, KEYLESS_BASE, credits_used

STATUSES = ("active", "untracked", "inactive", "unresolved")
UNTRACKED_DEFINITION = (
    "registered cryptocurrency projects that are listed but do not yet meet methodology "
    "requirements to have tracked markets"
)
HERO_RULE = (
    "the most prominent tokenised underlying on CoinMarketCap (lowest rwa_rank) whose every "
    "wrapper is untracked"
)
NO_ISSUER = "(no issuer)"


def wrappers_from(rwa_rows, quote_assets):
    """Flatten tokens[] into one row per wrapper, carrying its underlying's identity."""
    by_rwa = {r["rwa_id"]: r for r in rwa_rows}
    out = []
    for asset in quote_assets:
        u = by_rwa.get(asset.get("rwa_id"), {})
        for t in asset.get("tokens") or []:
            out.append(
                {
                    "crypto_id": t.get("crypto_id"),
                    "symbol": t.get("symbol"),
                    "name": t.get("name"),
                    "rwa_id": asset.get("rwa_id"),
                    "underlying": asset.get("symbol") or u.get("symbol"),
                    "underlying_name": asset.get("name") or u.get("name"),
                    "asset_type": asset.get("asset_type") or u.get("asset_type"),
                    "rwa_rank": asset.get("rwa_rank", u.get("rwa_rank")),
                    "issuer_id": t.get("issuer_id"),
                    "issuer_name": t.get("issuer_name"),
                    "price": t.get("price"),
                    "market_cap": t.get("market_cap"),
                    "volume_24h": t.get("volume_24h"),
                }
            )
    return out


def resolve(wrappers, cmc_map):
    """Attach CMC's listing state to each wrapper. An id absent from the map is `unresolved`:
    shown in its own bucket, never counted as shelf."""
    for w in wrappers:
        m = cmc_map.get(w["crypto_id"]) or {}
        w["status"] = m.get("status") if m.get("status") in STATUSES[:3] else "unresolved"
        w["first_historical_data"] = m.get("first_historical_data")
        w["last_historical_data"] = m.get("last_historical_data")
        p = m.get("platform") or {}
        w["platform"] = (
            {"name": p.get("name"), "token_address": p.get("token_address")} if p else None
        )
    return wrappers


def enrich_info(wrappers, info):
    """Attach the listing date and the info surface's coarse state to each wrapper."""
    for w in wrappers:
        r = info.get(w["crypto_id"]) or {}
        w["date_added"] = r.get("date_added")
        w["info_status"] = r.get("status")
    return wrappers


def is_shelf(w):
    return w.get("status") == "untracked"


def by_underlying(wrappers):
    groups = {}
    for w in wrappers:
        groups.setdefault(w["rwa_id"], []).append(w)
    return groups


def zero_tracked(wrappers, has_tokens_rows, strict=True):
    """rwa_ids of underlyings with no wrapper that has a CMC-tracked market.

    strict (the headline): the underlying has >= 1 attached wrapper and EVERY one is untracked.
    loose: no wrapper is active — also counts unresolved-only and inactive-only underlyings.
    Strict is always <= loose; the headline never takes the larger number."""
    groups = by_underlying(wrappers)
    out = []
    for r in has_tokens_rows:
        ws = groups.get(r["rwa_id"], [])
        if strict:
            if ws and all(is_shelf(w) for w in ws):
                out.append(r["rwa_id"])
        elif not any(w.get("status") == "active" for w in ws):
            out.append(r["rwa_id"])
    return out


def scorecard(wrappers, issuers):
    """Per issuer: declared (registry num_tokens) · attached · tracked · untracked · inactive ·
    unresolved · shelf_rate · live market cap of the tracked wrappers."""
    declared = {i.get("issuer_id"): i.get("num_tokens") for i in issuers}
    names = {i.get("issuer_id"): i.get("name") for i in issuers}
    rows = {}
    for w in wrappers:
        k = w.get("issuer_id") or NO_ISSUER
        e = rows.setdefault(
            k,
            {
                "issuer_id": w.get("issuer_id"),
                "issuer_name": (w.get("issuer_name") or names.get(k) or NO_ISSUER)
                if w.get("issuer_id")
                else NO_ISSUER,
                "declared": declared.get(k),
                "attached": 0,
                "tracked": 0,
                "untracked": 0,
                "inactive": 0,
                "unresolved": 0,
                "live_market_cap_usd": 0.0,
            },
        )
        e["attached"] += 1
        s = w.get("status")
        if s == "active":
            e["tracked"] += 1
            e["live_market_cap_usd"] += float(w.get("market_cap") or 0)
        elif s in ("untracked", "inactive"):
            e[s] += 1
        else:
            e["unresolved"] += 1
    for e in rows.values():
        e["shelf_rate"] = round(e["untracked"] / e["attached"], 4) if e["attached"] else None
        e["live_market_cap_usd"] = round(e["live_market_cap_usd"], 2)
    # registry issuers that declare tokens but have none attached to any underlying
    for i in issuers:
        if i.get("issuer_id") not in rows:
            rows[i["issuer_id"]] = {
                "issuer_id": i.get("issuer_id"),
                "issuer_name": i.get("name"),
                "declared": i.get("num_tokens"),
                "attached": 0,
                "tracked": 0,
                "untracked": 0,
                "inactive": 0,
                "unresolved": 0,
                "live_market_cap_usd": 0.0,
                "shelf_rate": None,
            }
    return sorted(
        rows.values(),
        key=lambda e: (-(e["shelf_rate"] if e["shelf_rate"] is not None else -1), -e["attached"]),
    )


def type_bars(wrappers):
    rows = {}
    for w in wrappers:
        e = rows.setdefault(
            w.get("asset_type") or "unknown",
            {
                "asset_type": w.get("asset_type") or "unknown",
                "attached": 0,
                "tracked": 0,
                "untracked": 0,
                "other": 0,
            },
        )
        e["attached"] += 1
        s = w.get("status")
        if s == "active":
            e["tracked"] += 1
        elif s == "untracked":
            e["untracked"] += 1
        else:
            e["other"] += 1
    for e in rows.values():
        e["shelf_rate"] = round(e["untracked"] / e["attached"], 4) if e["attached"] else None
    return sorted(rows.values(), key=lambda e: -e["attached"])


def pct_rank(values, p):
    """Nearest-rank percentile: always a real observation, never an interpolation."""
    if not values:
        return None
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(p / 100 * len(s) + 0.5)) - 1))
    return s[idx]


def age_of_tracked(wrappers, now):
    """Days since first_historical_data, over active wrappers that carry one. Untracked rows
    carry no dates at all, which is why this panel covers only what trades."""
    ages = []
    for w in wrappers:
        if w.get("status") == "active" and w.get("first_historical_data"):
            born = datetime.fromisoformat(w["first_historical_data"].replace("Z", "+00:00"))
            ages.append((now - born).days)
    return {
        "n": len(ages),
        "median": statistics.median(ages) if ages else None,
        "p10": pct_rank(ages, 10),
        "p90": pct_rank(ages, 90),
    }


def age_of_shelf(wrappers, now):
    """Days since date_added (the day CMC listed the coin) over untracked wrappers: how long
    each has sat on the shelf. The listing date is not a market date — nothing traded."""
    ages = []
    for w in wrappers:
        if is_shelf(w) and w.get("date_added"):
            born = datetime.fromisoformat(w["date_added"].replace("Z", "+00:00"))
            ages.append((now - born).days)
    return {
        "n": len(ages),
        "median": statistics.median(ages) if ages else None,
        "p10": pct_rank(ages, 10),
        "p90": pct_rank(ages, 90),
    }


def hero(wrappers, has_tokens_rows):
    """The demo ticker, by a published rule rather than a pick: the lowest rwa_rank among
    underlyings whose every wrapper is untracked. If tomorrow's census promotes its wrapper,
    the rule selects the next one and the page says so."""
    ids = set(zero_tracked(wrappers, has_tokens_rows, strict=True))
    ranked = sorted(
        (r for r in has_tokens_rows if r["rwa_id"] in ids and r.get("rwa_rank") is not None),
        key=lambda r: r["rwa_rank"],
    )
    if not ranked:
        return None
    r = ranked[0]
    groups = by_underlying(wrappers)
    return {
        "rule": HERO_RULE,
        "rwa_id": r["rwa_id"],
        "symbol": r.get("symbol"),
        "name": r.get("name"),
        "rwa_rank": r.get("rwa_rank"),
        "wrappers": [w["crypto_id"] for w in groups.get(r["rwa_id"], [])],
        "runners_up": [
            {"symbol": x.get("symbol"), "rwa_rank": x.get("rwa_rank")} for x in ranked[1:5]
        ],
    }


def counts_of(wrappers, rwa_rows, has_tokens_rows, issuers=None, cmc_rows=None):
    buckets = {s: 0 for s in STATUSES}
    for w in wrappers:
        buckets[w.get("status") if w.get("status") in STATUSES else "unresolved"] += 1
    strict = zero_tracked(wrappers, has_tokens_rows, strict=True)
    loose = zero_tracked(wrappers, has_tokens_rows, strict=False)
    attached_ids = {w["rwa_id"] for w in wrappers}
    c = {
        "underlyings": len(rwa_rows),
        "has_tokens": len(has_tokens_rows),
        "has_tokens_without_wrappers": sum(
            1 for r in has_tokens_rows if r["rwa_id"] not in attached_ids
        ),
        "wrappers": len(wrappers),
        **buckets,
        "underlyings_zero_tracked": len(strict),
        "underlyings_zero_tracked_loose": len(loose),
        "underlyings_mixed": sum(
            1
            for ws in by_underlying(wrappers).values()
            if any(w.get("status") == "active" for w in ws) and any(is_shelf(w) for w in ws)
        ),
    }
    if issuers is not None:
        c["issuers_in_registry"] = len(issuers)
    if cmc_rows is not None:
        c["cmc_map_rows"] = cmc_rows
    return c


def census(
    rwa_rows, quote_assets, cmc_map, issuers, info=None, receipt=None, now=None, wall_clock_s=None
):
    """A + B + C + D (+ E) -> the census document data/census.json and every snapshot carry."""
    now = now or datetime.now(UTC)
    has_tokens = [r for r in rwa_rows if r.get("has_tokens")]
    wrappers = resolve(wrappers_from(rwa_rows, quote_assets), cmc_map)
    enrich_info(wrappers, info or {})
    wrappers.sort(key=lambda w: (w["rwa_id"] or 0, w["crypto_id"] or 0))
    receipt = receipt or []
    doc = {
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "wall_clock_s": wall_clock_s,
        "credits_used": credits_used(receipt),
        "keyed_calls": sum(1 for m in receipt if m.get("keyed")),
        "keyless_calls": sum(1 for m in receipt if not m.get("keyed")),
        "source": {"keyed": KEYED_BASE, "keyless": KEYLESS_BASE},
        "untracked_definition": UNTRACKED_DEFINITION,
        "counts": counts_of(wrappers, rwa_rows, has_tokens, issuers, len(cmc_map)),
        "age_tracked_days": age_of_tracked(wrappers, now),
        "age_untracked_days": age_of_shelf(wrappers, now),
        "hero": hero(wrappers, has_tokens),
        "by_issuer": scorecard(wrappers, issuers),
        "by_type": type_bars(wrappers),
        "chains_of_untracked": chains(w for w in wrappers if is_shelf(w)),
        "unresolved": [
            {k: w.get(k) for k in ("crypto_id", "symbol", "underlying", "issuer_name")}
            for w in wrappers
            if w.get("status") == "unresolved"
        ],
        "issuers_registry": issuers,
        "receipt": [{k: v for k, v in m.items() if k not in ("attempts",)} for m in receipt],
        "wrappers": wrappers,
    }
    return doc


def chains(wrappers):
    out = {}
    for w in wrappers:
        name = (w.get("platform") or {}).get("name") or "(no platform)"
        out[name] = out.get(name, 0) + 1
    return sorted(
        ({"chain": k, "wrappers": v} for k, v in out.items()), key=lambda e: -e["wrappers"]
    )


def recount(doc):
    """Re-derive every headline from wrappers[] alone — what verify.py and the tests compare
    against `counts`. Needs no ledger but the rows the document already carries."""
    ws = doc["wrappers"]
    rwa_ids = {w["rwa_id"] for w in ws}
    # the has_tokens universe is not in wrappers[]; take it from counts (or the rows).
    has_tokens_rows = [{"rwa_id": i} for i in rwa_ids]
    buckets = {s: sum(1 for w in ws if w.get("status") == s) for s in STATUSES}
    strict = len(zero_tracked(ws, has_tokens_rows, strict=True))
    issuer_rows = scorecard(ws, doc.get("issuers_registry") or [])
    return {
        "wrappers": len(ws),
        **buckets,
        "underlyings_zero_tracked": strict,
        "untracked_share": round(buckets["untracked"] / len(ws), 4) if ws else None,
        "by_issuer": {
            e["issuer_name"]: (
                e["untracked"],
                e["attached"],
                e["shelf_rate"],
                e["live_market_cap_usd"],
            )
            for e in issuer_rows
            if e["attached"]
        },
        "by_type": {e["asset_type"]: (e["untracked"], e["attached"]) for e in type_bars(ws)},
        "price_null_iff_untracked_exceptions": sum(
            1
            for w in ws
            if w.get("status") in ("active", "untracked")
            and ((w.get("price") is None) != is_shelf(w))
        ),
    }
