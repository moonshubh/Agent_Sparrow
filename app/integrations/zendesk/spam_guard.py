from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

from app.core.logging_config import get_logger
from app.agents.unified.minimax_tools import (
    is_minimax_available,
    minimax_understand_image_tool,
)
from .attachments import AttachmentInfo, cleanup_attachments, fetch_ticket_attachments

logger = get_logger(__name__)


SHORTENER_DOMAINS: set[str] = {
    "bit.ly",
    "t.co",
    "tinyurl.com",
    "shorturl.at",
    "goo.gl",
    "ow.ly",
    "buff.ly",
    "is.gd",
    "rb.gy",
    "cutt.ly",
    "tiny.cc",
    "trib.al",
    "lnkd.in",
}

EXPLICIT_TEXT_PATTERN = re.compile(
    r"("
    r"s[\W_]*e[\W_]*x|"
    r"n[\W_]*u[\W_]*d[\W_]*e|"
    r"p[\W_]*o[\W_]*r[\W_]*n|"
    r"naughty|"
    r"hook\s*up|"
    r"escort|"
    r"xxx|"
    r"blowjob|"
    r"onlyfans|"
    r"explicit"
    r")",
    flags=re.IGNORECASE,
)

URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")


@dataclass(frozen=True)
class SpamGuardDecision:
    skip: bool
    reason: str | None
    details: dict[str, Any]
    tag: str
    note: str


def _extract_original_recipients_count(
    ticket: dict[str, Any] | None,
    comments: Iterable[dict[str, Any]] | None = None,
) -> int:
    t = ticket or {}
    via = t.get("via") if isinstance(t.get("via"), dict) else {}
    source = via.get("source") if isinstance(via, dict) else {}
    from_obj = source.get("from") if isinstance(source, dict) else {}
    recipients = from_obj.get("original_recipients")
    if isinstance(recipients, list):
        count = len([r for r in recipients if isinstance(r, str) and r.strip()])
        if count:
            return count

    if comments:
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            via = comment.get("via") if isinstance(comment.get("via"), dict) else {}
            source = via.get("source") if isinstance(via, dict) else {}
            from_obj = source.get("from") if isinstance(source, dict) else {}
            recipients = from_obj.get("original_recipients")
            if isinstance(recipients, list):
                count = len([r for r in recipients if isinstance(r, str) and r.strip()])
                if count:
                    return count
    return 0


def _extract_text(ticket: dict[str, Any] | None) -> str:
    t = ticket or {}
    subject = str(t.get("subject") or "").strip()
    description = str(t.get("description") or "").strip()
    if subject and description:
        return f"{subject}\n\n{description}"
    return subject or description


def _normalize_url(url: str) -> str:
    return url.rstrip(".,;:!?)\"'")


def _extract_shortlink_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not text:
        return counts
    for raw in URL_PATTERN.findall(text):
        url = _normalize_url(raw)
        parsed = urlparse(url)
        domain = (parsed.netloc or "").lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if not domain or domain not in SHORTENER_DOMAINS:
            continue
        counts[url] = counts.get(url, 0) + 1
    return counts


def _contains_explicit_solicitation(text: str) -> bool:
    if not text:
        return False
    return bool(EXPLICIT_TEXT_PATTERN.search(text))


def _summarize_repeated_shortlinks(counts: dict[str, int]) -> dict[str, Any]:
    repeated = {u: c for u, c in counts.items() if c >= 2}
    domains = set()
    for url in repeated.keys():
        parsed = urlparse(url)
        domain = (parsed.netloc or "").lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain:
            domains.add(domain)
    return {
        "repeated_shortlink": bool(repeated),
        "repeated_shortlink_count": len(repeated),
        "shortlink_domains": sorted(domains),
    }


def _make_thumbnail_path(image_path: str, *, max_size: int = 512) -> str | None:
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            img.thumbnail((max_size, max_size))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp.close()
            img.save(tmp.name, format="JPEG", quality=70, optimize=True)
            return tmp.name
    except (UnidentifiedImageError, OSError) as exc:
        logger.debug("spam_guard_thumbnail_failed", error=str(exc)[:180])
        return None


