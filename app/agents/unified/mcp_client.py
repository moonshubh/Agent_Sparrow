"""MCP Client for Firecrawl integration.

This module provides MCP (Model Context Protocol) integration for Firecrawl,
enabling full access to all Firecrawl features including:
- scrape: Single-page scraping with screenshots, actions, mobile, PDF parsing
- map: URL discovery for site structure
- search: Multi-source search (web, images, news)
- crawl: Multi-page extraction with async support
- extract: AI-powered structured data extraction
- agent: Autonomous data gathering (new!)

Uses HTTP transport against the Firecrawl MCP endpoint for hosted execution.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, cast

from langchain_core.tools import BaseTool

from app.core.logging_config import get_logger
from app.core.settings import settings

logger = get_logger("mcp_client")

AUTH_HEADER_NAME = "Authorization"
AUTH_HEADER_SCHEME = "Bearer"

# Try to import MCP adapters - gracefully degrade if not available
try:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    MultiServerMCPClient = None  # type: ignore[misc, assignment]
    logger.warning("langchain-mcp-adapters not installed, MCP tools disabled")


def _build_firecrawl_mcp_config(api_key: str) -> Dict[str, Any]:
    endpoint = settings.firecrawl_mcp_endpoint
    headers: Dict[str, str] = {}
    if "{FIRECRAWL_API_KEY}" in endpoint:
        endpoint = endpoint.replace("{FIRECRAWL_API_KEY}", api_key)
    else:
        headers = {AUTH_HEADER_NAME: f"{AUTH_HEADER_SCHEME} {api_key}"}

    config: Dict[str, Any] = {
        "transport": "http",
        "url": endpoint,
    }
    if headers:
        config["headers"] = headers
    return config


MCP_TOOL_CACHE_MAX = 128
MCP_TOOL_CACHE_TTL_CAP_SEC = 3600
MCP_CLIENT_POOL_MAX = 16
_MCP_TOOL_CACHE: Dict[str, tuple[float, Any]] = {}
_MCP_TOOL_CACHE_LOCK = threading.Lock()


def _cache_key(namespace: str, tool_name: str, args: Dict[str, Any]) -> str:
    serialized = json.dumps(args, sort_keys=True, default=str)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{namespace}:{tool_name}:{digest}"


def _cache_get(cache_key: str) -> Optional[Any]:
    now = time.monotonic()
    with _MCP_TOOL_CACHE_LOCK:
        entry = _MCP_TOOL_CACHE.get(cache_key)
        if not entry:
            return None
        expires_at, payload = entry
        if expires_at <= now:
            _MCP_TOOL_CACHE.pop(cache_key, None)
            return None
        return payload


def _cache_set(cache_key: str, ttl_sec: float, payload: Any) -> None:
    if ttl_sec <= 0:
        return
    expires_at = time.monotonic() + ttl_sec
    with _MCP_TOOL_CACHE_LOCK:
        if len(_MCP_TOOL_CACHE) >= MCP_TOOL_CACHE_MAX:
            oldest_key = None
            oldest_expiry = None
            for key, (expiry, _) in _MCP_TOOL_CACHE.items():
                if oldest_expiry is None or expiry < oldest_expiry:
                    oldest_key = key
                    oldest_expiry = expiry
            if oldest_key:
                _MCP_TOOL_CACHE.pop(oldest_key, None)
        _MCP_TOOL_CACHE[cache_key] = (expires_at, payload)


@dataclass
class MCPToolConfig:
    """Configuration for an MCP tool with caching and rate limiting."""

    name: str
    max_age_ms: int = 172800000  # 48 hours default
    rate_limit_rpm: int = 60
    timeout_sec: float = 90.0
    retry_count: int = 3


@dataclass
class MCPToolRequest:
    name: str
    args: Dict[str, Any]


# Tool-specific configurations
FIRECRAWL_TOOL_CONFIGS: Dict[str, MCPToolConfig] = {
    "firecrawl_scrape": MCPToolConfig(
        name="firecrawl_scrape",
        max_age_ms=172800000,  # 48 hours - pages don't change often
        rate_limit_rpm=60,
        timeout_sec=60.0,
    ),
    "firecrawl_map": MCPToolConfig(
        name="firecrawl_map",
        max_age_ms=3600000,  # 1 hour - site structure changes
        rate_limit_rpm=30,
        timeout_sec=30.0,
    ),
    "firecrawl_search": MCPToolConfig(
        name="firecrawl_search",
        max_age_ms=3600000,  # 1 hour - search results change
        rate_limit_rpm=60,
        timeout_sec=45.0,
    ),
    "firecrawl_crawl": MCPToolConfig(
        name="firecrawl_crawl",
        max_age_ms=86400000,  # 24 hours
        rate_limit_rpm=10,  # Crawls are expensive
        timeout_sec=120.0,
    ),
    "firecrawl_extract": MCPToolConfig(
        name="firecrawl_extract",
        max_age_ms=86400000,  # 24 hours - extracted data is stable
        rate_limit_rpm=30,
        timeout_sec=90.0,
    ),
    "firecrawl_agent": MCPToolConfig(
        name="firecrawl_agent",
        max_age_ms=0,  # Disable local caching for agent jobs
        rate_limit_rpm=10,  # Agent is expensive
        # The MCP agent endpoint can be slower/unreliable; keep the timeout low so we
        # can quickly fall back to the Firecrawl SDK path in `tools.py`.
        timeout_sec=60.0,
        retry_count=1,
    ),
    "firecrawl_check_crawl_status": MCPToolConfig(
        name="firecrawl_check_crawl_status",
        max_age_ms=0,
        rate_limit_rpm=60,
        timeout_sec=30.0,
        retry_count=2,
    ),
    "firecrawl_agent_status": MCPToolConfig(
        name="firecrawl_agent_status",
        max_age_ms=0,
        rate_limit_rpm=60,
        timeout_sec=30.0,
        retry_count=2,
    ),
}


class FirecrawlMCPClient:
    """Async-safe Firecrawl MCP client with connection pooling.

    This client manages the MCP connection to the Firecrawl server,
    providing tool access with proper error handling and observability.
    """

    _instances: Dict[str, "FirecrawlMCPClient"] = {}
    _pool_lock = threading.Lock()

    def __init__(self, api_key: str) -> None:
        """Initialize the MCP client."""
        self._client: Optional[MultiServerMCPClient] = None
        self._tools: List[BaseTool] = []
        self._initialized = False
        self._api_key: str = api_key
        self._key_id = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        self._cache_namespace = f"firecrawl:{self._key_id}"
        self._init_lock: Optional[asyncio.Lock] = None
        self._last_used = time.monotonic()
        self._rate_limiters: Dict[str, Callable] = {}
        self._rate_limit_settings: Dict[str, int] = {}
        self._logging_interceptor: Optional[Callable] = None

    @classmethod
    async def get_instance(
        cls, api_key: Optional[str] = None
    ) -> Optional["FirecrawlMCPClient"]:
        """Get or create an MCP client instance scoped to an API key."""
        if not MCP_AVAILABLE or not settings.firecrawl_mcp_enabled:
            return None

        resolved_key = api_key or settings.firecrawl_api_key
        if not resolved_key:
            return None

        key_id = hashlib.sha256(resolved_key.encode("utf-8")).hexdigest()
        victim: Optional["FirecrawlMCPClient"] = None

        with cls._pool_lock:
            client = cls._instances.get(key_id)
            if client is None:
                client = cls(resolved_key)
                cls._instances[key_id] = client

                if len(cls._instances) > MCP_CLIENT_POOL_MAX:
                    oldest_key = None
                    oldest_time = None
                    for cache_key, instance in cls._instances.items():
                        if oldest_time is None or instance._last_used < oldest_time:
                            oldest_key = cache_key
                            oldest_time = instance._last_used
                    if oldest_key and oldest_key != key_id:
                        victim = cls._instances.pop(oldest_key, None)
            client._last_used = time.monotonic()

        if victim is not None:
            await victim.close()

        if client and not client._initialized:
            await client.initialize(resolved_key)

        return client

    @property
    def is_available(self) -> bool:
        """Check if MCP is available and configured."""
        if not MCP_AVAILABLE or not settings.firecrawl_mcp_enabled:
            return False
        return bool(settings.firecrawl_api_key)

    async def initialize(self, api_key: Optional[str] = None) -> bool:
        """Initialize the MCP client with the Firecrawl server.

        Args:
            api_key: Optional API key override.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        if not MCP_AVAILABLE:
            logger.warning("mcp_client_init_skipped", reason="mcp_not_available")
            return False
        if not settings.firecrawl_mcp_enabled:
            logger.info("mcp_client_init_skipped", reason="mcp_disabled")
            return False

        resolved_key = api_key or self._api_key
        if not resolved_key:
            logger.warning("mcp_client_init_skipped", reason="no_api_key")
            return False
        if resolved_key != self._api_key:
            logger.warning("mcp_client_init_key_mismatch")
            return False

        try:
            if self._init_lock is None:
                self._init_lock = asyncio.Lock()
            async with self._init_lock:
                if self._initialized and self._client:
                    return True

                config: Dict[str, Any] = {
                    "firecrawl": _build_firecrawl_mcp_config(resolved_key)
                }
                self._client = MultiServerMCPClient(cast(Any, config))
                self._initialized = True
                self._tools = []
                logger.info("mcp_client_initialized", server="firecrawl")
                return True

        except Exception as e:
            logger.error("mcp_client_init_failed", error=str(e))
            self._initialized = False
            return False

    async def get_tools(self) -> List[BaseTool]:
        """Get all Firecrawl MCP tools.

        Returns:
            List of LangChain tools from the Firecrawl MCP server.
        """
        if not self._initialized:
            if not await self.initialize():
                return []

        if not self._client:
            return []

        try:
            if self._tools:
                return self._tools
            # Get tools from MCP client
            tools = await self._client.get_tools()
            self._tools = tools
            logger.info(
                "mcp_tools_loaded",
                tool_count=len(tools),
                tool_names=[t.name for t in tools],
            )
            return tools

        except Exception as e:
            logger.error("mcp_tools_load_failed", error=str(e))
            return []

    async def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        tools = await self.get_tools()
        for tool in tools:
            if tool.name == tool_name:
                return tool
        return None

    async def _get_rate_limit_interceptor(
        self, tool_name: str, rate_limit_rpm: int
    ) -> Optional[Callable]:
        if rate_limit_rpm <= 0:
            return None
        cached = self._rate_limiters.get(tool_name)
        if cached and self._rate_limit_settings.get(tool_name) == rate_limit_rpm:
            return cached
        interceptor = await create_rate_limiting_interceptor(rate_limit_rpm)
        self._rate_limiters[tool_name] = interceptor
        self._rate_limit_settings[tool_name] = rate_limit_rpm
        return interceptor

    async def _get_logging_interceptor(self) -> Callable:
        if self._logging_interceptor is None:
            self._logging_interceptor = await create_logging_interceptor()
        return self._logging_interceptor

    async def invoke_tool(
        self, tool_name: str, args: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        if not self._initialized:
            if not await self.initialize():
                return None

        tool = await self.get_tool(tool_name)
        if not tool:
            logger.warning("mcp_tool_not_found", tool_name=tool_name)
            return None

        config = get_tool_config(tool_name)
        self._last_used = time.monotonic()

        async def handler(request: MCPToolRequest):
            return await asyncio.wait_for(
                tool.ainvoke(request.args), timeout=config.timeout_sec
            )

        rate_interceptor = await self._get_rate_limit_interceptor(
            tool_name, config.rate_limit_rpm
        )
        logging_interceptor = await self._get_logging_interceptor()
        retry_interceptor = await create_retry_interceptor(max(1, config.retry_count))
        cache_ttl = _resolve_cache_ttl(tool_name, config)
        cache_interceptor = await create_cache_interceptor(
            self._cache_namespace, tool_name, cache_ttl
        )

        raw_interceptors = [
            cache_interceptor,
            rate_interceptor,
            retry_interceptor,
            logging_interceptor,
        ]
        interceptors = cast(
            List[Callable[..., Any]],
            [i for i in raw_interceptors if i is not None],
        )

        request = MCPToolRequest(name=tool_name, args=args)
        result = await _apply_interceptors(request, handler, interceptors)
        normalized = _normalize_result(result)
        if isinstance(normalized, dict):
            return normalized
        return {"data": normalized}

    @asynccontextmanager
    async def session(self):
        """Create a stateful session for multi-step tool operations.

        Use this when you need to maintain state across multiple tool calls,
        such as when crawling pages that share session context.

        Usage:
            async with client.session() as session:
                # Use MCP session-scoped operations as needed
        """
        if not self._client:
            raise RuntimeError("MCP client not initialized")

        async with self._client.session("firecrawl") as session:
            yield session

    async def close(self) -> None:
        """Close the MCP client and cleanup resources."""
        if self._client:
            # MultiServerMCPClient handles cleanup internally
            self._client = None
            self._initialized = False
            self._tools = []
            logger.info("mcp_client_closed")


# Convenience functions for tool access


async def get_firecrawl_mcp_tools(api_key: Optional[str] = None) -> List[BaseTool]:
    """Get Firecrawl tools via MCP protocol.

    This is the primary entry point for getting Firecrawl tools.
    Falls back to empty list if MCP is not available.

    Args:
        api_key: Optional API key override.

    Returns:
        List of Firecrawl MCP tools, or empty list if unavailable.
    """
    client = await FirecrawlMCPClient.get_instance(api_key)
    if not client:
        return []
    return await client.get_tools()


async def invoke_firecrawl_mcp_tool(
    tool_name: str, args: Dict[str, Any], api_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    client = await FirecrawlMCPClient.get_instance(api_key)
    if not client:
        return None
    return await client.invoke_tool(tool_name, args)


def is_mcp_available() -> bool:
    """Check if MCP integration is available.

    Returns:
        True if langchain-mcp-adapters is installed and API key is configured.
    """
    if not MCP_AVAILABLE or not settings.firecrawl_mcp_enabled:
        return False
    return bool(settings.firecrawl_api_key)


def get_tool_config(tool_name: str) -> MCPToolConfig:
    """Get configuration for a specific MCP tool.

    Args:
        tool_name: Name of the Firecrawl tool.

    Returns:
        MCPToolConfig with tool-specific settings.
    """
    return FIRECRAWL_TOOL_CONFIGS.get(
        tool_name,
        MCPToolConfig(name=tool_name),  # Default config
    )


def _normalize_result(payload: Any) -> Any:
    if isinstance(payload, (dict, list)):
        return payload
    if hasattr(payload, "model_dump"):
        return payload.model_dump()  # type: ignore[call-arg]
    if hasattr(payload, "dict"):
        return payload.dict()  # type: ignore[call-arg]
    return payload


def _resolve_cache_ttl(tool_name: str, config: MCPToolConfig) -> float:
    if config.max_age_ms <= 0:
        return 0.0
    if tool_name in {
        "firecrawl_agent",
        "firecrawl_agent_status",
        "firecrawl_check_crawl_status",
    }:
        return 0.0
    ttl_sec = config.max_age_ms / 1000.0
    return min(ttl_sec, MCP_TOOL_CACHE_TTL_CAP_SEC)


async def _apply_interceptors(
    request: MCPToolRequest,
    handler: Callable[[MCPToolRequest], Any],
    interceptors: List[Callable],
) -> Any:
    if not interceptors:
        return await handler(request)

    async def _call(req: MCPToolRequest) -> Any:
        return await handler(req)

    def _wrap_interceptor(
        interceptor: Callable[[MCPToolRequest, Callable[[MCPToolRequest], Any]], Any],
        next_handler: Callable[[MCPToolRequest], Any],
    ) -> Callable[[MCPToolRequest], Any]:
        async def _wrapped(req: MCPToolRequest) -> Any:
            return await interceptor(req, next_handler)

        return _wrapped

    call: Callable[[MCPToolRequest], Any] = _call
    for interceptor in reversed(interceptors):
        call = _wrap_interceptor(interceptor, call)

    return await call(request)


# MCP Tool Interceptors for enhanced functionality


async def create_rate_limiting_interceptor(
    rate_limit_rpm: int = 60,
) -> Callable:
    """Create a rate limiting interceptor for MCP tools.

    Args:
        rate_limit_rpm: Maximum requests per minute.

    Returns:
        Interceptor function for rate limiting.
    """
    if rate_limit_rpm <= 0:

        async def noop_interceptor(request, handler):
            return await handler(request)

        return noop_interceptor

    # Simple token bucket implementation
    tokens = float(rate_limit_rpm)
    last_refill = time.monotonic()
    lock = asyncio.Lock()

    async def interceptor(request, handler):
        nonlocal tokens, last_refill

        sleep_time = 0.0
        async with lock:
            now = time.monotonic()
            # Refill tokens based on time elapsed
            elapsed = now - last_refill
            tokens = min(rate_limit_rpm, tokens + (elapsed * rate_limit_rpm / 60))
            last_refill = now

            # Reserve a token now; if unavailable, we'll sleep outside the lock
            tokens -= 1.0
            if tokens < 0:
                sleep_time = (-tokens) * 60 / rate_limit_rpm

        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

        return await handler(request)

    return interceptor


async def create_logging_interceptor() -> Callable:
    """Create a logging interceptor for MCP tool calls.

    Returns:
        Interceptor function that logs tool calls.
    """

    async def interceptor(request, handler):
        logger.info(
            "mcp_tool_call_start",
            tool_name=request.name,
            args=request.args,
        )
        try:
            result = await handler(request)
            logger.info(
                "mcp_tool_call_success",
                tool_name=request.name,
            )
            return result
        except Exception as e:
            logger.error(
                "mcp_tool_call_error",
                tool_name=request.name,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    return interceptor


async def create_retry_interceptor(
    max_retries: int = 3, base_delay: float = 1.0
) -> Callable:
    """Create a retry interceptor with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds for exponential backoff.

    Returns:
        Interceptor function that retries failed calls.
    """
    effective_retries = max(1, int(max_retries))

    async def interceptor(request, handler):
        last_error: Exception | None = None
        for attempt in range(effective_retries):
            try:
                return await handler(request)
            except Exception as e:
                # Firecrawl frequently returns non-recoverable billing/limit errors.
                # Retrying just burns time and delays fallbacks (e.g., Tavily).
                lower = str(e).lower()
                if any(
                    phrase in lower
                    for phrase in (
                        "insufficient credits",
                        "rate limit exceeded",
                        "upgrade your plan",
                        "payment required",
                        "quota exceeded",
                    )
                ):
                    logger.warning(
                        "mcp_tool_no_retry",
                        tool_name=request.name,
                        attempt=attempt + 1,
                        max_retries=effective_retries,
                        error=str(e),
                    )
                    raise
                last_error = e
                if attempt < effective_retries - 1:
                    wait_time = max(0.0, base_delay) * (2**attempt)
                    logger.warning(
                        "mcp_tool_retry",
                        tool_name=request.name,
                        attempt=attempt + 1,
                        max_retries=effective_retries,
                        wait_time=wait_time,
                        error=str(e),
                    )
                    await asyncio.sleep(wait_time)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Retry interceptor exhausted without capturing error")

    return interceptor


async def create_cache_interceptor(
    namespace: str,
    tool_name: str,
    ttl_sec: float,
) -> Callable:
    """Create a cache interceptor for MCP tool calls."""

    async def interceptor(request, handler):
        if ttl_sec <= 0:
            return await handler(request)

        cache_key = _cache_key(namespace, request.name, request.args)
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.info("mcp_tool_cache_hit", tool_name=request.name)
            return cached

        result = await handler(request)
        if isinstance(result, dict) and (
            result.get("error") or result.get("success") is False
        ):
            return result
        _cache_set(cache_key, ttl_sec, result)
        logger.info("mcp_tool_cache_store", tool_name=request.name)
        return result

    return interceptor
