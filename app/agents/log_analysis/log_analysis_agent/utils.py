"""
Shared utilities for log analysis and security helpers.

Provides small, dependency-light functions to parse JSON payloads from
LLM responses or user input and to slice log sections from line ranges.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, TypeVar

from app.core.logging_config import get_logger

from .simplified_schemas import LogSection

# Generic type for JSON extraction fallbacks
T = TypeVar("T")


def extract_json_payload(
    text: Any,
    *,
    pattern: str = r"\{.*?\}|\[.*?\]",
    fallback: Optional[T] = None,
    logger_instance: Optional[Any] = None,
) -> Optional[T]:
    """Extract and parse JSON from text, returning a fallback on failure."""
    logger = logger_instance or get_logger("log_analysis_utils")

    expected_type: Optional[type] = None
    if "\\[" in pattern and "\\{" not in pattern:
        expected_type = list
    elif "\\{" in pattern and "\\[" not in pattern:
        expected_type = dict

    # Handle already-parsed content (e.g. some chat model content blocks).
    if expected_type and isinstance(text, expected_type):
        return text
    if expected_type is None and isinstance(text, (dict, list)):
        return text  # type: ignore[return-value]

    def _strip_code_fences(raw: str) -> str:
        stripped = (raw or "").strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*```\s*$", "", stripped)
        return stripped.strip()

    def _extract_balanced(block: str, start_idx: int, opener: str, closer: str) -> Optional[str]:
        depth = 0
        in_string = False
        escape = False
        for idx in range(start_idx, len(block)):
            ch = block[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return block[start_idx : idx + 1]
        return None

    raw_text: str
    if text is None:
        return fallback
    if isinstance(text, str):
        raw_text = text
    elif isinstance(text, (bytes, bytearray)):
        raw_text = bytes(text).decode("utf-8", errors="ignore")
    elif isinstance(text, list):
        parts: list[str] = []
        for item in text:
            if isinstance(item, str) and item.strip():
                parts.append(item)
                continue
            if isinstance(item, dict):
                maybe_text = item.get("text") or item.get("content")
                if isinstance(maybe_text, str) and maybe_text.strip():
                    parts.append(maybe_text)
        raw_text = "\n".join(parts) if parts else str(text)
    else:
        raw_text = str(text)

    cleaned = _strip_code_fences(raw_text)

    # Fast path: response is already valid JSON (common when using JSON mime type).
    try:
        parsed_full = json.loads(cleaned)
        if expected_type is None or isinstance(parsed_full, expected_type):
            return parsed_full
    except json.JSONDecodeError:
        pass

    # Prefer balanced-bracket extraction over regex to handle nested JSON.
    bracket_order = [("{", "}", dict), ("[", "]", list)]
    if expected_type is list:
        bracket_order = [("[", "]", list), ("{", "}", dict)]
    elif expected_type is dict:
        bracket_order = [("{", "}", dict), ("[", "]", list)]

    for opener, closer, kind in bracket_order:
        start = cleaned.find(opener)
        attempts = 0
        while start >= 0 and attempts < 6:
            attempts += 1
            blob = _extract_balanced(cleaned, start, opener, closer)
            if blob:
                try:
                    parsed = json.loads(blob)
                    if expected_type is None or isinstance(parsed, expected_type):
                        return parsed
                except json.JSONDecodeError as exc:
                    logger.debug(f"JSON extraction failed: {exc}")
            start = cleaned.find(opener, start + 1)

    # Fallback to regex-based extraction (legacy behavior)
    try:
        json_match = re.search(pattern, cleaned, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            if expected_type is None or isinstance(parsed, expected_type):
                return parsed
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.debug(f"JSON extraction failed: {exc}")
    return fallback


def build_log_sections_from_ranges(
    sections_data: List[Dict[str, Any]],
    log_content: str,
    *,
    max_sections: int,
    logger_instance: Optional[Any] = None,
) -> List[LogSection]:
    """
    Convert JSON section metadata into LogSection objects with safe bounds.

    Args:
        sections_data: Parsed JSON list containing line_range keys.
        log_content: Full log content to slice.
        max_sections: Maximum sections to return.
        logger_instance: Optional logger for debug messages.
    """
    logger = logger_instance or get_logger("log_analysis_utils")
    lines = log_content.splitlines()
    sections: List[LogSection] = []

    for section in sections_data[:max_sections]:
        line_range = str(section.get("line_range", "1-10"))
        try:
            start, end = map(int, line_range.split("-"))
            if start < 1 or end < start:
                logger.debug(f"Invalid line range: {line_range}")
                continue
            start = max(0, start - 1)
            end = min(len(lines), end)

            sections.append(
                LogSection(
                    line_numbers=line_range,
                    content="\n".join(lines[start:end]),
                    relevance_score=0.9,
                )
            )
        except (ValueError, AttributeError):
            logger.debug(f"Invalid line range: {line_range}")
            continue

    return sections
