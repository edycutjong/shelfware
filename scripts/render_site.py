#!/usr/bin/env python3
"""Render site/index.html, site/judge/index.html and site/pitch/index.html from data/census.json
(+ delta.json, docs/proof/ms.json, docs/proof/bench.json, docs/proof/live_run.json, JUDGE.md).

    python3 scripts/render_site.py            # write the three pages and data/health.json
    python3 scripts/render_site.py --check    # exit 1 if what is on disk is not this render

Every number on the page comes from the committed census — a real keyed run whose receipt is
docs/proof/live_run.json — or from the committed keyless run docs/proof/ms.json. The template
uses {{slots}}; the render fails if any slot is left unfilled, so a placeholder can never reach
the page and a number can never be typed in by hand. site/index.html is generated output: edit
the template or the census, never the page.
"""

import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
from datetime import UTC, datetime
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import md2html  # noqa: E402

from shelfware.cli import answer_lines  # noqa: E402
from shelfware.join import UNTRACKED_DEFINITION, is_shelf, recount, type_underlyings  # noqa: E402
from shelfware.verify import JQ_RECIPE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "scripts" / "site_templates"
SITE = ROOT / "site"
DATA = ROOT / "data"
HEALTH_OUT = DATA / "health.json"
PROOF = ROOT / "docs" / "proof"
JUDGE_MD = ROOT / "JUDGE.md"
README_MD = ROOT / "README.md"
FEEDBACK_MD = ROOT / "FEEDBACK.md"
JUDGE_OUT = SITE / "judge" / "index.html"
PITCH_OUT = SITE / "pitch" / "index.html"
REPO = "https://github.com/edycutjong/shelfware"
# The canonical host. The same site/ is served by Vercel (with the api/ functions) and, once the
# repository is public, by GitHub Pages at PAGES_URL (static; its page calls the Vercel functions
# cross-origin). Flip SITE_URL to PAGES_URL after the DNS record and the Pages site exist.
SITE_URL = "https://shelfware-cmc.vercel.app"
PAGES_URL = "https://shelfware.edycu.dev"
# Where the api/ functions run, always: the page fetches them same-origin on Vercel and at this
# absolute URL from any other host (GitHub Pages), so the search works on both.
API_URL = "https://shelfware-cmc.vercel.app"
EVENT = "https://dorahacks.io/hackathon/coinmarketcap-api-202609/detail"
AUTHOR = "Edy Cu"
X_HANDLE = "@edycutjong"
OG_IMAGE = SITE / "og-image.png"
# Public-page fixtures that are not numbers: test counts as README states them, and the QR that
# encodes SITE_URL/judge (generated once with segno; static so the render needs no dependency).
TESTS = {"offline": 104, "node": 11, "live": 6}
QR_SVG = TEMPLATES / "qr-judge.svg"
DOTTED = re.compile(r"^[A-Za-z0-9]+$")
# Every endpoint the client calls, in the order the census calls them; the API table on the
# landing page is rendered from this list with the call counts read off the receipts. The row
# marked engine is one the product cannot exist without; the last row was tried and refused.
ENDPOINTS = [
    (
        "/v5/real-world-assets/map",
        "the universe — every underlying, has_tokens, rwa_rank, asset_type",
        "keyed · 0 credits",
        "",
    ),
    (
        "/v5/real-world-assets/quotes/latest",
        "tokens[] — the wrapper roster including the price: null rows the RWA pages hide; issuer_id and crypto_id per wrapper",
        "keyed · 1 credit / 250 assets",
        "engine",
    ),
    (
        "/v5/real-world-assets/issuers/list",
        "the issuer registry with its declared num_tokens",
        "keyed · 1 credit",
        "",
    ),
    (
        "/public-api/v1/cryptocurrency/map",
        "listing state per wrapper across active, inactive, untracked; platform and address — the join's other half",
        "none",
        "engine",
    ),
    (
        "/public-api/v2/cryptocurrency/info",
        "date_added — the day a shelf wrapper was listed; state for the dotted symbols the map filter rejects",
        "none",
        "",
    ),
    (
        "/v1/key/info",
        "the credit ledger before and after a census, so the receipt's credit count is CoinMarketCap's, not ours",
        "keyed · 0 credits",
        "",
    ),
    (
        "/v5/real-world-assets/market-pairs/list",
        "not used — documented as Basic, answered 403 error 1006 on the Startup plan; tried, recorded in FEEDBACK.md §3, not built on",
        "plan-gated",
        "unused",
    ),
]

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


def version():
    """The deck's version stamp: the repository's latest tag, so the deck, the README's Release
    badge and the live app carry the same string. No tag yet reads v0.0.0-dev — an honest signal
    that no release exists, never a faked number. The CI check job clones with tags for this."""
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return out or "v0.0.0-dev"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "v0.0.0-dev"


def money(x):
    if not x:
        return "$0"
    if x >= 1e9:
        return f"${x / 1e9:.2f}B"
    if x >= 1e6:
        return f"${x / 1e6:.0f}M"
    return f"${x:,.0f}"


def og_version():
    """Cache-buster for the social card: sha1 of the image bytes, so a corrected card reaches
    feeds and an unchanged one keeps its cache."""
    return hashlib.sha1(OG_IMAGE.read_bytes()).hexdigest()[:8] if OG_IMAGE.exists() else "0"


def utc_short(ts):
    return str(ts).replace("T", " ").replace("Z", "")[:19]


def tagline():
    """The lede is the README's tagline verbatim — read, never retyped."""
    m = re.search(r"<p><em>(.+?)</em></p>", README_MD.read_text())
    return m.group(1) if m else "Counts the shelf."


def feedback_n():
    return len(re.findall(r"^## \d+\. ", FEEDBACK_MD.read_text(), re.M))


