"""One property-based verification of the join over its whole input space.

Coverage says the lines ran. This says that across PROPERTY_CASES generated ledgers, the
counting rules never violated the six invariants the METHOD doc publishes:

    I1  price is None  <=>  status == untracked, for every resolved wrapper (when the
        generator honours it — it is a fact about CMC's data the census checks, not a rule)
    I2  every wrapper is active, untracked, inactive or unresolved — never a fifth thing
    I3  strict zero-tracked <= loose zero-tracked <= has_tokens, and every strict one has a wrapper
    I4  Σ by_issuer.attached == wrappers == Σ by_type.attached
    I5  the census's counts block equals a recount from its own rows
    I6  unresolved wrappers are never counted as shelf anywhere
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from shelfware.join import census, is_shelf, recount, zero_tracked

PROPERTY_CASES = 500  # published in README.md and DEMO.md — keep in sync
STATUS = st.sampled_from(["active", "untracked", "inactive", None])  # None = absent from the map


@st.composite
def ledgers(draw):
    n_under = draw(st.integers(1, 8))
    rwa = [
        {
            "rwa_id": i,
            "symbol": f"U{i}",
            "name": f"Under {i}",
            "asset_type": draw(st.sampled_from(["stock", "etf", "commodity"])),
            "rwa_rank": i,
            "has_tokens": draw(st.booleans()),
        }
        for i in range(1, n_under + 1)
    ]
    issuers = [
        {"issuer_id": f"iss{k}", "name": f"Issuer {k}", "num_tokens": draw(st.integers(0, 50))}
        for k in range(3)
    ]
    assets, cmc, next_id = [], {}, 1000
    for r in rwa:
        if not r["has_tokens"]:
            continue
        toks = []
        for _ in range(draw(st.integers(0, 4))):
            next_id += 1
            status = draw(STATUS)
            price = None if status in ("untracked", None) else draw(st.floats(0.01, 1e4))
            if status == "inactive":
                price = draw(st.one_of(st.none(), st.floats(0.01, 1e4)))
            toks.append(
                {
                    "crypto_id": next_id,
                    "symbol": f"W{next_id}",
                    "name": "w",
                    "issuer_id": draw(st.sampled_from(["iss0", "iss1", None])),
                    "issuer_name": None,
                    "price": price,
                    "market_cap": None if price is None else price * 10,
                    "volume_24h": None,
                }
            )
            if status is not None:
                cmc[next_id] = {
                    "id": next_id,
                    "status": status,
                    "first_historical_data": "2025-01-01T00:00:00.000Z"
                    if status == "active"
                    else None,
                }
        assets.append({**r, "tokens": toks})
    return rwa, assets, cmc, issuers


@settings(max_examples=PROPERTY_CASES, deadline=None)
@given(ledgers())
def test_join_invariants_hold_over_the_whole_input_space(ledger):
    rwa, assets, cmc, issuers = ledger
    doc = census(rwa, assets, cmc, issuers)
    ws, c = doc["wrappers"], doc["counts"]
    has_tokens = [r for r in rwa if r["has_tokens"]]
    # I1 — the generator honours it for resolved rows, so the recount must see zero exceptions
    assert recount(doc)["price_null_iff_untracked_exceptions"] == 0
    # I2
    assert all(w["status"] in ("active", "untracked", "inactive", "unresolved") for w in ws)
    assert (
        c["active"] + c["untracked"] + c["inactive"] + c["unresolved"] == c["wrappers"] == len(ws)
    )
    # I3
    strict, loose = zero_tracked(ws, has_tokens, True), zero_tracked(ws, has_tokens, False)
    assert set(strict) <= set(loose)
    assert (
        c["underlyings_zero_tracked"]
        == len(strict)
        <= c["underlyings_zero_tracked_loose"]
        == len(loose)
        <= c["has_tokens"]
    )
    attached = {w["rwa_id"] for w in ws}
    assert all(i in attached for i in strict)
    # I4
    assert (
        sum(e["attached"] for e in doc["by_issuer"])
        == len(ws)
        == sum(e["attached"] for e in doc["by_type"])
    )
    # I5
    r = recount(doc)
    for k in (
        "wrappers",
        "active",
        "untracked",
        "inactive",
        "unresolved",
        "underlyings_zero_tracked",
    ):
        assert c[k] == r[k], k
    # I6
    assert not any(is_shelf(w) for w in ws if w["status"] == "unresolved")
    assert sum(e["untracked"] for e in doc["by_issuer"]) == c["untracked"]
    assert all(
        e["unresolved"] == 0 or e["untracked"] <= e["attached"] - e["unresolved"]
        for e in doc["by_issuer"]
    )
    # the hero, when there is one, is a strict zero-tracked underlying with the lowest rank
    if doc["hero"]:
        assert doc["hero"]["rwa_id"] in strict
        assert doc["hero"]["rwa_rank"] == min(
            r["rwa_rank"] for r in has_tokens if r["rwa_id"] in strict
        )
