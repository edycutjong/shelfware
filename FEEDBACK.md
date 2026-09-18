# Feedback on the CoinMarketCap API

Written for the CMC product team, who asked for exactly this. Every item below was hit while
building [Shelfware](README.md) against the live API between 2026-09-18 and 2026-09-19 — nothing
is speculative, and each finding carries the date it was observed and the evidence that produced
it. Raw responses for the first three are committed in [`docs/proof/spike.json`](docs/proof/spike.json)
and [`docs/proof/live_run.json`](docs/proof/live_run.json).

## What the API made possible

One join that exists nowhere else. `/v5/real-world-assets/quotes/latest` returns, per underlying,
every wrapper CoinMarketCap knows about — **including the ones priced `null`** — with the issuer
that minted it; `/v1/cryptocurrency/map` returns, keyless, the listing state that explains the
null; `/v2/cryptocurrency/info` returns, keyless, the day each was listed. Put together: a census
of 1,435 wrappers across 791 tokenised assets and 25 issuers, graded by whether a market exists,
for 5 keyed credits and 15 keyless calls in 41 seconds — reproducible by anyone with a free key,
and the verdict for any single ticker reproducible with no key at all. The RWA family is weeks
old and it already carries the two facts an allocator needs and every RWA page omits.

The headline of the feedback: **the RWA surface is the richest thing in the catalogue, and its
`tokens[]` array quietly carries the most useful rows in it — the wrappers with `price: null`.**
Several items below are about making those rows, and the listing state that explains them,
easier to reach.

---

## 1. `has_tokens: true` says "tokenised"; nothing on the RWA surface says whether any wrapper has a market

**Observed 2026-09-18 · `/v5/real-world-assets/map` + `quotes/latest` · severity: high (it is the product)**

The RWA map flags 791 underlyings `has_tokens: true`. Their `tokens[]` in `quotes/latest` hold
1,435 wrappers, and 673 of them (47%) are priced `null`. The reason is not on the RWA surface:
it lives in `/v1/cryptocurrency/map` as `status: "untracked"` — *"listed but do not yet meet
methodology requirements to have tracked markets"*. Joined, **476 of the 791 (60%) have no
wrapper with a CMC-tracked market at all**: MS, GILD, IBIT, ETHE, PLD, BKNG…

**Why it matters:** a developer reading `has_tokens: true` ships "Morgan Stanley is tokenised"
and is wrong in the way that matters to an allocator. **Carry the wrapper's listing state into
`tokens[]`** (`status: "untracked"` beside `price: null`), and consider a
`has_tracked_tokens` boolean on the map beside `has_tokens`.

---

## 2. The RWA family is keyed while the cryptocurrency map is keyless — so the two halves of one question live on two tiers

**Observed 2026-09-18 21:31Z · `/public-api/v5/real-world-assets/map` → 403 error 1005 · severity: medium**

`/public-api/v1/cryptocurrency/map` answers with no key. `/public-api/v5/real-world-assets/*`
answers `403 "An API Key is required for this call."` A keyless integration can therefore say
*whether* a wrapper is tracked but not *which wrappers exist*. Our product ships a dated snapshot
for the second half and labels it. **If the RWA map and `quotes/latest` were on the keyless
surface, the whole census would be reproducible by anyone at 0 credits.**

---

## 3. `market-pairs/list` is documented as Basic and returns 403 error 1006 on Startup

**Observed 2026-09-18 21:31Z · `/v5/real-world-assets/market-pairs/list?symbol=MS` (and NVDA) · severity: medium**

`error_code 1006 "Your API Key subscription plan doesn't support this endpoint."` on a Startup
key, while the documentation lists the endpoint as Basic. It would have been the third evidence
leg per wrapper ("and here are its market pairs — none"). Either the docs or the plan gate is
wrong; **say which.**

---

## 4. The map's `symbol` filter rejects symbols CoinMarketCap itself assigns

**Observed 2026-09-18 22:1xZ · `/v1/cryptocurrency/map?symbol=NVDAX,NVDA.D,…` · severity: high**

```
HTTP 400  error_code 400  "symbol" should only include comma-separated alphanumeric cryptocurrency symbols
```

