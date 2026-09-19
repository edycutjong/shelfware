/* Shelfware — the one screen. Nothing here computes the census; the page is complete as
   rendered (every number a slot from the committed census and docs/proof/ms.json). This script
   asks the site's proxy the ticker question live — /api/roster (keyed via the proxy; snapshot
   fallback labelled) then /api/status (keyless map + info, live for anyone) — and re-renders the
   product section in the same shapes scripts/render_site.py rendered the committed run into.
   The join per wrapper mirrors shelfware/lookup.py. The motion layer at the end is the family's
   (LANDING_DESIGN.md §7). */
(function () {
  "use strict";
  var S = window.SHELF;
  var $ = function (id) { return document.getElementById(id); };
  // The two proxy functions live on Vercel. On that host (and on the local dev server) the
  // calls are same-origin; served from GitHub Pages (shelfware.edycu.dev) the same page calls
  // them cross-origin at the absolute URL — the functions answer with Access-Control-Allow-Origin: *.
  var API = /(^|\.)vercel\.app$|^localhost$|^127\.0\.0\.1$/.test(location.hostname) ? "" : S.api_base;
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var FILTERABLE = /^[A-Za-z0-9]+$/;
  var fmt = function (x, dp) { return x == null ? "null" : Number(x).toLocaleString("en-US", { maximumFractionDigits: dp == null ? 0 : dp, minimumFractionDigits: dp == null ? 0 : dp }); };
  var ext = function (href, text) { return '<a href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">' + text + '<span class="arrow arrow-ext" aria-hidden="true">↗</span><span class="sr-only"> (opens in a new tab)</span></a>'; };
  var isShelf = function (w) { return w.status === "untracked"; };
  var kindOf = function (w) { return w.status === "active" ? "lit" : isShelf(w) ? "shelf" : "unknown"; };
  var utcShort = function (ts) { return String(ts || "").replace("T", " ").replace("Z", "").slice(0, 19); };

  function stateFrom(w, asOf) {
    var src = w.status_source, base = w.base === "keyed" ? " · keyed via the proxy (the anonymous pool refused the host's IP)" : " · keyless";
    if (src === "map") return "/v1/cryptocurrency/map · live" + base;
    if (src === "info") return "/v2/cryptocurrency/info · live" + base + " (the map's symbol filter rejects this symbol)";
    if (src === "info+snapshot") return "/v2/cryptocurrency/info says inactive · live; the map's finer state from the " + esc(asOf) + " snapshot";
    return "committed snapshot " + esc(asOf) + (w.fallback_reason ? " — " + esc(w.fallback_reason) : "");
  }

  // ── the answer, in the shapes the render script used for the committed run ──
  function renderAnswer(res) {
    var r = res.roster || {}, s = res.status || {}, asOf = (r.as_of || "").slice(0, 10);
    var ws = res.wrappers || [], u = (res.underlyings || [])[0];
    var sym = esc(res.ticker);
    var tracked = ws.filter(function (w) { return w.status === "active"; }).length;
    var untracked = ws.filter(isShelf).length, other = ws.length - tracked - untracked;
    var pair = S.pair.zero_tracked + " of " + S.pair.has_tokens;
    var asked = utcShort(res.asked_utc);
    var rosterSrc = r.source === "live" ? "live via /api/roster · keyed · " + esc(r.credit_count == null ? 1 : r.credit_count) + " credit" : "snapshot " + esc(asOf) + (r.fallback_reason ? " — " + esc(r.fallback_reason) : " (the RWA endpoints need a key)");
    var stateSrc = res.live ? "live · keyless · 0 credits" : esc(s.source || "");
    $("context").innerHTML = u
      ? "<b>" + esc(u.symbol) + "</b> · " + esc(u.name || "") + " · " + esc(u.asset_type || "") + " · rwa_rank " + esc(u.rwa_rank) + " · has_tokens: <b>" + (u.has_tokens ? "true" : "false") + "</b> · asked " + esc(asked) + " UTC · roster: " + rosterSrc + " · state: " + stateSrc
      : "<b>" + sym + "</b> · not in CoinMarketCap's RWA map · asked " + esc(asked) + " UTC · roster: " + rosterSrc;
    var kind, shareText, claim, support;
    if (!ws.length) {
      kind = "none"; shareText = "0 of 0";
      claim = u ? "wrappers listed for <em>" + sym + "</em>." : "<em>" + sym + "</em> is not in CoinMarketCap's RWA map.";
      support = esc(res.verdict || "");
    } else {
      kind = tracked ? "lit" : "shelf"; shareText = tracked + " of " + ws.length;
      claim = "wrapper" + (ws.length !== 1 ? "s" : "") + " of <em>" + sym + "</em> " + (ws.length !== 1 ? "have" : "has") + " a CMC-tracked market.";
      var issuers = []; ws.forEach(function (w) { var n = w.issuer_name || "(no issuer)"; if (issuers.indexOf(n) < 0) issuers.push(n); }); issuers.sort();
      support = "<b>" + tracked + "</b> active · <b>" + untracked + "</b> untracked · " + other + " unresolved or inactive — issuer" + (issuers.length !== 1 ? "s" : "") + ": " + esc(issuers.join(", ")) + ". "
        + (kind === "shelf" ? "The RWA map says <b>has_tokens: true</b>; the cryptocurrency map says <b>untracked</b> for every wrapper — listed, no CMC-tracked market." : "Tracked means <b>status == active</b> on the cryptocurrency map; a wrapper with price: null is untracked, with 0 exceptions on the committed census.");
    }
    $("hero").className = "hero " + kind;
    $("share").textContent = shareText; $("share").setAttribute("data-target", String(tracked));
    $("claim").innerHTML = claim; $("support").innerHTML = support;
    $("tbody").innerHTML = ws.length ? ws.map(function (w) {
      var p = w.platform || {};
      return '<tr class="' + kindOf(w) + '"><td class="pool">' + esc(w.symbol || "—") + "<small>" + esc(w.name || "") + '</small></td><td class="l">' + esc(w.issuer_name || "(no issuer)") + '</td><td class="l">' + esc(p.name || "—") + '</td><td class="l mono addr">' + esc(p.token_address || "—") + '</td><td class="mono">' + (w.price == null ? "null" : fmt(w.price, 4)) + '</td><td><span class="state ' + esc(w.status || "unresolved") + '">' + esc(w.status || "unresolved") + '</span></td><td class="l src">' + stateFrom(w, asOf) + '</td><td class="mono">' + esc(((w.date_added || w.first_historical_data || "—")).slice(0, 10)) + "</td></tr>";
    }).join("") : '<tr><td class="pool" colspan="8">' + esc(res.verdict || "no wrappers") + "</td></tr>";
    var route = $("route"), n = ws.length, plural = n !== 1 ? "s" : "";
    if (kind === "shelf") { route.className = "route shelf"; $("routeline").textContent = "▶ " + tracked + " of " + n + " wrapper" + plural + " with a CMC-tracked market — on the shelf"; $("routerule").textContent = "rule: strict — an underlying counts only when every attached wrapper is untracked · an unresolved id never counts · " + res.ticker + " is one of the " + pair + (res.live ? " as of the committed census" : ""); }
    else if (kind === "lit") { route.className = "route lit"; $("routeline").textContent = "▶ " + tracked + " of " + n + " wrapper" + plural + " with a CMC-tracked market"; $("routerule").textContent = "rule: tracked = status == active on /v1/cryptocurrency/map · price == null ⇔ untracked, 0 exceptions on the committed census · " + res.ticker + " is not one of the " + pair; }
    else { route.className = "route none"; $("routeline").textContent = "▶ " + (res.verdict || "no wrapper listed"); $("routerule").textContent = "rule: a wrapper must be in tokens[] on /v5/real-world-assets/quotes/latest to be counted at all"; }
    // raw rows: one line per (wrapper × source) — tokens[] entry, map row, info row
    var ev = res.evidence || {}, mapById = {}; (ev.map_rows || []).forEach(function (m) { mapById[m.id] = m; });
    var info = ev.info_rows || {};
    var ids = ws.map(function (w) { return w.crypto_id; }).join(", ") || "—";
    $("rowstitle").textContent = (ws.map(function (w) { return w.symbol || "?"; }).join(", ") || res.ticker) + " — raw rows (" + n + " wrapper" + plural + ", three sources)";
    $("rowscap").innerHTML = "rwa_id " + (u ? esc(u.rwa_id) : "—") + " · crypto_id " + esc(ids) + ' · tokens[] from <span class="mono">/v5/real-world-assets/quotes/latest</span> (' + (r.source === "live" ? "live" : "snapshot " + esc(asOf)) + ') · state from <span class="mono">/public-api/v1/cryptocurrency/map</span> · listing date from <span class="mono">/public-api/v2/cryptocurrency/info</span>' + (res.committed ? " · " + ext(S.repo + "/blob/main/docs/proof/ms.json", "docs/proof/ms.json") : " · live, not committed");
    var trs = [];
    (ev.tokens || []).forEach(function (t) {
      trs.push("<tr><td>tokens[]</td><td>/v5/real-world-assets/quotes/latest</td><td class=\"mono\">" + esc(t.crypto_id) + '</td><td class="mono">' + esc(t.symbol || "null") + '</td><td class="mono">' + (t.price == null ? "null" : fmt(t.price, 4)) + "</td><td>" + esc(t.issuer_name || "(no issuer)") + "</td><td>" + esc((t.platform || {}).name || "—") + '</td><td class="mono">—</td></tr>');
      var m = mapById[t.crypto_id];
      if (m) trs.push('<tr class="' + (m.status === "untracked" ? "leg" : m.status === "active" ? "lit" : "unknown") + '"><td>map row</td><td>/public-api/v1/cryptocurrency/map</td><td class="mono">' + esc(m.id) + '</td><td class="mono">' + esc(m.symbol || "") + '</td><td class="mono">status ' + esc(m.status || "") + "</td><td>rank " + (m.rank == null ? "null" : esc(m.rank)) + "</td><td>" + esc((m.platform || {}).name || "—") + '</td><td class="mono">' + esc((m.first_historical_data || "—").slice(0, 10)) + "</td></tr>");
      var i = info[String(t.crypto_id)];
      if (i) trs.push("<tr><td>info row</td><td>/public-api/v2/cryptocurrency/info</td><td class=\"mono\">" + esc(i.id) + '</td><td class="mono">' + esc(i.symbol || "") + '</td><td class="mono">status ' + esc(i.status || "") + "</td><td>—</td><td>" + esc((i.platform || {}).name || "—") + '</td><td class="mono">' + esc((i.date_added || "—").slice(0, 10)) + "</td></tr>");
    });
    $("rowlist").innerHTML = "<table><thead><tr><th>source</th><th>endpoint</th><th>id</th><th>symbol</th><th>price / status</th><th>issuer / rank</th><th>platform</th><th>date</th></tr></thead><tbody>" + trs.join("") + "</tbody></table>";
    var arith = ws.length ? [
      "tokens[] on /v5/real-world-assets/quotes/latest → " + n + " wrapper" + plural + " attached to " + res.ticker + (u ? " (rwa_id " + u.rwa_id + ")" : ""),
      "/public-api/v1/cryptocurrency/map → status per crypto_id: " + untracked + " untracked · " + tracked + " active · " + other + " unresolved or inactive",
      "tracked = wrappers with status == active = " + tracked + " · attached = " + n,
      tracked + " of " + n + " → " + (kind === "shelf" ? "every wrapper untracked → " + res.ticker + " has no wrapper with a CMC-tracked market" : res.ticker + " has a wrapper with a CMC-tracked market")
    ] : [res.verdict || ""];
    $("arith").innerHTML = arith.map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("");
    $("rawpre").textContent = JSON.stringify(ev, null, 1);
    // the receipt grid and the call list follow the answer
    var calls = res.calls || [], first = calls.filter(function (m) { return m.sha256; })[0] || calls[0] || {};
    var endpoints = [];
    calls.forEach(function (m) { ["/public-api/v1/cryptocurrency/map", "/public-api/v2/cryptocurrency/info", "/v5/real-world-assets/quotes/latest"].forEach(function (ep) { var key = ep.replace("/public-api", ""); if ((String(m.call || "").indexOf(key) >= 0 || String(m.url || "").indexOf(ep) >= 0) && endpoints.indexOf(ep) < 0) endpoints.push(ep); }); });
    var http = []; calls.forEach(function (m) { if (http.indexOf(String(m.http)) < 0) http.push(String(m.http)); }); http.sort();
    var keyedN = calls.filter(function (m) { return m.keyed; }).length;
    var creditsN = 0; calls.forEach(function (m) { if (m.keyed) creditsN += Number(m.credit_count || 0); });
    var elapsed = 0; calls.forEach(function (m) { elapsed += Number(m.elapsed_ms || 0); });
    var firstUrl = (calls.filter(function (m) { return m.url; })[0] || {}).url || (s.call && s.call.url) || "";
    $("receipt-grid").innerHTML = [
      '<div><div class="k">endpoint</div><div class="v">' + endpoints.map(function (e) { return '<span class="mono">' + esc(e) + "</span>"; }).join(" · ") + "</div></div>",
      '<div><div class="k">calls</div><div class="v">' + calls.length + " · HTTP " + esc(http.join(",") || "—") + " · " + (calls.length - keyedN) + " keyless" + (keyedN ? " · " + keyedN + " keyed" : "") + "</div></div>",
      '<div><div class="k">credits used</div><div class="v"><span class="mono">' + creditsN + "</span> — " + (creditsN ? "keyed roster leg via the site's proxy" + (res.live ? "; the state leg keyless" : "") : "none — the state leg is CoinMarketCap's keyless /public-api surface; the roster from the committed snapshot of " + esc(asOf)) + "</div></div>",
      '<div><div class="k">captured</div><div class="v"><span class="mono">' + esc(res.asked_utc) + "</span> · " + (elapsed / 1000).toFixed(2) + " s across the calls</div></div>",
      '<div><div class="k">first call sha256</div><div class="v"><span class="mono">' + esc(first.sha256 || "—") + "</span></div></div>",
      '<div><div class="k">first request</div><div class="v">' + (firstUrl ? ext(firstUrl, '<span class="mono">' + esc(firstUrl) + "</span>") : "—") + "</div></div>",
      '<div><div class="k">re-derive</div><div class="v"><span class="mono">python3 -m shelfware ' + sym + "</span> · " + ext(S.repo + "/tree/main/docs/proof", "docs/proof/") + ' · <a href="#calls">every call ↓</a></div></div>'
    ].join("");
    $("calls-list").innerHTML = "<table><thead><tr><th>call</th><th>http</th><th>key</th><th>credits</th><th>ms</th><th>sha256</th><th>utc</th></tr></thead><tbody>" + calls.map(function (m) {
      return "<tr><td>" + esc(m.call || "") + '</td><td class="mono">' + esc(m.http) + "</td><td>" + (m.keyed ? "keyed" : "keyless") + '</td><td class="mono">' + (m.keyed ? esc(m.credit_count) : "0 to any key") + '</td><td class="mono">' + (m.elapsed_ms != null ? esc(m.elapsed_ms) : "—") + '</td><td class="mono">' + esc(m.sha256 || "—") + '</td><td class="mono">' + esc(m.fetched_utc || "") + "</td></tr>";
    }).join("") + "</tbody></table>";
  }

  function joinWrappers(tokens, mapRows, infoRows, snapTokens, bases) {
    var byId = {}, info = {}, snap = {};
    bases = bases || {};
    (mapRows || []).forEach(function (r) { byId[r.id] = r; });
    Object.keys(infoRows || {}).forEach(function (k) { info[k] = infoRows[k]; });
    (snapTokens || []).forEach(function (t) { snap[t.crypto_id] = t; });
    return tokens.map(function (t) {
      var w = { crypto_id: t.crypto_id, symbol: t.symbol, name: t.name, issuer_id: t.issuer_id, issuer_name: t.issuer_name, price: t.price, market_cap: t.market_cap, volume_24h: t.volume_24h };
      var m = byId[t.crypto_id], i = info[String(t.crypto_id)], s = snap[t.crypto_id];
      w.date_added = i ? i.date_added : (s ? s.date_added : null);
      if (m) { w.status = m.status; w.status_source = "map"; w.base = bases.map; w.platform = m.platform; w.first_historical_data = m.first_historical_data; return w; }
      if (mapRows === null) { w.status = s ? s.status : "unresolved"; w.status_source = "snapshot"; w.platform = s ? s.platform : null; w.first_historical_data = s ? s.first_historical_data : null; return w; }
      if (i && i.status === "active") { w.status = "active"; w.status_source = "info"; w.base = bases.info; w.platform = i.platform; return w; }
      if (i && i.status === "inactive") { var fine = s ? s.status : null; w.status = (fine === "untracked" || fine === "inactive") ? fine : "inactive"; w.status_source = (fine === "untracked" || fine === "inactive") ? "info+snapshot" : "info"; w.base = bases.info; w.platform = i.platform || (s ? s.platform : null); return w; }
      w.status = "unresolved"; w.status_source = "info"; w.platform = null; return w;
    });
  }

  function getJSON(url) { return fetch(API + url, { headers: { Accept: "application/json" } }).then(function (r) { return r.json().then(function (j) { j.__http = r.status; return j; }); }); }

  var cmdFor = function (sym) { return "git clone " + S.repo + ".git && cd shelfware && python3 -m shelfware " + sym; };
  function setMode(text, cls) { var m = $("mode"); m.textContent = text; m.className = "chip " + cls; }

  function ask(ticker) {
    var sym = ticker.trim().toUpperCase(), btn = $("go"), status = $("status");
    if (!sym || !/^[A-Z0-9.\-]{1,16}$/.test(sym)) { status.textContent = "a ticker is letters and digits — try MS, NVDA, GILD, GOLD"; return; }
    btn.disabled = true; setMode("fetching", "busy");
    status.textContent = "asking /api/roster?symbol=" + sym + " …";
    history.replaceState(null, "", "?t=" + encodeURIComponent(sym));
    var res = { ticker: sym, asked_utc: new Date().toISOString().replace(/\.\d+Z$/, "Z"), underlyings: [], wrappers: [], calls: [], evidence: {}, roster: {}, status: {}, live: true };
    getJSON("/api/roster?symbol=" + encodeURIComponent(sym)).then(function (r) {
      if (r.__http === 429) throw { status: 429, message: r.error || "HTTP 429 from /api/roster" };
      res.roster = { source: r.source, as_of: r.as_of, credit_count: r.credit_count, fallback_reason: r.fallback_reason };
      res.calls.push({ call: "/api/roster → " + (r.source === "live" ? "/v5/real-world-assets/quotes/latest?symbol=" + sym : "data/roster_snapshot.json"), url: r.source === "live" ? "https://pro-api.coinmarketcap.com/v5/real-world-assets/quotes/latest?symbol=" + sym : "", http: r.upstream_http || r.__http, keyed: r.source === "live", credit_count: r.credit_count, elapsed_ms: r.elapsed_ms, fetched_utc: r.fetched_utc, sha256: r.sha256 });
      var assets = r.assets || [];
      res.underlyings = assets.map(function (a) { return { rwa_id: a.rwa_id, symbol: a.symbol, name: a.name, asset_type: a.asset_type, rwa_rank: a.rwa_rank, has_tokens: a.has_tokens }; });
      var tokens = []; assets.forEach(function (a) { (a.tokens || []).forEach(function (t) { tokens.push(t); }); });
      res.evidence.tokens = tokens;
      var snapTokens = r.snapshot_tokens || [];
      if (!assets.length) { res.verdict = "CoinMarketCap's RWA map has no underlying " + sym; res.status = { source: "—" }; return res; }
      if (!tokens.length) { res.verdict = sym + " is in the RWA map with has_tokens: false — 0 wrappers listed"; res.status = { source: "—" }; return res; }
      var symbols = tokens.map(function (t) { return t.symbol; }).filter(function (x) { return x && FILTERABLE.test(x); });
      var ids = tokens.map(function (t) { return t.crypto_id; }).filter(function (x) { return x != null; });
      status.textContent = "asking /api/status — keyless map for " + symbols.join(",") + " and info for " + ids.length + " ids …";
      return getJSON("/api/status?symbols=" + encodeURIComponent(symbols.join(",")) + "&ids=" + encodeURIComponent(ids.join(","))).then(function (s) {
        var mapRows = null, infoRows = {}, bases = { map: s.map && s.map.base, info: s.info && s.info.base };
        var callOf = function (x, label) { return { call: "/api/status → " + label + (x.base === "keyed" ? "  [keyless refused: " + x.keyless_error + "]" : ""), url: x.url, http: x.http, keyed: x.base === "keyed", credit_count: x.credit_count, elapsed_ms: x.elapsed_ms, fetched_utc: s.fetched_utc, sha256: x.sha256 }; };
        if (s.map) { res.calls.push(callOf(s.map, "/v1/cryptocurrency/map?symbol=" + symbols.join(","))); if (s.map.http === 200 && s.map.raw) mapRows = s.map.raw.data || []; }
        if (s.info) { res.calls.push(callOf(s.info, "/v2/cryptocurrency/info?id=" + ids.join(","))); if (s.info.http === 200 && s.info.raw) infoRows = s.info.raw.data || {}; }
        res.status = { source: "live keyless", call: s.map ? { url: s.map.url } : null, fallback_reason: null };
        if (mapRows === null && symbols.length) { res.status.fallback_reason = (s.map && s.map.error) || s.error || "no answer from the keyless map"; res.status.source = "snapshot"; }
        if (mapRows === null && !symbols.length) mapRows = [];
        var wanted = {}; ids.forEach(function (i) { wanted[i] = true; });
        res.evidence.map_rows = mapRows ? mapRows.filter(function (row) { return wanted[row.id]; }) : null;
        res.evidence.info_rows = Object.keys(infoRows).length ? infoRows : null;
        res.wrappers = joinWrappers(tokens, mapRows, infoRows, snapTokens, bases);
        res.wrappers.forEach(function (w) { if (w.status_source === "snapshot") w.fallback_reason = res.status.fallback_reason; });
        var tracked = res.wrappers.filter(function (w) { return w.status === "active"; }).length;
        res.verdict = tracked + " of " + res.wrappers.length + " wrapper(s) with a CMC-tracked market";
        if (mapRows === null) res.throttled = res.status.fallback_reason;
        return res;
      }, function (e) {
        res.wrappers = joinWrappers(tokens, null, {}, snapTokens);
        res.wrappers.forEach(function (w) { w.fallback_reason = "/api/status unreachable: " + e; });
        res.status = { source: "snapshot", fallback_reason: "/api/status unreachable: " + e };
        var tracked = res.wrappers.filter(function (w) { return w.status === "active"; }).length;
        res.verdict = tracked + " of " + res.wrappers.length + " wrapper(s) with a CMC-tracked market (snapshot)";
        res.throttled = String(e);
        return res;
      });
    }).then(function (r) {
      renderAnswer(r);
      if (r.throttled) { setMode("state: snapshot", "err"); status.innerHTML = "The keyless state leg did not answer (" + esc(r.throttled) + ") — the rows above carry the committed snapshot's state and say so. Run the same question from your own IP, keyless:<span class=\"cmd\">" + esc(cmdFor(sym)) + "</span>"; }
      else { setMode("live · keyless", "ok"); status.textContent = "live answer for " + sym + " — the receipt grid and the call list below follow it"; }
    }, function (e) {
      var is429 = e && e.status === 429;
      setMode(is429 ? "HTTP 429" : "proxy down", "err");
      status.innerHTML = (is429 ? "HTTP 429 — CoinMarketCap's anonymous tier is rate-limited per IP, and every visitor of this page shares the proxy's. " : "The search needs this site's proxy (/api/roster), which did not answer: " + esc(e && e.message ? e.message : e) + ". ") + "Ask the same question on your machine, live and keyless:<span class=\"cmd\">" + esc(cmdFor(sym)) + "</span>";
    }).then(function () { btn.disabled = false; });
  }

  $("paste").addEventListener("submit", function (e) { e.preventDefault(); ask($("t").value); });
  var q = new URLSearchParams(location.search).get("t");
  if (q) { $("t").value = q.toUpperCase(); ask(q); }

  getJSON("/api/health").then(function (h) {
    if (!h.ok) { setMode("proxy not answering", "err"); }
  }, function () {
    setMode("no proxy on this host", "err");
    $("status").innerHTML = "No proxy on this host, so the box cannot ask live; the answer shown is the committed run. On your machine, keyless:<span class=\"cmd\">" + esc(cmdFor(S.hero_symbol)) + "</span>";
  });

  // ── the family's motion layer (LANDING_DESIGN.md §7) ─────────────────────────
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const top = $('top');
  if (top) { const onScroll = () => top.classList.toggle('scrolled', window.scrollY > 8); window.addEventListener('scroll', onScroll, { passive: true }); requestAnimationFrame(onScroll); }
  const io = 'IntersectionObserver' in window ? new IntersectionObserver((es) => { es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }); }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 }) : null;
  document.querySelectorAll('.reveal').forEach((el) => { if (io) io.observe(el); else el.classList.add('in'); });
  const blocks = [...document.querySelectorAll('svg.block')], block = blocks.find((b) => b.getClientRects().length) || blocks[0];
  const release = () => blocks.forEach((b) => b.classList.add('go'));
  setTimeout(() => { document.querySelectorAll('.reveal').forEach((el) => el.classList.add('in', 'now')); if (block) release(); }, 2500);
  if (block) { if (reduce || !('IntersectionObserver' in window)) release(); else { const bo = new IntersectionObserver((es) => { es.forEach((e) => { if (e.isIntersecting) { release(); bo.disconnect(); } }); }, { threshold: 0.35 }); bo.observe(block); } }
  const big = document.querySelector('h1 [data-count]');
  if (big && !reduce && 'IntersectionObserver' in window) {
    const target = parseFloat(big.dataset.count), suffix = big.textContent.replace(/^[0-9.]+/, ''), dec = (big.dataset.count.split('.')[1] || '').length;
    let t0 = null; const dur = 1100;
    const tick = (ts) => { if (!t0) t0 = ts; let p = Math.min(1, (ts - t0) / dur); p = 1 - Math.pow(1 - p, 3); big.textContent = (target * p).toFixed(dec) + suffix; if (p < 1) requestAnimationFrame(tick); else big.textContent = big.dataset.count + suffix; };
    const co = new IntersectionObserver((es) => { if (es[0].isIntersecting) { requestAnimationFrame(tick); co.disconnect(); } }, { threshold: 0.5 }); co.observe(big);
  }
  if (!reduce) document.querySelectorAll('details').forEach((d) => {
    const sum = d.querySelector(':scope > summary'), fold = d.querySelector(':scope > .fold'); if (!sum || !fold) return;
    d.classList.add('fx'); let closing = null;
    const settle = () => { if (closing) { clearTimeout(closing); closing = null; d.open = false; } };
    fold.addEventListener('transitionend', (e) => { if (e.target === fold && !d.classList.contains('is-open')) settle(); });
    sum.addEventListener('click', (e) => { e.preventDefault(); if (d.open && !closing) { d.classList.remove('is-open'); closing = setTimeout(settle, 320); } else if (!d.open) { d.open = true; void fold.offsetHeight; d.classList.add('is-open'); } });
    d.addEventListener('toggle', () => { if (d.open && !d.classList.contains('is-open') && !closing) { void fold.offsetHeight; d.classList.add('is-open'); } if (!d.open) d.classList.remove('is-open'); });
  });
  document.querySelectorAll('button.copy[data-copy]').forEach((btn) => btn.addEventListener('click', () => {
    const done = () => { btn.textContent = 'copied'; btn.classList.add('done'); setTimeout(() => { btn.textContent = 'copy'; btn.classList.remove('done'); }, 1600); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(btn.dataset.copy).then(done, done); else done();
  }));
})();
