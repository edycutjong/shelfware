"""The one GET, exercised without the network. Regression tests are named for the defect
they pin, with the date it was seen against the live API."""

import json

import pytest
from conftest import FakeOpener, envelope

from shelfware import client as C
from shelfware.client import Client, NoKey, api_key, credits_used


def noop_sleep(_):
    pass


def make(*script, key=None):
    op = FakeOpener(*script)
    return Client(api_key=key, sleep=noop_sleep, opener=op), op


# ── credential boundary ────────────────────────────────────────────────────────


def test_keyless_call_never_sends_the_key_even_when_one_is_exported():
    """The status leg must be live for anyone at 0 credits — so a keyless call carries no
    key even when the process has one, and goes to /public-api, never the Pro base."""
    c, op = make((200, envelope([])), key="secret-key")
    _, meta = c.get("/v1/cryptocurrency/map", {"symbol": "wMSx"}, keyed=False)
    req = op.requests[0]
    assert req.get_header("X-cmc_pro_api_key") is None
    assert req.full_url.startswith(C.KEYLESS_BASE)
    assert meta["keyed"] is False and "secret-key" not in json.dumps(meta)


def test_keyed_call_sends_the_pro_header_to_the_keyed_base():
    c, op = make((200, envelope({"rwa_assets": []})), key="k123")
    c.get("/v5/real-world-assets/map", keyed=True)
    req = op.requests[0]
    assert req.get_header("X-cmc_pro_api_key") == "k123"
    assert req.full_url.startswith(C.KEYED_BASE + "/v5/")


def test_keyed_call_without_a_key_refuses_before_touching_the_network():
    c, op = make()
    with pytest.raises(NoKey):
        c.get("/v5/real-world-assets/map", keyed=True)
    assert op.requests == []


def test_a_blank_key_variable_is_no_key(monkeypatch):
    for var in C.KEY_VARS:
        monkeypatch.setenv(var, "   ")
    assert api_key() is None
    monkeypatch.setenv("CMC_API_KEY", " abc ")
    assert api_key() == "abc"


# ── failure handling ───────────────────────────────────────────────────────────


def test_transient_status_is_retried_with_backoff_then_reported_throttled():
    sleeps = []
    op = FakeOpener(
        (429, envelope(None, error_code=1022, error_message="limit")),
        (500, b"busy"),
        (200, envelope([1])),
    )
    c = Client(sleep=sleeps.append, opener=op)
    js, meta = c.get("/v1/cryptocurrency/map", keyed=False)
    assert js["data"] == [1] and meta["error"] is None and meta["attempts"] == 3
    assert sleeps == [2, 4]


def test_exhausted_throttle_is_returned_as_throttled_never_raised():
    op = FakeOpener(*[(429, envelope(None, error_code=1022, error_message="too many"))] * C.RETRIES)
    c = Client(sleep=noop_sleep, opener=op)
    _, meta = c.get("/v1/cryptocurrency/map", keyed=False)
    assert meta["throttled"] is True and meta["http"] == 429
    assert "error_code 1022" in meta["error"] and "transient" in meta["error"]


def test_a_400_is_returned_immediately_and_described_by_cmc_message():
    op = FakeOpener(
        (400, envelope(None, error_code=400, error_message='Invalid value for "symbol": "BNVDA"'))
    )
    c = Client(sleep=noop_sleep, opener=op)
    _, meta = c.get("/v1/cryptocurrency/map", keyed=False)
    assert meta["attempts"] == 1 and meta["http"] == 400
    assert meta["error"] == 'HTTP 400 error_code 400: Invalid value for "symbol": "BNVDA"'


def test_malformed_json_is_an_error_not_a_number():
    c, _ = make((200, b"<html>Human Verification</html>"))
    js, meta = c.get("/v1/cryptocurrency/map", keyed=False)
    assert js == {} and "not JSON" in meta["error"]


def test_a_dropped_connection_is_retried_as_congestion_not_raised_as_a_traceback():
    import urllib.error

    calls = {"n": 0}

    def flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError("connection reset")
        return FakeOpener((200, envelope([7])))(req)

    c = Client(sleep=noop_sleep, opener=flaky)
    js, meta = c.get("/v1/cryptocurrency/map", keyed=False)
    assert js["data"] == [7] and meta["attempts"] == 2


# ── the receipt ────────────────────────────────────────────────────────────────


