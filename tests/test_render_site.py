"""The page is generated output: every number on it comes from the census, the drift gate can
fail, and no slot can survive unfilled."""

import json
import re
import subprocess
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import render_site  # noqa: E402


def test_the_page_states_the_pair_the_rows_produce(committed_census):
    html = (ROOT / "site" / "index.html").read_text()
    c = committed_census["counts"]
    assert re.search(rf'id="zt">{c["underlyings_zero_tracked"]}<', html)
    assert f">{c['has_tokens']}</b> underlyings" in html
    assert committed_census["generated_utc"] in html
    assert "listed, no CMC-tracked market" in html and "never traded" not in html.replace(
        "does not mean never traded", ""
    )


def test_the_page_names_every_endpoint_and_the_definition(committed_census):
    html = (ROOT / "site" / "index.html").read_text()
    for ep in (
        "/v5/real-world-assets/map",
        "/v5/real-world-assets/quotes/latest",
        "/v5/real-world-assets/issuers/list",
        "/public-api/v1/cryptocurrency/map",
        "/public-api/v2/cryptocurrency/info",
        "/v1/key/info",
    ):
        assert ep in html, ep
    assert committed_census["untracked_definition"] in html


def test_rendered_output_matches_disk_and_the_drift_gate_can_fail(tmp_path, monkeypatch):
    html, health = render_site.render()
    assert html == (ROOT / "site" / "index.html").read_text()
    assert (
        json.loads(health)["counts"]["underlyings_zero_tracked"]
        == json.loads((ROOT / "data" / "health.json").read_text())["counts"][
            "underlyings_zero_tracked"
        ]
    )
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(html.replace('id="zt">', 'id="zt">9'))
    (tmp_path / "health.json").write_text(health)
    monkeypatch.setattr(render_site, "SITE", site)
    monkeypatch.setattr(render_site, "HEALTH_OUT", tmp_path / "health.json")
    monkeypatch.setattr(sys, "argv", ["render_site.py", "--check"])
    assert render_site.main() == 1


def test_an_unfilled_slot_fails_the_render(monkeypatch, tmp_path):
    tpl = tmp_path / "index.html"
    tpl.write_text("{{share_pct}} {{not_a_slot}}")
    (tmp_path / "app.js").write_text("")
    monkeypatch.setattr(render_site, "TEMPLATES", tmp_path)
    with pytest.raises(SystemExit, match="unfilled slots"):
        render_site.render()


def test_the_hero_card_is_the_committed_keyless_run():
    h = render_site.hero_run()
    assert (
        h["ticker"] == "MS"
        and h["roster"]["source"] == "snapshot"
        and h["status"]["source"] == "live keyless"
    )
    assert any(c["call"].startswith("cmc/map") and not c["keyed"] for c in h["calls"])


def test_issuer_row_carries_the_registry_row_as_evidence(committed_census):
    e = next(x for x in committed_census["by_issuer"] if x["issuer_name"] == "Backed Assets")
    row = render_site.issuer_row(e, committed_census["issuers_registry"])
    assert (
        "<details>" in row and "&quot;num_tokens&quot;: 1176" in row and 'class="rate">82%' in row
    )


def test_bar_widths_sum_to_the_row():
    html = render_site.bar(1, 3, 0, label="x")
    widths = [float(w) for w in re.findall(r"width:([\d.]+)%", html)]
    assert widths == [75.0, 25.0, 0.0]
    assert 'aria-label="x"' in html


def test_render_script_check_passes_from_the_command_line():
    r = subprocess.run(
        [sys.executable, "scripts/render_site.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
