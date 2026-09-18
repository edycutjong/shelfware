.PHONY: help setup lint test test-live bench bench-replay seed site demo census snapshot verify check audit ci all

help:  ## show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-13s %s\n",$$1,$$2}'

setup:  ## install dev deps (the product itself needs nothing)
	python3 -m pip install -r requirements-dev.txt

lint:  ## ruff check + format check
	ruff check . && ruff format --check .

test:  ## pytest, offline only (no internet)
	pytest -q -m "not live"

test-live:  ## the live tests — hit the real CoinMarketCap API, keyless
	pytest -q -m live

demo:  ## the judged capability, live, zero config: does MS have a wrapper that trades, and whose?
	python3 -m shelfware MS

census:  ## the full live census (needs CMC_API_KEY; ~5 credits) -> data/census.json + docs/proof/live_run.json
	python3 -m shelfware census

snapshot:  ## take today's daily snapshot and recompute data/delta.json (needs CMC_API_KEY)
	python3 scripts/snapshot.py

verify:  ## recount every headline from the committed rows; exit 1 on drift
	python3 scripts/verify.py

bench:  ## p50/p95 of the live keyless status leg and of the join, separately
	python3 scripts/bench.py --json docs/proof/bench.json

bench-replay:  ## the join alone, over the committed census, no network (CI only — not the product)
	python3 scripts/bench.py --replay --iterations 200

seed:  ## re-select the hero ticker by the published rule and re-cut data/seed/ from the committed census
	python3 scripts/seed.py

site:  ## re-render site/index.html from data/census.json
	python3 scripts/render_site.py

audit:  ## dependency + secret audit
	pip-audit -r requirements.txt || true
	gitleaks detect --no-banner --redact || true

check:  ## refuse to ship a placeholder, a key, or a page that drifted from its census
	python3 scripts/check_submission_readiness.py
	python3 scripts/render_site.py --check
	python3 scripts/verify.py

ci: lint test check  ## everything CI runs, offline
all: ci bench-replay  ## ci plus the deterministic benchmark
