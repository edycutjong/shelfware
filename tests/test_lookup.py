"""The ticker question, both legs, with a scripted client."""

from conftest import BACKED, DINARI, FakeOpener, envelope

from shelfware.client import Client
from shelfware.lookup import lookup, roster_snapshot_from


def noop(_):
    pass


MS_ASSET = {
    "rwa_id": 35,
    "symbol": "MS",
    "name": "Morgan Stanley",
    "asset_type": "stock",
    "rwa_rank": 43,
    "has_tokens": True,
    "tokens": [
        {
            "crypto_id": 41513,
            "symbol": "wMSx",
            "name": "Wrapped MS",
            "issuer_id": BACKED,
            "issuer_name": "Backed Assets",
            "price": None,
            "market_cap": None,
            "volume_24h": None,
        }
    ],
}
MS_MAP_ROW = {
    "id": 41513,
    "symbol": "wMSx",
    "status": "untracked",
    "platform": {"name": "X Layer", "token_address": "0x2874"},
}
MS_INFO = {
    "41513": {
        "id": 41513,
        "symbol": "wMSx",
        "status": "inactive",
        "date_added": "2026-08-11T16:24:36.000Z",
    }
}


def snapshot():
    doc = {
        "generated_utc": "2026-09-18T22:09:08Z",
        "wrappers": [
            {
                "crypto_id": 41513,
                "symbol": "wMSx",
                "name": "Wrapped MS",
                "rwa_id": 35,
                "underlying": "MS",
                "underlying_name": "Morgan Stanley",
                "asset_type": "stock",
                "rwa_rank": 43,
                "issuer_id": BACKED,
                "issuer_name": "Backed Assets",
                "price": None,
                "market_cap": None,
                "volume_24h": None,
                "status": "untracked",
                "first_historical_data": None,
                "date_added": "2026-08-11T16:24:36.000Z",
                "platform": {"name": "X Layer", "token_address": "0x2874"},
            },
            {
                "crypto_id": 28616,
                "symbol": "NVDA.D",
                "name": "NVDA Dinari",
                "rwa_id": 2,
                "underlying": "NVDA",
                "underlying_name": "Nvidia",
                "asset_type": "stock",
                "rwa_rank": 2,
                "issuer_id": DINARI,
                "issuer_name": "Dinari Assets",
                "price": None,
                "market_cap": None,
                "volume_24h": None,
                "status": "untracked",
                "first_historical_data": None,
                "date_added": "2023-12-07T10:41:41.000Z",
                "platform": {"name": "Arbitrum", "token_address": "0x4DaF"},
            },
            {
                "crypto_id": 36992,
                "symbol": "NVDAX",
                "name": "NVDA xStock",
                "rwa_id": 2,
                "underlying": "NVDA",
                "underlying_name": "Nvidia",
                "asset_type": "stock",
                "rwa_rank": 2,
                "issuer_id": BACKED,
                "issuer_name": "Backed Assets",
                "price": 222.0,
                "market_cap": 4.1e7,
                "volume_24h": 1.0,
                "status": "active",
                "first_historical_data": "2025-06-28T20:05:00.000Z",
                "date_added": None,
                "platform": {"name": "Solana", "token_address": "Xsc9"},
            },
        ],
    }
    return roster_snapshot_from(
        doc,
        [
            {
                "rwa_id": 999,
                "symbol": "XYZ",
                "name": "Untokenised",
                "asset_type": "stock",
                "rwa_rank": 999,
                "has_tokens": False,
            }
        ],
    )


def test_roster_snapshot_indexes_by_underlying_and_keeps_the_no_tokens_symbols():
    s = snapshot()
    assert s["as_of"] == "2026-09-18T22:09:08Z"
    assert [t["symbol"] for t in s["underlyings"]["NVDA"]["tokens"]] == ["NVDA.D", "NVDAX"]
    assert s["no_tokens"]["XYZ"][1] == "Untokenised"


def test_no_key_roster_comes_from_the_snapshot_and_the_status_is_live():
    op = FakeOpener((200, envelope([MS_MAP_ROW])), (200, envelope(MS_INFO)))
    res = lookup("ms", Client(api_key=None, sleep=noop, opener=op), snapshot())
    assert res["roster"]["source"] == "snapshot" and res["roster"]["as_of"].startswith("2026-09-18")
    assert res["status"]["source"] == "live keyless"
    assert (
        res["wrappers"][0]["status"] == "untracked" and res["wrappers"][0]["status_source"] == "map"
    )
    assert res["wrappers"][0]["date_added"].startswith("2026-08-11")
    assert res["verdict"] == "0 of 1 wrapper(s) with a CMC-tracked market"
    assert len(op.requests) == 2 and all(
        r.get_header("X-cmc_pro_api_key") is None for r in op.requests
    )


