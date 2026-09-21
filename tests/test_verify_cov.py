"""scripts/verify.py offline: the flags it forwards to the engine, the surfaces it reads, and
the exit code it returns when a surface states a stale pair."""

import io
import runpy
import sys
from contextlib import redirect_stdout

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import verify as script  # noqa: E402

DOC = {
    "generated_utc": "2026-09-19T00:00:00Z",
    "counts": {
        "underlyings": 10,
        "has_tokens": 7,
        "wrappers": 9,
        "active": 3,
        "untracked": 6,
        "inactive": 0,
        "unresolved": 0,
        "underlyings_zero_tracked": 5,
    },
    "wrappers": [],
}


@pytest.fixture
def engine(monkeypatch):
    calls = {}

    def fake_cmd_verify(argv):
        calls["argv"] = argv
        return calls.get("rc", 0)

    monkeypatch.setattr(script, "cmd_verify", fake_cmd_verify)
    monkeypatch.setattr(script, "load_census", lambda: DOC)
    return calls


@pytest.fixture
def surfaces(tmp_path, monkeypatch):
    monkeypatch.setattr(script, "ROOT", tmp_path)
    (tmp_path / "site").mkdir()

    def write(name, text):
        (tmp_path / name).write_text(text)

    return write


@pytest.fixture
def run(monkeypatch):
    def go(argv):
        monkeypatch.setattr("sys.argv", ["verify.py", *argv])
        out = io.StringIO()
        with redirect_stdout(out):
            rc = script.main()
        return rc, out.getvalue()

    return go


def test_without_flags_the_engine_is_called_with_no_arguments(engine, surfaces, run):
    surfaces("README.md", "5 of 7 underlyings")
    rc, out = run([])
    assert rc == 0
    assert engine["argv"] == []
    assert "README.md: each states the pair the rows produce" in out


def test_live_alone_forwards_only_the_live_flag(engine, surfaces, run):
    rc, _ = run(["--live"])
    assert rc == 0 and engine["argv"] == ["--live"]


def test_live_with_a_seed_forwards_both(engine, surfaces, run):
    run(["--live", "--seed", "42"])
    assert engine["argv"] == ["--live", "--seed", "42"]


def test_a_seed_without_live_is_not_forwarded(engine, surfaces, run):
    run(["--seed", "42"])
    assert engine["argv"] == []


def test_a_surface_stating_a_stale_pair_is_named_and_exits_one(engine, surfaces, run):
    surfaces("README.md", "5 of 7 underlyings")
    surfaces("DEMO.md", "4 of 7 underlyings")
    rc, out = run([])
    assert rc == 1
    assert "DRIFT: DEMO.md: does not state '5 of 7'" in out
    assert "DRIFT: README.md" not in out


def test_only_surfaces_present_on_disk_are_listed(engine, surfaces, run):
    surfaces("JUDGE.md", "5 of 7")
    surfaces("site/index.html", "<p>5 of 7</p>")
    _, out = run([])
    assert "JUDGE.md, site/index.html: each states the pair" in out
    assert "README.md" not in out


def test_the_engine_exit_code_is_returned_when_no_surface_drifts(engine, surfaces, run):
    engine["rc"] = 75
    rc, out = run([])
    assert rc == 75 and "each states the pair" in out


def test_the_module_runs_as_a_script(monkeypatch, capsys):
    monkeypatch.setattr("shelfware.cli.cmd_verify", lambda argv: 0)
    monkeypatch.setattr("shelfware.verify.load_census", lambda: DOC)
    monkeypatch.setattr("shelfware.verify.check_text_mentions", lambda text, doc, label: [])
    monkeypatch.setattr("sys.argv", ["verify.py"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(ROOT / "scripts" / "verify.py"), run_name="__main__")
    assert e.value.code == 0
    assert "each states the pair the rows produce" in capsys.readouterr().out
