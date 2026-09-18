"""The counting rules, on a ledger set small enough to count by eye."""

from datetime import UTC, datetime

from conftest import BACKED, DINARI, FIDELITY, NOW

from shelfware.join import (
    age_of_shelf,
    age_of_tracked,
    census,
    chains,
    counts_of,
    enrich_info,
    hero,
    is_shelf,
    recount,
    resolve,
    scorecard,
    type_bars,
    type_underlyings,
    wrappers_from,
    zero_tracked,
)


def joined(rwa_rows, quote_assets, cmc_map):
    return resolve(wrappers_from(rwa_rows, quote_assets), cmc_map)


def has_tokens(rwa_rows):
    return [r for r in rwa_rows if r["has_tokens"]]


# ── shelf ──────────────────────────────────────────────────────────────────────


def test_shelf_is_the_map_state_not_the_price(rwa_rows, quote_assets, cmc_map):
    """DEADT is priced null AND inactive. Price alone would call it shelf; the rule is CMC's
    own listing state, so it is inactive — shown, not counted as shelf."""
    ws = {w["symbol"]: w for w in joined(rwa_rows, quote_assets, cmc_map)}
    assert ws["DEADT"]["price"] is None
    assert not is_shelf(ws["DEADT"])
    assert is_shelf(ws["wMSx"])
    assert ws["wMSx"]["platform"]["name"] == "X Layer"


def test_unresolved_id_is_shown_and_never_counted_as_shelf(rwa_rows, quote_assets, cmc_map):
    """VVV -> 40784 is in tokens[] and absent from the map (live, 2026-09-18). It gets its own
    bucket; it is neither tracked nor shelf, so the loose rule says one more zero-tracked
    underlying than the strict rule and the headline takes the smaller number."""
    ws = joined(rwa_rows, quote_assets, cmc_map)
    vvv = next(w for w in ws if w["symbol"] == "VVV")
    assert vvv["status"] == "unresolved"
    strict = zero_tracked(ws, has_tokens(rwa_rows), strict=True)
    loose = zero_tracked(ws, has_tokens(rwa_rows), strict=False)
    assert 900 not in strict and 900 in loose
    assert len(strict) < len(loose)


def test_zero_tracked_strict_requires_every_wrapper_untracked(rwa_rows, quote_assets, cmc_map):
    """NVDA has one tracked wrapper beside two that are not: mixed, never zero-tracked.
    MS and APH have only untracked wrappers: zero-tracked."""
    ws = joined(rwa_rows, quote_assets, cmc_map)
    assert set(zero_tracked(ws, has_tokens(rwa_rows), strict=True)) == {35, 80}


def test_zero_tracked_strict_is_never_larger_than_loose(rwa_rows, quote_assets, cmc_map):
    ws = joined(rwa_rows, quote_assets, cmc_map)
    ht = has_tokens(rwa_rows)
    assert set(zero_tracked(ws, ht, strict=True)) <= set(zero_tracked(ws, ht, strict=False))


def test_underlying_with_only_an_inactive_wrapper_is_not_zero_tracked_strict(
    rwa_rows, quote_assets, cmc_map
):
    ws = joined(rwa_rows, quote_assets, cmc_map)
    assert 700 not in zero_tracked(ws, has_tokens(rwa_rows), strict=True)
    assert 700 in zero_tracked(ws, has_tokens(rwa_rows), strict=False)


def test_has_tokens_false_underlying_is_never_in_either_count(rwa_rows, quote_assets, cmc_map):
    ws = joined(rwa_rows, quote_assets, cmc_map)
    assert 999 not in zero_tracked(ws, has_tokens(rwa_rows), strict=False)
    c = counts_of(ws, rwa_rows, has_tokens(rwa_rows))
    assert c["has_tokens"] == 7 and c["underlyings"] == 8


# ── scorecard ──────────────────────────────────────────────────────────────────


def test_scorecard_sums_to_wrappers_and_type_bars_agree(rwa_rows, quote_assets, cmc_map, issuers):
    ws = joined(rwa_rows, quote_assets, cmc_map)
    assert sum(e["attached"] for e in scorecard(ws, issuers)) == len(ws)
    assert sum(e["attached"] for e in type_bars(ws)) == len(ws)


