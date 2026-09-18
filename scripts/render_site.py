#!/usr/bin/env python3
"""Render site/index.html from data/census.json (+ delta.json, docs/proof/ms.json).

    python3 scripts/render_site.py            # write site/index.html and data/health.json
    python3 scripts/render_site.py --check    # exit 1 if what is on disk is not this render

Every number on the page comes from the committed census — a real keyed run whose receipt is
docs/proof/live_run.json. The template uses {{slots}}; the render fails if any slot is left
unfilled, so a placeholder can never reach the page and a number can never be typed in by
hand. site/index.html is generated output: edit the template or the census, never the page.
"""

import json
import re
import sys
import urllib.parse
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfware.join import UNTRACKED_DEFINITION, type_underlyings  # noqa: E402
from shelfware.verify import JQ_RECIPE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "scripts" / "site_templates"
SITE = ROOT / "site"
DATA = ROOT / "data"
HEALTH_OUT = DATA / "health.json"
PROOF = ROOT / "docs" / "proof"
REPO = "https://github.com/edycutjong/shelfware"
SITE_URL = "https://shelfware-cmc.vercel.app"
DOTTED = re.compile(r"^[A-Za-z0-9]+$")

LOGO = (
    '<svg viewBox="0 0 34 22" aria-hidden="true"><rect x="0" y="17" width="34" height="2" rx="1" fill="#26313F"/>'
    '<rect x="1" y="4" width="5" height="12" rx="1.5" fill="#3A4453"/><rect x="8" y="4" width="5" height="12" rx="1.5" fill="#3A4453"/>'
    '<rect x="15" y="4" width="5" height="12" rx="1.5" fill="#3A4453"/><rect x="22" y="4" width="5" height="12" rx="1.5" fill="#3BD37D"/>'
    '<rect x="29" y="4" width="5" height="12" rx="1.5" fill="#3BD37D"/></svg>'
)
FAVICON = urllib.parse.quote(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 34 22"><rect width="34" height="22" fill="#0B0F14"/>'
    + LOGO.split('aria-hidden="true">', 1)[1].rsplit("</svg>", 1)[0]
    + "</svg>"
)


def money(x):
    if not x:
        return "$0"
    if x >= 1e9:
        return f"${x / 1e9:.2f}B"
    if x >= 1e6:
        return f"${x / 1e6:.0f}M"
    return f"${x:,.0f}"


def bar(lit, dim, unk=0, small=True, label=""):
    total = lit + dim + unk
    if not total:
        return f'<div class="bar{" small" if small else ""}" role="img" aria-label="{escape(label)}"></div>'
    p = lambda n: f"{100 * n / total:.1f}%"  # noqa: E731
    return (
        f'<div class="bar{" small" if small else ""}" role="img" aria-label="{escape(label)}">'
        f'<span class="dim" style="width:{p(dim)}"></span><span class="lit" style="width:{p(lit)}"></span>'
        f'<span class="unk" style="width:{p(unk)}"></span></div>'
    )


def issuer_row(e, registry):
    rate = e["shelf_rate"]
    rate_html = (
        f'<span class="rate{" full" if rate == 1.0 else ""}">{rate:.0%}</span>'
        if rate is not None
        else '<span class="rate">—</span>'
    )
    raw = next((r for r in registry if r.get("issuer_id") == e["issuer_id"]), None)
    label = f"{e['issuer_name']}: {e['tracked']} tracked, {e['untracked']} untracked, {e['inactive'] + e['unresolved']} other of {e['attached']}"
    drawer = (
        f"<details><summary>{escape(str(e['issuer_name']))}</summary>"
        f'<p class="ev">/v5/real-world-assets/issuers/list row</p><pre>{escape(json.dumps(raw, indent=1))}</pre>'
        f'<p class="ev">joined row</p><pre>{escape(json.dumps({k: v for k, v in e.items()}, indent=1))}</pre></details>'
    )
    return (
        f'<tr class="issuer"><td class="issuer-name">{drawer}</td>'
        f'<td class="barcell">{bar(e["tracked"], e["untracked"], e["inactive"] + e["unresolved"], label=label)}</td>'
        f'<td class="n">{rate_html}</td><td class="n hide-m">{e["declared"] if e["declared"] is not None else "—"}</td>'
        f'<td class="n">{e["attached"]}</td><td class="n">{e["tracked"]}</td><td class="n hide-m">{money(e["live_market_cap_usd"])}</td></tr>'
    )


def type_card(t, u):
    label = f"{t['asset_type']}: {t['untracked']} of {t['attached']} wrappers untracked"
    b = bar(t["tracked"], t["untracked"], t["other"], label=label)
    return (
        f'<div class="card"><div class="t"><span>{escape(t["asset_type"])}</span><b>{t["shelf_rate"]:.0%} shelf</b></div>{b}'
        f'<p class="sub" style="margin-top:8px"><b class="mono">{t["untracked"]}</b> of {t["attached"]} wrappers untracked · '
        f'<b class="mono">{u["zero_tracked"]}</b> of {u["underlyings"]} underlyings with no tracked wrapper ({u["share"]:.0%})</p></div>'
    )


