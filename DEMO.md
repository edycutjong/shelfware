# Demo — a real run, with its receipt

Everything below is a transcript of actual runs against CoinMarketCap's live API on
**2026-09-18**. No fixtures, no flags. Re-run it yourself; the numbers will move, because they come
from the market rather than from this file, and the page states the day it counted.

## Reproduce — no key, no install

```bash
git clone https://github.com/edycutjong/shelfware.git && cd shelfware
python3 -m shelfware MS
```

That is the whole thing: the package is stdlib-only and the state leg is keyless. `MS` is not a
pick — it is the ticker a published rule selects (see below). Try `NVDA` for a mixed one, `GILD`,
`IBIT`, `PLD` for more shelf, `GOLD` for a commodity that trades, `MSFT` for eight wrappers where
one is on the shelf.

**Two legs, labelled on every row.** The roster (which wrappers exist) comes from
`/v5/real-world-assets/quotes/latest`, which CoinMarketCap keys (keyless → 403 error 1005), so with
no key it is read from the committed snapshot and says so with its date. The state (does the
wrapper have a CMC-tracked market) comes from `/public-api/v1/cryptocurrency/map` — **live, keyless,
0 credits** — and the listing date from `/public-api/v2/cryptocurrency/info`, also keyless. Unset
every CMC variable and the verdict is still a live answer.

**There is no offline flag on this path, deliberately.** The one replay in the repository
(`scripts/bench.py --replay`) times the join over the committed rows and is labelled a replay
everywhere it appears; nothing on the judged path reads it.

### With a free key — the roster goes live, and the census runs

```bash
export CMC_API_KEY=...            # free Basic key from coinmarketcap.com/api; never committed
python3 -m shelfware MS           # roster live (1 credit), state still keyless
python3 -m shelfware census       # the full census, ~5 credits, ~40 s
python3 -m shelfware verify       # recount every headline from the committed rows
```

The key is read from the environment at call time, never from a file. A keyed run says so on
the roster line and in its receipt, so it can never pass as a keyless one.

## Receipt — `python3 -m shelfware MS`, keyless, 2026-09-18T22:43:39Z

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
wrote docs/proof/ms.json
```

| | |
|---|---|
| **Credentials** | none — run with `CMC_API_KEY`, `COINMARKETCAP_API_KEY` and `CMC_PRO_API_KEY` explicitly unset |
| **State leg** | `https://pro-api.coinmarketcap.com/public-api/v1/cryptocurrency/map?listing_status=active,inactive,untracked&symbol=wMSx&aux=…` → HTTP 200 · **0 credits** |
| **Listing date** | `/public-api/v2/cryptocurrency/info?id=41513&aux=status,date_added,platform` → HTTP 200 · 0 credits |
| **Roster leg** | committed snapshot of the census below, labelled with its date (live with a key, 1 credit) |
| **Wall clock** | 0.55 s median for the whole question over 9 tickers, keyless ([`bench.json`](docs/proof/bench.json)) |
| **Raw receipt** | [`docs/proof/ms.json`](docs/proof/ms.json) — the `tokens[]` entry, the map row, the info row, both call metas |

The two facts on that card come from the same API and disagree about what "tokenised" means:
`has_tokens: true` from the RWA map, `status: untracked` from the cryptocurrency map. That is the
whole product, one row at a time. The issuer table is the same pair, 772 times.

## Receipt — `python3 -m shelfware census`, live, 2026-09-18T22:16:17Z

