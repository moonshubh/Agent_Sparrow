from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from app.core.settings import settings  # noqa: E402
from app.integrations.zendesk.client import ZendeskClient  # noqa: E402
from app.integrations.zendesk import scheduler  # noqa: E402


def _require_settings() -> tuple[str, str, str]:
    subdomain = getattr(settings, "zendesk_subdomain", None)
    email = getattr(settings, "zendesk_email", None)
    api_token = getattr(settings, "zendesk_api_token", None)
    missing = [
        k
        for k, v in (
            ("ZENDESK_SUBDOMAIN", subdomain),
            ("ZENDESK_EMAIL", email),
            ("ZENDESK_API_TOKEN", api_token),
        )
        if not v
    ]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")
    return str(subdomain), str(email), str(api_token)


def _build_format_test_note() -> str:
    return """Hi there,
Many thanks for contacting the Mailbird Customer Happiness Team.

Thanks for the details. To double-check the settings, here is a quick reference table:

| Setting | Value |
| --- | --- |
| IMAP server | `imap.example.com` |
| IMAP port | `993` |
| SMTP server | `smtp.example.com` |
| SMTP port | `465` |

![Inline Screenshot](https://example.com/screenshot.png)

1. Restart Mailbird.
2. Re-authenticate the account.

- If you see `AUTHENTICATIONFAILED`, confirm the incoming server and port values match the table above.
    - If they do not, update them and try again.
"""


def _build_complex_table_rows() -> list[tuple[str, str, str]]:
    # 3-column table: (Test/Area, Notes, Expected/Verify)
    base_expected = "Email account is added and emails can be seen in Mailbird"
    return [
        ("First impression/Overall general cases", "", ""),
        (
            "Newsletter consent on first open",
            "",
            "User is presented with a clear option to consent to newsletters emails during first run/setup.",
        ),
        ("MB Trial", "", "Verify that MB Trial is offered for 7 days"),
        (
            "General first impressions (tooltips and stuff)",
            "",
            "Initial tooltips or popups are helpful and not intrusive. The overall initial experience feels smooth and intuitive.",
        ),
        (
            "Tooltip",
            "",
            "Verify that tool tip correctly shows names/titles everywhere (Eg - when hovering over folders, accounts, icons)",
        ),
        (
            "Cursor States",
            "Check/verify this alongside other testing sections (composer actions, drag & drop emails, left emails viewing pane, etc).",
            "Verify cursor changes to I-beam when hovering over text input areas (Compose body, To/Subject fields, Search).",
        ),
        (
            "Cursor States",
            "",
            "Verify cursor changes to pointer/hand when hovering over clickable elements (buttons, links, conversation items, app icons).",
        ),
        (
            "Cursor States",
            "",
            "Verify cursor remains default arrow when hovering over non-interactive areas.",
        ),
        ("Email account", "", ""),
        ("Adding Accounts", "", ""),
        ("Add all of your email accounts", "", base_expected),
        ("Add an Gmail", "", base_expected),
        ("Add an Outlook/MS 365", "", base_expected),
        ("Add an Yahoo", "", base_expected),
        ("Add an Exchange account (verify auto-discovery)", "", base_expected),
        (
            "Add an iCloud (Test manual addition)",
            "Meaning: try to put in server settings manually",
            base_expected,
        ),
        (
            "Adding Accounts",
            "",
            "Verify that for all accounts by default inbox is selected after accounts are added in MB",
        ),
    ]


def _render_html_table(rows: list[tuple[str, str, str]]) -> str:
    parts: list[str] = [
        '<table border="1" cellpadding="6" cellspacing="0">',
        "<thead><tr><th>Area / Test</th><th>Notes</th><th>Expected</th></tr></thead>",
        "<tbody>",
    ]
    for col1, col2, col3 in rows:
        if not (str(col1).strip() or str(col2).strip() or str(col3).strip()):
            continue
        parts.append(
            "<tr>"
            f"<td>{html.escape(str(col1 or ''))}</td>"
            f"<td>{html.escape(str(col2 or ''))}</td>"
            f"<td>{html.escape(str(col3 or ''))}</td>"
            "</tr>"
        )
    parts.append("</tbody></table>")
    return "\n".join(parts)


def _build_complex_html_note(*, images: list[dict[str, str | None]]) -> str:
    rows = _build_complex_table_rows()
    table_html = _render_html_table(rows)

    img_blocks: list[str] = []
    link_blocks: list[str] = []
    for idx, info in enumerate(images, start=1):
        name = str(info.get("file_name") or f"image_{idx}")
        url = info.get("content_url")
        if url:
            url_str = str(url)
            # Attempt inline <img> plus an explicit link fallback.
            img_blocks.append(
                f"<p><strong>Image {idx}:</strong> {html.escape(name)}</p>"
                f'<p><img src="{html.escape(url_str)}" alt="{html.escape(name)}" /></p>'
            )
            link_blocks.append(
                f'<li><a href="{html.escape(url_str)}">{html.escape(name)}</a></li>'
            )
        else:
            img_blocks.append(
                f"<p><strong>Image {idx}:</strong> {html.escape(name)} (uploaded)</p>"
            )

    fallback_links = ""
    if link_blocks:
        fallback_links = (
            "<p>Attachment links (fallback):</p><ul>" + "".join(link_blocks) + "</ul>"
        )

    parts = [
        "<p>Hi there,&nbsp;<br>Many thanks for contacting the Mailbird Customer Happiness Team.</p><br>&nbsp;<br>",
        "<p>Formatting test: complex table + 3 uploaded images (internal note).</p>",
        "<h3>Complex Table</h3>",
        table_html,
        "<h3>Images</h3>",
        "\n".join(img_blocks) if img_blocks else "<p>(No images provided.)</p>",
        fallback_links,
    ]
    return "\n".join([p for p in parts if p]).strip()