def property_cases():
    m = re.search(
        r"^PROPERTY_CASES\s*=\s*(\d+)", (ROOT / "tests" / "test_property.py").read_text(), re.M
    )
    return int(m.group(1)) if m else 0


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
    declared = f"{e['declared']:,}" if e["declared"] is not None else "—"
    return (
        f'<tr class="issuer"><td class="issuer-name">{drawer}</td>'
        f'<td class="barcell">{bar(e["tracked"], e["untracked"], e["inactive"] + e["unresolved"], label=label)}</td>'
        f'<td class="n">{rate_html}</td><td class="n hide-m">{declared}</td>'
        f'<td class="n">{e["attached"]:,}</td><td class="n">{e["tracked"]:,}</td><td class="n hide-m">{money(e["live_market_cap_usd"])}</td></tr>'
    )


def type_card(t, u):
    label = f"{t['asset_type']}: {t['untracked']} of {t['attached']} wrappers untracked"
    b = bar(t["tracked"], t["untracked"], t["other"], label=label)
    return (
        f'<div class="stat"><span class="stat-v">{t["shelf_rate"]:.0%}</span>'
        f'<span class="stat-l">{escape(t["asset_type"])} — <b>{t["untracked"]}</b> of {t["attached"]:,} wrappers on the shelf</span>{b}'
        f'<span class="stat-l"><b>{u["zero_tracked"]}</b> of {u["underlyings"]} {escape(t["asset_type"])} underlyings with no tracked wrapper ({u["share"]:.0%})</span></div>'
    )


