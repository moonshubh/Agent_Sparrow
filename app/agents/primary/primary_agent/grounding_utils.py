import re
from typing import Any


def sanitize_model_response(text: str) -> str:
    """Remove URLs, citations, and source sections."""
    cleaned = re.sub(r"https://\S+", "", text)
    cleaned = re.sub(r"\[\d+\]", "", cleaned)
    cleaned = cleaned.replace("Sources:", "").strip()
    return cleaned


def kb_retrieval_satisfied(summary: Any, min_results: int, min_relevance: float) -> bool:
    return getattr(summary, "total_results", 0) >= min_results and getattr(summary, "avg_relevance", 0.0) >= min_relevance
