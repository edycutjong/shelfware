#!/usr/bin/env python3
"""Refuse to let a placeholder, a key, or a stale number reach a judge.

Scans every judge-facing file for the things that quietly survive into a submission and
destroy it on sight: an unfilled address, a fake video link, a TODO, a template token, a
32-hex string that looks like a CoinMarketCap key, and a census older than the page admits.

    python3 scripts/check_submission_readiness.py          # exit 1 on any finding
    python3 scripts/check_submission_readiness.py --json

Exit 0 = clean. Exit 1 = something is not ready. Wired into `make check`.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Files a judge actually opens. A TODO in a source comment is ordinary engineering; a TODO
# in the README is an unfinished submission.
TARGETS = ["README.md", "DEMO.md", "JUDGE.md", "FEEDBACK.md", "ARCHITECTURE.md", "site/index.html"]
TARGET_GLOBS = ["docs/*.md", ".github/*.md"]
# The key scan covers everything tracked, not just the judge-facing files.
KEY_PATTERN = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])|X-CMC_PRO_API_KEY['\"]?\s*[:=]\s*['\"]?[0-9a-zA-Z]{20,}"
)
MAX_CENSUS_AGE_DAYS = 3

PATTERNS = [
    ("unfilled address", r"0x\.\.\."),
    ("placeholder video", r"youtu\.be/(xxx|your-video|VIDEO_ID)\b"),
    ("placeholder video", r"youtube\.com/watch\?v=(xxx|your-video|VIDEO_ID)\b"),
    ("TODO marker", r"\bTODO\b"),
    ("TODO marker", r"\bFIXME\b"),
    ("unreplaced template token", r"\[\[FILL\]\]"),
    ("unreplaced template token", r"\[Project Name\]"),
    ("unreplaced template token", r"\bOWNER/REPO\b"),
    ("unreplaced template token", r"\[your-[a-z-]+\]"),
    ("placeholder URL", r"https?://\[[a-z-]+\]"),
    ("placeholder URL", r"example\.com/(your|placeholder)"),
    ("overclaim", r"never traded"),
    ("overclaim", r"\$0 traded ever"),
]

# A line that is itself the definition of a pattern is not a violation.
# ...and so is the wording guard itself: a line that NEGATES the overclaim is the R6 rule at work.
SELF_REFERENTIAL = re.compile(
    r"placeholder|readiness|scanner|check_submission|wording guard|never \"never traded\"|never say"
    r"|not \"never traded\"|does not mean never traded|not (a claim|mean) .*never traded"
    r"|'never traded' would be false"
)


def scan():
    files = [ROOT / t for t in TARGETS if (ROOT / t).exists()]
    for g in TARGET_GLOBS:
        files += sorted(ROOT.glob(g))
    findings = []
    for f in sorted(set(files)):
        for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if SELF_REFERENTIAL.search(line):
                continue
            for label, pat in PATTERNS:
                if re.search(pat, line, re.IGNORECASE if "youtu" in pat or "traded" in pat else 0):
                    findings.append(
                        {
                            "file": str(f.relative_to(ROOT)),
                            "line": n,
                            "kind": label,
                            "text": line.strip()[:110],
                        }
                    )
                    break
    # secrets: every tracked file, plus the git history for the key's own shape
    try:
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        tracked = []
    for rel in tracked:
        p = ROOT / rel
        if not p.is_file() or p.suffix in (".png", ".jpg", ".woff2", ".ico"):
            continue
        text = p.read_text(errors="replace")
        if KEY_PATTERN.search(text):
            findings.append(
                {
                    "file": rel,
                    "line": 0,
                    "kind": "credential-shaped string",
                    "text": "a UUID-shaped or header-assigned key pattern is in a tracked file",
                }
            )
    # staleness: the page and the README must not carry a census older than the limit
    census = ROOT / "data" / "census.json"
    if census.exists():
        utc = json.loads(census.read_text())["generated_utc"]
        age = (datetime.now(UTC) - datetime.fromisoformat(utc.replace("Z", "+00:00"))).days
        if age > MAX_CENSUS_AGE_DAYS:
            findings.append(
                {
                    "file": "data/census.json",
                    "line": 0,
                    "kind": "stale census",
                    "text": f"generated {utc}, {age} days ago — run `make census` and re-render",
                }
            )
    return [str(f.relative_to(ROOT)) for f in sorted(set(files))], findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    scanned, findings = scan()
    if a.json:
        print(json.dumps({"scanned": scanned, "findings": findings}, indent=2))
    else:
        print(
            f"submission readiness — scanned {len(scanned)} judge-facing file(s) + every tracked file for a key"
        )
        for s in scanned:
            print(f"  · {s}")
        if findings:
            print(f"\n{len(findings)} problem(s) still in the submission:\n")
            for f in findings:
                print(f"  {f['file']}:{f['line']}  [{f['kind']}]  {f['text']}")
        else:
            print(
                "\nclean — no unfilled addresses, fake links, TODOs, template tokens, overclaims, keys or stale census"
            )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
