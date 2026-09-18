#!/usr/bin/env python3
"""Recount every headline from the committed rows; fail if the README or the page drifted.

    python3 scripts/verify.py            # counts vs a recount of wrappers[]; README + site state the pair
    python3 scripts/verify.py --live     # + re-fetch 10 statuses keyless and compare (0 credits)

Exit 0 = every number on every judged surface is the one the rows produce. Exit 1 = drift.
Exit 75 = the live check could not run because the anonymous pool is throttling.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfware.cli import cmd_verify  # noqa: E402
from shelfware.verify import check_text_mentions, load_census  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SURFACES = ["README.md", "DEMO.md", "JUDGE.md", "site/index.html"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    rc = cmd_verify(
        ["--live", "--seed", str(a.seed)]
        if a.live and a.seed is not None
        else ["--live"]
        if a.live
        else []
    )
    doc = load_census()
    findings = []
    for name in SURFACES:
        p = ROOT / name
        if p.exists():
            findings += check_text_mentions(p.read_text(), doc, name)
    print()
    for f in findings:
        print(f"  DRIFT: {f}")
    present = [s for s in SURFACES if (ROOT / s).exists()]
    if not findings:
        print(f"  {', '.join(present)}: each states the pair the rows produce")
    return 1 if findings else rc


if __name__ == "__main__":
    sys.exit(main())
