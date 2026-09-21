"""scripts/snapshot.py offline, every branch: the recount's status and cmc_map_rows rules, the
three main() paths (--import, --delta, today's), the missing-key exit, the two failure codes."""

import io
import json
import runpy
import sys
from contextlib import redirect_stdout

import pytest
from conftest import ROOT

from shelfware import cli
from shelfware.client import EX_TEMPFAIL

sys.path.insert(0, str(ROOT / "scripts"))
import snapshot  # noqa: E402

SCRIPT = ROOT / "scripts" / "snapshot.py"


def wrapper(crypto_id, status, rwa_id=10):
    return {
        "crypto_id": crypto_id,
        "symbol": f"S{crypto_id}",
        "underlying": f"U{rwa_id}",
        "rwa_id": rwa_id,
        "issuer_id": "i",
        "issuer_name": "I",
        "status": status,
        "price": None,
        "market_cap": None,
        "asset_type": "stock",
    }


def run_doc(utc="2026-09-20T00:00:00Z", **extra_counts):
    return {
        "generated_utc": utc,
        "counts": {"underlyings": 5, "has_tokens": 1, **extra_counts},
        "issuers_registry": [{"issuer_id": "i", "name": "I", "num_tokens": 2}],
        "wrappers": [wrapper(1, "untracked"), wrapper(2, "active")],
        "_rwa_rows": [{"rwa_id": 10}],
    }


@pytest.fixture
def snapshots_dir(tmp_path, monkeypatch):
    d = tmp_path / "snapshots"
    monkeypatch.setattr(snapshot, "SNAPSHOTS", d)
    monkeypatch.setattr(cli, "SNAPSHOTS", d)
    monkeypatch.setattr(cli, "DATA", tmp_path)
    return d


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("CMC_API_KEY", "k")
    monkeypatch.delenv("COINMARKETCAP_API_KEY", raising=False)
    monkeypatch.delenv("CMC_PRO_API_KEY", raising=False)
    monkeypatch.setattr(snapshot, "print_census", lambda doc, out=None: None)


@pytest.fixture
def keyless(monkeypatch):
    for var in ("CMC_API_KEY", "COINMARKETCAP_API_KEY", "CMC_PRO_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_recount_coerces_an_unknown_status_to_unresolved_and_leaves_known_ones_alone():
    doc = run_doc()
    doc["wrappers"].append(wrapper(3, "weird", rwa_id=20))
    out = snapshot.recounted(doc)
    assert [w["status"] for w in out["wrappers"]] == ["untracked", "active", "unresolved"]
    assert out["counts"]["unresolved"] == 1 and out["counts"]["wrappers"] == 3


def test_recount_keeps_cmc_map_rows_only_when_the_source_run_had_it():
    with_rows = snapshot.recounted(run_doc(cmc_map_rows=42))
    without = snapshot.recounted(run_doc())
    assert with_rows["counts"]["cmc_map_rows"] == 42
    assert "cmc_map_rows" not in without["counts"]
    assert without["counts"]["underlyings"] == 5 and without["counts"]["has_tokens"] == 1


def test_recount_defaults_has_tokens_to_the_distinct_rwa_ids_and_tolerates_no_registry():
    doc = run_doc()
    del doc["counts"]["has_tokens"]
    del doc["issuers_registry"]
    out = snapshot.recounted(doc)
    assert out["counts"]["has_tokens"] == 1
    assert out["by_issuer"][0]["issuer_name"] == "I" and out["by_type"][0]["asset_type"] == "stock"


def test_import_flag_writes_the_dated_file_then_recomputes_the_delta(
    snapshots_dir, tmp_path, monkeypatch, capsys
):
    src = tmp_path / "earlier.json"
    src.write_text(json.dumps(run_doc("2026-09-17T12:00:00Z")))
    monkeypatch.setattr(sys, "argv", ["snapshot.py", "--import", str(src)])
    assert snapshot.main() == 0
    out = capsys.readouterr().out
    assert (snapshots_dir / "2026-09-17.json").exists()
    assert "imported earlier.json" in out and "delta: 1 snapshot(s)" in out


def test_delta_flag_only_recomputes_delta_json_from_the_two_latest_days(
    snapshots_dir, tmp_path, monkeypatch, capsys
):
    snapshots_dir.mkdir()
    for day, doc in (
        ("2026-09-18", run_doc("2026-09-18T00:00:00Z")),
        ("2026-09-19", run_doc("2026-09-19T00:00:00Z")),
    ):
        (snapshots_dir / f"{day}.json").write_text(json.dumps(cli.compact(doc)))
    monkeypatch.setattr(sys, "argv", ["snapshot.py", "--delta"])
    assert snapshot.main() == 0
    assert "delta 2026-09-18 → 2026-09-19" in capsys.readouterr().out
    assert json.loads((tmp_path / "delta.json").read_text())["to"] == "2026-09-19T00:00:00Z"
    assert sorted(p.name for p in snapshots_dir.iterdir()) == ["2026-09-18.json", "2026-09-19.json"]


def test_a_missing_key_exits_with_the_keyed_endpoint_explanation(keyless, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["snapshot.py"])
    with pytest.raises(SystemExit) as e:
        snapshot.main()
    assert "needs CMC_API_KEY" in str(e.value)


def test_a_transient_census_failure_returns_tempfail(keyed, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["snapshot.py"])
    monkeypatch.setattr(snapshot, "Client", lambda api_key: api_key)

    def refuse(client, out=None):
        raise RuntimeError("transient: pool exhausted")

    monkeypatch.setattr(snapshot, "run_census", refuse)
    assert snapshot.main() == EX_TEMPFAIL
    assert "snapshot failed: transient: pool exhausted" in capsys.readouterr().out


def test_a_hard_census_failure_returns_one(keyed, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["snapshot.py"])
    monkeypatch.setattr(snapshot, "Client", lambda api_key: api_key)

    def refuse(client, out=None):
        raise RuntimeError("403 error 1005")

    monkeypatch.setattr(snapshot, "run_census", refuse)
    assert snapshot.main() == 1
    assert "snapshot failed: 403 error 1005" in capsys.readouterr().out


def test_todays_snapshot_is_written_compact_without_the_rwa_rows_and_the_delta_follows(
    keyed, snapshots_dir, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", ["snapshot.py"])
    seen = {}
    monkeypatch.setattr(snapshot, "Client", lambda api_key: seen.setdefault("key", api_key))
    monkeypatch.setattr(snapshot, "run_census", lambda client, out=None: run_doc())
    assert snapshot.main() == 0
    written = json.loads((snapshots_dir / "2026-09-20.json").read_text())
    assert seen["key"] == "k"
    assert "_rwa_rows" not in written and "issuers_registry" not in written
    assert [w["crypto_id"] for w in written["wrappers"]] == [1, 2]
    out = capsys.readouterr().out
    assert "wrote " in out and "snapshots/2026-09-20.json" in out and "delta: 1 snapshot(s)" in out


def test_running_the_script_as_main_exits_with_the_delta_path_code(snapshots_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["snapshot.py", "--delta"])
    buf = io.StringIO()
    with pytest.raises(SystemExit) as e, redirect_stdout(buf):
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert e.value.code == 0
    assert "delta: 0 snapshot(s)" in buf.getvalue()
