"""The deck at /pitch/ is generated output like the page: every number a slot from the census,
the receipt and the benchmark; the same drift gate; the same wording guard; a version stamp
that is the repository's, not a typed one; and a page the landing links to on both hosts."""

import json
import re
import subprocess
import sys

from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
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


def test_the_version_stamp_is_the_repository_tag_or_the_honest_dev_fallback():
    html = DECK.read_text()
    stamped = re.findall(r'<span class="ver">([^<]+)</span>', html)
    assert stamped and len(set(stamped)) == 1
    try:
        tag = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        tag = "v0.0.0-dev"
    assert stamped[0] == render_site.version() == (tag or "v0.0.0-dev")
    assert re.fullmatch(r"v\d+\.\d+\.\d+(-dev)?", stamped[0])


def test_the_landing_and_judge_pages_link_the_deck_and_call_the_api_at_an_absolute_base():
    landing = (ROOT / "site" / "index.html").read_text()
    judge = (ROOT / "site" / "judge" / "index.html").read_text()
    assert 'href="/pitch/"' in landing and 'href="/pitch/"' in judge
    inline = json.loads(re.search(r"window\.SHELF = (\{.*?\});\n</script>", landing, re.S).group(1))
    assert inline["api_base"] == render_site.API_URL
    assert f'href="{render_site.API_URL}/api/health"' in landing
    # the page's fetches go through the base: same-origin on Vercel and localhost, absolute elsewhere
    app = (ROOT / "scripts" / "site_templates" / "app.js").read_text()
    assert "fetch(API + url" in app and "S.api_base" in app
    assert (ROOT / "site" / "CNAME").read_text().strip() == render_site.PAGES_URL.split("//", 1)[1]