```
shelfware census — keyed (A, B, C) + keyless (D), live

1. /v5/real-world-assets/map (keyed, 0 credits)
   7,811 underlyings · 791 has_tokens
2. /v5/real-world-assets/quotes/latest tokens[] (keyed, 1 credit / 250 assets)
   1,435 wrappers
3. /v5/real-world-assets/issuers/list (keyed, 1 credit)
   25 issuers
4. /public-api/v1/cryptocurrency/map active,inactive,untracked (keyless, 0 credits)
   38,681 rows
   +1 resolved by symbol that the paged map omitted
5. /public-api/v2/cryptocurrency/info date_added for the shelf (keyless, 0 credits)
   673 listing dates · 4 ids CMC does not know

join
  wrappers 1,435: active 758 · untracked 673 · inactive 0 · unresolved 4  → 46.9% on the shelf
  underlyings with has_tokens 791: 476 have no wrapper with a CMC-tracked market  → 60.2%   (loose rule, no active wrapper: 476)
  what trades is young: median 80 d · p10 24 · p90 380 (n=757)
  time on the shelf (since date_added): median 38 d · p10 38 · p90 100 (n=673)
  hero by rule (the most prominent tokenised underlying on CoinMarketCap (lowest rwa_rank) whose every wrapper is untracked): MS rwa_rank 43

  issuer                        declared attached tracked  shelf   live market cap
  Dinari Assets                       91       27       0   100%   $0
  Backed Assets                     1176      772     140    82%   $669,101,579
  (no issuer)                          —        5       3    20%   $0
  Robinhood                          107      106      98     8%   $135,432,308
  Ondo Assets                        551      214     210     2%   $891,329,106
  NA (Derivatives)                   247      131     128     0%   $0
  bStocks                             77       77      77     0%   $797,027,721
  Reality                             71       71      71     0%   $131,344,866
  Hyperliquid Assets                  12       12      12     0%   $1,111
  Backpack                             7        5       5     0%   $17,404,739

  by type: stock 49% shelf (606/1244) · etf 38% shelf (67/177) · commodity 0% shelf (0/14)

40.9 s · 39 keyed calls = 5 credits · 15 keyless calls = 0 credits to any key
wrote data/census.json
wrote data/roster_snapshot.json (791 underlyings with tokens, 7020 without)
wrote docs/proof/live_run.json
wrote data/snapshots/2026-09-18.json
```

| | |
|---|---|
| **Wall clock** | **40.9 s**, 54 calls, cold start to final line |
| **Rows** | 7,811 underlyings · 791 `has_tokens` · **1,435 wrappers** · 38,682 map rows · 25 issuers |
| **Keyed credits** | **5** — `/v1/key/info` read 12,020 → 12,025 credits used this month, before and after, which equals Σ `status.credit_count` over the 39 keyed calls |
| **Keyless calls** | 15 (8 map pages + 1 retry by symbol + 6 info batches) — the envelope says `credit_count: 1` on each, charged to no key |
| **The number** | **476 of 791 tokenised underlyings (60.2%) have no wrapper with a CMC-tracked market.** Stocks alone: 437 of 689 (63%). 673 of 1,435 wrappers (46.9%) are on the shelf; 603 of them sit on X Layer, all Backed Assets. |
| **Raw receipt** | [`docs/proof/live_run.json`](docs/proof/live_run.json) — all 54 calls: URL, HTTP, `credit_count`, bytes, sha256, UTC |
| **The rows** | [`data/census.json`](data/census.json) — every wrapper with its underlying, issuer, price, state, chain, listing date |

### Check it by hand

Two `jq` filters over the committed rows reproduce both headline numbers. `python3 -m shelfware
verify` does the same in Python and fails on any drift between the rows, the counts block, the
README and the page.

```bash
jq '[.wrappers[] | select(.status=="untracked")] | length' data/census.json                                  # 673
jq '.wrappers | group_by(.rwa_id) | map(select(all(.[]; .status=="untracked"))) | length' data/census.json  # 476
```

The rule is deliberately the conservative one. An underlying counts only when **every** attached
wrapper is `untracked`; a wrapper whose id resolves on no public CMC surface (4 today, all with a
null symbol in `tokens[]`) is shown in its own bucket and never counted as shelf. The loose rule
("no active wrapper") gives the same 476 today; the headline never takes the larger number.

`price == null ⇔ status == "untracked"` held with zero exceptions across all 1,431 resolved
wrappers, so the join is exact, not heuristic — and the test suite re-checks it on every run.

## How the demo ticker is chosen — a rule, not a pick

> **The most prominent tokenised underlying on CoinMarketCap (lowest `rwa_rank`) whose every
> wrapper is untracked.**

`scripts/seed.py --hero` prints the selection from the committed census: **MS, rank 43** — the
only all-shelf underlying inside CMC's top 50. Next: APH (80), GILD (83), WELL (94), UNP (95). If
tomorrow's census promotes `wMSx` to `active`, the rule selects APH, `docs/proof/ms.json` is
superseded, and the delta panel shows the flip — a shelf wrapper coming alive on camera is the
strongest possible proof that the census is live.

## Benchmarks

```bash
make bench           # live, keyless: 10 tickers, then the join
make bench-replay    # the join alone, over the committed rows — no network, CI only
```

The state leg, the whole question and the arithmetic are timed **separately**, because averaging
them would hide the only interesting fact: the product's own work is a millisecond and everything
a judge waits for is CoinMarketCap's network. Nearest-rank percentiles — every p95 is a real
observation. Live run 2026-09-18T22:55:13Z, keyless, 0 credits ([`bench.json`](docs/proof/bench.json)):

