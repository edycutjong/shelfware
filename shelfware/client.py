"""One HTTP GET against CoinMarketCap, with backoff and a receipt.

Keyless by default: `get(..., keyed=False)` goes to /public-api and never sends a key, even
when one is exported — that is the point of the status leg, it is live for anyone at 0 credits.
`keyed=True` needs a key and goes to the Pro base. Errors are RETURNED in the meta, never
swallowed and never raised as a traceback, so a rate limit can never be reported as a fact
about a token.
"""

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

KEYED_BASE = "https://pro-api.coinmarketcap.com"
KEYLESS_BASE = "https://pro-api.coinmarketcap.com/public-api"
KEY_VARS = ("CMC_API_KEY", "COINMARKETCAP_API_KEY", "CMC_PRO_API_KEY")
RETRIES = 4
BACKOFF_S = (2, 4, 8, 16)
TRANSIENT = {429, 500, 502, 503, 504}
EX_TEMPFAIL = 75  # sysexits.h: temporary failure — the keyless pool is exhausted, retry later

RWA_MAP_PAGE = 250
QUOTES_BATCH = 200
CMC_MAP_PAGE = 5000
MAP_AUX = "first_historical_data,last_historical_data,status,platform"
INFO_AUX = "status,date_added,platform"
INFO_BATCH = 200
ALL_STATUSES = "active,inactive,untracked"
# the map's symbol filter takes alphanumerics only; CMC's own RWA symbols include NVDA.D and
# AI.FRx, which it rejects with HTTP 400 for the whole call (verified 2026-09-18)
FILTERABLE = re.compile(r"^[A-Za-z0-9]+$")


def api_key(env=None):
    """The exported key, read at call time. A blank variable is no key."""
    env = os.environ if env is None else env
    for var in KEY_VARS:
        v = (env.get(var) or "").strip()
        if v:
            return v
    return None


def utc_now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def describe_error(js, http):
    """CMC's own error code and message when the body carries them, never a raw body."""
    st = js.get("status") if isinstance(js, dict) else None
    if isinstance(st, dict) and st.get("error_message"):
        return f"HTTP {http} error_code {st.get('error_code')}: {st.get('error_message')}"
    return f"HTTP {http}"


class NoKey(RuntimeError):
    """A keyed call was asked for without a key. The CLI turns this into one line."""


