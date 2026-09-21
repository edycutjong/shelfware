"""The day-1 spike, offline: every CoinMarketCap answer is scripted, every write lands in a
temporary tree, and the verdict follows the rows rather than the script."""

import io
import json
import runpy
import sys
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from conftest import ROOT, FakeOpener, envelope

sys.path.insert(0, str(ROOT / "scripts"))
import spike  # noqa: E402

MAP_ROW = {"id": 41513, "symbol": "wMSx", "status": "untracked", "platform": {"name": "X Layer"}}


def key_info(credits_used):
    return envelope({"usage": {"current_month": {"credits_used": credits_used}}})


def keyed_script(rwa, quotes_latest, quotes_historical, map_rows=(MAP_ROW,)):
    counter = iter([100, 103])

    def answer(url):
        if "/v1/key/info" in url:
            return 200, key_info(next(counter))
        if "/cryptocurrency/map" in url:
            return 200, envelope(list(map_rows))
        if "/real-world-assets/quotes/latest" in url:
            return 200, rwa
        if "/quotes/latest" in url:
            return 200, quotes_latest
        return 200, quotes_historical

    return [answer] * 6


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(spike, "ROOT", tmp_path)
    monkeypatch.setattr(spike, "OUT", tmp_path / "docs" / "proof" / "spike.json")
    monkeypatch.delenv("CMC_API_KEY", raising=False)
    return tmp_path


@pytest.fixture
def opener(monkeypatch):
    def install(*script):
        fake = FakeOpener(*script)
        monkeypatch.setattr(urllib.request, "urlopen", fake)
        return fake

    return install


def run_main():
    out = io.StringIO()
    with redirect_stdout(out):
        code = spike.main()
    return code, out.getvalue()


def test_get_without_a_key_sends_no_key_header_and_records_the_meta(opener):
    fake = opener((200, envelope([MAP_ROW], credit_count=0)))
    js, meta = spike.get("https://x/map")
    assert js["data"] == [MAP_ROW]
    assert "X-CMC_PRO_API_KEY" not in fake.requests[0].headers
    assert meta["keyed"] is False
    assert meta["http"] == 200
    assert meta["credit_count"] == 0
    assert meta["bytes"] > 0
    assert len(meta["sha256"]) == 16
    assert meta["utc"].endswith("Z")


def test_get_with_a_key_sends_the_header(opener):
    fake = opener((200, envelope({})))
    _, meta = spike.get("https://x/info", "secret")
    assert fake.requests[0].headers["X-cmc_pro_api_key"] == "secret"
    assert meta["keyed"] is True


def test_get_keeps_an_http_error_body_and_status(opener):
    opener((401, envelope(None, credit_count=0, error_code=1002, error_message="bad key")))
    js, meta = spike.get("https://x/info", "wrong")
    assert meta["http"] == 401
    assert js["status"]["error_message"] == "bad key"


def test_get_keeps_a_non_json_body_as_raw_text(opener):
    opener((200, b"<html>Human Verification</html>"))
    js, meta = spike.get("https://x/map")
    assert js == {"_raw": "<html>Human Verification</html>"}
    assert meta["credit_count"] is None


def test_get_reports_no_credit_count_for_a_non_object_body(opener):
    opener((200, [1, 2, 3]))
    js, meta = spike.get("https://x/map")
    assert js == [1, 2, 3]
    assert meta["credit_count"] is None


def test_a_keyless_run_records_the_map_row_and_skips_the_keyed_legs(sandbox, opener):
    fake = opener((200, envelope([MAP_ROW], credit_count=0)))
    code, out = run_main()
    assert code == 0
    assert len(fake.requests) == 1
    assert "listing_status=active%2Cinactive%2Cuntracked" in fake.requests[0].full_url
    doc = json.loads((sandbox / "docs" / "proof" / "spike.json").read_text())
    f = doc["findings"]
    assert f["map_status"] == "untracked"
    assert f["map_has_dates"] is False
    assert f["map_platform"] == {"name": "X Layer"}
    assert f["keyed_calls"].startswith("skipped")
    assert "first_snapshot" not in f
    assert f["verdict"].startswith("see calls")
    assert f["time_axis"].startswith("untracked map rows carry no")
    assert list(doc["calls"]) == ["map_keyless"]
    assert "wrote docs/proof/spike.json" in out


