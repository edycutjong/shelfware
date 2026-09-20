"""Set the one version the tree carries — pyproject.toml, shelfware/__init__.py, api/health.js —
to X.Y.Z, so the CLI's --version, the health endpoint and the page's stamp cannot disagree.

release.yml calls this with the version it computed from the commits since the last tag, then
re-renders the site and commits the result BEFORE it tags, so the tag always points at a commit
whose stamp is the tag. By hand: python3 scripts/bump_version.py 1.2.3 && make site."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
# file -> (pattern, replacement template); exactly one match each, or the bump refuses.
STAMPS = {
    ROOT / "pyproject.toml": (re.compile(r'^version = "\d+\.\d+\.\d+"$', re.M), 'version = "{v}"'),
    ROOT / "shelfware" / "__init__.py": (
        re.compile(r'^__version__ = "\d+\.\d+\.\d+"$', re.M),
        '__version__ = "{v}"',
    ),
    ROOT / "api" / "health.js": (
        re.compile(r'^(\s+)version: "\d+\.\d+\.\d+",$', re.M),
        r'\g<1>version: "{v}",',
    ),
}


def current():
    """The version pyproject.toml declares — the source of truth for every other stamp."""
    m = STAMPS[ROOT / "pyproject.toml"][0].search((ROOT / "pyproject.toml").read_text())
    if not m:
        sys.exit('pyproject.toml carries no version = "X.Y.Z" line')
    return m.group(0).split('"')[1]


def bump(version, root=ROOT):
    if not SEMVER.match(version):
        sys.exit(f"not a version: {version!r} (want X.Y.Z, no leading v)")
    for path, (pattern, template) in STAMPS.items():
        path = root / path.relative_to(ROOT)
        text = path.read_text()
        if len(pattern.findall(text)) != 1:
            sys.exit(f"{path.relative_to(root)}: expected exactly one version stamp")
        path.write_text(pattern.sub(template.format(v=version), text))
        print(f"{path.relative_to(root)} -> {version}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(current())
    elif len(sys.argv) == 2:
        bump(sys.argv[1].lstrip("v"))
    else:
        sys.exit("usage: bump_version.py [X.Y.Z]")
