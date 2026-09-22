"""The render's other branches, offline: a ticker outside the RWA map, a wrapper with a tracked
market, every state source, a missing proof file, unfilled slots on the judge page and the
deck, and the write path that --check later confirms."""

import json
import runpy
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import render_site  # noqa: E402

ASKED = "2026-09-18T22:43:39Z"
QUOTES = "https://pro-api.coinmarketcap.com/v5/real-world-assets/quotes/latest?id=1"


@pytest.fixture
def doc():
    return {
        "counts": {"underlyings_zero_tracked": 476, "has_tokens": 791},
        "hero": {"symbol": "MS", "rule": "highest rwa_rank on the shelf"},
    }


@pytest.fixture
def unmapped_res():
    return {
        "ticker": "ZZZ",
        "asked_utc": ASKED,
        "roster": {"source": "snapshot", "as_of": "2026-09-18T22:16:17Z", "call": None},
        "status": {"source": "committed snapshot", "call": None},
        "underlyings": [],
        "wrappers": [],
        "verdict": "ZZZ is not in the RWA map",
        "evidence": {"tokens": [{"crypto_id": 7}], "map_rows": [], "info_rows": []},
        "calls": [{"call": "cmc/key/info", "http": 200, "keyed": False}],
        "committed": False,
    }


@pytest.fixture
def lit_res():
    return {
        "ticker": "NVDA",
        "asked_utc": ASKED,
        "roster": {"source": "live", "as_of": "2026-09-18T22:16:17Z", "call": {"url": QUOTES}},
        "status": {"source": "live keyless", "call": None},
        "underlyings": [
            {
                "rwa_id": 2,
                "symbol": "NVDA",
                "name": "Nvidia",
                "asset_type": "stock",
                "rwa_rank": 2,
                "has_tokens": True,
            }
        ],
        "wrappers": [
            {
                "crypto_id": 1,
                "symbol": "NVDAx",
                "name": "Nvidia xStock",
                "issuer_name": "Backed Assets",
                "price": 181.25,
                "status": "active",
                "status_source": "info",
                "platform": {"name": "Solana", "token_address": "Xsc9"},
                "date_added": "2025-06-30T00:00:00.000Z",
            },
            {
                "crypto_id": 2,
                "symbol": "NVDA.d",
                "name": "Dinari NVDA",
                "issuer_name": "Dinari Assets",
                "price": None,
                "status": "inactive",
                "status_source": "info+snapshot",
                "platform": {},
            },
            {
                "crypto_id": 3,
                "symbol": "bNVDA",
                "name": "bStock NVDA",
                "issuer_name": None,
                "price": None,
                "status": None,
                "platform": None,
            },
        ],
        "verdict": "1 of 3 wrapper(s) with a CMC-tracked market",
        "evidence": {
            "tokens": [{"crypto_id": 1, "symbol": "NVDAx", "price": 181.25}, {"crypto_id": 3}],
            "map_rows": [{"id": 1, "symbol": "NVDAx", "status": "active", "rank": 900}],
            "info_rows": {"1": {"id": 1, "symbol": "NVDAx", "status": "active"}},
        },
        "calls": [
            {
                "call": "rwa/quotes id=2",
                "url": QUOTES,
                "http": 200,
                "keyed": True,
                "credit_count": 1,
                "elapsed_ms": 300,
                "sha256": "abc123",
                "fetched_utc": ASKED,
            }
        ],
        "committed": False,
    }


def test_a_wrapper_kind_is_lit_when_active_and_unknown_when_neither_active_nor_untracked():
    assert render_site.wrapper_kind({"status": "active"}) == "lit"
    assert render_site.wrapper_kind({"status": "untracked"}) == "shelf"
    assert render_site.wrapper_kind({"status": "inactive"}) == "unknown"


def test_the_state_source_names_the_endpoint_that_answered_or_the_snapshot():
    assert "/v1/cryptocurrency/map" in render_site.state_from({"status_source": "map"}, "x")
    assert "rejects this symbol" in render_site.state_from({"status_source": "info"}, "x")
    assert "2026-09-18 snapshot" in render_site.state_from(
        {"status_source": "info+snapshot"}, "2026-09-18"
    )
    assert render_site.state_from({}, "2026-09-18") == "committed snapshot 2026-09-18"


