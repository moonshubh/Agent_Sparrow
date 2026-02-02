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

from .client import ZendeskRateLimitError, zendesk_throttle

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
    allowed_extensions: Iterable[str] = (".log", ".txt", ".png", ".jpg", ".jpeg", ".pdf", ".gif"),
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB guardrail per file (support large logs)
    public_only: bool = False,
) -> List[AttachmentInfo]:
    """
    Fetch allowed attachments for a ticket and download them to a temp folder.

    Returns a list of AttachmentInfo with local_path set for downloaded files.
    """
    exts = {ext.lower() for ext in allowed_extensions}
    url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_id}/comments.json?sort_order=asc&include=attachments"
    zendesk_throttle()
    resp = requests.get(url, auth=_auth(), timeout=20)
    if resp.status_code == 429:
        raise ZendeskRateLimitError.from_response(resp, operation="fetch_ticket_attachments")
    resp.raise_for_status()
    data = resp.json()
    comments = data.get("comments") or []
    if public_only:
        comments = [c for c in comments if isinstance(c, dict) and c.get("public") is True]

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
                        zendesk_throttle()
                        r = requests.get(content_url, auth=_auth(), timeout=30)
                        if r.status_code == 429:
                            raise ZendeskRateLimitError.from_response(
                                r, operation="download_attachment"
                            )
                        r.raise_for_status()
                        local_path = os.path.join(tmpdir, name)
                        with open(local_path, "wb") as f:
                            f.write(r.content)
                    except ZendeskRateLimitError:
                        raise
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


# MIME type mapping for unified agent's multimodal processor
MIME_TYPE_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
}


def convert_to_unified_attachments(
    att_list: List[AttachmentInfo],
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB limit to prevent memory issues
) -> List["Attachment"]:
    """Convert Zendesk attachments to unified agent Attachment model for multimodal processing.

    This enables images and PDFs to be processed by vision APIs (Gemini, Grok, OpenRouter),
    and log files to be fully inlined in context (up to 10MB).

    Args:
        att_list: List of AttachmentInfo objects from Zendesk
        max_bytes: Maximum file size to read (default 10MB)

    Returns:
        List of Attachment objects suitable for GraphState.attachments
    """
    import base64
    from app.agents.orchestration.orchestration.state import Attachment

    results: List[Attachment] = []

    # Supported types for multimodal processing
    # Images: Gemini, Grok 2 Vision, and many OpenRouter models support these
    # Text: Full log files inlined in context (Gemini/Grok have 1M+ token context)
    ALLOWED_TYPES = {
        # Images (vision)
        "image/png", "image/jpeg", "image/gif", "image/webp",
        # Documents (PDF vision)
        "application/pdf",
        # Text files (full content inline)
        "text/plain", "text/csv", "text/html", "text/markdown",
        "application/json", "application/xml",
        # Fallback for .log files detected by extension
        "application/octet-stream",
    }

    for att in att_list:
        if not att.local_path or not os.path.exists(att.local_path):
            continue

        # Check file size before reading to prevent memory issues
        if att.size and att.size > max_bytes:
            logger.warning(f"Skipping oversized attachment {att.file_name}: {att.size} bytes > {max_bytes} limit")
            continue

        # Get proper MIME type
        ext = os.path.splitext(att.file_name.lower())[1]
        mime_type = att.content_type or MIME_TYPE_MAP.get(ext, "application/octet-stream")

        # Handle .log files that might come as octet-stream
        if mime_type == "application/octet-stream" and ext in (".log", ".txt"):
            mime_type = "text/plain"

        if mime_type not in ALLOWED_TYPES:
            logger.debug(f"Skipping attachment {att.file_name} with unsupported MIME type: {mime_type}")
            continue

        try:
            with open(att.local_path, "rb") as f:
                content = f.read(max_bytes + 1)  # Read one extra byte to detect oversized files

            # Check actual file size (in case att.size was not set)
            if len(content) > max_bytes:
                logger.warning(f"Skipping oversized attachment {att.file_name}: file exceeds {max_bytes} byte limit")
                continue

            file_size = len(content)

            # Encode as base64 data URL
            b64_content = base64.b64encode(content).decode("utf-8")
            data_url = f"data:{mime_type};base64,{b64_content}"

            results.append(Attachment(
                name=att.file_name,
                mime_type=mime_type,
                data_url=data_url,
                size=att.size or file_size,
            ))
            size_mb = file_size / (1024 * 1024)
            logger.info(f"Converted attachment for multimodal: {att.file_name} ({mime_type}, {size_mb:.2f}MB)")

        except Exception as e:
            logger.warning(f"Failed to convert attachment {att.file_name}: {e}")
            continue

    return results
