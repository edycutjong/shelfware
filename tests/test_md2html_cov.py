"""The Markdown subset, edge by edge: every link shape, every block boundary, every place a
block ends because the next line is something else."""

import sys

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import md2html  # noqa: E402

REPO = "https://github.com/o/r"


@pytest.fixture
def checkout(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "DEMO.md").write_text("# demo\n")
    return tmp_path


def test_a_relative_file_link_becomes_a_blob_and_a_directory_a_tree(checkout):
    assert md2html._rewrite("DEMO.md", REPO, checkout) == f"{REPO}/blob/main/DEMO.md"
    assert md2html._rewrite("pkg", REPO, checkout) == f"{REPO}/tree/main/pkg"
    assert md2html._rewrite("pkg/", REPO, checkout) == f"{REPO}/tree/main/pkg/"
    assert md2html._rewrite("missing.txt", REPO, checkout) == f"{REPO}/blob/main/missing.txt"


def test_a_fragment_on_a_relative_link_survives_the_rewrite(checkout):
    assert md2html._rewrite("DEMO.md#top", REPO, checkout) == f"{REPO}/blob/main/DEMO.md#top"
    assert md2html._rewrite("pkg#x", REPO, checkout) == f"{REPO}/tree/main/pkg#x"


def test_scheme_fragment_and_root_relative_links_are_left_alone(checkout):
    for href in ("https://x.org/a", "mailto:a@b.c", "s3+http://k", "#frag", "/api/health"):
        assert md2html._rewrite(href, REPO, checkout) == href


def test_inline_escapes_before_marking_up_so_markdown_cannot_inject_html(checkout):
    out = md2html.inline("<b>x</b> **y** `<i>` *z* [q](DEMO.md)", REPO, checkout)
    assert out == (
        "&lt;b&gt;x&lt;/b&gt; <strong>y</strong> <code>&lt;i&gt;</code> <em>z</em> "
        f'<a href="{REPO}/blob/main/DEMO.md">q</a>'
    )


def test_markup_inside_inline_code_is_not_interpreted(checkout):
    out = md2html.inline("`**not bold** [not](a.md) *no*` and **yes**", REPO, checkout)
    assert "<code>**not bold** [not](a.md) *no*</code>" in out
    assert "<strong>yes</strong>" in out
    assert "\x00" not in out


def test_several_code_spans_come_back_in_order(checkout):
    out = md2html.inline("`a` then `b` then `c`", REPO, checkout)
    assert out == "<code>a</code> then <code>b</code> then <code>c</code>"


def test_emphasis_does_not_fire_inside_words_or_on_spaced_asterisks(checkout):
    assert md2html.inline("a*b*c", REPO, checkout) == "a*b*c"
    assert md2html.inline("2 * 3 * 4", REPO, checkout) == "2 * 3 * 4"
    assert md2html.inline("say *hi* now", REPO, checkout) == "say <em>hi</em> now"


def test_a_link_href_with_a_quote_is_escaped_in_the_attribute(checkout):
    out = md2html.inline('[t](https://x.org/?q="2")', REPO, checkout)
    assert out == '<a href="https://x.org/?q=&quot;2&quot;">t</a>'


def test_blank_lines_are_skipped_and_headings_take_three_levels(checkout):
    out = md2html.render("\n\n# one\n\n## two **b**\n### three\n#### four\n", REPO, checkout)
    assert out.split("\n") == [
        "<h1>one</h1>",
        "<h2>two <strong>b</strong></h2>",
        "<h3>three</h3>",
        "<p>#### four</p>",
    ]


def test_a_fenced_block_is_escaped_verbatim_and_its_language_tag_dropped(checkout):
    out = md2html.render("```py\nx = 1 < 2\n**not bold**\n```\nafter", REPO, checkout)
    assert out == "<pre>x = 1 &lt; 2\n**not bold**</pre>\n<p>after</p>"


def test_an_unclosed_fence_runs_to_the_end_of_the_document(checkout):
    out = md2html.render("before\n```\nline a\nline b", REPO, checkout)
    assert out == "<p>before</p>\n<pre>line a\nline b</pre>"


def test_an_empty_fence_renders_an_empty_pre(checkout):
    assert md2html.render("```\n```", REPO, checkout) == "<pre></pre>"


