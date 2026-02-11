"""
Metadata and Observability Endpoints for Phase 6
Provides memory stats, quota status, and trace metadata for frontend transparency
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from functools import lru_cache
import ipaddress
import socket
import threading
import time
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx

from fastapi import APIRouter, HTTPException, Depends, Path, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_user, User
from app.db.supabase.client import get_supabase_client
from app.agents.unified.model_health import quota_tracker
from app.core.config import coordinator_bucket_name
from app.core.logging_config import get_logger
from app.core.rate_limiting.agent_wrapper import get_rate_limiter
from app.core.settings import settings
from app.tools.research_tools import FirecrawlTool

logger = get_logger("metadata_endpoints")
router = APIRouter(prefix="/metadata", tags=["Metadata"])

# ============================================
# Pydantic Models
# ============================================


class MemoryStats(BaseModel):
    """Memory statistics for a session"""

    facts_count: int = Field(..., description="Total facts in memory for this session")
    recent_facts: List[Dict[str, Any]] = Field(
        ..., description="Most recently retrieved facts"
    )
    write_count: int = Field(..., description="Number of facts written this session")
    last_write_at: Optional[datetime] = Field(
        None, description="Timestamp of last write"
    )
    relevance_scores: Optional[List[float]] = Field(
        None, description="Recent relevance scores"
    )


class QuotaStatus(BaseModel):
    """Real-time quota status across services"""

    gemini_pro_pct: float = Field(
        ...,
        ge=0,
        le=100,
        description="Gemini Pro usage percentage (tool-only image generation)",
    )
    gemini_flash_pct: float = Field(
        ..., ge=0, le=100, description="Gemini Flash usage percentage"
    )
    grounding_pct: float = Field(
        ..., ge=0, le=100, description="Grounding service usage percentage"
    )
    embeddings_pct: float = Field(
        ..., ge=0, le=100, description="Embeddings usage percentage"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Active quota warnings"
    )

    # Detailed breakdowns
    gemini_pro: Dict[str, Any] = Field(default_factory=dict)
    gemini_flash: Dict[str, Any] = Field(default_factory=dict)
    grounding: Dict[str, Any] = Field(default_factory=dict)
    embeddings: Dict[str, Any] = Field(default_factory=dict)


class TraceMetadata(BaseModel):
    """Enhanced trace metadata from LangSmith"""

    trace_id: str = Field(..., description="LangSmith trace ID")
    session_id: str = Field(..., description="Session ID")
    model_used: str = Field(..., description="Primary model used")
    fallback_chain: Optional[List[str]] = Field(
        None, description="Models tried in order"
    )
    fallback_occurred: bool = Field(False, description="Whether fallback was triggered")
    fallback_reason: Optional[str] = Field(None, description="Reason for fallback")

    search_service: Optional[str] = Field(None, description="Search service used")
    search_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Search service details"
    )

    memory_operations: Optional[Dict[str, Any]] = Field(
        None, description="Memory operation stats"
    )
    tool_calls: List[Dict[str, Any]] = Field(
        default_factory=list, description="Tools invoked"
    )

    duration_ms: Optional[int] = Field(
        None, description="Total execution time in milliseconds"
    )
    token_count: Optional[int] = Field(None, description="Total tokens used")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Link preview endpoint models and helpers
class LinkPreviewResponse(BaseModel):
    """Normalized link-preview payload for chat/artifact hover cards."""

    url: str = Field(..., description="Original request URL")
    resolvedUrl: str = Field(..., description="Final URL after redirect resolution")
    title: str | None = Field(None, description="Page title")
    description: str | None = Field(None, description="Page description")
    siteName: str | None = Field(None, description="Site name/hostname")
    imageUrl: str | None = Field(None, description="OpenGraph image URL")
    screenshotUrl: str | None = Field(
        None, description="Rendered screenshot URL from screenshot provider"
    )
    mode: Literal["screenshot", "og", "fallback"] = Field(
        ..., description="Primary preview mode used"
    )
    status: Literal["ok", "degraded"] = Field(
        ..., description="Preview quality status"
    )
    retryable: bool = Field(
        False,
        description="Whether retrying later may improve this preview",
    )


_LINK_PREVIEW_METADATA_REQUEST_TIMEOUT_SECONDS = 6.0
_LINK_PREVIEW_SCREENSHOT_REQUEST_TIMEOUT_SECONDS = 5.0
_LINK_PREVIEW_METADATA_SOFT_TIMEOUT_SECONDS = 4.0
_LINK_PREVIEW_SCREENSHOT_SOFT_TIMEOUT_SECONDS = 0.25
_LINK_PREVIEW_MAX_REDIRECTS = 5
_LINK_PREVIEW_MAX_HTML_BYTES = 350_000
_LINK_PREVIEW_HEAD_SCAN_WINDOW_BYTES = 8192
_LINK_PREVIEW_CACHE_TTL_SECONDS = 600
_LINK_PREVIEW_HOST_CACHE_TTL_SECONDS = 300

_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)

_LINK_PREVIEW_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LINK_PREVIEW_CACHE_LOCK = threading.Lock()
_LINK_PREVIEW_HOST_IP_CACHE: dict[str, tuple[float, tuple[str, ...]]] = {}
_LINK_PREVIEW_HOST_IP_CACHE_LOCK = threading.Lock()


@dataclass
class _LinkPreviewMetadata:
    resolved_url: str
    title: str | None
    description: str | None
    site_name: str | None
    image_url: str | None


class _LinkPreviewFetchError(Exception):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        resolved_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.resolved_url = resolved_url


def _fallback_metadata(url: str) -> _LinkPreviewMetadata:
    site_name = _site_name_from_url(url)
    return _LinkPreviewMetadata(
        resolved_url=url,
        title=site_name,
        description="Preview unavailable right now.",
        site_name=site_name,
        image_url=None,
    )


def _resolve_hostname_ips(hostname: str) -> tuple[str, ...]:
    now = time.monotonic()
    with _LINK_PREVIEW_HOST_IP_CACHE_LOCK:
        cached = _LINK_PREVIEW_HOST_IP_CACHE.get(hostname)
        if cached:
            expires_at, ip_values = cached
            if expires_at > now:
                return ip_values
            _LINK_PREVIEW_HOST_IP_CACHE.pop(hostname, None)

    infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
    ips = tuple(sorted({info[4][0] for info in infos if info and info[4]}))
    with _LINK_PREVIEW_HOST_IP_CACHE_LOCK:
        _LINK_PREVIEW_HOST_IP_CACHE[hostname] = (
            now + _LINK_PREVIEW_HOST_CACHE_TTL_SECONDS,
            ips,
        )
    return ips


async def _cancel_task(task: asyncio.Task[Any]) -> None:
    if task.done():
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _cache_key_for_preview(url: str) -> str:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.netloc or "").lower()
    path = parsed.path or "/"
    query = parsed.query or ""
    return f"{scheme}://{host}{path}?{query}"


def _get_cached_link_preview(cache_key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _LINK_PREVIEW_CACHE_LOCK:
        hit = _LINK_PREVIEW_CACHE.get(cache_key)
        if not hit:
            return None
        expires_at, payload = hit
        if expires_at <= now:
            _LINK_PREVIEW_CACHE.pop(cache_key, None)
            return None
        return dict(payload)


def _store_cached_link_preview(cache_key: str, payload: dict[str, Any]) -> None:
    with _LINK_PREVIEW_CACHE_LOCK:
        _LINK_PREVIEW_CACHE[cache_key] = (
            time.monotonic() + _LINK_PREVIEW_CACHE_TTL_SECONDS,
            dict(payload),
        )


def _is_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_safe_public_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format"

    if parsed.scheme not in {"http", "https"}:
        return False, f"Disallowed scheme: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"

    lowered = hostname.lower()
    if lowered in {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}:
        return False, f"Blocked hostname: {hostname}"
    if lowered in {"metadata.google.internal", "169.254.169.254"}:
        return False, "Blocked cloud metadata endpoint"

    try:
        resolved_ips = _resolve_hostname_ips(hostname)
    except socket.gaierror:
        return False, f"Could not resolve hostname: {hostname}"
    except Exception as exc:
        return False, f"Hostname resolution failed: {exc}"

    for ip_str in resolved_ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for network in _PRIVATE_NETWORKS:
            if ip in network:
                return False, f"Resolved to private IP: {ip}"

    return True, ""


def _resolve_redirect_url(base_url: str, location: str) -> str:
    try:
        return str(httpx.URL(base_url).join(location))
    except Exception:
        return urljoin(base_url, location)


def _extract_meta_content(soup: BeautifulSoup, *keys: str) -> str | None:
    for key in keys:
        tag = soup.find("meta", property=key) or soup.find("meta", attrs={"name": key})
        if not tag:
            continue
        value = (tag.get("content") or "").strip()
        if value:
            return value
    return None


def _site_name_from_url(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").replace("www.", "") or url
    except Exception:
        return url


def _extract_named_url(payload: Any, keys: set[str]) -> str | None:
    queue: list[Any] = [payload]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                normalized_key = str(key).lower().replace("_", "")
                if normalized_key in keys and isinstance(value, str):
                    candidate = value.strip()
                    if _is_http_url(candidate):
                        return candidate
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)
    return None


@lru_cache(maxsize=1)
def _link_preview_firecrawl_tool() -> FirecrawlTool:
    return FirecrawlTool(api_key=settings.firecrawl_api_key)


async def _attempt_screenshot_preview(url: str) -> str | None:
    tool = _link_preview_firecrawl_tool()
    if getattr(tool, "disabled", True):
        return None

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                tool.scrape_with_options,
                url,
                formats=["screenshot"],
                only_main_content=False,
                max_age=3600,
            ),
            timeout=_LINK_PREVIEW_SCREENSHOT_REQUEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.debug("link_preview_screenshot_request_timeout", url=url)
        return None
    except Exception as exc:
        logger.debug("link_preview_screenshot_attempt_failed", error=str(exc), url=url)
        return None

    if not isinstance(result, dict) or result.get("error"):
        return None

    screenshot_url = _extract_named_url(
        result,
        {"screenshot", "screenshoturl"},
    )
    if not screenshot_url:
        return None

    safe, reason = _is_safe_public_url(screenshot_url)
    if not safe:
        logger.warning(
            "link_preview_screenshot_rejected",
            screenshot_url=screenshot_url,
            reason=reason,
        )
        return None
    return screenshot_url


async def _request_html_with_safe_redirects(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[str, bytes, str]:
    current_url = url

    for _ in range(_LINK_PREVIEW_MAX_REDIRECTS + 1):
        safe, reason = _is_safe_public_url(current_url)
        if not safe:
            raise _LinkPreviewFetchError(
                f"URL blocked for security reasons: {reason}",
                retryable=False,
                resolved_url=current_url,
            )

        try:
            async with client.stream(
                "GET",
                current_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                },
                follow_redirects=False,
            ) as response:
                if 300 <= response.status_code < 400:
                    location = (response.headers.get("location") or "").strip()
                    if not location:
                        raise _LinkPreviewFetchError(
                            "Redirect missing location header",
                            retryable=True,
                            resolved_url=current_url,
                        )
                    current_url = _resolve_redirect_url(current_url, location)
                    continue

                if response.status_code >= 400:
                    raise _LinkPreviewFetchError(
                        f"Upstream returned HTTP {response.status_code}",
                        retryable=response.status_code >= 500,
                        resolved_url=current_url,
                    )

                chunks: list[bytes] = []
                total = 0
                head_window = b""
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                    remaining = _LINK_PREVIEW_MAX_HTML_BYTES - total
                    if remaining <= 0:
                        break
                    clipped = chunk[:remaining]
                    chunks.append(clipped)
                    total += len(clipped)
                    head_window = (head_window + clipped)[
                        -_LINK_PREVIEW_HEAD_SCAN_WINDOW_BYTES :
                    ]
                    if b"</head>" in head_window.lower():
                        break
                    if total >= _LINK_PREVIEW_MAX_HTML_BYTES:
                        break

                body = b"".join(chunks)
                content_type = (response.headers.get("content-type") or "").lower()
                resolved_url = str(response.url) if response.url else current_url
                return resolved_url, body, content_type

        except _LinkPreviewFetchError:
            raise
        except httpx.TimeoutException as exc:
            raise _LinkPreviewFetchError(
                f"Timeout while fetching preview: {exc}",
                retryable=True,
                resolved_url=current_url,
            ) from exc
        except httpx.HTTPError as exc:
            raise _LinkPreviewFetchError(
                f"Failed to fetch preview: {exc}",
                retryable=True,
                resolved_url=current_url,
            ) from exc

    raise _LinkPreviewFetchError(
        "Too many redirects while resolving preview",
        retryable=True,
        resolved_url=current_url,
    )


async def _fetch_link_metadata(url: str) -> _LinkPreviewMetadata:
    async with httpx.AsyncClient(
        timeout=_LINK_PREVIEW_METADATA_REQUEST_TIMEOUT_SECONDS
    ) as client:
        resolved_url, raw_body, content_type = await _request_html_with_safe_redirects(
            client, url
        )

    html_text = raw_body.decode("utf-8", errors="replace") if raw_body else ""
    title: str | None = None
    description: str | None = None
    site_name: str | None = None
    image_url: str | None = None

    if html_text:
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            title = _extract_meta_content(soup, "og:title", "twitter:title")
            if not title and soup.title and soup.title.string:
                title = soup.title.string.strip()

            description = _extract_meta_content(
                soup,
                "og:description",
                "twitter:description",
                "description",
            )
            site_name = _extract_meta_content(
                soup,
                "og:site_name",
                "application-name",
            )

            raw_image = _extract_meta_content(
                soup,
                "og:image",
                "twitter:image",
                "twitter:image:src",
            )
            if raw_image:
                candidate = _resolve_redirect_url(resolved_url, raw_image)
                if _is_http_url(candidate):
                    safe, _ = _is_safe_public_url(candidate)
                    if safe:
                        image_url = candidate
        except Exception as exc:
            logger.debug("link_preview_html_parse_failed", error=str(exc), url=url)

    content_is_html = "text/html" in content_type or "application/xhtml" in content_type
    if not content_is_html and not title:
        title = _site_name_from_url(resolved_url)
        description = "Preview metadata unavailable for this content type."

    if not site_name:
        site_name = _site_name_from_url(resolved_url)

    return _LinkPreviewMetadata(
        resolved_url=resolved_url,
        title=title,
        description=description,
        site_name=site_name,
        image_url=image_url,
    )


# ============================================
# Memory Endpoints
# ============================================


@router.get("/memory/{session_id}/stats", response_model=MemoryStats)
async def get_memory_stats(
    session_id: str = Path(..., description="Session ID to get memory stats for"),
    current_user: User = Depends(get_current_user),
) -> MemoryStats:
    """
    Get memory statistics for a specific session.

    Returns facts count, recent retrievals, write stats, and relevance scores.
    """
    try:
        supabase = get_supabase_client()

        # Get facts count for this session
        result = (
            supabase.table("memory_facts")
            .select("*", count="exact")
            .eq("session_id", session_id)
            .eq("user_id", current_user.id)
            .execute()
        )

        facts_count = result.count if result else 0

        # Get recent facts (last 5)
        recent_result = (
            supabase.table("memory_facts")
            .select("*")
            .eq("session_id", session_id)
            .eq("user_id", current_user.id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )

        recent_facts = []
        if recent_result and recent_result.data:
            recent_facts = [
                {
                    "fact": fact.get("fact", ""),
                    "relevance_score": fact.get("relevance_score"),
                    "created_at": fact.get("created_at"),
                }
                for fact in recent_result.data
            ]

        # Get write count for this session
        write_result = (
            supabase.table("memory_facts")
            .select("created_at", count="exact")
            .eq("session_id", session_id)
            .eq("user_id", current_user.id)
            .gte("created_at", (datetime.utcnow() - timedelta(hours=24)).isoformat())
            .execute()
        )

        write_count = write_result.count if write_result else 0
        last_write_at = None

        # Get last_write_at from recent_result (already ordered by created_at desc)
        if recent_result and recent_result.data and len(recent_result.data) > 0:
            last_write_at = recent_result.data[0].get("created_at")

        # Get recent relevance scores
        relevance_scores = [
            fact.get("relevance_score", 0.0)
            for fact in recent_facts
            if fact.get("relevance_score") is not None
        ]

        return MemoryStats(
            facts_count=facts_count,
            recent_facts=recent_facts,
            write_count=write_count,
            last_write_at=last_write_at,
            relevance_scores=relevance_scores if relevance_scores else None,
        )

    except Exception as e:
        logger.error(f"Error fetching memory stats: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch memory stats: {str(e)}"
        )


# ============================================
# Quota Endpoints
# ============================================


@router.get("/quotas/status", response_model=QuotaStatus)
async def get_quota_status(
    current_user: User = Depends(get_current_user),
) -> QuotaStatus:
    """
    Get real-time quota status for all services.

    Returns usage percentages and warnings for rate limits approaching.
    """
    try:
        coordinator_bucket = coordinator_bucket_name(
            "google", with_subagents=True, zendesk=False
        )
        image_bucket = "internal.image"
        grounding_bucket = "internal.grounding"
        embedding_bucket = "internal.embedding"

        # Get current usage for each service
        gemini_pro_health = await quota_tracker.get_health(image_bucket)
        gemini_flash_health = await quota_tracker.get_health(coordinator_bucket)
        grounding_health = await quota_tracker.get_health(grounding_bucket)
        embedding_health = await quota_tracker.get_health(embedding_bucket)

        # Calculate percentages
        def calculate_percentage(used: int, limit: int) -> float:
            if limit == 0:
                return 0.0
            return min(100.0, (used / limit) * 100)

        gemini_pro_pct = calculate_percentage(
            gemini_pro_health.rpd_used, gemini_pro_health.rpd_limit
        )
        gemini_flash_pct = calculate_percentage(
            gemini_flash_health.rpd_used, gemini_flash_health.rpd_limit
        )

        grounding_pct = calculate_percentage(
            grounding_health.rpd_used,
            grounding_health.rpd_limit,
        )
        embeddings_pct = calculate_percentage(
            embedding_health.rpd_used,
            embedding_health.rpd_limit,
        )

        # Generate warnings
        warnings = []
        if gemini_pro_pct > 80:
            warnings.append(
                f"Gemini Pro Image usage at {gemini_pro_pct:.0f}% - consider fallback"
            )
        if gemini_flash_pct > 80:
            warnings.append(f"Gemini Flash usage at {gemini_flash_pct:.0f}%")
        if grounding_pct > 80:
            warnings.append(
                f"Grounding service approaching limit ({grounding_pct:.0f}%)"
            )
        if embeddings_pct > 80:
            warnings.append(f"Embeddings usage at {embeddings_pct:.0f}%")

        # Detailed breakdowns
        gemini_pro_details = {
            "bucket": gemini_pro_health.bucket,
            "rpm_used": gemini_pro_health.rpm_used,
            "rpm_limit": gemini_pro_health.rpm_limit,
            "rpd_used": gemini_pro_health.rpd_used,
            "rpd_limit": gemini_pro_health.rpd_limit,
            "circuit_state": gemini_pro_health.circuit_state,
            "available": gemini_pro_health.available,
        }

        gemini_flash_details = {
            "rpm_used": gemini_flash_health.rpm_used,
            "rpm_limit": gemini_flash_health.rpm_limit,
            "rpd_used": gemini_flash_health.rpd_used,
            "rpd_limit": gemini_flash_health.rpd_limit,
            "circuit_state": gemini_flash_health.circuit_state,
            "available": gemini_flash_health.available,
        }

        grounding_details = {
            "bucket": grounding_health.bucket,
            "rpm_used": grounding_health.rpm_used,
            "rpm_limit": grounding_health.rpm_limit,
            "rpd_used": grounding_health.rpd_used,
            "rpd_limit": grounding_health.rpd_limit,
            "circuit_state": grounding_health.circuit_state,
            "available": grounding_health.available,
        }

        embedding_details = {
            "bucket": embedding_health.bucket,
            "rpm_used": embedding_health.rpm_used,
            "rpm_limit": embedding_health.rpm_limit,
            "rpd_used": embedding_health.rpd_used,
            "rpd_limit": embedding_health.rpd_limit,
            "tpm_used": embedding_health.tpm_used,
            "tpm_limit": embedding_health.tpm_limit,
            "circuit_state": embedding_health.circuit_state,
            "available": embedding_health.available,
        }

        return QuotaStatus(
            gemini_pro_pct=gemini_pro_pct,
            gemini_flash_pct=gemini_flash_pct,
            grounding_pct=grounding_pct,
            embeddings_pct=embeddings_pct,
            warnings=warnings,
            gemini_pro=gemini_pro_details,
            gemini_flash=gemini_flash_details,
            grounding=grounding_details,
            embeddings=embedding_details,
        )

    except Exception as e:
        logger.error(f"Error fetching quota status: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch quota status: {str(e)}"
        )


# ============================================
# Trace Metadata Endpoints
# ============================================


@router.get("/sessions/{session_id}/traces/{trace_id}", response_model=TraceMetadata)
async def get_trace_metadata(
    session_id: str = Path(..., description="Session ID"),
    trace_id: str = Path(..., description="Trace ID from LangSmith"),
    current_user: User = Depends(get_current_user),
) -> TraceMetadata:
    """
    Get enhanced metadata for a specific trace.

    This would typically fetch from LangSmith API, but for now returns
    structured metadata from our local tracking.
    """
    try:
        # Verify session ownership
        supabase = get_supabase_client()
        session_check = (
            supabase.table("chat_sessions")
            .select("id")
            .eq("id", session_id)
            .eq("user_id", current_user.id)
            .execute()
        )

        if not session_check.data:
            raise HTTPException(
                status_code=404, detail="Session not found or access denied"
            )

        # In production, this would fetch from LangSmith API
        # For now, we'll return mock structured data
        # You could also store this in Redis or database during execution

        # Example implementation - replace with actual LangSmith integration
        metadata = TraceMetadata(
            trace_id=trace_id,
            session_id=session_id,
            model_used="gemini-2.5-flash",
            fallback_chain=None,
            fallback_occurred=False,
            fallback_reason=None,
            search_service="gemini_grounding",
            search_metadata={
                "results_count": 5,
                "max_requested": 5,
                "query_length": 42,
            },
            memory_operations={
                "retrieval_attempted": True,
                "facts_retrieved": 3,
                "write_attempted": True,
                "facts_written": 1,
            },
            tool_calls=[
                {
                    "tool": "search_knowledge_base",
                    "confidence": 0.95,
                    "duration_ms": 245,
                }
            ],
            duration_ms=1250,
            token_count=850,
            timestamp=datetime.now(timezone.utc),
        )

        return metadata

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching trace metadata: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch trace metadata: {str(e)}"
        )


# ============================================
# Link Preview Endpoint
# ============================================


@router.get("/link-preview", response_model=LinkPreviewResponse)
async def get_link_preview(
    url: str = Query(..., description="External URL to preview"),
    current_user: User = Depends(get_current_user),
) -> LinkPreviewResponse:
    """
    Generate a safe link preview payload for chat and artifact link hovers.

    Flow:
    1. Validate URL with SSRF protections.
    2. Attempt screenshot preview first.
    3. Fetch OpenGraph/title metadata as fallback or enrichment.
    4. Return degraded fallback shell when metadata cannot be fetched.
    """
    _ = current_user  # Required for authenticated access; value used by dependency.

    candidate_url = (url or "").strip()
    if not candidate_url:
        raise HTTPException(status_code=400, detail="URL is required")

    if not _is_http_url(candidate_url):
        raise HTTPException(
            status_code=400,
            detail="Only http/https URLs are supported for link previews",
        )

    safe, reason = _is_safe_public_url(candidate_url)
    if not safe:
        raise HTTPException(
            status_code=400,
            detail=f"URL blocked for security reasons: {reason}",
        )

    cache_key = _cache_key_for_preview(candidate_url)
    cached = _get_cached_link_preview(cache_key)
    if cached:
        return LinkPreviewResponse(**cached)

    started_at = time.perf_counter()
    screenshot_task = asyncio.create_task(_attempt_screenshot_preview(candidate_url))
    metadata_task = asyncio.create_task(_fetch_link_metadata(candidate_url))

    screenshot_url: str | None = None
    metadata_error: _LinkPreviewFetchError | None = None
    metadata_timed_out = False
    screenshot_timed_out = False

    try:
        metadata = await asyncio.wait_for(
            metadata_task,
            timeout=_LINK_PREVIEW_METADATA_SOFT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        metadata_timed_out = True
        await _cancel_task(metadata_task)
        metadata = _fallback_metadata(candidate_url)
        logger.info(
            "link_preview_metadata_soft_timeout",
            url=candidate_url,
            timeout_seconds=_LINK_PREVIEW_METADATA_SOFT_TIMEOUT_SECONDS,
        )
    except _LinkPreviewFetchError as exc:
        metadata_error = exc
        logger.warning(
            "link_preview_metadata_fetch_failed",
            url=candidate_url,
            error=str(exc),
            retryable=exc.retryable,
        )
        fallback_resolved = exc.resolved_url or candidate_url
        metadata = _fallback_metadata(fallback_resolved)

    # Prioritize speed: if OG image is already available, do not block the response
    # waiting for screenshot capture.
    if metadata.image_url:
        if screenshot_task.done():
            try:
                screenshot_url = screenshot_task.result()
            except Exception as exc:
                logger.debug(
                    "link_preview_screenshot_join_failed",
                    error=str(exc),
                    url=candidate_url,
                )
        else:
            screenshot_timed_out = True
            await _cancel_task(screenshot_task)
    else:
        try:
            screenshot_url = await asyncio.wait_for(
                screenshot_task,
                timeout=_LINK_PREVIEW_SCREENSHOT_SOFT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            screenshot_timed_out = True
            await _cancel_task(screenshot_task)
            logger.debug(
                "link_preview_screenshot_soft_timeout",
                url=candidate_url,
                timeout_seconds=_LINK_PREVIEW_SCREENSHOT_SOFT_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            await _cancel_task(screenshot_task)
            logger.debug(
                "link_preview_screenshot_join_failed",
                error=str(exc),
                url=candidate_url,
            )

    mode: Literal["screenshot", "og", "fallback"] = "fallback"
    status: Literal["ok", "degraded"] = "degraded"

    if screenshot_url:
        mode = "screenshot"
    elif metadata.image_url:
        mode = "og"

    metadata_fetch_ok = metadata_error is None and not metadata_timed_out
    if metadata_fetch_ok or screenshot_url or metadata.image_url:
        # Metadata-only previews are valid and should not show degraded banners.
        status = "ok"
    else:
        status = "degraded"

    retryable = (
        status == "degraded"
        and bool(
            (metadata_error and metadata_error.retryable)
            or metadata_timed_out
            or screenshot_timed_out
        )
    )

    payload = LinkPreviewResponse(
        url=candidate_url,
        resolvedUrl=metadata.resolved_url or candidate_url,
        title=metadata.title,
        description=metadata.description,
        siteName=metadata.site_name,
        imageUrl=metadata.image_url,
        screenshotUrl=screenshot_url,
        mode=mode,
        status=status,
        retryable=retryable,
    )

    _store_cached_link_preview(cache_key, payload.model_dump())
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "link_preview_mode_selected",
        url=candidate_url,
        mode=payload.mode,
        status=payload.status,
        retryable=payload.retryable,
        duration_ms=duration_ms,
        metadata_timed_out=metadata_timed_out,
        screenshot_timed_out=screenshot_timed_out,
    )
    return payload


# ============================================
# Health Check Endpoint
# ============================================


@router.get("/health")
async def health_check():
    """
    Check health of metadata services.
    """
    try:
        rate_limiter = get_rate_limiter()
        limiter_health = await rate_limiter.health_check()
        redis_ok = limiter_health.get("redis", False)

        return {
            "status": "healthy" if redis_ok else "degraded",
            "services": {
                "redis": "healthy" if redis_ok else "unavailable",
                "memory": "healthy",  # Could check Supabase connection
                "quotas": (
                    "healthy"
                    if limiter_health.get("overall") == "healthy"
                    else "degraded"
                ),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }
