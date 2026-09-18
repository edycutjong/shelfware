"""The readiness gate refuses placeholders, overclaims and key-shaped strings."""

import subprocess
import sys

from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import check_submission_readiness as gate  # noqa: E402


def test_the_committed_tree_is_clean():
    scanned, findings = gate.scan()
    assert "README.md" in scanned
    assert findings == [], findings


def test_an_overclaim_in_a_judge_facing_file_is_caught(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("MS has never traded anywhere.\nAlso youtu.be/xxx\n")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    _, findings = gate.scan()
    kinds = {f["kind"] for f in findings}
    assert "overclaim" in kinds and "placeholder video" in kinds


def test_a_key_shaped_string_in_a_tracked_file_is_caught(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "notes.txt").write_text("X-CMC_PRO_API_KEY: abcdefghijklmnopqrstuvwxyz1234\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    _, findings = gate.scan()
    assert any(f["kind"] == "credential-shaped string" for f in findings)


def test_the_wording_guard_line_itself_is_not_an_overclaim(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text(
        'The page says "listed, no CMC-tracked market" — never "never traded".\n'
    )
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    _, findings = gate.scan()
    assert findings == []
