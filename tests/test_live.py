"""Live tests — the external side effect, not a return value (LESSONS R11).

    pytest -q -m live

Each test hits CoinMarketCap's real API, keyless, and asserts against what the outside world
returns. They fail if CMC changes the contract the product rests on. Every test also asserts
that the call carried no key, so the judged path is proven keyless while it is proven live.
"""

import json
import os
from pathlib import Path

import pytest

from shelfware.client import Client, api_key
from shelfware.verify import live_check

pytestmark = pytest.mark.live
ROOT = Path(__file__).resolve().parents[1]


def keyless():
    return Client(api_key=None)


def _skip_if_throttled(meta):
    if meta and meta.get("throttled"):
        pytest.skip(f"the anonymous pool is throttling this IP: {meta['error']}")


def test_live_keyless_map_returns_a_listing_state_for_the_hero_wrapper():
    """The whole claim rests on this field existing and being one of CMC's three states."""
    c = keyless()
    rows, meta, dropped = c.cmc_map(["wMSx"])
    _skip_if_throttled(meta)
    assert meta["error"] is None and meta["keyed"] is False and dropped == []
    row = rows.get(41513)
    assert row is not None, "wMSx (41513) is no longer in the map — the hero rule will move on"
    assert row["status"] in ("active", "untracked", "inactive")
    assert meta["url"].startswith("https://pro-api.coinmarketcap.com/public-api/")


def test_live_ten_committed_statuses_still_match_the_world():
    """Ten wrappers sampled from data/census.json, re-fetched keyless. A mismatch is the
    market moving (a shelf wrapper coming alive), which the delta panel exists to show —
    but on the day the census is cut, they match."""
    doc = json.loads((ROOT / "data" / "census.json").read_text())
    ok, lines, meta = live_check(doc, keyless(), n=10, seed=20260918)
    _skip_if_throttled(meta)
    assert ok is not None, lines
    assert ok, "\n".join(lines)


def test_live_keyless_info_carries_the_hero_wrappers_listing_date():
    c = keyless()
    rows, metas, dropped = c.cmc_info([41513])
    _skip_if_throttled(metas[-1] if metas else None)
    assert 41513 in rows and rows[41513]["date_added"].startswith("20")
    assert rows[41513]["status"] in ("active", "inactive")
    assert all(m["keyed"] is False for m in metas)


def test_live_rwa_family_is_keyed_by_coinmarketcap():
    """The fact that shapes the whole deployment: the RWA endpoints refuse keyless calls with
    error 1005. If this ever passes keyless, the roster leg can drop its snapshot fallback."""
    js, meta = keyless().get(
        "/v5/real-world-assets/map", {"limit": 1}, keyed=False, label="rwa/map keyless"
    )
    _skip_if_throttled(meta)
    assert meta["http"] == 403 and "1005" in (meta["error"] or "")


@pytest.mark.skipif(not api_key(), reason="needs CMC_API_KEY — the roster leg is keyed by CMC")
def test_live_keyed_roster_still_lists_the_hero_with_a_null_price():
    """1 credit. With a key, the roster leg is live: MS has a wrapper and it is priced null."""
    c = Client(api_key=api_key())
    assets, meta = c.rwa_quotes(symbol="MS")
    assert meta["error"] is None and meta["credit_count"] == 1
    ms = next(a for a in assets if a["symbol"] == "MS")
    assert ms["has_tokens"] is True and any(t["crypto_id"] == 41513 for t in ms["tokens"])
    assert os.environ.get("CMC_API_KEY", "") not in meta["url"]
