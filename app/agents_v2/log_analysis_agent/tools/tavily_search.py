"""
Tavily Web Search Integration for Log Analysis

This module provides web search capabilities optimized for finding
solutions to log-related issues.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

from app.tools.user_research_tools import UserTavilySearchTool
from app.core.user_context import get_current_user_context
try:
    from ..schemas.log_schemas import ErrorPattern, LogMetadata, ErrorCategory
except ModuleNotFoundError:
    try:
        from schemas.log_schemas import ErrorPattern, LogMetadata, ErrorCategory
    except ModuleNotFoundError:
        from app.agents_v2.log_analysis_agent.schemas.log_schemas import ErrorPattern, LogMetadata, ErrorCategory
from .orchestrator import WebResource

logger = logging.getLogger(__name__)


class TavilyLogSearch:
    """
    Web search for latest solutions and updates.

    This class uses Tavily API to search for solutions to identified
    log issues, focusing on official documentation and community resources.
    """

    def __init__(self):
        """Initialize Tavily search"""
        self.max_results = 5
        self.search_depth = "advanced"
        self.preferred_domains = [
            "getmailbird.com",
            "support.microsoft.com",
            "stackoverflow.com",
            "github.com",
            "superuser.com",
            "answers.microsoft.com",
            "reddit.com"
        ]
        self._search_tool = None

    def _get_search_tool(self):
        """Get or create Tavily search tool"""
        if self._search_tool is None:
            try:
                self._search_tool = UserTavilySearchTool()
            except Exception as e:
                logger.warning(f"Failed to initialize Tavily search tool: {e}")
        return self._search_tool

    def _build_search_query(
        self,
        patterns: List[ErrorPattern],
        metadata: LogMetadata
    ) -> str:
        """
        Build targeted search query based on patterns.

        Args:
            patterns: List of error patterns
            metadata: Log metadata

        Returns:
            Optimized search query string
        """
        query_parts = []

        # Add Mailbird and version
        query_parts.append(f"Mailbird {metadata.mailbird_version}")

        # Add top error pattern description
        if patterns:
            # Get the most significant pattern
            top_pattern = max(
                patterns,
                key=lambda p: p.occurrences * p.confidence
            )

            # Clean up the description for search
            description = top_pattern.description or ""
            if description:
                # Remove technical jargon
                description = description.replace("System.", "")
                description = description.replace("Exception", "error")

            if description:
                query_parts.append(description)

            # Add category-specific terms
            if top_pattern.category:
                category_terms = self._get_category_search_terms(top_pattern.category)
                if category_terms:
                    query_parts.append(category_terms[0])

        # Add solution-focused terms
        query_parts.extend(["solution", "fix", "resolve"])

        # Add OS information if Windows
        if "Windows" in metadata.os_version:
            query_parts.append("Windows")

        # Build final query
        query = " ".join(query_parts[:6])  # Limit query length
        return query

    def _get_category_search_terms(self, category) -> List[str]:
        """Get search terms for specific error category"""

        category_terms = {
            ErrorCategory.AUTHENTICATION: ["authentication error", "login failed"],
            ErrorCategory.SYNCHRONIZATION: ["sync error", "synchronization failed"],
            ErrorCategory.NETWORK: ["connection error", "network timeout"],
            ErrorCategory.DATABASE: ["database error", "corruption"],
            ErrorCategory.CONFIGURATION: ["configuration error", "settings"],
            ErrorCategory.PERFORMANCE: ["slow performance", "high memory"],
            ErrorCategory.UI_INTERACTION: ["UI freeze", "interface error"],
            ErrorCategory.FILE_SYSTEM: ["file access error", "permission denied"],
            ErrorCategory.MEMORY: ["out of memory", "memory leak"],
            ErrorCategory.LICENSING: ["license error", "activation failed"]
        }

        return category_terms.get(category, [])

    async def search_web_solutions(
        self,
        patterns: List[ErrorPattern],
        metadata: LogMetadata,
        query_override: Optional[str] = None
    ) -> List[WebResource]:
        """
        Search web for solutions to identified issues.

        Args:
            patterns: List of error patterns
            metadata: Log metadata
            query_override: Optional query override

        Returns:
            List of relevant web resources
        """
        try:
            search_tool = self._get_search_tool()
            if not search_tool:
                logger.warning("Tavily search tool not available")
                return []

            # Build or use override query
            if query_override:
                query = query_override
            else:
                query = self._build_search_query(patterns, metadata)

            logger.info(f"Searching web for solutions: '{query[:100]}...'")

            # Execute search
            try:
                results = await search_tool.search(
                    query=query,
                    max_results=self.max_results * 2  # Get extra for filtering
                )
            except Exception as e:
                logger.error(f"Tavily search execution error: {e}")
                return []

            # Parse and filter results
            resources = self._parse_search_results(results, patterns)

            # Filter by relevance
            filtered_resources = self.filter_relevant_results(
                resources,
                patterns,
                metadata
            )

            logger.info(f"Found {len(filtered_resources)} relevant web resources")
            return filtered_resources[:self.max_results]

        except Exception as e:
            logger.error(f"Web search error: {e}", exc_info=True)
            return []

    def _parse_search_results(
        self,
        raw_results: Dict[str, Any],
        patterns: List[ErrorPattern]
    ) -> List[WebResource]:
        """
        Parse Tavily search results into WebResource objects.

        Args:
            raw_results: Raw search results from Tavily
            patterns: Error patterns for relevance scoring

        Returns:
            List of WebResource objects
        """
        resources = []

        try:
            # Handle different result formats
            urls = []

            if isinstance(raw_results, dict):
                # Check for URLs in results
                if "urls" in raw_results:
                    urls = raw_results["urls"]
                elif "results" in raw_results:
                    # Full results format
                    for result in raw_results["results"]:
                        resource = self._create_resource_from_result(
                            result,
                            patterns
                        )
                        if resource:
                            resources.append(resource)
                    return resources
            elif isinstance(raw_results, list):
                urls = raw_results

            # Process URL-only results
            for i, url in enumerate(urls):
                if isinstance(url, str):
                    resource = WebResource(
                        url=url,
                        title=self._extract_title_from_url(url),
                        snippet="",
                        relevance_score=self._calculate_url_relevance(url, patterns),
                        source_domain=urlparse(url).netloc
                    )
                    resources.append(resource)

        except Exception as e:
            logger.error(f"Error parsing web search results: {e}")

        return resources

    def _create_resource_from_result(
        self,
        result: Dict[str, Any],
        patterns: List[ErrorPattern]
    ) -> Optional[WebResource]:
        """Create WebResource from full result data"""
        try:
            url = result.get("url", "")
            if not url:
                return None

            # Safe extraction with proper None handling
            snippet = result.get("snippet") or result.get("content") or ""
            snippet = snippet[:500] if snippet else ""

            # Ensure title is never None
            title = result.get("title") or self._extract_title_from_url(url)

            return WebResource(
                url=url,
                title=title,
                snippet=snippet,
                relevance_score=self._calculate_relevance(result, patterns),
                source_domain=urlparse(url).netloc,
                published_date=self._parse_date(result.get("published_date"))
            )
        except Exception as e:
            logger.debug(f"Failed to create resource: {e}")
            return None

    def _extract_title_from_url(self, url: str) -> str:
        """Extract a title from URL path"""
        try:
            parsed = urlparse(url)
            path = parsed.path.strip("/")
            if path:
                # Get last part of path and clean it
                title = path.split("/")[-1]
                title = title.replace("-", " ").replace("_", " ")
                title = title.split(".")[0]  # Remove extension
                return title.title()
            return parsed.netloc
        except:
            return "Web Resource"

    def _calculate_url_relevance(
        self,
        url: str,
        patterns: List[ErrorPattern]
    ) -> float:
        """Calculate relevance based on URL alone"""
        score = 0.3  # Base score

        # Check domain preference
        domain = urlparse(url).netloc.lower()
        for preferred in self.preferred_domains:
            if preferred in domain:
                score += 0.3
                break

        # Check for error-related terms in URL
        url_lower = url.lower()
        error_terms = ["error", "fix", "solution", "resolve", "troubleshoot"]
        for term in error_terms:
            if term in url_lower:
                score += 0.1

        # Check for Mailbird in URL
        if "mailbird" in url_lower:
            score += 0.2

        return min(score, 1.0)

    def _calculate_relevance(
        self,
        result: Dict[str, Any],
        patterns: List[ErrorPattern]
    ) -> float:
        """
        Calculate relevance score for a search result.

        Args:
            result: Search result data
            patterns: Error patterns for matching

        Returns:
            Relevance score between 0 and 1
        """
        score = 0.3  # Base score

        # Get content for analysis with safe string handling
        title = result.get("title") or ""
        snippet = result.get("snippet") or ""
        full_content = result.get("content") or ""

        content = f"{title} {snippet} {full_content}".lower()

        # Check for pattern matches
        for pattern in patterns[:3]:
            if pattern.description and pattern.description.lower() in content:
                score += 0.2

            # Check for category keywords
            if pattern.category and pattern.category.name:
                if pattern.category.name.lower() in content:
                    score += 0.1

        # Domain bonus
        url = result.get("url", "")
        domain = urlparse(url).netloc.lower()

        if "mailbird" in domain:
            score += 0.3
        elif "microsoft" in domain:
            score += 0.2
        elif any(d in domain for d in ["stackoverflow", "github", "reddit"]):
            score += 0.15

        # Recency bonus
        if "published_date" in result:
            published = self._parse_date(result["published_date"])
            if published:
                days_old = (datetime.now() - published).days
                if days_old < 30:
                    score += 0.1
                elif days_old < 90:
                    score += 0.05

        return min(score, 1.0)

    def _parse_date(self, date_str: Any) -> Optional[datetime]:
        """Parse various date formats"""
        if not date_str:
            return None

        if isinstance(date_str, datetime):
            return date_str

        if isinstance(date_str, str):
            try:
                # Try ISO format
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except:
                pass

            # Try other formats
            from dateutil import parser
            try:
                return parser.parse(date_str)
            except:
                pass

        return None

    def filter_relevant_results(
        self,
        resources: List[WebResource],
        patterns: List[ErrorPattern],
        metadata: LogMetadata
    ) -> List[WebResource]:
        """
        Filter web resources for relevance.

        Args:
            resources: List of web resources
            patterns: Error patterns
            metadata: Log metadata

        Returns:
            Filtered list of relevant resources
        """
        if not resources:
            return []

        # Apply additional filtering
        filtered = []

        for resource in resources:
            # Skip if relevance too low
            if resource.relevance_score < 0.3:
                continue

            # Boost official Mailbird resources
            if "mailbird" in resource.source_domain.lower():
                resource.relevance_score = min(
                    resource.relevance_score + 0.2,
                    1.0
                )

            # Check for spam/unrelated content
            spam_indicators = [
                "download", "crack", "serial", "keygen",
                "torrent", "free trial", "discount"
            ]

            if any(
                indicator in resource.title.lower() or
                indicator in resource.snippet.lower()
                for indicator in spam_indicators
            ):
                continue  # Skip spam

            filtered.append(resource)

        # Sort by relevance
        filtered.sort(key=lambda r: r.relevance_score, reverse=True)

        # Ensure diversity in domains
        seen_domains = set()
        diverse_results = []

        for resource in filtered:
            domain = resource.source_domain
            # Allow multiple from preferred domains
            if domain in self.preferred_domains[:3] or domain not in seen_domains:
                diverse_results.append(resource)
                seen_domains.add(domain)
                if len(diverse_results) >= self.max_results:
                    break

        return diverse_results