def _parse_minimax_classification(payload: Any) -> tuple[str, float]:
    if isinstance(payload, dict):
        text = payload.get("analysis") or ""
    else:
        text = str(payload or "")

    match = re.search(r"\{[^{}]*\}", text)
    if not match:
        return "uncertain", 0.0
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, TypeError):
        return "uncertain", 0.0
    label = str(data.get("label") or "uncertain").strip().lower()
    confidence = data.get("confidence")
    try:
        confidence_val = float(confidence)
    except (TypeError, ValueError):
        confidence_val = 0.0
    if label not in {"explicit_adult", "suggestive", "benign", "uncertain"}:
        label = "uncertain"
    confidence_val = max(0.0, min(1.0, confidence_val))
    return label, confidence_val


async def _classify_explicit_images(
    ticket_id: int | str,
    attachments: Iterable[AttachmentInfo],
) -> tuple[str, float]:
    if not is_minimax_available():
        return "uncertain", 0.0

    for att in attachments:
        if not att.local_path:
            continue
        lower = att.file_name.lower()
        if not lower.endswith((".png", ".jpg", ".jpeg")):
            continue
        thumb_path = _make_thumbnail_path(att.local_path)
        if not thumb_path:
            continue
        try:
            prompt = (
                "Classify the image content. Respond with ONLY valid JSON in this format: "
                "{\"label\":\"explicit_adult|suggestive|benign|uncertain\","
                "\"confidence\":0.0-1.0}. Do not add any other text."
            )
            result = await minimax_understand_image_tool(
                prompt=prompt,
                image_url=thumb_path,
            )
            label, confidence = _parse_minimax_classification(result)
            logger.info(
                "spam_guard_image_classification",
                ticket_id=ticket_id,
                label=label,
                confidence=confidence,
            )
            if label == "explicit_adult" and confidence >= 0.9:
                return label, confidence
        finally:
            try:
                Path(thumb_path).unlink(missing_ok=True)
            except OSError as exc:
                logger.debug("spam_guard_thumbnail_cleanup_failed", error=str(exc)[:180])

    return "uncertain", 0.0


async def evaluate_spam_guard(
    *,
    ticket_id: int | str,
    ticket: dict[str, Any] | None,
    comments: list[dict[str, Any]] | None = None,
) -> SpamGuardDecision | None:
    text = _extract_text(ticket)
    recipients_count = _extract_original_recipients_count(ticket, comments)
    shortlink_counts = _extract_shortlink_counts(text)
    shortlink_summary = _summarize_repeated_shortlinks(shortlink_counts)
    explicit_text = _contains_explicit_solicitation(text)

    if recipients_count < 5:
        return None

    if shortlink_summary["repeated_shortlink"] or explicit_text:
        details = {
            "recipient_count": recipients_count,
            "explicit_text": explicit_text,
            **shortlink_summary,
        }
        return SpamGuardDecision(
            skip=True,
            reason="spam_guard",
            details=details,
            tag="mb_spam_suspected",
            note="Suspected spam content detected. No response was generated. Please review.",
        )

    # If no strong text signal, look for explicit image content.
    if not is_minimax_available():
        return None
    attachments: list[AttachmentInfo] = []
    try:
        attachments = fetch_ticket_attachments(
            ticket_id,
            allowed_extensions=(".png", ".jpg", ".jpeg"),
            max_bytes=3 * 1024 * 1024,
            public_only=True,
        )
        label, confidence = await _classify_explicit_images(ticket_id, attachments)
    finally:
        if attachments:
            cleanup_attachments(attachments)

    if label == "explicit_adult" and confidence >= 0.9:
        details = {
            "recipient_count": recipients_count,
            "explicit_text": explicit_text,
            "explicit_image_label": label,
            "explicit_image_confidence": confidence,
            **shortlink_summary,
        }
        return SpamGuardDecision(
            skip=True,
            reason="spam_guard_explicit_image",
            details=details,
            tag="mb_spam_suspected",
            note="Suspected spam content detected. No response was generated. Please review.",
        )

    return None
