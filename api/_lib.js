// Shared by the three functions. Underscore-prefixed: not a route.
"use strict";
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const KEYED = "https://pro-api.coinmarketcap.com";
const KEYLESS = "https://pro-api.coinmarketcap.com/public-api";
const SYMBOL = /^[A-Za-z0-9.$-]{1,16}$/; // what the RWA roster accepts
const FILTERABLE = /^[A-Za-z0-9]{1,16}$/; // what the map's symbol filter accepts (dots rejected, verified 2026-09-18)
const MAP_AUX = "first_historical_data,last_historical_data,status,platform";
const INFO_AUX = "status,date_added,platform";
const TTL_MS = 60000;
const cache = new Map();

function readData(name) {
  for (const base of [process.cwd(), path.join(__dirname, "..")]) {
    const p = path.join(base, "data", name);
    if (fs.existsSync(p)) return JSON.parse(fs.readFileSync(p, "utf8"));
  }
  return null;
}

let rosterSnapshot = null;
function snapshot() {
  if (!rosterSnapshot) rosterSnapshot = readData("roster_snapshot.json");
  return rosterSnapshot;
}

function cached(key, fn) {
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL_MS) return Promise.resolve({ ...hit.value, cached: true });
  return fn().then((value) => {
    if (value && value.ok !== false && !value.failed) cache.set(key, { at: Date.now(), value });
    return value;
  });
}

/** One GET, backoff on 429/5xx (1 s, 2 s), the body passed through verbatim under `raw`.
 *  Returns {url, http, credit_count, bytes, sha256, elapsed_ms, raw, error}. Never throws.
 *  A keyless 429 with error_code 1022 ("limit for anonymous access") is not retried: from a
 *  shared cloud egress IP that pool is exhausted for good, and waiting only wastes the reader's
 *  time (observed on the first production deploy, 2026-09-18). */
async function get(url, key) {
  const headers = { Accept: "application/json", "User-Agent": "shelfware-proxy/0.1" };
  if (key) headers["X-CMC_PRO_API_KEY"] = key;
  const t0 = Date.now();
  let res;
  let text;
  let attempt = 0;
  for (;;) {
    attempt += 1;
    try {
      res = await fetch(url, { headers, signal: AbortSignal.timeout(20000) });
      text = await res.text();
    } catch (e) {
      res = null;
      text = String(e);
    }
    const status = res ? res.status : 0;
    const anonymousExhausted = !key && status === 429 && /"error_code":\s*1022/.test(text || "");
    if ((status === 429 || status >= 500 || status === 0) && attempt < 3 && !anonymousExhausted) {
      await new Promise((r) => setTimeout(r, 1000 * attempt));
      continue;
    }
    break;
  }
  let raw = null;
  try {
    raw = JSON.parse(text);
  } catch (e) {
    raw = null;
  }
  const status = res ? res.status : 0;
  const st = raw && raw.status ? raw.status : {};
  const error =
    status === 200 ? null : st.error_message ? `HTTP ${status} error_code ${st.error_code}: ${st.error_message}` : `HTTP ${status}`;
  return {
    url,
    http: status,
    credit_count: st.credit_count == null ? null : st.credit_count,
    bytes: Buffer.byteLength(text || ""),
    sha256: crypto.createHash("sha256").update(text || "").digest("hex").slice(0, 16),
    elapsed_ms: Date.now() - t0,
    attempts: attempt,
    raw,
    error,
  };
}

/** The keyless surface first — live for anyone, 0 credits. If the anonymous pool refuses
 *  (per-IP, and this host's egress IP is shared with every other tenant), the IDENTICAL call
 *  on the keyed base, 1 credit, labelled `base: "keyed"` with the keyless error kept beside
 *  it. The page prints which base answered; a judge's own machine stays keyless. */
async function getKeylessFirst(pathAndQuery, key) {
  const first = await get(`${KEYLESS}${pathAndQuery}`);
  if (!first.error || first.http === 400 || !key) return { ...first, base: "keyless" };
  const second = await get(`${KEYED}${pathAndQuery}`, key);
  return { ...second, base: "keyed", keyless_error: first.error, keyless_http: first.http };
}

/** CORS, open: the same site/ is served from GitHub Pages (shelfware.edycu.dev) as well as from
 *  this deployment, and the Pages copy calls these functions cross-origin. Nothing here is
 *  private — the responses are CoinMarketCap rows and a health line — so any origin may read. */
function cors(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Accept, Content-Type");
  res.setHeader("Access-Control-Max-Age", "86400");
}

/** A CORS preflight is answered here, before any work: 204, the allow headers, no body.
 *  Returns true when the request was a preflight and has been answered. */
function preflight(req, res) {
  if ((req.method || "GET").toUpperCase() !== "OPTIONS") return false;
  cors(res);
  res.status(204).send("");
  return true;
}

function send(res, status, body) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  cors(res);
  res.setHeader("Cache-Control", "no-store");
  res.status(status).send(JSON.stringify(body));
}

function nowUtc() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

module.exports = { KEYED, KEYLESS, SYMBOL, FILTERABLE, MAP_AUX, INFO_AUX, get, getKeylessFirst, send, cors, preflight, cached, snapshot, readData, nowUtc };
