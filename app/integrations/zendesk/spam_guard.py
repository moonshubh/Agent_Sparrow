from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

from app.agents.unified.minimax_tools import (
    is_minimax_available,
    minimax_understand_image_tool,
)
from app.core.logging_config import get_logger
from app.core.settings import settings
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
    r"explicit|"
    r"fuck|"
    r"boob(?:s)?|"
    r"dick|"
    r"cock|"
    r"grann(?:y|ies)|"
    r"craigslist|"
    r"dating"
    r")",
    flags=re.IGNORECASE,
)

EXPLICIT_EMOJI_PATTERN = re.compile(r"[💋🍑🍆🔞]")
URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")
SUPPORT_INTENT_PATTERN = re.compile(
    r"(?i)\b("
    r"mailbird|support|help|issue|problem|error|cannot|can't|won't|"
    r"sync|login|smtp|imap|oauth|password|refund|billing|license|subscription|"
    r"account|inbox|email|install|update|crash|bug"
    r")\b"
)


@dataclass(frozen=True)
class SpamGuardDecision:
    skip: bool
    reason: str | None
    details: dict[str, Any]
    tag: str
    note: str
    reason_tag: str | None = None


def _extract_original_recipients_count(
    ticket: dict[str, Any] | None,
    comments: Iterable[dict[str, Any]] | None = None,
) -> int:
    t = ticket or {}
    via_val = t.get("via")
    via = via_val if isinstance(via_val, dict) else {}
    source = via.get("source")
    if not isinstance(source, dict):
        source = {}
    from_obj = source.get("from")
    if not isinstance(from_obj, dict):
        from_obj = {}
    recipients = from_obj.get("original_recipients")
    if isinstance(recipients, list):
        count = len([r for r in recipients if isinstance(r, str) and r.strip()])
        if count:
            return count

    if comments:
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            via_val = comment.get("via")
            via = via_val if isinstance(via_val, dict) else {}
            source = via.get("source")
            if not isinstance(source, dict):
                source = {}
            from_obj = source.get("from")
            if not isinstance(from_obj, dict):
                from_obj = {}
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


def _contains_explicit_emoji(text: str) -> bool:
    if not text:
        return False
    return bool(EXPLICIT_EMOJI_PATTERN.search(text))


def _ticket_has_support_intent(text: str) -> bool:
    if not text:
        return False
    return bool(SUPPORT_INTENT_PATTERN.search(text))


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


def _domain_is_high_risk(domain: str, extra_suffixes: Iterable[str]) -> bool:
    candidate = (domain or "").lower().strip()
    if not candidate:
        return False
    if candidate in SHORTENER_DOMAINS:
        return True
    for raw in extra_suffixes:
        suffix = str(raw or "").lower().strip().lstrip(".")
        if not suffix:
            continue
        if candidate == suffix or candidate.endswith(f".{suffix}"):
            return True
    return False


def _extract_url_signals(text: str) -> dict[str, Any]:
    urls: list[str] = []
    domain_counts: Counter[str] = Counter()
    high_risk_domains: set[str] = set()
    shortlink_counts = _extract_shortlink_counts(text)
    extra_risk_suffixes = getattr(
        settings,
        "zendesk_spam_high_risk_domain_suffixes",
        [],
    )

    for raw in URL_PATTERN.findall(text or ""):
        url = _normalize_url(raw)
        if not url:
            continue
        urls.append(url)
        parsed = urlparse(url)
        domain = (parsed.netloc or "").lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if not domain:
            continue
        domain_counts[domain] += 1
        if _domain_is_high_risk(domain, extra_risk_suffixes):
            high_risk_domains.add(domain)

    url_counts = Counter(urls)
    repeated_urls = {url: c for url, c in url_counts.items() if c >= 2}
    top_domains = [domain for domain, _ in domain_counts.most_common(5)]

    return {
        "external_link_count": len(urls),
        "repeated_url_count": len(repeated_urls),
        "high_risk_domain_count": len(high_risk_domains),
        "high_risk_domains": sorted(high_risk_domains),
        "top_link_domains": top_domains,
        **_summarize_repeated_shortlinks(shortlink_counts),
    }


def _make_thumbnail_path(image_path: str, *, max_size: int = 512) -> str | None:
    try:
        with Image.open(image_path) as img:
            converted = img.convert("RGB")
            converted.thumbnail((max_size, max_size))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp.close()
            converted.save(tmp.name, format="JPEG", quality=70, optimize=True)
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
                '{"label":"explicit_adult|suggestive|benign|uncertain",'
                '"confidence":0.0-1.0}. Do not add any other text.'
            )
            result = await minimax_understand_image_tool.ainvoke(
                {
                    "prompt": prompt,
                    "image_url": thumb_path,
                }
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
                logger.debug(
                    "spam_guard_thumbnail_cleanup_failed", error=str(exc)[:180]
                )

    return "uncertain", 0.0


async def _evaluate_baseline_guard(
    *,
    ticket_id: int | str,
    ticket: dict[str, Any] | None,
    comments: list[dict[str, Any]] | None,
) -> SpamGuardDecision | None:
    """Compatibility path used when strict guard is disabled."""
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
            "spam_score": 1.0 if explicit_text else 0.85,
            "spam_signals": {
                "explicit_text": explicit_text,
                "repeated_shortlink": shortlink_summary["repeated_shortlink"],
            },
            "spam_reason_tag": (
                "mb_spam_explicit_link" if explicit_text else "mb_spam_suspicious_link"
            ),
            "top_link_domains": shortlink_summary.get("shortlink_domains") or [],
            **shortlink_summary,
        }
        return SpamGuardDecision(
            skip=True,
            reason="spam_guard",
            details=details,
            tag="mb_spam_suspected",
            reason_tag=str(details["spam_reason_tag"]),
            note="Suspected spam content detected. No response was generated. Please review.",
        )

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
            "spam_score": 1.0,
            "spam_signals": {
                "explicit_image": True,
            },
            "spam_reason_tag": "mb_spam_explicit_image",
            "top_link_domains": shortlink_summary.get("shortlink_domains") or [],
            **shortlink_summary,
        }
        return SpamGuardDecision(
            skip=True,
            reason="spam_guard_explicit_image",
            details=details,
            tag="mb_spam_suspected",
            reason_tag="mb_spam_explicit_image",
            note="Suspected spam content detected. No response was generated. Please review.",
        )
    return None


