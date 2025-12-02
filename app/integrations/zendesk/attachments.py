"""
Lightweight Zendesk attachment fetcher for tickets.

Fetches the latest allowed attachments for a ticket and returns a summary plus
local paths for downstream processing (e.g., log analysis).
"""

from __future__ import annotations

import os
import tempfile
import shutil
import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional

import requests

logger = logging.getLogger(__name__)

ZENDESK_SUBDOMAIN = os.environ.get("ZENDESK_SUBDOMAIN") or "mailbird"
ZENDESK_EMAIL = os.environ.get("ZENDESK_EMAIL")
ZENDESK_API_TOKEN = os.environ.get("ZENDESK_API_TOKEN")


@dataclass
class AttachmentInfo:
    id: int
    file_name: str
    content_url: str
    local_path: Optional[str]
    size: Optional[int]
    content_type: Optional[str]


def _auth() -> tuple[str, str]:
    if not ZENDESK_EMAIL or not ZENDESK_API_TOKEN:
        raise RuntimeError("Missing Zendesk credentials (ZENDESK_EMAIL/ZENDESK_API_TOKEN)")
    return (f"{ZENDESK_EMAIL}/token", ZENDESK_API_TOKEN)


def fetch_ticket_attachments(
    ticket_id: int | str,
    allowed_extensions: Iterable[str] = (".log", ".txt", ".png", ".jpg", ".jpeg", ".pdf"),
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB guardrail per file
) -> List[AttachmentInfo]:
    """
    Fetch allowed attachments for a ticket and download them to a temp folder.

    Returns a list of AttachmentInfo with local_path set for downloaded files.
    """
    exts = {ext.lower() for ext in allowed_extensions}
    url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_id}/comments.json?sort_order=asc&include=attachments"
    resp = requests.get(url, auth=_auth(), timeout=20)
    resp.raise_for_status()
    data = resp.json()
    comments = data.get("comments") or []

    results: List[AttachmentInfo] = []
    tmpdir: str | None = None

    try:
        tmpdir = tempfile.mkdtemp(prefix=f"zendesk-{ticket_id}-")

        for comment in comments:
            for att in comment.get("attachments") or []:
                name = att.get("file_name") or ""
                lower = name.lower()
                if not any(lower.endswith(ext) for ext in exts):
                    continue
                size = att.get("size")
                if size and size > max_bytes:
                    # Skip overly large attachments to avoid surprises
                    continue
                content_url = att.get("content_url")
                local_path = None
                if content_url:
                    try:
                        r = requests.get(content_url, auth=_auth(), timeout=30)
                        r.raise_for_status()
                        local_path = os.path.join(tmpdir, name)
                        with open(local_path, "wb") as f:
                            f.write(r.content)
                    except Exception as exc:
                        logger.warning("failed_to_download_attachment", extra={"ticket_id": ticket_id, "name": name, "error": str(exc)})
                        local_path = None
                att_id = att.get("id") or 0
                results.append(
                    AttachmentInfo(
                        id=att_id,
                        file_name=name,
                        content_url=content_url,
                        local_path=local_path,
                        size=size,
                        content_type=att.get("content_type"),
                    )
                )
    except Exception:
        if tmpdir and os.path.exists(tmpdir):
            shutil.rmtree(tmpdir, ignore_errors=True)
        raise

    return results


def summarize_attachments(att_list: List[AttachmentInfo], max_chars: int = 2000) -> str:
    """Produce a compact textual summary for the agent context."""
    if not att_list:
        return "No attachments fetched."
    lines: List[str] = []
    for att in att_list:
        size_kb = f"{(att.size or 0) / 1024:.1f}KB" if att.size else "unknown size"
        lines.append(f"- {att.file_name} ({size_kb})")
        if att.local_path and att.file_name.lower().endswith((".log", ".txt")):
            try:
                with open(att.local_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read(max_chars + 1)
                snippet = text[:max_chars].rstrip()
                if len(text) > max_chars:
                    snippet += "\n[truncated]"
                lines.append(f"  snippet: {snippet}")
            except Exception:
                lines.append("  snippet: <failed to read>")
    return "\n".join(lines)


def cleanup_attachments(att_list: List[AttachmentInfo]) -> None:
    """Delete temp folders created for attachments in this run."""
    parents = set()
    for att in att_list:
        if att.local_path:
            parents.add(os.path.dirname(att.local_path))
    for parent in parents:
        try:
            shutil.rmtree(parent, ignore_errors=True)
        except Exception:
            pass
