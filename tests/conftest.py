"""Fixtures: a small synthetic ledger set built around the anomalies the counting rules exist
for, and a fake HTTP opener so the client can be exercised without the network.

The synthetic set mirrors real rows observed live on 2026-09-18 (ids and shapes are real; the
numbers are small so a test can count them by eye)."""

import io
import json
import sys
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BACKED, DINARI, FIDELITY, PAXOS, BSTOCKS, DERIV = (
    "6878977dcbbf471de3366e85",
    "688c6172abae9b5b9fb30359",
    "fid000000000000000000001",
    "68904c24abae9b5b9fb35815",
    "6a2aed5097c45356b1a5f710",
    "695e11f774b54210f3b95dc3",
)
NOW = datetime(2026, 9, 19, 0, 0, tzinfo=UTC)


def tok(crypto_id, symbol, issuer_id, issuer_name, price=None, mcap=None):
    return {
        "crypto_id": crypto_id,
        "symbol": symbol,
        "name": f"{symbol} wrapper",
        "issuer_id": issuer_id,
        "issuer_name": issuer_name,
        "price": price,
        "market_cap": mcap,
        "volume_24h": None if price is None else 1.0,
    }


@pytest.fixture
def rwa_rows():
    return [
        {
            "rwa_id": 1,
            "symbol": "GOLD",
            "name": "Gold",
            "asset_type": "commodity",
            "rwa_rank": 1,
            "has_tokens": True,
        },
        {
            "rwa_id": 2,
            "symbol": "NVDA",
            "name": "Nvidia",
            "asset_type": "stock",
            "rwa_rank": 2,
            "has_tokens": True,
        },
        {
            "rwa_id": 35,
            "symbol": "MS",
            "name": "Morgan Stanley",
            "asset_type": "stock",
            "rwa_rank": 43,
            "has_tokens": True,
        },
        {
            "rwa_id": 80,
            "symbol": "APH",
            "name": "Amphenol",
            "asset_type": "stock",
            "rwa_rank": 80,
            "has_tokens": True,
        },
        {
            "rwa_id": 300,
            "symbol": "NOISS",
            "name": "No Issuer Co",
            "asset_type": "etf",
            "rwa_rank": 300,
            "has_tokens": True,
        },
        {
            "rwa_id": 700,
            "symbol": "DEAD",
            "name": "Delisted Co",
            "asset_type": "stock",
            "rwa_rank": 700,
            "has_tokens": True,
        },
        {
            "rwa_id": 900,
            "symbol": "VVV",
            "name": "Valvoline",
            "asset_type": "stock",
            "rwa_rank": 900,
            "has_tokens": True,
        },
        {
            "rwa_id": 999,
            "symbol": "XYZ",
            "name": "Untokenised Co",
            "asset_type": "stock",
            "rwa_rank": 999,
            "has_tokens": False,
        },
    ]


@pytest.fixture
def quote_assets(rwa_rows):
    by = {r["symbol"]: r for r in rwa_rows}

    def asset(sym, tokens):
        r = by[sym]
        return {**r, "tokens": tokens}

    return [
        asset("GOLD", [tok(4705, "PAXG", PAXOS, "Paxos", 4371.0, 1.9e9)]),
        asset(
            "NVDA",
            [
                tok(36992, "NVDAX", BACKED, "Backed Assets", 222.0, 4.1e7),
                tok(28616, "NVDA.D", DINARI, "Dinari Assets"),
                tok(7913, "NVDA", DERIV, "NA (Derivatives)", 222.5, 0.0),
            ],
        ),
        asset("MS", [tok(41513, "wMSx", BACKED, "Backed Assets")]),
        asset(
            "APH",
            [
                tok(41500, "wAPHx", BACKED, "Backed Assets"),
                tok(28600, "APH.D", DINARI, "Dinari Assets"),
            ],
        ),
        asset("NOISS", [tok(50001, "NOI", None, None, 1.0, 10.0)]),
        asset("DEAD", [tok(60001, "DEADT", BSTOCKS, "bStocks", None, None)]),
        asset("VVV", [tok(40784, "VVV", DERIV, "NA (Derivatives)", None, None)]),
    ]


