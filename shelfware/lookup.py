"""The ticker question: does this asset have a wrapper that trades, and whose?

Two legs, labelled separately on every surface:

    roster  /v5/real-world-assets/quotes/latest?symbol=   keyed (1 credit) — or, with no key,
            the committed snapshot with its date. The RWA family is keyed by CMC (403 error 1005
            keyless, verified 2026-09-18), so this is the only leg that can be a snapshot.
    status  /public-api/v1/cryptocurrency/map?symbol=     keyless, LIVE for anyone, 0 credits.
            Falls back to the committed status only when the anonymous pool is exhausted, and
            says so.
"""

from shelfware.client import utc_now
from shelfware.join import UNTRACKED_DEFINITION, enrich_info, resolve, wrappers_from


def roster_snapshot_from(doc, rwa_rows=None):
    """data/roster_snapshot.json — the roster leg's no-key fallback, cut from a live census.
    `underlyings` carries every has_tokens asset with its tokens[]; `no_tokens` carries the
    symbols the RWA map lists with has_tokens: false, so a miss can be told from a no."""
    under = {}
    for w in doc["wrappers"]:
        sym = (w.get("underlying") or "").upper()
        e = under.setdefault(
            sym,
            {
                "rwa_id": w["rwa_id"],
                "symbol": w.get("underlying"),
                "name": w.get("underlying_name"),
                "asset_type": w.get("asset_type"),
                "rwa_rank": w.get("rwa_rank"),
                "has_tokens": True,
                "tokens": [],
            },
        )
        e["tokens"].append(
            {
                k: w.get(k)
                for k in (
                    "crypto_id",
                    "symbol",
                    "name",
                    "issuer_id",
                    "issuer_name",
                    "price",
                    "market_cap",
                    "volume_24h",
                    "status",
                    "first_historical_data",
                    "date_added",
                    "platform",
                )
            }
        )
    no_tokens = {}
    for r in rwa_rows or []:
        if not r.get("has_tokens") and r.get("symbol"):
            no_tokens[r["symbol"].upper()] = [
                r.get("rwa_id"),
                r.get("name"),
                r.get("asset_type"),
                r.get("rwa_rank"),
            ]
    return {
        "_note": "The no-key fallback for the ROSTER leg only. The status leg is always live.",
        "as_of": doc["generated_utc"],
        "source": "/v5/real-world-assets/quotes/latest via data/census.json (a live keyed run)",
        "underlyings": under,
        "no_tokens": no_tokens,
    }


def _status_fallback(wrappers, snapshot):
    """When the keyless pool is exhausted: the committed status per crypto_id, labelled."""
    known = {}
    for e in (snapshot or {}).get("underlyings", {}).values():
        for t in e["tokens"]:
            known[t["crypto_id"]] = t
    for w in wrappers:
        t = known.get(w["crypto_id"]) or {}
        w["status"] = t.get("status") or "unresolved"
        w["first_historical_data"] = t.get("first_historical_data")
        w["last_historical_data"] = None
        w["platform"] = t.get("platform")


