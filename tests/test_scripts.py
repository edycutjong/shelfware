"""The proof scripts, offline: the snapshot importer recounts by this engine's rules, the seed
selector is deterministic, the replay bench runs on the committed rows."""

import io
import json
import sys
from contextlib import redirect_stdout

from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import bench  # noqa: E402
import seed  # noqa: E402
import snapshot  # noqa: E402


def kitchen_doc():
    """A run shaped like the kitchen collector's: counts by the loose rule, an unresolved id,
    no date_added — what --import must bring into the series recounted."""
    ws = [
        {
            "crypto_id": 1,
            "symbol": "A",
            "underlying": "U1",
            "rwa_id": 10,
            "issuer_id": "i",
            "issuer_name": "I",
            "status": "untracked",
            "price": None,
            "market_cap": None,
            "asset_type": "stock",
        },
        {
            "crypto_id": 2,
            "symbol": "B",
            "underlying": "U2",
            "rwa_id": 20,
            "issuer_id": "i",
            "issuer_name": "I",
            "status": "unresolved",
            "price": None,
            "market_cap": None,
            "asset_type": "stock",
        },
        {
            "crypto_id": 3,
            "symbol": "C",
            "underlying": "U3",
            "rwa_id": 30,
            "issuer_id": "j",
            "issuer_name": "J",
            "status": "active",
            "price": 1.0,
            "market_cap": 5.0,
            "asset_type": "etf",
        },
    ]
    return {
        "generated_utc": "2026-09-18T21:36:35Z",
        "counts": {
            "underlyings": 100,
            "has_tokens": 3,
            "wrappers": 3,
            "underlyings_zero_tracked": 2,
            "cmc_map_rows": 999,
        },
        "issuers_registry": [{"issuer_id": "i", "name": "I", "num_tokens": 9}],
        "wrappers": ws,
    }


def test_import_recounts_the_kitchen_run_by_the_strict_rule(tmp_path, monkeypatch):
    src = tmp_path / "kitchen.json"
    src.write_text(json.dumps(kitchen_doc()))
    monkeypatch.setattr(snapshot, "SNAPSHOTS", tmp_path / "snapshots")
    out = io.StringIO()
    with redirect_stdout(out):
        written = snapshot.import_run(src)
    doc = json.loads(written.read_text())
    assert written.name == "2026-09-18.json"
    assert (
        doc["counts"]["underlyings_zero_tracked"] == 1
    )  # U2's only wrapper is unresolved: not counted
    assert doc["counts"]["underlyings_zero_tracked_loose"] == 2
    assert doc["counts"]["underlyings"] == 100 and doc["counts"]["cmc_map_rows"] == 999
    assert doc["by_issuer"][0]["issuer_name"] == "I" and doc["by_issuer"][0]["declared"] == 9
    assert "issuers_registry" not in doc  # compact
    assert "1 zero-tracked underlyings" in out.getvalue()


def test_the_committed_snapshot_series_is_dated_and_compact():
    files = sorted((ROOT / "data" / "snapshots").glob("*.json"))
    assert files and all(len(f.stem) == 10 for f in files)
    doc = json.loads(files[0].read_text())
    assert doc["generated_utc"].startswith(files[0].stem)
    assert set(doc["wrappers"][0]) == {
        "crypto_id",
        "symbol",
        "underlying",
        "rwa_id",
        "issuer_name",
        "status",
        "price",
        "market_cap",
    }


def test_seed_selection_is_deterministic_and_leads_with_the_named_cases(committed_census):
    syms, ids = seed.select_underlyings(committed_census, 40)
    assert syms[:3] == ["MS", "NVDA", "GOLD"] and len(syms) == 40 and len(set(syms)) == 40
    assert ids["MS"] == 35
    again, _ = seed.select_underlyings(committed_census, 40)
    assert again == syms


def test_seed_hero_flag_prints_the_rule_without_network(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["seed.py", "--hero"])
    assert seed.main() == 0
    out = capsys.readouterr().out
    # the rank is whatever the committed census says today — the rule is the invariant, not the number
    hero = json.loads((ROOT / "data" / "census.json").read_text())["hero"]
    assert "hero rule:" in out
    assert f"{hero['symbol']} ({hero['name']}) rwa_rank {hero['rwa_rank']}" in out


def test_replay_bench_runs_on_the_committed_rows_without_network(monkeypatch):
    monkeypatch.setattr(bench, "Client", None)  # any network use would blow up
    out = io.StringIO()
    with redirect_stdout(out):
        r = bench.replay(5)
    assert r["join_seed"]["n"] == 5 and r["recount_census"]["wrappers"] == 1435
    assert r["join_seed"]["p50"] <= r["join_seed"]["p95"] <= r["join_seed"]["max"]
    assert "no network" in out.getvalue()


def test_nearest_rank_percentile_is_a_real_observation():
    from shelfware.join import pct_rank

    assert (
        pct_rank([5, 1, 3], 50) == 3 and pct_rank([5, 1, 3], 95) == 5 and pct_rank([], 50) is None
    )
