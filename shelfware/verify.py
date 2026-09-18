"""Re-derive every headline from the committed rows, and compare.

A judge should not have to trust `counts`. This recounts from `wrappers[]` alone — one filter,
one count — and fails on any drift between the rows, the counts block, and the numbers the
README and the page print. `--live` re-fetches ten statuses keyless and compares them to the
committed rows: the external side effect, not a return value.
"""

import json
import random
import re
from pathlib import Path

from shelfware.join import recount

ROOT = Path(__file__).resolve().parents[1]
CENSUS = ROOT / "data" / "census.json"

JQ_RECIPE = (
    "jq '[.wrappers[] | select(.status==\"untracked\")] | length' data/census.json   "
    "# wrappers on the shelf\n"
    'jq \'[.wrappers[] | group_by(.rwa_id)[] | select(all(.[]; .status=="untracked"))] '
    "| length' data/census.json   # underlyings with zero tracked wrapper"
)


def load_census(path=CENSUS):
    return json.loads(Path(path).read_text())


def compare_counts(doc):
    """(ok, findings) — every counted number against its recount from the rows."""
    c, r = doc["counts"], recount(doc)
    findings = []
    for k in (
        "wrappers",
        "active",
        "untracked",
        "inactive",
        "unresolved",
        "underlyings_zero_tracked",
    ):
        if c.get(k) != r.get(k):
            findings.append(f"counts.{k} = {c.get(k)} but the rows recount to {r.get(k)}")
    if r["price_null_iff_untracked_exceptions"]:
        findings.append(
            f"{r['price_null_iff_untracked_exceptions']} resolved wrapper(s) where price:null "
            "and status:untracked disagree — the join is no longer exact, say so on the page"
        )
    for e in doc["by_issuer"]:
        if not e["attached"]:
            continue
        got = r["by_issuer"].get(e["issuer_name"])
        want = (e["untracked"], e["attached"], e["shelf_rate"], e["live_market_cap_usd"])
        if got != want:
            findings.append(f"by_issuer[{e['issuer_name']}] = {want} but rows recount to {got}")
    for e in doc["by_type"]:
        got = r["by_type"].get(e["asset_type"])
        if got != (e["untracked"], e["attached"]):
            findings.append(f"by_type[{e['asset_type']}] drifted: {got}")
    a = sum(e["attached"] for e in doc["by_issuer"])
    if a != c["wrappers"]:
        findings.append(f"Σ by_issuer.attached = {a} ≠ wrappers {c['wrappers']}")
    t = sum(e["attached"] for e in doc["by_type"])
    if t != c["wrappers"]:
        findings.append(f"Σ by_type.attached = {t} ≠ wrappers {c['wrappers']}")
    if c["underlyings_zero_tracked"] > c["has_tokens"]:
        findings.append("zero-tracked underlyings exceed has_tokens — impossible")
    keyed = sum(int(m.get("credit_count") or 0) for m in doc["receipt"] if m.get("keyed"))
    if keyed != doc["credits_used"]:
        findings.append(f"credits_used {doc['credits_used']} ≠ Σ keyed credit_count {keyed}")
    return not findings, findings


def headline_numbers(doc):
    c = doc["counts"]
    return {
        "zero_tracked": c["underlyings_zero_tracked"],
        "has_tokens": c["has_tokens"],
        "share_pct": round(100 * c["underlyings_zero_tracked"] / c["has_tokens"]),
        "untracked": c["untracked"],
        "wrappers": c["wrappers"],
    }


def check_text_mentions(text, doc, label):
    """The README and the page must print the number the rows produce, not an older one."""
    h = headline_numbers(doc)
    findings = []
    pair = re.compile(rf"\b{h['zero_tracked']}\s+of\s+{h['has_tokens']}\b")
    if not pair.search(text):
        findings.append(f"{label}: does not state '{h['zero_tracked']} of {h['has_tokens']}'")
    return findings


def sample_for_live(doc, n=10, seed=None):
    rng = random.Random(seed)
    rows = [w for w in doc["wrappers"] if w.get("symbol") and w.get("status") != "unresolved"]
    return rng.sample(rows, min(n, len(rows)))


def live_check(doc, client, n=10, seed=None):
    """Re-fetch n statuses keyless and compare. Returns (ok, lines, meta)."""
    sample = sample_for_live(doc, n, seed)
    rows, meta, dropped = client.cmc_map([w["symbol"] for w in sample])
    if meta is None or meta.get("error"):
        return None, [f"live check could not run: {(meta or {}).get('error')}"], meta
    lines, ok = [], True
    for w in sample:
        live = (rows.get(w["crypto_id"]) or {}).get("status") or "unresolved"
        same = live == w["status"]
        ok = ok and same
        lines.append(
            f"  {w['symbol']:12} {w['crypto_id']:>6}  committed {w['status']:10} live {live:10} "
            f"{'=' if same else '≠ (the market moved)'}"
        )
    return ok, lines, meta
