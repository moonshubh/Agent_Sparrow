"""Domain tools exposed to the unified agent."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import re
import socket
from datetime import datetime
from functools import lru_cache
import json
import uuid
from typing import Any, Dict, List, Optional, Annotated, Callable, Literal
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from langgraph.prebuilt import InjectedState, ToolRuntime
from langchain_core.tools import BaseTool, tool, InjectedToolArg
from langchain_core.runnables import RunnableConfig
from langchain_core.callbacks.manager import adispatch_custom_event
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from app.agents.log_analysis.log_analysis_agent.simplified_agent import (
    SimplifiedLogAnalysisAgent,
)
from app.agents.log_analysis.log_analysis_agent.simplified_schemas import (
    SimplifiedAgentState,
    SimplifiedLogAnalysisOutput,
)
from app.tools.feedme_knowledge import (
    EnhancedKBSearchInput,
)
from app.agents.unified.grounding import (
    GeminiGroundingService,
    GroundingServiceError,
    GroundingUnavailableError,
)
from app.agents.unified.quota_manager import QuotaExceededError
from app.agents.orchestration.orchestration.state import GraphState
from app.core.rate_limiting.agent_wrapper import rate_limited
from app.core.settings import settings
from app.db.embedding import utils as embedding_utils
from app.db.supabase.client import get_supabase_client
from app.security.pii_redactor import redact_pii, redact_pii_from_dict
from app.services.global_knowledge.hybrid_retrieval import HybridRetrieval
import os
from app.tools.research_tools import FirecrawlTool, TavilySearchTool
from app.core.logging_config import get_logger
from app.agents.unified.mcp_client import invoke_firecrawl_mcp_tool
import redis


TOOL_RATE_LIMIT_MODEL = (
    settings.router_model or settings.primary_agent_model or "gemini-2.5-flash-lite"
)
ALLOWED_SUPABASE_TABLES = {
    "mailbird_knowledge",
    "feedme_conversations",
    "chat_sessions",
    "web_research_snapshots",
}

# Private IP ranges for SSRF protection
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


def _is_safe_url(url: str) -> tuple[bool, str]:
    """Validate URL against SSRF attacks.

    Returns:
        Tuple of (is_safe, reason). If not safe, reason explains why.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format"

    # Only allow http/https schemes
    if parsed.scheme not in ("http", "https"):
        return False, f"Disallowed scheme: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"

    # Block localhost and special hostnames
    blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}
    if hostname.lower() in blocked_hosts:
        return False, f"Blocked hostname: {hostname}"

    # Block internal/metadata endpoints
    if hostname.lower() in ("metadata.google.internal", "169.254.169.254"):
        return False, "Blocked cloud metadata endpoint"

    # Resolve hostname to IP and check against private ranges
    try:
        # Get all IP addresses for the hostname
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        for info in infos:
            ip_str = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
                for network in _PRIVATE_NETWORKS:
                    if ip in network:
                        return False, f"Resolved to private IP: {ip}"
            except ValueError:
                continue  # Skip invalid IP addresses
    except socket.gaierror:
        return False, f"Could not resolve hostname: {hostname}"

    return True, ""


# Naming guidance for new tools:
# - search_* for retrieval, read_* for file/record reads,
# - write_* for mutations, analyze_* for diagnostics.


@lru_cache(maxsize=32)
def _tavily_client_for_key(api_key: Optional[str]) -> TavilySearchTool:
    return TavilySearchTool(api_key=api_key)


def _tavily_client() -> TavilySearchTool:
    return _tavily_client_for_key(settings.tavily_api_key)


@lru_cache(maxsize=32)
def _firecrawl_client_for_key(api_key: Optional[str]) -> FirecrawlTool:
    return FirecrawlTool(api_key=api_key)


def _firecrawl_client() -> FirecrawlTool:
    return _firecrawl_client_for_key(settings.firecrawl_api_key)


@lru_cache(maxsize=1)
def _hybrid_retriever() -> HybridRetrieval:
    return HybridRetrieval()


@lru_cache(maxsize=1)
def _supabase_client_cached():
    return get_supabase_client()


@lru_cache(maxsize=1)
def _grounding_service() -> GeminiGroundingService:
    return GeminiGroundingService()


# Simple in-process tool cache (best-effort, small footprint)
_TOOL_CACHE: dict[str, str] = {}
_TOOL_CACHE_MAX = 256
logger = get_logger(__name__)

# Optional Redis cache for multi-process/tool caching
_REDIS_CACHE = None
if settings.redis_url and os.getenv("DISABLE_TOOL_CACHE") not in {"1", "true", "True"}:
    try:  # pragma: no cover - best effort
        _REDIS_CACHE = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        logger.info("tool_cache_redis_enabled", url=settings.redis_url)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("tool_cache_redis_unavailable", error=str(exc))


_FIRECRAWL_AGENT_USAGE_WINDOW_SECONDS = 60 * 60 * 24
_FIRECRAWL_AGENT_MAX_USES_PER_WINDOW = int(
    os.getenv("FIRECRAWL_AGENT_MAX_USES_PER_24H", "5")
)
_FIRECRAWL_AGENT_USAGE_FALLBACK: dict[str, list[int]] = {}


def _firecrawl_agent_usage_key() -> str:
    api_key = settings.firecrawl_api_key or ""
    api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return f"firecrawl_agent_usage:{api_key_hash}"


def _check_and_record_firecrawl_agent_use() -> tuple[bool, int, int]:
    limit = _FIRECRAWL_AGENT_MAX_USES_PER_WINDOW
    if limit <= 0:
        return True, 0, 0

    now = int(datetime.utcnow().timestamp())
    window_start = now - _FIRECRAWL_AGENT_USAGE_WINDOW_SECONDS
    key = _firecrawl_agent_usage_key()

    if _REDIS_CACHE is not None:
        try:  # pragma: no cover - best effort
            pipe = _REDIS_CACHE.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            _, count = pipe.execute()
            count_int = int(count or 0)

            if count_int >= limit:
                earliest = _REDIS_CACHE.zrange(key, 0, 0, withscores=True)
                earliest_ts = int(earliest[0][1]) if earliest else now
                retry_after = max(
                    earliest_ts + _FIRECRAWL_AGENT_USAGE_WINDOW_SECONDS - now,
                    0,
                )
                return False, count_int, retry_after

            member = str(uuid.uuid4())
            pipe = _REDIS_CACHE.pipeline()
            pipe.zadd(key, {member: now})
            pipe.expire(key, _FIRECRAWL_AGENT_USAGE_WINDOW_SECONDS * 2)
            pipe.execute()
            return True, count_int + 1, 0
        except Exception:
            pass

    events = _FIRECRAWL_AGENT_USAGE_FALLBACK.get(key, [])
    events = [ts for ts in events if ts > window_start]
    if len(events) >= limit:
        earliest_ts = min(events) if events else now
        retry_after = max(earliest_ts + _FIRECRAWL_AGENT_USAGE_WINDOW_SECONDS - now, 0)
        _FIRECRAWL_AGENT_USAGE_FALLBACK[key] = events
        return False, len(events), retry_after

    events.append(now)
    _FIRECRAWL_AGENT_USAGE_FALLBACK[key] = events
    return True, len(events), 0


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


_FIRECRAWL_ALLOWED_FORMATS = {
    "markdown",
    "html",
    "rawHtml",
    "screenshot",
    "links",
    "summary",
    "changeTracking",
    "branding",
}


def _normalize_firecrawl_formats(
    formats: Optional[List[Any]],
    json_schema: Optional[Dict[str, Any]] = None,
) -> tuple[List[Any], List[str]]:
    normalized: List[Any] = []
    dropped: List[str] = []

    for entry in formats or []:
        if isinstance(entry, str):
            if entry in _FIRECRAWL_ALLOWED_FORMATS:
                normalized.append(entry)
            elif entry == "json":
                if json_schema:
                    normalized.append({"type": "json", "schema": json_schema})
                else:
                    dropped.append(entry)
            else:
                dropped.append(entry)
            continue

        if isinstance(entry, dict):
            entry_type = entry.get("type")
            if entry_type == "json":
                schema = entry.get("schema") or json_schema
                if schema:
                    normalized.append({"type": "json", "schema": schema})
                else:
                    dropped.append(json.dumps(entry, default=str))
            elif entry_type == "screenshot":
                normalized.append(entry)
            else:
                dropped.append(json.dumps(entry, default=str))
            continue

        dropped.append(str(entry))

    if json_schema and not any(
        isinstance(item, dict) and item.get("type") == "json" for item in normalized
    ):
        normalized.append({"type": "json", "schema": json_schema})

    return normalized, dropped


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
        "hote inconnu",  # "hôte inconnu" without accent to match logs safely
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


def _maybe_cached_tool_result(cache_key: str) -> Optional[str]:
    if not _tool_cache_enabled():
        return None
    key = _tool_cache_key(cache_key)
    # Check Redis first for multi-process coherence
    if _REDIS_CACHE is not None:
        try:
            val = _REDIS_CACHE.get(key)
            if val:
                return val
        except Exception:
            pass
    return _TOOL_CACHE.get(key)


def _store_tool_result(cache_key: str, value: str) -> None:
    if not _tool_cache_enabled():
        return
    key = _tool_cache_key(cache_key)
    if len(_TOOL_CACHE) >= _TOOL_CACHE_MAX:
        _TOOL_CACHE.pop(next(iter(_TOOL_CACHE)), None)
    _TOOL_CACHE[key] = value
    if _REDIS_CACHE is not None:
        try:
            _REDIS_CACHE.setex(key, 900, value)  # 15-minute TTL for tool cache
        except Exception:
            pass


async def _http_fetch_fallback(url: str, max_chars: int = 8000) -> Dict[str, Any]:
    """Best-effort HTML fetch when Firecrawl is unavailable."""

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    # SSRF protection: validate URL before fetching
    is_safe, reason = _is_safe_url(url)
    if not is_safe:
        logger.warning(f"SSRF protection blocked URL: {url} - {reason}")
        return {"error": f"URL blocked for security reasons: {reason}", "url": url}

    cache_key = f"fetch:{url}"
    cached = _maybe_cached_tool_result(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    _cache_hit_miss(False, cache_key)

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()

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

    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip()

    payload = {
        "url": str(resp.url),
        "status_code": resp.status_code,
        "content_type": content_type,
        "title": (title or "").strip() or url,
        "content": cleaned[:max_chars],
        "source": "httpx_fallback",
    }
    _store_tool_result(cache_key, _serialize_tool_output(payload))
    _cache_hit_miss(False, cache_key)  # False = cache miss (we stored new data)
    return payload


async def _grounding_fallback(
    query: str, max_results: int, reason: str
) -> Dict[str, Any]:
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
    """Enhanced web search input with full Tavily API support."""

    query: str = Field(..., description="Natural language query to research.")
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of URLs to return.",
    )
    include_images: bool = Field(
        default=True,
        description="Whether to include image results in the response.",
    )
    # NEW: Advanced Tavily features
    search_depth: str = Field(
        default="advanced",
        description="Search depth: 'basic' for quick results, 'advanced' for comprehensive search.",
    )
    include_domains: Optional[List[str]] = Field(
        default=None,
        description="Only return results from these domains (e.g., ['wikipedia.org', 'github.com']).",
    )
    exclude_domains: Optional[List[str]] = Field(
        default=None,
        description="Exclude results from these domains.",
    )
    days: Optional[int] = Field(
        default=None,
        ge=1,
        description="Limit results to last N days. Useful for recent news/events.",
    )
    topic: Optional[str] = Field(
        default=None,
        description="Search topic: 'general' or 'news' for topic-specific results.",
    )


