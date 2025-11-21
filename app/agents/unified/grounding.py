"""Gemini Search Grounding integration with quota + fallbacks."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from app.core.logging_config import get_logger
from app.core.settings import settings
from app.tools.research_tools import TavilySearchTool

from .quota_manager import QuotaExceededError, QuotaManager

GROUNDING_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GroundingServiceError(RuntimeError):
    """Base error for grounding service failures."""


class GroundingUnavailableError(GroundingServiceError):
    """Raised when the Gemini grounding service is disabled or misconfigured."""


class GeminiGroundingService:
    """Calls Gemini Search Grounding with quota enforcement and fallbacks."""

    def __init__(
        self,
        *,
        quota_manager: Optional[QuotaManager] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        enabled: Optional[bool] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.logger = get_logger("gemini_grounding")
        self.quota_manager = quota_manager or QuotaManager()
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.grounding_model
        self.timeout = timeout or settings.grounding_timeout_sec
        resolved_enabled = enabled if enabled is not None else settings.enable_grounding_search
        self.enabled = bool(resolved_enabled and self.api_key)
        self.max_results_default = settings.grounding_max_results
        self.snippet_limit = settings.grounding_snippet_chars
        self._tavily: Optional[TavilySearchTool] = None

    async def search_with_grounding(self, query: str, max_results: Optional[int] = None) -> Dict[str, Any]:
        if not self.enabled:
            raise GroundingUnavailableError("Grounding search is disabled or missing GEMINI_API_KEY")
        normalized_query = (query or "").strip()
        if not normalized_query:
            return {"source": "gemini_grounding", "results": [], "langsmith_metadata": {}}

        limit = self._resolve_limit(max_results)
        if not self.quota_manager.check_and_track("grounding"):
            raise QuotaExceededError("grounding")

        try:
            payload = await self._call_grounding_api(normalized_query, limit)
        except httpx.HTTPError as exc:
            raise GroundingServiceError(str(exc)) from exc
        results = self._normalize_response(payload, limit)

        # LangSmith observability metadata
        langsmith_metadata = {
            "search_service": "gemini_grounding",
            "search_model": self.model,
            "results_count": len(results),
            "max_results_requested": limit,
            "query_length": len(normalized_query),
        }

        return {
            "source": "gemini_grounding",
            "model": self.model,
            "results": results,
            "raw_response": payload,
            "langsmith_metadata": langsmith_metadata,
        }

    async def fallback_search(self, query: str, max_results: Optional[int] = None, reason: str = "error") -> Dict[str, Any]:
        """Fallback chain: Tavily."""

        limit = self._resolve_limit(max_results)
        tavily = self._get_tavily()

        # Track services used for LangSmith
        services_used = []
        tavily_success = False

        fallback_payload: Dict[str, Any] = {
            "source": "tavily_fallback",
            "reason": reason,
            "results": [],
            "extracted": [],
        }

        tavily_result: Optional[Dict[str, Any]] = None
        try:
            tavily_result = await asyncio.to_thread(tavily.search, query, limit)
            urls = tavily_result.get("urls", [])
            tavily_success = bool(urls)
            services_used.append("tavily")
        except Exception as exc:  # pragma: no cover - network failure
            self.logger.warning("grounding_fallback_tavily_error", error=str(exc))
            urls = []
        fallback_payload["results"] = [{"url": url} for url in urls]

        extracts: List[Dict[str, Any]] = []
        if isinstance(tavily_result, dict):
            structured_results = tavily_result.get("results") or []
            for item in structured_results[: min(3, len(structured_results))]:
                url = item.get("url") or item.get("source") or ""
                snippet = self._trim_snippet(
                    item.get("content")
                    or item.get("snippet")
                    or item.get("title")
                    or ""
                )
                if url or snippet:
                    extracts.append(
                        {
                            "url": url,
                            "snippet": snippet,
                            "source": "tavily",
                        }
                    )
        if extracts:
            fallback_payload["extracted"] = extracts

        # Add LangSmith observability metadata
        langsmith_metadata = {
            "search_service": "fallback_chain",
            "fallback_reason": reason,
            "services_used": services_used,
            "tavily_success": tavily_success,
            "urls_found": len(urls),
            "query_length": len(query or ""),
        }
        fallback_payload["langsmith_metadata"] = langsmith_metadata

        return fallback_payload

    async def _call_grounding_api(self, query: str, limit: int) -> Dict[str, Any]:
        # Use the currently supported googleSearch tool for the Generative Language API.
        # Note: responseMimeType="application/json" is not supported when tools are used,
        # so we omit it here and parse groundingMetadata from the normal response payload.
        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": query,
                        }
                    ],
                }
            ],
            "tools": [{"googleSearch": {}}],
            "generationConfig": {
                "maxOutputTokens": 512,
            },
        }

        url = GROUNDING_ENDPOINT.format(model=self.model)
        params = {"key": self.api_key}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, params=params, json=body)
            response.raise_for_status()
            return response.json()

    def _normalize_response(self, payload: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        candidates = payload.get("candidates") or []
        for candidate in candidates:
            metadata = candidate.get("groundingMetadata") or candidate.get("grounding_metadata") or {}
            chunks = metadata.get("groundingChunks") or metadata.get("grounding_chunks") or []
            chunk_refs = {chunk.get("id") or chunk.get("chunkId"): chunk for chunk in chunks}
            citations = metadata.get("citations") or []
            citation_map = self._map_citations(citations)
            for chunk_id, chunk in chunk_refs.items():
                web_info = chunk.get("web") or {}
                # Fallback to model text when no explicit web/snippet text is present.
                fallback_text = ""
                content_obj = candidate.get("content") or {}
                if isinstance(content_obj, dict):
                    parts = content_obj.get("parts") or []
                    if parts and isinstance(parts[0], dict):
                        fallback_text = parts[0].get("text") or ""

                snippet = self._trim_snippet(
                    web_info.get("text")
                    or chunk.get("snippet")
                    or chunk.get("text")
                    or fallback_text
                )
                results.append(
                    {
                        "id": chunk_id,
                        "title": web_info.get("title") or web_info.get("uri") or "Grounded evidence",
                        "url": web_info.get("uri"),
                        "snippet": snippet,
                        "score": chunk.get("confidenceScore") or chunk.get("score"),
                        "domain": web_info.get("domain"),
                        "citation": citation_map.get(chunk_id),
                    }
                )
        if not results and candidates:
            # Fall back to textual content when no structured grounding metadata returned
            for candidate in candidates:
                text_parts: List[str] = []
                content_obj = candidate.get("content") or {}
                if isinstance(content_obj, dict):
                    for part in content_obj.get("parts", []) or []:
                        if isinstance(part, dict):
                            value = part.get("text")
                            if value:
                                text_parts.append(value)
                if text_parts:
                    results.append(
                        {
                            "id": None,
                            "title": "Gemini summary",
                            "url": None,
                            "snippet": self._trim_snippet("\n".join(text_parts)),
                            "score": None,
                            "domain": None,
                        }
                    )
        return results[:limit]

    def _map_citations(self, citations: List[Dict[str, Any]]) -> Dict[str, Any]:
        mapping: Dict[str, Any] = {}
        for citation in citations:
            reference_id = citation.get("chunkReference") or citation.get("chunk_reference")
            if not reference_id:
                continue
            mapping[reference_id] = {
                "startIndex": citation.get("startIndex"),
                "endIndex": citation.get("endIndex"),
                "uri": citation.get("uri"),
            }
        return mapping

    def _resolve_limit(self, requested: Optional[int]) -> int:
        if not requested:
            return self.max_results_default
        return max(1, min(requested, 10))

    def _trim_snippet(self, text: str) -> str:
        snippet = (text or "").strip()
        if len(snippet) <= self.snippet_limit:
            return snippet
        return snippet[: self.snippet_limit - 1].rstrip() + "…"

    def _get_tavily(self) -> TavilySearchTool:
        if self._tavily is None:
            self._tavily = TavilySearchTool()
        return self._tavily