def test_a_pipe_table_drops_the_separator_row_and_marks_up_cells(checkout):
    md = "| h1 | `h2` |\n|---|---|\n| a | [l](pkg) |\n| **b** | c |"
    out = md2html.render(md, REPO, checkout)
    assert out == (
        "<table><thead><tr><th>h1</th><th><code>h2</code></th></tr></thead>"
        f'<tbody><tr><td>a</td><td><a href="{REPO}/tree/main/pkg">l</a></td></tr>'
        "<tr><td><strong>b</strong></td><td>c</td></tr></tbody></table>"
    )


def test_a_one_row_table_has_a_head_and_no_body(checkout):
    out = md2html.render("| only | row |", REPO, checkout)
    assert out == "<table><thead><tr><th>only</th><th>row</th></tr></thead><tbody></tbody></table>"


def test_a_table_whose_head_is_all_empty_cells_has_no_thead(checkout):
    out = md2html.render("|  |  |\n|---|---|\n| a | b |", REPO, checkout)
    assert out == "<table><tbody><tr><td>a</td><td>b</td></tr></tbody></table>"


def test_a_table_ends_at_the_first_line_without_a_leading_pipe(checkout):
    out = md2html.render("| a |\n|---|\n| 1 |\ntext", REPO, checkout)
    assert out.endswith("</table>\n<p>text</p>")


def test_an_ordered_list_joins_indented_continuations_and_ends_at_a_blank_line(checkout):
    out = md2html.render("1. one\n   more\n2. two\n\n3. three", REPO, checkout)
    assert out == "<ol><li>one more</li><li>two</li></ol>\n<ol><li>three</li></ol>"


def test_a_bulleted_list_joins_indented_continuations(checkout):
    out = md2html.render("- x\n  cont\n- y", REPO, checkout)
    assert out == "<ul><li>x cont</li><li>y</li></ul>"


def test_a_list_ends_at_a_line_that_is_neither_an_item_nor_indented(checkout):
    out = md2html.render("- x\n- y\nplain", REPO, checkout)
    assert out == "<ul><li>x</li><li>y</li></ul>\n<p>plain</p>"
    out = md2html.render("1. a\n# h", REPO, checkout)
    assert out == "<ol><li>a</li></ol>\n<h1>h</h1>"


def test_an_ordered_list_does_not_absorb_a_bullet_and_a_bullet_list_not_a_number(checkout):
    out = md2html.render("1. a\n- b", REPO, checkout)
    assert out == "<ol><li>a</li></ol>\n<ul><li>b</li></ul>"
    out = md2html.render("- b\n2. a", REPO, checkout)
    assert out == "<ul><li>b</li></ul>\n<ol><li>a</li></ol>"


def test_a_list_at_the_end_of_the_document_closes(checkout):
    assert md2html.render("- last", REPO, checkout) == "<ul><li>last</li></ul>"
    assert md2html.render("1. last\n   tail", REPO, checkout) == "<ol><li>last tail</li></ol>"


def test_a_paragraph_joins_its_lines_and_stops_at_every_block_opener(checkout):
    for opener, tag in (
        ("# h", "<h1>"),
        ("```", "<pre>"),
        ("| c |", "<table>"),
        ("- i", "<ul>"),
        ("1. i", "<ol>"),
    ):
        out = md2html.render(f"line one\n  line two\n{opener}", REPO, checkout)
        assert out.startswith("<p>line one line two</p>\n" + tag), opener


def test_a_paragraph_stops_at_a_blank_line_or_the_end_of_the_document(checkout):
    assert md2html.render("a\nb\n\nc", REPO, checkout) == "<p>a b</p>\n<p>c</p>"
    assert md2html.render("tail", REPO, checkout) == "<p>tail</p>"


def test_an_empty_document_renders_nothing(checkout):
    assert md2html.render("", REPO, checkout) == ""
    assert md2html.render("\n\n  \n", REPO, checkout) == ""


def test_render_file_reads_the_file_and_resolves_links_against_its_directory(checkout):
    (checkout / "JUDGE.md").write_text("# t\n\nsee [d](DEMO.md) and [p](pkg)\n")
    out = md2html.render_file(str(checkout / "JUDGE.md"), REPO)
    assert out == (
        "<h1>t</h1>\n"
        f'<p>see <a href="{REPO}/blob/main/DEMO.md">d</a> and <a href="{REPO}/tree/main/pkg">p</a></p>'
    )
