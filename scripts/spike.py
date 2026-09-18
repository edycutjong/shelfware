#!/usr/bin/env python3
"""Day-1 spike — the one API question the whole claim rests on, answered with real calls.

The claim is "listed, no CMC-tracked market". The risk register named the way it fails:
overclaiming. So before any engine exists, this script asks CoinMarketCap the question three
ways for the demo ticker and writes every raw response to docs/proof/spike.json:

    1. keyless  /public-api/v1/cryptocurrency/map?symbol=wMSx        what is the listing state?
    2. keyed    /v5/real-world-assets/quotes/latest?symbol=MS         is the wrapper priced? does
                                                                       the asset trade ANYWHERE?
    3. keyed    /v2/cryptocurrency/quotes/latest?id=41513             does the quotes surface know
                                                                       a price CMC's RWA page hides?
    4. keyed    /v2/cryptocurrency/quotes/historical?id=41513         has it EVER had a tracked
                                                                       market?
    5. keyed    /v1/key/info before and after                          what did that cost?

If (1) says untracked, (2) says price null but names a TradFi venue, (3) and (4) return no
price, then the honest sentence is exactly the one on every surface of this project — "listed,
no CMC-tracked market" — and never "never traded". The second question the register named is
the time axis: untracked map rows carry no dates, so the spike also records whether (1) carries
any, and diffs the row against the first daily snapshot.

    python3 scripts/spike.py            # ~3 keyed credits; needs CMC_API_KEY for calls 2-5
"""

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "proof" / "spike.json"
KEYED = "https://pro-api.coinmarketcap.com"
KEYLESS = "https://pro-api.coinmarketcap.com/public-api"
TICKER, WRAPPER, WRAPPER_ID = "MS", "wMSx", 41513