def test_a_ticker_outside_the_rwa_map_renders_the_verdict_in_every_slot(doc, unmapped_res):
    ctx = render_site.answer_ctx(unmapped_res, doc)
    assert "not in CoinMarketCap's RWA map" in ctx["context"]
    assert ctx["hero_kind"] == "none" and ctx["hero_share_text"] == "0 of 0"
    assert ctx["hero_claim"] == "<em>ZZZ</em> is not in CoinMarketCap's RWA map."
    assert 'colspan="8">ZZZ is not in the RWA map' in ctx["table_rows"]
    assert ctx["route_kind"] == "none" and ctx["route_line"] == "▶ ZZZ is not in the RWA map"
    assert ctx["rows_arith"] == "<li>ZZZ is not in the RWA map</li>"
    assert ctx["rows_table"].count("<tr>") == 2 and "map row" not in ctx["rows_table"]
    assert "/public-api/v1/cryptocurrency/map" in ctx["receipt"]
    assert 'first request</div><div class="v">—' in ctx["receipt"]
    assert ctx["hero_rank"] == "—" and ctx["calls_n"] == 1


def test_an_underlying_with_no_wrapper_says_none_are_listed(doc, unmapped_res):
    unmapped_res["underlyings"] = [{"rwa_id": 9, "symbol": "ZZZ", "rwa_rank": 9}]
    ctx = render_site.answer_ctx(unmapped_res, doc)
    assert ctx["hero_claim"] == "wrappers listed for <em>ZZZ</em>."
    assert "rwa_id 9 · crypto_id —" in ctx["rows_cap"]


def test_a_tracked_wrapper_makes_the_answer_lit_with_its_active_count(doc, lit_res):
    ctx = render_site.answer_ctx(lit_res, doc)
    assert ctx["hero_kind"] == "lit" and ctx["hero_share_text"] == "1 of 3"
    assert "chosen by rule" not in ctx["context"] and "live via /api/roster" in ctx["context"]
    assert "<b>1</b> active · <b>0</b> untracked · 2 unresolved" in ctx["hero_support"]
    assert "issuers: (no issuer), Backed Assets, Dinari Assets" in ctx["hero_support"]
    assert ctx["route_kind"] == "lit" and "NVDA is not one of the 476 of 791" in ctx["route_rule"]
    assert "181.2500" in ctx["table_rows"] and "state unresolved" in ctx["table_rows"]
    assert ctx["table_rows"].count("<tr") == 3
    assert ctx["rows_table"].count("map row") == 1 and ctx["rows_table"].count("info row") == 1
    assert "rank 900" in ctx["rows_table"] and 'class="lit"' in ctx["rows_table"]
    assert "(live)" in ctx["rows_cap"] and "docs/proof/ms.json" not in ctx["rows_cap"]
    assert "NVDA has a wrapper with a CMC-tracked market" in ctx["rows_arith"]
    assert "keyed roster leg" in ctx["receipt"] and "1 keyed" in ctx["receipt"]
    assert f'href="{QUOTES}"' in ctx["receipt"] and "abc123" in ctx["receipt"]
    assert ctx["hero_rank"] == 2


def test_the_api_table_counts_hero_calls_by_path_and_skips_one_without_a_url():
    receipt = [{"url": "https://pro-api.coinmarketcap.com/v1/key/info?x=1"}]
    hero_calls = [{"url": None}, {"url": QUOTES}]
    rows = render_site.api_rows(receipt, hero_calls)
    assert "<code>/v1/key/info</code></td><td>" in rows
    assert rows.count('<td class="n">1</td>') == 2
    assert "0 — refused" in rows


