#!/usr/bin/env python3
"""Cut the seed set — real captured responses with provenance — and pick the hero by rule.

WHAT THIS IS: data/seed/*.json, four real responses from the live API around the one query a
judge sees (MS) plus the edge cases the counting rules exist for: a mixed underlying (NVDA),
a tracked commodity (GOLD/PAXG), an id the map does not carry (VVV), an issuer whose whole
catalogue is on the shelf (Dinari), a registry issuer with nothing attached (Fidelity), and
wrappers with no issuer_id. Offline tests and `bench.py --replay` run on these.

WHAT THIS IS NOT: the demo path. `python3 -m shelfware MS` and `shelfware census` always
fetch live; nothing on the judged path reads this directory.

THE HERO IS A RULE, NOT A PICK: the most prominent tokenised underlying (lowest rwa_rank)
whose every wrapper is untracked, selected from the committed census. If tomorrow's census
promotes wMSx, the rule selects the next one and docs/proof/ms.json is superseded.

    python3 scripts/seed.py            # ~2 keyed credits (needs CMC_API_KEY) + 2 keyless calls
    python3 scripts/seed.py --hero     # only print the rule and its selection, no network
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfware.client import Client, api_key  # noqa: E402
from shelfware.join import HERO_RULE, hero  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed"
CENSUS = ROOT / "data" / "census.json"

# the pitch's shelf list, the mixed cases, the controls — by underlying symbol
NAMED = [
    "MS",
    "NVDA",
    "GOLD",
    "SPCX",
    "GILD",
    "IBIT",
    "ETHE",
    "PLD",
    "BKNG",
    "VVV",
    "AAPL",
    "TSLA",
    "HOOD",
    "SILVER",
]


def select_underlyings(doc, n=40):
    """The named set, then the hero's runners-up, then the largest wrappers-per-underlying."""
    by_sym = {}
    for w in doc["wrappers"]:
        by_sym.setdefault(w["underlying"], []).append(w)
    chosen = [s for s in NAMED if s in by_sym]
    if doc.get("hero"):
        chosen += [r["symbol"] for r in doc["hero"]["runners_up"] if r["symbol"] in by_sym]
    chosen = list(dict.fromkeys(chosen))  # GILD is both named and a runner-up: once
    rest = sorted(by_sym, key=lambda s: (-len(by_sym[s]), s))
    for s in rest:
        if len(chosen) >= n:
            break
        if s not in chosen:
            chosen.append(s)
    return chosen[:n], {s: by_sym[s][0]["rwa_id"] for s in chosen[:n]}


def provenance(meta, **extra):
    return {
        "captured_utc": meta["utc"],
        "endpoint": meta["url"].split("?")[0],
        "params": meta["url"].split("?", 1)[1] if "?" in meta["url"] else "",
        "http": meta["http"],
        "keyed": meta["keyed"],
        "credit_count": meta["credit_count"],
        "sha256": meta["sha256"],
        **extra,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hero", action="store_true", help="print the hero rule and selection only")
    ap.add_argument("--n", type=int, default=40)
    a = ap.parse_args()
    doc = json.loads(CENSUS.read_text())
    has_tokens_rows = [
        {
            "rwa_id": w["rwa_id"],
            "symbol": w["underlying"],
            "name": w.get("underlying_name"),
            "rwa_rank": w.get("rwa_rank"),
        }
        for w in doc["wrappers"]
    ]
    seen, ht = set(), []
    for r in has_tokens_rows:
        if r["rwa_id"] not in seen:
            seen.add(r["rwa_id"])
            ht.append(r)
    h = hero(doc["wrappers"], ht)
    print(f"hero rule: {HERO_RULE}")
    print(
        f"  -> {h['symbol']} ({h['name']}) rwa_rank {h['rwa_rank']}, wrappers {h['wrappers']}; next: "
        + ", ".join(f"{r['symbol']} ({r['rwa_rank']})" for r in h["runners_up"])
    )
    if a.hero:
        return 0
    key = api_key()
    if not key:
        sys.exit("seed.py needs CMC_API_KEY for the two keyed captures (RWA family is keyed)")
    client = Client(api_key=key)
    syms, rwa_ids = select_underlyings(doc, a.n)
    SEED.mkdir(parents=True, exist_ok=True)
    note = "A RECORDING with provenance, for offline tests and bench --replay. The judged path never reads it."

    print(
        f"1. rwa/map — the universe, {len(ht)} has_tokens rows + 20 has_tokens:false controls (0 credits)"
    )
    rwa = client.rwa_map()
    keep = [r for r in rwa if r.get("has_tokens")] + [r for r in rwa if not r.get("has_tokens")][
        :20
    ]
    m = client.receipt[-1]
    (SEED / "rwa_map.json").write_text(
        json.dumps(
            {
                "_note": note,
                **provenance(
                    m, pages=sum(1 for x in client.receipt if x["call"].startswith("rwa/map"))
                ),
                "rows": keep,
            },
            indent=1,
        )
    )

    print(f"2. rwa/quotes — tokens[] for {len(syms)} underlyings (1 credit)")
    assets, _ = client.rwa_quotes(rwa_ids=[rwa_ids[s] for s in syms])
    m = client.receipt[-1]
    (SEED / "rwa_quotes.json").write_text(
        json.dumps(
            {"_note": note, **provenance(m), "underlyings": syms, "rwa_assets": assets}, indent=1
        )
    )

    print("3. rwa/issuers/list — the registry (1 credit)")
    issuers = client.issuers()
    m = client.receipt[-1]
    (SEED / "issuers.json").write_text(
        json.dumps({"_note": note, **provenance(m), "issuers": issuers}, indent=1)
    )

    wsyms = [t["symbol"] for x in assets for t in x.get("tokens") or [] if t.get("symbol")]
    ids = [t["crypto_id"] for x in assets for t in x.get("tokens") or []]
    print(f"4. cmc/map by symbol — the {len(wsyms)} wrapper symbols those resolve to (keyless)")
    rows, m, dropped = client.cmc_map(wsyms)
    slice_rows = [r for r in rows.values() if r["id"] in set(ids)]
    print(f"5. cmc/info — listing dates for the {len(ids)} wrapper ids (keyless)")
    info, metas, bad = client.cmc_info(ids)
    (SEED / "cmc_map_slice.json").write_text(
        json.dumps(
            {
                "_note": note + " Ids in tokens[] that are absent here are the unresolved cases.",
                **provenance(m, dropped_symbols=dropped),
                "rows": slice_rows,
                "info": {
                    "captured_utc": metas[-1]["utc"],
                    "endpoint": metas[-1]["url"].split("?")[0],
                    "unknown_ids": bad,
                    "rows": {
                        str(k): {
                            kk: v.get(kk)
                            for kk in ("id", "symbol", "status", "date_added", "platform")
                        }
                        for k, v in info.items()
                    },
                },
            },
            indent=1,
        )
    )
    print(
        f"\nwrote data/seed/ — {len(keep)} universe rows, {sum(len(x.get('tokens') or []) for x in assets)} wrappers, "
        f"{len(issuers)} issuers, {len(slice_rows)} map rows, {len(info)} listing dates; "
        f"{sum(int(x.get('credit_count') or 0) for x in client.receipt if x['keyed'])} keyed credits"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
