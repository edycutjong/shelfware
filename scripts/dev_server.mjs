#!/usr/bin/env node
// Serve site/ and the three api/ functions locally, the way Vercel does — for a local look
// at the one screen before a deploy.     node scripts/dev_server.mjs     (port 8103)
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PORT = Number(process.env.PORT || 8103);
const routes = {
  "/api/status": require(path.join(ROOT, "api/status.js")),
  "/api/roster": require(path.join(ROOT, "api/roster.js")),
  "/api/health": require(path.join(ROOT, "api/health.js")),
};

http
  .createServer(async (req, res) => {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const fn = routes[url.pathname];
    if (fn) {
      req.query = Object.fromEntries(url.searchParams.entries());
      res.status = (c) => {
        res.statusCode = c;
        return res;
      };
      res.send = (b) => res.end(b);
      try {
        await fn(req, res);
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ ok: false, error: String(e) }));
      }
      return;
    }
    let file = path.join(ROOT, "site", url.pathname === "/" ? "index.html" : url.pathname);
    // a directory resolves to its index.html, as Vercel does: /judge -> site/judge/index.html
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
    if (file.startsWith(path.join(ROOT, "site")) && fs.existsSync(file) && fs.statSync(file).isFile()) {
      const types = { ".html": "text/html; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml", ".json": "application/json", ".css": "text/css", ".js": "text/javascript" };
      res.setHeader("Content-Type", types[path.extname(file)] || "application/octet-stream");
      fs.createReadStream(file).pipe(res);
    } else {
      res.statusCode = 404;
      res.end("not found");
    }
  })
  .listen(PORT, () => console.log(`shelfware dev server -> http://localhost:${PORT}`));
