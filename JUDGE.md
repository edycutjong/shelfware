# For judges

Everything you need in one page. No setup, no key, no account.
Built on the CoinMarketCap API for the Build with CMC: API Hackathon — **Real World Assets** track.

## The claim

**CoinMarketCap's RWA surface says whether an asset is tokenised. It does not say whether any
wrapper of it has a market. Joined to the cryptocurrency map's listing state, 476 of the 791
underlyings it flags `has_tokens: true` — 60% — have no wrapper with a CMC-tracked market.**

## The 30-second path

```bash
git clone https://github.com/edycutjong/shelfware.git && cd shelfware
python3 -m shelfware MS
```

Nothing else is required: the package is stdlib-only, the state leg is keyless. You will see
Morgan Stanley's one wrapper (`wMSx`, Backed Assets, X Layer), its `price: null`, and its
listing state `UNTRACKED` fetched live from `/public-api/v1/cryptocurrency/map` — with CMC's own
definition of the word beside it, the day it was listed, and the receipt line (endpoint, HTTP,
credits, sha256).

Or open **[shelfware-cmc.vercel.app](https://shelfware-cmc.vercel.app)**: the census, the issuer
table, and the same ticker question live through the site's proxy. Type `NVDA` for a mixed case
(7 of 8 wrappers tracked; Dinari's is not), `GILD` or `PLD` for more shelf, `GOLD` for a
commodity that trades. Open the evidence drawer on any answer for the raw `tokens[]` entry, the
raw map row and the raw info row.

1. **The two facts come from the same API and disagree.** `has_tokens: true` is from the RWA
   map; `status: untracked` is from the cryptocurrency map. The product is that pair, one row at
   a time; the issuer table is the same pair 772 times (Backed Assets: 632 of 772 on the shelf).
2. **The number is a count, not a model.** Two `jq` filters over the committed rows reproduce
   it; `python3 -m shelfware verify` does the same and fails on drift. See [DEMO.md](DEMO.md).
3. **The word is CoinMarketCap's.** "untracked" means *listed, no CMC-tracked market*, and the
   surfaces say so — never "never traded". The spike that settled the wording is committed.

## Receipt — live census, 2026-09-18T22:16:17Z

| | |
|---|---|
| Wall clock | **40.9 s**, 54 calls |
| Rows | 7,811 underlyings · 791 `has_tokens` · **1,435 wrappers** · 25 issuers · 38,682 map rows |
| **Keyed credits** | **5** — `/v1/key/info` read 12,020 → 12,025 before and after |
| Keyless calls | 15, charged to no key |
| **The number** | **476 of 791** tokenised underlyings with no wrapper that has a CMC-tracked market (60%); stocks alone 437 of 689 (63%); 673 of 1,435 wrappers untracked |
| Issuers | Dinari 27 / 27 on the shelf · Backed 632 / 772 (82%, $669M live in the rest) · Robinhood 8 / 106 · Ondo 4 / 214 · bStocks 0 / 77 |
| Tests | **106** (92 offline in ~1 s, 9 for the proxy functions, 5 live against the real contract), 9 named for the defect they pin, one property over 500 generated ledgers |
| Latency | ticker question p50 **552 ms** keyless (p95 603 ms); the join itself 1.2 ms |
| Raw receipts | [`docs/proof/live_run.json`](docs/proof/live_run.json) · [`ms.json`](docs/proof/ms.json) · [`bench.json`](docs/proof/bench.json) · [`spike.json`](docs/proof/spike.json) |

## Reproduce

```bash
python3 -m shelfware MS                 # the ticker question, keyless
python3 -m shelfware NVDA               # a mixed one
python3 -m shelfware verify             # recount the headline from data/census.json
make test                               # 92 offline tests
make test-live                          # 5 live tests, keyless
export CMC_API_KEY=… && make census     # the full census, ~5 credits (a free Basic key is enough)
```

## Why only CoinMarketCap

The wrapper roster with its null-price rows exists in exactly one place: `tokens[]` on
`/v5/real-world-assets/quotes/latest`. The listing state that explains the nulls exists in
exactly one place: `status` on `/v1/cryptocurrency/map`. Delete CoinMarketCap and both ledgers
vanish; recovering them would take an issuer-by-issuer catalogue crawl and a per-venue market
census. Six endpoints are used (named in [ARCHITECTURE.md](ARCHITECTURE.md)); a seventh,
`market-pairs/list`, was tried and is plan-gated on Startup — recorded, not built on.

## Honest limitations

- "untracked" is CMC's listing state, not a claim that nothing ever traded anywhere.
- The roster leg needs a key (the RWA family is keyed); with none it is a dated snapshot, labelled.
- The map's symbol filter rejects CMC's own dotted symbols (38 wrappers); those rows name the
  two sources they combine.
- The series started 2026-09-18; the delta panel appears once a second day exists.
- 4 wrapper ids resolve nowhere and are counted nowhere.

Twelve dated findings for the CMC team are in [FEEDBACK.md](FEEDBACK.md).

## Links

| | |
|---|---|
| **Run it** | [DEMO.md](DEMO.md) — transcripts + receipts |
| **How it works** | [ARCHITECTURE.md](ARCHITECTURE.md) — derived from the code · [docs/METHOD.md](docs/METHOD.md) — the rules and invariants |
| **The field** | [docs/COMPARISON.md](docs/COMPARISON.md) |
| **API feedback for CMC** | [FEEDBACK.md](FEEDBACK.md) |
| **The engine** | [`shelfware/`](shelfware/) — 1,573 lines, stdlib only |
| **Live** | [shelfware-cmc.vercel.app](https://shelfware-cmc.vercel.app) · [/api/health](https://shelfware-cmc.vercel.app/api/health) |
