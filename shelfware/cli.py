"""shelfware — the command line.

    shelfware MS                 the ticker question (status leg live + keyless; roster live with a key)
    shelfware census             the full live census — needs a free key, ~5 credits
    shelfware verify [--live]    recount every headline from the committed rows
    shelfware delta              what changed between the two most recent daily snapshots

exit codes: 0 ok · 1 failure · 75 (EX_TEMPFAIL) the keyless pool is exhausted — retry, or
export a free key
"""

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from shelfware import __version__
from shelfware.client import EX_TEMPFAIL, Client, NoKey, api_key
from shelfware.delta import delta as diff
from shelfware.join import UNTRACKED_DEFINITION, census, is_shelf
from shelfware.lookup import lookup, roster_snapshot_from
from shelfware.verify import (
    JQ_RECIPE,
    compare_counts,
    headline_numbers,
    live_check,
    load_census,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROOF = ROOT / "docs" / "proof"
SNAPSHOTS = DATA / "snapshots"
SUBCOMMANDS = ("census", "verify", "delta")

HELP = f"""usage: shelfware [-h] {{census,verify,delta}} | TICKER
Shelfware {__version__} — which tokenised stocks on CoinMarketCap actually have a market.
  TICKER          e.g. MS, NVDA, GILD — prints every wrapper, its issuer, chain and CMC listing state
  census          enumerate every tokenised underlying, join, count (keyed, ~5 credits)
  verify          re-derive the headline numbers from the committed census by counting rows
  delta           what changed between the two most recent daily snapshots
env: CMC_API_KEY (optional for TICKER, required for census) · SHELFWARE_SNAPSHOT (override data path)
exit: 0 ok · 1 failure · 75 keyless pool exhausted (retry, or export a free key)
"""


def _fmt(x, dp=0):
    return "null" if x is None else f"{x:,.{dp}f}"


def _load_roster_snapshot():
    """data/roster_snapshot.json, or the file SHELFWARE_SNAPSHOT points at."""
    p = Path(os.environ.get("SHELFWARE_SNAPSHOT") or DATA / "roster_snapshot.json")
    return json.loads(p.read_text()) if p.exists() else None


def compact(doc):
    """A daily snapshot keeps counts, tables and a slim row per wrapper — enough to diff."""
    keep = (
        "crypto_id",
        "symbol",
        "underlying",
        "rwa_id",
        "issuer_name",
        "status",
        "price",
        "market_cap",
    )
    return {
        **{k: v for k, v in doc.items() if k not in ("wrappers", "issuers_registry")},
        "wrappers": [{k: w.get(k) for k in keep} for w in doc["wrappers"]],
    }


# ── TICKER ─────────────────────────────────────────────────────────────────────


def cmd_ticker(ticker, json_out=None, out=sys.stdout):
    client = Client(api_key=api_key())
    res = lookup(ticker, client, _load_roster_snapshot())
    p = lambda s="": print(s, file=out)  # noqa: E731
    p(f"shelfware {res['ticker']} — does it have a wrapper that trades, and whose?\n")
    r, s = res["roster"], res["status"]
    roster_src = (
        "live (1 credit)"
        if r["source"] == "live"
        else f"snapshot {r['as_of'] or '?'} (the RWA endpoints need a key; export CMC_API_KEY to go live"
        + (f"; live call failed: {r['fallback_reason']}" if r["fallback_reason"] else "")
        + ")"
    )
    as_of = (res["roster"].get("as_of") or "")[:10]

    def status_src(w):
        src = w.get("status_source")
        if src == "map":
            return "/public-api/v1/cryptocurrency/map, live, keyless, 0 credits"
        if src == "info":
            return "/public-api/v2/cryptocurrency/info, live, keyless (the map's symbol filter rejects this symbol)"
        if src == "info+snapshot":
            return (
                f"/public-api/v2/cryptocurrency/info says inactive, live, keyless; the map's finer state "
                f'is from the {as_of} snapshot (its symbol filter rejects "{w.get("symbol")}")'
            )
        return f"snapshot {as_of} — {s['fallback_reason']}"

    for u in res["underlyings"]:
        p(
            f"  {u['symbol']}  {u.get('name') or ''} · {u.get('asset_type')} · rwa_rank "
            f"{u.get('rwa_rank')} · has_tokens: {str(u.get('has_tokens')).lower()}"
        )
    p(f"      roster: {roster_src}")
    for w in res["wrappers"]:
        pl = w.get("platform") or {}
        p(
            f"      {'▒' if is_shelf(w) else '▓' if w['status'] == 'active' else '?'} {w['symbol']}  {w.get('name') or ''}"
        )
        p(f"          issuer   {w.get('issuer_name') or '(no issuer)'}  {w.get('issuer_id') or ''}")
        p(f"          chain    {pl.get('name') or '—'}  {pl.get('token_address') or ''}")
        p(
            f"          price    {_fmt(w.get('price'), 4)} · market_cap {_fmt(w.get('market_cap'))} · "
            f"volume_24h {_fmt(w.get('volume_24h'))}"
        )
        p(f"          status   {w['status'].upper()}      ← {status_src(w)}")
        if is_shelf(w):
            p(f'                   "listed, no CMC-tracked market" — CMC: {UNTRACKED_DEFINITION}')
            if w.get("date_added"):
                born = datetime.fromisoformat(w["date_added"].replace("Z", "+00:00"))
                days = (datetime.now(UTC) - born).days
                p(
                    f"                   listed {w['date_added'][:10]} (date_added) · {days} days on the shelf"
                )
        elif w["status"] == "active":
            p(f"                   tracked since {(w.get('first_historical_data') or '?')[:10]}")
        elif w["status"] == "unresolved":
            p("                   this id is in tokens[] but not in the map — not counted as shelf")
    p(f"\n  {res['verdict']}")
    calls = [m for m in (r["call"], s["call"], *(s.get("info_calls") or [])) if m]
    if calls:
        p(
            "\nreceipt: "
            + "  |  ".join(
                f"{m['call']} → HTTP {m['http']} · "
                f"{'keyed · ' + str(m.get('credit_count') or 0) + ' credit' if m['keyed'] else 'keyless · 0 credits to any key'} · "
                f"{m['elapsed_ms']} ms · sha256 {m['sha256']}"
                for m in calls
            )
        )
    if json_out:
        Path(json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(json_out).write_text(json.dumps(res, indent=2))
        p(f"wrote {json_out}")
    if res["temporary_failure"]:
        p(
            "\nthe anonymous pool is exhausted for this IP — wait a few minutes, or export a free key",
        )
        return EX_TEMPFAIL
    return 0


# ── census ─────────────────────────────────────────────────────────────────────


def run_census(client, out=sys.stdout, now=None):
    """A + B + C + D live, then the join. Returns the census document."""
    p = lambda s="": print(s, file=out)  # noqa: E731
    t0 = time.time()
    before = client.key_info()
    p("1. /v5/real-world-assets/map (keyed, 0 credits)")
    rwa = client.rwa_map()
    has_tokens = [r for r in rwa if r.get("has_tokens")]
    p(f"   {len(rwa):,} underlyings · {len(has_tokens):,} has_tokens")
    p("2. /v5/real-world-assets/quotes/latest tokens[] (keyed, 1 credit / 250 assets)")
    assets, _ = client.rwa_quotes(rwa_ids=[r["rwa_id"] for r in has_tokens])
    p(f"   {sum(len(a.get('tokens') or []) for a in assets):,} wrappers")
    p("3. /v5/real-world-assets/issuers/list (keyed, 1 credit)")
    issuers = client.issuers()
    p(f"   {len(issuers)} issuers")
    p("4. /public-api/v1/cryptocurrency/map active,inactive,untracked (keyless, 0 credits)")
    cmc, _, _ = client.cmc_map()
    p(f"   {len(cmc):,} rows")
    # the paged map omits rows the symbol filter returns (VVV 40784, 2026-09-18): ask again by
    # symbol for whatever did not resolve, so 'unresolved' means CMC has no row, not that we
    # paged past one
    ids_in_roster = {t.get("crypto_id") for a in assets for t in a.get("tokens") or []}
    missing = [
        t.get("symbol")
        for a in assets
        for t in a.get("tokens") or []
        if t.get("crypto_id") not in cmc and t.get("symbol")
    ]
    if missing:
        more, _, _ = client.cmc_map(missing)
        found = {k: v for k, v in more.items() if k in ids_in_roster and k not in cmc}
        cmc.update(found)
        p(f"   +{len(found)} resolved by symbol that the paged map omitted")
    p("5. /public-api/v2/cryptocurrency/info date_added for the shelf (keyless, 0 credits)")
    shelf_ids = [
        t.get("crypto_id")
        for a in assets
        for t in a.get("tokens") or []
        if (cmc.get(t.get("crypto_id")) or {}).get("status") != "active"
    ]
    info, _, dropped = client.cmc_info(shelf_ids)
    p(f"   {len(info):,} listing dates · {len(dropped)} ids CMC does not know")
    after = client.key_info()
    doc = census(
        rwa,
        assets,
        cmc,
        issuers,
        info=info,
        receipt=client.receipt,
        now=now,
        wall_clock_s=round(time.time() - t0, 1),
    )
    doc["key_usage"] = {"before": before, "after": after}
    doc["_rwa_rows"] = rwa  # not written to census.json; used for the roster snapshot
    return doc


def print_census(doc, out=sys.stdout):
    p = lambda s="": print(s, file=out)  # noqa: E731
    c = doc["counts"]
    p("\njoin")
    p(
        f"  wrappers {c['wrappers']:,}: active {c['active']} · untracked {c['untracked']} · "
        f"inactive {c['inactive']} · unresolved {c['unresolved']}"
        f"  → {c['untracked'] / c['wrappers']:.1%} on the shelf"
    )
    p(
        f"  underlyings with has_tokens {c['has_tokens']}: {c['underlyings_zero_tracked']} have no "
        f"wrapper with a CMC-tracked market  → {c['underlyings_zero_tracked'] / c['has_tokens']:.1%}"
        f"   (loose rule, no active wrapper: {c['underlyings_zero_tracked_loose']})"
    )
    a = doc["age_tracked_days"]
    p(
        f"  what trades is young: median {a['median']} d · p10 {a['p10']} · p90 {a['p90']} (n={a['n']})"
    )
    if doc.get("hero"):
        h = doc["hero"]
        p(f"  hero by rule ({h['rule']}): {h['symbol']} rwa_rank {h['rwa_rank']}")
    p("\n  issuer                        declared attached tracked  shelf   live market cap")
    for e in [e for e in doc["by_issuer"] if e["attached"] >= 5][:12]:
        p(
            f"  {str(e['issuer_name'])[:29]:29} {str(e['declared'] or '—'):>8} {e['attached']:>8} "
            f"{e['tracked']:>7}  {e['shelf_rate']:>5.0%}   ${e['live_market_cap_usd']:,.0f}"
        )
    p(
        "\n  by type: "
        + " · ".join(
            f"{e['asset_type']} {e['shelf_rate']:.0%} shelf ({e['untracked']}/{e['attached']})"
            for e in doc["by_type"]
        )
    )
    p(
        f"\n{doc['wall_clock_s']} s · {doc['keyed_calls']} keyed calls = {doc['credits_used']} credits · "
        f"{doc['keyless_calls']} keyless calls = 0 credits to any key"
    )


def write_census(
    doc, census_path=DATA / "census.json", receipt_path=PROOF / "live_run.json", out=sys.stdout
):
    p = lambda s="": print(s, file=out)  # noqa: E731
    rwa_rows = doc.pop("_rwa_rows", [])
    census_path.parent.mkdir(parents=True, exist_ok=True)
    census_path.write_text(json.dumps(doc, indent=1))
    p(f"wrote {census_path.relative_to(ROOT)}")
    roster = roster_snapshot_from(doc, rwa_rows)
    (DATA / "roster_snapshot.json").write_text(json.dumps(roster, separators=(",", ":")))
    p(
        f"wrote data/roster_snapshot.json ({len(roster['underlyings'])} underlyings with tokens, {len(roster['no_tokens'])} without)"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(
            {
                "_note": "Every call of the committed census, verbatim meta: URL, HTTP, credit_count, sha256, UTC.",
                "generated_utc": doc["generated_utc"],
                "wall_clock_s": doc["wall_clock_s"],
                "credits_used": doc["credits_used"],
                "keyed_calls": doc["keyed_calls"],
                "keyless_calls": doc["keyless_calls"],
                "counts": doc["counts"],
                "age_tracked_days": doc["age_tracked_days"],
                "age_untracked_days": doc["age_untracked_days"],
                "hero": doc["hero"],
                "key_usage": doc.get("key_usage"),
                "receipt": doc["receipt"],
            },
            indent=1,
        )
    )
    p(f"wrote {receipt_path.relative_to(ROOT)}")
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    day = doc["generated_utc"][:10]
    snap = SNAPSHOTS / f"{day}.json"
    snap.write_text(json.dumps(compact(doc), indent=1))
    p(f"wrote {snap.relative_to(ROOT)}")
    write_delta(out)


def write_delta(out=sys.stdout):
    files = sorted(SNAPSHOTS.glob("*.json"))
    if len(files) < 2:
        print(f"delta: {len(files)} snapshot(s) — the delta panel needs two", file=out)
        return None
    before, after = (json.loads(f.read_text()) for f in files[-2:])
    d = diff(before, after)
    (DATA / "delta.json").write_text(json.dumps(d, indent=1))
    print(
        f"delta {files[-2].stem} → {files[-1].stem}: +{d['newly_tracked']} newly tracked · "
        f"+{d['newly_shelved']} newly shelved · +{d['new_wrappers']} new wrappers · "
        f"-{d['gone_wrappers']} gone",
        file=out,
    )
    return d


def cmd_census(argv, out=sys.stdout):
    ap = argparse.ArgumentParser(prog="shelfware census")
    ap.add_argument("--out", default=str(DATA / "census.json"))
    ap.add_argument("--receipt", default=str(PROOF / "live_run.json"))
    a = ap.parse_args(argv)
    key = api_key()
    if not key:
        print(
            "shelfware census needs a key — the RWA endpoints are keyed by CoinMarketCap "
            "(keyless → 403 error 1005). Export CMC_API_KEY (a free Basic key is enough, ~5 credits), "
            "or read the committed run: python3 -m shelfware verify",
            file=out,
        )
        return 1
    client = Client(api_key=key)
    print("shelfware census — keyed (A, B, C) + keyless (D), live\n", file=out)
    try:
        doc = run_census(client, out=out)
    except NoKey as e:
        print(str(e), file=out)
        return 1
    except RuntimeError as e:
        print(f"census failed: {e}", file=out)
        return EX_TEMPFAIL if "transient" in str(e) else 1
    print_census(doc, out=out)
    write_census(doc, Path(a.out), Path(a.receipt), out=out)
    return 0


# ── verify ─────────────────────────────────────────────────────────────────────


def cmd_verify(argv, out=sys.stdout):
    ap = argparse.ArgumentParser(prog="shelfware verify")
    ap.add_argument("--live", action="store_true", help="re-fetch 10 statuses keyless and compare")
    ap.add_argument("--census", default=str(DATA / "census.json"))
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args(argv)
    p = lambda s="": print(s, file=out)  # noqa: E731
    doc = load_census(a.census)
    h = headline_numbers(doc)
    p(
        f"verify — recounting data/census.json ({doc['generated_utc']}) from its {h['wrappers']:,} rows\n"
    )
    ok, findings = compare_counts(doc)
    p(
        f"  {h['zero_tracked']} of {h['has_tokens']} tokenised underlyings have no wrapper with a "
        f"CMC-tracked market ({h['share_pct']}%) · {h['untracked']} of {h['wrappers']} wrappers untracked"
    )
    for f in findings:
        p(f"  DRIFT: {f}")
    p("  counts == recount from rows" if ok else f"  {len(findings)} drift(s)")
    p("\nby hand:\n  " + JQ_RECIPE.replace("\n", "\n  "))
    rc = 0 if ok else 1
    if a.live:
        p("\nlive — 10 statuses re-fetched keyless from /public-api/v1/cryptocurrency/map:")
        lok, lines, meta = live_check(doc, Client(api_key=None), seed=a.seed)
        for line in lines:
            p(line)
        if lok is None:
            rc = EX_TEMPFAIL if (meta or {}).get("throttled") else 1
        elif not lok:
            p("  a status moved since the census was cut — the market moves; re-run the census")
    return rc


# ── delta ──────────────────────────────────────────────────────────────────────


def cmd_delta(argv, out=sys.stdout):
    files = sorted(SNAPSHOTS.glob("*.json"))
    if len(files) < 2:
        print(f"delta needs two snapshots in data/snapshots/, found {len(files)}", file=out)
        return 1
    d = write_delta(out)
    for f in d["flips"][:20]:
        print(
            f"  {f['symbol'] or f['crypto_id']:12} {f['underlying'] or '':8} {f['before']} → {f['after']}  ({f['issuer_name']})",
            file=out,
        )
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(HELP, end="")
        return 0
    if argv[0] == "--version":
        print(f"shelfware {__version__}")
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "census":
        return cmd_census(rest)
    if cmd == "verify":
        return cmd_verify(rest)
    if cmd == "delta":
        return cmd_delta(rest)
    ap = argparse.ArgumentParser(prog="shelfware", add_help=False)
    ap.add_argument("ticker")
    ap.add_argument("--json", metavar="PATH", default=None)
    a = ap.parse_args(argv)
    return cmd_ticker(a.ticker, a.json)


if __name__ == "__main__":
    sys.exit(main())