def test_receipt_records_credit_count_sha256_bytes_and_utc():
    c, _ = make((200, envelope([1, 2], credit_count=3)))
    _, meta = c.get("/v1/cryptocurrency/map", keyed=False, label="x")
    assert meta["credit_count"] == 3 and meta["bytes"] > 0 and len(meta["sha256"]) == 16
    assert meta["utc"].endswith("Z") and c.receipt == [meta] and meta["call"] == "x"


def test_credits_used_sums_keyed_calls_only():
    """The keyless envelope also says credit_count: 1 (observed on every keyless call), but
    nothing is charged to any key. The sum is over keyed calls."""
    receipt = [
        {"keyed": False, "credit_count": 1},
        {"keyed": True, "credit_count": 1},
        {"keyed": True, "credit_count": 0},
        {"keyed": True, "credit_count": None},
    ]
    assert credits_used(receipt) == 1


# ── the symbol filter ──────────────────────────────────────────────────────────


def test_dotted_symbols_are_never_sent_to_the_map_filter():
    """NVDA.D, live 2026-09-18: the map's symbol filter takes alphanumerics only and rejects
    the WHOLE call with HTTP 400. CMC assigns dotted symbols to 38 of its own RWA wrappers."""
    c, op = make((200, envelope([{"id": 36992, "status": "active"}])))
    rows, meta, dropped = c.cmc_map(["NVDAX", "NVDA.D", "AI.FRx"])
    assert dropped == ["NVDA.D", "AI.FRx"]
    assert "symbol=NVDAX&" in op.requests[0].full_url and "NVDA.D" not in op.requests[0].full_url
    assert rows[36992]["status"] == "active"


def test_a_symbol_the_map_rejects_is_dropped_and_the_call_retried():
    """BNVDA, live 2026-09-18: an unknown symbol 400s the whole call. Drop it, retry once."""
    c, op = make(
        (400, envelope(None, error_code=400, error_message='Invalid value for "symbol": "BNVDA"')),
        (200, envelope([{"id": 41513, "status": "untracked"}])),
    )
    rows, meta, dropped = c.cmc_map(["wMSx", "BNVDA"])
    assert dropped == ["BNVDA"] and rows[41513]["status"] == "untracked"
    assert len(op.requests) == 2 and "BNVDA" not in op.requests[1].full_url


def test_only_dotted_symbols_means_no_call_at_all():
    c, op = make()
    rows, meta, dropped = c.cmc_map(["NVDA.D"])
    assert rows == {} and meta is None and dropped == ["NVDA.D"] and op.requests == []


def test_full_map_paging_stops_on_a_short_page():
    page1 = [{"id": i, "status": "active"} for i in range(C.CMC_MAP_PAGE)]
    page2 = [{"id": 99999, "status": "untracked"}]
    c, op = make((200, envelope(page1)), (200, envelope(page2)))
    rows, meta, _ = c.cmc_map()
    assert len(rows) == C.CMC_MAP_PAGE + 1 and len(op.requests) == 2
    assert "start=5001" in op.requests[1].full_url


# ── the info leg ───────────────────────────────────────────────────────────────


def test_info_drops_the_ids_cmc_names_in_its_400_and_retries():
    """39318 etc., live 2026-09-18: an unknown id 400s the whole call and the message lists
    every bad id at once. Drop them all, retry once."""
    c, op = make(
        (
            400,
            envelope(None, error_code=400, error_message="Invalid value for 'id': '39318,39002'"),
        ),
        (
            200,
            envelope(
                {
                    "41513": {
                        "id": 41513,
                        "status": "inactive",
                        "date_added": "2026-08-11T16:24:36.000Z",
                    }
                }
            ),
        ),
    )
    rows, metas, dropped = c.cmc_info([41513, 39318, 39002])
    assert dropped == [39002, 39318] and rows[41513]["date_added"].startswith("2026-08-11")
    assert len(op.requests) == 2 and "39318" not in op.requests[1].full_url


def test_info_batches_two_hundred_ids_per_keyless_call():
    c, op = make((200, envelope({})), (200, envelope({})))
    c.cmc_info(range(1, 402))
    assert len(op.requests) == 3
    assert op.requests[0].full_url.startswith(C.KEYLESS_BASE + "/v2/cryptocurrency/info")


# ── the ledgers ────────────────────────────────────────────────────────────────


def test_rwa_map_follows_has_more_and_costs_nothing():
    c, op = make(
        (200, envelope({"rwa_assets": [{"rwa_id": 1}], "has_more": True}, credit_count=0)),
        (200, envelope({"rwa_assets": [{"rwa_id": 2}], "has_more": False}, credit_count=0)),
        key="k",
    )
    rows = c.rwa_map()
    assert [r["rwa_id"] for r in rows] == [1, 2] and credits_used(c.receipt) == 0
    assert "start=251" in op.requests[1].full_url


