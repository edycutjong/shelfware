// /api/status?symbols=wMSx,NVDAX&ids=41513,36992 — the STATE leg. Keyless, always: this
// function holds no secret and cannot use one. It passes CoinMarketCap's bodies through
// verbatim under `map.raw` and `info.raw`, so the page shows the judge exactly what the API
// said. 60 s in-memory cache per query per instance.
"use strict";
const { KEYLESS, FILTERABLE, MAP_AUX, INFO_AUX, get, send, cached, nowUtc } = require("./_lib.js");

module.exports = async (req, res) => {
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
  const key = `${ok.join(",")}|${idsOk.join(",")}`;
  const out = await cached(key, async () => {
    const [map, info] = await Promise.all([
      ok.length
        ? get(
            `${KEYLESS}/v1/cryptocurrency/map?listing_status=active,inactive,untracked&symbol=${encodeURIComponent(ok.join(","))}&aux=${MAP_AUX}`
          )
        : Promise.resolve(null),
      idsOk.length ? get(`${KEYLESS}/v2/cryptocurrency/info?id=${idsOk.join(",")}&aux=${INFO_AUX}`) : Promise.resolve(null),
    ]);
    return {
      ok: true,
      source: "keyless /public-api — no key is used by this function",
      fetched_utc: nowUtc(),
      dropped_symbols: dropped,
      map,
      info,
    };
  });
  const failed = (x) => x && x.error && x.http !== 400;
  send(res, failed(out.map) || failed(out.info) ? 502 : 200, out);
};