class TavilyExtractInput(BaseModel):
    """Input schema for Tavily extract (full-content fetch)."""

    urls: List[str] = Field(
        ...,
        description="URLs to extract content from (max 10).",
    )


class GroundingSearchInput(BaseModel):
    query: str = Field(
        ..., description="Query to send through Gemini Search Grounding."
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of grounded evidence chunks to return.",
    )


class FeedMeSearchInput(BaseModel):
    query: str = Field(
        ..., description="Natural language query to search FeedMe conversations."
    )
    max_results: int = Field(
        default=5, ge=1, le=10, description="Maximum conversations to surface."
    )
    folder_id: Optional[int] = Field(
        default=None, description="Optional FeedMe folder filter."
    )
    start_date: Optional[datetime] = Field(
        default=None, description="Only include conversations on/after this ISO date."
    )
    end_date: Optional[datetime] = Field(
        default=None, description="Only include conversations on/before this ISO date."
    )


class SupabaseQueryInput(BaseModel):
    table: str = Field(..., description="Whitelisted table to query via Supabase.")
    filters: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Field→operations map (eq/gte/lte/ilike/in).",
    )
    limit: int = Field(default=20, ge=1, le=100, description="Max rows to return.")
    order_by: Optional[str] = Field(
        default=None, description="Optional column to order by."
    )
    ascending: bool = Field(
        default=True, description="Order direction when order_by is set."
    )


# --- Database Retrieval Subagent Input Schemas ---


class DbUnifiedSearchInput(BaseModel):
    """Unified semantic search across all internal sources."""

    query: str = Field(..., description="Natural language search query")
    sources: List[str] = Field(
        default=["kb", "macros", "feedme"],
        description="Sources to search: kb, macros, feedme",
    )
    max_results_per_source: int = Field(default=5, ge=1, le=10)
    min_relevance: float = Field(default=0.3, ge=0.0, le=1.0)


class DbGrepSearchInput(BaseModel):
    """Pattern-based text search (like grep) for precise matching."""

    pattern: str = Field(..., description="Text pattern or regex to search for")
    sources: List[str] = Field(
        default=["kb", "macros", "feedme"],
        description="Sources to search: kb, macros, feedme",
    )
    case_sensitive: bool = Field(default=False, description="Case-sensitive matching")
    max_results: int = Field(default=10, ge=1, le=20)


class DbContextSearchInput(BaseModel):
    """Retrieve full document and surrounding context by ID."""

    source: str = Field(..., description="Source type: kb, macro, or feedme")
    doc_id: str = Field(..., description="Document ID to retrieve")


def _serialize_tool_output(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        return str(payload)


def _tool_cache_enabled() -> bool:
    return os.getenv("DISABLE_TOOL_CACHE") not in {"1", "true", "True"}


def _cache_hit_miss(hit: bool, key: str) -> None:
    logger.info("tool_cache_hit" if hit else "tool_cache_miss", key=key)


async def _invoke_firecrawl_mcp_tool(
    tool_name: str, args: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    try:
        return await invoke_firecrawl_mcp_tool(
            tool_name, args, api_key=settings.firecrawl_api_key
        )
    except Exception as exc:
        logger.warning("mcp_tool_failed", tool_name=tool_name, error=str(exc))
        return None


@lru_cache(maxsize=2048)
def _tool_cache_key(key: str) -> str:
    # Wrapper to keep lru_cache hot; key already hashed upstream
    return key


def _trim_content(content: str, max_chars: int = 500) -> str:
    snippet = (content or "").strip()
    if len(snippet) <= max_chars:
        return snippet
    return snippet[: max_chars - 1].rstrip() + "…"


def _dedupe_results(
    results: list[dict],
    id_key: str = "id",
    url_key: str = "url",
    key_func: Optional[Callable[[dict], Any]] = None,
) -> list[dict]:
    """Deduplicate results by id/url or custom key, keeping the first occurrence."""
    seen = set()
    deduped: list[dict] = []
    for item in results:
        key = key_func(item) if key_func else (item.get(id_key) or item.get(url_key))
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(item)
    return deduped


@tool("kb_search", args_schema=EnhancedKBSearchInput)
async def kb_search_tool(
    query: str,
    context: Optional[Dict[str, Any]] = None,
    max_results: int = 5,
    search_sources: Optional[List[str]] = None,
    min_confidence: Optional[float] = None,
    state: Annotated[Optional[GraphState], InjectedState] = None,
    runtime: Optional[ToolRuntime] = None,
) -> str:
    """Search the Mailbird knowledge base via hybrid vector/text retrieval."""

    session_id = getattr(state, "session_id", "default")
    if runtime and getattr(runtime, "stream_writer", None):
        runtime.stream_writer.write("Searching knowledge base…")

    sources = search_sources or ["knowledge_base"]
    if "knowledge_base" not in sources:
        logger.info("kb_search skipped because knowledge_base not requested")
        return _serialize_tool_output(
            {
                "query": query,
                "results": [],
                "reason": "knowledge_base_not_requested",
                "session_id": session_id,
            }
        )

    retriever = _hybrid_retriever()
    filters = _build_kb_filters(context or {})
    effective_query = _rewrite_search_query(query)

    cache_hit_key = f"kb:{effective_query}:{filters}:{max_results}:{min_confidence}"
    cached = _maybe_cached_tool_result(cache_hit_key)
    if cached:
        _cache_hit_miss(True, cache_hit_key)
        return cached
    _cache_hit_miss(False, cache_hit_key)

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
        "session_id": session_id,
    }
    serialized = _serialize_tool_output(payload)
    _store_tool_result(cache_hit_key, serialized)
    return serialized


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
    offset: int = Field(
        default=0,
        ge=0,
        description="Optional line offset for large logs to keep prompts small.",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional max number of lines to include from the log (applied after offset).",
    )


class FirecrawlLocationInput(BaseModel):
    """Location configuration for geo-targeted scraping."""

    country: Optional[str] = Field(
        default=None,
        description="Country code for geo-targeted requests (e.g., 'us', 'uk', 'de').",
    )
    languages: Optional[List[str]] = Field(
        default=None,
        description="Preferred languages for content (e.g., ['en', 'de']).",
    )


class FirecrawlFetchInput(BaseModel):
    """Enhanced input schema for Firecrawl fetch with advanced options.

    Supports all MCP features including mobile scraping, geographic targeting,
    branding extraction, PDF parsing, and built-in caching via maxAge.
    """

    url: str = Field(..., description="URL to scrape for detailed content.")
    formats: Optional[List[str]] = Field(
        default=None,
        description="Output formats: markdown, html, screenshot, links, rawHtml, branding, summary. Default: ['markdown']",
    )
    actions: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Page actions before scraping: [{type: 'click'|'scroll'|'wait'|'write'|'press'|'screenshot'|'executeJavascript', ...}]",
    )
    wait_for: Optional[int] = Field(
        default=None,
        description="Wait time in milliseconds for dynamic content to load.",
    )
    only_main_content: bool = Field(
        default=True,
        description="Extract main content only, filtering out navigation/ads.",
    )
    json_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="JSON schema for structured extraction (enables JSON mode).",
    )
    # NEW: MCP-enabled features
    mobile: bool = Field(
        default=False,
        description="Use mobile user agent and viewport for scraping.",
    )
    location: Optional[FirecrawlLocationInput] = Field(
        default=None,
        description="Geographic location for geo-targeted scraping.",
    )
    max_age: Optional[int] = Field(
        default=172800000,  # 48 hours in ms
        description="Max age in milliseconds for cached results. Use for 500% faster scrapes.",
    )
    proxy: Optional[str] = Field(
        default=None,
        description="Proxy mode: 'basic', 'stealth', or 'auto'. Use 'stealth' for anti-bot sites.",
    )
    parsers: Optional[List[str]] = Field(
        default=None,
        description="Content parsers: ['pdf'] for PDF documents.",
    )
    remove_base64_images: bool = Field(
        default=False,
        description="Remove base64 encoded images to reduce response size.",
    )


class FirecrawlMapInput(BaseModel):
    """Input schema for Firecrawl map (URL discovery)."""

    url: str = Field(..., description="Base URL to map and discover all pages.")
    limit: int = Field(
        default=100, ge=1, le=1000, description="Maximum URLs to discover."
    )
    search: Optional[str] = Field(
        default=None, description="Filter URLs containing this string."
    )
    include_subdomains: bool = Field(
        default=False, description="Include subdomains in results."
    )


class FirecrawlCrawlInput(BaseModel):
    """Input schema for Firecrawl crawl (multi-page extraction)."""

    url: str = Field(..., description="Starting URL to crawl.")
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Max pages to crawl. <=10 is sync, >10 is async.",
    )
    max_depth: int = Field(
        default=2, ge=1, le=5, description="Maximum link depth to follow."
    )
    include_paths: Optional[List[str]] = Field(
        default=None,
        description="Only crawl paths matching these patterns (e.g., ['/blog/*']).",
    )
    exclude_paths: Optional[List[str]] = Field(
        default=None,
        description="Skip paths matching these patterns (e.g., ['/admin/*']).",
    )


class FirecrawlCrawlStatusInput(BaseModel):
    """Input schema for checking async crawl status."""

    crawl_id: str = Field(..., description="Crawl job ID from async crawl.")


class FirecrawlExtractInput(BaseModel):
    """Input schema for Firecrawl extract (AI-powered structured extraction)."""

    model_config = ConfigDict(populate_by_name=True)

    urls: List[str] = Field(..., description="URLs to extract data from.")
    prompt: Optional[str] = Field(
        default=None,
        description="Natural language extraction prompt (e.g., 'Extract product prices').",
    )
    extraction_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="schema",
        description="JSON schema for structured extraction.",
    )
    enable_web_search: bool = Field(
        default=False, description="Enable web search for additional context."
    )

    @model_validator(mode="after")
    def validate_prompt_or_schema(self):
        if not self.prompt and not self.extraction_schema:
            raise ValueError(
                "Either 'prompt' or 'extraction_schema' must be provided for extraction."
            )
        return self


class FirecrawlSearchInput(BaseModel):
    """Input schema for Firecrawl enhanced search."""

    query: str = Field(..., description="Search query string.")
    limit: int = Field(default=5, ge=1, le=10, description="Maximum number of results.")
    sources: List[str] = Field(
        default=["web"], description="Sources to search: web, images, news."
    )
    scrape_options: Optional[Dict[str, Any]] = Field(
        default=None, description="Options for scraping search results."
    )


class FirecrawlAgentInput(BaseModel):
    """Input schema for Firecrawl autonomous agent.

    The Firecrawl Agent is a powerful autonomous data gathering tool that can
    search, navigate, and extract data without knowing URLs upfront. Use this
    for complex research tasks where you don't know which pages contain the info.
    """

    model_config = ConfigDict(populate_by_name=True)

    prompt: str = Field(
        ...,
        description="Natural language description of what data you want to gather. Be specific about the information needed.",
        max_length=10000,
    )
    urls: Optional[List[str]] = Field(
        default=None,
        description="Optional starting URLs to focus the agent on specific pages.",
    )
    output_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="schema",
        description="Optional JSON schema for structured output format.",
    )


class FirecrawlAgentStatusInput(BaseModel):
    """Input schema for checking Firecrawl agent job status."""

    agent_id: str = Field(..., description="Agent job ID from firecrawl_agent call.")


