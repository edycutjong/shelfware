// The three Vercel functions, exercised in-process with a stubbed fetch.
//     node --test tests/api.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const status = require(path.join(ROOT, "api/status.js"));
const roster = require(path.join(ROOT, "api/roster.js"));
const health = require(path.join(ROOT, "api/health.js"));

const envelope = (data, credit = 1, code = 0, msg = null) => ({
  data,
  status: { timestamp: "2026-09-18T22:00:00.000Z", error_code: code, error_message: msg, credit_count: credit },
});

/** Script fetch: each entry is [status, body] or (url, headers) => [status, body]. Records URLs and headers. */
function stubFetch(...script) {
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push({ url, headers: opts.headers });
    let entry = script.length ? script.shift() : [200, envelope([])];
    if (typeof entry === "function") entry = entry(url, opts.headers);
    const [code, body] = entry;
    return { status: code, text: async () => JSON.stringify(body) };
  };
  return calls;
}

function run(fn, query, env = {}) {
  const saved = process.env.CMC_API_KEY;
  if ("CMC_API_KEY" in env) process.env.CMC_API_KEY = env.CMC_API_KEY;
  else delete process.env.CMC_API_KEY;
  const res = { headers: {}, code: null, body: null, setHeader(k, v) { this.headers[k] = v; }, status(c) { this.code = c; return this; }, send(b) { this.body = JSON.parse(b); } };
  return fn({ query }, res).then(() => {
    if (saved === undefined) delete process.env.CMC_API_KEY;
    else process.env.CMC_API_KEY = saved;
    return res;
  });
}

test("status: keyless first, no key sent, dotted symbols dropped before the call", async () => {
  const calls = stubFetch([200, envelope([{ id: 41513, symbol: "wMSx", status: "untracked" }])], [200, envelope({ 41513: { id: 41513, status: "inactive" } })]);
  const res = await run(status, { symbols: "wMSx,NVDA.D", ids: "41513" }, { CMC_API_KEY: "k" });
  assert.equal(res.code, 200);
  assert.deepEqual(res.body.dropped_symbols, ["NVDA.D"]);
  assert.equal(res.body.map.base, "keyless");
  assert.ok(calls.every((c) => c.url.includes("/public-api/") && !("X-CMC_PRO_API_KEY" in c.headers)));
  assert.ok(!calls[0].url.includes("NVDA.D"));
  assert.equal(res.body.map.raw.data[0].status, "untracked");
});

test("status: a refused anonymous pool repeats the identical call keyed and says so", async () => {
  const refused = [429, envelope(null, 0, 1022, "You've reached the limit for anonymous access.")];
  const calls = stubFetch(refused, refused, [200, envelope([{ id: 41513, status: "untracked" }], 1)], [200, envelope({ 41513: { status: "inactive" } }, 1)]);
  const res = await run(status, { symbols: "wMSxb", ids: "41513" }, { CMC_API_KEY: "k" });
  assert.equal(res.code, 200);
  assert.equal(res.body.map.base, "keyed");
  assert.match(res.body.map.keyless_error, /1022/);
  assert.match(res.body.source, /keyed base/);
  const keyed = calls.filter((c) => c.headers["X-CMC_PRO_API_KEY"] === "k");
  assert.equal(keyed.length, 2);
  assert.ok(keyed.every((c) => !c.url.includes("/public-api/")));
  assert.equal(calls.length, 4, "a 1022 refusal is not retried keyless — it is terminal for that IP");
});

test("status: with no key a refused pool is a 502 with the error, never cached", async () => {
  const refused = [429, envelope(null, 0, 1022, "limit")];
  stubFetch(refused, refused);
  const res = await run(status, { symbols: "wMSxc", ids: "41514" }, {});
  assert.equal(res.code, 502);
  assert.equal(res.body.failed, true);
  assert.match(res.body.map.error, /1022/);
  stubFetch([200, envelope([])], [200, envelope({})]);
  const again = await run(status, { symbols: "wMSxc", ids: "41514" }, {});
  assert.equal(again.code, 200, "the failure was not served from the cache");
});

test("status: rejects an empty or malformed query", async () => {
  stubFetch();
  const res = await run(status, { symbols: "NVDA.D" }, {});
  assert.equal(res.code, 400);
  assert.deepEqual(res.body.dropped_symbols, ["NVDA.D"]);
});

