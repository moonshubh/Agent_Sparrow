"""
User-specific research tools using per-user API keys.
Tavily-only integration (search + extract) with quota and caching.
"""

import os
import json
import redis
import logging
import asyncio
import hashlib
import functools
from typing import Optional, Dict, Any, List

from app.core.settings import settings
from app.core.user_context import get_current_user_context
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# Optional third-party SDKs
try:
    # New SDK name
    from tavily import TavilyClient  # type: ignore
except ImportError:  # Backward compatibility with older tavily-python
    TavilyClient = None  # type: ignore
try:
    # Older SDK exported Tavily client class
    from tavily import Tavily  # type: ignore
except ImportError:
    Tavily = None  # type: ignore

logger = logging.getLogger(__name__)

# Redis URL
REDIS_URL = settings.redis_url
SCRAPE_CACHE_TTL_SEC = int(os.getenv("SCRAPE_CACHE_TTL_SEC", "86400"))

# Helper to get a singleton Redis client
_redis_client: Optional[redis.Redis] = None

# Quota config: 1000 API calls per user per month
TAVILY_MONTHLY_LIMIT = int(os.getenv("TAVILY_MONTHLY_LIMIT", "1000"))
SEARCH_CACHE_TTL_SEC = int(os.getenv("TAVILY_SEARCH_TTL_SEC", "604800"))  # 7 days
EXTRACT_CACHE_TTL_SEC = int(os.getenv("TAVILY_EXTRACT_TTL_SEC", "604800"))
REDIS_TIMEOUT_SEC = float(os.getenv("REDIS_OP_TIMEOUT_SEC", "5"))
TAVILY_TIMEOUT_SEC = float(os.getenv("TAVILY_OP_TIMEOUT_SEC", "20"))

def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


