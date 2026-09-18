# The field — the other Real World Assets entries, and the exact boundary

Read from the public BUIDL gallery of the Build with CMC: API Hackathon on 2026-09-18. One line
each on where Shelfware stops and they begin; none of the four overlap on the row that matters.

| BUIDL | What it is | The boundary |
|---|---|---|
| **Signal Desk** (48805) | A live RWA issuer explorer over 20 endpoints, with a capability probe that classifies each as reachable / plan-403 / bad-request, and an Nvidia → issuer → every-token inversion. | Explores wrappers **that trade**. It is built on the seven `/v5/real-world-assets/*` endpoints and prices what has a price. Shelfware is built on the `price: null` rows in `tokens[]` that a price explorer filters out, and joins them to the one ledger the RWA family does not carry — the cryptocurrency map's listing state. Different rows, different question. |
| **Parity** (48797) | Fair-price / wrapper-spread for tokenised stocks — a wrapper's price against its underlying. | A wrapper with no CMC-tracked market has no price to compare, so every row Shelfware counts is a row Parity cannot show. Parity answers *"is the price right?"* for the 758 wrappers that have one; Shelfware answers *"is there a market at all, and whose?"* for all 1,435. |
| **RWA Compass** (48802) | An agent over the RWA endpoints (pitch only at the time of reading). | An agent reasons over the RWA surface; Shelfware is a census with no model in it — every number is a count over committed rows a judge can re-derive with `jq`. Where Compass would say *"tokenised"*, Shelfware says *"tokenised, and 0 of 1 wrappers has a market"*. |

**What none of them count:** 476 of 791 tokenised underlyings (60%) have no wrapper with a
CMC-tracked market; Backed Assets' 772-wrapper catalogue is 82% shelf; Dinari's is 100%. The
`has_tokens: true` flag and the `status: untracked` state come from the same API, and no other
entry puts them side by side.

**What they do that Shelfware does not, deliberately:** price charts, wrapper-vs-underlying
spreads, portfolios, issuer profiles of what trades, off-CMC venue discovery. Those are their
lanes; the scope here is one verb — count the shelf — and one screen.