test("roster: without a key the committed snapshot answers and says so", async () => {
  const calls = stubFetch();
  const res = await run(roster, { symbol: "ms" }, {});
  assert.equal(res.code, 200);
  assert.equal(res.body.source, "snapshot");
  assert.match(res.body.fallback_reason, /no roster key/);
  assert.equal(res.body.assets[0].symbol, "MS");
  assert.ok(res.body.assets[0].tokens.some((t) => t.crypto_id === 41513));
  assert.equal(res.body.snapshot_tokens[0].status, "untracked");
  assert.equal(calls.length, 0);
});

test("roster: with a key the live body passes through verbatim and the snapshot tokens ride along", async () => {
  const body = envelope({ rwa_assets: [{ rwa_id: 35, symbol: "MS", has_tokens: true, tokens: [{ crypto_id: 41513, symbol: "wMSx", price: null }] }] }, 1);
  const calls = stubFetch([200, body]);
  const res = await run(roster, { symbol: "MS1" }, { CMC_API_KEY: "k" });
  assert.equal(res.body.source, "live");
  assert.equal(res.body.credit_count, 1);
  assert.deepEqual(res.body.raw, body);
  assert.equal(calls[0].headers["X-CMC_PRO_API_KEY"], "k");
  assert.ok(calls[0].url.startsWith("https://pro-api.coinmarketcap.com/v5/real-world-assets/quotes/latest?symbol=MS1"));
  // the receipt names the upstream URL like /api/status does — and the key is never in it
  assert.equal(res.body.upstream_url, calls[0].url);
  assert.ok(!JSON.stringify(res.body).includes('"k"'));
});

test("roster: an unknown symbol is a live answer with no assets, a quota error is a labelled snapshot", async () => {
  stubFetch([400, envelope(null, 0, 400, 'Invalid value for "symbol": "ZZZZ"')]);
  let res = await run(roster, { symbol: "ZZZZ" }, { CMC_API_KEY: "k" });
  assert.equal(res.body.source, "live");
  assert.deepEqual(res.body.assets, []);
  const quota = [429, envelope(null, 0, 1008, "quota")];
  stubFetch(quota, quota, quota);
  res = await run(roster, { symbol: "NVDA" }, { CMC_API_KEY: "k" });
  assert.equal(res.body.source, "snapshot");
  assert.match(res.body.fallback_reason, /1008/);
  assert.ok(res.body.assets[0].tokens.length > 1);
});

test("roster: exactly one allowlisted symbol", async () => {
  stubFetch();
  const res = await run(roster, { symbol: "MS;DROP" }, {});
  assert.equal(res.code, 400);
});

test("health: reports the census date and only a boolean about the key", async () => {
  const res = await run(health, {}, { CMC_API_KEY: "k" });
  assert.equal(res.body.ok, true);
  assert.match(res.body.census_utc, /^2026-/);
  assert.equal(res.body.roster_key_configured, true);
  assert.ok(!JSON.stringify(res.body).includes('"k"'));
  assert.ok(res.body.snapshots >= 1);
});

test("cors: every function answers with Access-Control-Allow-Origin: * — the GitHub Pages copy calls them cross-origin", async () => {
  stubFetch([200, envelope([{ id: 41513, symbol: "wMSx", status: "untracked" }])], [200, envelope({ 41513: { status: "inactive" } })]);
  for (const [fn, q] of [[health, {}], [status, { symbols: "wMSx", ids: "41513" }], [roster, { symbol: "MS" }]]) {
    const res = await run(fn, q, {});
    assert.equal(res.headers["Access-Control-Allow-Origin"], "*");
    assert.match(res.headers["Access-Control-Allow-Methods"], /GET/);
  }
});

test("cors: an OPTIONS preflight is answered 204 with the allow headers, no body, and no upstream call", async () => {
  const calls = stubFetch();
  for (const fn of [health, status, roster]) {
    const res = { headers: {}, code: null, body: undefined, setHeader(k, v) { this.headers[k] = v; }, status(c) { this.code = c; return this; }, send(b) { this.body = b; } };
    await fn({ method: "OPTIONS", query: {} }, res);
    assert.equal(res.code, 204);
    assert.equal(res.body, "");
    assert.equal(res.headers["Access-Control-Allow-Origin"], "*");
    assert.match(res.headers["Access-Control-Allow-Headers"], /Accept/);
  }
  assert.equal(calls.length, 0);
});