def test_scorecard_keeps_declared_and_attached_apart(rwa_rows, quote_assets, cmc_map, issuers):
    """Backed declares 1,176 in the registry and has 772 attached (live). Two ledgers; the
    scorecard shows both and substitutes neither."""
    row = next(
        e
        for e in scorecard(joined(rwa_rows, quote_assets, cmc_map), issuers)
        if e["issuer_id"] == BACKED
    )
    assert row["declared"] == 1176
    assert row["attached"] == 3
    assert row["tracked"] == 1 and row["untracked"] == 2
    assert row["shelf_rate"] == 0.6667


def test_registry_issuer_with_nothing_attached_still_gets_a_row(
    rwa_rows, quote_assets, cmc_map, issuers
):
    """Fidelity: 1 declared, 0 attached. The bar is empty, not missing."""
    row = next(
        e
        for e in scorecard(joined(rwa_rows, quote_assets, cmc_map), issuers)
        if e["issuer_id"] == FIDELITY
    )
    assert row["attached"] == 0 and row["declared"] == 1 and row["shelf_rate"] is None


def test_wrapper_without_issuer_id_lands_in_the_no_issuer_row(
    rwa_rows, quote_assets, cmc_map, issuers
):
    rows = scorecard(joined(rwa_rows, quote_assets, cmc_map), issuers)
    no_issuer = next(e for e in rows if e["issuer_id"] is None)
    assert no_issuer["issuer_name"] == "(no issuer)"
    assert no_issuer["attached"] == 1  # NOI
    assert next(e for e in rows if e["issuer_name"] == "NA (Derivatives)")["unresolved"] == 1


def test_live_market_cap_sums_only_tracked_wrappers(rwa_rows, quote_assets, cmc_map, issuers):
    rows = {
        e["issuer_name"]: e for e in scorecard(joined(rwa_rows, quote_assets, cmc_map), issuers)
    }
    assert rows["Backed Assets"]["live_market_cap_usd"] == 4.1e7  # NVDAX only; wMSx/wAPHx are null
    assert rows["Dinari Assets"]["live_market_cap_usd"] == 0.0
    assert rows["Dinari Assets"]["shelf_rate"] == 1.0


def test_whole_catalogue_on_the_shelf_sorts_first(rwa_rows, quote_assets, cmc_map, issuers):
    rows = scorecard(joined(rwa_rows, quote_assets, cmc_map), issuers)
    assert rows[0]["issuer_id"] == DINARI and rows[0]["shelf_rate"] == 1.0


def test_zero_percent_shelf_bar_is_all_lit_not_missing(rwa_rows, quote_assets, cmc_map):
    """Commodity: 1 attached, 0 untracked. shelf_rate must be 0.0, not None — a None renders
    as an empty bar, a 0.0 renders as a fully lit one."""
    bars = {e["asset_type"]: e for e in type_bars(joined(rwa_rows, quote_assets, cmc_map))}
    assert bars["commodity"]["shelf_rate"] == 0.0


# ── age, chains, hero ──────────────────────────────────────────────────────────


def test_age_panel_covers_only_active_wrappers_with_a_birth_date(rwa_rows, quote_assets, cmc_map):
    ws = joined(rwa_rows, quote_assets, cmc_map)
    a = age_of_tracked(ws, NOW)
    assert a["n"] == 4  # PAXG, NVDAX, NVDA deriv, NOI — not DEADT (inactive), not the shelf
    assert a["p10"] <= a["median"] <= a["p90"]
    assert a["p90"] == (NOW - datetime(2019, 9, 26, 2, 25, tzinfo=UTC)).days


def test_shelf_age_uses_date_added_over_untracked_wrappers_only(
    rwa_rows, quote_assets, cmc_map, info_rows
):
    ws = enrich_info(joined(rwa_rows, quote_assets, cmc_map), info_rows)
    a = age_of_shelf(ws, NOW)
    assert a["n"] == 4
    assert a["p10"] == (NOW - datetime(2026, 8, 11, 16, 24, 36, tzinfo=UTC)).days == 38


def test_chains_of_the_shelf_count_platform_names(rwa_rows, quote_assets, cmc_map):
    ws = joined(rwa_rows, quote_assets, cmc_map)
    assert {e["chain"]: e["wrappers"] for e in chains(w for w in ws if is_shelf(w))} == {
        "X Layer": 2,
        "Arbitrum": 2,
    }


