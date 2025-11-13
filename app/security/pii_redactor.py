"""Lightweight PII detection and redaction helpers."""

from __future__ import annotations

import re
from typing import Any, Iterable

EMAIL_PATTERN = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}")
IPV4_PATTERN = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
IPV6_PATTERN = re.compile(r"\b(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}\b", re.IGNORECASE)
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def contains_pii(text: str) -> bool:
    """Return True if the string contains recognizable PII tokens."""

    if not text:
        return False
    return any(pattern.search(text) for pattern in _patterns())


def redact_pii(text: str) -> str:
    """Redact email, phone, IP, and card-like sequences in the text."""

    if not text:
        return text

    redacted = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    redacted = PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)
    redacted = IPV4_PATTERN.sub("[REDACTED_IP]", redacted)
    redacted = IPV6_PATTERN.sub("[REDACTED_IP]", redacted)
    redacted = CREDIT_CARD_PATTERN.sub("[REDACTED_CARD]", redacted)
    return redacted


def redact_pii_from_dict(data: Any) -> Any:
    """Walk nested structures and redact PII from all string leaves."""

    if isinstance(data, dict):
        return {key: redact_pii_from_dict(value) for key, value in data.items()}
    if isinstance(data, list):
        return [redact_pii_from_dict(item) for item in data]
    if isinstance(data, tuple):
        return tuple(redact_pii_from_dict(item) for item in data)
    if isinstance(data, str):
        return redact_pii(data)
    return data


def _patterns() -> Iterable[re.Pattern[str]]:
    return (EMAIL_PATTERN, PHONE_PATTERN, IPV4_PATTERN, IPV6_PATTERN, CREDIT_CARD_PATTERN)
