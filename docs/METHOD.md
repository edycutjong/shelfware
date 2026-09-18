# Method — four ledgers, one join, three counting rules

The formal specification of what `shelfware` counts, so that every number on every surface can
be re-derived from the committed rows by someone who does not trust us.

## The four ledgers

| | Endpoint | Rows | What it contributes | Access |
|---|---|---|---|---|
| **A** | `/v5/real-world-assets/map` | 7,811 underlyings | `rwa_id`, `symbol`, `asset_type`, `rwa_rank`, **`has_tokens`** — the boolean the product corrects | keyed, 0 credits, 32 pages of 250 |
| **B** | `/v5/real-world-assets/quotes/latest?rwa_id=…` | 1,435 wrappers in `tokens[]` | per wrapper: `crypto_id`, `symbol`, `issuer_id`, `issuer_name`, `price`, `market_cap`, `volume_24h` — **including the `price: null` rows** the RWA pages and every price-based tool drop | keyed, 1 credit per 250 assets, 200 ids per call |
| **C** | `/v5/real-world-assets/issuers/list` | 25 issuers | `num_tokens` — what the registry says an issuer has **declared** | keyed, 1 credit |
| **D** | `/public-api/v1/cryptocurrency/map?listing_status=active,inactive,untracked&aux=…` | 38,681 coins | **`status`** per `crypto_id`, `first_historical_data`, `platform` | keyless, 0 credits, 8 pages of 5,000 — or `symbol=` per ticker |
| **E** | `/public-api/v2/cryptocurrency/info?id=…&aux=status,date_added,platform` | per id | `date_added` (the day CMC listed the coin), a coarse `status` (`active` / `inactive`) | keyless, 0 credits, 200 ids per call |

`/v1/key/info` is read before and after a census so the receipt can show the month's credit
counter moving by exactly Σ `credit_count` of the keyed calls.

## The word

`untracked` is CoinMarketCap's listing state. Its map documentation defines it as:

> *"registered cryptocurrency projects that are listed but do not yet meet methodology
> requirements to have tracked markets"*

On every surface this project writes **"listed, no CMC-tracked market"** — never "never traded".
Dinari dShares trade on Dinari's own venue; some wrappers may sit in pools CMC does not index. The claim is about CoinMarketCap's coverage of what CoinMarketCap calls
tokenised, and that is exactly why a judge can re-derive it. The spike that settled the wording
(`docs/proof/spike.json`, 2026-09-18) asked the same wrapper three ways: the map says untracked,
the RWA roster prices it null but names a TradFi venue where the underlying trades,
`quotes/latest` and `quotes/historical` hold no price and no history.

## The join

```
wrapper.status = D[crypto_id].status            if crypto_id is in D
               = "unresolved"                    otherwise (retried once by symbol; see below)
wrapper.date_added = E[crypto_id].date_added     for wrappers that are not active
```

Two corrections the live API made necessary, both in `shelfware/client.py`:

1. **The paged map omits rows the symbol filter returns.** VVV → 40784 was absent from all
   38,681 paged rows (both `sort=cmc_rank` and `sort=id`) yet `symbol=VVV` returns it as
   `active`. Every id that does not resolve after paging is retried by symbol; only what still
   does not resolve is `unresolved`.
2. **The map's symbol filter takes alphanumerics only.** CMC's own RWA symbols include `NVDA.D`,
   `AI.FRx`, `BRK.A.D` (38 wrappers), and one of them rejects the whole call with HTTP 400. Per
   ticker, those wrappers take their live state from ledger E (`active` → tracked; `inactive` →
   the map's finer word, `untracked` or `inactive`, from the committed snapshot) and the row
   names both sources.

## The three counting rules

| Rule | Definition | Conservative direction |
|---|---|---|
| **shelf** | `status == "untracked"` — CMC's word, not `price is None` | The two coincide today with zero exceptions across 1,431 resolved wrappers (invariant I1), but the state is CMC's and the price is a symptom. |
| **zero-tracked underlying** *(the headline)* | an underlying with `has_tokens: true`, at least one attached wrapper, and **every** attached wrapper `untracked` | An `unresolved` or `inactive` wrapper blocks the count. The loose rule ("no active wrapper") is computed and shown beside it; the headline never takes the larger number. |
| **shelf rate (issuer)** | `untracked / attached`, beside Σ `market_cap` of the tracked wrappers | `declared` (ledger C's `num_tokens`) and `attached` (ledger B) are shown as two ledgers; neither is substituted for the other. |

Derived, presentation only: shelf rate per `asset_type` (over wrappers) and the headline split by
`asset_type` (over underlyings); the age of what trades (days since `first_historical_data`,
active wrappers only); time on the shelf (days since `date_added`, untracked wrappers only — a
listing day, not a market day); the chains the shelf sits on.

## The hero rule

> The most prominent tokenised underlying on CoinMarketCap (lowest `rwa_rank`) whose every
> wrapper is untracked.

Today: MS (rank 43); then APH (80), GILD (83), WELL (94), UNP (95). The rule is printed beside
the card on the page and by `scripts/seed.py --hero`. When the census moves, the hero moves.

## Invariants

Held by `tests/test_property.py` over 500 generated ledgers and by `tests/test_join.py` on the
committed census, and re-checked by `python3 -m shelfware verify` on every run.

| # | Invariant | Committed census, 2026-09-18T22:16:17Z |
|---|---|---|
| I1 | `price is None ⇔ status == "untracked"` for every resolved wrapper | 0 exceptions in 1,431 |
| I2 | every wrapper is `active`, `untracked`, `inactive` or `unresolved`, and the four sum to the wrapper count | 758 + 673 + 0 + 4 = 1,435 |
| I3 | `strict zero-tracked ≤ loose zero-tracked ≤ has_tokens`, and every strict one has ≥ 1 wrapper | 476 ≤ 476 ≤ 791 |
| I4 | Σ `by_issuer.attached` = wrappers = Σ `by_type.attached` | 1,435 = 1,435 = 1,435 |
| I5 | the `counts` block equals a recount from `wrappers[]` alone | equal (`shelfware verify`) |
| I6 | `credits_used` = Σ `credit_count` over keyed calls in the receipt = the movement of `/v1/key/info` | 5 = 5 = 12,025 − 12,020 |

## Re-derive by hand

```bash
jq '[.wrappers[] | select(.status=="untracked")] | length' data/census.json                                  # 673 shelf wrappers
jq '.wrappers | group_by(.rwa_id) | map(select(all(.[]; .status=="untracked"))) | length' data/census.json  # 476 zero-tracked underlyings
jq '[.wrappers[] | select(.issuer_name=="Backed Assets")] | (map(select(.status=="untracked")) | length), length' data/census.json  # 632 of 772
```

## The time axis

Untracked map rows carry no `first_historical_data` / `last_historical_data`. The only history
of the shelf is the one this repository records: `scripts/snapshot.py` takes one census a day into
`data/snapshots/YYYY-MM-DD.json` (~5 keyed credits) and `data/delta.json` names what moved between
the two latest days — `newly_tracked` is strictly `untracked → active`, `newly_shelved` strictly
`active → untracked`; a resolution such as `unresolved → active` is listed under `other_flips`
and never counted as a market event. The series started 2026-09-18.