def test_rwa_quotes_batches_two_hundred_ids_and_keeps_null_price_rows():
    tokens = [{"crypto_id": 41513, "symbol": "wMSx", "price": None}]
    c, op = make(
        (200, envelope({"rwa_assets": [{"rwa_id": 35, "tokens": tokens}]})),
        (200, envelope({"rwa_assets": []})),
        key="k",
    )
    assets, _ = c.rwa_quotes(rwa_ids=range(1, 202))
    assert len(op.requests) == 2 and assets[0]["tokens"][0]["price"] is None
    assert "skip_invalid=true" in op.requests[0].full_url


def test_a_failed_ledger_call_raises_with_cmc_message_not_an_empty_universe():
    c, _ = make((403, envelope(None, error_code=1006, error_message="plan")), key="k")
    with pytest.raises(RuntimeError, match="error_code 1006"):
        c.issuers()


def test_an_error_body_without_cmcs_status_block_is_described_by_its_http_code_alone():
    assert C.describe_error([], 502) == "HTTP 502"
    assert C.describe_error({"status": {"error_code": 0}}, 404) == "HTTP 404"


def test_a_failed_rwa_map_or_quotes_page_raises_rather_than_returning_a_short_universe():
    refused = (403, envelope(None, error_code=1006, error_message="plan"))
    c, _ = make(refused, key="k")
    with pytest.raises(RuntimeError, match="rwa/map failed: .*error_code 1006"):
        c.rwa_map()
    c, _ = make(refused, key="k")
    with pytest.raises(RuntimeError, match="rwa/quotes failed: .*error_code 1006"):
        c.rwa_quotes(rwa_ids=["35"])


def test_a_400_naming_a_symbol_that_was_never_sent_stops_the_map_retry_loop():
    c, op = make(
        (400, envelope(None, error_code=400, error_message='Invalid value for "symbol": "ZZZ"')),
    )
    rows, meta, dropped = c.cmc_map(["wMSx"])
    assert rows == {} and dropped == [] and meta["http"] == 400 and len(op.requests) == 1


def test_a_400_naming_ids_that_were_never_sent_stops_the_info_retry_loop():
    c, op = make(
        (400, envelope(None, error_code=400, error_message="Invalid value for 'id': '1,2'")),
    )
    rows, metas, dropped = c.cmc_info([41513])
    assert rows == {} and dropped == [] and len(metas) == 1 and len(op.requests) == 1


def test_a_batch_whose_every_id_cmc_rejects_is_not_retried_empty():
    c, op = make(
        (400, envelope(None, error_code=400, error_message="Invalid value for 'id': '41513'")),
    )
    rows, metas, dropped = c.cmc_info([41513])
    assert rows == {} and dropped == [41513] and len(op.requests) == 1


def test_key_info_is_none_without_a_key_or_when_the_ledger_call_fails():
    c, op = make()
    assert c.key_info() is None and op.requests == []
    c, _ = make((403, envelope(None, error_code=1006, error_message="plan")), key="k")
    assert c.key_info() is None


def test_a_json_list_body_carries_no_credit_count_and_is_still_a_usable_answer():
    c, _ = make((200, []))
    js, meta = c.get("/v1/cryptocurrency/map")
    assert js == [] and meta["error"] is None and meta["credit_count"] is None


def test_every_symbol_rejected_one_by_one_ends_with_no_call_left_to_make():
    def reject(sym):
        return (
            400,
            envelope(None, error_code=400, error_message=f'Invalid value for "symbol": "{sym}"'),
        )

    c, op = make(reject("AAA"), reject("BBB"))
    rows, meta, dropped = c.cmc_map(["AAA", "BBB"])
    assert rows == {} and dropped == ["AAA", "BBB"] and meta["http"] == 400
    assert len(op.requests) == 2


def test_info_gives_up_on_a_batch_after_three_rounds_of_rejected_ids():
    def reject(i):
        return (400, envelope(None, error_code=400, error_message=f"Invalid value for 'id': '{i}'"))

    c, op = make(reject(1), reject(2), reject(3))
    rows, metas, dropped = c.cmc_info([1, 2, 3, 4])
    assert rows == {} and dropped == [1, 2, 3] and len(metas) == 3 and len(op.requests) == 3