def lookup(ticker, client, snapshot):
    """Returns the verdict document. Never raises for an API condition: every leg records its
    source and, when it fell back, why."""
    sym = ticker.strip().upper()
    out = {
        "ticker": sym,
        "asked_utc": utc_now(),
        "roster": {"source": None, "as_of": None, "call": None, "fallback_reason": None},
        "status": {"source": None, "call": None, "dropped_symbols": [], "fallback_reason": None},
        "underlyings": [],
        "wrappers": [],
        "verdict": None,
        "untracked_definition": UNTRACKED_DEFINITION,
        "temporary_failure": False,
        "evidence": {"tokens": [], "map_rows": []},
    }
    assets = None
    # ── roster leg ─────────────────────────────────────────────────────────────
    if client.api_key:
        assets, meta = client.rwa_quotes(symbol=sym)
        out["roster"]["call"] = meta
        if meta["error"] and meta["http"] == 400:
            out["roster"]["source"] = "live"
            assets = []  # CMC's RWA universe has no such symbol
        elif meta["error"]:
            out["roster"]["fallback_reason"] = meta["error"]
            assets = None
        else:
            out["roster"]["source"] = "live"
    if assets is None:
        snap = snapshot or {}
        out["roster"]["source"] = "snapshot"
        out["roster"]["as_of"] = snap.get("as_of")
        e = (snap.get("underlyings") or {}).get(sym)
        if e:
            assets = [dict(e)]
        elif sym in (snap.get("no_tokens") or {}):
            rid, name, atype, rank = snap["no_tokens"][sym]
            assets = [
                {
                    "rwa_id": rid,
                    "symbol": sym,
                    "name": name,
                    "asset_type": atype,
                    "rwa_rank": rank,
                    "has_tokens": False,
                    "tokens": [],
                }
            ]
        else:
            assets = []
    out["underlyings"] = [
        {k: a.get(k) for k in ("rwa_id", "symbol", "name", "asset_type", "rwa_rank", "has_tokens")}
        | {"tokens_listed": len(a.get("tokens") or [])}
        for a in assets
    ]
    out["evidence"]["tokens"] = [t for a in assets for t in (a.get("tokens") or [])]
    wrappers = wrappers_from(
        [{"rwa_id": a.get("rwa_id"), "symbol": a.get("symbol")} for a in assets], assets
    )
    # ── status leg — keyless, live ─────────────────────────────────────────────
    symbols = [w["symbol"] for w in wrappers if w.get("symbol")]
    snap_state = {}
    for e in ((snapshot or {}).get("underlyings") or {}).values():
        for t in e["tokens"]:
            snap_state[t["crypto_id"]] = t
    out["status"]["base"] = "keyless"
    if wrappers:
        rows, meta, dropped = client.cmc_map(symbols) if symbols else ({}, None, [])
        if meta is not None and meta.get("throttled") and client.api_key:
            # the escape hatch: the anonymous pool refused this IP; the identical call, keyed
            out["status"]["keyless_error"] = meta["error"]
            out["status"]["base"] = "keyed"
            rows, meta, dropped = client.cmc_map(symbols, keyed=True)
        out["status"]["call"] = meta
        out["status"]["dropped_symbols"] = dropped
        if meta is not None and meta.get("error"):
            out["status"]["source"] = "snapshot"
            out["status"]["fallback_reason"] = meta["error"]
            out["temporary_failure"] = bool(meta.get("throttled"))
            _status_fallback(wrappers, snapshot)
            for w in wrappers:
                w["status_source"] = "snapshot"
        else:
            out["status"]["source"] = (
                "live keyless"
                if out["status"]["base"] == "keyless"
                else "live keyed (escape hatch)"
            )
            resolve(wrappers, rows)
            wanted = {w["crypto_id"] for w in wrappers}
            out["evidence"]["map_rows"] = [r for r in rows.values() if r.get("id") in wanted]
            for w in wrappers:
                w["status_source"] = "map" if w["crypto_id"] in rows else None
        # the listing date, and the state of any wrapper whose symbol the map will not filter
        info, metas, _ = client.cmc_info(
            [w["crypto_id"] for w in wrappers], keyed=out["status"]["base"] == "keyed"
        )
        if (
            metas
            and metas[-1].get("throttled")
            and client.api_key
            and out["status"]["base"] == "keyless"
        ):
            out["status"]["keyless_error"] = metas[-1]["error"]
            info, metas, _ = client.cmc_info([w["crypto_id"] for w in wrappers], keyed=True)
        out["status"]["info_calls"] = metas
        enrich_info(wrappers, info)
        out["evidence"]["info_rows"] = [
            {
                k: v
                for k, v in r.items()
                if k in ("id", "symbol", "status", "date_added", "platform")
            }
            for r in info.values()
        ]
        for w in wrappers:
            if w.get("status_source") in ("map", "snapshot"):
                continue
            coarse = w.get("info_status")
            ip = (info.get(w["crypto_id"]) or {}).get("platform") or {}
            if not w.get("platform") and ip:
                w["platform"] = {"name": ip.get("name"), "token_address": ip.get("token_address")}
            if coarse == "active":
                w["status"], w["status_source"] = "active", "info"
            elif coarse == "inactive":
                fine = (snap_state.get(w["crypto_id"]) or {}).get("status")
                w["status"] = fine if fine in ("untracked", "inactive") else "inactive"
                w["status_source"] = (
                    "info+snapshot" if fine in ("untracked", "inactive") else "info"
                )
                w["platform"] = w.get("platform") or (snap_state.get(w["crypto_id"]) or {}).get(
                    "platform"
                )
            else:
                w["status"], w["status_source"] = "unresolved", "info"
    out["wrappers"] = wrappers
    n = len(wrappers)
    tracked = sum(1 for w in wrappers if w.get("status") == "active")
    if not assets:
        out["verdict"] = f"CoinMarketCap's RWA map has no underlying {sym}"
    elif n == 0:
        out["verdict"] = f"{sym} is in the RWA map with has_tokens: false — 0 wrappers listed"
    else:
        out["verdict"] = f"{tracked} of {n} wrapper(s) with a CMC-tracked market"
    out["tracked"], out["attached"] = tracked, n
    return out