class Client:
    def __init__(self, api_key=None, receipt=None, sleep=time.sleep, opener=None, timeout=90):
        self.api_key = api_key
        self.receipt = receipt if receipt is not None else []
        self._sleep = sleep
        self._open = opener or urllib.request.urlopen
        self.timeout = timeout

    # ── the one GET ────────────────────────────────────────────────────────────

    def get(self, path, params=None, keyed=False, label=None):
        """Returns (json, meta). meta.error is None on a usable 200; meta.throttled is True
        when the call died on a transient status after every retry."""
        if keyed and not self.api_key:
            raise NoKey(f"{path} needs a key: export CMC_API_KEY (a free Basic key is enough)")
        base = KEYED_BASE if keyed else KEYLESS_BASE
        url = f"{base}{path}?{urllib.parse.urlencode(params)}" if params else f"{base}{path}"
        headers = {"Accept": "application/json", "User-Agent": "shelfware/0.1 (+stdlib urllib)"}
        if keyed:
            headers["X-CMC_PRO_API_KEY"] = self.api_key
        meta = {
            "call": label or path,
            "url": url,
            "keyed": keyed,
            "http": None,
            "bytes": 0,
            "sha256": None,
            "credit_count": None,
            "rows": None,
            "elapsed_ms": None,
            "utc": utc_now(),
            "error": None,
            "throttled": False,
            "attempts": 0,
        }
        t0 = time.perf_counter()
        js, body, code = None, b"", None
        for attempt in range(RETRIES):
            meta["attempts"] = attempt + 1
            try:
                with self._open(
                    urllib.request.Request(url, headers=headers), timeout=self.timeout
                ) as r:
                    body, code = r.read(), int(r.status)
            except urllib.error.HTTPError as e:
                body, code = e.read(), int(e.code)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                # a dropped connection is congestion, not a verdict: retry it like a 5xx
                body, code = str(e).encode(), None
            if code in TRANSIENT or code is None:
                if attempt < RETRIES - 1:
                    self._sleep(BACKOFF_S[attempt])
                    continue
                meta["throttled"] = True
            break
        meta["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
        meta["http"] = code
        meta["bytes"] = len(body)
        meta["sha256"] = hashlib.sha256(body).hexdigest()[:16]
        try:
            js = json.loads(body) if body else {}
        except ValueError:
            js = {}
            meta["error"] = f"HTTP {code}: response was not JSON"
        if isinstance(js, dict):
            meta["credit_count"] = (js.get("status") or {}).get("credit_count")
        if code != 200 and meta["error"] is None:
            meta["error"] = (
                f"{describe_error(js, code)} — transient status on every retry"
                if meta["throttled"]
                else describe_error(js, code)
                if code is not None
                else f"no response: {body[:120].decode('utf-8', 'replace')}"
            )
        self.receipt.append(meta)
        return js, meta

    # ── the four ledgers ───────────────────────────────────────────────────────

    def rwa_map(self):
        """A — every underlying with rwa_id, symbol, asset_type, rwa_rank, has_tokens. Keyed,
        0 credits, 250 per page, `has_more` paging."""
        rows, start = [], 1
        while True:
            js, meta = self.get(
                "/v5/real-world-assets/map",
                {"start": start, "limit": RWA_MAP_PAGE, "sort": "rwa_id"},
                keyed=True,
                label=f"rwa/map start={start}",
            )
            if meta["error"]:
                raise RuntimeError(f"rwa/map failed: {meta['error']}")
            data = js.get("data") or {}
            page = data.get("rwa_assets") or []
            meta["rows"] = len(page)
            rows.extend(page)
            if not data.get("has_more") or not page:
                return rows
            start += RWA_MAP_PAGE

    def rwa_quotes(self, rwa_ids=None, symbol=None):
        """B — rwa_assets[] each with tokens[] (crypto_id, issuer_id, issuer_name, price,
        market_cap, volume_24h — the price:null rows included). Keyed, 1 credit per 250 assets."""
        if symbol is not None:
            js, meta = self.get(
                "/v5/real-world-assets/quotes/latest",
                {"symbol": symbol},
                keyed=True,
                label=f"rwa/quotes symbol={symbol}",
            )
            assets = (js.get("data") or {}).get("rwa_assets") or [] if not meta["error"] else []
            meta["rows"] = len(assets)
            return assets, meta
        assets, ids = [], [str(i) for i in rwa_ids]
        for i in range(0, len(ids), QUOTES_BATCH):
            batch = ids[i : i + QUOTES_BATCH]
            js, meta = self.get(
                "/v5/real-world-assets/quotes/latest",
                {"rwa_id": ",".join(batch), "skip_invalid": "true"},
                keyed=True,
                label=f"rwa/quotes batch {i // QUOTES_BATCH + 1} ({len(batch)} ids)",
            )
            if meta["error"]:
                raise RuntimeError(f"rwa/quotes failed: {meta['error']}")
            page = (js.get("data") or {}).get("rwa_assets") or []
            meta["rows"] = sum(len(a.get("tokens") or []) for a in page)
            assets.extend(page)
        return assets, None

    def issuers(self):
        """C — the issuer registry with num_tokens declared. Keyed, 1 credit."""
        js, meta = self.get(
            "/v5/real-world-assets/issuers/list",
            {"limit": 250},
            keyed=True,
            label="rwa/issuers/list",
        )
        if meta["error"]:
            raise RuntimeError(f"rwa/issuers/list failed: {meta['error']}")
        rows = (js.get("data") or {}).get("issuers") or []
        meta["rows"] = len(rows)
        return rows

    def cmc_map(self, symbols=None):
        """D — listing state per crypto_id. KEYLESS, always: this call never carries the key.

        Full map (symbols=None): 8 pages of 5,000 across active,inactive,untracked, ~9 MB.
        Per ticker: symbol= filter. An unknown symbol rejects the WHOLE call with HTTP 400
        ('Invalid value for "symbol": "X"'), so rejected symbols are dropped and the call
        retried without them — a wrapper whose symbol CMC will not filter on is unresolved.
        Returns ({id: row}, meta_of_last_call, dropped_symbols)."""
        rows, dropped = {}, []
        if symbols is not None:
            wanted = [s for s in dict.fromkeys(symbols) if s]
            dropped = [s for s in wanted if not FILTERABLE.match(s)]
            wanted = [s for s in wanted if FILTERABLE.match(s)]
            meta = None
            for _ in range(len(wanted) + 1):
                if not wanted:
                    break
                js, meta = self.get(
                    "/v1/cryptocurrency/map",
                    {"listing_status": ALL_STATUSES, "symbol": ",".join(wanted), "aux": MAP_AUX},
                    keyed=False,
                    label=f"cmc/map symbol={','.join(wanted)}",
                )
                if meta["http"] == 400 and 'Invalid value for "symbol"' in (meta["error"] or ""):
                    bad = meta["error"].rsplit('"symbol": "', 1)[-1].rstrip('"').strip()
                    hit = next((s for s in wanted if s.upper() == bad.upper()), None)
                    if hit is None:
                        break
                    dropped.append(hit)
                    wanted.remove(hit)
                    continue
                if not meta["error"]:
                    for r in js.get("data") or []:
                        rows[r["id"]] = r
                    meta["rows"] = len(js.get("data") or [])
                break
            return rows, meta, dropped
        start, meta = 1, None
        while True:
            js, meta = self.get(
                "/v1/cryptocurrency/map",
                {
                    "listing_status": ALL_STATUSES,
                    "start": start,
                    "limit": CMC_MAP_PAGE,
                    "aux": MAP_AUX,
                },
                keyed=False,
                label=f"cmc/map start={start}",
            )
            if meta["error"]:
                raise RuntimeError(f"cmc/map failed: {meta['error']}")
            page = js.get("data") or []
            meta["rows"] = len(page)
            for r in page:
                rows[r["id"]] = r
            if len(page) < CMC_MAP_PAGE:
                return rows, meta, dropped
            start += CMC_MAP_PAGE

    def cmc_info(self, ids):
        """E — /v2/cryptocurrency/info by id, KEYLESS: `status` (active|inactive — a coarser
        vocabulary than the map's) and `date_added`, the day CMC listed the coin. Untracked map
        rows carry no dates; this is where a shelf wrapper's listing date lives. An unknown id
        rejects the whole call with HTTP 400 naming every bad id, so those are dropped and the
        batch retried. Returns ({id: row}, [meta per call], dropped_ids)."""
        rows, metas, dropped = {}, [], []
        wanted = [int(i) for i in dict.fromkeys(ids) if i is not None]
        for i in range(0, len(wanted), INFO_BATCH):
            batch = wanted[i : i + INFO_BATCH]
            for _ in range(3):
                if not batch:
                    break
                js, meta = self.get(
                    "/v2/cryptocurrency/info",
                    {"id": ",".join(map(str, batch)), "aux": INFO_AUX},
                    keyed=False,
                    label=f"cmc/info batch {i // INFO_BATCH + 1} ({len(batch)} ids)",
                )
                metas.append(meta)
                if meta["http"] == 400 and "Invalid value for 'id'" in (meta["error"] or ""):
                    bad = meta["error"].rsplit("'id': '", 1)[-1].rstrip("'").split(",")
                    bad_ids = {int(b) for b in bad if b.strip().isdigit()}
                    if not bad_ids & set(batch):
                        break
                    dropped.extend(sorted(bad_ids & set(batch)))
                    batch = [b for b in batch if b not in bad_ids]
                    continue
                if not meta["error"]:
                    data = js.get("data") or {}
                    for k, v in data.items():
                        rows[int(k)] = v
                    meta["rows"] = len(data)
                break
        return rows, metas, dropped

    def key_info(self):
        """The credit ledger, before and after — keyed, 0 credits. None without a key."""
        if not self.api_key:
            return None
        js, meta = self.get("/v1/key/info", keyed=True, label="key/info")
        return None if meta["error"] else (js.get("data") or {}).get("usage")


def credits_used(receipt):
    """Keyed credits only. The keyless envelope also says credit_count: 1, but nothing is
    charged to any key — so the sum is over keyed calls, and the receipt says so."""
    return sum(int(m.get("credit_count") or 0) for m in receipt if m.get("keyed"))