def hero_viz(c, per_row=60, cls="desk"):
    """The frozen moment, drawn from the census counts: one box per underlying CoinMarketCap flags
    has_tokens: true, on shelves of sixty (thirty on a phone, so a box stays a box at 335 px),
    sorted shelf first. No text inside the SVG — the key beneath carries the numbers. A row of
    boxes is one rect filled with a pattern whose tile is one box, so a 791-box shelf is ~70
    elements; an amber overlay per row (the boolean, before the join) fades out row by row when
    the card scrolls into view (the CSS in the template, row delay = --i)."""
    n, shelf = c["has_tokens"], c["underlyings_zero_tracked"]
    gap = 4
    box = (1200 + gap) // per_row - gap
    pitch = box + 8
    rows = -(-n // per_row)
    height = rows * pitch + 12
    label = (
        f"{n} tokenised underlyings on CoinMarketCap as boxes on a shelf: {shelf} grey — no wrapper "
        f"with a CMC-tracked market — and {n - shelf} green with at least one."
    )
    tile = lambda kind: (  # noqa: E731
        f'<pattern id="p{kind}-{cls}" width="{box + gap}" height="{pitch}" patternUnits="userSpaceOnUse">'
        f'<rect y="6" width="{box}" height="{box}" rx="3" class="{kind}"/></pattern>'
    )
    parts = [
        f'<svg class="block {cls}" viewBox="0 0 1200 {height}" role="img" aria-label="{label}" xmlns="http://www.w3.org/2000/svg">',
        f"<title>{label}</title>",
        f"<defs>{tile('s')}{tile('t')}{tile('a')}</defs>",
    ]
    width = lambda k: k * (box + gap) - gap  # noqa: E731  — k boxes, the trailing gap cut off
    for r_ in range(rows):
        y = 6 + r_ * pitch
        first, in_row = r_ * per_row, min(n - r_ * per_row, per_row)
        n_shelf = max(0, min(in_row, shelf - first))
        parts.append(f'<g class="u" style="--i:{r_}">')
        segs = [(0, n_shelf, "s"), (n_shelf, in_row - n_shelf, "t")]
        for x0, k, kind in segs:
            if k:
                parts.append(
                    f'<rect x="{x0 * (box + gap)}" y="{y}" width="{width(k)}" height="{box}" fill="url(#p{kind}-{cls})"/>'
                )
        parts.append(
            f'<rect class="pre" x="0" y="{y}" width="{width(in_row)}" height="{box}" fill="url(#pa-{cls})"/>'
        )
        parts.append("</g>")
        parts.append(
            f'<line class="rail" x1="0" y1="{y + box + 3}" x2="{width(in_row)}" y2="{y + box + 3}"/>'
        )
    parts.append("</svg>")
    return "\n".join(parts), height


def wrapper_kind(w):
    if w.get("status") == "active":
        return "lit"
    if is_shelf(w):
        return "shelf"
    return "unknown"


def state_from(w, as_of):
    src = w.get("status_source")
    if src == "map":
        return "/v1/cryptocurrency/map · live · keyless"
    if src == "info":
        return (
            "/v2/cryptocurrency/info · live · keyless (the map's symbol filter rejects this symbol)"
        )
    if src == "info+snapshot":
        return f"/v2/cryptocurrency/info says inactive · live; the map's finer state from the {as_of} snapshot"
    return f"committed snapshot {as_of}"


def answer_ctx(res, doc):
    """docs/proof/ms.json → every slot of the product section, in the shapes app.js re-renders
    live: the context line, the headline, the wrapper table, the verdict, the raw rows, the
    receipt grid and the call list."""
    c = doc["counts"]
    r, s = res["roster"], res["status"]
    as_of = (r.get("as_of") or "")[:10]
    ws = res["wrappers"]
    tracked = sum(1 for w in ws if w.get("status") == "active")
    untracked = sum(1 for w in ws if is_shelf(w))
    other = len(ws) - tracked - untracked
    sym = escape(res["ticker"])
    u = res["underlyings"][0] if res["underlyings"] else None
    asked = utc_short(res["asked_utc"])
    roster_src = (
        "live via /api/roster · keyed · 1 credit"
        if r.get("source") == "live"
        else f"snapshot {as_of} (the RWA endpoints need a key)"
    )
    state_src = (
        "live · keyless · 0 credits"
        if s.get("source") == "live keyless"
        else escape(str(s.get("source")))
    )
    rule = (doc.get("hero") or {}).get("rule") or ""
    if u:
        context = (
            f"<b>{escape(u['symbol'])}</b> · {escape(u.get('name') or '')} · {escape(u.get('asset_type') or '')} · rwa_rank {u.get('rwa_rank')} · "
            f"has_tokens: <b>{str(u.get('has_tokens')).lower()}</b> · asked {asked} UTC · roster: {roster_src} · state: {state_src}"
            + (
                f" · chosen by rule: {escape(rule)}"
                if u["symbol"] == (doc.get("hero") or {}).get("symbol")
                else ""
            )
        )
    else:
        context = f"<b>{sym}</b> · not in CoinMarketCap's RWA map · asked {asked} UTC · roster: {roster_src}"
    if not ws:
        kind, share_num, share_text = "none", 0, "0 of 0"
        claim = (
            f"wrappers listed for <em>{sym}</em>."
            if u
            else f"<em>{sym}</em> is not in CoinMarketCap's RWA map."
        )
        support = escape(res.get("verdict") or "")
    else:
        kind = "lit" if tracked else "shelf"
        share_num, share_text = tracked, f"{tracked} of {len(ws)}"
        claim = f"wrapper{'s' if len(ws) != 1 else ''} of <em>{sym}</em> {'have' if len(ws) != 1 else 'has'} a CMC-tracked market."
        issuers = sorted({w.get("issuer_name") or "(no issuer)" for w in ws})
        support = (
            f"<b>{tracked}</b> active · <b>{untracked}</b> untracked · {other} unresolved or inactive — "
            f"issuer{'s' if len(issuers) != 1 else ''}: {escape(', '.join(issuers))}. "
            + (
                "The RWA map says <b>has_tokens: true</b>; the cryptocurrency map says <b>untracked</b> for every wrapper — listed, no CMC-tracked market."
                if kind == "shelf"
                else "Tracked means <b>status == active</b> on the cryptocurrency map; a wrapper with price: null is untracked, with 0 exceptions on the committed census."
            )
        )
    rows = []
    for w in ws:
        pl = w.get("platform") or {}
        k = wrapper_kind(w)
        rows.append(
            f'<tr class="{k}"><td class="pool">{escape(w.get("symbol") or "—")}<small>{escape(w.get("name") or "")}</small></td>'
            f'<td class="l">{escape(w.get("issuer_name") or "(no issuer)")}</td><td class="l">{escape(pl.get("name") or "—")}</td>'
            f'<td class="l mono addr">{escape(pl.get("token_address") or "—")}</td>'
            '<td class="mono">'
            + ("null" if w.get("price") is None else f"{w['price']:,.4f}")
            + "</td>"
            f'<td><span class="state {escape(w.get("status") or "unresolved")}">{escape(w.get("status") or "unresolved")}</span></td>'
            f'<td class="l src">{state_from(w, as_of)}</td>'
            f'<td class="mono">{escape((w.get("date_added") or w.get("first_historical_data") or "—")[:10])}</td></tr>'
        )
    if not ws:
        rows.append(
            f'<tr><td class="pool" colspan="8">{escape(res.get("verdict") or "no wrappers")}</td></tr>'
        )
    pair = f"{c['underlyings_zero_tracked']} of {c['has_tokens']}"
    if kind == "shelf":
        route_kind = "shelf"
        route_line = f"▶ {tracked} of {len(ws)} wrapper{'s' if len(ws) != 1 else ''} with a CMC-tracked market — on the shelf"
        route_rule = f"rule: strict — an underlying counts only when every attached wrapper is untracked · an unresolved id never counts · {sym} is one of the {pair}"
    elif kind == "lit":
        route_kind = "lit"
        route_line = f"▶ {tracked} of {len(ws)} wrapper{'s' if len(ws) != 1 else ''} with a CMC-tracked market"
        route_rule = f"rule: tracked = status == active on /v1/cryptocurrency/map · price == null ⇔ untracked, 0 exceptions on the committed census · {sym} is not one of the {pair}"
    else:
        route_kind = "none"
        route_line = f"▶ {escape(res.get('verdict') or 'no wrapper listed')}"
        route_rule = "rule: a wrapper must be in tokens[] on /v5/real-world-assets/quotes/latest to be counted at all"
    ev = res.get("evidence") or {}
    ids = ", ".join(str(w.get("crypto_id")) for w in ws) or "—"
    rows_title = f"{escape(', '.join(w.get('symbol') or '?' for w in ws) or sym)} — raw rows ({len(ws)} wrapper{'s' if len(ws) != 1 else ''}, three sources)"
    proof_link = (
        f' · <a href="{REPO}/blob/main/docs/proof/ms.json" target="_blank" rel="noopener noreferrer">docs/proof/ms.json<span class="arrow arrow-ext" aria-hidden="true">↗</span><span class="sr-only"> (opens in a new tab)</span></a>'
        if res.get("committed")
        else ""
    )
    roster_when = "live" if r.get("source") == "live" else "snapshot " + as_of
    rows_cap = (
        f"rwa_id {u['rwa_id'] if u else '—'} · crypto_id {escape(ids)} · tokens[] from "
        f'<span class="mono">/v5/real-world-assets/quotes/latest</span> ({roster_when}) · '
        'state from <span class="mono">/public-api/v1/cryptocurrency/map</span> · listing date from '
        f'<span class="mono">/public-api/v2/cryptocurrency/info</span>{proof_link}'
    )
    trs = []
    info_rows = ev.get("info_rows") or {}
    map_by_id = {m.get("id"): m for m in (ev.get("map_rows") or [])}
    for t in ev.get("tokens") or []:
        cid = t.get("crypto_id")
        trs.append(
            f'<tr><td>tokens[]</td><td>/v5/real-world-assets/quotes/latest</td><td class="mono">{cid}</td><td class="mono">{escape(t.get("symbol") or "null")}</td>'
            '<td class="mono">'
            + ("null" if t.get("price") is None else f"{t['price']:,.4f}")
            + f'</td><td>{escape(t.get("issuer_name") or "(no issuer)")}</td><td>{escape((t.get("platform") or {}).get("name") or "—")}</td><td class="mono">—</td></tr>'
        )
        m = map_by_id.get(cid)
        if m:
            k = (
                "leg"
                if m.get("status") == "untracked"
                else "lit"
                if m.get("status") == "active"
                else "unknown"
            )
            trs.append(
                f'<tr class="{k}"><td>map row</td><td>/public-api/v1/cryptocurrency/map</td><td class="mono">{m.get("id")}</td><td class="mono">{escape(m.get("symbol") or "")}</td>'
                f'<td class="mono">status {escape(m.get("status") or "")}</td><td>rank {escape("null" if m.get("rank") is None else str(m.get("rank")))}</td><td>{escape((m.get("platform") or {}).get("name") or "—")}</td><td class="mono">{escape((m.get("first_historical_data") or "—")[:10])}</td></tr>'
            )
        i = info_rows.get(str(cid)) if isinstance(info_rows, dict) else None
        if i is None and isinstance(info_rows, list):
            i = next((x for x in info_rows if x.get("id") == cid), None)
        if i:
            trs.append(
                f'<tr><td>info row</td><td>/public-api/v2/cryptocurrency/info</td><td class="mono">{i.get("id")}</td><td class="mono">{escape(i.get("symbol") or "")}</td>'
                f'<td class="mono">status {escape(i.get("status") or "")}</td><td>—</td><td>{escape((i.get("platform") or {}).get("name") or "—")}</td><td class="mono">{escape((i.get("date_added") or "—")[:10])}</td></tr>'
            )
    rows_table = (
        "<table><thead><tr><th>source</th><th>endpoint</th><th>id</th><th>symbol</th><th>price / status</th><th>issuer / rank</th><th>platform</th><th>date</th></tr></thead>"
        f"<tbody>{''.join(trs)}</tbody></table>"
    )
    arith = []
    if ws:
        arith.append(
            f"tokens[] on /v5/real-world-assets/quotes/latest → {len(ws)} wrapper{'s' if len(ws) != 1 else ''} attached to {sym}"
            + (f" (rwa_id {u['rwa_id']})" if u else "")
        )
        arith.append(
            f"/public-api/v1/cryptocurrency/map → status per crypto_id: {untracked} untracked · {tracked} active · {other} unresolved or inactive"
        )
        arith.append(f"tracked = wrappers with status == active = {tracked} · attached = {len(ws)}")
        arith.append(
            f"{tracked} of {len(ws)} → "
            + (
                "every wrapper untracked → " + sym + " has no wrapper with a CMC-tracked market"
                if kind == "shelf"
                else sym + " has a wrapper with a CMC-tracked market"
            )
        )
    else:
        arith.append(escape(res.get("verdict") or ""))
    rows_arith = "".join(f"<li>{escape(a) if '<' not in a else a}</li>" for a in arith)
    rows_json = escape(json.dumps(ev, indent=1))
    calls = res.get("calls") or []
    first = next((m for m in calls if m.get("sha256")), calls[0] if calls else {})
    endpoints = []
    for m in calls:
        for ep in (
            "/public-api/v1/cryptocurrency/map",
            "/public-api/v2/cryptocurrency/info",
            "/v5/real-world-assets/quotes/latest",
        ):
            key = ep.replace("/public-api", "")
            if (
                key in str(m.get("call", "")) or ep in str(m.get("url", ""))
            ) and ep not in endpoints:
                endpoints.append(ep)
    if not endpoints and calls:
        endpoints = ["/public-api/v1/cryptocurrency/map"]
    http = sorted({str(m.get("http")) for m in calls}) or ["—"]
    keyed_n = sum(1 for m in calls if m.get("keyed"))
    credits_n = sum(int(m.get("credit_count") or 0) for m in calls if m.get("keyed"))
    elapsed = sum(int(m.get("elapsed_ms") or 0) for m in calls)
    first_url = (
        next((m["url"] for m in calls if m.get("url")), "")
        or (s.get("call") or {}).get("url")
        or ""
    )
    ep_html = " · ".join('<span class="mono">' + escape(e) + "</span>" for e in endpoints)
    credits_note = (
        "none — the state leg is CoinMarketCap's keyless /public-api surface; the roster from the committed snapshot of "
        + as_of
        if not credits_n
        else "keyed roster leg via the site's proxy"
    )
    first_link = (
        f'<a class="mono" href="{escape(first_url)}" target="_blank" rel="noopener noreferrer">{escape(first_url)}<span class="arrow arrow-ext" aria-hidden="true">↗</span><span class="sr-only"> (opens in a new tab)</span></a>'
        if first_url
        else "—"
    )
    keyed_note = f" · {keyed_n} keyed" if keyed_n else ""
    receipt = "".join(
        [
            f'<div><div class="k">endpoint</div><div class="v">{ep_html}</div></div>',
            f'<div><div class="k">calls</div><div class="v">{len(calls)} · HTTP {escape(",".join(http))} · {len(calls) - keyed_n} keyless{keyed_note}</div></div>',
            f'<div><div class="k">credits used</div><div class="v"><span class="mono">{credits_n}</span> — {credits_note}</div></div>',
            f'<div><div class="k">captured</div><div class="v"><span class="mono">{escape(res["asked_utc"])}</span> · {elapsed / 1000:.2f} s across the calls</div></div>',
            f'<div><div class="k">first call sha256</div><div class="v"><span class="mono">{escape(first.get("sha256") or "—")}</span></div></div>',
            f'<div><div class="k">first request</div><div class="v">{first_link}</div></div>',
            f'<div><div class="k">re-derive</div><div class="v"><span class="mono">python3 -m shelfware {sym}</span> · <a href="{REPO}/tree/main/docs/proof" target="_blank" rel="noopener noreferrer">docs/proof/<span class="arrow arrow-ext" aria-hidden="true">↗</span><span class="sr-only"> (opens in a new tab)</span></a> · <a href="#calls">every call ↓</a></div></div>',
        ]
    )
    calls_rows = (
        "<table><thead><tr><th>call</th><th>http</th><th>key</th><th>credits</th><th>ms</th><th>sha256</th><th>utc</th></tr></thead><tbody>"
        + "".join(
            f'<tr><td>{escape(m.get("call") or "")}</td><td class="mono">{m.get("http")}</td><td>{"keyed" if m.get("keyed") else "keyless"}</td>'
            f'<td class="mono">{m.get("credit_count") if m.get("keyed") else "0 to any key"}</td><td class="mono">{m.get("elapsed_ms") if m.get("elapsed_ms") is not None else "—"}</td>'
            f'<td class="mono">{escape(m.get("sha256") or "—")}</td><td class="mono">{escape(m.get("fetched_utc") or "")}</td></tr>'
            for m in calls
        )
        + "</tbody></table>"
    )
    return {
        "context": context,
        "hero_kind": kind,
        "hero_share_num": share_num,
        "hero_share_text": share_text,
        "hero_claim": claim,
        "hero_support": support,
        "table_rows": "".join(rows),
        "route_kind": route_kind,
        "route_line": route_line,
        "route_rule": route_rule,
        "rows_title": rows_title,
        "rows_cap": rows_cap,
        "rows_table": rows_table,
        "rows_arith": rows_arith,
        "rows_json": rows_json,
        "receipt": receipt,
        "calls_rows": calls_rows,
        "calls_n": len(calls),
        "hero_asked": asked,
        "hero_rank": u.get("rwa_rank") if u else "—",
    }


def census_calls(receipt):
    rows = "".join(
        f'<tr><td class="mono">{i}</td><td>{escape(m["call"])}</td><td class="mono">{m["http"]}</td><td>{"keyed" if m["keyed"] else "keyless"}</td>'
        f'<td class="mono">{m.get("credit_count") if m["keyed"] else "0 to any key"}</td><td class="mono">{m["bytes"]:,}</td>'
        f'<td class="mono">{escape(m["sha256"])}</td><td class="mono">{escape(m["utc"])}</td></tr>'
        for i, m in enumerate(receipt, 1)
    )
    return f"<table><thead><tr><th>#</th><th>call</th><th>http</th><th>key</th><th>credit_count</th><th>bytes</th><th>sha256</th><th>utc</th></tr></thead><tbody>{rows}</tbody></table>"


def api_rows(receipt, hero_calls):
    counts = {}
    for m in receipt:
        key = m["url"].split("?")[0].replace("https://pro-api.coinmarketcap.com", "")
        counts[key] = counts.get(key, 0) + 1
    for m in hero_calls:
        url = str(m.get("url") or "")
        key = url.split("?")[0].replace("https://pro-api.coinmarketcap.com", "")
        if key:
            counts[key] = counts.get(key, 0) + 1
    rows = []
    for path, used, key, cls in ENDPOINTS:
        n = counts.get(path, 0)
        rows.append(
            f'<tr class="{cls}"><td><code>{escape(path)}</code></td><td>{escape(used)}</td><td class="key">{escape(key)}</td>'
            f'<td class="n">{n if cls != "unused" else "0 — refused"}</td></tr>'
        )
    return "".join(rows)


def proof_links(doc, res, bench):
    c = doc["counts"]
    cards = [
        (
            "docs/proof/ms.json",
            f"{res['ticker']} · the keyless run · {res['verdict']} · {utc_short(res['asked_utc'])} UTC",
        ),
        (
            "docs/proof/live_run.json",
            f"the census · {len(doc['receipt'])} calls · {doc['credits_used']} credits · {doc['wall_clock_s']} s · {utc_short(doc['generated_utc'])} UTC",
        ),
        (
            "data/census.json",
            f"every wrapper with its underlying, issuer, price, state, chain, listing date · {c['wrappers']:,} rows · the jq filters run here",
        ),
        (
            "docs/proof/bench.json",
            f"p50 {round(bench['lookup']['p50'])} ms · p95 {round(bench['lookup']['p95'])} ms keyless (n={bench['lookup']['n']}) · the join {bench['recount_census']['p50']:.2f} ms · {utc_short(bench['utc'])} UTC",
        ),
    ]
    return "".join(
        f'<a href="{REPO}/blob/main/{f}" target="_blank" rel="noopener noreferrer"><div class="f">{escape(f)}<span class="arrow arrow-ext" aria-hidden="true">↗</span><span class="sr-only"> (opens in a new tab)</span></div><div class="m">{escape(m)}</div></a>'
        for f, m in cards
    )


def runs_html(doc):
    """The daily snapshots as run cards — the number moving (or, honestly, not) day over day."""
    snaps = sorted((DATA / "snapshots").glob("*.json"))
    delta = (
        json.loads((DATA / "delta.json").read_text()) if (DATA / "delta.json").exists() else None
    )
    cards = []
    for i, p in enumerate(snaps):
        d = json.loads(p.read_text())
        c = d["counts"]
        m = f"of {c['has_tokens']} underlyings with no tracked wrapper · {c['untracked']} of {c['wrappers']:,} wrappers on the shelf · {d.get('credits_used', '—')} credits · {d.get('wall_clock_s', '—')} s"
        if i > 0 and delta and delta.get("to") == d["generated_utc"]:
            m += f" · since the day before: +{delta['newly_tracked']} tracked · +{delta['newly_shelved']} shelved · +{delta['new_wrappers']} new · {delta['gone_wrappers']} gone"
        cards.append(
            f'<div class="run"><div class="t">{escape(utc_short(d["generated_utc"])[:16])} UTC</div><div class="v">{c["underlyings_zero_tracked"]}</div>'
            f'<div class="m">{escape(m)} · <a href="{REPO}/blob/main/data/snapshots/{p.name}" target="_blank" rel="noopener noreferrer">{escape(p.name)}<span class="arrow arrow-ext" aria-hidden="true">↗</span><span class="sr-only"> (opens in a new tab)</span></a></div></div>'
        )
    return "".join(cards), [p.stem for p in snaps]


def term_html(res):
    """The terminal: the bare command, then its own output rendered from docs/proof/ms.json by the
    CLI's formatter — the same function that printed it. Never a typed transcript."""
    now = datetime.fromisoformat(res["asked_utc"].replace("Z", "+00:00")).astimezone(UTC)
    out = []
    for line in answer_lines(res, now=now):
        e = escape(line)
        if line.startswith("receipt:"):
            e = (
                '<span class="dim">'
                + e.replace("HTTP 200", '<span class="ok">HTTP 200</span>')
                + "</span>"
            )
        elif "of " in line and "wrapper(s)" in line:
            e = f'<span class="hi">{e}</span>'
        elif "status   " in line:
            e = e.replace("UNTRACKED", '<span class="hi">UNTRACKED</span>').replace(
                "ACTIVE", '<span class="ok">ACTIVE</span>'
            )
        elif line.startswith("shelfware "):
            e = f'<span class="bl">{e}</span>'
        out.append(e)
    return (
        f'<span class="p">$</span> <span class="cmd">git clone {REPO}.git &amp;&amp; cd shelfware</span>\n'
        f'<span class="p">$</span> <span class="cmd">python3 -m shelfware {escape(res["ticker"])}</span>\n'
        + "\n".join(out)
    )


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
                    "url": m.get("url"),
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
        "committed": True,
    }


