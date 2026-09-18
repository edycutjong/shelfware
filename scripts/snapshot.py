#!/usr/bin/env python3
"""The daily snapshot — the census's only time axis.

Untracked rows in /v1/cryptocurrency/map carry no dates (verified 2026-09-18, see
docs/proof/spike.json), so "what changed this week" can only be answered by diffing snapshots
taken daily. This script takes today's, writes data/snapshots/YYYY-MM-DD.json (compact: counts,
tables, a slim row per wrapper) and recomputes data/delta.json from the two most recent days.
It does NOT touch data/census.json — that file is the committed run the receipts describe.

    python3 scripts/snapshot.py                    # today's, ~5 keyed credits (needs CMC_API_KEY)
    python3 scripts/snapshot.py --import FILE      # bring an earlier run into the series, recounted
    python3 scripts/snapshot.py --delta            # only recompute data/delta.json
"""

import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfware.cli import SNAPSHOTS, compact, print_census, run_census, write_delta  # noqa: E402
from shelfware.client import EX_TEMPFAIL, Client, api_key  # noqa: E402
from shelfware.join import STATUSES, counts_of, scorecard, type_bars  # noqa: E402


def recounted(doc):
    """Counts, issuer table and type bars rebuilt from the rows by this engine, so an imported
    run and a native one carry the same rules (strict zero-tracked, unresolved never shelf)."""
    ws = doc["wrappers"]
    for w in ws:
        if w.get("status") not in STATUSES:
            w["status"] = "unresolved"
    has_tokens_rows = [{"rwa_id": i} for i in sorted({w["rwa_id"] for w in ws})]
    c = counts_of(ws, [], has_tokens_rows, doc.get("issuers_registry"))
    c["underlyings"] = doc["counts"].get("underlyings")
    c["has_tokens"] = doc["counts"].get("has_tokens", len(has_tokens_rows))
    if "cmc_map_rows" in doc["counts"]:
        c["cmc_map_rows"] = doc["counts"]["cmc_map_rows"]
    return {
        **doc,
        "counts": c,
        "by_issuer": scorecard(ws, doc.get("issuers_registry") or []),
        "by_type": type_bars(ws),
    }


def import_run(path):
    doc = recounted(json.loads(Path(path).read_text()))
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    out = SNAPSHOTS / f"{doc['generated_utc'][:10]}.json"
    out.write_text(json.dumps(compact(doc), indent=1))
    c = doc["counts"]
    print(
        f"imported {Path(path).name} → {out.relative_to(SNAPSHOTS.parents[1])}  "
        f"({doc['generated_utc']}: {c['wrappers']} wrappers, {c['untracked']} untracked, "
        f"{c['underlyings_zero_tracked']} zero-tracked underlyings)"
    )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--import", dest="import_path", metavar="FILE")
    ap.add_argument("--delta", action="store_true", help="only recompute data/delta.json")
    a = ap.parse_args()
    if a.import_path:
        import_run(a.import_path)
        write_delta()
        return 0
    if a.delta:
        write_delta()
        return 0
    key = api_key()
    if not key:
        sys.exit(
            "snapshot needs CMC_API_KEY — the RWA endpoints are keyed (403 error 1005 keyless)"
        )
    client = Client(api_key=key)
    try:
        doc = run_census(client, out=io.StringIO())
    except RuntimeError as e:
        print(f"snapshot failed: {e}")
        return EX_TEMPFAIL if "transient" in str(e) else 1
    doc.pop("_rwa_rows", None)
    print_census(doc)
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    out = SNAPSHOTS / f"{doc['generated_utc'][:10]}.json"
    out.write_text(json.dumps(compact(doc), indent=1))
    print(f"wrote {out.relative_to(SNAPSHOTS.parents[1])}")
    write_delta()
    return 0


if __name__ == "__main__":
    sys.exit(main())
