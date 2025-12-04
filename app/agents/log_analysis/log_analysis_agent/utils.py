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
    text: str,
    *,
    pattern: str = r"\{.*?\}|\[.*?\]",
    fallback: Optional[T] = None,
    logger_instance: Optional[Any] = None,
) -> Optional[T]:
    """Extract and parse JSON from text, returning a fallback on failure."""
    logger = logger_instance or get_logger("log_analysis_utils")
    try:
        json_match = re.search(pattern, text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
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