def delta_html():
    p = DATA / "delta.json"
    snaps = sorted(x.stem for x in (DATA / "snapshots").glob("*.json"))
    if not p.exists() or len(snaps) < 2:
        return (
            f'<p class="sub">The delta panel appears once two daily snapshots exist. Series so far: <b class="mono">{", ".join(snaps) or "none"}</b> '
            f'(taken by <span class="mono">scripts/snapshot.py</span>, ~5 keyed credits a day; untracked rows carry no dates of their own).</p>'
        )
    d = json.loads(p.read_text())
    flips = "".join(
        f'<li><span class="mono">{escape(str(f["symbol"] or f["crypto_id"]))}</span> ({escape(str(f["underlying"] or ""))}, {escape(str(f["issuer_name"] or ""))}): {f["before"]} → {f["after"]}</li>'
        for f in d["flips"][:20]
    )
    return (
        f'<div class="stat"><div><div class="v">+{d["newly_tracked"]}</div><div class="l">newly tracked (untracked → active)</div></div>'
        f'<div><div class="v">+{d["newly_shelved"]}</div><div class="l">newly shelved (active → untracked)</div></div>'
        f'<div><div class="v">+{d["new_wrappers"]}</div><div class="l">new wrappers · {d["gone_wrappers"]} gone · {d["other_flips"]} other flips</div></div></div>'
        f'<p class="sub" style="margin-top:10px"><span class="mono">{escape(d["from"])}</span> → <span class="mono">{escape(d["to"])}</span> · '
        f"wrappers {d['counts_before']['wrappers']} → {d['counts_after']['wrappers']} · untracked {d['counts_before']['untracked']} → {d['counts_after']['untracked']}</p>"
        + (f'<ul class="limits">{flips}</ul>' if flips else "")
    )


def receipt_rows(receipt):
    groups = {}
    for m in receipt:
        key = m["url"].split("?")[0].replace("https://pro-api.coinmarketcap.com", "")
        g = groups.setdefault(
            key,
            {
                "calls": 0,
                "http": set(),
                "credits": 0,
                "bytes": 0,
                "sha": m["sha256"],
                "keyed": m["keyed"],
            },
        )
        g["calls"] += 1
        g["http"].add(str(m["http"]))
        g["credits"] += int(m.get("credit_count") or 0) if m["keyed"] else 0
        g["bytes"] += m["bytes"]
    rows = []
    for k, g in groups.items():
        tag = "" if g["keyed"] else ' <span class="pill off">keyless</span>'
        credits = g["credits"] if g["keyed"] else "0 to any key"
        rows.append(
            f'<tr><td class="mono">{escape(k)}{tag}</td><td class="n">{g["calls"]}</td>'
            f'<td class="n">{escape(",".join(sorted(g["http"])))}</td><td class="n">{credits}</td>'
            f'<td class="n hide-m">{g["bytes"]:,}</td><td class="mono hide-m">{escape(g["sha"])}</td></tr>'
        )
    return "".join(rows)


def hero_run():
    """docs/proof/ms.json (the CLI's real keyless run) in the shape the page renders."""
    p = PROOF / "ms.json"
    if not p.exists():
        return None
    r = json.loads(p.read_text())
    calls = []
    for m in [
        r["roster"].get("call"),
        r["status"].get("call"),
        *(r["status"].get("info_calls") or []),
    ]:
        if m:
            calls.append(
                {
                    "call": m["call"],
                    "http": m["http"],
                    "keyed": m["keyed"],
                    "credit_count": m["credit_count"],
                    "elapsed_ms": m["elapsed_ms"],
                    "sha256": m["sha256"],
                    "fetched_utc": m["utc"],
                }
            )
    return {
        "ticker": r["ticker"],
        "asked_utc": r["asked_utc"],
        "roster": r["roster"],
        "status": r["status"],
        "underlyings": r["underlyings"],
        "wrappers": r["wrappers"],
        "verdict": r["verdict"],
        "evidence": r["evidence"],
        "calls": calls,
    }


