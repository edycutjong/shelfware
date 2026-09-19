# Contributing

## Run it in 30 seconds — no key, no signup, no install

```bash
git clone https://github.com/edycutjong/shelfware.git && cd shelfware
python3 -m shelfware MS
```

The package is stdlib-only. The listing-state leg is a live, keyless call to CoinMarketCap's
`/public-api/v1/cryptocurrency/map` (0 credits to any key); the wrapper roster comes from the
committed snapshot, labelled with its date, because CoinMarketCap keys the RWA family. Export a
free Basic key as `CMC_API_KEY` and the roster leg goes live too.

## Development

```bash
make setup           # dev deps only: pytest, pytest-cov, ruff, mypy, hypothesis, pip-audit
make lint            # ruff check + format check
make typecheck       # mypy
make test            # 104 offline tests, ~1 s, no internet
make test-coverage   # the same, with the engine gated at 90% coverage
make test-api        # the three Vercel functions, in-process with a stubbed fetch
make test-live       # 6 tests against the real CoinMarketCap contract and the deployed /judge route
make demo            # the judged capability, live, no key
make verify          # recount every headline from the committed rows
make site            # re-render site/index.html, site/judge/index.html and data/health.json
make check           # refuse to ship a placeholder, a key, or a page that drifted from its census
make ci              # lint + typecheck + coverage + api tests + audit + check
```

## The one rule that matters here

**Never mock the judged capability.** The state leg of `python3 -m shelfware MS` is a live call
and stays one; `shelfware census` refuses to run without a key rather than replaying. The one
sanctioned offline path is `scripts/bench.py --replay`, which times the join over the committed
rows and is labelled a replay everywhere it appears. A pull request that puts the ticker question
behind a `MOCK=` flag will be closed.

**Say "untracked", not more.** `untracked` is CoinMarketCap's own listing state — *listed, no
CMC-tracked market*. Dinari's dShares trade on Dinari's venue; a pool CMC does not index is still
a pool. Every surface says the listing state and never "never traded"; the readiness gate fails
on the overclaim.

## Tests

Three categories carry more weight than coverage here, and pull requests are expected to keep them:

- **Regression tests are named after the defect they pin**, with the day it was seen against the
  live API — `test_dotted_symbols_are_never_sent_to_the_map_filter`, not `test_client_7`. The
  test list is meant to read as a changelog of real bugs.
- **The counting rules are verified by property, not by example** (`tests/test_property.py`,
  500 generated ledgers, six invariants). If you change the arithmetic, the invariants must
  still hold across the generated input space.
- **The key boundary is tested from both sides**: a keyless call never carries the key even when
  one is exported; a keyed call without a key refuses before touching the network; with a key
  exported, the run says so and the key reaches no surface a judge reads.

Every number a judge reads is held to the data: `scripts/verify.py` recounts the headline from
`data/census.json` on README, DEMO, JUDGE and the page; `tests/test_published_counts.py` holds
the stated test count to the suite; `render_site.py --check` fails if a rendered page is not
what its inputs produce.

## Commits

Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`, `data:`), small and
iterative. `release.yml` derives the version from these, so the prefix decides the version bump.
