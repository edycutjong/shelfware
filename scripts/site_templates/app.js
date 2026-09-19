/* Shelfware — the one screen. Nothing here computes the census; it renders window.SHELF
   (inlined at build time from data/census.json) and asks the site's proxy the ticker question:
   /api/roster (keyed, via the proxy; snapshot fallback labelled) then /api/status (keyless map +
   info, live for anyone). The join per wrapper mirrors shelfware/lookup.py. */
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
  var days = function (iso) { return Math.floor((Date.now() - Date.parse(iso)) / 86400000); };

  // ── the one animation: the headline counts up while the shelf bar fills ──
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var big = $("bignum");
  if (big && !reduce) {
    var target = parseInt(big.getAttribute("data-target"), 10), zt = $("zt"), ztTarget = parseInt(zt.textContent, 10);
    var dim = $("bar-dim"), lit = $("bar-lit"), dimW = dim.style.width, litW = lit.style.width;
    dim.style.transition = "none"; lit.style.transition = "none"; dim.style.width = "0%"; lit.style.width = "0%";
    var t0 = null;
    var step = function (ts) {
      if (!t0) t0 = ts;
      var p = Math.min(1, (ts - t0) / 1500), e = 1 - Math.pow(1 - p, 3);
      big.textContent = Math.round(target * e) + "%";
      zt.textContent = Math.round(ztTarget * e);
      dim.style.width = (parseFloat(dimW) * e) + "%";
      if (p >= 0.75) lit.style.width = (parseFloat(litW) * Math.min(1, (p - 0.75) / 0.25)) + "%";
      if (p < 1) requestAnimationFrame(step); else { big.textContent = target + "%"; zt.textContent = ztTarget; dim.style.width = dimW; lit.style.width = litW; }
    };
    requestAnimationFrame(step);
  }

  // ── the ticker question ───────────────────────────────────────────────────
  function chip(status) { return '<span class="chip ' + esc(status) + '">' + esc(status.toUpperCase()) + "</span>"; }
  function via(base, ep) {
    if (base === "keyed") return "/" + ep + " · live · keyed via this site's proxy, 1 credit (CMC's anonymous pool refuses the host's shared IP; on your machine it is keyless)";
    return "/public-api/" + ep + " · live · keyless · 0 credits";
  }
  function sourceLine(w, asOf) {
    if (w.status_source === "map") return via(w.base, "v1/cryptocurrency/map");
    if (w.status_source === "info") return via(w.base, "v2/cryptocurrency/info") + " (the map's symbol filter rejects this symbol)";
    if (w.status_source === "info+snapshot") return via(w.base, "v2/cryptocurrency/info").replace(" · live", " says inactive · live") + "; the map's finer state from the " + esc(asOf) + " snapshot (its symbol filter rejects \"" + esc(w.symbol) + "\")";
    return "committed snapshot " + esc(asOf) + " — " + esc(w.fallback_reason || "the keyless pool did not answer");
  }
  function renderCard(res) {
    var html = "";
    var r = res.roster, asOf = (r.as_of || "").slice(0, 10);
    if (!res.underlyings.length) {
      html += '<p class="verdict">' + esc(res.verdict) + "</p>";
      html += '<p class="src">roster: ' + (r.source === "live" ? "<b>live</b> — the RWA map has no such symbol" : "snapshot " + esc(asOf)) + "</p>";
    }
    res.underlyings.forEach(function (u) {
      html += '<div class="uline"><span class="mono">' + esc(u.symbol) + "</span><span>" + esc(u.name || "") + "</span><span class=\"src\">" + esc(u.asset_type || "") + " · rwa_rank " + esc(u.rwa_rank) + '</span><span class="pill' + (u.has_tokens ? "" : " off") + '">has_tokens: ' + (u.has_tokens ? "true" : "false") + "</span></div>";
    });
    html += '<p class="src">roster: ' + (r.source === "live" ? "<b>live</b> via /api/roster → /v5/real-world-assets/quotes/latest · keyed · " + esc(r.credit_count == null ? 1 : r.credit_count) + " credit" : "<b>snapshot " + esc(asOf) + "</b>" + (r.fallback_reason ? " — " + esc(r.fallback_reason) : " (the RWA endpoints need a key)")) + "</p>";
    res.wrappers.forEach(function (w) {
      var p = w.platform || {};
      html += '<div class="wrow"><div class="box ' + (w.status === "active" ? "lit" : (w.status === "untracked" ? "" : "unk")) + '"></div><div>';
      html += '<div><span class="wsym">' + esc(w.symbol) + "</span> <span>" + esc(w.name || "") + "</span>" + chip(w.status) + "</div>";
      html += '<div class="wmeta"><span>issuer</span><span>' + esc(w.issuer_name || "(no issuer)") + (w.issuer_id ? " · " + esc(w.issuer_id) : "") + "</span>";
      html += "<span>chain</span><span>" + esc(p.name || "—") + (p.token_address ? " · " + esc(p.token_address) : "") + "</span>";
      html += "<span>price</span><span>" + (w.price == null ? "null" : fmt(w.price, 4)) + " · market_cap " + fmt(w.market_cap) + " · volume_24h " + fmt(w.volume_24h) + "</span>";
      html += "<span>state</span><span>" + sourceLine(w, asOf) + "</span>";
      if (w.status === "untracked") html += "<span>meaning</span><span>listed, no CMC-tracked market — CMC: " + esc(S.definition) + (w.date_added ? " · listed " + esc(w.date_added.slice(0, 10)) + " (date_added) · " + days(w.date_added) + " days on the shelf" : "") + "</span>";
      else if (w.status === "active") html += "<span>tracked since</span><span>" + esc((w.first_historical_data || "?").slice(0, 10)) + "</span>";
      else if (w.status === "unresolved") html += "<span>meaning</span><span>this id is in tokens[] but on no public CMC surface — not counted as shelf</span>";
      html += "</div></div></div>";
    });
    if (res.wrappers.length) html += '<p class="verdict">' + esc(res.verdict) + "</p>";
    var ev = res.evidence || {};
    html += "<details><summary>evidence — the raw rows, endpoint, HTTP status, credit_count</summary>";
    (res.calls || []).forEach(function (c) { html += '<p class="ev">' + esc(c.call) + " → HTTP " + esc(c.http) + " · " + (c.keyed ? "keyed · " + esc(c.credit_count) + " credit" : "keyless · 0 credits to any key") + (c.elapsed_ms != null ? " · " + esc(c.elapsed_ms) + " ms" : "") + (c.sha256 ? " · sha256 " + esc(c.sha256) : "") + (c.fetched_utc ? " · " + esc(c.fetched_utc) : "") + "</p>"; });
    if (ev.tokens) html += '<p class="ev">tokens[] entries — /v5/real-world-assets/quotes/latest</p><pre>' + esc(JSON.stringify(ev.tokens, null, 1)) + "</pre>";
    if (ev.map_rows) html += '<p class="ev">map rows — /public-api/v1/cryptocurrency/map</p><pre>' + esc(JSON.stringify(ev.map_rows, null, 1)) + "</pre>";
    if (ev.info_rows) html += '<p class="ev">info rows — /public-api/v2/cryptocurrency/info</p><pre>' + esc(JSON.stringify(ev.info_rows, null, 1)) + "</pre>";
    html += "</details>";
    return html;
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

  function ask(ticker) {
    var sym = ticker.trim().toUpperCase(), card = $("tcard"), btn = $("go");
    if (!sym) return;
    btn.disabled = true; btn.textContent = "asking…";
    card.innerHTML = '<p class="src">asking /api/roster?symbol=' + esc(sym) + " …</p>";
    history.replaceState(null, "", "?t=" + encodeURIComponent(sym));
    var res = { ticker: sym, underlyings: [], wrappers: [], calls: [], evidence: {}, roster: {}, status: {} };
    getJSON("/api/roster?symbol=" + encodeURIComponent(sym)).then(function (r) {
      res.roster = { source: r.source, as_of: r.as_of, credit_count: r.credit_count, fallback_reason: r.fallback_reason };
      res.calls.push({ call: "/api/roster → " + (r.source === "live" ? "/v5/real-world-assets/quotes/latest?symbol=" + sym : "data/roster_snapshot.json"), http: r.upstream_http || r.__http, keyed: r.source === "live", credit_count: r.credit_count, fetched_utc: r.fetched_utc, sha256: r.sha256 });
      var assets = r.assets || [];
      res.underlyings = assets.map(function (a) { return { rwa_id: a.rwa_id, symbol: a.symbol, name: a.name, asset_type: a.asset_type, rwa_rank: a.rwa_rank, has_tokens: a.has_tokens }; });
      var tokens = []; assets.forEach(function (a) { (a.tokens || []).forEach(function (t) { tokens.push(t); }); });
      res.evidence.tokens = tokens;
      var snapTokens = r.snapshot_tokens || [];
      if (!assets.length) { res.verdict = "CoinMarketCap's RWA map has no underlying " + sym; return res; }
      if (!tokens.length) { res.verdict = sym + " is in the RWA map with has_tokens: false — 0 wrappers listed"; return res; }
      var symbols = tokens.map(function (t) { return t.symbol; }).filter(function (x) { return x && FILTERABLE.test(x); });
      var ids = tokens.map(function (t) { return t.crypto_id; }).filter(function (x) { return x != null; });
      card.innerHTML += '<p class="src">asking /api/status — keyless map for ' + esc(symbols.join(",")) + " and info for " + ids.length + " ids …</p>";
      return getJSON("/api/status?symbols=" + encodeURIComponent(symbols.join(",")) + "&ids=" + encodeURIComponent(ids.join(","))).then(function (s) {
        var mapRows = null, infoRows = {}, bases = { map: s.map && s.map.base, info: s.info && s.info.base };
        var callOf = function (x) { return { call: "/api/status → " + x.url + (x.base === "keyed" ? "  [keyless refused: " + x.keyless_error + "]" : ""), http: x.http, keyed: x.base === "keyed", credit_count: x.credit_count, elapsed_ms: x.elapsed_ms, fetched_utc: s.fetched_utc, sha256: x.sha256 }; };
        if (s.map) { res.calls.push(callOf(s.map)); if (s.map.http === 200 && s.map.raw) mapRows = s.map.raw.data || []; }
        if (s.info) { res.calls.push(callOf(s.info)); if (s.info.http === 200 && s.info.raw) infoRows = s.info.raw.data || {}; }
        if (mapRows === null && symbols.length) { res.status.fallback_reason = (s.map && s.map.error) || s.error || "no answer from the keyless map"; }
        if (mapRows === null && !symbols.length) mapRows = [];
        var wanted = {}; ids.forEach(function (i) { wanted[i] = true; });
        res.evidence.map_rows = mapRows ? mapRows.filter(function (row) { return wanted[row.id]; }) : null;
        res.evidence.info_rows = Object.keys(infoRows).length ? infoRows : null;
        res.wrappers = joinWrappers(tokens, mapRows, infoRows, snapTokens, bases);
        res.wrappers.forEach(function (w) { if (w.status_source === "snapshot") w.fallback_reason = res.status.fallback_reason; });
        var tracked = res.wrappers.filter(function (w) { return w.status === "active"; }).length;
        res.verdict = tracked + " of " + res.wrappers.length + " wrapper(s) with a CMC-tracked market";
        return res;
      }, function (e) {
        res.wrappers = joinWrappers(tokens, null, {}, snapTokens);
        res.wrappers.forEach(function (w) { w.fallback_reason = "/api/status unreachable: " + e; });
        var tracked = res.wrappers.filter(function (w) { return w.status === "active"; }).length;
        res.verdict = tracked + " of " + res.wrappers.length + " wrapper(s) with a CMC-tracked market (snapshot)";
        return res;
      });
    }).then(function (r) { card.innerHTML = renderCard(r); }, function (e) {
      card.innerHTML = '<p class="verdict">The search needs this site\'s proxy (/api/roster), which did not answer: ' + esc(e) + '</p><p class="src">Ask the same question on your machine, live and keyless: <code>python3 -m shelfware ' + esc(sym) + "</code></p>";
    }).then(function () { btn.disabled = false; btn.textContent = "Ask CMC"; });
  }

  $("f").addEventListener("submit", function (e) { e.preventDefault(); ask($("t").value); });
  var q = new URLSearchParams(location.search).get("t");
  if (q) { $("t").value = q.toUpperCase(); ask(q); }
  else if (S.hero_run) {
    // the committed run of the hero ticker (docs/proof/ms.json), so the answer is on screen
    // before anything is typed; Ask CMC re-runs it live
    $("tcard").innerHTML = '<p class="src">committed run <b class="mono">' + esc(S.hero_run.asked_utc) + '</b> of <code>python3 -m shelfware ' + esc(S.hero_run.ticker) + '</code>, no key — press <b>Ask CMC</b> to re-run it live now</p>' + renderCard(S.hero_run);
  }

  getJSON("/api/health").then(function (h) {
    $("health").innerHTML = h.ok ? '<span class="status-ok">● proxy up</span> · roster key ' + (h.roster_key_configured ? "configured" : "not configured (snapshot roster)") + " · " + esc(h.snapshots) + " daily snapshot(s)" : '<span class="status-bad">● proxy not answering</span>';
  }, function () { $("health").innerHTML = '<span class="status-bad">● no proxy on this host — the search falls back to the CLI</span>'; });
})();