def render():
    doc = json.loads((DATA / "census.json").read_text())
    c, a, s = doc["counts"], doc["age_tracked_days"], doc["age_untracked_days"]
    tu = {e["asset_type"]: e for e in type_underlyings(doc["wrappers"])}
    stock = tu.get("stock", {"zero_tracked": 0, "underlyings": 0, "share": 0})
    share = round(100 * c["underlyings_zero_tracked"] / c["has_tokens"])
    big = [e for e in doc["by_issuer"] if e["attached"] >= 5]
    small = [e for e in doc["by_issuer"] if e["attached"] < 5]
    chains = doc["chains_of_untracked"]
    dotted = sum(1 for w in doc["wrappers"] if w.get("symbol") and not DOTTED.match(w["symbol"]))
    backed = next(
        (e for e in doc["by_issuer"] if e["issuer_name"] == "Backed Assets"),
        {"declared": "?", "attached": "?"},
    )
    usage = doc.get("key_usage") or {}
    cm = lambda k: ((usage.get(k) or {}).get("current_month") or {}).get("credits_used")  # noqa: E731
    hero = hero_run()
    slots = {
        "share_pct": share,
        "lit_pct": 100 - share,
        "zero_tracked": c["underlyings_zero_tracked"],
        "has_tokens": c["has_tokens"],
        "with_tracked": c["has_tokens"] - c["underlyings_zero_tracked"],
        "stock_zero": stock["zero_tracked"],
        "stock_under": stock["underlyings"],
        "stock_pct": round(100 * (stock["share"] or 0)),
        "untracked": c["untracked"],
        "wrappers": c["wrappers"],
        "generated_utc": doc["generated_utc"],
        "generated_short": doc["generated_utc"].replace("T", " ").replace("Z", "")[:16],
        "credits": doc["credits_used"],
        "keyed_calls": doc["keyed_calls"],
        "keyless_calls": doc["keyless_calls"],
        "wall_clock": doc["wall_clock_s"],
        "usage_before": cm("before") if cm("before") is not None else "—",
        "usage_after": cm("after") if cm("after") is not None else "—",
        "hero_symbol": (doc.get("hero") or {}).get("symbol") or "MS",
        "hero_card": '<noscript><p class="src">Enable JavaScript to ask, or run <code>python3 -m shelfware MS</code>.</p></noscript>',
        "issuer_rows": "".join(issuer_row(e, doc["issuers_registry"]) for e in big),
        "issuer_rows_small": "".join(issuer_row(e, doc["issuers_registry"]) for e in small),
        "n_smaller": len(small),
        "type_cards": "".join(
            type_card(t, tu.get(t["asset_type"], {"zero_tracked": 0, "underlyings": 0, "share": 0}))
            for t in doc["by_type"]
        ),
        "delta_html": delta_html(),
        "age_median": a["median"],
        "age_p10": a["p10"],
        "age_p90": a["p90"],
        "age_n": a["n"],
        "shelf_median": s["median"],
        "shelf_p10": s["p10"],
        "shelf_p90": s["p90"],
        "shelf_n": s["n"],
        "top_chain_n": chains[0]["wrappers"] if chains else 0,
        "top_chain": chains[0]["chain"] if chains else "—",
        "chains_rest": ", ".join(f"{x['chain']} {x['wrappers']}" for x in chains[1:5]),
        "definition": UNTRACKED_DEFINITION,
        "unresolved": c["unresolved"],
        "unresolved_list": ", ".join(
            f"{u['crypto_id']} {u['underlying']}" for u in doc["unresolved"]
        ),
        "dotted": dotted,
        "backed_declared": backed["declared"],
        "backed_attached": backed["attached"],
        "receipt_rows": receipt_rows(doc["receipt"]),
        "jq": JQ_RECIPE,
        "repo": REPO,
        "site_url": SITE_URL,
        "logo": LOGO,
        "favicon": FAVICON,
        "inline_json": json.dumps(
            {
                "definition": UNTRACKED_DEFINITION,
                "generated_utc": doc["generated_utc"],
                "hero_run": hero,
            },
            separators=(",", ":"),
        ),
        "app_js": (TEMPLATES / "app.js").read_text().rstrip(),
    }
    html = (TEMPLATES / "index.html").read_text()
    for k, v in slots.items():
        html = html.replace(
            "{{" + k + "}}",
            str(v)
            if k
            in (
                "logo",
                "favicon",
                "inline_json",
                "app_js",
                "hero_card",
                "issuer_rows",
                "issuer_rows_small",
                "type_cards",
                "delta_html",
                "receipt_rows",
                "jq",
            )
            or not isinstance(v, str)
            else escape(v),
        )
    left = re.findall(r"\{\{[a-z_]+\}\}", html)
    if left:
        sys.exit(f"unfilled slots: {sorted(set(left))}")
    health = {
        "census_utc": doc["generated_utc"],
        "snapshots": sorted(x.stem for x in (DATA / "snapshots").glob("*.json")),
        "counts": {
            k: c[k] for k in ("has_tokens", "wrappers", "untracked", "underlyings_zero_tracked")
        },
        "hero": (doc.get("hero") or {}).get("symbol"),
    }
    return html, json.dumps(health, indent=1)


def main():
    check = "--check" in sys.argv
    html, health = render()
    targets = {SITE / "index.html": html, HEALTH_OUT: health}
    if check:
        stale = [
            str(p.relative_to(ROOT))
            for p, want in targets.items()
            if not p.exists() or p.read_text() != want
        ]
        if stale:
            print(
                f"drift: {', '.join(stale)} is not what the census renders — run: python3 scripts/render_site.py"
            )
            return 1
        print("site/index.html and data/health.json match the census")
        return 0
    SITE.mkdir(exist_ok=True)
    for p, content in targets.items():
        p.write_text(content)
        print(f"wrote {p.name} ({len(content):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
