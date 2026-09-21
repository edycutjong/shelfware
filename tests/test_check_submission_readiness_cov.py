"""The readiness gate end to end, offline: every scan branch, the key scan's skips and
failures, the census staleness clock, and both output modes of main()."""

import io
import json
import runpy
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import check_submission_readiness as gate  # noqa: E402

SCRIPT = ROOT / "scripts" / "check_submission_readiness.py"


@pytest.fixture
def tree(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def git_tree(tree):
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    return tree


def census_at(tree, when):
    (tree / "data").mkdir()
    (tree / "data" / "census.json").write_text(
        json.dumps({"generated_utc": when.strftime("%Y-%m-%dT%H:%M:%SZ")})
    )


def run_main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["check_submission_readiness.py", *argv])
    out = io.StringIO()
    with redirect_stdout(out):
        code = gate.main()
    return code, out.getvalue()


def test_glob_targets_and_clean_lines_produce_no_findings(tree):
    (tree / "docs").mkdir()
    (tree / "docs" / "notes.md").write_text("ordinary prose\nmore prose\n")
    scanned, findings = gate.scan()
    assert scanned == ["docs/notes.md"]
    assert findings == []


def test_one_line_yields_one_finding_even_when_several_patterns_match(tree):
    (tree / "README.md").write_text("send to 0x... and fix the T" + "ODO\n")
    _, findings = gate.scan()
    assert findings == [
        {
            "file": "README.md",
            "line": 1,
            "kind": "unfilled address",
            "text": "send to 0x... and fix the T" + "ODO",
        }
    ]


def test_a_missing_git_binary_skips_the_key_scan(tree, monkeypatch):
    (tree / "README.md").write_text("fine\n")

    def no_git(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(gate.subprocess, "run", no_git)
    _, findings = gate.scan()
    assert findings == []


# Assembled at runtime so this file never carries a UUID-shaped literal of its own — the
# scanner under test reads every tracked file, this one included (CI 2026-09-21).
FAKE_UUID = "-".join(["12345678", "1234", "1234", "1234", "123456789abc"])


def test_binary_and_deleted_tracked_files_are_skipped_by_the_key_scan(git_tree):
    uuid = FAKE_UUID
    (git_tree / "logo.png").write_bytes(uuid.encode())
    (git_tree / "gone.txt").write_text(uuid + "\n")
    (git_tree / "kept.txt").write_text("nothing to see\n")
    subprocess.run(["git", "add", "."], cwd=git_tree, check=True)
    (git_tree / "gone.txt").unlink()
    _, findings = gate.scan()
    assert findings == []


def test_a_uuid_shaped_key_in_a_tracked_text_file_is_reported_once(git_tree):
    (git_tree / "cfg.txt").write_text(f"key={FAKE_UUID}\n")
    subprocess.run(["git", "add", "."], cwd=git_tree, check=True)
    _, findings = gate.scan()
    assert findings == [
        {
            "file": "cfg.txt",
            "line": 0,
            "kind": "credential-shaped string",
            "text": "a UUID-shaped or header-assigned key pattern is in a tracked file",
        }
    ]


def test_a_fresh_census_is_not_stale(tree):
    census_at(tree, datetime.now(UTC) - timedelta(days=1))
    _, findings = gate.scan()
    assert findings == []


def test_a_census_older_than_the_limit_is_stale(tree):
    census_at(tree, datetime.now(UTC) - timedelta(days=gate.MAX_CENSUS_AGE_DAYS + 2))
    _, findings = gate.scan()
    assert [f["kind"] for f in findings] == ["stale census"]
    assert findings[0]["file"] == "data/census.json"
    assert f"{gate.MAX_CENSUS_AGE_DAYS + 2} days ago" in findings[0]["text"]


def test_main_prints_json_and_exits_nonzero_on_a_finding(tree, monkeypatch):
    (tree / "DEMO.md").write_text("watch youtu.be/xxx\n")
    code, out = run_main(monkeypatch, "--json")
    doc = json.loads(out)
    assert code == 1
    assert doc["scanned"] == ["DEMO.md"]
    assert doc["findings"][0]["kind"] == "placeholder video"


def test_main_lists_problems_in_text_mode(tree, monkeypatch):
    (tree / "JUDGE.md").write_text("see [Project Name]\n")
    code, out = run_main(monkeypatch)
    assert code == 1
    assert "scanned 1 judge-facing file(s)" in out
    assert "  · JUDGE.md" in out
    assert "1 problem(s) still in the submission" in out
    assert "JUDGE.md:1  [unreplaced template token]" in out


def test_main_reports_clean_and_exits_zero_without_findings(tree, monkeypatch):
    (tree / "README.md").write_text("all good\n")
    code, out = run_main(monkeypatch)
    assert code == 0
    assert out.startswith("submission readiness — scanned 1")
    assert "clean — no unfilled addresses" in out


def test_running_the_script_as_a_program_exits_with_the_scan_result(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["check_submission_readiness.py"])
    out = io.StringIO()
    with redirect_stdout(out), pytest.raises(SystemExit) as exc:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert exc.value.code in (0, 1)
    assert out.getvalue().startswith("submission readiness — scanned")
