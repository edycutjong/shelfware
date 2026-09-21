"""The benchmark script, offline: the live leg with a scripted client and lookup, the replay
leg over the committed rows, the CLI in both modes, and the entry point."""

import io
import json
import runpy
import sys
from contextlib import redirect_stdout

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import bench  # noqa: E402

BENCH_PATH = ROOT / "scripts" / "bench.py"


@pytest.fixture
def roster(tmp_path, monkeypatch):
    doc = {
        "underlyings": {
            "MS": {"tokens": [{"symbol": "wMSx"}, {"symbol": None}]},
            "APH": {"tokens": [{"symbol": "wAPHx"}]},
            "GILD": {"tokens": [{"symbol": "GILDx"}]},
            "NVDA": {"tokens": []},
            "AAPL": None,
        }
    }
    path = tmp_path / "roster.json"
    path.write_text(json.dumps(doc))
    monkeypatch.setattr(bench, "ROSTER", path)
    monkeypatch.setattr(bench.time, "sleep", lambda _s: None)
    return doc


@pytest.fixture
def scripted(monkeypatch):
    calls = {"map": [], "lookup": []}

    class FakeClient:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def cmc_map(self, syms):
            calls["map"].append(list(syms))
            if syms == ["wAPHx"]:
                return [], {"error": "429 throttled by the anonymous pool " * 4}, None
            return [{"symbol": s} for s in syms], {}, None

    def fake_lookup(ticker, client, roster):
        calls["lookup"].append(ticker)
        if ticker == "GILD":
            return {
                "temporary_failure": True,
                "status": {"fallback_reason": "map leg failed: " + "x" * 100},
            }
        return {"temporary_failure": False, "verdict": f"{ticker} is shelfware"}

    monkeypatch.setattr(bench, "Client", FakeClient)
    monkeypatch.setattr(bench, "lookup", fake_lookup)
    return calls


def run_live(iterations, tickers):
    out = io.StringIO()
    with redirect_stdout(out):
        res = bench.live(iterations, tickers)
    return res, out.getvalue()


def test_report_prints_nearest_rank_percentiles_and_returns_rounded_numbers(capsys):
    r = bench.report("label", [3.0, 1.0, 2.0], unit="s")
    assert r == {"n": 3, "p50": 2.0, "p95": 3.0, "max": 3.0, "unit": "s"}
    assert "p50      2.00s" in capsys.readouterr().out


def test_timed_returns_elapsed_milliseconds_and_the_callable_result():
    ms, r = bench.timed(lambda: "done")
    assert r == "done" and ms >= 0


def test_live_times_the_status_leg_only_for_tickers_with_wrapper_symbols(roster, scripted):
    res, text = run_live(5, ["MS", "APH", "GILD", "NVDA", "AAPL"])
    assert scripted["map"] == [["wMSx"], ["wAPHx"], ["GILDx"]]
    assert scripted["lookup"] == ["MS", "APH", "GILD", "NVDA", "AAPL"]
    assert res["status_leg"]["n"] == 2 and res["lookup"]["n"] == 4
    assert res["tickers"] == ["MS", "APH", "GILD", "NVDA", "AAPL"] and res["credits_used"] == 0
    assert len(res["errors"]) == 2
    assert res["errors"][0].startswith("APH: 429 throttled") and len(res["errors"][0]) <= 85
    assert res["errors"][1].startswith("GILD: map leg failed") and len(res["errors"][1]) <= 86
    assert "MS is shelfware" in text and "error: APH" in text and "GILD is shelfware" not in text


def test_live_truncates_the_ticker_list_to_the_iteration_count(roster, scripted):
    res, _ = run_live(1, ["MS", "APH"])
    assert scripted["lookup"] == ["MS"] and res["tickers"] == ["MS"]


def test_live_omits_the_status_leg_when_no_ticker_had_a_symbol(roster, scripted):
    res, _ = run_live(2, ["NVDA", "AAPL"])
    assert "status_leg" not in res and res["lookup"]["n"] == 2 and res["errors"] == []


def test_live_exits_when_every_ticker_failed(roster, scripted):
    with pytest.raises(SystemExit, match="every ticker failed"), redirect_stdout(io.StringIO()):
        bench.live(1, ["GILD"])


def test_replay_mode_defaults_to_two_hundred_iterations_and_writes_json(monkeypatch, tmp_path):
    seen = {}

    def fake_replay(iterations):
        seen["iterations"] = iterations
        return {"join_seed": {"n": iterations}}

    monkeypatch.setattr(bench, "replay", fake_replay)
    monkeypatch.setattr(bench, "live", None)
    target = tmp_path / "bench.json"
    monkeypatch.setattr(sys, "argv", ["bench.py", "--replay", "--json", str(target)])
    out = io.StringIO()
    with redirect_stdout(out):
        bench.main()
    doc = json.loads(target.read_text())
    assert seen["iterations"] == 200 and doc["iterations"] == 200
    assert doc["mode"] == "replay" and doc["join_seed"] == {"n": 200}
    assert doc["utc"].endswith("Z")
    assert "no network" in out.getvalue() and f"wrote {target}" in out.getvalue()


def test_live_mode_runs_the_tickers_then_the_replay_and_writes_no_file(monkeypatch, tmp_path):
    order = []

    def fake_live(iterations, tickers):
        order.append(("live", iterations, tickers))
        return {"lookup": {"n": iterations}}

    def fake_replay(iterations):
        order.append(("replay", iterations))
        return {"join_seed": {"n": iterations}}

    monkeypatch.setattr(bench, "live", fake_live)
    monkeypatch.setattr(bench, "replay", fake_replay)
    monkeypatch.setattr(sys, "argv", ["bench.py", "--iterations", "3"])
    out = io.StringIO()
    with redirect_stdout(out):
        bench.main()
    assert order == [("live", 3, bench.TICKERS), ("replay", 200)]
    assert "0 credits — keyless" in out.getvalue() and "wrote" not in out.getvalue()
    assert list(tmp_path.iterdir()) == []


def test_live_mode_defaults_to_one_iteration_per_ticker(monkeypatch):
    seen = {}
    monkeypatch.setattr(bench, "live", lambda n, t: seen.setdefault("n", n) and {})
    monkeypatch.setattr(bench, "replay", lambda n: {})
    monkeypatch.setattr(sys, "argv", ["bench.py"])
    with redirect_stdout(io.StringIO()):
        bench.main()
    assert seen["n"] == len(bench.TICKERS)


def test_running_the_script_as_main_replays_the_committed_rows(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bench.py", "--replay", "--iterations", "2"])
    out = io.StringIO()
    with redirect_stdout(out):
        runpy.run_path(str(BENCH_PATH), run_name="__main__")
    text = out.getvalue()
    assert "replay — data/seed captured" in text and "recount (1435 wrappers, census)" in text
    assert text.rstrip().endswith("no network")