def test_hero_rule_picks_the_lowest_rwa_rank_among_all_shelf_underlyings(
    rwa_rows, quote_assets, cmc_map
):
    h = hero(joined(rwa_rows, quote_assets, cmc_map), has_tokens(rwa_rows))
    assert h["symbol"] == "MS" and h["rwa_rank"] == 43
    assert h["runners_up"][0]["symbol"] == "APH"


def test_hero_rule_moves_on_when_the_wrapper_comes_alive(rwa_rows, quote_assets, cmc_map):
    cmc_map[41513]["status"] = "active"
    h = hero(joined(rwa_rows, quote_assets, cmc_map), has_tokens(rwa_rows))
    assert h["symbol"] == "APH"


def test_hero_is_none_when_nothing_is_on_the_shelf(rwa_rows, quote_assets, cmc_map):
    for r in cmc_map.values():
        r["status"] = "active"
    assert hero(joined(rwa_rows, quote_assets, cmc_map), has_tokens(rwa_rows)) is None


# ── the census document and its recount ───────────────────────────────────────


def test_census_counts_agree_with_a_recount_from_its_own_rows(
    rwa_rows, quote_assets, cmc_map, issuers, info_rows
):
    doc = census(rwa_rows, quote_assets, cmc_map, issuers, info=info_rows, now=NOW)
    r = recount(doc)
    for k in (
        "wrappers",
        "active",
        "untracked",
        "inactive",
        "unresolved",
        "underlyings_zero_tracked",
    ):
        assert doc["counts"][k] == r[k], k
    assert doc["counts"]["underlyings_mixed"] == 1
    assert doc["credits_used"] == 0 and doc["receipt"] == []


def test_committed_census_recounts_to_its_own_headline(committed_census):
    """data/census.json is a live run. Its counts block must be derivable from its rows."""
    r = recount(committed_census)
    c = committed_census["counts"]
    assert r["underlyings_zero_tracked"] == c["underlyings_zero_tracked"]
    assert r["untracked"] == c["untracked"] and r["wrappers"] == c["wrappers"]
    assert c["underlyings_zero_tracked"] <= c["has_tokens"]


def test_price_null_iff_untracked_holds_on_the_committed_census(committed_census):
    """I1, verified live 2026-09-18 with 0 exceptions. If CMC ever prices an untracked wrapper
    or nulls a tracked one, this is the test that says so."""
    assert recount(committed_census)["price_null_iff_untracked_exceptions"] == 0


def test_every_committed_wrapper_is_resolved_or_reported(committed_census):
    unresolved = {
        w["crypto_id"] for w in committed_census["wrappers"] if w["status"] == "unresolved"
    }
    assert unresolved == {u["crypto_id"] for u in committed_census["unresolved"]}
    assert all(
        w["status"] in ("active", "untracked", "inactive", "unresolved")
        for w in committed_census["wrappers"]
    )


def test_committed_scorecard_sums_to_the_wrapper_count(committed_census):
    c = committed_census["counts"]
    assert sum(e["attached"] for e in committed_census["by_issuer"]) == c["wrappers"]
    assert sum(e["attached"] for e in committed_census["by_type"]) == c["wrappers"]
    assert c["active"] + c["untracked"] + c["inactive"] + c["unresolved"] == c["wrappers"]


def test_headline_split_by_type_counts_underlyings_not_wrappers(rwa_rows, quote_assets, cmc_map):
    """NVDA has three wrappers and counts once; MS and APH are the two all-shelf stocks."""
    rows = {e["asset_type"]: e for e in type_underlyings(joined(rwa_rows, quote_assets, cmc_map))}
    assert rows["stock"]["underlyings"] == 5 and rows["stock"]["zero_tracked"] == 2
    assert rows["commodity"] == {
        "asset_type": "commodity",
        "underlyings": 1,
        "zero_tracked": 0,
        "share": 0.0,
    }


def test_headline_split_by_type_sums_to_the_headline_on_the_committed_census(committed_census):
    rows = type_underlyings(committed_census["wrappers"])
    assert (
        sum(e["zero_tracked"] for e in rows)
        == committed_census["counts"]["underlyings_zero_tracked"]
    )
    assert sum(e["underlyings"] for e in rows) == committed_census["counts"]["has_tokens"]
