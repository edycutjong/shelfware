#!/usr/bin/env python3
"""Reproducible benchmark: how long does the ticker question and the join actually take?

Two things are timed separately, because they have completely different characters:

    status leg   one keyless call to /public-api/v1/cryptocurrency/map?symbol= (network-bound)
    lookup       the whole ticker question, no key: snapshot roster + live status + live info
    join         the census arithmetic over real rows (CPU-bound, deterministic)

Reporting them together would hide the only interesting fact: the product's own work is
milliseconds, and every second a judge waits is CoinMarketCap's network.

    python3 scripts/bench.py                       # live, keyless: 10 tickers, then the join
    python3 scripts/bench.py --replay              # join only, over data/seed and the census — no network

--replay is deterministic and is the right thing for CI. It is NOT the product: the judged
path is `python3 -m shelfware MS`, which always fetches live.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfware.client import Client  # noqa: E402
from shelfware.join import census, pct_rank, recount  # noqa: E402
from shelfware.lookup import lookup  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed"
CENSUS = ROOT / "data" / "census.json"
ROSTER = ROOT / "data" / "roster_snapshot.json"
# the hero, its runners-up, the mixed cases, a commodity, a no
TICKERS = ["MS", "APH", "GILD", "NVDA", "AAPL", "TSLA", "GOLD", "IBIT", "PLD", "MSFT"]


def report(label, ms, unit="ms"):
    print(
        f"  {label:34} n={len(ms):<4} p50 {pct_rank(ms, 50):9.2f}{unit}   "
        f"p95 {pct_rank(ms, 95):9.2f}{unit}   max {max(ms):9.2f}{unit}"
    )
    return {
        "n": len(ms),
        "p50": round(pct_rank(ms, 50), 3),
        "p95": round(pct_rank(ms, 95), 3),
        "max": round(max(ms), 3),
        "unit": unit,
    }


def timed(fn):
    t = time.perf_counter()
    r = fn()
    return (time.perf_counter() - t) * 1000, r


def replay(iterations):
    out = {}
    seed = {
        n: json.loads((SEED / f"{n}.json").read_text())
        for n in ("rwa_map", "rwa_quotes", "issuers", "cmc_map_slice")
    }
    rwa, assets, issuers = (
        seed["rwa_map"]["rows"],
        seed["rwa_quotes"]["rwa_assets"],
        seed["issuers"]["issuers"],
    )
    cmc = {r["id"]: r for r in seed["cmc_map_slice"]["rows"]}
    info = {int(k): v for k, v in seed["cmc_map_slice"]["info"]["rows"].items()}
    n_w = sum(len(a.get("tokens") or []) for a in assets)
    print(
        f"replay — data/seed captured {seed['rwa_quotes']['captured_utc']}, {n_w} wrappers, no network\n"
    )
    ms = [timed(lambda: census(rwa, assets, cmc, issuers, info=info))[0] for _ in range(iterations)]
    out["join_seed"] = {**report(f"join + count ({n_w} wrappers, seed)", ms), "wrappers": n_w}
    doc = json.loads(CENSUS.read_text())
    ms = [timed(lambda: recount(doc))[0] for _ in range(iterations)]
    out["recount_census"] = {
        **report(f"recount ({len(doc['wrappers'])} wrappers, census)", ms),
        "wrappers": len(doc["wrappers"]),
    }
    return out


def live(iterations, tickers):
    out = {}
    client = Client(api_key=None)
    roster = json.loads(ROSTER.read_text())
    print(
        f"live — keyless, {len(tickers)} tickers: the status leg alone, then the whole question\n"
    )
    status_ms, lookup_ms, errors = [], [], []
    for t in tickers[:iterations]:
        syms = [
            x["symbol"]
            for x in (roster["underlyings"].get(t) or {}).get("tokens", [])
            if x.get("symbol")
        ]
        if syms:
            ms, (rows, meta, _) = timed(lambda syms=syms: client.cmc_map(syms))
            if meta and meta.get("error"):
                errors.append(f"{t}: {meta['error'][:80]}")
            else:
                status_ms.append(ms)
        ms, res = timed(lambda t=t: lookup(t, Client(api_key=None), roster))
        if res["temporary_failure"]:
            errors.append(f"{t}: {res['status']['fallback_reason'][:80]}")
        else:
            lookup_ms.append(ms)
            print(f"    {t:6} {res['verdict']:48} {ms:7.0f} ms")
        time.sleep(0.3)
    for e in errors:
        print(f"  error: {e}")
    if not lookup_ms:
        sys.exit(
            "every ticker failed — the anonymous pool is rate-limiting this IP; wait and re-run"
        )
    if status_ms:
        out["status_leg"] = report("status leg (keyless map call)", status_ms)
    out["lookup"] = report("shelfware TICKER, no key", lookup_ms)
    out["errors"] = errors
    out["tickers"] = tickers[:iterations]
    out["credits_used"] = 0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=None)
    ap.add_argument(
        "--replay", action="store_true", help="join only, no network — CI, not the product"
    )
    ap.add_argument("--json", metavar="PATH")
    a = ap.parse_args()
    out = {
        "mode": "replay" if a.replay else "live",
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if a.replay:
        out.update(replay(a.iterations or 200))
        out["iterations"] = a.iterations or 200
    else:
        out.update(live(a.iterations or len(TICKERS), TICKERS))
        print()
        out.update(replay(200))
        out["iterations"] = a.iterations or len(TICKERS)
    print(f"\n  {'no network' if a.replay else '0 credits — keyless'}")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2, sort_keys=True))
        print(f"  wrote {a.json}")


if __name__ == "__main__":
    main()
