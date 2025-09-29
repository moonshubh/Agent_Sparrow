"""
Knowledge Base Search Enhancement for Log Analysis

This module provides specialized KB search functionality optimized for
log error analysis and resolution.
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from app.agents_v2.primary_agent.feedme_knowledge_tool import (
    enhanced_mailbird_kb_search,
    get_feedme_connector
)
try:
    from ..schemas.log_schemas import ErrorPattern, ErrorCategory
except ImportError:
    try:
        from schemas.log_schemas import ErrorPattern, ErrorCategory
    except ImportError:
        from app.agents_v2.log_analysis_agent.schemas.log_schemas import ErrorPattern, ErrorCategory
from .orchestrator import KBArticle

logger = logging.getLogger(__name__)


class EnhancedKBSearch:
    """
    Knowledge Base search optimized for log analysis.

    Enhances standard KB search with log-specific query building,
    error pattern matching, and relevance ranking.
    """

    def __init__(self):
        """Initialize the enhanced KB search"""
        self.min_confidence = 0.7
        self.max_results = 10

    def build_error_query(self, error_patterns: List[ErrorPattern]) -> str:
        """
        Build an optimized search query from error patterns.

        Args:
            error_patterns: List of detected error patterns

        Returns:
            Optimized search query string
        """
        query_terms = []

        # Prioritize patterns by occurrences and confidence
        sorted_patterns = sorted(
            error_patterns,
            key=lambda p: (p.occurrences * p.confidence),
            reverse=True
        )[:5]  # Top 5 patterns

        for pattern in sorted_patterns:
            # Add error description
            if pattern.description:
                query_terms.append(pattern.description)

            # Add category-specific terms
            if pattern.category:
                category_terms = self._get_category_search_terms(pattern.category)
                query_terms.extend(category_terms)

            # Add specific error indicators
            if pattern.indicators:  # Guard against None
                for indicator in pattern.indicators[:2]:  # Top 2 indicators
                    if indicator and len(indicator) > 10:  # Skip short generic terms
                        query_terms.append(f'"{indicator}"')

        # Deduplicate and join
        seen = set()
        unique_terms = []
        for term in query_terms:
            term_lower = term.lower().strip()
            if term_lower not in seen and term_lower:
                seen.add(term_lower)
                unique_terms.append(term)

        # Build final query
        query = " OR ".join(unique_terms[:5])  # Limit to 5 terms
        return query if query else "Mailbird error troubleshooting"

    def _get_category_search_terms(self, category: ErrorCategory) -> List[str]:
        """
        Get search terms for specific error categories.

        Args:
            category: Error category enum

        Returns:
            List of relevant search terms
        """
        category_terms = {
            ErrorCategory.AUTHENTICATION: [
                "authentication failed",
                "login error",
                "password incorrect",
                "OAuth token"
            ],
            ErrorCategory.SYNCHRONIZATION: [
                "sync error",
                "synchronization failed",
                "IMAP sync",
                "calendar sync"
            ],
            ErrorCategory.NETWORK: [
                "connection timeout",
                "network error",
                "proxy configuration",
                "SSL certificate"
            ],
            ErrorCategory.DATABASE: [
                "database error",
                "corruption",
                "SQLite error",
                "database locked"
            ],
            ErrorCategory.CONFIGURATION: [
                "configuration error",
                "settings invalid",
                "account setup"
            ],
            ErrorCategory.PERFORMANCE: [
                "performance issue",
                "slow response",
                "high memory usage",
                "CPU usage"
            ],
            ErrorCategory.UI_INTERACTION: [
                "UI freeze",
                "interface error",
                "rendering issue",
                "display problem"
            ],
            ErrorCategory.FILE_SYSTEM: [
                "file access error",
                "permission denied",
                "disk full",
                "file not found"
            ],
            ErrorCategory.MEMORY: [
                "out of memory",
                "memory leak",
                "allocation failed"
            ],
            ErrorCategory.LICENSING: [
                "license expired",
                "activation failed",
                "license key invalid"
            ]
        }

        return category_terms.get(category, ["Mailbird error"])

    async def search_for_log_errors(
        self,
        error_patterns: List[ErrorPattern],
        query_override: Optional[str] = None
    ) -> List[KBArticle]:
        """
        Search KB for error-specific articles.

        Args:
            error_patterns: List of detected error patterns
            query_override: Optional query to use instead of building one

        Returns:
            List of relevant KB articles
        """
        try:
            # Use override query or build from patterns
            if query_override:
                query = query_override
            else:
                query = self.build_error_query(error_patterns)

            logger.info(f"KB search for log errors: '{query[:100]}...'")

            # Prepare context for enhanced search
            context = {
                "source": "log_analysis",
                "error_types": [
                    p.category.name if p.category else "UNKNOWN"
                    for p in error_patterns[:3]
                ],
                "error_count": sum(p.occurrences for p in error_patterns),
                "priority": "high" if any(p.occurrences > 10 for p in error_patterns) else "normal"
            }

            # Use existing enhanced KB search
            raw_results = enhanced_mailbird_kb_search(
                query=query,
                context=context,
                search_sources=["knowledge_base", "feedme"],
                max_results=self.max_results,
                min_confidence=self.min_confidence
            )

            # Parse and convert results
            articles = self._parse_search_results(raw_results, error_patterns)

            # Rank by relevance to specific errors
            ranked_articles = self.rank_by_relevance(articles, error_patterns)

            logger.info(f"Found {len(ranked_articles)} relevant KB articles")
            return ranked_articles[:self.max_results]

        except Exception as e:
            logger.error(f"KB search error: {e}", exc_info=True)
            return []

    def _parse_search_results(
        self,
        raw_results: str,
        error_patterns: List[ErrorPattern]
    ) -> List[KBArticle]:
        """
        Parse raw search results into KBArticle objects.

        Args:
            raw_results: Raw search results string
            error_patterns: Error patterns for matching

        Returns:
            List of KBArticle objects
        """
        articles = []

        try:
            # Parse the formatted results string
            # The enhanced_mailbird_kb_search returns formatted text
            sections = raw_results.split("\n\n")

            for i, section in enumerate(sections):
                if not section.strip():
                    continue

                # Extract article information from formatted text
                lines = section.strip().split("\n")
                if not lines:
                    continue

                # Create article with parsed information
                article = KBArticle(
                    article_id=f"kb_{i}",
                    title=self._extract_title(lines),
                    content="\n".join(lines),
                    url=self._extract_url(lines),
                    relevance_score=self._calculate_initial_relevance(section, error_patterns),
                    categories=self._extract_categories(section),
                    error_patterns_matched=self._match_patterns(section, error_patterns)
                )

                articles.append(article)

        except Exception as e:
            logger.error(f"Error parsing KB search results: {e}")

        return articles

    def _extract_title(self, lines: List[str]) -> str:
        """Extract title from result lines"""
        for line in lines:
            if line.strip():
                # Remove markdown formatting if present
                title = line.strip()
                if title.startswith("**") and title.endswith("**"):
                    title = title[2:-2]
                elif title.startswith("### "):
                    title = title[4:]
                return title
        return "Untitled Article"

    def _extract_url(self, lines: List[str]) -> str:
        """Extract URL from result lines"""
        for line in lines:
            if "http" in line.lower():
                # Extract URL from line
                import re
                url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]*'
                match = re.search(url_pattern, line)
                if match:
                    return match.group(0)
        return ""

    def _extract_categories(self, content: str) -> List[str]:
        """Extract categories from content"""
        categories = []

        # Look for category indicators
        category_keywords = {
            "authentication": ["login", "password", "oauth", "credentials"],
            "sync": ["synchronization", "sync", "imap", "exchange"],
            "network": ["connection", "network", "proxy", "ssl"],
            "database": ["database", "sqlite", "corruption", "data"],
            "configuration": ["settings", "config", "setup", "preferences"],
            "performance": ["slow", "performance", "memory", "cpu"]
        }

        content_lower = content.lower()
        for category, keywords in category_keywords.items():
            if any(keyword in content_lower for keyword in keywords):
                categories.append(category)

        return categories[:3]  # Limit to 3 categories

    def _calculate_initial_relevance(
        self,
        content: str,
        error_patterns: List[ErrorPattern]
    ) -> float:
        """
        Calculate initial relevance score.

        Args:
            content: Article content
            error_patterns: Error patterns to match

        Returns:
            Relevance score between 0 and 1
        """
        score = 0.0
        content_lower = content.lower()

        # Check for pattern descriptions
        for pattern in error_patterns:
            # Safe check for pattern description
            if pattern.description and pattern.description.lower() in content_lower:
                score += 0.3

            # Check for indicators with proper None/type handling
            if pattern.indicators:
                for indicator in pattern.indicators:
                    # Ensure indicator is a string before calling .lower()
                    if indicator and isinstance(indicator, str) and indicator.lower() in content_lower:
                        score += 0.1

            # Category match
            if pattern.category and pattern.category.name.lower() in content_lower:
                score += 0.2

        # Normalize score
        return min(score, 1.0)

    def _match_patterns(
        self,
        content: str,
        error_patterns: List[ErrorPattern]
    ) -> List[str]:
        """
        Find which error patterns match the content.

        Args:
            content: Article content
            error_patterns: Error patterns to check

        Returns:
            List of matched pattern IDs
        """
        matched = []
        content_lower = content.lower()

        for pattern in error_patterns:
            # Check if pattern elements appear in content with proper None checks
            description_match = (pattern.description and
                                pattern.description.lower() in content_lower)

            # Safe indicator checking
            indicator_match = False
            if pattern.indicators:
                # Take up to 3 indicators, filter None values
                indicators_to_check = [ind for ind in pattern.indicators[:3]
                                      if ind and isinstance(ind, str)]
                indicator_match = any(ind.lower() in content_lower
                                    for ind in indicators_to_check)

            if description_match or indicator_match:
                matched.append(pattern.pattern_id)

        return matched

    def rank_by_relevance(
        self,
        articles: List[KBArticle],
        error_patterns: List[ErrorPattern]
    ) -> List[KBArticle]:
        """
        Rank articles by relevance to specific error patterns.

        Args:
            articles: List of KB articles
            error_patterns: Error patterns for ranking

        Returns:
            Ranked list of articles
        """
        if not articles:
            return []

        # Calculate detailed relevance scores
        for article in articles:
            # Base score from initial calculation
            score = article.relevance_score

            # Boost for pattern matches
            pattern_match_score = len(article.error_patterns_matched) * 0.15
            score += min(pattern_match_score, 0.3)

            # Boost for category matches
            if error_patterns:
                top_categories = {
                    p.category.name.lower() if p.category else ""
                    for p in error_patterns[:3]
                }
                category_matches = sum(
                    1 for cat in article.categories
                    if cat in top_categories
                )
                score += category_matches * 0.1

            # Boost for title relevance
            title_lower = article.title.lower() if article.title else ""
            for pattern in error_patterns[:2]:
                if pattern.description:
                    # Split description into terms safely
                    description_terms = pattern.description.lower().split()
                    if any(term in title_lower for term in description_terms):
                        score += 0.2
                        break

            # Update score (cap at 1.0)
            article.relevance_score = min(score, 1.0)

        # Sort by relevance score
        ranked = sorted(articles, key=lambda a: a.relevance_score, reverse=True)

        # Log top results
        if ranked:
            logger.debug(
                f"Top KB results: {ranked[0].title} (score: {ranked[0].relevance_score:.2f})"
            )

        return ranked