def test_with_a_key_the_roster_is_live_and_the_status_leg_is_still_keyless():
    op = FakeOpener(
        (200, envelope({"rwa_assets": [MS_ASSET]}, credit_count=1)),
        (200, envelope([MS_MAP_ROW])),
        (200, envelope(MS_INFO)),
    )
    res = lookup("MS", Client(api_key="k", sleep=noop, opener=op), snapshot())
    assert res["roster"]["source"] == "live" and res["roster"]["call"]["credit_count"] == 1
    assert op.requests[0].get_header("X-cmc_pro_api_key") == "k"
    assert op.requests[1].get_header("X-cmc_pro_api_key") is None
    assert op.requests[2].get_header("X-cmc_pro_api_key") is None
    assert res["evidence"]["tokens"] == MS_ASSET["tokens"] and res["evidence"]["map_rows"] == [
        MS_MAP_ROW
    ]


def test_unknown_ticker_is_reported_as_absent_not_as_zero_wrappers():
    res = lookup("ZZZZ", Client(sleep=noop, opener=FakeOpener()), snapshot())
    assert res["underlyings"] == [] and res["wrappers"] == []
    assert res["verdict"] == "CoinMarketCap's RWA map has no underlying ZZZZ"


def test_live_400_on_an_unknown_ticker_is_an_absence_not_a_fallback():
    op = FakeOpener(
        (400, envelope(None, error_code=400, error_message='Invalid value for "symbol": "ZZZZ"'))
    )
    res = lookup("ZZZZ", Client(api_key="k", sleep=noop, opener=op), snapshot())
    assert res["roster"]["source"] == "live" and res["roster"]["fallback_reason"] is None
    assert "no underlying ZZZZ" in res["verdict"]


def test_has_tokens_false_underlying_reports_zero_wrappers_listed():
    res = lookup("xyz", Client(sleep=noop, opener=FakeOpener()), snapshot())
    assert res["underlyings"][0]["has_tokens"] is False
    assert res["verdict"] == "XYZ is in the RWA map with has_tokens: false — 0 wrappers listed"


def test_dotted_symbol_wrapper_takes_its_state_from_info_plus_snapshot():
    """NVDA.D, live 2026-09-18. The map filter rejects the symbol, so the map leg answers for
    NVDAX only; the info leg says NVDA.D is inactive (its coarse vocabulary) and the committed
    snapshot supplies the map's finer state, untracked. Both sources are named on the row."""
    op = FakeOpener(
        (
            200,
            envelope(
                [
                    {
                        "id": 36992,
                        "symbol": "NVDAX",
                        "status": "active",
                        "first_historical_data": "2025-06-28T20:05:00.000Z",
                        "platform": {"name": "Solana", "token_address": "Xsc9"},
                    }
                ]
            ),
        ),
        (
            200,
            envelope(
                {
                    "28616": {
                        "id": 28616,
                        "status": "inactive",
                        "date_added": "2023-12-07T10:41:41.000Z",
                        "platform": {"name": "Arbitrum", "token_address": "0x4DaF"},
                    },
                    "36992": {"id": 36992, "status": "active"},
                }
            ),
        ),
    )
    res = lookup("NVDA", Client(sleep=noop, opener=op), snapshot())
    ws = {w["symbol"]: w for w in res["wrappers"]}
    assert res["status"]["dropped_symbols"] == ["NVDA.D"]
    assert ws["NVDAX"]["status"] == "active" and ws["NVDAX"]["status_source"] == "map"
    assert (
        ws["NVDA.D"]["status"] == "untracked" and ws["NVDA.D"]["status_source"] == "info+snapshot"
    )
    assert ws["NVDA.D"]["platform"]["name"] == "Arbitrum"
    assert res["verdict"] == "1 of 2 wrapper(s) with a CMC-tracked market"


def test_dotted_symbol_wrapper_that_info_calls_active_is_tracked_live():
    op = FakeOpener(
        (
            200,
            envelope(
                {
                    "28616": {
                        "id": 28616,
                        "status": "active",
                        "date_added": "2023-12-07T10:41:41.000Z",
                    }
                }
            ),
        )
    )
    snap = snapshot()
    snap["underlyings"]["NVDA"]["tokens"] = [
        t for t in snap["underlyings"]["NVDA"]["tokens"] if t["symbol"] == "NVDA.D"
    ]
    res = lookup("NVDA", Client(sleep=noop, opener=op), snap)
    assert (
        res["wrappers"][0]["status"] == "active" and res["wrappers"][0]["status_source"] == "info"
    )
    assert len(op.requests) == 1  # no map call: nothing filterable


