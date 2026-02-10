from __future__ import annotations

import re


_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]{1,})@([A-Za-z0-9.-]{1,})")
_PHONE_RE = re.compile(
    r"(?<!\d)(\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?){2}\d{4}(?!\d)"
)

# Common order-reference token forms seen in Zendesk billing tickets.
_ORDER_TOKEN_RE = re.compile(
    r"(?i)\b(?=[A-Z0-9\[\]_-]*\d)MAI(?:\[[^\]]+\]|[A-Z0-9]{2,})?(?:[-_][A-Z0-9]{2,})+\b"
)

# Label + token capture for contextual replacement.
_ORDER_LABELED_RE = re.compile(
    r"(?is)\b(?P<label>"
    r"order(?:\s*(?:id|number|no\.?|reference|ref\.?))?|"
    r"transaction(?:\s*(?:id|number|reference|ref\.?))?|"
    r"purchase(?:\s*(?:id|number|reference|ref\.?))?"
    r")\s*(?:[:#-]|\bis\b|\bwas\b)?\s*(?P<token>"
    r"(?=[A-Z0-9\[\]_-]{6,})(?=[A-Z0-9\[\]_-]*\d)[A-Z0-9\[\]_-]+)"
)

_TRANSACTION_CONTEXT_RE = re.compile(r"(?i)\b(transaction|txn)\b")
_PURCHASE_CONTEXT_RE = re.compile(r"(?i)\b(purchase|bought|buy)\b")
_ORDER_CONTEXT_RE = re.compile(
    r"(?i)\b(order|billing|invoice|refund|subscription|charge)\b"
)


def _redact_basic_pii(text: str) -> str:
    redacted = _EMAIL_RE.sub(lambda m: f"{m.group(1)[:2]}***@{m.group(2)}", text)
    redacted = _PHONE_RE.sub("[redacted-phone]", redacted)
    return redacted


def _contextual_reference_phrase(context: str) -> str:
    if _TRANSACTION_CONTEXT_RE.search(context):
        return "the transaction reference you shared"
    if _PURCHASE_CONTEXT_RE.search(context):
        return "the purchase reference you shared"
    if _ORDER_CONTEXT_RE.search(context):
        return "the order reference you shared"
    return "the reference details you shared"


def _replace_labeled_order_reference(match: re.Match[str]) -> str:
    label = str(match.group("label") or "")
    return _contextual_reference_phrase(label)


def contains_order_reference_token(text: str) -> bool:
    if not text:
        return False
    if _ORDER_TOKEN_RE.search(text):
        return True
    return bool(_ORDER_LABELED_RE.search(text))


def sanitize_order_references(text: str) -> str:
    if not text:
        return text
    sanitized = _ORDER_LABELED_RE.sub(_replace_labeled_order_reference, text)

    # Replace standalone MAI-like references while preserving sentence flow.
    def _replace_token(match: re.Match[str]) -> str:
        span_start, span_end = match.span()
        window_start = max(0, span_start - 64)
        window_end = min(len(sanitized), span_end + 64)
        context = sanitized[window_start:window_end]
        return _contextual_reference_phrase(context)

    sanitized = _ORDER_TOKEN_RE.sub(_replace_token, sanitized)
    return sanitized


def sanitize_zendesk_ticket_text(text: str) -> str:
    if not text:
        return ""
    return sanitize_order_references(_redact_basic_pii(str(text)))
