"""
Primary Agent Connector for FeedMe Integration

Provides integration between the Primary Agent and FeedMe knowledge retrieval system.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.db.session import get_db
from app.core.settings import settings

logger = logging.getLogger(__name__)


class PrimaryAgentConnector:
    """Connector for integrating FeedMe knowledge with the Primary Agent."""
    
    def __init__(self):
        """Initialize the connector with necessary configurations."""
        self.enabled = settings.feedme_enabled
        self.similarity_threshold = settings.feedme_similarity_threshold
        self.max_results = settings.feedme_max_retrieval_results
        
    async def search_feedme_examples(
        self,
        query: str,
        limit: Optional[int] = None,
        min_similarity: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search FeedMe examples for relevant Q&A pairs.
        
        Args:
            query: The search query
            limit: Maximum number of results to return
            min_similarity: Minimum similarity score threshold
            
        Returns:
            List of relevant FeedMe examples with metadata
        """
        if not self.enabled:
            logger.debug("FeedMe integration is disabled")
            return []
            
        try:
            # For now, return empty list as the actual implementation
            # would require database queries and embeddings
            logger.info(f"FeedMe search called with query: {query}")
            return []
            
        except Exception as e:
            logger.error(f"Error searching FeedMe examples: {e}")
            return []
            
    async def get_example_context(
        self,
        example_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get full context for a specific FeedMe example.
        
        Args:
            example_id: The ID of the example to retrieve
            
        Returns:
            Full example data with context or None if not found
        """
        if not self.enabled:
            return None
            
        try:
            # Placeholder implementation
            logger.info(f"Getting context for example ID: {example_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting example context: {e}")
            return None
            
    def format_feedme_results(
        self,
        examples: List[Dict[str, Any]]
    ) -> str:
        """
        Format FeedMe examples for inclusion in agent responses.
        
        Args:
            examples: List of FeedMe examples
            
        Returns:
            Formatted string representation
        """
        if not examples:
            return ""
            
        formatted_parts = []
        for idx, example in enumerate(examples, 1):
            parts = [
                f"**Example {idx}:**",
                f"Question: {example.get('question_text', 'N/A')}",
                f"Answer: {example.get('answer_text', 'N/A')}",
                f"Confidence: {example.get('confidence_score', 0):.2f}",
                ""
            ]
            formatted_parts.extend(parts)
            
        return "\n".join(formatted_parts)

    async def retrieve_knowledge(
        self,
        query: Dict[str, Any],
        max_results: int = 5,
        track_performance: bool = False,
    ) -> List[Dict[str, Any]]:
        """Unified knowledge retrieval for Enhanced KB search.

        Currently returns FeedMe examples via Supabase vector search.
        """
        if not self.enabled:
            logger.debug("FeedMe integration disabled; returning empty results")
            return []

        try:
            from app.db.supabase_client import SupabaseClient
            from app.db.embedding_utils import get_embedding_model

            text = str(query.get("query_text") or query.get("query") or "").strip()
            if not text:
                return []

            # Build embedding
            emb_model = get_embedding_model()
            loop = asyncio.get_running_loop()
            query_vec = await loop.run_in_executor(None, emb_model.embed_query, text)

            # Search Supabase examples
            client = SupabaseClient()
            rows = await client.search_examples(
                query_embedding=query_vec,
                limit=max_results,
                similarity_threshold=getattr(self, "similarity_threshold", 0.7),
            )

            def _safe_float(val: Any) -> float:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return 0.0

            results: List[Dict[str, Any]] = []
            for r in rows:
                # Normalize fields defensively
                title = r.get("conversation_title") or r.get("title") or "Support Example"
                answer = r.get("answer_text") or ""
                question = r.get("question_text") or ""
                confidence = _safe_float(r.get("similarity", r.get("similarity_score", 0.0)))

                results.append(
                    {
                        "source": "feedme",
                        "title": title,
                        "content": f"Q: {question}\n\nA: {answer}",
                        "relevance_score": confidence,
                        "metadata": {
                            "conversation_id": r.get("conversation_id"),
                            "example_id": r.get("id"),
                            "issue_type": r.get("issue_type"),
                            "resolution_type": r.get("resolution_type"),
                            "tags": r.get("tags") or [],
                        },
                        "quality_indicators": {
                            "high_confidence": confidence >= 0.8,
                        },
                    }
                )

            return results

        except Exception as e:
            logger.error(f"retrieve_knowledge failed: {e}")
            return []