class UserTavilySearchTool:
    """
    User-specific Tavily search tool that uses API keys from user context.
    """
    
    def __init__(self):
        self.name = "tavily_web_search"
        self.description = "Search the web using Tavily API with user-specific API key"
        self.search_depth = "advanced"
    
    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def search(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Search the web with user's Tavily API key.

        Returns a dict containing both a structured "results" list and a legacy
        "urls" list for backward compatibility. Attempts light extraction for
        the top 2 results to provide LLM-ready content while respecting quota.
        """

        # Get user context
        user_context = get_current_user_context()
        if not user_context:
            logger.warning("No user context available for Tavily search")
            return {"results": [], "urls": []}

        # Get user's Tavily API key
        api_key = await user_context.get_tavily_api_key()
        if not api_key:
            logger.info("No Tavily API key configured for user")
            return {"results": [], "urls": []}

        # Quota and caching keys
        user_id = user_context.user_id or "anon"
        qhash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
        search_cache_key = f"tavily:search:{user_id}:{qhash}:{max_results}"

        # Try cache first
        try:
            rc = _get_redis()
            cached = await asyncio.wait_for(asyncio.to_thread(rc.get, search_cache_key), timeout=REDIS_TIMEOUT_SEC)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.debug(f"Tavily cache miss/error: {e}")

        # Quota check: 1 call for search + up to 2 extract calls later
        calls_needed = 1
        if not await asyncio.wait_for(asyncio.to_thread(_check_and_reserve_quota, user_id, calls_needed), timeout=REDIS_TIMEOUT_SEC):
            logger.warning("Tavily monthly quota exceeded; returning empty results or stale cache")
            return {"results": [], "urls": []}

        client = _make_tavily_client(api_key)
        if client is None:
            logger.warning("Tavily SDK not available")
            return {"results": [], "urls": []}

        try:
            res = await asyncio.wait_for(asyncio.to_thread(
                client.search,
                query,
                search_depth=self.search_depth,
                max_results=max_results,
            ), timeout=TAVILY_TIMEOUT_SEC)
            items = res.get("results", []) if isinstance(res, dict) else []
            results: List[Dict[str, Any]] = []
            urls: List[str] = []
            for it in items:
                url = it.get("url")
                title = it.get("title")
                snippet = it.get("snippet") or it.get("content")
                score = it.get("score") or it.get("relevance")
                results.append({
                    "url": url,
                    "title": title,
                    "snippet": snippet,
                    "score": score,
                    "published_date": it.get("published_date")
                })
                if isinstance(url, str):
                    urls.append(url)

            # Light extraction for top 2 items, with caching + quota
            extracted: List[Dict[str, Any]] = []
            for url in urls[:2]:
                content = await _extract_with_cache_and_quota(client, user_id, url)
                if content:
                    # include title if available
                    title = next((r.get("title") for r in results if r.get("url") == url), None)
                    extracted.append({"url": url, "title": title, "content": content})

            payload = {"results": results, "urls": urls, "extracted": extracted}

            # Store cache
            try:
                rc = _get_redis()
                await asyncio.wait_for(asyncio.to_thread(rc.setex, search_cache_key, SEARCH_CACHE_TTL_SEC, json.dumps(payload)), timeout=REDIS_TIMEOUT_SEC)
            except Exception:
                pass

            return payload

        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return {"results": [], "urls": []}


async def _extract_with_cache_and_quota(client: Any, user_id: str, url: str) -> Optional[str]:
    """Extract content for URL using Tavily, with cache and quota enforcement."""
    uhash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    cache_key = f"tavily:extract:{uhash}"
    try:
        rc = _get_redis()
        cached = await asyncio.wait_for(asyncio.to_thread(rc.get, cache_key), timeout=REDIS_TIMEOUT_SEC)
        if cached:
            data = json.loads(cached)
            return data.get("content")
    except Exception:
        pass

    # Reserve 1 API call for extract
    if not await asyncio.wait_for(asyncio.to_thread(_check_and_reserve_quota, user_id, 1), timeout=REDIS_TIMEOUT_SEC):
        return None

    try:
        if hasattr(client, "extract"):
            res = await asyncio.wait_for(asyncio.to_thread(client.extract, url), timeout=TAVILY_TIMEOUT_SEC)
            content = None
            if isinstance(res, dict):
                # Some SDKs return {"content": "..."} or {"results": [...]}
                content = res.get("content") or res.get("text") or res.get("data")
                if isinstance(content, dict):
                    # Fallback for nested payloads
                    content = content.get("content") or content.get("text")
            if isinstance(res, str):
                content = res
            if content:
                try:
                    rc = _get_redis()
                    await asyncio.wait_for(asyncio.to_thread(rc.setex, cache_key, EXTRACT_CACHE_TTL_SEC, json.dumps({"content": content})), timeout=REDIS_TIMEOUT_SEC)
                except Exception:
                    pass
                return content
    except Exception as e:
        logger.debug(f"Tavily extract failed for {url}: {e}")
    return None

def _make_tavily_client(api_key: str) -> Optional[Any]:
    """Instantiate a Tavily client compatible with installed SDK version."""
    try:
        if TavilyClient is not None:
            return TavilyClient(api_key=api_key)
        if Tavily is not None:
            return Tavily(api_key=api_key)
    except Exception as e:
        logger.warning(f"Failed to create Tavily client: {e}")
    return None

def _check_and_reserve_quota(user_id: str, calls: int) -> bool:
    """Check remaining monthly quota and reserve the requested number of calls."""
    try:
        rc = _get_redis()
        ym = _current_ym()
        key = f"tavily:usage:{ym}:{user_id}"
        current = rc.incrby(key, calls)
        if current == calls:
            # first set expiry to end of month (~32 days safe upper bound)
            rc.expire(key, 32 * 24 * 3600)
        if current > TAVILY_MONTHLY_LIMIT:
            # Rollback reservation to avoid drift
            rc.decrby(key, calls)
            return False
        return True
    except Exception as e:
        logger.debug(f"Quota check failed, allowing call: {e}")
        return True

def _current_ym() -> str:
    import datetime as _dt
    now = _dt.datetime.utcnow()
    return now.strftime("%Y%m")


# Global tool instances
_tavily_tool: Optional[UserTavilySearchTool] = None


def get_user_tavily_tool() -> UserTavilySearchTool:
    """Get singleton user-specific Tavily search tool."""
    global _tavily_tool
    if _tavily_tool is None:
        _tavily_tool = UserTavilySearchTool()
    return _tavily_tool


# LangChain-compatible tool functions
async def tavily_web_search(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    LangChain tool function for Tavily web search using user API key.
    """
    tool = get_user_tavily_tool()
    return await tool.search(query, max_results)


def get_user_research_tools():
    """
    Get list of research tools that use user-specific API keys (Tavily only).
    """
    return [
        tavily_web_search,
    ]