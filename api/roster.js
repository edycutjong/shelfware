// /api/roster?symbol=MS — the ROSTER leg. The RWA family is keyed by CoinMarketCap (keyless →
// 403 error 1005), so this is the one function that reads a secret: CMC_API_KEY from the
// Vercel environment, never from the repository. Exactly one symbol, regex-allowlisted; no
// other path, no other params. On a missing key, a 4xx/5xx or a quota error it answers from
// the committed snapshot with source: "snapshot" and its date — never silently. The snapshot
// tokens (with their committed state) ride along on every answer so the page can label the
// wrappers whose symbol the map will not filter on. 60 s cache per symbol per instance.
"use strict";
const { KEYED, SYMBOL, get, send, preflight, cached, snapshot, nowUtc } = require("./_lib.js");

function fromSnapshot(sym) {
  const snap = snapshot() || { underlyings: {}, no_tokens: {}, as_of: null };
  const e = snap.underlyings[sym];
  if (e) {
    return {
      assets: [
        { rwa_id: e.rwa_id, symbol: e.symbol, name: e.name, asset_type: e.asset_type, rwa_rank: e.rwa_rank, has_tokens: true, tokens: e.tokens },
      ],
      as_of: snap.as_of,
      snapshot_tokens: e.tokens,
    };
  }
  const n = snap.no_tokens[sym];
  if (n) {
    return {
      assets: [{ rwa_id: n[0], symbol: sym, name: n[1], asset_type: n[2], rwa_rank: n[3], has_tokens: false, tokens: [] }],
      as_of: snap.as_of,
      snapshot_tokens: [],
    };
  }
  return { assets: [], as_of: snap.as_of, snapshot_tokens: [] };
}

module.exports = async (req, res) => {
  if (preflight(req, res)) return;
  const sym = String((req.query || {}).symbol || "")
    .trim()
    .toUpperCase();
  if (!SYMBOL.test(sym)) return send(res, 400, { ok: false, error: "symbol= required: 1-16 characters of A-Z 0-9 . $ -" });
  const key = process.env.CMC_API_KEY || "";
  const out = await cached(`roster:${sym}`, async () => {
    const snap = fromSnapshot(sym);
    const base = { ok: true, fetched_utc: nowUtc(), snapshot_tokens: snap.snapshot_tokens };
    if (!key) {
      return {
        ...base,
        source: "snapshot",
        as_of: snap.as_of,
        fallback_reason: "no roster key configured on this deployment",
        credit_count: 0,
        assets: snap.assets,
        raw: null,
      };
    }
    const url = `${KEYED}/v5/real-world-assets/quotes/latest?symbol=${encodeURIComponent(sym)}`;
    const r = await get(url, key);
    // the same receipt shape /api/status returns: the URL carries the symbol only — the key travels in a header
    const meta = { upstream_url: url, upstream_http: r.http, credit_count: r.credit_count, sha256: r.sha256, elapsed_ms: r.elapsed_ms };
    if (r.http === 200 && r.raw && r.raw.data) {
      return { ...base, ...meta, source: "live", as_of: null, assets: r.raw.data.rwa_assets || [], raw: r.raw };
    }
    if (r.http === 400) {
      // CMC's RWA universe has no such symbol — a live answer, not a fallback
      return { ...base, ...meta, source: "live", as_of: null, assets: [], snapshot_tokens: [], raw: r.raw, upstream_error: r.error };
    }
    return {
      ...base,
      source: "snapshot",
      as_of: snap.as_of,
      upstream_http: r.http,
      fallback_reason: r.error || `HTTP ${r.http}`,
      credit_count: 0,
      assets: snap.assets,
      raw: r.raw,
    };
  });
  send(res, 200, out);
};
