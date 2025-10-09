"""Utility helpers for grounded primary agent responses."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

URL_PATTERN = re.compile(r"https?://\S+")
CITATION_PATTERN = re.compile(r"\[\d+\]")


def sanitize_model_response(text: str) -> str:
    """Remove visible URLs, citation markers, and trailing source blocks."""

    if not text:
        return text

    cleaned = URL_PATTERN.sub("", text)
    cleaned = CITATION_PATTERN.sub("", cleaned)
    # Drop trailing Sources sections
    cleaned = re.sub(r"\n+sources?:\n.*", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    # Collapse extra whitespace introduced by removals
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+\n", "\n", cleaned)
    return cleaned.strip()


def kb_retrieval_satisfied(
    summary: Optional[Any],
    *,
    min_results: int,
    min_relevance: float,
) -> bool:
    """Check whether KB evidence meets configured thresholds."""

    if summary is None:
        return False

    total_results = getattr(summary, "total_results", 0)
    avg_relevance = getattr(summary, "avg_relevance", 0.0)
    if total_results < min_results:
        return False
    return avg_relevance >= min_relevance


def _clean_snippet(text: str, max_chars: int) -> str:
    if not text:
        return ""
    sanitized = sanitize_model_response(text)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if len(sanitized) <= max_chars:
        return sanitized
    return sanitized[: max_chars - 1].rstrip() + "…"


def summarize_kb_results(
    results: List[Dict[str, Any]],
    *,
    max_items: int = 3,
    max_chars: int = 320,
) -> List[Dict[str, str]]:
    """Take raw KB results and return compact title/snippet pairs."""

    summary: List[Dict[str, str]] = []
    for item in results[:max_items]:
        title = item.get("title") or "Knowledge Item"
        snippet = item.get("content") or item.get("metadata", {}).get("summary") or ""
        summary.append(
            {
                "title": title,
                "source": item.get("source", "knowledge_base"),
                "snippet": _clean_snippet(snippet, max_chars),
            }
        )
    return summary


def summarize_tavily_results(
    results: List[Dict[str, Any]],
    *,
    max_items: int = 3,
    max_chars: int = 240,
) -> List[Dict[str, str]]:
    """Compact Tavily results to title/snippet pairs without URLs."""

    summary: List[Dict[str, str]] = []
    for item in results[:max_items]:
        title = item.get("title") or "Result"
        snippet = item.get("snippet") or item.get("content") or ""
        summary.append(
            {
                "title": title,
                "snippet": _clean_snippet(snippet, max_chars),
            }
        )
    return summary


def build_grounding_digest(
    kb_items: List[Dict[str, str]],
    tavily_items: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Create a textual digest for prompts or logging from evidence lists."""

    sections: List[str] = []

    if kb_items:
        sections.append("Knowledge Base Evidence:")
        for item in kb_items:
            snippet = item.get("snippet", "").strip()
            sections.append(f"- {item.get('title')}: {snippet}")

    if tavily_items:
        sections.append("Web Research Insights:")
        for item in tavily_items:
            snippet = item.get("snippet", "").strip()
            sections.append(f"- {item.get('title')}: {snippet}")

    return "\n".join(sections).strip()
