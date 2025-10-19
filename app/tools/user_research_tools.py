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
from typing import Optional, Dict, Any, List, Tuple

from app.core.settings import settings
from app.core.user_context import get_current_user_context
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
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
def _redis_timeout_sec() -> float:
    """Fetch Redis operation timeout from env at call-time.

    Keeping this dynamic ensures tests that set env vars during runtime take effect
    even if this module was imported earlier by another path.
    """
    try:
        return float(os.getenv("REDIS_OP_TIMEOUT_SEC", "5"))
    except Exception:
        return 5.0


def _tavily_timeout_sec() -> float:
    """Fetch Tavily client operation timeout from env at call-time.

    Tests toggle TAVILY_OP_TIMEOUT_SEC to validate timeout behavior; reading it
    lazily avoids stale values cached at import-time.
    """
    try:
        return float(os.getenv("TAVILY_OP_TIMEOUT_SEC", "20"))
    except Exception:
        return 20.0

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

    # ---- profile + capability config ----
    @staticmethod
    def _profile_defaults() -> Dict[str, Dict[str, Any]]:
        def _b(name: str, default: str) -> str:
            return os.getenv(name, default)
        def _i(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, str(default)))
            except Exception:
                return default
        def _bool(name: str, default: bool) -> bool:
            return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}

        return {
            # medium means advanced depth with conservative limits
            "medium": {
                "search_depth": "advanced",
                "max_results": _i("TAVILY_MAX_RESULTS", 6),
                "extract_top_n": _i("TAVILY_EXTRACT_TOP_N", 2),
                "include_answer": _bool("TAVILY_INCLUDE_ANSWER", False),
            },
            # advanced pushes limits higher (still advanced depth)
            "advanced": {
                "search_depth": "advanced",
                "max_results": _i("TAVILY_ADV_MAX_RESULTS", 10),
                "extract_top_n": _i("TAVILY_ADV_EXTRACT_TOP_N", 2),
                "include_answer": _bool("TAVILY_INCLUDE_ANSWER", False),
            },
        }

    @staticmethod
    def _sanitize_query(q: str) -> str:
        q = (q or "").strip()
        # trim to safe length to avoid server 400s on overly long prompts
        max_len = int(os.getenv("TAVILY_QUERY_MAX_CHARS", "1000"))
        return q if len(q) <= max_len else q[: max_len - 1].rstrip()

    @staticmethod
    def _has_advanced_signals(q: str) -> bool:
        ql = (q or "").lower()
        signals = ["site:", "after:", "before:", "news", "latest", "today", "yesterday"]
        return any(s in ql for s in signals)

    @staticmethod
    def _select_profile(query: str) -> str:
        # default medium; escalate to advanced for certain signals
        return "advanced" if UserTavilySearchTool._has_advanced_signals(query) else "medium"
    
    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def search(self, query: str, max_results: int = 10, profile: Optional[str] = None) -> Dict[str, Any]:
        """Search the web with user's Tavily API key.

        Returns a dict containing both a structured "results" list and a legacy
        "urls" list for backward compatibility. Attempts light extraction for
        the top N results to provide LLM-ready content while respecting quota.
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

        # Determine profile and config
        user_id = user_context.user_id or "anon"
        prof = (profile or os.getenv("TAVILY_DEFAULT_PROFILE", "medium")).lower()
        if prof not in ("medium", "advanced"):
            prof = "medium"
        profiles = self._profile_defaults()
        cfg = profiles.get(prof, profiles["medium"]).copy()
        # Allow explicit max_results override (clamped 1..10)
        try:
            if max_results is not None:
                cfg["max_results"] = max(1, min(int(max_results), 10))
        except Exception:
            pass
        depth = cfg["search_depth"]  # always "advanced"
        extract_top_n = max(0, int(cfg.get("extract_top_n", 1)))
        include_answer = bool(cfg.get("include_answer", False))

        # Quota and caching keys
        qsafe = self._sanitize_query(query)
        qhash = hashlib.sha256(qsafe.encode("utf-8")).hexdigest()[:16]
        flags = f"ia{1 if include_answer else 0}"
        search_cache_key = f"tavily:search:{user_id}:{qhash}:{prof}:{cfg['max_results']}:{extract_top_n}:{flags}"

        # Try cache first
        try:
            rc = _get_redis()
            cached = await asyncio.wait_for(
                asyncio.to_thread(rc.get, search_cache_key),
                timeout=_redis_timeout_sec(),
            )
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.debug(f"Tavily cache miss/error: {e}")

        # Quota check: count search only; extracts reserve individually to align with tests
        calls_needed = 1
        if not await asyncio.wait_for(
            asyncio.to_thread(_check_and_reserve_quota, user_id, calls_needed),
            timeout=_redis_timeout_sec(),
        ):
            logger.warning("Tavily monthly quota exceeded; returning empty results or stale cache")
            return {"results": [], "urls": []}

        client = _make_tavily_client(api_key)
        if client is None:
            logger.warning("Tavily SDK not available")
            return {"results": [], "urls": []}

        async def _call_search(send_extras: bool) -> Tuple[Dict[str, Any], Dict[str, Any]]:
            # returns (response_dict, meta)
            extra_kwargs: Dict[str, Any] = {}
            if send_extras and include_answer:
                extra_kwargs["include_answer"] = True
            meta = {"profile_used": prof, "depth_used": depth, "extras_sent": bool(extra_kwargs)}
            res = await asyncio.wait_for(
                asyncio.to_thread(
                    client.search,
                    qsafe,
                    search_depth=depth,
                    max_results=cfg["max_results"],
                    **extra_kwargs,
                ),
                timeout=_tavily_timeout_sec(),
            )
            if not isinstance(res, dict):
                return ({"results": []}, meta)
            return (res, meta)

        try:
            # First attempt: advanced depth; send extras if enabled
            try:
                res, meta = await _call_search(send_extras=True)
            except TypeError:
                # SDK doesn't accept extras kwarg(s); retry without extras
                res, meta = await _call_search(send_extras=False)
                meta["extras_stripped"] = True
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

            # Light extraction per profile, with caching + quota
            extracted: List[Dict[str, Any]] = []
            for url in urls[:extract_top_n]:
                content = await _extract_with_cache_and_quota(client, user_id, url)
                if content:
                    # include title if available
                    title = next((r.get("title") for r in results if r.get("url") == url), None)
                    extracted.append({"url": url, "title": title, "content": content})

            payload = {"results": results, "urls": urls, "extracted": extracted, "meta": meta}

            # Store cache
            try:
                rc = _get_redis()
                await asyncio.wait_for(
                    asyncio.to_thread(
                        rc.setex, search_cache_key, SEARCH_CACHE_TTL_SEC, json.dumps(payload)
                    ),
                    timeout=_redis_timeout_sec(),
                )
            except Exception:
                pass

            return payload

        except Exception as e:
            # Hardened diagnostics: capture HTTP status/body if available (no PII)
            status_code: Optional[int] = None
            body_preview: Optional[str] = None
            try:
                resp = getattr(e, "response", None)
                if resp is not None:
                    status_code = getattr(resp, "status_code", None) or getattr(resp, "status", None)
                    text = getattr(resp, "text", None)
                    if callable(text):
                        try:
                            text = text()
                        except Exception:
                            text = None
                    if isinstance(text, str) and text:
                        body_preview = text[:500]
            except Exception:
                pass

            error_type = "tavily_error"
            if status_code == 400:
                # Retry once stripping extras (still advanced depth)
                try:
                    res = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.search,
                            qsafe,
                            search_depth=depth,
                            max_results=cfg["max_results"],
                        ),
                        timeout=_tavily_timeout_sec(),
                    )
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

                    extracted: List[Dict[str, Any]] = []
                    for url in urls[:extract_top_n]:
                        content = await _extract_with_cache_and_quota(client, user_id, url)
                        if content:
                            title = next((r.get("title") for r in results if r.get("url") == url), None)
                            extracted.append({"url": url, "title": title, "content": content})

                    payload = {"results": results, "urls": urls, "extracted": extracted, "meta": {"profile_used": prof, "depth_used": depth, "extras_sent": False, "extras_stripped": True}}
                    try:
                        rc = _get_redis()
                        await asyncio.wait_for(
                            asyncio.to_thread(
                                rc.setex, search_cache_key, SEARCH_CACHE_TTL_SEC, json.dumps(payload)
                            ),
                            timeout=_redis_timeout_sec(),
                        )
                    except Exception:
                        pass
                    return payload
                except Exception:
                    pass
                error_type = "tavily_bad_request"
            elif status_code in (401, 403):
                error_type = "tavily_auth_error"
            elif status_code == 429:
                error_type = "tavily_rate_limited"
            elif status_code and status_code >= 500:
                error_type = "tavily_server_error"

            logger.error(
                "Tavily search failed: type=%s status=%s body_preview=%s err=%s",
                error_type,
                status_code,
                (body_preview or ""),
                repr(e),
                exc_info=True,
            )
            return {"results": [], "urls": [], "error": error_type, "status": status_code}


async def _extract_with_cache_and_quota(client: Any, user_id: str, url: str) -> Optional[str]:
    """Extract content for URL using Tavily, with cache and quota enforcement."""
    uhash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    cache_key = f"tavily:extract:{uhash}"
    try:
        rc = _get_redis()
        cached = await asyncio.wait_for(
            asyncio.to_thread(rc.get, cache_key),
            timeout=_redis_timeout_sec(),
        )
        if cached:
            data = json.loads(cached)
            return data.get("content")
    except Exception:
        pass

    # Reserve 1 API call for extract
    if not await asyncio.wait_for(
        asyncio.to_thread(_check_and_reserve_quota, user_id, 1),
        timeout=_redis_timeout_sec(),
    ):
        return None

    try:
        if hasattr(client, "extract"):
            res = await asyncio.wait_for(
                asyncio.to_thread(client.extract, url),
                timeout=_tavily_timeout_sec(),
            )
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
                    await asyncio.wait_for(
                        asyncio.to_thread(
                            rc.setex, cache_key, EXTRACT_CACHE_TTL_SEC, json.dumps({"content": content})
                        ),
                        timeout=_redis_timeout_sec(),
                    )
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
async def tavily_web_search(query: str, max_results: int = 10, profile: Optional[str] = None) -> Dict[str, Any]:
    """
    LangChain tool function for Tavily web search using user API key.
    """
    tool = get_user_tavily_tool()
    return await tool.search(query, max_results, profile)


def get_user_research_tools():
    """
    Get list of research tools that use user-specific API keys (Tavily only).
    """
    return [
        tavily_web_search,
    ]
