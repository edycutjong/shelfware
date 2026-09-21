"""The version bump, offline: it reads the one stamp pyproject declares, rewrites all three
stamps in lockstep, refuses anything that is not X.Y.Z or a tree with a stamp missing or
doubled, and the command line is print / bump / usage by argument count."""

import io
import runpy
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import bump_version  # noqa: E402

SCRIPT = ROOT / "scripts" / "bump_version.py"
STAMPED = ("pyproject.toml", "shelfware/__init__.py", "api/health.js")


@pytest.fixture
def tree(tmp_path):
    for rel in STAMPED:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text((ROOT / rel).read_text())
    return tmp_path


@pytest.fixture
def writes_go_to(tree, monkeypatch):
    """Every write the script aims at the real tree lands in the copy instead."""
    real_write = Path.write_text

    def redirected(self, data, *args, **kwargs):
        target = tree / self.relative_to(ROOT) if self.is_relative_to(ROOT) else self
        return real_write(target, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", redirected)
    return tree


def test_current_is_the_version_pyproject_declares():
    assert 'version = "' + bump_version.current() + '"' in (ROOT / "pyproject.toml").read_text()


def test_current_refuses_a_pyproject_without_a_version_line(monkeypatch):
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: "[project]\nname = 'x'\n")
    with pytest.raises(SystemExit, match="carries no version"):
        bump_version.current()


def test_bump_rewrites_all_three_stamps_and_reports_each(tree):
    out = io.StringIO()
    with redirect_stdout(out):
        bump_version.bump("4.5.6", root=tree)
    assert 'version = "4.5.6"' in (tree / "pyproject.toml").read_text()
    assert '__version__ = "4.5.6"' in (tree / "shelfware" / "__init__.py").read_text()
    assert '    version: "4.5.6",' in (tree / "api" / "health.js").read_text()
    assert out.getvalue().splitlines() == [f"{rel} -> 4.5.6" for rel in STAMPED]


def test_bump_refuses_anything_that_is_not_x_y_z(tree):
    before = {rel: (tree / rel).read_text() for rel in STAMPED}
    for bad in ("v1.2.3", "1.2", "1.2.3-rc1", ""):
        with pytest.raises(SystemExit, match="not a version"):
            bump_version.bump(bad, root=tree)
    assert {rel: (tree / rel).read_text() for rel in STAMPED} == before


def test_bump_refuses_a_tree_where_a_stamp_is_missing_or_doubled(tree):
    init = tree / "shelfware" / "__init__.py"
    init.write_text(init.read_text() + '__version__ = "0.0.0"\n')
    with pytest.raises(
        SystemExit, match="shelfware/__init__.py: expected exactly one version stamp"
    ):
        bump_version.bump("1.0.0", root=tree)
    assert 'version = "1.0.0"' in (tree / "pyproject.toml").read_text()
    (tree / "api" / "health.js").write_text("export default () => ({ ok: true });\n")
    init.write_text('__version__ = "0.0.0"\n')
    with pytest.raises(SystemExit, match="api/health.js: expected exactly one version stamp"):
        bump_version.bump("1.0.0", root=tree)


def test_the_command_with_no_argument_prints_the_current_version(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bump_version.py"])
    out = io.StringIO()
    with redirect_stdout(out):
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert out.getvalue().strip() == bump_version.current()


def test_the_command_with_one_argument_bumps_the_tree_and_tolerates_a_leading_v(
    writes_go_to, monkeypatch
):
    monkeypatch.setattr(sys, "argv", ["bump_version.py", "v7.8.9"])
    out = io.StringIO()
    with redirect_stdout(out):
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert out.getvalue().splitlines() == [f"{rel} -> 7.8.9" for rel in STAMPED]
    assert 'version = "7.8.9"' in (writes_go_to / "pyproject.toml").read_text()
    assert 'version: "7.8.9",' in (writes_go_to / "api" / "health.js").read_text()
    assert bump_version.current() != "7.8.9"


def test_the_command_with_more_arguments_exits_with_usage(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bump_version.py", "1.2.3", "4.5.6"])
    with pytest.raises(SystemExit, match="usage: bump_version.py"):
        runpy.run_path(str(SCRIPT), run_name="__main__")
