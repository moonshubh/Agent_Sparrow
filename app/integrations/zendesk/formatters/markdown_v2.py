from __future__ import annotations

import re

import bleach
import mistune
from bs4 import BeautifulSoup, NavigableString
from mistune.plugins import url


_UNICODE_BULLETS_RE = re.compile(r"^(\s*)([•●◦‣▪∙·])\s+(.*)$")
_BOLDED_ORDINAL_RE = re.compile(r"^(\s*)(\*\*|__)(\d+)[\.)]\s+(.*?)(\2)\s*(.*)$")
_LABEL_VALUE_RE = re.compile(r"^(\s*)([A-Z][A-Za-z0-9 \-/()]+):\s+(.*)$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*[:\-]+\s*(?:\|\s*[:\-]+\s*)+\|?\s*$")


def _split_table_row(line: str) -> list[str]:
    raw = line.strip().strip("|")
    return [c.strip() for c in raw.split("|")]


def _pipe_table_to_ascii(table_lines: list[str]) -> str:
    header = _split_table_row(table_lines[0])
    body_lines = table_lines[2:]
    rows = [header] + [_split_table_row(ln) for ln in body_lines]

    if not rows or len(rows[0]) < 2:
        return "\n".join(table_lines)

    col_count = len(rows[0])
    if any(len(r) != col_count for r in rows):
        return "\n".join(table_lines)

    widths = [0] * col_count
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(r: list[str]) -> str:
        cells = [r[i].ljust(widths[i]) for i in range(col_count)]
        return "| " + " | ".join(cells) + " |"

    sep = "| " + " | ".join("-" * widths[i] for i in range(col_count)) + " |"
    out = [fmt_row(header), sep]
    for r in rows[1:]:
        out.append(fmt_row(r))
    return "\n".join(out)


def _normalize_markdown(text: str) -> str:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    out: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")
        stripped = line.strip()

        # Render pipe tables as a fenced code block (safe fallback if Zendesk strips <table>).
        if (
            "|" in line
            and i + 1 < len(lines)
            and _TABLE_SEPARATOR_RE.match(lines[i + 1])
        ):
            header_cells = _split_table_row(line)
            if len(header_cells) >= 2:
                table_block = [line, lines[i + 1]]
                j = i + 2
                while j < len(lines) and lines[j].strip() and "|" in lines[j]:
                    table_block.append(lines[j])
                    j += 1

                ascii_table = _pipe_table_to_ascii(table_block)
                out.append("```")
                out.extend(ascii_table.splitlines())
                out.append("```")
                out.append("")
                i = j
                continue

        # Hide noisy section label that agents often include but humans remove in Zendesk.
        if stripped.lower().rstrip(":") == "suggested reply":
            out.append("")
            i += 1
            continue

        m_bullet = _UNICODE_BULLETS_RE.match(line)
        if m_bullet:
            out.append(f"{m_bullet.group(1)}- {m_bullet.group(3)}")
            i += 1
            continue

        # Convert "**2. Title**" -> "2. **Title**" (Markdown list detection requires the digit first).
        m_bold_ordinal = _BOLDED_ORDINAL_RE.match(line)
        if m_bold_ordinal:
            indent, marker, num, title, _, tail = m_bold_ordinal.groups()
            rebuilt = f"{indent}{num}. {marker}{title.strip()}{marker}"
            tail = (tail or "").strip()
            if tail:
                rebuilt += f" {tail}"
            out.append(rebuilt)
            i += 1
            continue

        # Convert "Server: foo" -> "- **Server:** foo" to match Zendesk formatting expectations.
        if not re.match(r"^\s*(?:[-*+]\s+|\d+[\.)]\s+)", line):
            m_label = _LABEL_VALUE_RE.match(line)
            if m_label:
                indent, label, rest = m_label.groups()
                out.append(f"{indent}- **{label.strip()}:** {rest.strip()}")
                i += 1
                continue

        out.append(line)

        i += 1

    merged = "\n".join(out)
    # Models sometimes emit literal formatting examples like `inline code`.
    merged = re.sub(r"`\s*inline\s+code\s*`\s*", "", merged, flags=re.IGNORECASE)
    merged = re.sub(r"\n{3,}", "\n\n", merged).strip()
    return merged


_TRAILING_BR_NBSP_RE = re.compile(r"(?is)<br\s*/?>\s*(?:&nbsp;|\u00a0)\s*$")


def _remove_trailing_br_nbsp(li) -> None:
    # Remove whitespace-only text nodes at the end.
    while (
        li.contents
        and isinstance(li.contents[-1], NavigableString)
        and not str(li.contents[-1]).strip()
    ):
        li.contents[-1].extract()

    # Remove <br>&nbsp; at the very end.
    if len(li.contents) >= 2:
        last = li.contents[-1]
        prev = li.contents[-2]
        if isinstance(last, NavigableString) and str(last) in {"\u00a0", "&nbsp;"}:
            if getattr(prev, "name", None) == "br":
                last.extract()
                prev.extract()