Dinari's dShares are `NVDA.D`, `AAPL.D`, `BRK.A.D`; Backed's European xStocks are `AI.FRx`,
`AV.GBx`, `ENR.DEx`. **38 of 1,435 RWA wrappers carry a symbol the map will not filter on**, and
one of them in a list rejects the whole call. There is no `id=` filter on the map to fall back to.
We route those wrappers through `/v2/cryptocurrency/info?id=` (keyless, id-based), which
works — but its `status` is a coarser vocabulary (see #7). **Accept the symbols the platform
assigns, or add `id=` to the map's filters.**

---

## 5. An unknown symbol or id fails the whole batched call

**Observed 2026-09-18 · map `symbol=` and info `id=` · severity: medium**

`/v1/cryptocurrency/map?symbol=bMS,MS,bNVDA` → `400 Invalid value for "symbol": "BNVDA"`.
`/v2/cryptocurrency/info?id=28616,…,39318` → `400 Invalid value for 'id': '39318'`. A batch of
200 ids with one stranger returns nothing. The info endpoint at least names every bad id in one
message (`'39318,42326,39002,39839'`), which lets a client drop them and retry once; the map names
one symbol per failure. **Return the rows you can and list the rejects in `status.notice`**, the
way `skip_invalid=true` already works on `quotes/latest`.

---

## 6. The paged map omits rows that the symbol filter returns

**Observed 2026-09-18 22:2xZ · `/public-api/v1/cryptocurrency/map` · severity: high**

Paging the full map with `listing_status=active,inactive,untracked&limit=5000` returns 38,681
unique rows — identical under `sort=cmc_rank` and `sort=id`. Neither set contains id **40784**
(Valvoline Inc, Derivatives). `?symbol=VVV` returns it, `status: "active"`. So a client that
pages the listing to build an index will be told a wrapper does not exist while a client that
asks by symbol is told it trades. We now retry every unresolved id by symbol after paging.
**Document what the listing excludes, or include it.**

---

## 7. Two endpoints, two vocabularies for the same coin's state

**Observed 2026-09-18 22:2xZ · map vs info · severity: medium**

For id 41513 (`wMSx`) on the same minute: `/v1/cryptocurrency/map` says `status: "untracked"`;
`/v2/cryptocurrency/info?aux=status` says `status: "inactive"`; `/v2/cryptocurrency/quotes/latest`
says `is_active: 0`. The map distinguishes *never met the bar* (`untracked`) from *was tracked,
now delisted* (`inactive`) — a distinction that matters for the question "did this ever have a
market" — and the other two surfaces collapse it. A related mismatch: the same X Layer platform is
`platform.id 216` on the map row and `3897` on the quotes row. **One `status` enum across the
catalogue, and one platform id.**

---

## 8. Untracked map rows carry no dates; the listing date is on a different endpoint

**Observed 2026-09-18 · severity: medium**

`aux=first_historical_data,last_historical_data` is empty on every `untracked` row (673 of 673),
so the map cannot say how long a wrapper has sat without a market. `/v2/cryptocurrency/info`
carries `date_added` for the same ids (2026-08-11 for `wMSx`, 2023-12-07 for `NVDA.D`), which is
what we use for "time on the shelf". **Return `date_added` under the map's `aux`** — it is the
only time axis an untracked coin has, and it is one more call per 200 ids today.

---

## 9. `tokens[]` references ids that exist on no public surface

**Observed 2026-09-18 · `quotes/latest` tokens[] · severity: low**

Four wrappers (crypto_ids 39318 SILVER, 39002 HOOD, 39839 QQQ, 42326 APLD) appear in `tokens[]`
with `symbol: null`, and both the map (all three statuses) and `info` reject or omit the ids.
They are counted nowhere in our census and shown in their own bucket. **Either drop them from
`tokens[]` or expose whatever record they refer to.**

---

## 10. The anonymous tier is per IP, shared cloud egress exhausts it for good, and the envelope hides it

**Observed 2026-09-18 22:37Z · first production deploy on Vercel (iad1) · severity: high for any hosted keyless integration**

From our machine every keyless call in this project succeeds. From the serverless host's shared
egress IP the very first call returned `429 error_code 1022 "You've reached the limit for
anonymous access"`, on both the map and the info endpoints, and stayed there; a later invocation
from another instance succeeded. No `Retry-After`, no `X-RateLimit-*` header on either the
refusal or a success, and every keyless 200 says `credit_count: 1` — a charge against an account
that does not exist. We now repeat a refused call on the keyed base and label the row. **Publish
the anonymous quota (per minute, per day, per IP), send `Retry-After`, and report `credit_count:
0` on keyless calls** so a client can tell "free and metered" from "free and unmetered".

---

## 11. `num_tokens` on the issuer registry is undocumented, and disagrees with what is attached

**Observed 2026-09-18 · `/v5/real-world-assets/issuers/list` vs `quotes/latest` · severity: low**

Backed Assets: `num_tokens: 1176` in the registry, 772 wrappers attached to any underlying in
`tokens[]`. Dinari: 91 vs 27 (`/v5/real-world-assets/issuers?issuer_id=` shows the other 64 carry
no `rwa_id`). Fidelity: 1 declared, 0 attached. We show both numbers as two ledgers and substitute
neither. **Document what `num_tokens` counts.**

---

## 12. A null-quoted row costs a credit; an empty history costs none

**Observed 2026-09-18 22:02Z · severity: low**

`/v2/cryptocurrency/quotes/latest?id=41513` returns a full row whose every `quote.USD` field is
`null` — and charges `credit_count: 1`. `/v2/cryptocurrency/quotes/historical?id=41513` returns
`quotes: []` and charges 0. Consistent behaviour would be welcome; better still, a 200 with an
explicit `status: "untracked"` on the quotes row so the client learns *why* the price is null.

---

*All of the above is reproducible from this repository: `python3 scripts/spike.py` for #1, #7,
#12 (2 keyed credits), `python3 -m shelfware census` for #4–#6, #8, #9, #11 (5 credits), and the
deployment at [shelfware-cmc.vercel.app/api/status](https://shelfware-cmc.vercel.app/api/status?symbols=wMSx&ids=41513)
for #10.*