RAW_SLOTS = {
    "logo",
    "favicon",
    "inline_json",
    "app_js",
    "issuer_rows",
    "issuer_rows_small",
    "type_cards",
    "jq",
    "hero_viz",
    "viz_key",
    "viz_foot",
    "context",
    "hero_claim",
    "hero_support",
    "table_rows",
    "route_line",
    "route_rule",
    "rows_title",
    "rows_cap",
    "rows_table",
    "rows_arith",
    "rows_json",
    "receipt",
    "calls_rows",
    "census_calls",
    "api_rows",
    "proof_links",
    "runs",
    "term",
    "cmd",
    "tagline",
}


def render():
    doc = json.loads((DATA / "census.json").read_text())
    c, a, s = doc["counts"], doc["age_tracked_days"], doc["age_untracked_days"]
    bench = json.loads((PROOF / "bench.json").read_text())
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
    rc = recount(doc)
    viz = hero_viz(c)[0] + "\n" + hero_viz(c, per_row=30, cls="phone")[0]
    with_tracked = c["has_tokens"] - c["underlyings_zero_tracked"]
    title = f"Shelfware — {share}% of CoinMarketCap's tokenised assets have no tracked wrapper"
    description = (
        f"Counts the shelf: {c['underlyings_zero_tracked']} of {c['has_tokens']} tokenised underlyings on CoinMarketCap "
        f"have no wrapper with a CMC-tracked market. Type a ticker: every wrapper, its listing state."
    )
    og_description = (
        f"{c['underlyings_zero_tracked']} of {c['has_tokens']} tokenised underlyings on CoinMarketCap have no wrapper "
        f"with a CMC-tracked market. Counted {doc['generated_utc'][:10]}, {doc['credits_used']} credits."
    )
    og_alt = (
        f"Shelfware — {share}% of the tokenised assets on CoinMarketCap have no wrapper with a CMC-tracked market: "
        f"a shelf of boxes, {c['underlyings_zero_tracked']} grey and {with_tracked} green."
    )
    runs, snaps = runs_html(doc)
    hero_doc = doc.get("hero") or {}
    slots = {
        "title": title,
        "description": description,
        "og_description": og_description,
        "og_alt": og_alt,
        "og_v": og_version(),
        "author": AUTHOR,
        "x_handle": X_HANDLE,
        "event": EVENT,
        "tagline": escape(tagline()),
        "share_pct": share,
        "lit_pct": 100 - share,
        "zero_tracked": c["underlyings_zero_tracked"],
        "zero_tracked_loose": c["underlyings_zero_tracked_loose"],
        "has_tokens": c["has_tokens"],
        "with_tracked": with_tracked,
        "stock_zero": stock["zero_tracked"],
        "stock_under": stock["underlyings"],
        "stock_pct": round(100 * (stock["share"] or 0)),
        "untracked": c["untracked"],
        "untracked_pct": round(100 * c["untracked"] / c["wrappers"]),
        "active": c["active"],
        "wrappers": c["wrappers"],
        "wrappers_fmt": f"{c['wrappers']:,}",
        "underlyings_fmt": f"{c['underlyings']:,}",
        "map_rows_fmt": f"{c['cmc_map_rows']:,}",
        "issuers_n": c["issuers_in_registry"],
        "resolved_fmt": f"{c['wrappers'] - c['unresolved']:,}",
        "exceptions": rc["price_null_iff_untracked_exceptions"],
        "generated_utc": doc["generated_utc"],
        "generated_short": utc_short(doc["generated_utc"]),
        "generated_date": doc["generated_utc"][:10],
        "credits": doc["credits_used"],
        "keyed_calls": doc["keyed_calls"],
        "keyless_calls": doc["keyless_calls"],
        "calls_total": len(doc["receipt"]),
        "wall_clock": doc["wall_clock_s"],
        "usage_before": cm("before") if cm("before") is not None else "—",
        "usage_after": cm("after") if cm("after") is not None else "—",
        "hero_symbol": hero_doc.get("symbol") or "MS",
        "hero_rule": hero_doc.get("rule") or "",
        "runners_up": ", ".join(
            f"{r['symbol']} ({r['rwa_rank']})" for r in hero_doc.get("runners_up") or []
        ),
        "hero_viz": viz,
        "viz_key": (
            f'<span><i class="amber"></i><span>before the join: every box is an underlying the RWA map flags <b>has_tokens: true</b> — {c["has_tokens"]} of them, one box each, shelf first</span></span>'
            f'<span><i class="shelf"></i><span><b id="zt">{c["underlyings_zero_tracked"]}</b> of <b>{c["has_tokens"]}</b> underlyings: <b>no wrapper with a CMC-tracked market</b> — listed, no CMC-tracked market</span></span>'
            f'<span><i class="lit"></i><span><b>{with_tracked}</b> with at least one wrapper whose map status is <b>active</b></span></span>'
            f'<span><i class="shelf"></i><span>join: tokens[] (price: null rows kept) → status on /v1/cryptocurrency/map → count underlyings whose every wrapper is untracked</span></span>'
        ),
        "viz_foot": f"{c['has_tokens']} underlyings · {c['wrappers']:,} wrappers · {len(doc['receipt'])} calls · {doc['credits_used']} credits · {doc['wall_clock_s']} s",
        "issuer_rows": "".join(issuer_row(e, doc["issuers_registry"]) for e in big),
        "issuer_rows_small": "".join(issuer_row(e, doc["issuers_registry"]) for e in small),
        "n_smaller": len(small),
        "type_cards": "".join(
            type_card(t, tu.get(t["asset_type"], {"zero_tracked": 0, "underlyings": 0, "share": 0}))
            for t in doc["by_type"]
        ),
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
        "census_calls": census_calls(doc["receipt"]),
        "api_rows": api_rows(doc["receipt"], (hero or {}).get("calls") or []),
        "api_count": sum(1 for *_, cls in ENDPOINTS if cls != "unused"),
        "proof_links": proof_links(doc, hero, bench),
        "runs": runs,
        "snapshots_n": len(snaps),
        "snapshots_list": ", ".join(snaps),
        "term": term_html(hero),
        "cmd": f"git clone {REPO}.git && cd shelfware && python3 -m shelfware {hero['ticker']}",
        "lookup_p50": round(bench["lookup"]["p50"]),
        "lookup_p95": round(bench["lookup"]["p95"]),
        "lookup_n": bench["lookup"]["n"],
        "join_p50": f"{bench['recount_census']['p50']:.2f}",
        "join_p95": f"{bench['recount_census']['p95']:.2f}",
        "join_n": bench["recount_census"]["n"],
        "bench_iterations": bench["iterations"],
        "bench_throttled": len({e.split(":")[0] for e in bench.get("errors") or []}),
        "tests_total": sum(TESTS.values()),
        "tests_offline": TESTS["offline"],
        "tests_node": TESTS["node"],
        "tests_live": TESTS["live"],
        "property_cases": property_cases(),
        "feedback_n": feedback_n(),
        "version": version(),
        "jq": escape(JQ_RECIPE),
        "repo": REPO,
        "site_url": SITE_URL,
        "api_url": API_URL,
        "logo": LOGO,
        "favicon": FAVICON,
        "inline_json": json.dumps(
            {
                "definition": UNTRACKED_DEFINITION,
                "generated_utc": doc["generated_utc"],
                "api_base": API_URL,
                "repo": REPO,
                "pair": {
                    "zero_tracked": c["underlyings_zero_tracked"],
                    "has_tokens": c["has_tokens"],
                },
                "hero_symbol": hero_doc.get("symbol") or "MS",
                "hero_run": hero,
            },
            separators=(",", ":"),
        ),
        "app_js": (TEMPLATES / "app.js").read_text().rstrip(),
    }
    slots.update(answer_ctx(hero, doc))
    html = (TEMPLATES / "index.html").read_text()
    for k, v in slots.items():
        html = html.replace(
            "{{" + k + "}}", str(v) if k in RAW_SLOTS or not isinstance(v, str) else escape(v)
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


def render_judge():
    """site/judge/index.html — JUDGE.md in the site's chrome, served at /judge with no auth,
    no cookies and no redirect. The page a judge reads is the file a judge reads, rendered;
    relative links point at the repository, and --check fails if the two ever diverge."""
    doc = json.loads((DATA / "census.json").read_text())
    c = doc["counts"]
    share = round(100 * c["underlyings_zero_tracked"] / c["has_tokens"])
    body = md2html.render_file(JUDGE_MD, REPO)
    slots = {
        "body": body,
        "logo": LOGO,
        "favicon": FAVICON,
        "repo": REPO,
        "site_url": SITE_URL,
        "api_url": API_URL,
        "share_pct": str(share),
        "generated_utc": doc["generated_utc"],
        "description": (
            f"The claim, the 30-second path, the receipt: {c['underlyings_zero_tracked']} of "
            f"{c['has_tokens']} tokenised underlyings on CoinMarketCap have no CMC-tracked wrapper."
        ),
    }
    html = (TEMPLATES / "judge.html").read_text()
    for k, v in slots.items():
        html = html.replace("{{" + k + "}}", v if k in ("body", "logo", "favicon") else escape(v))
    left = re.findall(r"\{\{[a-z_]+\}\}", html)
    if left:
        sys.exit(f"unfilled slots on the judge page: {sorted(set(left))}")
    return html


def issuer(doc, name):
    return next((e for e in doc["by_issuer"] if e["issuer_name"] == name), None)


def render_pitch():
    """site/pitch/index.html — the twelve-slide deck, every number a slot from the census, the
    receipt and the benchmark; served at /pitch/ on both hosts. Same drift gate as the page."""
    doc = json.loads((DATA / "census.json").read_text())
    c, a = doc["counts"], doc["age_tracked_days"]
    bench = json.loads((PROOF / "bench.json").read_text())
    tu = {e["asset_type"]: e for e in type_underlyings(doc["wrappers"])}
    stock = tu.get("stock", {"zero_tracked": 0, "underlyings": 0, "share": 0})
    share = round(100 * c["underlyings_zero_tracked"] / c["has_tokens"])
    usage = doc.get("key_usage") or {}
    cm = lambda k: ((usage.get(k) or {}).get("current_month") or {}).get("credits_used")  # noqa: E731
    backed = issuer(doc, "Backed Assets") or {}
    dinari = issuer(doc, "Dinari Assets") or {}
    bstocks = issuer(doc, "bStocks") or {}
    type_rows = "".join(
        f'<div class="type"><span class="muted">{escape(t["asset_type"])}</span>'
        + bar(
            t["tracked"],
            t["untracked"],
            t["other"],
            label=f"{t['asset_type']}: {t['untracked']} of {t['attached']} wrappers untracked",
        )
        + f'<span class="r">{t["shelf_rate"]:.0%} shelf</span></div>'
        for t in doc["by_type"]
    )
    qr = QR_SVG.read_text()
    qr_paths = qr.split(">", 1)[1].rsplit("</svg>", 1)[0]
    slots = {
        "version": version(),
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
        "wrappers_fmt": f"{c['wrappers']:,}",
        "underlyings_fmt": f"{c['underlyings']:,}",
        "map_rows_fmt": f"{c['cmc_map_rows']:,}",
        "issuers": c["issuers_in_registry"],
        "unresolved": c["unresolved"],
        "generated_utc": doc["generated_utc"],
        "generated_short": doc["generated_utc"].replace("T", " ").replace("Z", "")[:16],
        "credits": doc["credits_used"],
        "keyed_calls": doc["keyed_calls"],
        "keyless_calls": doc["keyless_calls"],
        "wall_clock": doc["wall_clock_s"],
        "usage_before": cm("before") if cm("before") is not None else "—",
        "usage_after": cm("after") if cm("after") is not None else "—",
        "age_median": a["median"],
        "age_p90": a["p90"],
        "age_n": a["n"],
        "backed_declared": backed.get("declared", "—"),
        "backed_attached": backed.get("attached", "—"),
        "backed_untracked": backed.get("untracked", "—"),
        "backed_pct": round(100 * (backed.get("shelf_rate") or 0)),
        "backed_live": money(backed.get("live_market_cap_usd")),
        "dinari_attached": dinari.get("attached", "—"),
        "dinari_untracked": dinari.get("untracked", "—"),
        "bstocks_attached": bstocks.get("attached", "—"),
        "bstocks_live": money(bstocks.get("live_market_cap_usd")),
        "lookup_p50": round(bench["lookup"]["p50"]),
        "lookup_p95": round(bench["lookup"]["p95"]),
        "join_p50": f"{bench['join_seed']['p50']:.2f}",
        "join_p95": f"{bench['join_seed']['p95']:.2f}",
        "tests_total": sum(TESTS.values()),
        "tests_offline": TESTS["offline"],
        "tests_node": TESTS["node"],
        "tests_live": TESTS["live"],
        "repo": REPO,
        "site_url": SITE_URL,
        "site_host": SITE_URL.split("//", 1)[1],
        "logo": LOGO,
        "favicon": FAVICON,
        "type_rows": type_rows,
        "qr_paths": qr_paths,
    }
    html = (TEMPLATES / "pitch.html").read_text()
    raw = {"logo", "favicon", "type_rows", "qr_paths"}
    for k, v in slots.items():
        html = html.replace(
            "{{" + k + "}}", str(v) if k in raw or not isinstance(v, str) else escape(v)
        )
    left = re.findall(r"\{\{[a-z_0-9]+\}\}", html)
    if left:
        sys.exit(f"unfilled slots on the deck: {sorted(set(left))}")
    return html


VERSION_STAMP = re.compile(r'(<span class="ver">)v\d+\.\d+\.\d+(?:-dev)?(</span>)')


def tag_reachable():
    try:
        return bool(
            subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def main():
    check = "--check" in sys.argv
    html, health = render()
    targets = {
        SITE / "index.html": html,
        HEALTH_OUT: health,
        JUDGE_OUT: render_judge(),
        PITCH_OUT: render_pitch(),
    }
    if check:
        # A shallow, tagless clone (the CI test matrix) renders the honest fallback where the
        # committed page carries the release tag; compare everything but the stamp there, and
        # say so, rather than fail on a version the checkout cannot see.
        mask = (lambda t: VERSION_STAMP.sub(r"\1vX\2", t)) if not tag_reachable() else (lambda t: t)
        stale = [
            p.name
            for p, want in targets.items()
            if not p.exists() or mask(p.read_text()) != mask(want)
        ]
        if stale:
            print(
                f"drift: {', '.join(stale)} is not what the census renders — run: python3 scripts/render_site.py"
            )
            return 1
        print(
            "site/index.html, site/judge/index.html, site/pitch/index.html and data/health.json match the census"
            + (
                ""
                if tag_reachable()
                else " (no release tag reachable here — the version stamp was not compared)"
            )
        )
        return 0
    SITE.mkdir(exist_ok=True)
    for p, content in targets.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        print(f"wrote {p.name} ({len(content):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