def _format_note(
    text: str, *, use_html: bool, engine: str, heading_level: str, style: str
) -> str:
    if not use_html:
        return text

    engine_norm = (engine or "").strip().lower()
    if engine_norm == "markdown_v2":
        from app.integrations.zendesk.formatters.markdown_v2 import (
            format_zendesk_internal_note_markdown_v2,
        )

        return format_zendesk_internal_note_markdown_v2(
            text,
            heading_level=heading_level,
            format_style=style,
        )

    return scheduler._format_zendesk_internal_note_html(
        text,
        heading_level=heading_level,
        format_style=style,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post a rich-formatting Zendesk internal note (table + image) to validate rendering."
    )
    parser.add_argument(
        "--ticket-id", type=int, default=552193, help="Zendesk ticket ID"
    )
    parser.add_argument(
        "--post", action="store_true", help="Actually post (otherwise dry-run)"
    )
    parser.add_argument(
        "--tag", type=str, default="", help="Optional tag to add on update"
    )
    parser.add_argument(
        "--use-html",
        dest="use_html",
        action="store_true",
        help="Force HTML posting (default: follow settings.zendesk_use_html)",
    )
    parser.add_argument(
        "--no-html",
        dest="use_html",
        action="store_false",
        help="Force plain text posting",
    )
    parser.set_defaults(use_html=None)
    parser.add_argument(
        "--engine",
        type=str,
        default="",
        help='Formatter engine: "legacy" or "markdown_v2" (default: follow settings.zendesk_format_engine)',
    )
    parser.add_argument(
        "--style",
        type=str,
        default="",
        help='Formatter style: "compact" or "relaxed" (default: follow settings.zendesk_format_style)',
    )
    parser.add_argument(
        "--heading-level",
        type=str,
        default="",
        help='Heading level: "h2" or "h3" (default: follow settings.zendesk_heading_level)',
    )
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        help="Local image path to upload+attach (repeatable)",
    )
    parser.add_argument(
        "--complex-table",
        action="store_true",
        help="Use the provided long/complex test table payload",
    )
    args = parser.parse_args()

    subdomain, email, api_token = _require_settings()
    zc = ZendeskClient(
        subdomain=subdomain,
        email=email,
        api_token=api_token,
        dry_run=not args.post,
    )

    use_html = (
        bool(args.use_html)
        if args.use_html is not None
        else bool(getattr(settings, "zendesk_use_html", True))
    )
    engine = args.engine or str(
        getattr(settings, "zendesk_format_engine", "markdown_v2")
    )
    style = args.style or str(getattr(settings, "zendesk_format_style", "compact"))
    heading_level = args.heading_level or str(
        getattr(settings, "zendesk_heading_level", "h3")
    )

    uploads: list[str] = []
    uploaded_images: list[dict[str, str | None]] = []
    for img_path in args.image or []:
        upload_res = zc.upload_file(img_path)
        token = upload_res.get("token")
        if isinstance(token, str) and token.strip() and token != "dry_run":
            uploads.append(token)
        attachment = upload_res.get("attachment")
        content_url = (
            attachment.get("content_url") if isinstance(attachment, dict) else None
        )
        file_name = (
            attachment.get("file_name") if isinstance(attachment, dict) else None
        )
        if not file_name:
            file_name = Path(img_path).name
        uploaded_images.append(
            {
                "file_name": str(file_name),
                "content_url": str(content_url) if content_url else None,
            }
        )

    if args.complex_table or args.image:
        if use_html:
            formatted = _build_complex_html_note(images=uploaded_images)
        else:
            # Plain-text fallback: attach uploads, include a compact table-like list.
            lines: list[str] = [
                "Hi there,",
                "Many thanks for contacting the Mailbird Customer Happiness Team.",
                "",
                "Formatting test: complex table + uploaded images (internal note).",
                "",
                "Complex table (plain text):",
            ]
            for col1, col2, col3 in _build_complex_table_rows():
                if not (col1.strip() or col2.strip() or col3.strip()):
                    continue
                lines.append(f"- {col1} | {col2} | {col3}")
            formatted = "\n".join(lines).strip()
    else:
        raw = _build_format_test_note()
        formatted = _format_note(
            raw,
            use_html=use_html,
            engine=engine,
            heading_level=heading_level,
            style=style,
        )

    issues = scheduler._quality_gate_issues(formatted, use_html=use_html)
    if issues:
        raise SystemExit(f"Quality gate failed: {', '.join(issues)}")

    add_tag = args.tag.strip() or None
    res = zc.add_internal_note(
        args.ticket_id,
        formatted,
        add_tag=add_tag,
        use_html=use_html,
        uploads=uploads if uploads else None,
    )
    if res.get("dry_run"):
        print(
            f"[DRY_RUN] Prepared note for ticket={args.ticket_id} (use_html={use_html}, engine={engine})."
        )
    else:
        updated_at = (
            res.get("ticket", {}).get("updated_at")
            if isinstance(res.get("ticket"), dict)
            else None
        )
        print(f"Posted internal note: ticket={args.ticket_id} updated_at={updated_at}")


if __name__ == "__main__":
    main()
