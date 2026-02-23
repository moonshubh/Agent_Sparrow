"""Helpers for Zendesk MB playbook memory imports."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional

LOG_LEVEL_RE = re.compile(
    r"\b(INFO|WARN|WARNING|ERROR|ERR|DEBUG|TRACE|FATAL|CRITICAL)\b", re.IGNORECASE
)
STACK_RE = re.compile(
    r"(Traceback \(most recent call last\):|^\s*at\s+\S+\(.*:\d+\))",
    re.MULTILINE,
)
ISO_TS_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:\d{2})?\b"
)
ERROR_KEYWORDS = (
    "error",
    "exception",
    "traceback",
    "fatal",
    "panic",
    "segmentation fault",
    "stack trace",
    "failed",
    "unable to",
    "could not",
)


def _is_error_start(line: str) -> bool:
    if not line:
        return False
    lowered = line.lower()
    if any(keyword in lowered for keyword in ERROR_KEYWORDS):
        return True
    if STACK_RE.search(line):
        return True
    if LOG_LEVEL_RE.search(line):
        return any(level in lowered for level in ("error", "err", "fatal", "critical"))
    return False


def _is_continuation_line(line: str) -> bool:
    if not line:
        return False
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(("at ", "...", "Caused by", "caused by")):
        return True
    if line.startswith((" ", "\t")):
        return True
    return bool(STACK_RE.search(line))


def _normalize_signature(line: str) -> str:
    if not line:
        return ""
    text = ISO_TS_RE.sub("", line)
    text = LOG_LEVEL_RE.sub("", text)
    text = re.sub(r"\b0x[0-9a-fA-F]+\b", "#", text)
    text = re.sub(r"\b[0-9a-fA-F]{8,}\b", "#", text)
    text = re.sub(r"\b\d+\b", "#", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text[:200]


def extract_log_errors(
    text: str,
    *,
    max_blocks: int = 8,
    max_block_lines: int = 30,
) -> List[Dict[str, Any]]:
    """Extract deterministic error blocks from log text."""
    if not text:
        return []

    lines = text.splitlines()
    raw_blocks: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not _is_error_start(line):
            i += 1
            continue
        start = i
        block_lines = [line]
        i += 1
        while i < len(lines) and len(block_lines) < max_block_lines:
            candidate = lines[i]
            if _is_continuation_line(candidate):
                block_lines.append(candidate)
                i += 1
                continue
            if ISO_TS_RE.search(candidate) and LOG_LEVEL_RE.search(candidate):
                break
            if not candidate.strip():
                i += 1
                break
            break
        raw_blocks.append(
            {
                "line_range": f"{start + 1}-{start + len(block_lines)}",
                "lines": block_lines,
            }
        )
        if len(raw_blocks) >= max_blocks:
            break

    aggregated: Dict[str, Dict[str, Any]] = {}
    for block in raw_blocks:
        lines = block.get("lines") or []
        first_line = lines[0] if lines else ""
        signature = _normalize_signature(first_line) or _normalize_signature(
            " ".join(lines[:2])
        )
        if not signature:
            continue
        record = aggregated.get(signature)
        if record is None:
            sample_lines = [ln for ln in lines if ln.strip()][:4]
            sample = "\n".join(sample_lines)[:800]
            aggregated[signature] = {
                "signature": signature,
                "count": 1,
                "first_line": first_line.strip()[:280],
                "sample": sample,
                "line_range": block.get("line_range"),
            }
        else:
            record["count"] += 1

    results = list(aggregated.values())
    results.sort(key=lambda item: item.get("count", 0), reverse=True)
    return results[:max_blocks]


def build_log_excerpt(
    errors: Iterable[Dict[str, Any]],
    fallback_text: str,
    *,
    max_chars: int = 6000,
) -> str:
    """Build a compact excerpt from extracted error blocks."""
    error_list = list(errors)
    if error_list:
        parts: List[str] = []
        for idx, error in enumerate(error_list[:4], start=1):
            line_range = error.get("line_range") or "unknown"
            sample = str(error.get("sample") or "").strip()
            if not sample:
                sample = str(error.get("first_line") or "").strip()
            if not sample:
                continue
            parts.append(f"[Error {idx} | lines {line_range}]")
            parts.append(sample)
        excerpt = "\n".join(parts).strip()
    else:
        excerpt = fallback_text.strip()

    if len(excerpt) > max_chars:
        return excerpt[: max_chars - 1].rstrip() + "…"
    return excerpt


def parse_summary_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json|JSON)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except Exception:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except Exception:
            return None
    return parsed if isinstance(parsed, dict) else None


def _as_list(value: Any, *, max_items: int = 10) -> List[str]:
    if value is None:
        return []
    items: List[str] = []
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [
            chunk.strip() for chunk in re.split(r"[\n;]+", value) if chunk.strip()
        ]
    else:
        raw_items = [str(value)]

    for item in raw_items:
        if item is None:
            continue
        text = str(item).strip().lstrip("-•*").strip()
        if text:
            items.append(text[:240])
        if len(items) >= max_items:
            break
    return items


def normalize_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "problem": str(summary.get("problem") or "").strip(),
        "impact": str(summary.get("impact") or "").strip(),
        "environment": str(summary.get("environment") or "").strip(),
        "symptoms": _as_list(summary.get("symptoms")),
        "timeline_steps": _as_list(summary.get("timeline_steps")),
        "actions_taken": _as_list(summary.get("actions_taken")),
        "errors": _as_list(summary.get("errors")),
        "resolution": str(summary.get("resolution") or "").strip(),
        "root_cause": str(summary.get("root_cause") or "").strip(),
        "contributing_factors": _as_list(summary.get("contributing_factors")),
        "prevention": _as_list(summary.get("prevention")),
        "follow_ups": _as_list(summary.get("follow_ups")),
        "key_settings": _as_list(summary.get("key_settings")),
        "log_error_summary": str(summary.get("log_error_summary") or "").strip(),
    }


def fallback_summary_from_text(
    text: str, *, subject: str | None = None
) -> Dict[str, Any]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    bullets = [
        ln.lstrip("-•* ").strip() for ln in lines if ln.startswith(("-", "•", "*"))
    ]
    if not bullets:
        bullets = [ln for ln in lines[:6]]
    return {
        "problem": subject or "Zendesk support ticket",
        "impact": "",
        "actions_taken": _as_list(bullets, max_items=8),
        "timeline_steps": [],
        "errors": [],
        "resolution": "",
        "root_cause": "",
        "contributing_factors": [],
        "prevention": [],
        "follow_ups": [],
    }


def format_zendesk_memory_content(
    summary: Dict[str, Any],
    *,
    subject: str,
    ticket_id: str,
    zendesk_url: str,
    log_errors: List[Dict[str, Any]],
    image_assets: List[Dict[str, Any]],
) -> str:
    lines: List[str] = []
    problem = summary.get("problem") or subject or "Zendesk support ticket"
    lines.append(f"Problem: {problem}")

    impact = summary.get("impact")
    if impact:
        lines.append(f"Impact: {impact}")

    environment = summary.get("environment")
    if environment:
        lines.append(f"Environment: {environment}")

    symptoms = summary.get("symptoms") or []
    if symptoms:
        lines.append("")
        lines.append("### Symptoms")
        lines.extend([f"- {item}" for item in symptoms])

    errors = summary.get("errors") or []
    log_error_summary = str(summary.get("log_error_summary") or "").strip()
    if log_error_summary and log_error_summary not in errors:
        errors = [*errors, log_error_summary]
    if errors:
        lines.append("")
        lines.append("### Errors")
        lines.extend([f"- {item}" for item in errors])

    resolution = summary.get("resolution")
    if resolution:
        lines.append("")
        lines.append(f"### Resolution\n{resolution}")

    root_cause = summary.get("root_cause")
    if root_cause:
        lines.append("")
        lines.append(f"### Root Cause\n{root_cause}")

    if image_assets:
        lines.append("")
        lines.append("### Images")
        for asset in image_assets:
            bucket = asset.get("bucket")
            path = asset.get("path")
            name = asset.get("file_name") or "attachment"
            if bucket and path:
                lines.append(f"- {name}")
                lines.append(f"![{name}](memory-asset://{bucket}/{path})")

    if ticket_id:
        lines.append("")
        lines.append("### Zendesk")
        lines.append(f"- Ticket: {ticket_id}")
    if zendesk_url:
        lines.append(f"- URL: {zendesk_url}")

    return "\n".join(lines).strip()


def build_zendesk_embedding_context(
    summary: Dict[str, Any],
    *,
    subject: str,
    ticket_id: str,
    zendesk_url: str,
    log_errors: List[Dict[str, Any]],
    log_findings: List[Dict[str, Any]],
    max_chars: int = 20000,
) -> str:
    """Build enriched embedding text while keeping UI-visible markdown concise.

    This payload intentionally includes detail-rich sections (including those
    hidden from visible markdown) to preserve retrieval quality for semantic
    search.
    """

    def _as_items(values: Any, *, max_items: int = 12) -> List[str]:
        if isinstance(values, list):
            raw = values
        elif isinstance(values, str):
            raw = [values]
        else:
            raw = []
        cleaned: List[str] = []
        for value in raw:
            text = str(value or "").strip()
            if text:
                cleaned.append(text[:500])
            if len(cleaned) >= max_items:
                break
        return cleaned

    lines: List[str] = []

    problem = str(summary.get("problem") or "").strip() or subject or "Zendesk support ticket"
    lines.append(f"Problem: {problem}")

    impact = str(summary.get("impact") or "").strip()
    if impact:
        lines.append(f"Impact: {impact}")

    environment = str(summary.get("environment") or "").strip()
    if environment:
        lines.append(f"Environment: {environment}")

    core_sections = [
        ("Symptoms", _as_items(summary.get("symptoms"))),
        ("Actions Taken", _as_items(summary.get("actions_taken"))),
        ("Timeline", _as_items(summary.get("timeline_steps"))),
        ("Errors", _as_items(summary.get("errors"))),
        ("Contributing Factors", _as_items(summary.get("contributing_factors"))),
        ("Prevention", _as_items(summary.get("prevention"))),
        ("Follow-ups", _as_items(summary.get("follow_ups"))),
        ("Key Settings", _as_items(summary.get("key_settings"))),
    ]
    for title, items in core_sections:
        if not items:
            continue
        lines.append("")
        lines.append(f"{title}:")
        for item in items:
            lines.append(f"- {item}")

    resolution = str(summary.get("resolution") or "").strip()
    if resolution:
        lines.append("")
        lines.append("Resolution:")
        lines.append(resolution)

    root_cause = str(summary.get("root_cause") or "").strip()
    if root_cause:
        lines.append("")
        lines.append("Root Cause:")
        lines.append(root_cause)

    log_error_summary = str(summary.get("log_error_summary") or "").strip()
    if log_error_summary:
        lines.append("")
        lines.append("Log Error Summary:")
        lines.append(log_error_summary)

    if log_errors:
        lines.append("")
        lines.append("Log Error Signatures:")
        for entry in log_errors[:8]:
            label = str(entry.get("first_line") or entry.get("signature") or "").strip()
            if not label:
                continue
            count = int(entry.get("count") or 1)
            file_name = str(entry.get("file_name") or "").strip()
            prefix = f"{file_name}: " if file_name else ""
            lines.append(f"- {prefix}{label} (x{count})")

    if log_findings:
        lines.append("")
        lines.append("Log Findings:")
        for finding in log_findings[:8]:
            file_name = str(finding.get("file_name") or "").strip()
            summary_text = str(finding.get("summary") or "").strip()
            if not summary_text:
                continue
            prefix = f"{file_name}: " if file_name else ""
            lines.append(f"- {prefix}{summary_text}")

    if ticket_id or zendesk_url:
        lines.append("")
        lines.append("Zendesk:")
        if ticket_id:
            lines.append(f"- Ticket: {ticket_id}")
        if zendesk_url:
            lines.append(f"- URL: {zendesk_url}")

    text = "\n".join(lines).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def redact_pii_preserving_assets(text: str) -> str:
    """Redact PII while preserving memory-asset URLs."""
    if not text:
        return text
    from app.security.pii_redactor import redact_pii

    placeholders: Dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        key = f"__ASSET_LINK_{len(placeholders)}__"
        placeholders[key] = match.group(0)
        return key

    masked = re.sub(r"memory-asset://[^\s)]+", _replace, text)
    redacted = redact_pii(masked)
    for key, value in placeholders.items():
        redacted = redacted.replace(key, value)
    return redacted
