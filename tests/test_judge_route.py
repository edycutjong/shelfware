"""The /judge route: the page a judge reads is JUDGE.md, rendered, with no auth, no cookies and
no redirect — and it cannot drift from the file, because it IS the file's render."""

import re
import sys
import urllib.request
from html import unescape
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import md2html  # noqa: E402
import render_site  # noqa: E402

CLAIM_WORDS = ("has no wrapper", "CMC-tracked market", "has_tokens")


def test_the_judge_page_carries_the_claim_and_states_the_pair_the_rows_produce():
    html = render_site.render_judge()
    body = html.split("<article>")[1].split("</article>")[0]
    for w in ("<h1>For judges</h1>", "<h2>The claim</h2>", "<h2>The 30-second path</h2>"):
        assert w in body
    # the same rule scripts/verify.py applies to README, DEMO and the landing page
    assert re.search(r"\b476\s+of\s+791\b", body)
    assert "python3 -m shelfware MS" in body
    assert "never traded" not in body.replace('never "never traded"', "")


def test_the_committed_judge_page_is_what_judge_md_renders():
    """render_site.py --check gates this in CI; here it is a named test so a hand edit to
    site/judge/index.html fails the suite too, not only the pipeline."""
    assert (ROOT / "site" / "judge" / "index.html").read_text() == render_site.render_judge()


def test_every_repository_link_on_the_judge_page_resolves_in_the_checkout():
    html = render_site.render_judge()
    hrefs = [unescape(h) for h in re.findall(r'href="([^"]+)"', html)]
    repo_links = [h for h in hrefs if h.startswith(render_site.REPO + "/")]
    assert len(repo_links) >= 10
    for h in repo_links:
        m = re.match(r"https://github\.com/edycutjong/shelfware/(blob|tree)/main/([^#]+)", h)
        if m:  # /blob/main/<file> and /tree/main/<dir> must exist in this checkout
            assert (ROOT / m.group(2)).exists(), h
    for h in hrefs:  # nothing relative survives — the page is served from the site, not the repo
        assert h.startswith(("http", "/", "#", "data:")), h


def test_relative_links_are_rewritten_to_the_repository_and_absolute_ones_are_left_alone():
    out = md2html.render(
        "[a](DEMO.md) [b](docs/proof/live_run.json#x) [c](shelfware/) "
        "[d](https://example.org/p) [e](#frag) [f](/api/health)",
        "https://github.com/o/r",
        ROOT,
    )
    assert 'href="https://github.com/o/r/blob/main/DEMO.md"' in out
    assert 'href="https://github.com/o/r/blob/main/docs/proof/live_run.json#x"' in out
    assert 'href="https://github.com/o/r/tree/main/shelfware/"' in out
    assert 'href="https://example.org/p"' in out and 'href="#frag"' in out
    assert 'href="/api/health"' in out


def test_the_markdown_subset_renders_every_construct_judge_md_uses_and_escapes_html():
    md = "\n".join(
        [
            "# T",
            "",
            "para with **bold**, `co<de>` and *em* <script>alert(1)</script>",
            "",
            "| a | b |",
            "|---|---|",
            "| 1 | **2** |",
            "",
            "1. one",
            "   continued",
            "2. two",
            "",
            "- x",
            "- y",
            "",
            "```bash",
            "echo <hi> && ok",
            "```",
        ]
    )
    out = md2html.render(md, "https://github.com/o/r", ROOT)
    assert "<h1>T</h1>" in out
    assert "<strong>bold</strong>" in out and "<code>co&lt;de&gt;</code>" in out
    assert "<em>em</em>" in out
    assert "<script>" not in out and "&lt;script&gt;alert(1)&lt;/script&gt;" in out
    assert "<table><thead><tr><th>a</th><th>b</th></tr></thead>" in out
    assert "<td><strong>2</strong></td>" in out
    assert "<ol><li>one continued</li><li>two</li></ol>" in out
    assert "<ul><li>x</li><li>y</li></ul>" in out
    assert "<pre>echo &lt;hi&gt; &amp;&amp; ok</pre>" in out


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AssertionError(f"/judge redirected ({code}) to {newurl} — it must be served directly")


@pytest.mark.live
def test_live_judge_route_answers_200_with_no_credentials_no_cookies_no_redirect():
    """§3.9 of the harness: a /judge page that breaks on submission day is worse than none.
    This fetches the deployed route the way a judge would — a bare GET, no session."""
    url = render_site.SITE_URL + "/judge"
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "shelfware-tests"})
    with opener.open(req, timeout=30) as resp:
        assert resp.status == 200
        assert resp.headers.get("Content-Type", "").startswith("text/html")
        assert resp.headers.get("Set-Cookie") is None
        page = resp.read().decode()
    assert "<h1>For judges</h1>" in page
    for w in CLAIM_WORDS:
        assert w in page
    assert re.search(r"\b476\s+of\s+791\b", page)
