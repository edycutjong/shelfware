<div align="center">

<img src="docs/assets/readme-hero-animated.svg" alt="Shelfware — counts the shelf. The join sweeps a shelf of amber ‘tokenised’ boxes: those with a market turn green, the rest turn grey." width="100%">

<h1>Shelfware</h1>

<p><em>Six in ten tokenised stocks on CoinMarketCap have no wrapper with a tracked market.</em></p>

<p>CoinMarketCap's RWA surface answers <strong>"is this asset tokenised?"</strong> with a boolean.
Shelfware answers the question an allocator actually asks before acting: <strong>does any wrapper
of it have a market, and whose?</strong> — by joining the wrapper roster, <code>price: null</code>
rows included, to each wrapper's listing state.</p>

<p><strong>Live, 2026-09-18T22:16Z, 5 keyed credits, 40.9 s:</strong> of the 791 underlyings
CoinMarketCap flags <code>has_tokens: true</code>, <strong>476 of 791 (60%) have no wrapper with a
CMC-tracked market.</strong> 673 of 1,435 wrappers are on the shelf; Backed Assets' catalogue is
82% shelf, Dinari's 100%. <a href="DEMO.md">Receipt →</a></p>

<br/>

[![Judge Guide](https://img.shields.io/badge/⚖️_Start-Here-06b6d4?style=for-the-badge)](JUDGE.md)
[![Live](https://img.shields.io/badge/📦_shelfware--cmc.vercel.app-Live-0B0F14?style=for-the-badge)](https://shelfware-cmc.vercel.app)
[![API Feedback](https://img.shields.io/badge/📮_CMC_API-Feedback-4C9AFF?style=for-the-badge)](FEEDBACK.md)
[![Built for Build with CMC](https://img.shields.io/badge/DoraHacks-Build_with_CMC-8b5cf6?style=for-the-badge)](https://dorahacks.io/hackathon/coinmarketcap-api-202609/detail)

<br/>

![Python](https://img.shields.io/badge/Python_3.11-3776AB?style=flat&logo=python&logoColor=white)
![CoinMarketCap](https://img.shields.io/badge/CoinMarketCap_RWA_API-3861FB?style=flat&logo=coinmarketcap&logoColor=white)
![No API key](https://img.shields.io/badge/API_key-optional-4C9AFF?style=flat)
![Zero dependencies](https://img.shields.io/badge/runtime_deps-zero-5E6C80?style=flat)
![Tests](https://img.shields.io/badge/tests-114-3BD37D?style=flat)
[![License](https://img.shields.io/badge/License-MIT-FFB020?style=flat)](LICENSE)

</div>

---

## 📸 See it in action

No key. No signup. No install. One command:

```bash
git clone https://github.com/edycutjong/shelfware.git && cd shelfware
python3 -m shelfware MS
```

```
shelfware MS — does it have a wrapper that trades, and whose?

  MS  Morgan Stanley · stock · rwa_rank 43 · has_tokens: true
      roster: snapshot 2026-09-18T22:16:17Z (the RWA endpoints need a key; export CMC_API_KEY to go live)
      ▒ wMSx  Wrapped Morgan Stanley Tokenized Stock (xStock)
          issuer   Backed Assets  6878977dcbbf471de3366e85
          chain    X Layer  0x2874A11805783324C54562eDB1A641C5d1d077a5
          price    null · market_cap null · volume_24h null
          status   UNTRACKED      ← /public-api/v1/cryptocurrency/map, live, keyless, 0 credits
                   "listed, no CMC-tracked market" — CMC: registered cryptocurrency projects that are listed but do not yet meet methodology requirements to have tracked markets
                   listed 2026-08-11 (date_added) · 38 days on the shelf

  0 of 1 wrapper(s) with a CMC-tracked market

receipt: cmc/map symbol=wMSx → HTTP 200 · keyless · 0 credits to any key · 491 ms · sha256 d7e1ecdef293e6c8  |  cmc/info batch 1 (1 ids) → HTTP 200 · keyless · 0 credits to any key · 762 ms · sha256 1559b2c185ccabe8
```

The RWA page says *tokenised*. The listing state says *listed, no CMC-tracked market*. Both come
from the CoinMarketCap API; Shelfware puts them on one row. Then the issuer table shows the same
pair 632 times in Backed Assets' row.

**MS is a rule, not a pick** — the most prominent tokenised underlying (lowest `rwa_rank`) whose
every wrapper is untracked. If its wrapper comes alive tomorrow, the rule moves to APH and the
delta panel shows the flip.

The one screen, live: **[shelfware-cmc.vercel.app](https://shelfware-cmc.vercel.app)** — the
number, the issuer table, and the same ticker question through the site's proxy, with the raw
API rows in an evidence drawer beside every answer.

## 🔑 With a free key — the roster goes live, and the census runs

```bash
export CMC_API_KEY=...        # a free Basic key from coinmarketcap.com/api; never committed, never required
python3 -m shelfware MS       # the roster leg goes live (1 credit); the state leg was live already
python3 -m shelfware census   # 7,811 underlyings → 1,435 wrappers → the count, ~5 credits, ~40 s
python3 -m shelfware verify   # recount every headline from the committed rows
```

The census fits Basic tier with room to spare: 5 credits a run, 0 for every state lookup.

## 🔌 The endpoints — named, with what each contributes

```
/v5/real-world-assets/map              universe: every underlying + has_tokens         keyed · 0 credits
/v5/real-world-assets/quotes/latest    tokens[] wrapper roster incl. price:null rows   keyed · 1 credit / 250 assets
/v5/real-world-assets/issuers/list     issuer registry, num_tokens declared            keyed · 1 credit
/public-api/v1/cryptocurrency/map      listing state, birth date, chain per wrapper    keyless · 0 credits
/public-api/v2/cryptocurrency/info     date_added — the day the shelf wrapper was listed keyless · 0 credits
/v1/key/info                           credit accounting in the receipt               keyed · 0 credits
/v5/real-world-assets/market-pairs/list   NOT USED — 403 error 1006 on the Startup plan (docs say Basic)
```

**Why only CoinMarketCap.** The wrapper roster with its null-price rows exists in one place
(`tokens[]`); the listing state that explains the nulls exists in one place (`status` on the map).
Delete the API and both ledgers vanish — recovering them would take an issuer-by-issuer catalogue
crawl and a per-venue market census.

## 🧮 The three counting rules

| Rule | Definition | Direction |
|---|---|---|
| shelf | `status == "untracked"` — CMC's own word, not `price is None` | the two coincide today with 0 exceptions in 1,431 resolved wrappers |
| zero-tracked underlying *(the headline)* | **every** attached wrapper untracked | an unresolved or inactive wrapper blocks the count; the loose rule is shown beside it and never headlined |
| shelf rate per issuer | untracked ÷ attached, beside the live market cap of what trades | `declared` (registry `num_tokens`) and `attached` are two ledgers; neither substitutes for the other |

Re-derive by hand: `jq '.wrappers | group_by(.rwa_id) | map(select(all(.[]; .status=="untracked"))) | length' data/census.json` → 476. Full method and invariants: [docs/METHOD.md](docs/METHOD.md).

## 🧪 Tests and benchmarks

**114 tests** — 99 offline Python (`make test`, ~1 s, no internet), 9 for the proxy functions
(`make test-api`, stubbed fetch), 6 live against the real contract and the deployed `/judge` route (`make test-live`, keyless). Nine regressions are named for the defect they pin, each seen against
the live API on 2026-09-18; one property test holds six invariants over 500 generated ledgers.

| Measurement | n | p50 | p95 |
|---|---|---|---|
| state leg, one keyless map call | 9 | 282 ms | 546 ms |
| `shelfware TICKER`, no key | 9 | 552 ms | 603 ms |
| join + count over 1,435 wrappers | 200 | 1.9 ms | 2.2 ms |

`make bench` reproduces it; `docs/proof/bench.json` is the committed run.

## 🗂 Repository

```
shelfware/      the engine — client, join, lookup, delta, verify, cli (stdlib only)
scripts/        spike · snapshot · seed · bench · verify · render_site · check_submission_readiness · dev_server
api/            roster (keyed, snapshot fallback labelled) · status (keyless first) · health — Vercel functions
site/           the one screen, rendered from data/census.json
data/           census.json · roster_snapshot.json · snapshots/ · delta.json · seed/
docs/proof/     live_run.json · ms.json · bench.json · spike.json — the receipts
DEMO.md · JUDGE.md · ARCHITECTURE.md · FEEDBACK.md · docs/METHOD.md · docs/COMPARISON.md
```

## ⚠️ Honest limitations

- **"untracked" is CoinMarketCap's listing state**, not a claim about the world: *listed, no
  CMC-tracked market*. Dinari dShares trade on Dinari's own venue. The number is about CMC's
  coverage of what CMC calls tokenised — which is exactly why it can be re-derived.
- **The roster leg needs a key** (the RWA family is keyed; keyless → 403 error 1005). Without one
  it is a dated snapshot, labelled on the row; the state leg is live regardless.
- **The map's symbol filter rejects CMC's own dotted symbols** (`NVDA.D`, 38 wrappers). Those rows
  combine the keyless info endpoint with the committed snapshot and say so.
- **The census is a daily series, not a history.** Untracked rows carry no dates; the series
  started 2026-09-18.
- Twelve dated findings for the CMC team, with evidence: [FEEDBACK.md](FEEDBACK.md).

## 📄 License

MIT — see [LICENSE](LICENSE). Built by Edy Cu for the Build with CMC: API Hackathon, Real World
Assets track.