@tool("log_diagnoser", args_schema=LogDiagnoserInput)
async def log_diagnoser_tool(
    input: Optional[LogDiagnoserInput] = None,
    log_content: Optional[str] = None,
    question: Optional[str] = None,
    trace_id: Optional[str] = None,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
    state: Annotated[Optional[GraphState], InjectedState] = None,
    runtime: Optional[ToolRuntime] = None,
) -> Dict[str, Any]:
    """Analyze application logs and return targeted diagnostics with error handling.

    Supports both structured invocation with a LogDiagnoserInput object and
    direct kwargs (log_content, question, trace_id) so that LangChain/DeepAgents
    tool calls that pass raw arguments continue to work. For large logs, supply
    offset/limit to paginate the content client-side before sending to the model.
    """

    # Normalize inputs regardless of how the tool is invoked
    effective_trace_id = trace_id or getattr(state, "trace_id", None)
    if runtime and getattr(runtime, "stream_writer", None):
        runtime.stream_writer.write("Analyzing logs…")

    if input is None:
        input = LogDiagnoserInput(
            log_content=log_content or "",
            question=question,
            trace_id=effective_trace_id,
            offset=offset or 0,
            limit=limit,
        )
    elif effective_trace_id and not input.trace_id:
        # Propagate trace_id from injected state when caller did not supply one
        input.trace_id = effective_trace_id
    # Normalize offset/limit from either args_schema or fallback kwargs
    if log_content is not None and input.log_content == (log_content or ""):
        input.offset = input.offset or 0
        input.limit = input.limit
    elif log_content is None and input.offset is None:
        input.offset = 0
    # Apply pagination slicing if provided
    lines = input.log_content.splitlines()
    start = max(input.offset or 0, 0)
    end = start + input.limit if input.limit else None
    sliced = "\n".join(lines[start:end]) if lines else input.log_content

    try:
        state = SimplifiedAgentState(
            raw_log_content=sliced,
            question=input.question,
            trace_id=input.trace_id or effective_trace_id,
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
            "suggestion": "Please check the log format and try again.",
        }


