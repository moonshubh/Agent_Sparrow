"""Domain tools exposed to the unified agent."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional

from loguru import logger
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from app.agents.log_analysis.log_analysis_agent.simplified_agent import (
    SimplifiedLogAnalysisAgent,
)
from app.agents.log_analysis.log_analysis_agent.simplified_schemas import (
    SimplifiedAgentState,
    SimplifiedLogAnalysisOutput,
)
from app.agents.primary.primary_agent.feedme_knowledge_tool import (
    EnhancedKBSearchInput,
)
from app.core.rate_limiting.agent_wrapper import rate_limited
from app.core.settings import settings
from app.db.embedding import utils as embedding_utils
from app.db.supabase.client import get_supabase_client
from app.security.pii_redactor import redact_pii, redact_pii_from_dict
from app.services.global_knowledge.hybrid_retrieval import HybridRetrieval
from app.tools.research_tools import FirecrawlTool, TavilySearchTool


TOOL_RATE_LIMIT_MODEL = settings.router_model or settings.primary_agent_model or "gemini-2.5-flash-lite"
ALLOWED_SUPABASE_TABLES = {
    "mailbird_knowledge",
    "feedme_conversations",
    "chat_sessions",
    "web_research_snapshots",
}


@lru_cache(maxsize=1)
def _tavily_client() -> TavilySearchTool:
    return TavilySearchTool()


@lru_cache(maxsize=1)
def _firecrawl_client() -> FirecrawlTool:
    return FirecrawlTool()


@lru_cache(maxsize=1)
def _hybrid_retriever() -> HybridRetrieval:
    return HybridRetrieval()


@lru_cache(maxsize=1)
def _supabase_client_cached():
    return get_supabase_client()


def _build_kb_filters(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not context:
        return {}
    filters: Dict[str, Any] = {}
    version = context.get("product_version") or context.get("version")
    if version:
        filters["product_version"] = str(version)
    tags = context.get("tags")
    if isinstance(tags, list) and tags:
        filters["tags"] = [str(tag) for tag in tags if tag]
    return filters


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00") if isinstance(value, str) else value
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def _summarize_snippets(snippets: List[str], max_chars: int = 400) -> str:
    cleaned = [re.sub(r"\s+", " ", snippet).strip() for snippet in snippets if snippet]
    if not cleaned:
        return ""
    summary = " \n".join(cleaned[:5])
    summary = summary.strip()
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 1].rstrip() + "…"


def _apply_supabase_filters(query, filters: Dict[str, Dict[str, Any]]):
    if not filters:
        return query
    for field, operations in filters.items():
        if not isinstance(operations, dict):
            continue
        for op, value in operations.items():
            try:
                if op == "eq":
                    query = query.eq(field, value)
                elif op == "neq":
                    query = query.neq(field, value)
                elif op == "gte":
                    query = query.gte(field, value)
                elif op == "lte":
                    query = query.lte(field, value)
                elif op == "gt":
                    query = query.gt(field, value)
                elif op == "lt":
                    query = query.lt(field, value)
                elif op == "like":
                    query = query.like(field, value)
                elif op == "ilike":
                    query = query.ilike(field, value)
                elif op == "in" and isinstance(value, list):
                    query = query.in_(field, value)
            except Exception as exc:
                logger.warning("Failed to apply filter %s on %s: %s", op, field, exc)
                continue
    return query


class WebSearchInput(BaseModel):
    query: str = Field(..., description="Natural language query to research.")
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of URLs to return.",
    )


class FeedMeSearchInput(BaseModel):
    query: str = Field(..., description="Natural language query to search FeedMe conversations.")
    max_results: int = Field(default=5, ge=1, le=10, description="Maximum conversations to surface.")
    folder_id: Optional[int] = Field(default=None, description="Optional FeedMe folder filter.")
    start_date: Optional[datetime] = Field(default=None, description="Only include conversations on/after this ISO date.")
    end_date: Optional[datetime] = Field(default=None, description="Only include conversations on/before this ISO date.")


class SupabaseQueryInput(BaseModel):
    table: str = Field(..., description="Whitelisted table to query via Supabase.")
    filters: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Field→operations map (eq/gte/lte/ilike/in).",
    )
    limit: int = Field(default=20, ge=1, le=100, description="Max rows to return.")
    order_by: Optional[str] = Field(default=None, description="Optional column to order by.")
    ascending: bool = Field(default=True, description="Order direction when order_by is set.")


@tool("kb_search", args_schema=EnhancedKBSearchInput)
async def kb_search_tool(input: EnhancedKBSearchInput) -> List[Dict[str, Any]]:
    """Search the Mailbird knowledge base via hybrid vector/text retrieval."""

    sources = input.search_sources or ["knowledge_base"]
    if "knowledge_base" not in sources:
        logger.info("kb_search skipped because knowledge_base not requested")
        return []

    retriever = _hybrid_retriever()
    filters = _build_kb_filters(input.context or {})
    results = await retriever.search_knowledge_base(
        query=input.query,
        top_k=input.max_results,
        min_score=input.min_confidence or 0.25,
        filters=filters,
    )
    return results


class LogDiagnoserInput(BaseModel):
    log_content: str = Field(..., description="Raw log text to analyze.")
    question: Optional[str] = Field(
        default=None,
        description="Specific question about the log contents.",
    )
    trace_id: Optional[str] = Field(
        default=None,
        description="Optional trace identifier for auditing.",
    )


class FirecrawlInput(BaseModel):
    url: str = Field(..., description="URL to scrape for detailed content.")


@tool("log_diagnoser", args_schema=LogDiagnoserInput)
async def log_diagnoser_tool(input: LogDiagnoserInput) -> Dict[str, Any]:
    """Analyze application logs and return targeted diagnostics with error handling."""
    try:
        state = SimplifiedAgentState(
            raw_log_content=input.log_content,
            question=input.question,
            trace_id=input.trace_id,
        )
        async with SimplifiedLogAnalysisAgent() as agent:
            result: SimplifiedLogAnalysisOutput = await agent.analyze(state)
        return result.model_dump()
    except Exception as e:
        # Return error information for graceful degradation
        return {
            "error": "log_analysis_failed",
            "message": str(e),
            "trace_id": input.trace_id,
            "suggestion": "Please check the log format and try again."
        }


@tool("web_search", args_schema=WebSearchInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def web_search_tool(input: WebSearchInput) -> Dict[str, Any]:
    """Search the public web using Tavily for broader context with retry logic."""
    max_retries = 3
    tavily = _tavily_client()
    
    for attempt in range(max_retries):
        try:
            return await asyncio.to_thread(tavily.search, input.query, input.max_results)
        except Exception as e:
            if attempt == max_retries - 1:
                raise Exception(f"Web search failed after {max_retries} attempts: {e}")
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff


@tool("fetch_url", args_schema=FirecrawlInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def firecrawl_fetch_tool(input: FirecrawlInput) -> Dict[str, Any]:
    """Fetch structured content from a URL via Firecrawl with retry logic."""
    max_retries = 3
    firecrawl = _firecrawl_client()
    
    for attempt in range(max_retries):
        try:
            return await asyncio.to_thread(firecrawl.scrape_url, input.url)
        except Exception as e:
            if attempt == max_retries - 1:
                raise Exception(f"URL fetch failed after {max_retries} attempts: {e}")
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff


def get_registered_tools() -> List[BaseTool]:
    """Return the tools bound to the unified agent."""

    return [
        kb_search_tool,
        feedme_search_tool,
        supabase_query_tool,
        web_search_tool,
        log_diagnoser_tool,
    ]
@tool("feedme_search", args_schema=FeedMeSearchInput)
async def feedme_search_tool(input: FeedMeSearchInput) -> List[Dict[str, Any]]:
    """Search historical FeedMe conversations using embeddings and metadata."""

    client = _supabase_client_cached()
    if getattr(client, "mock_mode", False):
        logger.warning("Supabase mock mode active; feedme search disabled")
        return []

    emb_model = embedding_utils.get_embedding_model()
    loop = asyncio.get_running_loop()
    query_vec = await loop.run_in_executor(None, emb_model.embed_query, input.query)

    match_count = max(input.max_results * 4, 20)
    try:
        chunk_rows = await client.search_text_chunks(
            query_vec,
            match_count=match_count,
            folder_id=input.folder_id,
        )
    except Exception as exc:
        logger.error("FeedMe chunk search failed: %s", exc)
        return []

    aggregated: Dict[int, Dict[str, Any]] = {}
    for row in chunk_rows or []:
        conv_id = row.get("conversation_id") or row.get("conversationId")
        if conv_id is None:
            continue
        try:
            conv_id = int(conv_id)
        except Exception:
            continue
        entry = aggregated.setdefault(
            conv_id,
            {
                "conversation_id": conv_id,
                "title": None,
                "confidence": 0.0,
                "snippets": [],
                "created_at": None,
            },
        )
        try:
            sim = float(row.get("similarity") or row.get("similarity_score") or 0.0)
        except Exception:
            sim = 0.0
        entry["confidence"] = max(entry["confidence"], sim)
        snippet = (row.get("content") or "").strip()
        if snippet:
            # Redact PII first, then slice to avoid partial PII at boundary
            redacted_snippet = redact_pii(snippet)
            entry["snippets"].append(redacted_snippet[:400])

    if not aggregated:
        return []

    try:
        conv_details = await client.get_conversations_by_ids(list(aggregated.keys()))
    except Exception as exc:
        logger.error("Failed to hydrate FeedMe conversations: %s", exc)
        conv_details = {}

    start_date = input.start_date
    end_date = input.end_date
    results: List[Dict[str, Any]] = []

    for conv_id, payload in aggregated.items():
        details = (conv_details or {}).get(conv_id, {})
        created_at = details.get("created_at") or payload.get("created_at")
        created_dt = _parse_iso_datetime(created_at)
        if start_date and (created_dt is None or created_dt < start_date):
            continue
        if end_date and (created_dt is None or created_dt > end_date):
            continue

        meta = details.get("metadata") or {}
        ai_note = meta.get("ai_note") if isinstance(meta, dict) else None
        summary_source = None
        if isinstance(ai_note, str) and ai_note.strip():
            summary_source = ai_note.strip()
        else:
            extracted = details.get("extracted_text") or ""
            if extracted:
                summary_source = extracted.strip()
        if not summary_source:
            summary_source = _summarize_snippets(payload.get("snippets", []))
        summary_compact = _summarize_snippets([summary_source] if summary_source else [])
        summary = redact_pii(summary_compact or summary_source or "")

        results.append(
            {
                "conversation_id": conv_id,
                "title": details.get("title") or f"Conversation {conv_id}",
                "summary": summary,
                "confidence": payload.get("confidence", 0.0),
                "created_at": created_at,
            }
        )

    results.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
    return results[: input.max_results]


@tool("supabase_query", args_schema=SupabaseQueryInput)
async def supabase_query_tool(input: SupabaseQueryInput) -> List[Dict[str, Any]]:
    """Run a whitelisted Supabase query with simple filter expressions."""

    table = input.table.strip()
    if table not in ALLOWED_SUPABASE_TABLES:
        raise ValueError(f"Table '{table}' is not permitted for supabase_query")

    client = _supabase_client_cached()
    if getattr(client, "mock_mode", False):
        logger.warning("Supabase mock mode active; supabase_query returning empty list")
        return []

    def _execute():
        query = client.client.table(table).select("*")
        query = _apply_supabase_filters(query, input.filters)
        query = query.limit(input.limit)
        if input.order_by:
            query = query.order(input.order_by, desc=not input.ascending)
        return query.execute()

    try:
        response = await asyncio.to_thread(_execute)
    except Exception as exc:
        logger.error("Supabase query failed: %s", exc)
        return []

    rows = response.data or []
    return [redact_pii_from_dict(row) for row in rows]
