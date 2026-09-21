"""The command line a judge runs: help, exit codes, both leg sources on the card, verify."""

import io
import json
import re
from pathlib import Path

from conftest import ROOT, FakeOpener, envelope
from test_lookup import MS_INFO, MS_MAP_ROW, snapshot

from shelfware import cli
from shelfware.client import EX_TEMPFAIL, Client, NoKey


def noop(_):
    pass


def run(argv, capsys):
    rc = cli.main(argv)
    return rc, capsys.readouterr().out


def test_help_lists_every_subcommand_and_the_exit_codes(capsys):
    rc, out = run(["--help"], capsys)
    assert rc == 0
    for word in ("TICKER", "census", "verify", "delta", "CMC_API_KEY", "75"):
        assert word in out
    rc, out = run([], capsys)
    assert rc == 0 and out.startswith("usage: shelfware")


def test_version_flag(capsys):
    rc, out = run(["--version"], capsys)
    assert rc == 0 and out.strip() == f"shelfware {cli.__version__}"
    assert re.fullmatch(r"\d+\.\d+\.\d+", cli.__version__)


def test_census_without_a_key_refuses_with_one_line_and_exit_1(monkeypatch, capsys):
    """The census must never silently replay. With no key it says why, in one line,
    and points at the committed run."""
    for var in ("CMC_API_KEY", "COINMARKETCAP_API_KEY", "CMC_PRO_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    rc, out = run(["census"], capsys)
    assert rc == 1
    assert out.count("\n") == 1 and "403 error 1005" in out and "verify" in out


def _scripted(monkeypatch, *script, key=None):
    op = FakeOpener(*script)
    monkeypatch.setattr(
        cli, "Client", lambda api_key=None: Client(api_key=key, sleep=noop, opener=op)
    )
    monkeypatch.setattr(cli, "api_key", lambda: key)
    monkeypatch.setattr(cli, "_load_roster_snapshot", snapshot)
    return op


def test_ticker_card_names_both_leg_sources_and_the_definition(monkeypatch, capsys, tmp_path):
    _scripted(monkeypatch, (200, envelope([MS_MAP_ROW])), (200, envelope(MS_INFO)))
    rc, out = run(["MS", "--json", str(tmp_path / "ms.json")], capsys)
    assert rc == 0
    assert "roster: snapshot 2026-09-18" in out
    assert "/public-api/v1/cryptocurrency/map, live, keyless, 0 credits" in out
    assert "listed, no CMC-tracked market" in out and "methodology requirements" in out
    assert "listed 2026-08-11 (date_added)" in out
    assert "0 of 1 wrapper(s) with a CMC-tracked market" in out
    assert "never traded" not in out
    assert json.loads((tmp_path / "ms.json").read_text())["verdict"].startswith("0 of 1")


def test_pool_exhaustion_answers_from_the_snapshot_and_exits_75(monkeypatch, capsys):
    throttle = (429, envelope(None, error_code=1022, error_message="limit"))
    _scripted(monkeypatch, throttle, throttle, throttle, throttle, (200, envelope(MS_INFO)))
    rc, out = run(["MS"], capsys)
    assert rc == EX_TEMPFAIL
    assert "UNTRACKED" in out and "snapshot 2026-09-18 — HTTP 429" in out
    assert "anonymous pool is exhausted" in out


def test_verify_passes_on_the_committed_census(capsys):
    rc, out = run(["verify"], capsys)
    assert rc == 0 and "counts == recount from rows" in out and "jq '" in out


def test_verify_fails_on_a_drifted_count(tmp_path, capsys):
    doc = json.loads((ROOT / "data" / "census.json").read_text())
    doc["counts"]["untracked"] += 1
    p = tmp_path / "census.json"
    p.write_text(json.dumps(doc))
    rc, out = run(["verify", "--census", str(p)], capsys)
    assert rc == 1 and "DRIFT: counts.untracked" in out


def test_compact_snapshot_keeps_what_the_diff_needs_and_drops_the_rest():
    doc = {
        "generated_utc": "x",
        "counts": {},
        "issuers_registry": [1],
        "wrappers": [{"crypto_id": 1, "status": "active", "name": "long", "platform": {}}],
    }
    c = cli.compact(doc)
    assert "issuers_registry" not in c and c["wrappers"][0] == {
        "crypto_id": 1,
        "symbol": None,
        "underlying": None,
        "rwa_id": None,
        "issuer_name": None,
        "status": "active",
        "price": None,
        "market_cap": None,
    }


def test_delta_with_one_snapshot_says_so(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "SNAPSHOTS", tmp_path)
    (tmp_path / "2026-09-18.json").write_text("{}")
    rc, out = run(["delta"], capsys)
    assert rc == 1 and "needs two snapshots" in out


def test_delta_between_two_snapshots_writes_delta_json(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "SNAPSHOTS", tmp_path / "snapshots")
    monkeypatch.setattr(cli, "DATA", tmp_path)
    (tmp_path / "snapshots").mkdir()
    for day, st in (("2026-09-18", "untracked"), ("2026-09-19", "active")):
        (tmp_path / "snapshots" / f"{day}.json").write_text(
            json.dumps(
                {
                    "generated_utc": day,
                    "counts": {"wrappers": 1, "active": 0, "untracked": 1},
                    "wrappers": [
                        {
                            "crypto_id": 41513,
                            "symbol": "wMSx",
                            "underlying": "MS",
                            "issuer_name": "Backed",
                            "status": st,
                        }
                    ],
                }
            )
        )
    rc, out = run(["delta"], capsys)
    assert rc == 0 and "+1 newly tracked" in out and "wMSx" in out
    assert json.loads((tmp_path / "delta.json").read_text())["newly_tracked"] == 1


def test_census_command_writes_every_artifact_from_a_scripted_run(monkeypatch, tmp_path):
    """The whole keyed path, scripted end to end: census.json, the roster snapshot, the
    receipt, today's snapshot. Nothing on the judged path reads a fixture — this one feeds
    the client canned responses in place of the network."""
    rwa = {
        "rwa_assets": [
            {
                "rwa_id": 35,
                "symbol": "MS",
                "name": "Morgan Stanley",
                "asset_type": "stock",
                "rwa_rank": 43,
                "has_tokens": True,
            },
            {
                "rwa_id": 999,
                "symbol": "XYZ",
                "name": "U",
                "asset_type": "stock",
                "rwa_rank": 999,
                "has_tokens": False,
            },
        ],
        "has_more": False,
    }
    quotes = {
        "rwa_assets": [
            {
                "rwa_id": 35,
                "symbol": "MS",
                "name": "Morgan Stanley",
                "asset_type": "stock",
                "rwa_rank": 43,
                "has_tokens": True,
                "tokens": [
                    {
                        "crypto_id": 41513,
                        "symbol": "wMSx",
                        "name": "W",
                        "issuer_id": "b",
                        "issuer_name": "Backed Assets",
                        "price": None,
                        "market_cap": None,
                        "volume_24h": None,
                    }
                ],
            }
        ]
    }
    usage = {"usage": {"current_month": {"credits_used": 1}}}
    op = FakeOpener(
        (200, envelope(usage, credit_count=0)),  # key/info before
        (200, envelope(rwa, credit_count=0)),  # rwa/map
        (200, envelope(quotes, credit_count=1)),  # rwa/quotes
        (
            200,
            envelope(
                {"issuers": [{"issuer_id": "b", "name": "Backed Assets", "num_tokens": 1176}]},
                credit_count=1,
            ),
        ),
        (200, envelope([MS_MAP_ROW])),  # cmc/map page 1 (short)
        (200, envelope(MS_INFO)),  # cmc/info
        (200, envelope(usage, credit_count=0)),  # key/info after
    )
    monkeypatch.setattr(
        cli, "Client", lambda api_key=None: Client(api_key="k", sleep=noop, opener=op)
    )
    monkeypatch.setattr(cli, "api_key", lambda: "k")
    monkeypatch.setattr(cli, "DATA", tmp_path)
    monkeypatch.setattr(cli, "SNAPSHOTS", tmp_path / "snapshots")
    out = io.StringIO()
    rc = cli.cmd_census(
        ["--out", str(tmp_path / "census.json"), "--receipt", str(tmp_path / "live_run.json")],
        out=out,
    )
    assert rc == 0, out.getvalue()
    doc = json.loads((tmp_path / "census.json").read_text())
    assert doc["counts"]["underlyings_zero_tracked"] == 1 and doc["credits_used"] == 2
    assert doc["hero"]["symbol"] == "MS"
    roster = json.loads((tmp_path / "roster_snapshot.json").read_text())
    assert "MS" in roster["underlyings"] and "XYZ" in roster["no_tokens"]
    receipt = json.loads((tmp_path / "live_run.json").read_text())
    assert (
        len(receipt["receipt"]) == 7
        and receipt["key_usage"]["after"]["current_month"]["credits_used"] == 1
    )
    assert list((tmp_path / "snapshots").glob("*.json"))
    assert "1 of 1" not in out.getvalue() and "MS rwa_rank 43" in out.getvalue()
    assert not Path(str(tmp_path / "census.json")).read_text().count("_rwa_rows")


def test_census_repeats_a_refused_keyless_map_paging_keyed_and_says_so(monkeypatch, tmp_path):
    """2026-09-19T00:00Z: the day-2 snapshot's keyless map paging was refused (429 error 1022 —
    this IP had paged the map several times that day). With the key already required for the
    census, the identical paging on the keyed base is the honest continuation; the receipt marks
    those calls keyed."""
    rwa = {
        "rwa_assets": [
            {
                "rwa_id": 35,
                "symbol": "MS",
                "name": "Morgan Stanley",
                "asset_type": "stock",
                "rwa_rank": 43,
                "has_tokens": True,
            }
        ],
        "has_more": False,
    }
    quotes = {
        "rwa_assets": [
            {
                "rwa_id": 35,
                "symbol": "MS",
                "name": "Morgan Stanley",
                "asset_type": "stock",
                "rwa_rank": 43,
                "has_tokens": True,
                "tokens": [
                    {
                        "crypto_id": 41513,
                        "symbol": "wMSx",
                        "name": "W",
                        "issuer_id": "b",
                        "issuer_name": "Backed Assets",
                        "price": None,
                        "market_cap": None,
                        "volume_24h": None,
                    }
                ],
            }
        ]
    }
    usage = {"usage": {"current_month": {"credits_used": 1}}}
    refused = (429, envelope(None, error_code=1022, error_message="limit for anonymous access"))
    op = FakeOpener(
        (200, envelope(usage, credit_count=0)),
        (200, envelope(rwa, credit_count=0)),
        (200, envelope(quotes, credit_count=1)),
        (200, envelope({"issuers": []}, credit_count=1)),
        refused,
        refused,
        refused,
        refused,  # keyless map page 1, exhausted
        (200, envelope([MS_MAP_ROW], credit_count=0)),  # the same page, keyed
        (200, envelope(MS_INFO, credit_count=1)),  # info, keyed from the start
        (200, envelope(usage, credit_count=0)),
    )
    monkeypatch.setattr(
        cli, "Client", lambda api_key=None: Client(api_key="k", sleep=noop, opener=op)
    )
    monkeypatch.setattr(cli, "api_key", lambda: "k")
    monkeypatch.setattr(cli, "DATA", tmp_path)
    monkeypatch.setattr(cli, "SNAPSHOTS", tmp_path / "snapshots")
    out = io.StringIO()
    rc = cli.cmd_census(
        ["--out", str(tmp_path / "census.json"), "--receipt", str(tmp_path / "live_run.json")],
        out=out,
    )
    assert rc == 0, out.getvalue()
    assert "keyless pool refused this IP" in out.getvalue()
    doc = json.loads((tmp_path / "census.json").read_text())
    map_calls = [m for m in doc["receipt"] if m["call"].startswith("cmc/map")]
    assert [m["keyed"] for m in map_calls] == [False, True]
    assert doc["counts"]["untracked"] == 1 and doc["credits_used"] == 3


# ── the branches the scripted census runs above do not take ───────────────────

_RWA = {
    "rwa_assets": [
        {
            "rwa_id": 35,
            "symbol": "MS",
            "name": "Morgan Stanley",
            "asset_type": "stock",
            "rwa_rank": 43,
            "has_tokens": True,
        }
    ],
    "has_more": False,
}
_QUOTES = {
    "rwa_assets": [
        {
            "rwa_id": 35,
            "symbol": "MS",
            "name": "Morgan Stanley",
            "asset_type": "stock",
            "rwa_rank": 43,
            "has_tokens": True,
            "tokens": [
                {
                    "crypto_id": 41513,
                    "symbol": "wMSx",
                    "name": "W",
                    "issuer_id": "b",
                    "issuer_name": "Backed Assets",
                    "price": None,
                    "market_cap": None,
                    "volume_24h": None,
                }
            ],
        }
    ]
}
_USAGE = {"usage": {"current_month": {"credits_used": 1}}}
_REFUSED = (429, envelope(None, error_code=1022, error_message="limit for anonymous access"))


def _keyed_census(monkeypatch, tmp_path, *script):
    op = FakeOpener(
        (200, envelope(_USAGE, credit_count=0)),
        (200, envelope(_RWA, credit_count=0)),
        (200, envelope(_QUOTES, credit_count=1)),
        (200, envelope({"issuers": []}, credit_count=1)),
        *script,
    )
    monkeypatch.setattr(
        cli, "Client", lambda api_key=None: Client(api_key="k", sleep=noop, opener=op)
    )
    monkeypatch.setattr(cli, "api_key", lambda: "k")
    monkeypatch.setattr(cli, "DATA", tmp_path)
    monkeypatch.setattr(cli, "SNAPSHOTS", tmp_path / "snapshots")
    out = io.StringIO()
    rc = cli.cmd_census(
        ["--out", str(tmp_path / "census.json"), "--receipt", str(tmp_path / "live_run.json")],
        out=out,
    )
    return rc, out.getvalue(), op


def test_census_asks_by_symbol_for_ids_the_paged_map_omitted_and_retries_that_keyed(
    monkeypatch, tmp_path
):
    """VVV 40784, 2026-09-18: the paged map omits rows the symbol filter returns. The census
    asks again by symbol for whatever did not resolve; if the pool refuses that call it is
    repeated keyed, so 'unresolved' means CMC has no row, not that we paged past one."""
    rc, out, op = _keyed_census(
        monkeypatch,
        tmp_path,
        (200, envelope([])),  # the paged map: empty
        _REFUSED,
        _REFUSED,
        _REFUSED,
        _REFUSED,  # by symbol, keyless: exhausted
        (200, envelope([MS_MAP_ROW], credit_count=1)),  # by symbol, keyed
        (200, envelope(MS_INFO, credit_count=1)),  # info, keyed now
        (200, envelope(_USAGE, credit_count=0)),
    )
    assert rc == 0, out
    assert "+1 resolved by symbol that the paged map omitted" in out
    doc = json.loads((tmp_path / "census.json").read_text())
    assert doc["counts"]["untracked"] == 1 and doc["wrappers"][0]["status"] == "untracked"
    by_symbol = [m for m in doc["receipt"] if "symbol=" in m["call"]]
    assert [m["keyed"] for m in by_symbol] == [False, True]


def test_census_repeats_a_refused_keyless_info_leg_keyed_and_says_so(monkeypatch, tmp_path):
    rc, out, op = _keyed_census(
        monkeypatch,
        tmp_path,
        (200, envelope([MS_MAP_ROW])),  # the paged map, keyless
        _REFUSED,
        _REFUSED,
        _REFUSED,
        _REFUSED,  # info, keyless: exhausted
        (200, envelope(MS_INFO, credit_count=1)),  # info, keyed
        (200, envelope(_USAGE, credit_count=0)),
    )
    assert rc == 0, out
    assert "keyless pool refused this IP — the identical calls, keyed" in out
    doc = json.loads((tmp_path / "census.json").read_text())
    info_calls = [m for m in doc["receipt"] if m["call"].startswith("cmc/info")]
    assert [m["keyed"] for m in info_calls] == [False, True]
    assert doc["wrappers"][0]["date_added"].startswith("2026-08-11")


def test_a_census_the_key_cannot_afford_exits_1_and_a_transient_one_exits_75(monkeypatch, tmp_path):
    rc, out, _ = _keyed_census(
        monkeypatch,
        tmp_path,
        (400, envelope(None, error_code=400, error_message="bad request")),  # map, permanent
    )
    assert rc == 1 and "census failed:" in out and "error_code 400" in out
    assert not (tmp_path / "census.json").exists()

    monkeypatch.setattr(
        cli, "run_census", lambda client, out=None: (_ for _ in ()).throw(RuntimeError("transient"))
    )
    rc = cli.cmd_census(["--out", str(tmp_path / "c.json")], out=io.StringIO())
    assert rc == EX_TEMPFAIL

    monkeypatch.setattr(
        cli, "run_census", lambda client, out=None: (_ for _ in ()).throw(NoKey("needs a key"))
    )
    out = io.StringIO()
    rc = cli.cmd_census(["--out", str(tmp_path / "c.json")], out=out)
    assert rc == 1 and out.getvalue().rstrip().endswith("needs a key")


def test_print_census_lists_the_issuers_with_five_or_more_wrappers(committed_census):
    out = io.StringIO()
    cli.print_census(committed_census, out=out)
    text = out.getvalue()
    assert (
        "issuer                        declared attached tracked  shelf   live market cap" in text
    )
    assert any(
        e["issuer_name"] in text for e in committed_census["by_issuer"] if e["attached"] >= 5
    )


def test_the_roster_snapshot_is_read_from_the_env_path_or_is_none(monkeypatch, tmp_path):
    p = tmp_path / "snap.json"
    p.write_text(json.dumps({"underlyings": {}, "no_tokens": []}))
    monkeypatch.setenv("SHELFWARE_SNAPSHOT", str(p))
    assert cli._load_roster_snapshot() == {"underlyings": {}, "no_tokens": []}
    monkeypatch.setenv("SHELFWARE_SNAPSHOT", str(tmp_path / "missing.json"))
    assert cli._load_roster_snapshot() is None


def test_the_card_names_the_info_leg_and_the_snapshot_behind_a_dotted_symbol(monkeypatch, capsys):
    """NVDA has NVDAX (map, active) and NVDA.D (info says inactive; the snapshot's finer state
    is untracked). Both sources are printed on their rows."""
    _scripted(
        monkeypatch,
        (
            200,
            envelope(
                [
                    {
                        "id": 36992,
                        "symbol": "NVDAX",
                        "status": "active",
                        "first_historical_data": "2025-06-28T20:05:00.000Z",
                        "platform": {"name": "Solana", "token_address": "Xsc9"},
                    }
                ]
            ),
        ),
        (
            200,
            envelope(
                {
                    "28616": {
                        "id": 28616,
                        "status": "inactive",
                        "date_added": "2023-12-07T10:41:41.000Z",
                    },
                    "36992": {"id": 36992, "status": "active"},
                }
            ),
        ),
    )
    rc, out = run(["NVDA"], capsys)
    assert rc == 0
    assert "tracked since 2025-06-28" in out
    assert "/public-api/v2/cryptocurrency/info says inactive, live, keyless" in out
    assert 'its symbol filter rejects "NVDA.D"' in out
    assert "1 of 2 wrapper(s) with a CMC-tracked market" in out


def test_the_card_names_the_info_leg_alone_and_an_unresolved_wrapper(monkeypatch, capsys):
    from test_lookup import snapshot as base

    def only_dotted():
        snap = base()
        snap["underlyings"]["NVDA"]["tokens"] = [
            t for t in snap["underlyings"]["NVDA"]["tokens"] if t["symbol"] == "NVDA.D"
        ]
        return snap

    _scripted(monkeypatch, (200, envelope({"28616": {"id": 28616, "status": "active"}})))
    monkeypatch.setattr(cli, "_load_roster_snapshot", only_dotted)
    rc, out = run(["NVDA"], capsys)
    assert rc == 0 and "the map's symbol filter rejects this symbol" in out

    _scripted(monkeypatch, (200, envelope({})))
    monkeypatch.setattr(cli, "_load_roster_snapshot", only_dotted)
    rc, out = run(["NVDA"], capsys)
    assert rc == 0 and "in tokens[] but not in the map — not counted as shelf" in out


def test_verify_live_compares_ten_statuses_and_exits_on_what_it_finds(monkeypatch, capsys):
    calls = {}

    def fake_live(doc, client, n=10, seed=None):
        calls["client"] = client
        return calls["result"]

    monkeypatch.setattr(cli, "live_check", fake_live)
    calls["result"] = (True, ["  PAXG  4705  committed active  live active  ="], {})
    rc, out = run(["verify", "--live", "--seed", "1"], capsys)
    assert rc == 0 and "live — 10 statuses re-fetched keyless" in out and "PAXG" in out
    assert calls["client"].api_key is None

    calls["result"] = (False, ["  x ≠ (the market moved)"], {})
    rc, out = run(["verify", "--live"], capsys)
    assert rc == 0 and "a status moved since the census was cut" in out

    calls["result"] = (None, ["live check could not run: HTTP 429"], {"throttled": True})
    rc, out = run(["verify", "--live"], capsys)
    assert rc == EX_TEMPFAIL and "could not run" in out

    calls["result"] = (None, ["live check could not run: HTTP 400"], {"throttled": False})
    rc, out = run(["verify", "--live"], capsys)
    assert rc == 1


def test_the_module_runs_as_a_script(monkeypatch, capsys):
    import runpy

    monkeypatch.setattr("sys.argv", ["shelfware", "--version"])
    with __import__("pytest").raises(SystemExit) as e:
        runpy.run_path(cli.__file__, run_name="__main__")
    assert e.value.code == 0 and capsys.readouterr().out.startswith("shelfware ")


def test_python_dash_m_shelfware_is_the_same_door(monkeypatch, capsys):
    """shelfware/__main__.py is the three lines behind `python3 -m shelfware`."""
    import runpy
    from pathlib import Path

    monkeypatch.setattr("sys.argv", ["shelfware", "--version"])
    with __import__("pytest").raises(SystemExit) as e:
        runpy.run_path(str(Path(cli.__file__).with_name("__main__.py")), run_name="__main__")
    assert e.value.code == 0 and capsys.readouterr().out.startswith("shelfware ")


def test_the_card_prints_a_shelf_wrapper_without_a_listing_date_and_an_inactive_one(
    monkeypatch, capsys
):
    from test_lookup import snapshot as base

    def two_wrappers():
        snap = base()
        snap["underlyings"]["MS"]["tokens"].append(
            {**snap["underlyings"]["MS"]["tokens"][0], "crypto_id": 99, "symbol": "wMSy"}
        )
        return snap

    _scripted(
        monkeypatch,
        (
            200,
            envelope(
                [
                    {"id": 41513, "symbol": "wMSx", "status": "untracked"},
                    {"id": 99, "symbol": "wMSy", "status": "inactive"},
                ]
            ),
        ),
        (200, envelope({})),  # info: no date_added for either
    )
    monkeypatch.setattr(cli, "_load_roster_snapshot", two_wrappers)
    rc, out = run(["MS"], capsys)
    assert rc == 0
    assert "status   UNTRACKED" in out and "date_added" not in out
    assert "status   INACTIVE" in out and "tracked since" not in out


def test_an_underlying_with_no_wrappers_prints_a_card_without_a_receipt(monkeypatch, capsys):
    from test_lookup import snapshot as base

    def none_listed():
        snap = base()
        snap["underlyings"]["MS"]["tokens"] = []
        snap["underlyings"]["MS"]["has_tokens"] = False
        return snap

    _scripted(monkeypatch)
    monkeypatch.setattr(cli, "_load_roster_snapshot", none_listed)
    rc, out = run(["MS"], capsys)
    assert rc == 0 and "receipt:" not in out
    assert "has_tokens: false — 0 wrappers listed" in out


def test_census_resolves_the_rows_the_paged_map_omitted_by_symbol_keyless(monkeypatch, tmp_path):
    rc, out, op = _keyed_census(
        monkeypatch,
        tmp_path,
        (200, envelope([])),  # the paged map: empty
        (200, envelope([MS_MAP_ROW])),  # by symbol, keyless, answered
        (200, envelope(MS_INFO)),
        (200, envelope(_USAGE, credit_count=0)),
    )
    assert rc == 0, out
    assert "+1 resolved by symbol that the paged map omitted" in out
    doc = json.loads((tmp_path / "census.json").read_text())
    by_symbol = [m for m in doc["receipt"] if "symbol=" in m["call"]]
    assert [m["keyed"] for m in by_symbol] == [False]


def test_print_census_without_a_hero_skips_the_hero_line(committed_census):
    doc = dict(committed_census)
    doc["hero"] = None
    out = io.StringIO()
    cli.print_census(doc, out=out)
    assert "hero by rule" not in out.getvalue()
