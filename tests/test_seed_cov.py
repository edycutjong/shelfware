"""seed.py, offline end to end: the selector's ordering rules, the provenance stamp, the key
gate, and the full capture run against a scripted client writing into a temp seed dir."""

import json
import runpy
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import seed  # noqa: E402


def wrapper(crypto_id, symbol, underlying, rwa_id, rwa_rank, status="untracked"):
    return {
        "crypto_id": crypto_id,
        "symbol": symbol,
        "underlying": underlying,
        "underlying_name": f"{underlying} Inc",
        "rwa_id": rwa_id,
        "rwa_rank": rwa_rank,
        "issuer_id": "iss",
        "issuer_name": "Issuer",
        "status": status,
        "price": None if status == "untracked" else 1.0,
        "market_cap": None if status == "untracked" else 5.0,
        "asset_type": "stock",
    }


def meta(call, url, keyed=True, credit_count=1):
    return {
        "call": call,
        "url": url,
        "utc": "2026-09-19T00:00:00Z",
        "http": 200,
        "keyed": keyed,
        "credit_count": credit_count,
        "sha256": "deadbeef",
    }


@pytest.fixture
def small_doc():
    ws = [
        wrapper(1, "wMSx", "MS", 35, 43),
        wrapper(2, "wGILDx", "GILD", 36, 50),
        wrapper(3, "wZZZx", "ZZZ", 37, 60),
        wrapper(4, "ZZZ.D", "ZZZ", 37, 60),
        wrapper(5, "wAAAx", "AAA", 38, 70),
        wrapper(6, "wBBBx", "BBB", 39, 80, status="active"),
    ]
    return {
        "wrappers": ws,
        "hero": {
            "runners_up": [
                {"symbol": "GILD", "rwa_rank": 50},
                {"symbol": "ZZZ", "rwa_rank": 60},
                {"symbol": "GHOST", "rwa_rank": 99},
            ]
        },
    }


@pytest.fixture
def seed_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "SEED", tmp_path / "seed")
    return tmp_path / "seed"


class ScriptedClient:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.receipt = []
        self.quotes_asked = None
        self.map_asked = None
        self.info_asked = None

    def rwa_map(self):
        self.receipt.append(meta("rwa/map?start=1", "https://k/rwa/map?start=1", credit_count=0))
        self.receipt.append(meta("rwa/map?start=2", "https://k/rwa/map?start=2", credit_count=0))
        tokens = [{"rwa_id": i, "symbol": f"T{i}", "has_tokens": True} for i in (35, 36, 37)]
        controls = [{"rwa_id": 100 + i, "symbol": f"C{i}", "has_tokens": False} for i in range(25)]
        return tokens + controls

    def rwa_quotes(self, rwa_ids=None, symbol=None):
        self.quotes_asked = rwa_ids
        self.receipt.append(meta("rwa/quotes", "https://k/rwa/quotes?id=35,36"))
        assets = [
            {"rwa_id": 35, "tokens": [{"crypto_id": 1, "symbol": "wMSx"}]},
            {"rwa_id": 36, "tokens": [{"crypto_id": 2, "symbol": "wGILDx"}, {"crypto_id": 9}]},
            {"rwa_id": 37, "tokens": None},
        ]
        return assets, {}

    def issuers(self):
        self.receipt.append(meta("rwa/issuers/list", "https://k/rwa/issuers/list"))
        return [{"issuer_id": "iss", "name": "Issuer", "num_tokens": 3}]

    def cmc_map(self, symbols=None, keyed=False):
        self.map_asked = symbols
        m = meta("cmc/map", "https://k/cmc/map?symbol=wMSx,wGILDx", keyed=False, credit_count=0)
        self.receipt.append(m)
        rows = {
            1: {"id": 1, "symbol": "wMSx", "status": "untracked"},
            77: {"id": 77, "symbol": "OTHER", "status": "active"},
        }
        return rows, m, ["wGILDx"]

    def cmc_info(self, ids, keyed=False):
        self.info_asked = ids
        m = meta("cmc/info", "https://k/cmc/info?id=1,2,9", keyed=False, credit_count=0)
        self.receipt.append(m)
        info = {
            1: {"id": 1, "symbol": "wMSx", "status": "inactive", "date_added": "2026-08-11"},
            2: {"id": 2, "symbol": "wGILDx", "status": "inactive", "date_added": None},
        }
        return info, [m], [9]


def test_named_symbols_lead_then_runners_up_then_the_widest_underlyings(small_doc):
    syms, ids = seed.select_underlyings(small_doc, 40)
    assert syms == ["MS", "GILD", "ZZZ", "AAA", "BBB"]
    assert ids == {"MS": 35, "GILD": 36, "ZZZ": 37, "AAA": 38, "BBB": 39}


