// /api/status?symbols=wMSx,NVDAX&ids=41513,36992 — the STATE leg. Keyless first, always:
// the identical call a judge's machine makes with no key. When CoinMarketCap's anonymous pool
// refuses this host's shared egress IP (429 error 1022 — observed on the first production
// deploy), the same call is repeated on the keyed base for 1 credit and the answer says so
// under `base`. Bodies pass through verbatim under `map.raw` and `info.raw`, so the page shows
// the judge exactly what the API said. 60 s in-memory cache per query per instance; failures
// are never cached.
"use strict";
const { FILTERABLE, MAP_AUX, INFO_AUX, getKeylessFirst, send, preflight, cached, nowUtc } = require("./_lib.js");

module.exports = async (req, res) => {
  if (preflight(req, res)) return;
  const q = req.query || {};
  const symbols = String(q.symbols || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const ids = String(q.ids || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const dropped = symbols.filter((s) => !FILTERABLE.test(s));
  const ok = symbols.filter((s) => FILTERABLE.test(s)).slice(0, 20);
  const idsOk = ids.filter((s) => /^\d{1,9}$/.test(s)).slice(0, 100);
  if (!ok.length && !idsOk.length) {
    return send(res, 400, {
      ok: false,
      error: "symbols= (1-20 alphanumeric, comma-separated) and/or ids= (1-100 integers) required",
      dropped_symbols: dropped,
    });
  }
  const cacheKey = `${ok.join(",")}|${idsOk.join(",")}`;
  const apiKey = process.env.CMC_API_KEY || "";
  const failed = (x) => x && x.error && x.http !== 400;
  const out = await cached(cacheKey, async () => {
    const [map, info] = await Promise.all([
      ok.length
        ? getKeylessFirst(
            `/v1/cryptocurrency/map?listing_status=active,inactive,untracked&symbol=${encodeURIComponent(ok.join(","))}&aux=${MAP_AUX}`,
            apiKey
          )
        : Promise.resolve(null),
      idsOk.length ? getKeylessFirst(`/v2/cryptocurrency/info?id=${idsOk.join(",")}&aux=${INFO_AUX}`, apiKey) : Promise.resolve(null),
    ]);
    const bases = [map, info].filter(Boolean).map((x) => x.base);
    return {
      ok: true,
      source: bases.every((b) => b === "keyless")
        ? "keyless /public-api — no key was used"
        : "keyless /public-api refused this host's shared IP (anonymous limit); the identical call on the keyed base answered, 1 credit each",
      fetched_utc: nowUtc(),
      dropped_symbols: dropped,
      map,
      info,
      failed: failed(map) || failed(info),
    };
  });
  send(res, out.failed ? 502 : 200, out);
};
