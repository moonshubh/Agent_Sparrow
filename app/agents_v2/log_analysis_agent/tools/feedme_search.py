"""
FeedMe Integration for Log Analysis

This module provides integration with FeedMe to search past conversations
for similar log issues and their resolutions.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.agents_v2.primary_agent.feedme_knowledge_tool import get_feedme_connector
from app.core.settings import settings
from ..schemas.log_schemas import ErrorPattern, LogMetadata
from .orchestrator import FeedMeConversation

logger = logging.getLogger(__name__)


class FeedMeLogSearch:
    """
    Search past conversations for similar log issues.

    This class integrates with FeedMe to find previously resolved issues
    that match current log error patterns.
    """

    def __init__(self):
        """Initialize FeedMe search"""
        self.max_results = 5
        self.min_confidence = 0.7
        self._connector = None

    def _get_connector(self):
        """Get or create FeedMe connector"""
        if self._connector is None:
            try:
                self._connector = get_feedme_connector()
            except Exception as e:
                logger.warning(f"Failed to initialize FeedMe connector: {e}")
        return self._connector

    def _build_search_query(
        self,
        patterns: List[ErrorPattern],
        metadata: LogMetadata
    ) -> Dict[str, Any]:
        """
        Build search query for FeedMe based on error patterns.

        Args:
            patterns: List of error patterns
            metadata: Log metadata

        Returns:
            Search query dictionary
        """
        # Extract error signatures from patterns
        error_signatures = []
        error_types = []

        for pattern in patterns[:5]:  # Top 5 patterns
            # Add pattern description as signature
            if pattern.description:
                error_signatures.append(pattern.description)

            # Add error category
            if pattern.category:
                error_types.append(pattern.category.name)

            # Add specific error messages from samples
            for entry in pattern.sample_entries[:2]:
                if entry.message and len(entry.message) > 20:
                    # Clean and add message
                    msg = entry.message.strip()[:150]
                    if msg not in error_signatures:
                        error_signatures.append(msg)

        # Build search parameters
        search_params = {
            "error_signatures": error_signatures[:5],  # Limit signatures
            "error_types": list(set(error_types)),  # Unique error types
            "version": metadata.mailbird_version,
            "os_type": "Windows" if metadata.os_version and "Windows" in metadata.os_version else "Other",
            "resolution_status": "resolved",  # Focus on resolved issues
            "max_results": self.max_results
        }

        # Add time range if available
        if metadata.session_start:
            # Look for issues in the last 90 days
            from datetime import timedelta
            search_params["date_from"] = (
                datetime.now() - timedelta(days=90)
            ).isoformat()

        return search_params

    async def find_similar_issues(
        self,
        patterns: List[ErrorPattern],
        metadata: LogMetadata,
        query_override: Optional[str] = None
    ) -> List[FeedMeConversation]:
        """
        Find conversations with similar error patterns.

        Args:
            patterns: List of error patterns
            metadata: Log metadata
            query_override: Optional query override

        Returns:
            List of relevant FeedMe conversations
        """
        try:
            # Check if FeedMe is enabled
            if not settings.feedme_enabled:
                logger.debug("FeedMe is disabled, skipping search")
                return []

            connector = self._get_connector()
            if not connector:
                logger.warning("FeedMe connector not available")
                return []

            # Build or use override query
            if query_override:
                # Parse override query into search params
                search_params = {
                    "query": query_override,
                    "resolution_status": "resolved",
                    "max_results": self.max_results
                }
            else:
                search_params = self._build_search_query(patterns, metadata)

            logger.info(
                f"Searching FeedMe for similar issues - "
                f"signatures: {len(search_params.get('error_signatures', []))}, "
                f"version: {search_params.get('version', 'any')}"
            )

            # Execute search
            raw_results = await self._search_feedme(connector, search_params)

            # Convert to FeedMeConversation objects
            conversations = self._parse_feedme_results(raw_results, patterns)

            # Filter by resolution status
            resolved_conversations = [
                conv for conv in conversations
                if conv.resolution_status == "resolved"
            ]

            logger.info(
                f"Found {len(resolved_conversations)} resolved conversations "
                f"out of {len(conversations)} total"
            )

            return resolved_conversations

        except Exception as e:
            logger.error(f"FeedMe search error: {e}", exc_info=True)
            return []

    async def _search_feedme(
        self,
        connector,
        search_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute FeedMe search with error handling.

        Args:
            connector: FeedMe connector instance
            search_params: Search parameters

        Returns:
            Raw search results
        """
        try:
            # Try to search conversations
            if hasattr(connector, 'search_conversations'):
                return await connector.search_conversations(search_params)
            elif hasattr(connector, 'search'):
                return await connector.search(search_params)
            else:
                # Fallback to basic search
                logger.warning("FeedMe connector missing search methods")
                return {"conversations": [], "total": 0}

        except AttributeError as e:
            logger.warning(f"FeedMe connector method not found: {e}")
            return {"conversations": [], "total": 0}
        except Exception as e:
            logger.error(f"FeedMe search execution error: {e}")
            return {"conversations": [], "total": 0}

    def _parse_feedme_results(
        self,
        raw_results: Dict[str, Any],
        patterns: List[ErrorPattern]
    ) -> List[FeedMeConversation]:
        """
        Parse FeedMe search results into conversation objects.

        Args:
            raw_results: Raw search results from FeedMe
            patterns: Error patterns for relevance scoring

        Returns:
            List of FeedMeConversation objects
        """
        conversations = []

        try:
            # Handle different result formats
            if isinstance(raw_results, dict):
                conv_list = raw_results.get("conversations", [])
            elif isinstance(raw_results, list):
                conv_list = raw_results
            else:
                logger.warning(f"Unexpected FeedMe result format: {type(raw_results)}")
                return []

            for conv_data in conv_list:
                try:
                    # Extract conversation details
                    conversation = self._create_conversation(conv_data, patterns)
                    if conversation:
                        conversations.append(conversation)

                except Exception as e:
                    logger.debug(f"Error parsing conversation: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error parsing FeedMe results: {e}")

        # Sort by confidence score
        conversations.sort(key=lambda c: c.confidence_score, reverse=True)

        return conversations

    def _create_conversation(
        self,
        conv_data: Dict[str, Any],
        patterns: List[ErrorPattern]
    ) -> Optional[FeedMeConversation]:
        """
        Create a FeedMeConversation object from raw data.

        Args:
            conv_data: Raw conversation data
            patterns: Error patterns for matching

        Returns:
            FeedMeConversation object or None
        """
        try:
            # Extract basic information
            conv_id = conv_data.get("id", str(datetime.now().timestamp()))
            title = conv_data.get("title", "Untitled Conversation")
            summary = conv_data.get("summary", "")
            resolution = conv_data.get("resolution", "")

            # Extract error patterns from conversation
            conv_patterns = conv_data.get("error_patterns", [])
            if not conv_patterns and "errors" in conv_data:
                conv_patterns = conv_data["errors"]
            if not conv_patterns and summary:
                # Try to extract patterns from summary
                conv_patterns = self._extract_patterns_from_text(summary)

            # Determine resolution status
            resolution_status = conv_data.get("resolution_status", "unknown")
            if not resolution_status or resolution_status == "unknown":
                # Infer from resolution text
                if resolution and len(resolution) > 20:
                    resolution_status = "resolved"
                else:
                    resolution_status = "unresolved"

            # Calculate confidence score
            confidence = self._calculate_confidence(
                conv_data,
                patterns,
                conv_patterns
            )

            # Parse timestamp
            created_at = self._parse_timestamp(conv_data.get("created_at"))

            return FeedMeConversation(
                conversation_id=conv_id,
                title=title,
                summary=summary,
                resolution=resolution,
                error_patterns=conv_patterns[:5],  # Limit patterns
                resolution_status=resolution_status,
                confidence_score=confidence,
                created_at=created_at
            )

        except Exception as e:
            logger.debug(f"Failed to create conversation object: {e}")
            return None

    def _extract_patterns_from_text(self, text: str) -> List[str]:
        """Extract error patterns from text content"""
        patterns = []

        # Look for common error indicators
        error_keywords = [
            "error", "failed", "exception", "timeout",
            "unable", "could not", "denied", "invalid"
        ]

        lines = text.split("\n")
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in error_keywords):
                # Clean and add as pattern
                pattern = line.strip()[:100]
                if pattern and pattern not in patterns:
                    patterns.append(pattern)

        return patterns[:3]  # Return top 3

    def _calculate_confidence(
        self,
        conv_data: Dict[str, Any],
        search_patterns: List[ErrorPattern],
        conv_patterns: List[str]
    ) -> float:
        """
        Calculate confidence score for conversation relevance.

        Args:
            conv_data: Conversation data
            search_patterns: Patterns we're searching for
            conv_patterns: Patterns found in conversation

        Returns:
            Confidence score between 0 and 1
        """
        score = 0.5  # Base score

        # Check pattern overlap
        if conv_patterns and search_patterns:
            for search_pattern in search_patterns[:3]:
                # Check description match with proper None checks
                if not search_pattern.description:
                    continue

                search_desc_lower = search_pattern.description.lower()
                for conv_pattern in conv_patterns:
                    # Ensure conv_pattern is a string before calling .lower()
                    conv_pattern_str = str(conv_pattern) if conv_pattern else ""
                    if conv_pattern_str:
                        conv_pattern_lower = conv_pattern_str.lower()
                        if (search_desc_lower in conv_pattern_lower or
                            conv_pattern_lower in search_desc_lower):
                            score += 0.15

                # Check category match
                if "category" in conv_data:
                    if (search_pattern.category and
                        search_pattern.category.name == conv_data["category"]):
                        score += 0.1

        # Boost for resolution
        if conv_data.get("resolution") and len(conv_data["resolution"]) > 50:
            score += 0.1

        # Boost for resolved status
        if conv_data.get("resolution_status") == "resolved":
            score += 0.1

        # Version match
        if "version" in conv_data:
            # Version matching logic would go here
            score += 0.05

        # Recency boost
        if "created_at" in conv_data:
            try:
                created = self._parse_timestamp(conv_data["created_at"])
                if created:
                    days_old = (datetime.now() - created).days
                    if days_old < 30:
                        score += 0.1
                    elif days_old < 60:
                        score += 0.05
            except:
                pass

        return min(score, 1.0)

    def _parse_timestamp(self, timestamp_str: Any) -> datetime:
        """Parse various timestamp formats"""
        if not timestamp_str:
            return datetime.now()

        if isinstance(timestamp_str, datetime):
            return timestamp_str

        if isinstance(timestamp_str, (int, float)):
            # Unix timestamp
            return datetime.fromtimestamp(timestamp_str)

        if isinstance(timestamp_str, str):
            # Try ISO format
            try:
                return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except:
                pass

            # Try other common formats
            from dateutil import parser
            try:
                return parser.parse(timestamp_str)
            except:
                pass

        return datetime.now()  # Default to now if parsing fails