def _ensure_trailing_br_nbsp(li, soup: BeautifulSoup) -> None:
    _remove_trailing_br_nbsp(li)
    li.append(soup.new_tag("br"))
    li.append(NavigableString("\u00a0"))


def _convert_headings_to_bold(root, soup: BeautifulSoup) -> None:
    """Convert heading tags to bold lines with Zendesk-friendly spacing.

    Zendesk applies large default margins to <h2>/<h3>, which creates
    excessive whitespace. We replace headings with <strong> and controlled
    <br>&nbsp; spacing to match manual edits.
    """
    for heading in list(root.find_all(["h1", "h2", "h3"])):
        inside_li = heading.find_parent("li") is not None

        strong = soup.new_tag("strong")
        for child in list(heading.contents):
            strong.append(child.extract())

        heading.replace_with(strong)

        if inside_li:
            nodes = [soup.new_tag("br"), NavigableString("\u00a0")]
        else:
            nodes = [
                soup.new_tag("br"),
                NavigableString("\u00a0"),
                soup.new_tag("br"),
            ]

        for node in reversed(nodes):
            strong.insert_after(node)


def _convert_paragraphs_to_br(root, soup: BeautifulSoup) -> None:
    # Convert <p> blocks into Zendesk-friendly <br>&nbsp;<br> spacing.
    for p in list(root.find_all("p")):
        inside_li = p.find_parent("li") is not None

        if inside_li:
            nodes = [soup.new_tag("br"), NavigableString("\u00a0")]
        else:
            nodes = [soup.new_tag("br"), NavigableString("\u00a0"), soup.new_tag("br")]

        # insert_after inserts closest-to-element; insert in reverse to preserve order
        for node in reversed(nodes):
            p.insert_after(node)
        p.unwrap()


def _ensure_br_nbsp_before_nested_lists(root, soup: BeautifulSoup) -> None:
    """Ensure a visible break between a list item's intro text and its nested list.

    Mistune sometimes renders nested lists without a <p> wrapper in the parent <li>,
    so our paragraph-to-<br> conversion won't insert spacing. Zendesk's editor typically
    inserts a <br>&nbsp; here when humans edit.
    """

    def _is_whitespace_text(node: object) -> bool:
        if not isinstance(node, NavigableString):
            return False
        txt = str(node)
        if txt in {"\u00a0", "&nbsp;"}:
            return False
        return not txt.strip()

    for li in root.find_all("li"):
        for child in list(li.contents):
            if getattr(child, "name", None) not in {"ul", "ol"}:
                continue

            # Build a list of meaningful nodes that appear before the nested list.
            prefix: list[object] = []
            for n in li.contents:
                if n is child:
                    break
                if _is_whitespace_text(n):
                    continue
                prefix.append(n)

            if not prefix:
                continue

            # Already has <br>&nbsp; immediately before the nested list.
            if len(prefix) >= 2:
                prev, last = prefix[-2], prefix[-1]
                if (
                    getattr(prev, "name", None) == "br"
                    and isinstance(last, NavigableString)
                    and str(last) in {"\u00a0", "&nbsp;"}
                ):
                    continue

            child.insert_before(soup.new_tag("br"))
            child.insert_before(NavigableString("\u00a0"))


def _normalize_list_spacing(root, soup: BeautifulSoup) -> None:
    # Unordered lists: loose spacing per item, but avoid trailing breaks on items that
    # contain nested lists (Zendesk already adds spacing there).
    for ul in root.find_all("ul"):
        lis = ul.find_all("li", recursive=False)
        for li in lis:
            if li.find(["ul", "ol"]):
                _remove_trailing_br_nbsp(li)
                continue
            _ensure_trailing_br_nbsp(li, soup)

    # Ordered lists: loose spacing for each item unless it contains a nested list
    for ol in root.find_all("ol"):
        lis = ol.find_all("li", recursive=False)
        for li in lis:
            if li.find(["ul", "ol"]):
                continue
            _ensure_trailing_br_nbsp(li, soup)


