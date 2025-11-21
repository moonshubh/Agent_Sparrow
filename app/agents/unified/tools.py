"""Domain tools exposed to the unified agent."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from functools import lru_cache
import json
import uuid
from typing import Any, Dict, List, Optional, Annotated

import httpx
from bs4 import BeautifulSoup

from loguru import logger
from langchain_core.tools import BaseTool, tool, InjectedToolArg
from langchain_core.runnables import RunnableConfig
from langchain_core.callbacks.manager import adispatch_custom_event
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
from app.agents.unified.grounding import (
    GeminiGroundingService,
    GroundingServiceError,
    GroundingUnavailableError,
)
from app.agents.unified.quota_manager import QuotaExceededError
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


@lru_cache(maxsize=1)
def _grounding_service() -> GeminiGroundingService:
    return GeminiGroundingService()


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


def _rewrite_search_query(raw_query: str, max_chars: int = 400) -> str:
    text = (raw_query or "").strip()
    if not text:
        return ""

    # If the query already looks concise, use it as-is.
    if len(text) <= max_chars and text.count("\n") <= 4:
        return text

    # Extract error-like lines and hostnames from long/log-heavy inputs.
    candidates: List[str] = []
    lower_keywords = (
        "error",
        "exception",
        "failed",
        "unknown host",
        "hte inconnu",
        "connection lost",
        "imap.gmail.com",
        "accounts.google.com",
        "oauth",
        "gmail",
    )

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(kw in lowered for kw in lower_keywords):
            candidates.append(stripped)

    host_pattern = re.compile(r"\b([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b")
    for match in host_pattern.findall(text):
        if match not in candidates:
            candidates.append(match)

    if candidates:
        # Deduplicate while preserving order
        seen = set()
        unique_parts: List[str] = []
        for part in candidates:
            if part in seen:
                continue
            seen.add(part)
            unique_parts.append(part)
        rewritten = " ".join(unique_parts)
        if len(rewritten) > max_chars:
            rewritten = rewritten[:max_chars].rstrip()
        return rewritten

    # Fallback: truncate the original text
    return text[:max_chars].rstrip()


async def _http_fetch_fallback(url: str, max_chars: int = 8000) -> Dict[str, Any]:
    """Best-effort HTML fetch when Firecrawl is unavailable."""

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")

    def _strip_html(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "iframe"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        text = re.sub(r"\n{2,}", "\n\n", text)
        return text

    # Run HTML parsing in executor to avoid blocking event loop
    loop = asyncio.get_running_loop()
    cleaned = await loop.run_in_executor(None, _strip_html, resp.text)

    title = None
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string if soup.title else None
    except Exception:
        title = None

    return {
        "url": str(resp.url),
        "status_code": resp.status_code,
        "content_type": content_type,
        "title": (title or "").strip() or url,
        "content": cleaned[:max_chars],
        "source": "httpx_fallback",
    }


async def _grounding_fallback(query: str, max_results: int, reason: str) -> Dict[str, Any]:
    service = _grounding_service()
    return await service.fallback_search(query, max_results, reason=reason)


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


class GroundingSearchInput(BaseModel):
    query: str = Field(..., description="Query to send through Gemini Search Grounding.")
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of grounded evidence chunks to return.",
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


def _serialize_tool_output(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        return str(payload)


@tool("kb_search", args_schema=EnhancedKBSearchInput)
async def kb_search_tool(
    query: str,
    context: Optional[Dict[str, Any]] = None,
    max_results: int = 5,
    search_sources: Optional[List[str]] = None,
    min_confidence: Optional[float] = None,
) -> str:
    """Search the Mailbird knowledge base via hybrid vector/text retrieval."""

    sources = search_sources or ["knowledge_base"]
    if "knowledge_base" not in sources:
        logger.info("kb_search skipped because knowledge_base not requested")
        return _serialize_tool_output({
            "query": query,
            "results": [],
            "reason": "knowledge_base_not_requested",
        })

    retriever = _hybrid_retriever()
    filters = _build_kb_filters(context or {})
    effective_query = _rewrite_search_query(query)
    results = await retriever.search_knowledge_base(
        query=effective_query,
        top_k=max_results,
        min_score=min_confidence or 0.25,
        filters=filters,
    )
    payload = {
        "query": query,
        "effective_query": effective_query,
        "filters": filters,
        "result_count": len(results),
        "results": results,
    }
    return _serialize_tool_output(payload)


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
async def log_diagnoser_tool(
    input: Optional[LogDiagnoserInput] = None,
    log_content: Optional[str] = None,
    question: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Analyze application logs and return targeted diagnostics with error handling.

    Supports both structured invocation with a LogDiagnoserInput object and
    direct kwargs (log_content, question, trace_id) so that LangChain/DeepAgents
    tool calls that pass raw arguments continue to work.
    """

    # Normalize inputs regardless of how the tool is invoked
    if input is None:
        input = LogDiagnoserInput(
            log_content=log_content or "",
            question=question,
            trace_id=trace_id,
        )

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
async def web_search_tool(
    input: Optional[WebSearchInput] = None,
    query: Optional[str] = None,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Search the public web using Tavily for broader context with retry logic.

    Supports both structured invocation with a WebSearchInput object and
    direct kwargs (query, max_results) so that LangChain/DeepAgents tool
    calls that pass raw arguments continue to work.
    """

    # Normalize inputs regardless of how the tool is invoked
    if input is None:
        input = WebSearchInput(query=query or "", max_results=max_results)

    max_retries = 3
    tavily = _tavily_client()

    for attempt in range(max_retries):
        try:
            logger.info(
                f"web_search_tool_invoked query='{input.query}' max_results={input.max_results} attempt={attempt + 1}"
            )
            result = await asyncio.to_thread(tavily.search, input.query, input.max_results)
            urls = result.get("urls") if isinstance(result, dict) else None
            logger.info(
                f"web_search_tool_success query='{input.query}' urls={len(urls or [])}"
            )
            return result
        except Exception as e:
            if attempt == max_retries - 1:
                raise Exception(f"Web search failed after {max_retries} attempts: {e}")
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff


@tool("grounding_search", args_schema=GroundingSearchInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def grounding_search_tool(
    input: Optional[GroundingSearchInput] = None,
    query: Optional[str] = None,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Call Gemini Search Grounding with automatic Tavily/Firecrawl fallback.

    Like web_search_tool, this accepts either a structured GroundingSearchInput
    instance or raw kwargs (query, max_results), so tool calls remain robust
    regardless of how arguments are passed.
    """

    if input is None:
        input = GroundingSearchInput(query=query or "", max_results=max_results)

    try:
        service = _grounding_service()
        if not service.enabled:
            raise GroundingUnavailableError("grounding_disabled")
        logger.info(
            f"grounding_search_tool_invoked query='{input.query}' max_results={input.max_results}"
        )
        response = await service.search_with_grounding(input.query, input.max_results)
        logger.info(
            f"grounding_search_tool_success query='{input.query}' result_count={len(response.get('results') or [])}"
        )
        if response.get("results"):
            return response
        logger.info(f"grounding_search_tool_empty query='{input.query}'")
        return await _grounding_fallback(input.query, input.max_results, reason="empty_results")
    except QuotaExceededError as exc:
        logger.warning("grounding_search_quota", error=str(exc))
        return await _grounding_fallback(input.query, input.max_results, reason="quota_exceeded")
    except GroundingUnavailableError as exc:
        logger.info("grounding_search_unavailable", error=str(exc))
        return await _grounding_fallback(input.query, input.max_results, reason="unavailable")
    except GroundingServiceError as exc:
        logger.warning("grounding_search_error", error=str(exc))
        return await _grounding_fallback(input.query, input.max_results, reason="service_error")


@tool("fetch_url", args_schema=FirecrawlInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def firecrawl_fetch_tool(
    input: Optional[FirecrawlInput] = None,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch structured content from a URL via Firecrawl with retry logic."""

    if input is None:
        input = FirecrawlInput(url=url or "")

    max_retries = 3
    firecrawl = _firecrawl_client()

    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            logger.info(
                f"firecrawl_fetch_tool_invoked url='{input.url}' attempt={attempt + 1}"
            )
            result = await asyncio.to_thread(firecrawl.scrape_url, input.url)
            logger.info(
                f"firecrawl_fetch_tool_success url='{input.url}' has_error={'error' in (result or {})}"
            )
            if isinstance(result, dict) and result.get("error"):
                raise RuntimeError(result["error"])
            return result
        except Exception as e:
            logger.warning(
                f"firecrawl_fetch_tool_error url='{input.url}' attempt={attempt + 1} error='{str(e)}'"
            )
            last_error = e
            if attempt == max_retries - 1:
                break
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff

    # Fallback to direct HTTP fetch when Firecrawl is unavailable or throttled.
    try:
        logger.info(f"firecrawl_http_fallback_start url='{input.url}'")
        fallback = await _http_fetch_fallback(input.url)
        logger.info(f"firecrawl_http_fallback_success url='{input.url}'")
        return fallback
    except Exception as http_exc:
        logger.warning(
            f"firecrawl_http_fallback_error url='{input.url}' error='{str(http_exc)}'"
        )
        raise Exception(
            f"URL fetch failed after {max_retries} attempts and HTTP fallback: {last_error or http_exc}"
        ) from http_exc


def get_registered_tools() -> List[BaseTool]:
    """Return the tools bound to the unified agent."""

    return [
        kb_search_tool,
        grounding_search_tool,
        web_search_tool,
        feedme_search_tool,
        supabase_query_tool,
        log_diagnoser_tool,
        get_weather,
        generate_task_steps_generative_ui,
        write_todos,
    ]


class Step(BaseModel):
    """
    A step in a task.
    """
    description: str = Field(description="The text of the step in gerund form")
    status: str = Field(description="The status of the step (pending|in_progress|done), defaults to pending")


class TodoItem(BaseModel):
    """Lightweight todo list entry for planning."""

    id: Optional[str] = Field(default=None, description="Stable id for tracking updates.")
    title: str = Field(description="Short title of the todo item (imperative).")
    status: Optional[str] = Field(
        default="pending",
        description="Status of the todo item (normalized to pending|in_progress|done).",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional metadata to display alongside the item."
    )


@tool
def get_weather(location: str):
    """
    Get the weather for a given location.
    """
    return {
        "temperature": 20,
        "conditions": "sunny",
        "humidity": 50,
        "wind_speed": 10,
        "feelsLike": 25,
    }


@tool
async def generate_task_steps_generative_ui(
    steps: Annotated[
        List[Step],
        "An array of 10 step objects, each containing text and status"
    ],
    config: Annotated[RunnableConfig, InjectedToolArg]
):
    """
    Make up 10 steps (only a couple of words per step) that are required for a task.
    The step should be in gerund form (i.e. Digging hole, opening door, ...).
    """
    # Simulate executing the steps with streaming updates
    current_steps = [step.model_dump() for step in steps]
    
    # Emit initial state
    await adispatch_custom_event(
        "manually_emit_state",
        {"steps": current_steps},
        config=config,
    )

    for i, _ in enumerate(current_steps):
        await asyncio.sleep(1)
        current_steps[i]["status"] = "completed"
        # Emit updated state
        await adispatch_custom_event(
            "manually_emit_state",
            {"steps": current_steps},
            config=config,
    )
    
    return "Steps generated and executed."


@tool
def write_todos(
    todos: Annotated[
        List[TodoItem],
        "List of todo items to set/update for the current task. Use for multi-step tasks only.",
    ]
):
    """
    Update the task todo list. Keep it short (3-6 items), imperative, and update statuses as you progress.
    """
    normalized: List[Dict[str, Any]] = []
    for item in todos:
        item_dict = item.model_dump()
        if not item_dict.get("id"):
            item_dict["id"] = f"todo-{uuid.uuid4().hex[:8]}"
        status = str(item_dict.get("status") or "pending").lower()
        if status not in {"pending", "in_progress", "done"}:
            status = "pending"
        item_dict["status"] = status
        normalized.append(item_dict)
    return {"todos": normalized}


@tool("feedme_search", args_schema=FeedMeSearchInput)
async def feedme_search_tool(
    input: Optional[FeedMeSearchInput] = None,
    query: Optional[str] = None,
    max_results: int = 5,
    folder_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Search historical FeedMe conversations using embeddings and metadata.

    Supports both structured invocation with a FeedMeSearchInput object and
    direct kwargs (query, max_results, folder_id, start_date, end_date) so that
    LangChain/DeepAgents tool calls that pass raw arguments continue to work.
    """

    # Normalize inputs regardless of how the tool is invoked
    if input is None:
        input = FeedMeSearchInput(
            query=query or "",
            max_results=max_results,
            folder_id=folder_id,
            start_date=start_date,
            end_date=end_date,
        )

    client = _supabase_client_cached()
    if getattr(client, "mock_mode", False):
        logger.warning("Supabase mock mode active; feedme search disabled")
        return []

    emb_model = embedding_utils.get_embedding_model()
    loop = asyncio.get_running_loop()
    effective_query = _rewrite_search_query(input.query)
    query_vec = await loop.run_in_executor(None, emb_model.embed_query, effective_query)

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
async def supabase_query_tool(
    input: Optional[SupabaseQueryInput] = None,
    table: Optional[str] = None,
    filters: Optional[Dict[str, Dict[str, Any]]] = None,
    limit: int = 20,
    order_by: Optional[str] = None,
    ascending: bool = True,
) -> List[Dict[str, Any]]:
    """Run a whitelisted Supabase query with simple filter expressions.

    Supports both structured invocation with a SupabaseQueryInput object and
    direct kwargs (table, filters, limit, order_by, ascending) so that
    LangChain/DeepAgents tool calls that pass raw arguments continue to work.
    """

    if input is None:
        input = SupabaseQueryInput(
            table=table or "",
            filters=filters or {},
            limit=limit,
            order_by=order_by,
            ascending=ascending,
        )

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
