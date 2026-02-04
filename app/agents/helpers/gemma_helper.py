"""Lightweight helper utilities for summarization and reranking.

Historically this used Google's hosted Gemma models, but in practice Gemma's
paid-tier TPM limits can be too low for long-running sessions. The configured
helper model is therefore controlled via `GEMMA_HELPER_MODEL` and defaults to a
high-quota Gemini model.
"""

from __future__ import annotations

from typing import Any, List, Optional

from loguru import logger

from app.core.config import get_models_config
from app.core.settings import settings
from app.core.rate_limiting.agent_wrapper import wrap_gemini_agent

try:
    # ChatGoogleGenerativeAI covers both Gemini and Gemma model IDs
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:  # pragma: no cover - import guard
    ChatGoogleGenerativeAI = None  # type: ignore


class GemmaHelper:
    """Small wrapper to share a single client and usage cap per run."""

    def __init__(self, *, max_calls: int = 10) -> None:
        # max_calls <= 0 disables the cap (unlimited helper calls).
        self.max_calls = max_calls
        self._calls = 0
        self._client: Optional[Any] = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if ChatGoogleGenerativeAI is None:
            raise RuntimeError("langchain_google_genai is not available")
        config = get_models_config()
        helper_cfg = config.internal["helper"]
        model = helper_cfg.model_id
        client = ChatGoogleGenerativeAI(
            model=model,
            temperature=helper_cfg.temperature,
            max_output_tokens=512,
            google_api_key=settings.gemini_api_key,
        )
        self._client = wrap_gemini_agent(client, "internal.helper", model)
        return self._client

    def _remaining(self) -> int:
        if self.max_calls <= 0:
            return 1_000_000_000
        return max(self.max_calls - self._calls, 0)

    async def summarize(self, text: str, *, budget_tokens: int = 1024) -> Optional[str]:
        if not text or self._remaining() <= 0:
            return None
        client = self._get_client()
        prompt = (
            "Summarize the following content concisely for downstream LLM context. "
            "Preserve key facts and entities. Limit to ~"
            f"{budget_tokens} tokens.\n\n" + text
        )
        try:
            self._calls += 1
            resp = await client.ainvoke(prompt)
            return str(getattr(resp, "content", "")) or None
        except Exception as exc:  # pragma: no cover - network/runtime failures
            logger.warning("gemma_summarize_failed", error=str(exc))
            return None

    async def rerank(
        self, snippets: List[str], query: str, *, top_k: int = 3
    ) -> Optional[List[str]]:
        if not snippets or self._remaining() <= 0:
            return None
        client = self._get_client()
        joined = "\n\n".join(f"Snippet {i + 1}: {s}" for i, s in enumerate(snippets))
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