def test_the_hero_run_is_absent_when_the_proof_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(render_site, "PROOF", tmp_path)
    assert render_site.hero_run() is None
    # the delta sentence is derived the same way: absent file, a real zero, a named flip
    monkeypatch.setattr(render_site, "DATA", tmp_path)
    assert render_site.delta_sentence_html() == "no delta yet"
    zero = dict(newly_tracked=0, newly_shelved=0, new_wrappers=0, gone_wrappers=0, flips=[])
    (tmp_path / "delta.json").write_text(json.dumps(zero))
    assert "a real zero, printed as one" in render_site.delta_sentence_html()
    flip = dict(
        zero, newly_shelved=1, flips=[dict(symbol="MXL", before="active", after="untracked")]
    )
    (tmp_path / "delta.json").write_text(json.dumps(flip))
    assert "+1 newly shelved" in render_site.delta_sentence_html()
    assert "(shelved: MXL active → untracked)" in render_site.delta_sentence_html()
    other = dict(zero, other_flips=1, flips=[dict(symbol="X", before="unresolved", after="active")])
    (tmp_path / "delta.json").write_text(json.dumps(other))
    assert "1 other flip (other: X unresolved → active)" in render_site.delta_sentence_html()
    assert "real zero" not in render_site.delta_sentence_html()
    # a mixed day names each flip under the count it feeds; a plural count pluralises
    mixed = dict(
        zero,
        newly_tracked=1,
        newly_shelved=1,
        other_flips=2,
        flips=[
            dict(symbol="MXL", before="active", after="untracked"),
            dict(symbol="X", before="unresolved", after="active"),
            dict(symbol="Y", before="active", after="inactive"),
            dict(symbol="Z", before="untracked", after="active"),
        ],
    )
    (tmp_path / "delta.json").write_text(json.dumps(mixed))
    s = render_site.delta_sentence_html()
    assert "2 other flips" in s
    assert (
        "(tracked: Z untracked → active · shelved: MXL active → untracked · other: X unresolved → active, Y active → inactive)"
        in s
    )
    # more than six of one kind: the first six in full, the rest counted, never dropped silently
    many = dict(
        zero,
        newly_shelved=8,
        flips=[dict(symbol=f"S{i}", before="active", after="untracked") for i in range(8)],
    )
    (tmp_path / "delta.json").write_text(json.dumps(many))
    s = render_site.delta_sentence_html()
    assert "S5 active → untracked, +2 more)" in s and "S6" not in s


def test_an_unfilled_slot_fails_the_judge_page(tmp_path, monkeypatch):
    (tmp_path / "judge.html").write_text("{{body}} {{nope}}")
    monkeypatch.setattr(render_site, "TEMPLATES", tmp_path)
    with pytest.raises(SystemExit, match="unfilled slots on the judge page"):
        render_site.render_judge()


def test_an_unfilled_slot_fails_the_deck(tmp_path, monkeypatch):
    (tmp_path / "pitch.html").write_text("{{share_pct}} {{nope}}")
    monkeypatch.setattr(render_site, "TEMPLATES", tmp_path)
    with pytest.raises(SystemExit, match="unfilled slots on the deck"):
        render_site.render_pitch()


def test_the_write_path_produces_the_files_the_check_path_then_accepts(
    tmp_path, monkeypatch, capsys
):
    site = tmp_path / "site"
    monkeypatch.setattr(render_site, "SITE", site)
    monkeypatch.setattr(render_site, "HEALTH_OUT", tmp_path / "data" / "health.json")
    monkeypatch.setattr(render_site, "JUDGE_OUT", site / "judge" / "index.html")
    monkeypatch.setattr(render_site, "PITCH_OUT", site / "pitch" / "index.html")
    monkeypatch.setattr(sys, "argv", ["render_site.py"])
    assert render_site.main() == 0
    assert capsys.readouterr().out.count("wrote ") == 4
    assert (site / "index.html").exists() and (site / "pitch" / "index.html").exists()
    monkeypatch.setattr(sys, "argv", ["render_site.py", "--check"])
    assert render_site.main() == 0
    assert "match the census" in capsys.readouterr().out


def test_the_script_entry_point_exits_with_the_check_result(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["render_site.py", "--check"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(ROOT / "scripts" / "render_site.py"), run_name="__main__")
    assert e.value.code == 0
