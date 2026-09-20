"""The deck at /pitch/ is generated output like the page: every number a slot from the census,
the receipt and the benchmark; the same drift gate; the same wording guard; a version stamp
that is the tree's one version, not a typed one; and a page the landing links to on both hosts."""

import json
import re
import subprocess
import sys

import pytest
from conftest import ROOT

import shelfware

sys.path.insert(0, str(ROOT / "scripts"))
import bump_version  # noqa: E402
import render_site  # noqa: E402

DECK = ROOT / "site" / "pitch" / "index.html"


def test_the_committed_deck_is_what_the_census_renders():
    assert DECK.read_text() == render_site.render_pitch()


def test_the_deck_states_the_pair_the_rows_produce_and_never_overclaims(committed_census):
    html = DECK.read_text()
    c = committed_census["counts"]
    share = round(100 * c["underlyings_zero_tracked"] / c["has_tokens"])
    assert f">{share}%<" in html
    assert f"{c['underlyings_zero_tracked']}<small> / {c['has_tokens']}</small>" in html
    assert str(c["untracked"]) in html and committed_census["generated_utc"] in html
    assert "no CMC-tracked market" in html
    assert "never traded" not in html.replace("not that nothing ever traded", "")
    assert "$0 traded ever" not in html


def test_twelve_slides_each_with_speaker_notes_and_no_unfilled_slot_or_placeholder():
    html = DECK.read_text()
    slides = re.findall(r'<section class="slide[^"]*" data-title="([^"]+)">', html)
    assert len(slides) == 12 and slides[0] == "Cover" and slides[-1] == "The ask"
    assert html.count('<aside class="speaker-notes">') == 12
    assert not re.search(r"\{\{[a-z_0-9]+\}\}", html)
    assert not re.search(r"placehold\.co|\[Project Name\]|Lorem|TODO|TBD", html)
    # every screenshot the deck embeds is a file that ships beside it
    for src in re.findall(r'<img src="([^"]+)"', html):
        assert (DECK.parent / src).is_file(), src


def test_the_version_stamp_is_the_one_version_the_tree_carries_and_the_bump_moves_all_of_it(
    tmp_path,
):
    """One version: pyproject.toml is the source; __version__, /api/health and the page's stamp
    repeat it. A release commit is tagged with exactly that string, so a tag on HEAD must equal
    the stamp (a bump that forgot to re-render is caught here, not on the live footer)."""
    html = DECK.read_text()
    stamped = re.findall(r'<span class="ver">([^<]+)</span>', html)
    assert stamped and len(set(stamped)) == 1
    assert re.fullmatch(r"v\d+\.\d+\.\d+", stamped[0])
    assert stamped[0] == render_site.version() == "v" + shelfware.__version__
    assert stamped[0] == "v" + bump_version.current()
    assert f'version: "{shelfware.__version__}"' in (ROOT / "api" / "health.js").read_text()
    assert stamped[0] in (ROOT / "site" / "index.html").read_text()
    exact = subprocess.run(
        ["git", "describe", "--tags", "--exact-match", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if exact.returncode == 0 and exact.stdout.strip():
        assert exact.stdout.strip() == stamped[0]
    # the bump rewrites all three stamps, exactly one each, and refuses a non-version
    for rel in ("pyproject.toml", "shelfware/__init__.py", "api/health.js"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text((ROOT / rel).read_text())
    bump_version.bump("9.8.7", root=tmp_path)
    assert 'version = "9.8.7"' in (tmp_path / "pyproject.toml").read_text()
    assert '__version__ = "9.8.7"' in (tmp_path / "shelfware" / "__init__.py").read_text()
    assert 'version: "9.8.7",' in (tmp_path / "api" / "health.js").read_text()
    with pytest.raises(SystemExit):
        bump_version.bump("v1", root=tmp_path)


def test_the_landing_and_judge_pages_link_the_deck_and_call_the_api_at_an_absolute_base():
    landing = (ROOT / "site" / "index.html").read_text()
    judge = (ROOT / "site" / "judge" / "index.html").read_text()
    assert 'href="/pitch/"' in landing and 'href="/pitch/"' in judge
    inline = json.loads(re.search(r"window\.SHELF = (\{.*?\});\n</script>", landing, re.S).group(1))
    assert inline["api_base"] == render_site.API_URL
    assert f'href="{render_site.API_URL}/api/health"' in landing
    # the page's fetches go through the base: same-origin on the canonical host, Vercel and localhost, absolute elsewhere
    app = (ROOT / "scripts" / "site_templates" / "app.js").read_text()
    assert "fetch(API + url" in app and "S.api_base" in app
    assert "shelfware\\.edycu\\.dev" in app
    # one host: no Pages mirror, so no CNAME may reappear and claim the Vercel domain
    assert not (ROOT / "site" / "CNAME").exists()
    assert not (ROOT / ".github" / "workflows" / "pages.yml").exists()