def _score_spam(
    *,
    text: str,
    recipients_count: int,
    url_signals: dict[str, Any],
    explicit_text: bool,
    explicit_emoji: bool,
) -> tuple[float, dict[str, Any]]:
    support_intent = _ticket_has_support_intent(text)
    word_count = len(re.findall(r"[A-Za-z0-9]{2,}", text or ""))
    low_support_intent = (not support_intent) and word_count <= 120
    recipient_burst_threshold = int(
        getattr(settings, "zendesk_spam_recipient_burst_threshold", 20)
    )
    recipient_burst = recipients_count >= recipient_burst_threshold
    repeated_url = bool(url_signals.get("repeated_url_count"))
    high_risk_domain = bool(url_signals.get("high_risk_domain_count"))
    external_link = bool(url_signals.get("external_link_count"))
    suspicious_link = external_link and (
        high_risk_domain or repeated_url or low_support_intent
    )

    score = 0.0
    if explicit_text:
        score += 0.45
    if explicit_emoji:
        score += 0.15
    if high_risk_domain:
        score += 0.3
    if repeated_url:
        score += 0.2
    if recipient_burst:
        score += 0.3
    if low_support_intent:
        score += 0.1
    if suspicious_link:
        score += 0.15

    score = max(0.0, min(1.0, score))
    signals = {
        "explicit_text": explicit_text,
        "explicit_emoji": explicit_emoji,
        "recipient_burst": recipient_burst,
        "support_intent": support_intent,
        "low_support_intent": low_support_intent,
        "high_risk_domain": high_risk_domain,
        "repeated_url": repeated_url,
        "external_link": external_link,
        "suspicious_link": suspicious_link,
    }
    return score, signals


def _reason_tag_from_signals(signals: dict[str, Any], *, explicit_link: bool) -> str:
    if explicit_link:
        return "mb_spam_explicit_link"
    if bool(signals.get("recipient_burst")) and (
        bool(signals.get("external_link")) or bool(signals.get("high_risk_domain"))
    ):
        return "mb_spam_recipient_burst"
    return "mb_spam_suspicious_link"


async def evaluate_spam_guard(
    *,
    ticket_id: int | str,
    ticket: dict[str, Any] | None,
    comments: list[dict[str, Any]] | None = None,
) -> SpamGuardDecision | None:
    strict_enabled = bool(getattr(settings, "zendesk_spam_guard_strict_enabled", True))
    if not strict_enabled:
        return await _evaluate_baseline_guard(
            ticket_id=ticket_id,
            ticket=ticket,
            comments=comments,
        )

    text = _extract_text(ticket)
    recipients_count = _extract_original_recipients_count(ticket, comments)
    url_signals = _extract_url_signals(text)
    explicit_text = _contains_explicit_solicitation(text)
    explicit_emoji = _contains_explicit_emoji(text)
    explicit_content = explicit_text or explicit_emoji
    external_link = int(url_signals.get("external_link_count") or 0) > 0
    block_explicit_link = bool(
        getattr(settings, "zendesk_spam_always_block_explicit_link", True)
    )

    score, signals = _score_spam(
        text=text,
        recipients_count=recipients_count,
        url_signals=url_signals,
        explicit_text=explicit_text,
        explicit_emoji=explicit_emoji,
    )
    details: dict[str, Any] = {
        "recipient_count": recipients_count,
        "spam_score": score,
        "spam_signals": signals,
        "top_link_domains": url_signals.get("top_link_domains") or [],
        **url_signals,
    }

    if block_explicit_link and explicit_content and external_link:
        reason_tag = "mb_spam_explicit_link"
        details["spam_reason_tag"] = reason_tag
        return SpamGuardDecision(
            skip=True,
            reason="spam_guard",
            details=details,
            tag="mb_spam_suspected",
            reason_tag=reason_tag,
            note="Suspected spam content detected. No response was generated. Please review.",
        )

    attachments: list[AttachmentInfo] = []
    label = "uncertain"
    confidence = 0.0
    if is_minimax_available():
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
        details["explicit_image_label"] = label
        details["explicit_image_confidence"] = confidence
        details["spam_reason_tag"] = "mb_spam_explicit_image"
        details["spam_signals"] = {**signals, "explicit_image": True}
        return SpamGuardDecision(
            skip=True,
            reason="spam_guard_explicit_image",
            details=details,
            tag="mb_spam_suspected",
            reason_tag="mb_spam_explicit_image",
            note="Suspected spam content detected. No response was generated. Please review.",
        )

    threshold = float(getattr(settings, "zendesk_spam_score_threshold", 0.65))
    if score >= threshold:
        reason_tag = _reason_tag_from_signals(
            signals, explicit_link=(explicit_content and external_link)
        )
        details["spam_reason_tag"] = reason_tag
        return SpamGuardDecision(
            skip=True,
            reason="spam_guard",
            details=details,
            tag="mb_spam_suspected",
            reason_tag=reason_tag,
            note="Suspected spam content detected. No response was generated. Please review.",
        )

    return None
