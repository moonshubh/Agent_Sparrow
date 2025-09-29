"""
Tool Orchestrator for Log Analysis Agent

This module provides centralized tool management with parallel execution
and caching capabilities for efficient log analysis.
"""

import asyncio
import hashlib
import json
import logging
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from ..schemas.log_schemas import ErrorPattern, LogMetadata
except ImportError:
    try:
        from schemas.log_schemas import ErrorPattern, LogMetadata
    except ImportError:
        from app.agents_v2.log_analysis_agent.schemas.log_schemas import ErrorPattern, LogMetadata

logger = logging.getLogger(__name__)


class ToolStatus(Enum):
    """Status of tool execution"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CACHED = "cached"


@dataclass
class ToolQuery:
    """Optimized queries for different tools"""
    kb_query: str
    feedme_query: str
    web_query: str
    error_signatures: List[str] = field(default_factory=list)
    version_info: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KBArticle:
    """Knowledge Base article result"""
    article_id: str
    title: str
    content: str
    url: str
    relevance_score: float
    categories: List[str] = field(default_factory=list)
    error_patterns_matched: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "article_id": self.article_id,
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "relevance_score": self.relevance_score,
            "categories": self.categories,
            "error_patterns_matched": self.error_patterns_matched
        }


@dataclass
class FeedMeConversation:
    """FeedMe conversation result"""
    conversation_id: str
    title: str
    summary: str
    resolution: str
    error_patterns: List[str]
    resolution_status: str
    confidence_score: float
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "conversation_id": self.conversation_id,
            "title": self.title,
            "summary": self.summary,
            "resolution": self.resolution,
            "error_patterns": self.error_patterns,
            "resolution_status": self.resolution_status,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


@dataclass
class WebResource:
    """Web search result"""
    url: str
    title: str
    snippet: str
    relevance_score: float
    source_domain: str
    published_date: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "relevance_score": self.relevance_score,
            "source_domain": self.source_domain,
            "published_date": self.published_date.isoformat() if self.published_date else None
        }


@dataclass
class ToolResults:
    """Combined results from all tools"""
    kb_articles: List[KBArticle] = field(default_factory=list)
    feedme_conversations: List[FeedMeConversation] = field(default_factory=list)
    web_resources: List[WebResource] = field(default_factory=list)
    execution_time_ms: int = 0
    tool_statuses: Dict[str, ToolStatus] = field(default_factory=dict)
    cache_hit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "kb_articles": [a.to_dict() for a in self.kb_articles],
            "feedme_conversations": [c.to_dict() for c in self.feedme_conversations],
            "web_resources": [r.to_dict() for r in self.web_resources],
            "execution_time_ms": self.execution_time_ms,
            "tool_statuses": {k: v.value for k, v in self.tool_statuses.items()},
            "cache_hit": self.cache_hit
        }

    @property
    def total_results(self) -> int:
        """Get total number of results"""
        return len(self.kb_articles) + len(self.feedme_conversations) + len(self.web_resources)

    @property
    def has_results(self) -> bool:
        """Check if any results were found"""
        return self.total_results > 0


class ToolResultCache:
    """Cache for tool results with TTL"""

    def __init__(self, ttl_minutes: int = 15, max_entries: int = 100):
        """
        Initialize cache with TTL.

        Args:
            ttl_minutes: Time to live for cache entries in minutes
            max_entries: Maximum number of cached entries to retain
        """
        self._cache: "OrderedDict[str, Tuple[ToolResults, datetime]]" = OrderedDict()
        self.ttl = timedelta(minutes=ttl_minutes)
        self.max_entries = max_entries

    async def get(self, cache_key: str) -> Optional[ToolResults]:
        """
        Get cached results if available and not expired.

        Args:
            cache_key: Cache key for the results

        Returns:
            Cached ToolResults or None if not found/expired
        """
        cached_entry = self._cache.get(cache_key)
        if cached_entry:
            results, timestamp = cached_entry
            if datetime.now() - timestamp < self.ttl:
                logger.debug(f"Cache hit for key: {cache_key[:16]}...")
                cached_copy = deepcopy(results)
                cached_copy.cache_hit = True
                if cached_copy.tool_statuses:
                    cached_copy.tool_statuses = {
                        tool: (ToolStatus.CACHED if status == ToolStatus.SUCCESS else status)
                        for tool, status in cached_copy.tool_statuses.items()
                    }
                return cached_copy

            # Expired entry, remove it from cache
            del self._cache[cache_key]
            logger.debug(f"Cache expired for key: {cache_key[:16]}...")

        return None

    async def set(self, cache_key: str, results: ToolResults):
        """
        Store results in cache.

        Args:
            cache_key: Cache key for the results
            results: ToolResults to cache
        """
        results_for_cache = deepcopy(results)
        results_for_cache.cache_hit = False
        self._cache[cache_key] = (results_for_cache, datetime.now())
        logger.debug(f"Cached results for key: {cache_key[:16]}...")

        # Clean up old entries
        await self._cleanup_expired()
        self._evict_if_needed()

    async def _cleanup_expired(self):
        """Remove expired cache entries"""
        now = datetime.now()
        expired_keys = [
            key for key, (_, timestamp) in self._cache.items()
            if now - timestamp >= self.ttl
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

    def _evict_if_needed(self) -> None:
        """Evict oldest cache entries when exceeding capacity"""
        while len(self._cache) > self.max_entries:
            evicted_key, _ = self._cache.popitem(last=False)
            logger.debug(f"Evicted cache entry due to capacity: {evicted_key[:16]}...")


class LogToolOrchestrator:
    """
    Centralized tool management with parallel execution for log analysis.

    This orchestrator coordinates searches across KB, FeedMe, and web resources,
    executing them in parallel for optimal performance.
    """

    def __init__(self, timeout_seconds: int = 30):
        """
        Initialize the orchestrator.

        Args:
            timeout_seconds: Timeout for tool execution
        """
        self.timeout = timeout_seconds
        self.cache = ToolResultCache()

        # Lazy import tools to avoid circular dependencies
        self._kb_tool = None
        self._feedme_tool = None
        self._tavily_tool = None

    def _initialize_tools(self):
        """Lazy initialization of tools"""
        if self._kb_tool is None:
            from .kb_search import EnhancedKBSearch
            self._kb_tool = EnhancedKBSearch()

        if self._feedme_tool is None:
            from .feedme_search import FeedMeLogSearch
            self._feedme_tool = FeedMeLogSearch()

        if self._tavily_tool is None:
            from .tavily_search import TavilyLogSearch
            self._tavily_tool = TavilyLogSearch()

    def generate_cache_key(
        self,
        patterns: List[ErrorPattern],
        metadata: LogMetadata
    ) -> str:
        """
        Generate a unique cache key based on patterns and metadata.

        Args:
            patterns: List of error patterns
            metadata: Log metadata

        Returns:
            SHA256 hash as cache key
        """
        key_data = {
            "patterns": [
                {
                    "category": p.category.name if p.category else "UNKNOWN",
                    "description": p.description,
                    "occurrences": p.occurrences
                }
                for p in patterns[:5]  # Top 5 patterns
            ],
            "version": metadata.mailbird_version,
            "os": metadata.os_version,
            "error_count": metadata.error_count
        }

        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def prepare_queries(
        self,
        patterns: List[ErrorPattern],
        metadata: LogMetadata
    ) -> ToolQuery:
        """
        Prepare optimized queries for each tool based on patterns.

        Args:
            patterns: List of error patterns
            metadata: Log metadata

        Returns:
            ToolQuery with optimized queries for each tool
        """
        # Get top error patterns for query building
        top_patterns = sorted(
            patterns,
            key=lambda p: (p.occurrences, p.confidence or 0.0),
            reverse=True
        )[:3]

        # Extract error signatures
        error_signatures = []
        for pattern in top_patterns:
            # Extract key error messages from sample entries
            for entry in pattern.sample_entries[:2]:
                if entry.message:
                    # Clean and truncate message
                    msg = entry.message.strip()[:100]
                    if msg not in error_signatures:
                        error_signatures.append(msg)

        # Build KB query - focus on error categories and symptoms
        kb_terms = []
        for pattern in top_patterns:
            kb_terms.append(pattern.description)
            if pattern.category:
                kb_terms.append(pattern.category.name.replace("_", " ").lower())

        kb_query = f"Mailbird {metadata.mailbird_version} " + " ".join(kb_terms[:3])

        # Build FeedMe query - focus on error patterns and resolution
        feedme_query = " OR ".join([
            f'"{sig}"' for sig in error_signatures[:2]
        ]) if error_signatures else patterns[0].description if patterns else "Mailbird error"

        # Build web query - broader search for solutions
        web_terms = []
        if patterns:
            web_terms.append(patterns[0].description)
        web_terms.append(f"Mailbird {metadata.mailbird_version}")
        if metadata.os_version and "Windows" in metadata.os_version:
            web_terms.append("Windows")
        web_terms.append("solution fix")

        web_query = " ".join(web_terms)

        return ToolQuery(
            kb_query=kb_query,
            feedme_query=feedme_query,
            web_query=web_query,
            error_signatures=error_signatures,
            version_info=metadata.mailbird_version,
            metadata={
                "os": metadata.os_version,
                "error_count": metadata.error_count,
                "account_count": metadata.account_count
            }
        )

    async def search_all(
        self,
        patterns: List[ErrorPattern],
        metadata: LogMetadata,
        use_cache: bool = True
    ) -> ToolResults:
        """
        Execute all tool searches in parallel.

        Args:
            patterns: List of error patterns
            metadata: Log metadata
            use_cache: Whether to use cached results

        Returns:
            Combined ToolResults from all searches
        """
        import time
        start_time = time.time()

        # Initialize tools if needed
        self._initialize_tools()

        # Check cache first
        if use_cache:
            cache_key = self.generate_cache_key(patterns, metadata)
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info(
                    "Returning cached tool search results - "
                    f"KB: {len(cached.kb_articles)}, "
                    f"FeedMe: {len(cached.feedme_conversations)}, "
                    f"Web: {len(cached.web_resources)}"
                )
                return cached
        else:
            cache_key = None

        # Prepare optimized queries
        queries = self.prepare_queries(patterns, metadata)

        logger.info(
            f"Starting parallel tool searches - "
            f"KB: '{queries.kb_query[:50]}...', "
            f"FeedMe: '{queries.feedme_query[:50]}...', "
            f"Web: '{queries.web_query[:50]}...'"
        )

        # Execute searches in parallel with timeout
        results = ToolResults()

        try:
            # Create search tasks
            tasks = [
                self._search_kb_with_timeout(queries, patterns),
                self._search_feedme_with_timeout(queries, patterns, metadata),
                self._search_tavily_with_timeout(queries, patterns, metadata)
            ]

            # Execute in parallel
            search_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process KB results
            if isinstance(search_results[0], tuple):
                kb_articles, kb_status = search_results[0]
                results.kb_articles = kb_articles
                results.tool_statuses["kb_search"] = kb_status
            else:
                logger.error(f"KB search error: {search_results[0]}")
                results.tool_statuses["kb_search"] = ToolStatus.FAILED

            # Process FeedMe results
            if isinstance(search_results[1], tuple):
                feedme_convs, feedme_status = search_results[1]
                results.feedme_conversations = feedme_convs
                results.tool_statuses["feedme_search"] = feedme_status
            else:
                logger.error(f"FeedMe search error: {search_results[1]}")
                results.tool_statuses["feedme_search"] = ToolStatus.FAILED

            # Process Tavily results
            if isinstance(search_results[2], tuple):
                web_resources, web_status = search_results[2]
                results.web_resources = web_resources
                results.tool_statuses["tavily_search"] = web_status
            else:
                logger.error(f"Tavily search error: {search_results[2]}")
                results.tool_statuses["tavily_search"] = ToolStatus.FAILED

        except Exception as e:
            logger.error(f"Tool orchestration error: {e}")

        # Calculate execution time
        execution_time = int((time.time() - start_time) * 1000)
        results.execution_time_ms = execution_time

        # Cache results if we have any
        if cache_key and results.has_results:
            await self.cache.set(cache_key, results)

        logger.info(
            f"Tool search completed in {execution_time}ms - "
            f"KB: {len(results.kb_articles)}, "
            f"FeedMe: {len(results.feedme_conversations)}, "
            f"Web: {len(results.web_resources)}"
        )

        return results

    async def _search_kb_with_timeout(
        self,
        queries: ToolQuery,
        patterns: List[ErrorPattern]
    ) -> Tuple[List[KBArticle], ToolStatus]:
        """Execute KB search with timeout"""
        try:
            async with asyncio.timeout(self.timeout):
                articles = await self._kb_tool.search_for_log_errors(
                    error_patterns=patterns,
                    query_override=queries.kb_query
                )
                return articles, ToolStatus.SUCCESS
        except asyncio.TimeoutError:
            logger.warning(f"KB search timed out after {self.timeout}s")
            return [], ToolStatus.TIMEOUT
        except Exception as e:
            logger.error(f"KB search failed: {e}")
            return [], ToolStatus.FAILED

    async def _search_feedme_with_timeout(
        self,
        queries: ToolQuery,
        patterns: List[ErrorPattern],
        metadata: LogMetadata
    ) -> Tuple[List[FeedMeConversation], ToolStatus]:
        """Execute FeedMe search with timeout"""
        try:
            async with asyncio.timeout(self.timeout):
                conversations = await self._feedme_tool.find_similar_issues(
                    patterns=patterns,
                    metadata=metadata,
                    query_override=queries.feedme_query
                )
                return conversations, ToolStatus.SUCCESS
        except asyncio.TimeoutError:
            logger.warning(f"FeedMe search timed out after {self.timeout}s")
            return [], ToolStatus.TIMEOUT
        except Exception as e:
            logger.error(f"FeedMe search failed: {e}")
            return [], ToolStatus.FAILED

    async def _search_tavily_with_timeout(
        self,
        queries: ToolQuery,
        patterns: List[ErrorPattern],
        metadata: LogMetadata
    ) -> Tuple[List[WebResource], ToolStatus]:
        """Execute Tavily search with timeout"""
        try:
            async with asyncio.timeout(self.timeout):
                resources = await self._tavily_tool.search_web_solutions(
                    patterns=patterns,
                    metadata=metadata,
                    query_override=queries.web_query
                )
                return resources, ToolStatus.SUCCESS
        except asyncio.TimeoutError:
            logger.warning(f"Tavily search timed out after {self.timeout}s")
            return [], ToolStatus.TIMEOUT
        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return [], ToolStatus.FAILED
