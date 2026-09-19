"""The Markdown subset JUDGE.md is written in, rendered to HTML with the stdlib.

Headings, paragraphs, fenced code, pipe tables, ordered and bulleted lists, and inline
bold / code / links. Nothing else is needed for the judge page, and a dependency for it
would be the project's first — the engine is stdlib-only by design, and so is its tooling.

Relative links are rewritten to the repository on GitHub, because the page is served from
the site, not from the checkout: `DEMO.md` -> `<repo>/blob/main/DEMO.md`, a directory ->
`<repo>/tree/main/…`. Absolute URLs and fragments are left alone.
"""

import re
from html import escape
from pathlib import Path

INLINE_CODE = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*(.+?)\*\*")
EM = re.compile(r"(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
ORDERED = re.compile(r"^(\d+)\.\s+(.*)$")


def _rewrite(href, repo, root):
    if re.match(r"^[a-z][a-z0-9+.-]*:", href) or href.startswith(("#", "/")):
        return href
    path, _, frag = href.partition("#")
    kind = "tree" if (root / path).is_dir() else "blob"
    return f"{repo}/{kind}/main/{path}" + (f"#{frag}" if frag else "")


def inline(text, repo, root):
    """Escape first, then mark up — so nothing in the Markdown can inject HTML."""
    text = escape(text, quote=False)
    codes = []

    def keep(m):
        codes.append(f"<code>{m.group(1)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = INLINE_CODE.sub(keep, text)
    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = EM.sub(r"<em>\1</em>", text)
    text = LINK.sub(
        lambda m: f'<a href="{escape(_rewrite(m.group(2), repo, root))}">{m.group(1)}</a>', text
    )
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def render(md, repo, root):
    lines = md.splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + escape("\n".join(lines[i + 1 : j])) + "</pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2), repo, root)}</h{level}>")
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[2:]] if len(rows) > 1 else []
            th = "".join(f"<th>{inline(c, repo, root)}</th>" for c in head)
            thead = f"<thead><tr>{th}</tr></thead>" if any(head) else ""
            trs = "".join(
                "<tr>" + "".join(f"<td>{inline(c, repo, root)}</td>" for c in r) + "</tr>"
                for r in body
            )
            out.append(f"<table>{thead}<tbody>{trs}</tbody></table>")
            continue
        if ORDERED.match(line) or line.startswith("- "):
            ordered = bool(ORDERED.match(line))
            items = []
            while i < len(lines) and lines[i].strip():
                m = ORDERED.match(lines[i]) if ordered else None
                if m or (not ordered and lines[i].startswith("- ")):
                    items.append(m.group(2) if m else lines[i][2:])
                elif lines[i].startswith(" ") and items:
                    items[-1] += " " + lines[i].strip()
                else:
                    break
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(
                f"<{tag}>"
                + "".join(f"<li>{inline(t, repo, root)}</li>" for t in items)
                + f"</{tag}>"
            )
            continue
        para = []
        while (
            i < len(lines)
            and lines[i].strip()
            and not re.match(r"^(#{1,3}\s|```|\||- |\d+\.\s)", lines[i])
        ):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(para), repo, root)}</p>")
    return "\n".join(out)


def render_file(path, repo):
    path = Path(path)
    return render(path.read_text(), repo, path.resolve().parent)