def _flatten_secondary_ordered_lists(root, soup: BeautifulSoup) -> None:
    # Some LLM outputs accidentally restart ordered lists at 1 after a <ul> block.
    # Zendesk renders that as a second 1..N list, which users often manually fix by
    # converting the second list into plain "3.", "4." lines.
    def _next_tag(node):
        sib = node.next_sibling
        while sib is not None:
            if isinstance(sib, NavigableString) and not str(sib).strip():
                sib = sib.next_sibling
                continue
            return sib if getattr(sib, "name", None) else None
        return None

    for ol in list(root.find_all("ol", recursive=False)):
        next1 = _next_tag(ol)
        if getattr(next1, "name", None) != "ul":
            continue
        next2 = _next_tag(next1)
        if getattr(next2, "name", None) != "ol":
            continue

        start_attr = (next2.get("start") or "").strip()
        if start_attr and start_attr != "1":
            continue

        base = len(ol.find_all("li", recursive=False))
        lis2 = next2.find_all("li", recursive=False)
        if not lis2:
            continue

        nodes_to_insert: list[object] = []
        for idx, li in enumerate(lis2, start=1):
            n = base + idx
            nodes_to_insert.append(NavigableString(f"{n}. "))

            frag = BeautifulSoup(li.decode_contents(), "lxml")
            frag_root = frag.body or frag
            for child in list(frag_root.contents):
                # Skip whitespace-only nodes to keep the output compact.
                if isinstance(child, NavigableString) and not str(child).strip():
                    continue
                nodes_to_insert.append(child)

            # Blank line after each numbered line (matches typical manual Zendesk formatting)
            nodes_to_insert.append(soup.new_tag("br"))
            nodes_to_insert.append(NavigableString("\u00a0"))
            nodes_to_insert.append(soup.new_tag("br"))

        # Insert after the <ul> in order (insert_after inserts closest; reverse to preserve order)
        for node in reversed(nodes_to_insert):
            next1.insert_after(node)

        # Remove the secondary <ol>
        next2.decompose()


class _ZendeskMarkdownV2Renderer(mistune.HTMLRenderer):
    def __init__(self, *, format_style: str) -> None:
        super().__init__()

    def list_item(self, text: str) -> str:
        rendered = (text or "").strip()
        return f"<li>{rendered}</li>\n"

    def image(self, text: str, url: str, title=None) -> str:
        label = (text or "").strip() or "Image"
        return self.link(label, url, title)


_ALLOWED_TAGS: list[str] = [
    "p",
    "br",
    "strong",
    "em",
    "code",
    "pre",
    "ul",
    "ol",
    "li",
    "a",
    "blockquote",
    "h1",
    "h2",
    "h3",
]

_ALLOWED_ATTRS: dict[str, list[str]] = {
    "a": ["href", "title", "rel"],
}


def format_zendesk_internal_note_markdown_v2(
    text: str,
    *,
    heading_level: str = "h3",
    format_style: str = "compact",
) -> str:
    """Render Markdown into Zendesk-safe HTML (v2).

    Goals:
    - Loose list spacing via trailing <br/>&nbsp; in list items (relaxed mode)
    - Support unicode bullets by normalizing to Markdown '-'
    - Avoid <img> tags (render images as links)
    """

    safe_heading_level = (heading_level or "h3").strip().lower()
    if safe_heading_level not in {"h2", "h3"}:
        safe_heading_level = "h3"

    normalized = _normalize_markdown(text)

    renderer = _ZendeskMarkdownV2Renderer(format_style=format_style)
    md = mistune.create_markdown(renderer=renderer, plugins=[url.url])
    rendered = md(normalized)

    cleaned = bleach.clean(
        rendered,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=["http", "https", "mailto"],
        strip=True,
    ).strip()

    # If headings made it through, normalize levels (h1->h3) to match Zendesk UI.
    cleaned = re.sub(r"(?i)<h1(\s[^>]*)?>", f"<{safe_heading_level}>", cleaned)
    cleaned = re.sub(r"(?i)</h1>", f"</{safe_heading_level}>", cleaned)

    # Ensure greeting exists early (downstream quality gate expects it).
    greeting_window = cleaned[:700].lower()
    has_hi = "hi there" in greeting_window
    has_team = "mailbird customer happiness team" in greeting_window
    if not (has_hi and has_team):
        greeting = "<p>Hi there,<br>&nbsp;<br>Many thanks for contacting the Mailbird Customer Happiness Team.</p>"
        cleaned = f"{greeting}\n{cleaned}".strip()

    # Normalize legacy greeting to the split-line format.
    cleaned = re.sub(
        r"(?is)<p>\s*Hi\s+there\s*,?\s+Many\s+thanks\s+for\s+contacting\s+the\s+Mailbird\s+Customer\s+Happiness\s+Team\b\.?\s*</p>",
        "<p>Hi there,<br>&nbsp;<br>Many thanks for contacting the Mailbird Customer Happiness Team.</p>",
        cleaned,
    )

    soup = BeautifulSoup(f"<div>{cleaned}</div>", "lxml")
    root = soup.div
    if root is None:
        return cleaned

    _convert_headings_to_bold(root, soup)
    _convert_paragraphs_to_br(root, soup)
    _ensure_br_nbsp_before_nested_lists(root, soup)
    _flatten_secondary_ordered_lists(root, soup)
    _normalize_list_spacing(root, soup)

    out = root.decode_contents().strip()
    # Avoid excessive trailing whitespace and breaks
    out = re.sub(
        r"(?:<br\s*/?>\s*(?:&nbsp;|\u00a0)?\s*){2,}$",
        "<br>",
        out,
        flags=re.IGNORECASE,
    )
    return out.strip()