| Measurement | n | p50 | p95 |
|---|---|---|---|
| State leg — one keyless `map?symbol=` call | 9 | **282 ms** | 546 ms |
| `shelfware TICKER`, no key — snapshot roster + live map + live info | 9 | **552 ms** | 603 ms |
| Join + count, 243 real wrappers (seed set) | 200 | **1.17 ms** | 1.48 ms |
| Recount, 1,435 committed wrappers | 200 | **1.94 ms** | 2.22 ms |

That n=9 is not a typo: **the tenth ticker (PLD) hit the anonymous tier's per-IP burst limit —
`429 error_code 1011 "You've hit an IP rate limit."` — after ~20 keyless calls in 15 seconds**, and
the bench reports it under `errors` rather than smoothing it away. That is the honest cost of a
keyless demo run in a tight loop; a judge typing tickers by hand never approaches it, and the
CLI backs off (2, 4, 8, 16 s) when it does.

## Tests

| | Count |
|---|---|
| Total | **99** (85 offline Python, 9 Node for the proxy functions, 5 live) |
| Regression tests named for the defect they pin, each seen against the live API on 2026-09-18 | 9 |
| Property-based verification of the join | **500 generated ledgers, 0 failing** — six invariants |
| Live tests asserting the outside world | 5 — the keyless map returns a state for `wMSx`; ten committed states still match; the info leg carries the listing date; the RWA family still refuses keyless calls with error 1005; with a key, the roster still prices `wMSx` null |

```bash
make test        # 85 offline tests, no internet, ~1 s
make test-api    # 9 tests of api/*.js with a stubbed fetch
make test-live   # 5 tests against the real CoinMarketCap contract, keyless
```

The property test is the number worth reading: across 500 generated ledgers the counting rules
never violated `strict ≤ loose ≤ has_tokens`, the issuer and type tables never summed to anything
but the wrapper count, the counts block always equalled a recount from the rows, and an unresolved
id was never counted as shelf. Reproduce: `pytest tests/test_property.py -q`.

## The one screen — [shelfware-cmc.vercel.app](https://shelfware-cmc.vercel.app)

The page carries the census above with its receipt, and the same ticker question through two
small serverless functions: `/api/roster` (keyed, one symbol, the key in the deployment's
environment — falls back to the committed snapshot with its date, never silently) and
`/api/status` (keyless first; when CoinMarketCap's anonymous pool refuses the host's shared IP,
the identical call is repeated keyed for 1 credit and the row says so). `/api/health` reports
the census date, the snapshot count and whether the roster key is configured — never the key.

## Honest limitations

- **"untracked" is CoinMarketCap's listing state, not a claim about the world.** It means listed,
  no CMC-tracked market. Dinari dShares trade on Dinari's own venue; some wrappers may sit in
  pools CMC does not index. The number is about CMC's coverage of what CMC calls tokenised, and
  the spike that settled the wording is in [`docs/proof/spike.json`](docs/proof/spike.json).
- **The roster leg needs a key.** With none, it is a dated snapshot, labelled; the state leg is
  live regardless. `shelfware census` refuses without a key rather than replaying.
- **The map's symbol filter rejects CMC's own dotted symbols** (`NVDA.D`, `AI.FRx` — 38 wrappers,
  HTTP 400 for the whole call). Those take their live state from `/v2/cryptocurrency/info`,
  whose vocabulary is coarser (`active` / `inactive`), and the map's finer word from the committed
  snapshot; each row names both sources. Filed in [FEEDBACK.md](FEEDBACK.md).
- **The census is a daily series, not a history.** Untracked rows carry no dates; `date_added`
  from the info endpoint gives a listing day, not a market day. The series started 2026-09-18.
- **The anonymous tier is per IP.** A shared cloud egress IP can be refused outright (429 error
  1022); the CLI backs off (2, 4, 8, 16 s) and, if a key is exported, repeats the identical call
  keyed and says so; an exhausted pool with no key exits **75** (`EX_TEMPFAIL`) after answering
  from the snapshot, so a script can tell a throttle from a failure.
- **4 wrapper ids resolve nowhere** (39318 SILVER, 39002 HOOD, 39839 QQQ, 42326 APLD — null
  symbols in `tokens[]`, unknown to both the map and the info endpoint). Shown, never counted.