@pytest.fixture
def cmc_map():
    def row(i, sym, status, platform=None, first=None):
        r = {"id": i, "symbol": sym, "name": f"{sym} wrapper", "status": status}
        if platform:
            r["platform"] = {"name": platform[0], "token_address": platform[1]}
        if first:
            r["first_historical_data"] = first
            r["last_historical_data"] = "2026-09-18T21:30:00.000Z"
        return r

    rows = [
        row(4705, "PAXG", "active", ("Ethereum", "0x4580"), "2019-09-26T02:25:00.000Z"),
        row(36992, "NVDAX", "active", ("Solana", "Xsc9"), "2025-06-28T20:05:00.000Z"),
        row(28616, "NVDA.D", "untracked", ("Arbitrum", "0x4DaF")),
        row(7913, "NVDA", "active", None, "2026-08-20T00:00:00.000Z"),
        row(41513, "wMSx", "untracked", ("X Layer", "0x2874A11805783324C54562eDB1A641C5d1d077a5")),
        row(41500, "wAPHx", "untracked", ("X Layer", "0xAPH")),
        row(28600, "APH.D", "untracked", ("Arbitrum", "0xAPHD")),
        row(50001, "NOI", "active", None, "2026-09-01T00:00:00.000Z"),
        row(60001, "DEADT", "inactive", None, "2025-01-01T00:00:00.000Z"),
        # 40784 (VVV) deliberately absent: unresolved
    ]
    return {r["id"]: r for r in rows}


@pytest.fixture
def issuers():
    return [
        {"issuer_id": BACKED, "name": "Backed Assets", "num_tokens": 1176},
        {"issuer_id": DINARI, "name": "Dinari Assets", "num_tokens": 91},
        {"issuer_id": FIDELITY, "name": "Fidelity Investments Assets", "num_tokens": 1},
        {"issuer_id": PAXOS, "name": "Paxos", "num_tokens": 1},
        {"issuer_id": BSTOCKS, "name": "bStocks", "num_tokens": 77},
        {"issuer_id": DERIV, "name": "NA (Derivatives)", "num_tokens": 247},
    ]


@pytest.fixture
def info_rows():
    return {
        41513: {
            "id": 41513,
            "symbol": "wMSx",
            "status": "inactive",
            "date_added": "2026-08-11T16:24:36.000Z",
        },
        28616: {
            "id": 28616,
            "symbol": "NVDA.D",
            "status": "inactive",
            "date_added": "2023-12-07T10:41:41.000Z",
        },
        41500: {
            "id": 41500,
            "symbol": "wAPHx",
            "status": "inactive",
            "date_added": "2026-08-11T16:24:36.000Z",
        },
        28600: {
            "id": 28600,
            "symbol": "APH.D",
            "status": "inactive",
            "date_added": "2024-01-01T00:00:00.000Z",
        },
    }


@pytest.fixture
def committed_census():
    return json.loads((ROOT / "data" / "census.json").read_text())


# ── a fake HTTP layer ─────────────────────────────────────────────────────────


class FakeResponse(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def http_error(url, code, body):
    return urllib.error.HTTPError(url, code, "err", {}, io.BytesIO(body))


class FakeOpener:
    """opener(request, timeout) -> response, scripted per call. Each script entry is either
    (status, json_body) or a callable(url) returning that. Records every request."""

    def __init__(self, *script):
        self.script = list(script)
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        entry = (
            self.script.pop(0)
            if self.script
            else (200, {"data": [], "status": {"credit_count": 1}})
        )
        if callable(entry):
            entry = entry(req.full_url)
        status, body = entry
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        if status == 200:
            return FakeResponse(raw, 200)
        raise http_error(req.full_url, status, raw)


def envelope(data, credit_count=1, error_code=0, error_message=None):
    return {
        "data": data,
        "status": {
            "timestamp": "2026-09-18T22:00:00.000Z",
            "error_code": error_code,
            "error_message": error_message,
            "credit_count": credit_count,
        },
    }
