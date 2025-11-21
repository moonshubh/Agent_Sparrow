"""Lightweight Gemma helper utilities for summarization and reranking.

These helpers are intentionally minimal: they use Google's hosted Gemma model
to cheaply compress or rerank inputs before the primary (Gemini) model runs.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from loguru import logger

from app.core.settings import settings


try:
    # ChatGoogleGenerativeAI covers both Gemini and Gemma model IDs
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:  # pragma: no cover - import guard
    ChatGoogleGenerativeAI = None  # type: ignore


class GemmaHelper:
    """Small wrapper to share a single client and usage cap per run."""

    def __init__(self, *, max_calls: int = 10) -> None:
        self.max_calls = max_calls
        self._calls = 0
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if ChatGoogleGenerativeAI is None:
            raise RuntimeError("langchain_google_genai is not available")
        model = getattr(settings, "gemma_helper_model", None) or "gemma-3-27b-it"
        self._client = ChatGoogleGenerativeAI(
            model=model,
            temperature=0.2,
            max_output_tokens=512,
            google_api_key=settings.gemini_api_key,
        )
        return self._client

    def _remaining(self) -> int:
        return max(self.max_calls - self._calls, 0)

    async def summarize(self, text: str, *, budget_tokens: int = 1024) -> Optional[str]:
        if not text or self._remaining() <= 0:
            return None
        client = self._get_client()
        prompt = (
            "Summarize the following content concisely for downstream LLM context. "
            "Preserve key facts and entities. Limit to ~" f"{budget_tokens} tokens.\n\n" + text
        )
        try:
            self._calls += 1
            resp = await client.ainvoke(prompt)
            return str(getattr(resp, "content", "")) or None
        except Exception as exc:  # pragma: no cover - network/runtime failures
            logger.warning("gemma_summarize_failed", error=str(exc))
            return None

    async def rerank(self, snippets: List[str], query: str, *, top_k: int = 3) -> Optional[List[str]]:
        if not snippets or self._remaining() <= 0:
            return None
        client = self._get_client()
        joined = "\n\n".join(f"Snippet {i+1}: {s}" for i, s in enumerate(snippets))
        prompt = (
            "Given the user query, rerank the snippets by relevance and return the top items as a bulleted list. "
            "Only include the text of the best snippets, preserve wording, no commentary.\n\n"
            f"Query: {query}\n\n{joined}"
        )
        try:
            self._calls += 1
            resp = await client.ainvoke(prompt)
            content = str(getattr(resp, "content", "") or "")
            if not content.strip():
                return None
            # Split on newlines and strip bullets
            lines = [line.strip("- •") for line in content.splitlines() if line.strip()]
            return lines[:top_k] if lines else None
        except Exception as exc:  # pragma: no cover
            logger.warning("gemma_rerank_failed", error=str(exc))
            return None

    async def rewrite_query(self, query: str) -> Optional[str]:
        if not query or self._remaining() <= 0:
            return None
        client = self._get_client()
        prompt = (
            "Rewrite the user query for better search recall and precision. Keep it concise, no bullet points.\n"
            f"Original: {query}"
        )
        try:
            self._calls += 1
            resp = await client.ainvoke(prompt)
            rewritten = str(getattr(resp, "content", "") or "").strip()
            if not rewritten or rewritten.lower() == query.lower():
                return None
            return rewritten
        except Exception as exc:  # pragma: no cover
            logger.warning("gemma_rewrite_failed", error=str(exc))
            return None