@tool("web_search", args_schema=WebSearchInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def web_search_tool(
    input: Optional[WebSearchInput] = None,
    query: Optional[str] = None,
    max_results: int = 5,
    include_images: bool = True,
    search_depth: str = "advanced",
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    days: Optional[int] = None,
    topic: Optional[str] = None,
) -> Dict[str, Any]:
    """Search the public web using Tavily for broader context with retry logic.

    Supports both structured invocation with a WebSearchInput object and
    direct kwargs (query, max_results, include_images, etc.) so that LangChain/DeepAgents
    tool calls that pass raw arguments continue to work.

    Args:
        input: Structured WebSearchInput object (preferred)
        query: Search query string
        max_results: Maximum results to return (1-10)
        include_images: Include image results
        search_depth: "basic" for quick, "advanced" for comprehensive (default: advanced)
        include_domains: Only search these domains
        exclude_domains: Exclude these domains from results
        days: Limit to results from last N days
        topic: "general" or "news" for topic-specific search

    Returns a dict containing:
    - query: The search query
    - results: List of search result objects
    - urls: List of result URLs
    - images: List of image objects with url, alt, source, width, height
    - attribution: Attribution from the search provider
    """

    # Normalize inputs regardless of how the tool is invoked
    if input is None:
        input = WebSearchInput(
            query=query or "",
            max_results=max_results,
            include_images=include_images,
            search_depth=search_depth,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            days=days,
            topic=topic,
        )

    max_retries = 3
    tavily = _tavily_client()

    # Include all search parameters in cache key for proper cache isolation
    cache_key = (
        f"web_search:{input.query}:{input.max_results}:{input.include_images}"
        f":{input.search_depth}:{input.include_domains}:{input.exclude_domains}"
        f":{input.days}:{input.topic}"
    )
    cached = _maybe_cached_tool_result(cache_key)
    if cached:
        _cache_hit_miss(True, cache_key)
        try:
            return json.loads(cached)
        except Exception:
            return cached
    _cache_hit_miss(False, cache_key)

    for attempt in range(max_retries):
        try:
            logger.info(
                f"web_search_tool_invoked query='{input.query}' max_results={input.max_results} "
                f"search_depth={input.search_depth} days={input.days} attempt={attempt + 1}"
            )
            result = await asyncio.to_thread(
                tavily.search,
                input.query,
                input.max_results,
                input.include_images,
                input.search_depth,
                input.include_domains,
                input.exclude_domains,
                input.days,
                input.topic,
            )
            urls = result.get("urls") if isinstance(result, dict) else None
            images = result.get("images") if isinstance(result, dict) else None
            logger.info(
                f"web_search_tool_success query='{input.query}' urls={len(urls or [])} images={len(images or [])}"
            )
            _store_tool_result(cache_key, _serialize_tool_output(result))
            return result
        except Exception as e:
            if attempt == max_retries - 1:
                logger.warning("web_search_tool_failed", error=str(e))
                try:
                    fallback_sources = (
                        ["web", "news", "images"]
                        if input.include_images
                        else ["web", "news"]
                    )
                    fallback = await firecrawl_search_tool(
                        input=FirecrawlSearchInput(
                            query=input.query,
                            limit=input.max_results,
                            sources=fallback_sources,
                        )
                    )
                    if isinstance(fallback, dict) and not fallback.get("error"):
                        return fallback
                except Exception as fallback_exc:
                    logger.error(
                        "web_search_firecrawl_fallback_failed", error=str(fallback_exc)
                    )
                return {
                    "error": "web_search_failed",
                    "message": str(e),
                    "query": input.query,
                }
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff


@tool("tavily_extract", args_schema=TavilyExtractInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def tavily_extract_tool(
    input: Optional[TavilyExtractInput] = None,
    urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Extract full page content for a list of URLs using Tavily."""

    if input is None:
        input = TavilyExtractInput(urls=urls or [])

    tavily = _tavily_client()
    try:
        logger.info("tavily_extract_tool_invoked", url_count=len(input.urls))
        result = await asyncio.to_thread(tavily.extract, input.urls)
        logger.info("tavily_extract_tool_success", url_count=len(input.urls))
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(result["error"])
        return result
    except Exception as e:
        logger.error("tavily_extract_tool_error", error=str(e))
        return {"error": str(e), "urls": input.urls}


@tool("grounding_search", args_schema=GroundingSearchInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def grounding_search_tool(
    input: Optional[GroundingSearchInput] = None,
    query: Optional[str] = None,
    max_results: int = 5,
    state: Annotated[Optional[GraphState], InjectedState] = None,
    runtime: Optional[ToolRuntime] = None,
) -> Dict[str, Any]:
    """Call Gemini Search Grounding with automatic Tavily/Firecrawl fallback.

    Like web_search_tool, this accepts either a structured GroundingSearchInput
    instance or raw kwargs (query, max_results), so tool calls remain robust
    regardless of how arguments are passed.
    """

    if input is None:
        input = GroundingSearchInput(query=query or "", max_results=max_results)

    try:
        if runtime and getattr(runtime, "stream_writer", None):
            runtime.stream_writer.write("Running grounding search…")
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
        return await _grounding_fallback(
            input.query, input.max_results, reason="empty_results"
        )
    except QuotaExceededError as exc:
        logger.warning("grounding_search_quota", error=str(exc))
        return await _grounding_fallback(
            input.query, input.max_results, reason="quota_exceeded"
        )
    except GroundingUnavailableError as exc:
        logger.info("grounding_search_unavailable", error=str(exc))
        return await _grounding_fallback(
            input.query, input.max_results, reason="unavailable"
        )
    except GroundingServiceError as exc:
        logger.warning("grounding_search_error", error=str(exc))
        return await _grounding_fallback(
            input.query, input.max_results, reason="service_error"
        )


@tool("firecrawl_fetch", args_schema=FirecrawlFetchInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def firecrawl_fetch_tool(
    input: Optional[FirecrawlFetchInput] = None,
    url: Optional[str] = None,
    formats: Optional[List[str]] = None,
    actions: Optional[List[Dict[str, Any]]] = None,
    wait_for: Optional[int] = None,
    only_main_content: bool = True,
    json_schema: Optional[Dict[str, Any]] = None,
    mobile: Optional[bool] = None,
    location: Optional[FirecrawlLocationInput] = None,
    max_age: Optional[int] = None,
    proxy: Optional[str] = None,
    parsers: Optional[List[str]] = None,
    remove_base64_images: Optional[bool] = None,
) -> Dict[str, Any]:
    """Fetch and scrape URL with advanced options (screenshots, actions, JSON mode).

    Supports both structured invocation with a FirecrawlFetchInput object and
    direct kwargs so that LangChain/DeepAgents tool calls work regardless of
    how arguments are passed.

    Features:
    - Multiple output formats: markdown, html, screenshot, links, rawHtml
    - Page actions: click, scroll, wait, write, press before scraping
    - JSON mode: Extract structured data with schema
    - Dynamic content: Wait for JS-rendered content
    """

    if input is None:
        input = FirecrawlFetchInput(
            url=url or "",
            formats=formats,
            actions=actions,
            wait_for=wait_for,
            only_main_content=only_main_content,
            json_schema=json_schema,
            mobile=bool(mobile) if mobile is not None else False,
            location=location,
            max_age=max_age,
            proxy=proxy,
            parsers=parsers,
            remove_base64_images=bool(remove_base64_images)
            if remove_base64_images is not None
            else False,
        )

    max_retries = 3
    firecrawl = _firecrawl_client()

    # Determine if we need advanced scraping or basic
    use_advanced = bool(
        input.formats
        or input.actions
        or input.wait_for
        or input.json_schema
        or input.mobile
        or input.location
        or input.max_age is not None
        or input.proxy
        or input.parsers
        or input.remove_base64_images
    )

    resolved_formats, dropped_formats = _normalize_firecrawl_formats(
        list(input.formats) if input.formats else None,
        json_schema=input.json_schema,
    )
    if dropped_formats:
        logger.warning(
            "firecrawl_formats_filtered",
            dropped=dropped_formats,
        )

    location_payload: Optional[Dict[str, Any]] = None
    if input.location:
        if hasattr(input.location, "model_dump"):
            location_payload = input.location.model_dump(exclude_none=True)
        else:
            location_payload = dict(input.location)  # type: ignore[arg-type]

    mcp_formats = resolved_formats or None

    mcp_args = {
        "url": input.url,
        "formats": mcp_formats,
        "actions": input.actions,
        "waitFor": input.wait_for,
        "onlyMainContent": input.only_main_content,
        "mobile": input.mobile,
        "location": location_payload,
        "maxAge": input.max_age,
        "proxy": input.proxy,
        "parsers": input.parsers,
        "removeBase64Images": input.remove_base64_images,
    }
    mcp_args = {k: v for k, v in mcp_args.items() if v not in (None, [], {})}

    mcp_result = await _invoke_firecrawl_mcp_tool("firecrawl_scrape", mcp_args)
    if mcp_result is not None:
        if isinstance(mcp_result, dict) and (
            mcp_result.get("error") or mcp_result.get("success") is False
        ):
            logger.warning("firecrawl_mcp_scrape_error", error=mcp_result.get("error"))
        else:
            return mcp_result

    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            logger.info(
                f"firecrawl_fetch_tool_invoked url='{input.url}' advanced={use_advanced} attempt={attempt + 1}"
            )

            if use_advanced:
                result = await asyncio.to_thread(
                    firecrawl.scrape_with_options,
                    input.url,
                    formats=resolved_formats or None,
                    actions=input.actions,
                    wait_for=input.wait_for,
                    only_main_content=input.only_main_content,
                    json_schema=input.json_schema,
                    mobile=input.mobile,
                    location=location_payload,
                    max_age=input.max_age,
                    proxy=input.proxy,
                    parsers=input.parsers,
                    remove_base64_images=input.remove_base64_images,
                )
            else:
                # Use fetch as default for grounding to reduce Gemini grounding calls in Zendesk flows
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


@tool("firecrawl_map", args_schema=FirecrawlMapInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def firecrawl_map_tool(
    input: Optional[FirecrawlMapInput] = None,
    url: Optional[str] = None,
    limit: int = 100,
    search: Optional[str] = None,
    include_subdomains: bool = False,
) -> Dict[str, Any]:
    """Discover all URLs on a website quickly.

    Use this tool to:
    - Map a website's structure before selective scraping
    - Find all pages matching a pattern (e.g., blog posts, products)
    - Discover sitemaps and subpages

    Returns a list of discovered URLs.
    """

    if input is None:
        input = FirecrawlMapInput(
            url=url or "",
            limit=limit,
            search=search,
            include_subdomains=include_subdomains,
        )

    firecrawl = _firecrawl_client()

    try:
        mcp_args = {
            "url": input.url,
            "limit": input.limit,
            "search": input.search,
            "includeSubdomains": input.include_subdomains,
        }
        mcp_args = {k: v for k, v in mcp_args.items() if v not in (None, [], {})}
        mcp_result = await _invoke_firecrawl_mcp_tool("firecrawl_map", mcp_args)
        if mcp_result is not None:
            if isinstance(mcp_result, dict) and (
                mcp_result.get("error") or mcp_result.get("success") is False
            ):
                logger.warning("firecrawl_mcp_map_error", error=mcp_result.get("error"))
            else:
                return mcp_result

        logger.info(
            f"firecrawl_map_tool_invoked url='{input.url}' limit={input.limit} search='{input.search}'"
        )
        result = await asyncio.to_thread(
            firecrawl.map_website,
            input.url,
            limit=input.limit,
            search=input.search,
            include_subdomains=input.include_subdomains,
        )
        urls_found = 0
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, dict):
                urls_found = len(data.get("links") or [])
            else:
                urls_found = len(result.get("links") or result.get("urls") or [])
        logger.info(
            f"firecrawl_map_tool_success url='{input.url}' urls_found={urls_found}"
        )
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(result["error"])
        return result
    except Exception as e:
        logger.error(f"firecrawl_map_tool_error url='{input.url}' error='{str(e)}'")
        return {"error": str(e)}


@tool("firecrawl_crawl", args_schema=FirecrawlCrawlInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def firecrawl_crawl_tool(
    input: Optional[FirecrawlCrawlInput] = None,
    url: Optional[str] = None,
    limit: int = 10,
    max_depth: int = 2,
    include_paths: Optional[List[str]] = None,
    exclude_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Crawl a website and extract content from multiple pages.

    Behavior:
    - limit <= 10: Synchronous crawl (waits for completion, returns results)
    - limit > 10: Async crawl (returns crawl_id for status polling)

    Use firecrawl_crawl_status to check progress of async crawls.
    """

    if input is None:
        input = FirecrawlCrawlInput(
            url=url or "",
            limit=limit,
            max_depth=max_depth,
            include_paths=include_paths,
            exclude_paths=exclude_paths,
        )

    mcp_args = {
        "url": input.url,
        "limit": input.limit,
        "maxDiscoveryDepth": input.max_depth,
        "includePaths": input.include_paths,
        "excludePaths": input.exclude_paths,
    }
    mcp_args = {k: v for k, v in mcp_args.items() if v not in (None, [], {})}
    mcp_result = await _invoke_firecrawl_mcp_tool("firecrawl_crawl", mcp_args)
    if mcp_result is not None:
        if isinstance(mcp_result, dict) and (
            mcp_result.get("error") or mcp_result.get("success") is False
        ):
            logger.warning("firecrawl_mcp_crawl_error", error=mcp_result.get("error"))
        else:
            return mcp_result

    firecrawl = _firecrawl_client()

    try:
        logger.info(
            f"firecrawl_crawl_tool_invoked url='{input.url}' limit={input.limit} max_depth={input.max_depth}"
        )
        result = await asyncio.to_thread(
            firecrawl.crawl,
            input.url,
            limit=input.limit,
            max_depth=input.max_depth,
            include_paths=input.include_paths,
            exclude_paths=input.exclude_paths,
        )
        logger.info(
            f"firecrawl_crawl_tool_success url='{input.url}' status={result.get('status', 'unknown')}"
        )
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(result["error"])
        return result
    except Exception as e:
        logger.error(f"firecrawl_crawl_tool_error url='{input.url}' error='{str(e)}'")
        return {"error": str(e)}


@tool("firecrawl_crawl_status", args_schema=FirecrawlCrawlStatusInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def firecrawl_crawl_status_tool(
    input: Optional[FirecrawlCrawlStatusInput] = None,
    crawl_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Check the status and get results of an async crawl job.

    Use this after starting an async crawl (limit > 10) to:
    - Check if crawl is still running
    - Get partial or complete results
    - Monitor progress
    """

    if input is None:
        input = FirecrawlCrawlStatusInput(crawl_id=crawl_id or "")

    mcp_result = await _invoke_firecrawl_mcp_tool(
        "firecrawl_check_crawl_status", {"id": input.crawl_id}
    )
    if mcp_result is not None:
        if isinstance(mcp_result, dict) and (
            mcp_result.get("error") or mcp_result.get("success") is False
        ):
            logger.warning(
                "firecrawl_mcp_crawl_status_error", error=mcp_result.get("error")
            )
        else:
            return mcp_result

    firecrawl = _firecrawl_client()

    try:
        logger.info(f"firecrawl_crawl_status_tool_invoked crawl_id='{input.crawl_id}'")
        result = await asyncio.to_thread(firecrawl.get_crawl_status, input.crawl_id)
        logger.info(
            f"firecrawl_crawl_status_tool_success crawl_id='{input.crawl_id}' status={result.get('status', 'unknown') if isinstance(result, dict) else 'unknown'}"
        )
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(result["error"])
        return result
    except Exception as e:
        logger.error(
            f"firecrawl_crawl_status_tool_error crawl_id='{input.crawl_id}' error='{str(e)}'"
        )
        return {"error": str(e)}


@tool("firecrawl_extract", args_schema=FirecrawlExtractInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def firecrawl_extract_tool(
    input: Optional[FirecrawlExtractInput] = None,
    urls: Optional[List[str]] = None,
    prompt: Optional[str] = None,
    schema: Optional[Dict[str, Any]] = None,
    enable_web_search: bool = False,
) -> Dict[str, Any]:
    """Extract structured data from web pages using AI.

    Use this tool to:
    - Extract specific information (prices, contacts, specs)
    - Convert unstructured content to structured data
    - Get data in a specific JSON schema format

    Either 'prompt' or 'schema' must be provided.
    """

    if input is None:
        input = FirecrawlExtractInput(
            urls=urls or [],
            prompt=prompt,
            schema=schema,
            enable_web_search=enable_web_search,
        )

    mcp_args = {
        "urls": input.urls,
        "prompt": input.prompt,
        "schema": input.extraction_schema,
        "enableWebSearch": input.enable_web_search,
    }
    mcp_args = {k: v for k, v in mcp_args.items() if v not in (None, [], {})}
    mcp_result = await _invoke_firecrawl_mcp_tool("firecrawl_extract", mcp_args)
    if mcp_result is not None:
        if isinstance(mcp_result, dict) and (
            mcp_result.get("error") or mcp_result.get("success") is False
        ):
            logger.warning(
                "firecrawl_mcp_extract_error", error=mcp_result.get("error")
            )
        else:
            return mcp_result

    firecrawl = _firecrawl_client()

    try:
        logger.info(
            f"firecrawl_extract_tool_invoked urls={len(input.urls)} has_prompt={bool(input.prompt)} has_schema={bool(input.extraction_schema)}"
        )
        result = await asyncio.to_thread(
            firecrawl.extract,
            input.urls,
            prompt=input.prompt,
            schema=input.extraction_schema,
            enable_web_search=input.enable_web_search,
        )
        logger.info(f"firecrawl_extract_tool_success urls={len(input.urls)}")
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(result["error"])
        return result
    except Exception as e:
        logger.error(
            f"firecrawl_extract_tool_error urls={len(input.urls)} error='{str(e)}'"
        )
        return {"error": str(e)}


@tool("firecrawl_search", args_schema=FirecrawlSearchInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def firecrawl_search_tool(
    input: Optional[FirecrawlSearchInput] = None,
    query: Optional[str] = None,
    limit: int = 5,
    sources: Optional[List[str]] = None,
    scrape_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Search the web with multiple sources (web, images, news).

    Use this tool for:
    - Finding current information across the web
    - Image search with visual results
    - News search for recent events
    - Optionally scrape search result pages for full content
    """

    if input is None:
        input = FirecrawlSearchInput(
            query=query or "",
            limit=limit,
            sources=sources or ["web"],
            scrape_options=scrape_options,
        )

    cleaned_scrape_options = None
    if isinstance(input.scrape_options, dict):
        cleaned_scrape_options = dict(input.scrape_options)
        raw_formats = cleaned_scrape_options.get("formats")
        normalized_formats, dropped_formats = _normalize_firecrawl_formats(raw_formats)
        if dropped_formats:
            logger.warning(
                "firecrawl_search_formats_filtered",
                dropped=dropped_formats,
            )
        if normalized_formats:
            cleaned_scrape_options["formats"] = normalized_formats
        else:
            cleaned_scrape_options.pop("formats", None)
        if not cleaned_scrape_options:
            cleaned_scrape_options = None

    mcp_sources = None
    if input.sources:
        mcp_sources = []
        for source in input.sources:
            if isinstance(source, str):
                mcp_sources.append({"type": source})
            elif isinstance(source, dict) and source.get("type"):
                mcp_sources.append({"type": source["type"]})

    mcp_args = {
        "query": input.query,
        "limit": input.limit,
        "sources": mcp_sources,
        "scrapeOptions": cleaned_scrape_options,
    }
    mcp_args = {k: v for k, v in mcp_args.items() if v not in (None, [], {})}
    mcp_result = await _invoke_firecrawl_mcp_tool("firecrawl_search", mcp_args)
    if mcp_result is not None:
        if isinstance(mcp_result, dict) and (
            mcp_result.get("error") or mcp_result.get("success") is False
        ):
            logger.warning("firecrawl_mcp_search_error", error=mcp_result.get("error"))
        else:
            return mcp_result

    firecrawl = _firecrawl_client()

    try:
        logger.info(
            f"firecrawl_search_tool_invoked query='{input.query}' limit={input.limit} sources={input.sources}"
        )
        result = await asyncio.to_thread(
            firecrawl.search_web,
            input.query,
            limit=input.limit,
            sources=input.sources,
            scrape_options=input.scrape_options,
        )
        results_count = 0
        if isinstance(result, dict):
            data = result.get("data") or {}
            if isinstance(data, dict):
                results_count = len(data.get("web") or [])
        logger.info(
            f"firecrawl_search_tool_success query='{input.query}' results={results_count}"
        )
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(result["error"])
        return result
    except Exception as e:
        logger.error(
            f"firecrawl_search_tool_error query='{input.query}' error='{str(e)}'"
        )
        return {"error": str(e)}


@tool("firecrawl_agent", args_schema=FirecrawlAgentInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def firecrawl_agent_tool(
    input: Optional[FirecrawlAgentInput] = None,
    prompt: Optional[str] = None,
    urls: Optional[List[str]] = None,
    schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Autonomous web data gathering agent - Firecrawl's most powerful feature.

    Use this tool for complex research tasks where you don't know which pages
    contain the information. The agent will:
    - Search the web to find relevant pages
    - Navigate and extract data autonomously
    - Return structured results matching your requirements

    WHEN TO USE:
    - Complex research requiring multiple unknown sources
    - Finding specific data without knowing exact URLs
    - Gathering structured information across many pages
    - When other Firecrawl tools require URLs you don't have

    EXAMPLES:
    - "Find the founders of Firecrawl and their backgrounds"
    - "Gather pricing information for top 5 AI startups"
    - "Extract contact information for tech companies in SF"

    Returns:
    - For quick queries: Immediate results with extracted data
    - For complex queries: {status: 'processing', agent_id: '...'} - use firecrawl_agent_status to check
    """

    if input is None:
        input = FirecrawlAgentInput(
            prompt=prompt or "",
            urls=urls,
            schema=schema,
        )

    if not input.prompt:
        return {"error": "prompt is required for firecrawl_agent"}

    if settings.firecrawl_api_key:
        allowed, used, retry_after = _check_and_record_firecrawl_agent_use()
        if not allowed:
            return {
                "error": "firecrawl_agent_daily_limit_exceeded",
                "message": (
                    "Firecrawl agent usage limit exceeded (free tier is typically 5 uses per 24h). "
                    "Try firecrawl_search + firecrawl_fetch/extract instead, or retry later."
                ),
                "limit": _FIRECRAWL_AGENT_MAX_USES_PER_WINDOW,
                "used": used,
                "retry_after_seconds": retry_after,
            }

    mcp_args = {
        "prompt": input.prompt,
        "urls": input.urls,
        "schema": input.output_schema,
    }
    mcp_args = {k: v for k, v in mcp_args.items() if v not in (None, [], {})}
    mcp_result = await _invoke_firecrawl_mcp_tool("firecrawl_agent", mcp_args)
    if mcp_result is not None:
        if isinstance(mcp_result, dict) and (
            mcp_result.get("error") or mcp_result.get("success") is False
        ):
            logger.warning("firecrawl_mcp_agent_error", error=mcp_result.get("error"))
        else:
            return mcp_result

    firecrawl = _firecrawl_client()

    try:
        logger.info(
            f"firecrawl_agent_tool_invoked prompt='{input.prompt[:100]}...' urls={len(input.urls or [])} has_schema={input.output_schema is not None}"
        )

        # Build agent request
        agent_params: Dict[str, Any] = {"prompt": input.prompt}
        if input.urls:
            agent_params["urls"] = input.urls
        if input.output_schema:
            agent_params["schema"] = input.output_schema

        if not hasattr(firecrawl, "app") or not firecrawl.app:
            return {"error": "firecrawl_disabled"}
        if not hasattr(firecrawl.app, "agent"):
            return {"error": "firecrawl_agent_not_supported"}

        # Call Firecrawl agent API (SDK)
        result = await asyncio.to_thread(firecrawl.app.agent, **agent_params)

        logger.info(
            f"firecrawl_agent_tool_success prompt='{input.prompt[:50]}...' status={result.get('status', 'unknown') if isinstance(result, dict) else 'completed'}"
        )

        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(result["error"])
        return result

    except Exception as e:
        logger.error(
            f"firecrawl_agent_tool_error prompt='{input.prompt[:50]}...' error='{str(e)}'"
        )
        return {"error": str(e)}


@tool("firecrawl_agent_status", args_schema=FirecrawlAgentStatusInput)
@rate_limited(TOOL_RATE_LIMIT_MODEL, fail_gracefully=True)
async def firecrawl_agent_status_tool(
    input: Optional[FirecrawlAgentStatusInput] = None,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Check the status of an async Firecrawl agent job.

    Use this after calling firecrawl_agent when it returns status='processing'.

    Returns:
    - status: 'processing' | 'completed' | 'failed'
    - data: Extracted data (when completed)
    - progress: Progress information (when processing)
    """

    if input is None:
        input = FirecrawlAgentStatusInput(agent_id=agent_id or "")

    if not input.agent_id:
        return {"error": "agent_id is required"}

    mcp_result = await _invoke_firecrawl_mcp_tool(
        "firecrawl_agent_status", {"id": input.agent_id}
    )
    if mcp_result is not None:
        if isinstance(mcp_result, dict) and (
            mcp_result.get("error") or mcp_result.get("success") is False
        ):
            logger.warning(
                "firecrawl_mcp_agent_status_error", error=mcp_result.get("error")
            )
        else:
            return mcp_result

    firecrawl = _firecrawl_client()

    try:
        logger.info(f"firecrawl_agent_status_tool_invoked agent_id='{input.agent_id}'")

        if not hasattr(firecrawl, "app") or not firecrawl.app:
            return {"error": "firecrawl_disabled"}
        if not hasattr(firecrawl.app, "get_agent_status"):
            return {"error": "firecrawl_agent_status_not_supported"}

        # Check agent status
        result = await asyncio.to_thread(
            firecrawl.app.get_agent_status, input.agent_id
        )

        logger.info(
            f"firecrawl_agent_status_tool_success agent_id='{input.agent_id}' status={result.get('status', 'unknown') if isinstance(result, dict) else 'unknown'}"
        )

        return result

    except Exception as e:
        logger.error(
            f"firecrawl_agent_status_tool_error agent_id='{input.agent_id}' error='{str(e)}'"
        )
        return {"error": str(e)}


def get_registered_tools() -> List[BaseTool]:
    """Return the tools bound to the unified agent.

    Tool priority order (FIRECRAWL FIRST for web tasks):

    1. FIRECRAWL (PRIMARY for URLs, scraping, research):
       - firecrawl_fetch: Single page with screenshots, mobile, PDF, branding
       - firecrawl_map: Site structure discovery
       - firecrawl_crawl: Multi-page extraction
       - firecrawl_extract: AI-powered structured extraction
       - firecrawl_search: Multi-source search (web, images, news)
       - firecrawl_agent: Autonomous data gathering (NEW - most powerful!)

    2. TAVILY (for general web search):
       - web_search_tool: Quick web search with images

    3. GEMINI GROUNDING (for quick facts):
       - grounding_search_tool: Fast factual lookups

    Caching:
    - Firecrawl fetch honors max_age for Firecrawl-native caching.
    - In-process cache (256 entries) for other tools; disable via DISABLE_TOOL_CACHE.

    MCP usage:
    - Firecrawl tools attempt MCP first when enabled, then fall back to SDK.
    - Mobile scraping, geo targeting, branding, PDF parsing, proxy modes supported.
    """

    tools: List[BaseTool] = [
        kb_search_tool,
        # Firecrawl tools FIRST - full web scraping and extraction suite
        firecrawl_fetch_tool,  # Single-page: screenshots, mobile, PDF, branding, geo
        firecrawl_map_tool,  # URL discovery with sitemap support
        firecrawl_crawl_tool,  # Multi-page extraction (sync/async)
        firecrawl_crawl_status_tool,  # Async crawl status
        firecrawl_extract_tool,  # AI structured extraction with web search
        firecrawl_search_tool,  # Multi-source search (web, images, news)
        firecrawl_agent_tool,  # NEW: Autonomous data gathering agent
        firecrawl_agent_status_tool,  # NEW: Agent job status
        # Web search tools (secondary)
        web_search_tool,  # Tavily - general web search
        tavily_extract_tool,  # Tavily - full-content extraction
        grounding_search_tool,  # Gemini grounding - quick facts
        # Other tools
        feedme_search_tool,
        supabase_query_tool,
        log_diagnoser_tool,
        generate_image_tool,  # Gemini Nano Banana Pro image generation
        write_article_tool,  # Rich article/report artifact creation
        read_skill_tool,  # Progressive skill disclosure - load full skill on demand
        get_weather,
        generate_task_steps_generative_ui,
    ]
    if settings.trace_mode in {"narrated", "hybrid"}:
        tools.append(trace_update)

    tools.append(write_todos)
    return tools


def get_registered_support_tools() -> List[BaseTool]:
    """Return a minimal, support-focused tool set.

    Intended for contexts like Zendesk where we want:
    - Smaller tool schema payloads (reduces model overhead / quota pressure)
    - Faster, more predictable routing
    """
    return [
        kb_search_tool,
        feedme_search_tool,
        web_search_tool,
        supabase_query_tool,
        log_diagnoser_tool,
    ]


class Step(BaseModel):
    """
    A step in a task.
    """

    description: str = Field(description="The text of the step in gerund form")
    status: str = Field(
        description="The status of the step (pending|in_progress|done), defaults to pending"
    )


class TodoItem(BaseModel):
    """Lightweight todo list entry for planning."""

    id: Optional[str] = Field(
        default=None, description="Stable id for tracking updates."
    )
    title: str = Field(
        description="Short title of the todo item (imperative).", alias="content"
    )
    status: Optional[str] = Field(
        default="pending",
        description="Status of the todo item (normalized to pending|in_progress|done).",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional metadata to display alongside the item."
    )

    model_config = ConfigDict(populate_by_name=True)


class TodoPayload(BaseModel):
    """Relaxed schema used for inbound todo items from tools."""

    id: Optional[str] = Field(
        default=None, description="Stable id for tracking updates."
    )
    title: Optional[str] = Field(
        default=None,
        description="Short title of the todo item (imperative).",
        alias="content",
    )
    description: Optional[str] = Field(
        default=None,
        description="Alternative text field if title/content is not provided.",
    )
    status: Optional[str] = Field(
        default=None,
        description="Status of the todo item (pending|in_progress|done).",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional metadata to display alongside the item."
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @model_validator(mode="before")
    @classmethod
    def coerce_to_dict(cls, value: Any) -> Any:
        """Allow strings or primitives to be coerced into todo dicts."""
        if isinstance(value, dict):
            return value
        if isinstance(value, cls):
            return value
        text = str(value).strip()
        if not text:
            return {"title": ""}
        return {"title": text}


class WriteTodosInput(BaseModel):
    """Flexible input schema for write_todos to tolerate imperfect tool calls.

    Allows the LLM to send either structured todo objects or plain strings,
    and we normalize everything server-side into a consistent shape.
    """

    todos: List[TodoPayload] = Field(
        ...,
        description=(
            "List of todo items. Each item can be an object with title/content/status/id "
            "fields or a plain string describing the task."
        ),
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @field_validator("todos", mode="before")
    @classmethod
    def coerce_todos(cls, value: Any) -> List[Any]:
        """Coerce arbitrary inputs into objects the model schema will accept."""
        if value is None:
            return []
        if isinstance(value, dict):
            # Common case: nested dict accidentally placed directly under todos
            if "todos" in value:
                value = value.get("todos")
        if not isinstance(value, list):
            return [value]

        coerced: List[Any] = []
        for item in value:
            if isinstance(item, (TodoPayload, dict, str)):
                coerced.append(item)
            else:
                coerced.append(str(item))
        return coerced

    @model_validator(mode="before")
    @classmethod
    def normalize_shapes(cls, value: Any) -> Any:
        """Allow nested payloads like {'update': {'todos': [...]}}."""
        # Accept a bare list as the complete todos payload
        if isinstance(value, list):
            return {"todos": value}

        if not isinstance(value, dict):
            return value

        # Flatten common wrappers used by LangChain/LangGraph
        for wrapper_key in ("input", "tool_input", "args", "payload"):
            inner = value.get(wrapper_key)
            if isinstance(inner, dict):
                for key, inner_val in inner.items():
                    if key not in value:
                        value[key] = inner_val

        # Unwrap common nested shapes
        if "update" in value and isinstance(value["update"], dict):
            inner = value["update"]
            if "todos" in inner and "todos" not in value:
                value = {**value, "todos": inner["todos"]}

        # Fallback aliases
        if "todo_list" in value and "todos" not in value:
            value["todos"] = value["todo_list"]

        # If we still didn't get todos, but a single todo-like dict was passed
        if "todos" not in value and {"title", "content", "description"} & set(
            value.keys()
        ):
            value["todos"] = [value]

        # Ensure todos field always exists to avoid validation errors
        if "todos" not in value:
            value["todos"] = []

        return value


class TraceUpdateInput(BaseModel):
    """Structured, user-visible narration for the Progress Updates panel.

    This tool is intentionally lightweight and should NOT dump raw tool outputs.
    """

    title: str = Field(
        ...,
        description="Short heading for the trace update (e.g. 'Checking tool configs').",
    )
    detail: Optional[str] = Field(
        default=None,
        description=(
            "Optional short detail (1-3 sentences). Do not include raw tool outputs."
        ),
    )
    kind: Literal["thought", "phase"] = Field(
        default="thought",
        description="Use 'phase' for major stages (Planning, Working, Writing answer).",
    )
    goal_for_next_tool: Optional[str] = Field(
        default=None,
        alias="goalForNextTool",
        description="Optional label describing the goal of the NEXT tool call.",
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @model_validator(mode="before")
    @classmethod
    def normalize_shapes(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {"title": "Update"}
            return {"title": text}

        if not isinstance(value, dict):
            return value

        # Flatten common wrappers used by LangChain/LangGraph tool calling
        for wrapper_key in ("input", "tool_input", "args", "payload"):
            inner = value.get(wrapper_key)
            if isinstance(inner, dict):
                for key, inner_val in inner.items():
                    if key not in value:
                        value[key] = inner_val

        # Fallback aliases
        if "message" in value and "detail" not in value:
            value["detail"] = value["message"]
        if "phase" in value and "kind" not in value:
            value["kind"] = "phase" if value.get("phase") else "thought"

        return value


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
        List[Step], "An array of 10 step objects, each containing text and status"
    ],
    config: Annotated[RunnableConfig, InjectedToolArg],
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


@tool("trace_update", args_schema=TraceUpdateInput)
def trace_update(
    title: str,
    detail: Optional[str] = None,
    kind: str = "thought",
    goal_for_next_tool: Optional[str] = None,
    **_: Any,
) -> Dict[str, bool]:
    """Emit a user-visible narration/phase update for the Progress Updates panel."""

    return {"ok": True}


@tool("write_todos", args_schema=WriteTodosInput)
def write_todos(todos: List[TodoPayload], **_: Any):
    """Create or update the task todo list displayed to the user.

    Use this tool FREQUENTLY to track your work and show progress to the user.
    Call it:
    - BEFORE starting any multi-step task to plan your approach
    - DURING work to update statuses (pending → in_progress → done)
    - When completing each step to mark it done

    Each todo should have:
    - title: Short, imperative task description (5-10 words)
    - status: 'pending', 'in_progress', or 'done'

    Keep it to 3-6 items. The UI displays these in real-time to the user.
    """

    input = WriteTodosInput(todos=todos)
    normalized: List[Dict[str, Any]] = []
    for idx, raw in enumerate(input.todos):
        item_dict: Dict[str, Any]

        # Preserve already-structured TodoItem instances when present
        if isinstance(raw, TodoItem):
            item_dict = raw.model_dump()
        elif isinstance(raw, TodoPayload):
            item_dict = raw.model_dump()
        elif isinstance(raw, dict):
            item_dict = dict(raw)
        else:
            # Treat plain strings or other primitives as a single pending todo
            text = str(raw).strip()
            if not text:
                continue
            item_dict = {"title": text, "status": "pending"}

        # Normalize title/content fields
        title = (
            item_dict.get("title")
            or item_dict.get("content")
            or item_dict.get("description")
            or f"Step {idx + 1}"
        )
        item_dict["title"] = str(title)

        # Normalize status
        status = str(item_dict.get("status") or "pending").lower()
        if status not in {"pending", "in_progress", "done"}:
            status = "pending"
        item_dict["status"] = status

        # Ensure we always have a stable id
        if not item_dict.get("id"):
            item_dict["id"] = f"todo-{uuid.uuid4().hex[:8]}"

        # Ensure metadata is always a dict when present
        metadata = item_dict.get("metadata")
        if metadata is None:
            item_dict["metadata"] = {}
        elif not isinstance(metadata, dict):
            item_dict["metadata"] = {"raw": str(metadata)}

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
                "last_updated": None,
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
            entry["snippets"].append(_trim_content(redacted_snippet, max_chars=400))
        if not entry["created_at"]:
            entry["created_at"] = row.get("created_at")
        if not entry["last_updated"]:
            entry["last_updated"] = row.get("updated_at")

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
        summary_compact = _summarize_snippets(
            [summary_source] if summary_source else []
        )
        summary = redact_pii(summary_compact or summary_source or "")

        results.append(
            {
                "conversation_id": conv_id,
                "title": details.get("title") or f"Conversation {conv_id}",
                "summary": summary,
                "confidence": payload.get("confidence", 0.0),
                "created_at": created_at,
                "snippet": _trim_content(summary or ""),
                "metadata": {
                    "id": conv_id,
                    "folder_id": details.get("folder_id"),
                    "last_updated": payload.get("last_updated"),
                },
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


# --- Database Retrieval Subagent Tools ---

FEEDME_SUMMARIZE_THRESHOLD = 3000  # Chars threshold for FeedMe summarization


def _format_result_with_content_type(
    source: str,
    title: str,
    content: str,
    relevance_score: float,
    metadata: Dict[str, Any],
    weight: float = 1.0,
) -> Dict[str, Any]:
    """Format a result with content_type indicator for long FeedMe content."""
    content_len = len(content or "")
    snippet = _trim_content(content)
    score = relevance_score * weight if relevance_score is not None else None
    result = {
        "source": source,
        "title": title,
        "snippet": snippet,
        "content": content,
        "content_type": "full",
        "relevance_score": relevance_score,
        "score": score,
        "metadata": metadata,
    }

    # For FeedMe, indicate if content was summarized
    if source == "feedme" and content_len > FEEDME_SUMMARIZE_THRESHOLD:
        result["content_type"] = "summarized"
        result["original_length"] = content_len

    return result


@tool("db_unified_search", args_schema=DbUnifiedSearchInput)
async def db_unified_search_tool(
    query: str,
    sources: Optional[List[str]] = None,
    max_results_per_source: int = 5,
    min_relevance: float = 0.3,
) -> Dict[str, Any]:
    """Semantic search across all database sources in parallel.

    Returns FULL content for KB/macros. For FeedMe >3000 chars,
    marks content_type as 'summarized' to indicate the agent should
    polish it while preserving key details.
    """
    if sources is None:
        sources = ["kb", "macros", "feedme"]
    weights = getattr(
        settings, "db_source_weights", {"kb": 1.0, "macro": 0.9, "feedme": 0.8}
    )

    retrieval_id = f"ret-{uuid.uuid4().hex[:8]}"
    results: List[Dict[str, Any]] = []
    sources_searched: List[str] = []
    no_results_sources: List[str] = []

    client = _supabase_client_cached()
    if getattr(client, "mock_mode", False):
        logger.warning("Supabase mock mode active; db_unified_search returning empty")
        return {
            "retrieval_id": retrieval_id,
            "query_understood": query,
            "sources_searched": sources,
            "results": [],
            "result_count": 0,
            "no_results_sources": sources,
        }

    effective_query = _rewrite_search_query(query)
    emb_model = embedding_utils.get_embedding_model()
    loop = asyncio.get_running_loop()
    query_vec = await loop.run_in_executor(None, emb_model.embed_query, effective_query)

    # Search KB using search_mailbird_knowledge RPC (sync call wrapped in thread)
    if "kb" in sources:
        sources_searched.append("kb")
        try:

            def _search_kb():
                return client.client.rpc(
                    "search_mailbird_knowledge",
                    {
                        "query_embedding": query_vec,
                        "match_count": max_results_per_source,
                        "match_threshold": min_relevance,
                    },
                ).execute()

            kb_results = await asyncio.to_thread(_search_kb)
            kb_rows = kb_results.data or []
            if kb_rows:
                for row in kb_rows[:max_results_per_source]:
                    # Use 'content' or 'markdown' field for full content
                    content = row.get("content") or row.get("markdown") or ""
                    # Extract title from URL if available
                    url = row.get("url", "")
                    title = (
                        url.split("/")[-1].replace("-", " ").title()
                        if url
                        else "KB Article"
                    )
                    results.append(
                        _format_result_with_content_type(
                            source="kb",
                            title=title,
                            content=content,  # Full content
                            relevance_score=float(row.get("similarity", 0.0)),
                            metadata={
                                "id": row.get("id"),
                                "url": url,
                                "last_updated": row.get("updated_at"),
                            },
                            weight=weights.get("kb", 1.0),
                        )
                    )
            else:
                no_results_sources.append("kb")
        except Exception as exc:
            logger.error("DB retrieval KB search failed: %s", exc)
            no_results_sources.append("kb")

    # Search Macros using search_zendesk_macros RPC (sync call wrapped in thread)
    # Note: param order is match_threshold, match_count (different from KB)
    if "macros" in sources:
        sources_searched.append("macros")
        try:

            def _search_macros():
                return client.client.rpc(
                    "search_zendesk_macros",
                    {
                        "query_embedding": query_vec,
                        "match_threshold": min_relevance,
                        "match_count": max_results_per_source,
                    },
                ).execute()

            macro_results = await asyncio.to_thread(_search_macros)
            macro_rows = macro_results.data or []
            if macro_rows:
                for row in macro_rows[:max_results_per_source]:
                    # Full macro content
                    content = row.get("comment_value", "") or row.get("description", "")
                    results.append(
                        _format_result_with_content_type(
                            source="macro",
                            title=row.get("title", "Macro"),
                            content=content,
                            relevance_score=float(row.get("similarity", 0.0)),
                            metadata={
                                "zendesk_id": row.get("zendesk_id"),
                                "last_updated": row.get("updated_at"),
                            },
                            weight=weights.get("macro", 1.0),
                        )
                    )
            else:
                no_results_sources.append("macros")
        except Exception as exc:
            logger.error("DB retrieval macros search failed: %s", exc)

            # Fallback: lightweight full-text search against zendesk_macros table
            # This keeps macros usable even if the semantic RPC is missing/broken.
            try:
                # Build a safe ILIKE pattern from a few sanitized tokens
                safe_query = " ".join((effective_query or "").split()).strip()[:200]
                raw_tokens = safe_query.split()[:5]
                tokens = [re.sub(r"[^a-zA-Z0-9]", "", t) for t in raw_tokens]
                tokens = [t for t in tokens if len(t) >= 2][:3]
                pattern_body = "%".join(tokens)[:200]
                # Neutral fallback when the pattern is empty (avoids hardcoded debug biases).
                pattern = f"%{pattern_body}%" if pattern_body else "%"

                def _search_macros_text():
                    builder = (
                        client.client.table("zendesk_macros")
                        .select("zendesk_id,title,comment_value,usage_30d,updated_at")
                        .order("usage_30d", desc=True)
                    )
                    try:
                        query_builder = builder.or_(
                            f"title.ilike.{pattern},comment_value.ilike.{pattern}"
                        )
                    except Exception:
                        query_builder = builder.ilike("comment_value", pattern)
                    return query_builder.limit(max_results_per_source).execute()

                macro_resp = await asyncio.to_thread(_search_macros_text)
                macro_rows = macro_resp.data or []
                if macro_rows:
                    for row in macro_rows[:max_results_per_source]:
                        content = row.get("comment_value", "") or ""
                        results.append(
                            _format_result_with_content_type(
                                source="macro",
                                title=row.get("title", "Macro"),
                                content=content,
                                relevance_score=0.15,  # fallback (non-semantic) score
                                metadata={
                                    "zendesk_id": row.get("zendesk_id"),
                                    "usage_30d": row.get("usage_30d"),
                                    "last_updated": row.get("updated_at"),
                                    "search_type": "fallback_ilike",
                                },
                                weight=weights.get("macro", 1.0),
                            )
                        )
                else:
                    no_results_sources.append("macros")
            except Exception as inner_exc:
                logger.error(
                    "DB retrieval macros fallback search failed: %s", inner_exc
                )
                no_results_sources.append("macros")

    # Search FeedMe
    if "feedme" in sources:
        sources_searched.append("feedme")
        try:
            feedme_rows = await client.search_text_chunks(
                query_vec,
                match_count=max_results_per_source * 3,
            )
            # Aggregate by conversation
            conv_data: Dict[int, Dict[str, Any]] = {}
            for row in feedme_rows or []:
                conv_id = row.get("conversation_id")
                if conv_id is None:
                    continue
                try:
                    conv_id = int(conv_id)
                except Exception:
                    continue
                if conv_id not in conv_data:
                    conv_data[conv_id] = {
                        "content_parts": [],
                        "max_similarity": 0.0,
                    }
                conv_data[conv_id]["content_parts"].append(row.get("content", ""))
                sim = float(row.get("similarity", 0.0))
                if sim > conv_data[conv_id]["max_similarity"]:
                    conv_data[conv_id]["max_similarity"] = sim

            # Get conversation details and build results
            if conv_data:
                ranked = sorted(
                    conv_data.items(),
                    key=lambda kv: float(kv[1].get("max_similarity") or 0.0),
                    reverse=True,
                )[:max_results_per_source]
                conv_ids = [cid for cid, _ in ranked]
                conv_details = await client.get_conversations_by_ids(conv_ids)

                for conv_id, data in ranked:
                    details = (conv_details or {}).get(conv_id, {})

                    # Fetch FULL conversation chunks (not just matched chunks).
                    chunks: list[dict[str, Any]] = []
                    try:
                        resp = await asyncio.to_thread(
                            lambda: client.client.table("feedme_text_chunks")
                            .select("content, chunk_index")
                            .eq("conversation_id", conv_id)
                            .order("chunk_index")
                            .execute()
                        )
                        chunks = resp.data or []
                    except Exception:
                        chunks = []

                    if chunks:
                        full_content = "\n\n".join(
                            str(chunk.get("content") or "") for chunk in chunks
                        )
                    else:
                        # Fallback: include whatever matched chunks we already have.
                        full_content = "\n\n".join(data["content_parts"])

                    full_content = redact_pii(full_content)

                    results.append(
                        _format_result_with_content_type(
                            source="feedme",
                            title=details.get("title", f"Conversation {conv_id}"),
                            content=full_content,
                            relevance_score=data["max_similarity"],
                            metadata={
                                "id": conv_id,
                                "created_at": details.get("created_at"),
                                "folder_id": details.get("folder_id"),
                                "chunk_count": len(chunks) if chunks else None,
                                "last_updated": details.get("updated_at"),
                            },
                            weight=weights.get("feedme", 1.0),
                        )
                    )
            else:
                no_results_sources.append("feedme")
        except Exception as exc:
            logger.error("DB retrieval FeedMe search failed: %s", exc)
            no_results_sources.append("feedme")

    # Deduplicate and sort by weighted score, fallback to relevance_score
    deduped = _dedupe_results(
        results,
        key_func=lambda r: (r.get("metadata") or {}).get("id")
        or (r.get("metadata") or {}).get("url"),
    )
    deduped.sort(
        key=lambda r: (
            r.get("score", 0.0),
            r.get("relevance_score", 0.0),
        ),
        reverse=True,
    )

    return {
        "retrieval_id": retrieval_id,
        "query_understood": query,
        "sources_searched": sources_searched,
        "results": deduped,
        "result_count": len(deduped),
        "no_results_sources": no_results_sources,
    }


@tool("db_grep_search", args_schema=DbGrepSearchInput)
async def db_grep_search_tool(
    pattern: str,
    sources: Optional[List[str]] = None,
    case_sensitive: bool = False,
    max_results: int = 10,
) -> Dict[str, Any]:
    """Pattern-based text search like grep for exact term matching.

    Use this when you need to find:
    - Exact error messages or codes
    - Specific configuration values
    - Technical terms or identifiers
    - Regex patterns
    """
    if sources is None:
        sources = ["kb", "macros", "feedme"]

    retrieval_id = f"grep-{uuid.uuid4().hex[:8]}"
    results: List[Dict[str, Any]] = []
    sources_searched: List[str] = []

    # Default per-source caps to avoid noisy scans
    kb_limit = max(
        1, min(max_results, getattr(settings, "db_grep_kb_limit", max_results))
    )
    macro_limit = max(
        1, min(max_results, getattr(settings, "db_grep_macro_limit", max_results))
    )
    feedme_limit = max(
        1, min(max_results, getattr(settings, "db_grep_feedme_limit", max_results))
    )

    client = _supabase_client_cached()
    if getattr(client, "mock_mode", False):
        return {
            "retrieval_id": retrieval_id,
            "pattern": pattern,
            "sources_searched": sources,
            "results": [],
            "result_count": 0,
        }

    # Build search pattern for ILIKE or regex
    ilike_pattern = f"%{pattern}%"

    cache_key = f"db_grep:{pattern}:{sources}:{case_sensitive}:{max_results}"
    cached = _maybe_cached_tool_result(cache_key)
    if cached:
        _cache_hit_miss(True, cache_key)
        try:
            return json.loads(cached)
        except Exception:
            return cached
    _cache_hit_miss(False, cache_key)

    # Search KB with text pattern (mailbird_knowledge has: id, url, content, markdown)
    if "kb" in sources:
        sources_searched.append("kb")
        try:
            query_builder = client.client.table("mailbird_knowledge").select(
                "id, url, content, markdown"
            )
            if case_sensitive:
                query_builder = query_builder.like("content", ilike_pattern)
            else:
                query_builder = query_builder.ilike("content", ilike_pattern)
            kb_resp = await asyncio.to_thread(
                lambda: query_builder.limit(kb_limit).execute()
            )
            for row in kb_resp.data or []:
                content = row.get("content") or row.get("markdown") or ""
                url = row.get("url", "")
                # Extract title from URL
                title = (
                    url.split("/")[-1].replace("-", " ").title()
                    if url
                    else "KB Article"
                )
                snippet = _trim_content(content)
                results.append(
                    {
                        "source": "kb",
                        "title": title,
                        "snippet": snippet,
                        "content": content,
                        "content_type": "full",
                        "match_pattern": pattern,
                        "score": None,
                        "metadata": {
                            "id": row.get("id"),
                            "url": url,
                            "last_updated": row.get("updated_at"),
                        },
                    }
                )
        except Exception as exc:
            logger.error("DB grep KB search failed: %s", exc)

    # Search Macros with text pattern
    if "macros" in sources:
        sources_searched.append("macros")
        try:
            query_builder = client.client.table("zendesk_macros").select(
                "zendesk_id, title, comment_value, usage_30d"
            )
            if case_sensitive:
                query_builder = query_builder.like("comment_value", ilike_pattern)
            else:
                query_builder = query_builder.ilike("comment_value", ilike_pattern)
            macro_resp = await asyncio.to_thread(
                lambda: query_builder.limit(macro_limit).execute()
            )
            for row in macro_resp.data or []:
                results.append(
                    {
                        "source": "macro",
                        "title": row.get("title", "Macro"),
                        "snippet": _trim_content(row.get("comment_value", "")),
                        "content": row.get("comment_value", ""),
                        "content_type": "full",
                        "match_pattern": pattern,
                        "score": None,
                        "metadata": {
                            "zendesk_id": row.get("zendesk_id"),
                            "usage_30d": row.get("usage_30d"),
                            "last_updated": row.get("updated_at"),
                        },
                    }
                )
        except Exception as exc:
            logger.error("DB grep macros search failed: %s", exc)

    # Search FeedMe with text pattern
    if "feedme" in sources:
        sources_searched.append("feedme")
        try:
            # Search in feedme_text_chunks for pattern
            query_builder = client.client.table("feedme_text_chunks").select(
                "conversation_id, content"
            )
            if case_sensitive:
                query_builder = query_builder.like("content", ilike_pattern)
            else:
                query_builder = query_builder.ilike("content", ilike_pattern)
            feedme_resp = await asyncio.to_thread(
                lambda: query_builder.limit(feedme_limit * 2).execute()
            )

            # Deduplicate by conversation
            seen_convs: set = set()
            for row in feedme_resp.data or []:
                conv_id = row.get("conversation_id")
                if conv_id in seen_convs:
                    continue
                seen_convs.add(conv_id)
                content = redact_pii(row.get("content", ""))
                snippet = _trim_content(content)
                results.append(
                    {
                        "source": "feedme",
                        "title": f"Conversation {conv_id}",
                        "snippet": snippet,
                        "content": content,
                        "content_type": "full"
                        if len(content) <= FEEDME_SUMMARIZE_THRESHOLD
                        else "summarized",
                        "match_pattern": pattern,
                        "score": None,
                        "metadata": {
                            "id": conv_id,
                            "last_updated": row.get("updated_at"),
                        },
                    }
                )
                if len([r for r in results if r["source"] == "feedme"]) >= feedme_limit:
                    break
        except Exception as exc:
            logger.error("DB grep FeedMe search failed: %s", exc)

    deduped = _dedupe_results(results[:max_results])
    payload = {
        "retrieval_id": retrieval_id,
        "pattern": pattern,
        "case_sensitive": case_sensitive,
        "sources_searched": sources_searched,
        "results": deduped,
        "result_count": len(deduped),
        "source_limits": {
            "kb": kb_limit if "kb" in sources else 0,
            "macros": macro_limit if "macros" in sources else 0,
            "feedme": feedme_limit if "feedme" in sources else 0,
        },
    }
    serialized = _serialize_tool_output(payload)
    _store_tool_result(cache_key, serialized)
    return payload


@tool("db_context_search", args_schema=DbContextSearchInput)
async def db_context_search_tool(
    source: str,
    doc_id: str,
) -> Dict[str, Any]:
    """Retrieve full document and surrounding context by ID.

    Use this when you found a relevant snippet and need more context,
    or when you need the complete document content.
    """
    retrieval_id = f"ctx-{uuid.uuid4().hex[:8]}"

    client = _supabase_client_cached()
    if getattr(client, "mock_mode", False):
        return {
            "retrieval_id": retrieval_id,
            "source": source,
            "doc_id": doc_id,
            "found": False,
            "content": None,
        }

    result: Dict[str, Any] = {
        "retrieval_id": retrieval_id,
        "source": source,
        "doc_id": doc_id,
        "found": False,
        "content": None,
        "snippet": None,
        "metadata": {},
    }

    try:
        if source == "kb":
            try:
                numeric_id = int(doc_id)
            except (TypeError, ValueError):
                result["error"] = f"Invalid KB doc_id format: {doc_id}"
                return result
            resp = await asyncio.to_thread(
                lambda: client.client.table("mailbird_knowledge")
                .select("*")
                .eq("id", numeric_id)
                .single()
                .execute()
            )
            if resp.data:
                result["found"] = True
                result["title"] = resp.data.get("title", "")
                content = resp.data.get("content", "")
                result["content"] = content
                result["snippet"] = _trim_content(content)
                result["metadata"] = {
                    "url": resp.data.get("url"),
                    "created_at": resp.data.get("created_at"),
                    "updated_at": resp.data.get("updated_at"),
                }

        elif source == "macro":
            try:
                zendesk_id = int(doc_id)
            except (TypeError, ValueError):
                result["error"] = f"Invalid macro doc_id format: {doc_id}"
                return result
            resp = await asyncio.to_thread(
                lambda: client.client.table("zendesk_macros")
                .select("*")
                .eq("zendesk_id", zendesk_id)
                .single()
                .execute()
            )
            if resp.data:
                result["found"] = True
                result["title"] = resp.data.get("title", "")
                content = resp.data.get("comment_value", "")
                result["content"] = content
                result["snippet"] = _trim_content(content)
                result["metadata"] = {
                    "zendesk_id": resp.data.get("zendesk_id"),
                    "description": resp.data.get("description"),
                    "usage_30d": resp.data.get("usage_30d"),
                    "active": resp.data.get("active"),
                }

        elif source == "feedme":
            try:
                conversation_id = int(doc_id)
            except (TypeError, ValueError):
                result["error"] = f"Invalid FeedMe doc_id format: {doc_id}"
                return result
            # Get all chunks for the conversation
            resp = await asyncio.to_thread(
                lambda: client.client.table("feedme_text_chunks")
                .select("content, chunk_index")
                .eq("conversation_id", conversation_id)
                .order("chunk_index")
                .execute()
            )
            if resp.data:
                # Combine all chunks
                full_content = "\n\n".join(
                    chunk.get("content", "") for chunk in resp.data
                )
                full_content = redact_pii(full_content)

                # Get conversation metadata
                conv_details = await client.get_conversations_by_ids([conversation_id])
                details = (conv_details or {}).get(conversation_id, {})

                result["found"] = True
                result["title"] = details.get("title", f"Conversation {doc_id}")
                result["content"] = full_content
                result["snippet"] = _trim_content(full_content)
                result["content_type"] = (
                    "full"
                    if len(full_content) <= FEEDME_SUMMARIZE_THRESHOLD
                    else "needs_summarization"
                )
                result["original_length"] = len(full_content)
                result["metadata"] = {
                    "conversation_id": doc_id,
                    "created_at": details.get("created_at"),
                    "folder_id": details.get("folder_id"),
                    "chunk_count": len(resp.data),
                    "updated_at": details.get("updated_at"),
                }

    except Exception as exc:
        logger.error("DB context search failed for %s/%s: %s", source, doc_id, exc)
        result["error"] = str(exc)

    return result


# --- Image Generation Tool (Gemini Nano Banana Pro) ---


class ImageGenerationInput(BaseModel):
    """Input schema for Gemini Nano Banana Pro image generation."""

    prompt: str = Field(
        ...,
        description="Detailed description of the image to generate. Include style, colors, composition.",
    )
    aspect_ratio: str = Field(
        default="16:9",
        description="Aspect ratio of the image. Options: 1:1, 2:3, 3:2, 4:3, 16:9",
    )
    resolution: str = Field(
        default="2K",
        description="Resolution of the image. Options: 1K, 2K, 4K",
    )
    model: str = Field(
        default="gemini-2.5-flash-image",
        description="Model to use. Options: gemini-2.5-flash-image (fast, GA), gemini-3-pro-image-preview (high-quality)",
    )
    input_image_base64: Optional[str] = Field(
        default=None,
        description="Optional base64-encoded input image for editing mode.",
    )


@tool("generate_image", args_schema=ImageGenerationInput)
async def generate_image_tool(
    input: Optional[ImageGenerationInput] = None,
    prompt: Optional[str] = None,
    aspect_ratio: str = "16:9",
    resolution: str = "2K",
    model: str = "gemini-2.5-flash-image",
    input_image_base64: Optional[str] = None,
    state: Annotated[Optional[GraphState], InjectedState] = None,
    runtime: Optional[ToolRuntime] = None,
) -> Dict[str, Any]:
    """Generate images using Gemini Nano Banana Pro (Gemini 3 Pro Image Preview).

    Use this tool to:
    - Generate images from text descriptions
    - Create diagrams, infographics, and illustrations
    - Generate UI mockups and screenshots
    - Edit existing images with text prompts

    Returns:
    - success: Whether generation succeeded
    - image_base64: Base64-encoded image data
    - description: Text description from the model
    - error: Error message if failed
    """
    # Normalize inputs
    if input is None:
        input = ImageGenerationInput(
            prompt=prompt or "",
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            model=model,
            input_image_base64=input_image_base64,
        )

    if runtime and getattr(runtime, "stream_writer", None):
        runtime.stream_writer.write("Generating image...")

    logger.info(
        f"generate_image_tool_invoked prompt='{input.prompt[:100]}...' "
        f"aspect_ratio={input.aspect_ratio} resolution={input.resolution}"
    )

    try:
        # Import google genai
        from google import genai
        from google.genai import types
        from app.core.settings import settings

        # Initialize client with API key from settings
        # google-genai looks for GOOGLE_API_KEY env var by default,
        # but we use GEMINI_API_KEY, so pass it explicitly
        api_key = settings.gemini_api_key
        if not api_key:
            return {
                "success": False,
                "error": "Image generation requires GEMINI_API_KEY to be set.",
            }
        client = genai.Client(api_key=api_key)

        # Build contents
        contents = [input.prompt]

        # Add input image if provided (for editing)
        if input.input_image_base64:
            import base64
            from PIL import Image
            import io

            image_data = base64.b64decode(input.input_image_base64)
            img = Image.open(io.BytesIO(image_data))
            contents.append(img)

        # Generate content with image modality
        response = client.models.generate_content(
            model=input.model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        # Extract results
        text_output = None
        image_base64 = None
        mime_type = "image/png"

        candidates = response.candidates or []
        if (
            not candidates
            or not getattr(candidates[0], "content", None)
            or not candidates[0].content.parts
        ):
            return {
                "success": False,
                "error": "No content generated by the model",
            }

        for part in candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                text_output = part.text
            elif hasattr(part, "inline_data") and part.inline_data:
                import base64 as b64

                image_base64 = b64.b64encode(part.inline_data.data).decode("utf-8")
                mime_type = part.inline_data.mime_type or "image/png"

        if not image_base64:
            return {
                "success": False,
                "error": "No image generated - model returned text only",
                "text_response": text_output,
            }

        logger.info(
            f"generate_image_tool_success prompt='{input.prompt[:50]}...' "
            f"has_image=True has_text={bool(text_output)}"
        )

        # Return image_base64 for handler to emit, but mark for eviction
        # The ToolResultEvictionMiddleware will strip this from conversation history
        # to prevent context overflow (each 2K image is ~1-3MB of base64)
        return {
            "success": True,
            "image_base64": image_base64,  # Handler reads this to emit to frontend
            "mime_type": mime_type,
            "description": text_output,
            "aspect_ratio": input.aspect_ratio,
            "resolution": input.resolution,
            # Marker for middleware/handler to know this result should be compacted
            "_large_payload": True,
        }

    except ImportError as e:
        logger.error(f"generate_image_tool_import_error: {e}")
        return {
            "success": False,
            "error": "Image generation requires google-genai>=1.0.0. Please install it.",
        }
    except Exception as e:
        logger.error(f"generate_image_tool_error: {e}")
        return {
            "success": False,
            "error": str(e),
        }


# -----------------------------------------------------------------------------
# Article Writing Tool
# -----------------------------------------------------------------------------


class ArticleInput(BaseModel):
    """Input schema for article writing tool."""

    title: str = Field(description="Title of the article")
    content: str = Field(
        description="Markdown content of the article with sections, images, etc."
    )
    images: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="Optional list of images to embed. Each dict should have 'url' and 'alt' keys.",
    )


@tool("write_article", args_schema=ArticleInput)
def write_article_tool(
    title: str,
    content: str,
    images: Optional[List[Dict[str, str]]] = None,
    runtime: Optional[Any] = None,
) -> Dict[str, Any]:
    """Write a SINGLE comprehensive article with ALL content in one document.

    IMPORTANT: Always create ONE complete article containing ALL sections requested.
    Do NOT call this tool multiple times for different sections - combine everything
    into a single, well-structured document.

    Use this tool to create professional articles, reports, or documents that the
    user can view and edit in a dedicated artifact panel.

    Content Formatting Guidelines:
    - Use # for main title (auto-added from title param)
    - Use ## for major sections
    - Use ### for subsections
    - Use **bold** for key terms and emphasis
    - Use bullet points (- or *) for lists
    - Use numbered lists (1. 2. 3.) for sequential steps
    - Use `code` for technical terms
    - Use > for blockquotes or callouts
    - Add blank lines between sections for readability

    Args:
        title: Main title of the article (displayed as header)
        content: Complete markdown content with ALL sections, headers, and formatting
        images: Optional list of images to embed. Each dict: {'url': 'image_url', 'alt': 'description'}

    Returns:
        Success status with article content (displayed in artifacts panel)
    """
    logger.info(
        f"write_article_tool_invoked title='{title}' content_length={len(content)}"
    )

    if runtime and getattr(runtime, "stream_writer", None):
        runtime.stream_writer.write(f"Creating article: {title}...")

    try:
        # Return the content - the handler will emit the artifact
        # This is consistent with how generate_image_tool works
        logger.info(f"write_article_tool_success title='{title}'")
        return {
            "success": True,
            "title": title,
            "content": content,
            "images": images,
            "message": f"Article '{title}' created successfully. It is now visible in the artifacts panel.",
        }

    except Exception as e:
        logger.error(f"write_article_tool_error: {e}")
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# SKILL TOOLS (Progressive Disclosure)
# =============================================================================


class ReadSkillInput(BaseModel):
    """Input schema for read_skill tool."""

    skill_name: str = Field(
        description="Name of the skill to load (e.g., 'research', 'writing', 'pdf')"
    )

    model_config = ConfigDict(extra="forbid")


@tool("read_skill", args_schema=ReadSkillInput)
def read_skill_tool(
    skill_name: str,
) -> Dict[str, Any]:
    """
    Read the full instructions for a specific skill.

    Use this tool when you need detailed guidance for a complex task.
    The system prompt shows available skills - call this to get full instructions.

    Progressive disclosure pattern:
    1. System prompt contains skill index (names + brief descriptions)
    2. Call read_skill when you need detailed instructions for a task
    3. Returns full SKILL.md content with step-by-step guidance

    Args:
        skill_name: Name of the skill (e.g., 'research', 'writing', 'pdf', 'canvas-design')

    Returns:
        Dict with skill content and metadata, or error if skill not found.
    """
    try:
        from app.agents.skills import get_skills_registry

        registry = get_skills_registry()
        skill = registry.load_skill(skill_name)

        if not skill:
            # List available skills for user guidance
            available = registry.discover_skills()
            available_names = [s.name for s in available]
            return {
                "success": False,
                "error": f"Skill '{skill_name}' not found",
                "available_skills": available_names,
                "hint": f"Try one of: {', '.join(available_names[:5])}...",
            }

        return {
            "success": True,
            "skill_name": skill.metadata.name,
            "description": skill.metadata.description,
            "content": skill.content,
            "has_references": len(skill.references) > 0,
            "reference_names": list(skill.references.keys())
            if skill.references
            else [],
        }

    except Exception as e:
        logger.error(f"read_skill_tool_error: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def get_db_retrieval_tools() -> List[BaseTool]:
    """Return tools for the database retrieval subagent in priority order."""
    return [
        db_unified_search_tool,  # semantic/hybrid first
        db_context_search_tool,  # full doc/context retrieval
        db_grep_search_tool,  # exact/pattern match
    ]