def get(url, key=None):
    headers = {"Accept": "application/json"}
    if key:
        headers["X-CMC_PRO_API_KEY"] = key
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
            body, code = r.read(), r.status
    except urllib.error.HTTPError as e:
        body, code = e.read(), e.code
    ms = round((time.perf_counter() - t) * 1000)
    try:
        js = json.loads(body)
    except ValueError:
        js = {"_raw": body[:300].decode("utf-8", "replace")}
    return js, {
        "url": url,
        "keyed": bool(key),
        "http": code,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest()[:16],
        "credit_count": (js.get("status") or {}).get("credit_count")
        if isinstance(js, dict)
        else None,
        "elapsed_ms": ms,
        "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main():
    key = os.environ.get("CMC_API_KEY") or ""
    calls = {}

    def call(name, base, path, k=None, **params):
        url = f"{base}{path}?{urllib.parse.urlencode(params)}" if params else f"{base}{path}"
        js, meta = get(url, k)
        calls[name] = {"meta": meta, "response": js}
        print(
            f"  [{meta['http']}] {name:28} credits={meta['credit_count']} {meta['elapsed_ms']} ms"
        )
        return js, meta

    print("spike — is 'untracked' the honest word? (real calls, raw responses kept)\n")
    before = call("key_info_before", KEYED, "/v1/key/info", key)[0] if key else None

    # 1. the listing state, keyless — the leg every judge can re-run with no key
    js1, _ = call(
        "map_keyless",
        KEYLESS,
        "/v1/cryptocurrency/map",
        None,
        listing_status="active,inactive,untracked",
        symbol=WRAPPER,
        aux="first_historical_data,last_historical_data,status,platform",
    )
    rows = js1.get("data") or []
    row = next((r for r in rows if r.get("id") == WRAPPER_ID), None)

    findings = {
        "wrapper": WRAPPER,
        "crypto_id": WRAPPER_ID,
        "map_status": (row or {}).get("status"),
        "map_has_dates": bool(
            row and (row.get("first_historical_data") or row.get("last_historical_data"))
        ),
        "map_platform": (row or {}).get("platform"),
    }

    if key:
        # 2. the roster, keyed — price null, but does the asset trade anywhere?
        js2, _ = call(
            "rwa_quotes_keyed", KEYED, "/v5/real-world-assets/quotes/latest", key, symbol=TICKER
        )
        assets = (js2.get("data") or {}).get("rwa_assets") or []
        asset = next((a for a in assets if a.get("symbol") == TICKER), assets[0] if assets else {})
        tok = next((t for t in asset.get("tokens") or [] if t.get("crypto_id") == WRAPPER_ID), {})
        findings.update(
            {
                "rwa_has_tokens": asset.get("has_tokens"),
                "rwa_rank": asset.get("rwa_rank"),
                "wrapper_price": tok.get("price"),
                "wrapper_issuer": tok.get("issuer_name"),
                "tradfi_markets": asset.get("tradfi_markets"),
            }
        )
        # 3. the quotes surface — does it know a price the RWA page hides?
        js3, m3 = call(
            "crypto_quotes_latest_keyed",
            KEYED,
            "/v2/cryptocurrency/quotes/latest",
            key,
            id=WRAPPER_ID,
        )
        q = ((js3.get("data") or {}).get(str(WRAPPER_ID)) or {}).get("quote") or {}
        findings["quotes_latest_http"] = m3["http"]
        findings["quotes_latest_price_usd"] = (q.get("USD") or {}).get("price")
        # 4. history — has it EVER had a tracked market?
        js4, m4 = call(
            "crypto_quotes_historical_keyed",
            KEYED,
            "/v2/cryptocurrency/quotes/historical",
            key,
            id=WRAPPER_ID,
            count=30,
            interval="daily",
        )
        hist = (js4.get("data") or {}) if isinstance(js4.get("data"), dict) else {}
        findings["quotes_historical_http"] = m4["http"]
        findings["quotes_historical_points"] = len(hist.get("quotes") or [])
        after = call("key_info_after", KEYED, "/v1/key/info", key)[0]
        cm = lambda j: ((j.get("data") or {}).get("usage") or {}).get("current_month") or {}  # noqa: E731
        findings["keyed_credits_this_spike"] = (cm(after).get("credits_used") or 0) - (
            cm(before).get("credits_used") or 0
        )
    else:
        findings["keyed_calls"] = (
            "skipped — no CMC_API_KEY; the keyless leg above is the judged one"
        )

    # the time axis: the same row on the first daily snapshot
    snaps = sorted((ROOT / "data" / "snapshots").glob("*.json"))
    if snaps:
        first = json.loads(snaps[0].read_text())
        prev = next((w for w in first["wrappers"] if w["crypto_id"] == WRAPPER_ID), None)
        findings["first_snapshot"] = {
            "file": snaps[0].name,
            "generated_utc": first["generated_utc"],
            "status_then": (prev or {}).get("status"),
            "same_status_now": bool(prev and prev.get("status") == findings["map_status"]),
        }

    honest = (
        findings["map_status"] == "untracked"
        and findings.get("wrapper_price") is None
        and findings.get("quotes_latest_price_usd") is None
        and findings.get("quotes_historical_points", 0) == 0
    )
    findings["verdict"] = (
        "listed, no CMC-tracked market — and the asset trades on a TradFi venue CMC names, "
        "so 'never traded' would be false. The wording guard stands."
        if honest and findings.get("tradfi_markets")
        else "see calls — the wording must follow the raw rows, not this script"
    )
    findings["time_axis"] = (
        "untracked map rows carry no first_/last_historical_data; the only time axis is the "
        "daily snapshot series this repository records"
        if not findings["map_has_dates"]
        else "the map row carries dates — re-check the time-axis assumption"
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "spike": "is 'untracked' the honest word?",
                "run_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "findings": findings,
                "calls": calls,
            },
            indent=2,
        )
    )
    print("\nfindings:")
    for k, v in findings.items():
        if k != "tradfi_markets":
            print(f"  {k:28} {v}")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0 if findings["map_status"] else 1


if __name__ == "__main__":
    sys.exit(main())