def test_a_runner_up_absent_from_the_wrappers_is_skipped(small_doc):
    syms, _ = seed.select_underlyings(small_doc, 40)
    assert "GHOST" not in syms


def test_the_cap_stops_the_fill_once_n_underlyings_are_chosen(small_doc):
    syms, ids = seed.select_underlyings(small_doc, 4)
    assert syms == ["MS", "GILD", "ZZZ", "AAA"] and set(ids) == set(syms)


def test_a_cap_below_the_named_count_truncates_the_named_set(small_doc):
    syms, ids = seed.select_underlyings(small_doc, 2)
    assert syms == ["MS", "GILD"] and list(ids) == syms


def test_without_a_hero_only_the_named_set_leads(small_doc):
    small_doc.pop("hero")
    syms, _ = seed.select_underlyings(small_doc, 40)
    assert syms == ["MS", "GILD", "ZZZ", "AAA", "BBB"]


def test_provenance_splits_the_query_string_off_the_endpoint():
    p = seed.provenance(meta("rwa/quotes", "https://k/rwa/quotes?id=35&convert=USD"), pages=2)
    assert p["endpoint"] == "https://k/rwa/quotes" and p["params"] == "id=35&convert=USD"
    assert p["pages"] == 2 and p["keyed"] is True and p["sha256"] == "deadbeef"


def test_provenance_of_a_bare_url_has_empty_params():
    p = seed.provenance(meta("rwa/issuers/list", "https://k/rwa/issuers/list"))
    assert p["endpoint"] == "https://k/rwa/issuers/list" and p["params"] == ""


def test_without_a_key_the_capture_run_exits_with_a_message(monkeypatch, seed_dir, capsys):
    monkeypatch.setattr(sys, "argv", ["seed.py"])
    monkeypatch.setattr(seed, "api_key", lambda: None)
    monkeypatch.setattr(seed, "Client", None)
    with pytest.raises(SystemExit) as e:
        seed.main()
    assert "CMC_API_KEY" in str(e.value)
    assert "hero rule:" in capsys.readouterr().out
    assert not seed_dir.exists()


def test_the_capture_run_writes_four_seed_files_with_provenance(
    monkeypatch, tmp_path, seed_dir, small_doc, capsys
):
    census = tmp_path / "census.json"
    census.write_text(json.dumps(small_doc))
    monkeypatch.setattr(seed, "CENSUS", census)
    monkeypatch.setattr(seed, "api_key", lambda: "k")
    made = []
    monkeypatch.setattr(
        seed, "Client", lambda api_key: made.append(ScriptedClient(api_key)) or made[-1]
    )
    monkeypatch.setattr(sys, "argv", ["seed.py", "--n", "3"])

    assert seed.main() == 0

    client = made[0]
    assert client.api_key == "k"
    assert client.quotes_asked == [35, 36, 37]
    assert client.map_asked == ["wMSx", "wGILDx"]
    assert client.info_asked == [1, 2, 9]

    rwa_map = json.loads((seed_dir / "rwa_map.json").read_text())
    assert rwa_map["pages"] == 2 and len(rwa_map["rows"]) == 23
    assert rwa_map["params"] == "start=2" and rwa_map["_note"].startswith("A RECORDING")

    quotes = json.loads((seed_dir / "rwa_quotes.json").read_text())
    assert quotes["underlyings"] == ["MS", "GILD", "ZZZ"] and len(quotes["rwa_assets"]) == 3

    issuers = json.loads((seed_dir / "issuers.json").read_text())
    assert issuers["issuers"][0]["issuer_id"] == "iss" and issuers["credit_count"] == 1

    cmc = json.loads((seed_dir / "cmc_map_slice.json").read_text())
    assert cmc["dropped_symbols"] == ["wGILDx"]
    assert [r["id"] for r in cmc["rows"]] == [1]
    assert cmc["info"]["unknown_ids"] == [9] and cmc["info"]["endpoint"] == "https://k/cmc/info"
    assert cmc["info"]["rows"]["1"] == {
        "id": 1,
        "symbol": "wMSx",
        "status": "inactive",
        "date_added": "2026-08-11",
        "platform": None,
    }

    out = capsys.readouterr().out
    assert "hero rule:" in out and "-> MS (MS Inc) rwa_rank 43" in out
    assert (
        "23 universe rows, 3 wrappers, 1 issuers, 1 map rows, 2 listing dates; 2 keyed credits"
        in out
    )


def test_running_the_script_as_main_exits_with_its_return_code(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["seed.py", "--hero"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(ROOT / "scripts" / "seed.py"), run_name="__main__")
    assert e.value.code == 0
    assert "hero rule:" in capsys.readouterr().out
