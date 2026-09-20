// /api/health — is the deploy alive, which census does it carry, is the roster key configured.
// The boolean is the only thing ever said about the key.
"use strict";
const { send, preflight, readData, nowUtc } = require("./_lib.js");

module.exports = async (req, res) => {
  if (preflight(req, res)) return;
  const h = readData("health.json") || {};
  send(res, 200, {
    ok: true,
    utc: nowUtc(),
    census_utc: h.census_utc || null,
    snapshots: (h.snapshots || []).length,
    snapshot_days: h.snapshots || [],
    counts: h.counts || null,
    hero: h.hero || null,
    roster_key_configured: Boolean(process.env.CMC_API_KEY),
    commit: process.env.VERCEL_GIT_COMMIT_SHA || null,
    version: "1.0.1",
  });
};