def test_a_keyed_run_asks_all_five_questions_and_charges_the_credit_difference(
    sandbox, opener, monkeypatch
):
    monkeypatch.setenv("CMC_API_KEY", "k")
    snaps = sandbox / "data" / "snapshots"
    snaps.mkdir(parents=True)
    (snaps / "2026-09-18.json").write_text(
        json.dumps(
            {
                "generated_utc": "2026-09-18T21:36:35Z",
                "wrappers": [{"crypto_id": 41513, "status": "untracked"}],
            }
        )
    )
    (snaps / "2026-09-19.json").write_text(json.dumps({"generated_utc": "x", "wrappers": []}))
    rwa = envelope(
        {
            "rwa_assets": [
                {"symbol": "OTHER", "tokens": []},
                {
                    "symbol": "MS",
                    "has_tokens": True,
                    "rwa_rank": 43,
                    "tradfi_markets": [{"exchange": "NYSE"}],
                    "tokens": [
                        {"crypto_id": 1, "price": 9.0},
                        {"crypto_id": 41513, "price": None, "issuer_name": "Backed Assets"},
                    ],
                },
            ]
        }
    )
    latest = envelope({"41513": {"quote": {"USD": {"price": None}}}})
    historical = envelope({"quotes": []})
    fake = opener(*keyed_script(rwa, latest, historical))
    code, out = run_main()
    assert code == 0
    assert [r.headers.get("X-cmc_pro_api_key") for r in fake.requests] == [
        "k",
        None,
        "k",
        "k",
        "k",
        "k",
    ]
    doc = json.loads((sandbox / "docs" / "proof" / "spike.json").read_text())
    f = doc["findings"]
    assert f["rwa_rank"] == 43
    assert f["wrapper_issuer"] == "Backed Assets"
    assert f["wrapper_price"] is None
    assert f["quotes_latest_http"] == 200
    assert f["quotes_latest_price_usd"] is None
    assert f["quotes_historical_points"] == 0
    assert f["keyed_credits_this_spike"] == 3
    assert f["first_snapshot"] == {
        "file": "2026-09-18.json",
        "generated_utc": "2026-09-18T21:36:35Z",
        "status_then": "untracked",
        "same_status_now": True,
    }
    assert f["verdict"].startswith("listed, no CMC-tracked market")
    assert list(doc["calls"]) == [
        "key_info_before",
        "map_keyless",
        "rwa_quotes_keyed",
        "crypto_quotes_latest_keyed",
        "crypto_quotes_historical_keyed",
        "key_info_after",
    ]
    assert "tradfi_markets" not in out
    assert "keyed_credits_this_spike" in out


def test_a_keyed_run_survives_empty_rosters_and_flags_a_dated_map_row(sandbox, opener, monkeypatch):
    monkeypatch.setenv("CMC_API_KEY", "k")
    snaps = sandbox / "data" / "snapshots"
    snaps.mkdir(parents=True)
    (snaps / "2026-09-18.json").write_text(
        json.dumps({"generated_utc": "2026-09-18T21:36:35Z", "wrappers": []})
    )
    dated = {**MAP_ROW, "status": "active", "first_historical_data": "2026-09-01T00:00:00.000Z"}
    opener(
        *keyed_script(
            envelope({"rwa_assets": []}),
            envelope(None),
            envelope([]),
            map_rows=[dated],
        )
    )
    code, _ = run_main()
    assert code == 0
    f = json.loads((sandbox / "docs" / "proof" / "spike.json").read_text())["findings"]
    assert f["map_has_dates"] is True
    assert f["rwa_has_tokens"] is None
    assert f["wrapper_price"] is None
    assert f["tradfi_markets"] is None
    assert f["quotes_latest_price_usd"] is None
    assert f["quotes_historical_points"] == 0
    assert f["first_snapshot"]["status_then"] is None
    assert f["first_snapshot"]["same_status_now"] is False
    assert f["verdict"].startswith("see calls")
    assert f["time_axis"].startswith("the map row carries dates")


def test_a_keyed_run_charges_nothing_when_key_info_has_no_usage(sandbox, opener, monkeypatch):
    monkeypatch.setenv("CMC_API_KEY", "k")

    def answer(url):
        if "/cryptocurrency/map" in url:
            return 200, envelope([MAP_ROW])
        return 200, envelope({})

    opener(*[answer] * 6)
    code, _ = run_main()
    assert code == 0
    f = json.loads((sandbox / "docs" / "proof" / "spike.json").read_text())["findings"]
    assert f["keyed_credits_this_spike"] == 0


def test_a_missing_map_row_exits_nonzero(sandbox, opener):
    opener((200, envelope([{"id": 1, "symbol": "wMSx", "status": "active"}])))
    code, _ = run_main()
    assert code == 1
    f = json.loads((sandbox / "docs" / "proof" / "spike.json").read_text())["findings"]
    assert f["map_status"] is None
    assert f["map_platform"] is None


def test_a_map_reply_without_data_exits_nonzero(sandbox, opener):
    opener((200, {"status": {"credit_count": 0}}))
    code, _ = run_main()
    assert code == 1


def test_running_the_script_as_main_exits_with_its_verdict(tmp_path, opener, monkeypatch):
    real_resolve = Path.resolve

    def resolve(self, strict=False):
        if self.name == "spike.py":
            return tmp_path / "scripts" / "spike.py"
        return real_resolve(self, strict)

    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.delenv("CMC_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["spike.py"])
    opener((200, envelope([MAP_ROW], credit_count=0)))
    with redirect_stdout(io.StringIO()), pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "spike.py"), run_name="__main__")
    assert exc.value.code == 0
    assert (tmp_path / "docs" / "proof" / "spike.json").exists()