def test_pool_exhausted_falls_back_to_snapshot_status_and_flags_temporary_failure():
    throttle = (429, envelope(None, error_code=1022, error_message="limit"))
    op = FakeOpener(throttle, throttle, throttle, throttle, (200, envelope(MS_INFO)))
    res = lookup("MS", Client(sleep=noop, opener=op), snapshot())
    assert res["status"]["source"] == "snapshot" and res["temporary_failure"] is True
    assert (
        res["wrappers"][0]["status"] == "untracked"
        and res["wrappers"][0]["status_source"] == "snapshot"
    )
    assert "error_code 1022" in res["status"]["fallback_reason"]


def test_keyed_roster_failure_falls_back_to_the_snapshot_and_says_why():
    op = FakeOpener(
        (403, envelope(None, error_code=1006, error_message="plan")),
        (200, envelope([MS_MAP_ROW])),
        (200, envelope(MS_INFO)),
    )
    res = lookup("MS", Client(api_key="k", sleep=noop, opener=op), snapshot())
    assert (
        res["roster"]["source"] == "snapshot"
        and "error_code 1006" in res["roster"]["fallback_reason"]
    )
    assert res["status"]["source"] == "live keyless"


def test_verdict_counts_active_wrappers_only():
    op = FakeOpener(
        (200, envelope([{"id": 36992, "symbol": "NVDAX", "status": "active"}])),
        (
            200,
            envelope(
                {
                    "28616": {"id": 28616, "status": "inactive"},
                    "36992": {"id": 36992, "status": "active"},
                }
            ),
        ),
    )
    res = lookup("NVDA", Client(sleep=noop, opener=op), snapshot())
    assert res["tracked"] == 1 and res["attached"] == 2


def test_exhausted_pool_with_a_key_retries_the_identical_call_keyed_and_says_so():
    """Observed on the first production deploy, 2026-09-18: from a shared cloud egress IP the
    anonymous pool answers 429 error 1022 for good. With a key the same call is repeated on the
    keyed base (1 credit) and the answer names the escape hatch; without one, the snapshot."""
    throttle = (429, envelope(None, error_code=1022, error_message="limit for anonymous access"))
    op = FakeOpener(
        (200, envelope({"rwa_assets": [MS_ASSET]}, credit_count=1)),  # roster, keyed
        throttle,
        throttle,
        throttle,
        throttle,  # keyless map, exhausted
        (200, envelope([MS_MAP_ROW], credit_count=1)),  # the same call, keyed
        (200, envelope(MS_INFO, credit_count=1)),  # info, keyed from the start now
    )
    res = lookup("MS", Client(api_key="k", sleep=noop, opener=op), snapshot())
    assert res["status"]["base"] == "keyed" and "1022" in res["status"]["keyless_error"]
    assert (
        res["status"]["source"] == "live keyless" or res["status"]["source"]
    )  # the leg answered live
    assert (
        res["wrappers"][0]["status"] == "untracked" and res["wrappers"][0]["status_source"] == "map"
    )
    assert res["temporary_failure"] is False
    keyed_calls = [r for r in op.requests if r.get_header("X-cmc_pro_api_key")]
    assert len(keyed_calls) == 3 and all("/public-api/" not in r.full_url for r in keyed_calls)


def test_a_wrapper_the_info_leg_does_not_know_either_is_unresolved():
    """The map filter rejects the symbol and info returns no row for its id: CMC has no state
    for it at all. It is unresolved, and it is not counted as shelf."""
    op = FakeOpener((200, envelope({})))
    snap = snapshot()
    snap["underlyings"]["NVDA"]["tokens"] = [
        t for t in snap["underlyings"]["NVDA"]["tokens"] if t["symbol"] == "NVDA.D"
    ]
    res = lookup("NVDA", Client(sleep=noop, opener=op), snap)
    w = res["wrappers"][0]
    assert w["status"] == "unresolved" and w["status_source"] == "info"
    assert res["verdict"] == "0 of 1 wrapper(s) with a CMC-tracked market"


def test_an_exhausted_pool_on_the_info_leg_alone_is_retried_keyed_when_a_key_is_there():
    throttle = (429, envelope(None, error_code=1022, error_message="limit for anonymous access"))
    op = FakeOpener(
        (200, envelope({"rwa_assets": [MS_ASSET]}, credit_count=1)),  # roster, keyed
        (200, envelope([MS_MAP_ROW])),  # keyless map answered
        throttle,
        throttle,
        throttle,
        throttle,  # keyless info, exhausted
        (200, envelope(MS_INFO, credit_count=1)),  # the same call, keyed
    )
    res = lookup("MS", Client(api_key="k", sleep=noop, opener=op), snapshot())
    assert res["status"]["base"] == "keyless" and "1022" in res["status"]["keyless_error"]
    assert res["status"]["info_calls"][-1]["keyed"] is True
    assert res["wrappers"][0]["date_added"].startswith("2026-08-11")
    assert res["temporary_failure"] is False
