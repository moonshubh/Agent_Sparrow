"""
FeedMe v2.0 Primary Agent Connector

Connector for integrating FeedMe knowledge source with the Primary Agent system.
Provides formatted knowledge retrieval that fits into the Primary Agent's workflow.
"""

import logging
import time
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from .knowledge_source import FeedMeKnowledgeSource

logger = logging.getLogger(__name__)


class PrimaryAgentConnector:
    """
    Connector for integrating FeedMe with Primary Agent system
    
    Provides:
    - Knowledge retrieval formatted for Primary Agent
    - Context enrichment for better search results
    - Response formatting and ranking
    - Performance tracking and analytics
    """
    
    def __init__(self, knowledge_source: Optional[FeedMeKnowledgeSource] = None):
        """
        Initialize Primary Agent connector
        
        Args:
            knowledge_source: Optional knowledge source instance (for testing)
        """
        self.feedme_knowledge_source = knowledge_source or FeedMeKnowledgeSource()
        
        # Performance tracking
        self._last_retrieval_performance = {}
        self._retrieval_stats = {
            'total_retrievals': 0,
            'successful_retrievals': 0,
            'avg_retrieval_time_ms': 0,
            'avg_results_per_query': 0
        }
        
        logger.info("Initialized FeedMe Primary Agent connector")
    
    async def retrieve_knowledge(
        self,
        query: Dict[str, Any],
        max_results: int = 3,
        enable_deduplication: bool = True,
        track_performance: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieve knowledge from FeedMe for Primary Agent
        
        Args:
            query: Query information from Primary Agent
            max_results: Maximum number of results to return
            enable_deduplication: Whether to deduplicate similar results
            track_performance: Whether to track detailed performance metrics
            
        Returns:
            List of formatted knowledge results for Primary Agent
        """
        start_time = time.time() if track_performance else None
        
        try:
            # Extract query text
            query_text = self._extract_query_text(query)
            if not query_text:
                logger.warning("No query text found in Primary Agent query")
                return []
            
            # Enrich context for FeedMe search
            enriched_context = self._enrich_context(query)
            
            # Perform knowledge search
            raw_results = await self.feedme_knowledge_source.search(
                query=query_text,
                context=enriched_context,
                limit=max_results * 2 if enable_deduplication else max_results
            )
            
            # Process and format results
            formatted_results = self._format_results_for_primary_agent(raw_results)
            
            # Apply deduplication if enabled
            if enable_deduplication:
                formatted_results = self._deduplicate_results(formatted_results)
            
            # Limit final results
            formatted_results = formatted_results[:max_results]
            
            # Track performance if requested
            if track_performance and start_time:
                self._track_retrieval_performance(
                    query_text=query_text,
                    raw_results_count=len(raw_results),
                    final_results_count=len(formatted_results),
                    retrieval_time_ms=int((time.time() - start_time) * 1000)
                )
            
            # Update statistics
            self._update_retrieval_stats(len(formatted_results), start_time)
            
            logger.debug(f"Retrieved {len(formatted_results)} knowledge results for Primary Agent")
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error retrieving knowledge for Primary Agent: {e}")
            return []
    
    async def retrieve_with_reasoning_context(
        self,
        query: str,
        reasoning_context: Dict[str, Any],
        max_results: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Retrieve knowledge with Primary Agent reasoning context
        
        Args:
            query: Simple query text
            reasoning_context: Context from Primary Agent reasoning system
            max_results: Maximum results to return
            
        Returns:
            Formatted knowledge results
        """
        # Build enhanced query object
        enhanced_query = {
            'query_text': query,
            'reasoning_context': reasoning_context
        }
        
        # Merge reasoning context into detection context
        if 'problem_category' in reasoning_context:
            enhanced_query['detected_category'] = reasoning_context['problem_category']
        
        if 'customer_technical_level' in reasoning_context:
            enhanced_query['customer_context'] = enhanced_query.get('customer_context', {})
            enhanced_query['customer_context']['technical_level'] = reasoning_context['customer_technical_level']
        
        # Retrieve with enhanced context
        return await self.retrieve_knowledge(
            query=enhanced_query,
            max_results=max_results,
            track_performance=True
        )
    
    def _extract_query_text(self, query: Dict[str, Any]) -> str:
        """
        Extract query text from Primary Agent query structure
        
        Args:
            query: Query object from Primary Agent
            
        Returns:
            Extracted query text
        """
        # Handle different query formats
        if isinstance(query, str):
            return query
        
        if isinstance(query, dict):
            # Try different possible field names
            for field in ['query_text', 'query', 'user_query', 'message', 'content']:
                if field in query and query[field]:
                    return str(query[field])
            
            # Try to extract from conversation history
            if 'conversation_history' in query:
                history = query['conversation_history']
                if history and isinstance(history, list):
                    # Get the last user message
                    for message in reversed(history):
                        if isinstance(message, dict) and message.get('role') == 'user':
                            return str(message.get('content', ''))
        
        logger.warning(f"Could not extract query text from: {type(query)}")
        return ""
    
    def _enrich_context(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich context for FeedMe search based on Primary Agent query
        
        Args:
            query: Query object from Primary Agent
            
        Returns:
            Enriched context dictionary
        """
        context = {}
        
        # Map Primary Agent fields to FeedMe context
        field_mappings = {
            'detected_intent': 'detected_category',
            'emotional_state': 'customer_emotion',
            'detected_category': 'detected_category'
        }
        
        for pa_field, feedme_field in field_mappings.items():
            if pa_field in query:
                context[feedme_field] = query[pa_field]
        
        # Extract customer context
        if 'customer_context' in query:
            customer_ctx = query['customer_context']
            if isinstance(customer_ctx, dict):
                # Map platform information
                if 'platform' in customer_ctx:
                    context['user_platform'] = customer_ctx['platform']
                
                # Map technical level
                if 'technical_level' in customer_ctx:
                    context['customer_technical_level'] = customer_ctx['technical_level']
                
                # Map urgency/priority
                if 'issue_duration' in customer_ctx:
                    duration = customer_ctx['issue_duration']
                    if duration in ['hours', 'days']:
                        context['urgency'] = 'high'
                    elif duration in ['weeks', 'months']:
                        context['urgency'] = 'medium'
                    else:
                        context['urgency'] = 'low'
        
        # Add reasoning context if available
        if 'reasoning_context' in query:
            reasoning_ctx = query['reasoning_context']
            if isinstance(reasoning_ctx, dict):
                context.update(reasoning_ctx)
        
        # Set confidence threshold based on emotional state
        emotion = context.get('customer_emotion', '').lower()
        if emotion in ['frustrated', 'angry', 'urgent']:
            context['min_confidence'] = 0.6  # Lower threshold for urgent cases
        elif emotion in ['confused', 'anxious']:
            context['min_confidence'] = 0.75  # Higher threshold for confused users
        else:
            context['min_confidence'] = 0.7  # Default threshold
        
        return context
    
    def _format_results_for_primary_agent(
        self,
        raw_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Format FeedMe results for Primary Agent consumption
        
        Args:
            raw_results: Raw results from FeedMe search
            
        Returns:
            Formatted results for Primary Agent
        """
        formatted_results = []
        
        for result in raw_results:
            formatted_result = {
                # Core content
                'source': 'feedme',
                'title': result.get('question_text', ''),
                'content': result.get('answer_text', ''),
                'relevance_score': result.get('combined_score', 0.0),
                'confidence': result.get('confidence_score', 0.0),
                
                # Metadata for Primary Agent
                'metadata': {
                    'feedme_id': result.get('id'),
                    'issue_type': result.get('issue_type', 'general'),
                    'tags': result.get('tags', []),
                    'usage_count': result.get('usage_count', 0),
                    'last_used_at': result.get('last_used_at'),
                    'search_scores': {
                        'vector_score': result.get('vector_score', 0.0),
                        'text_score': result.get('text_score', 0.0),
                        'combined_score': result.get('combined_score', 0.0)
                    },
                    'search_type': result.get('search_type', 'hybrid'),
                    'primary_match': result.get('primary_match', 'semantic')
                },
                
                # Additional context for Primary Agent reasoning
                'context': {
                    'question_context': result.get('context_before', ''),
                    'resolution_context': result.get('context_after', ''),
                    'is_tested_solution': result.get('usage_count', 0) > 5,
                    'popularity_score': min(1.0, result.get('usage_count', 0) / 20.0)
                },
                
                # Quality indicators
                'quality_indicators': {
                    'high_confidence': result.get('confidence_score', 0.0) >= 0.85,
                    'frequently_used': result.get('usage_count', 0) >= 10,
                    'recent_usage': self._is_recently_used(result.get('last_used_at')),
                    'semantic_match': result.get('primary_match') == 'semantic',
                    'exact_match': result.get('primary_match') == 'textual'
                }
            }
            
            formatted_results.append(formatted_result)
        
        # Sort by relevance score
        formatted_results.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return formatted_results
    
    def _is_recently_used(self, last_used_at: Optional[str]) -> bool:
        """
        Check if an example was used recently
        
        Args:
            last_used_at: Last usage timestamp string
            
        Returns:
            True if used within last 30 days
        """
        if not last_used_at:
            return False
        
        try:
            from datetime import datetime, timedelta
            
            # Parse timestamp (assuming ISO format)
            last_used = datetime.fromisoformat(last_used_at.replace('Z', '+00:00'))
            cutoff = datetime.now().replace(tzinfo=last_used.tzinfo) - timedelta(days=30)
            
            return last_used >= cutoff
            
        except Exception:
            return False
    
    def _deduplicate_results(
        self,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Remove similar results to avoid redundancy
        
        Args:
            results: Results to deduplicate
            
        Returns:
            Deduplicated results
        """
        if len(results) <= 1:
            return results
        
        deduplicated = []
        seen_titles = set()
        
        for result in results:
            title = result.get('title', '').lower().strip()
            
            # Simple deduplication based on title similarity
            # In production, this could use more sophisticated similarity measures
            is_duplicate = False
            for seen_title in seen_titles:
                if self._calculate_title_similarity(title, seen_title) > 0.8:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                deduplicated.append(result)
                seen_titles.add(title)
        
        return deduplicated
    
    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """
        Calculate similarity between two titles
        
        Args:
            title1: First title
            title2: Second title
            
        Returns:
            Similarity score between 0 and 1
        """
        # Simple word-based similarity
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _track_retrieval_performance(
        self,
        query_text: str,
        raw_results_count: int,
        final_results_count: int,
        retrieval_time_ms: int
    ):
        """
        Track detailed retrieval performance
        
        Args:
            query_text: Original query text
            raw_results_count: Number of raw results from FeedMe
            final_results_count: Number of final formatted results
            retrieval_time_ms: Total retrieval time in milliseconds
        """
        self._last_retrieval_performance = {
            'query': query_text,
            'search_time_ms': retrieval_time_ms,
            'total_results': raw_results_count,
            'filtered_results': final_results_count,
            'filtering_efficiency': final_results_count / max(1, raw_results_count),
            'timestamp': datetime.now().isoformat()
        }
    
    def _update_retrieval_stats(self, result_count: int, start_time: Optional[float]):
        """
        Update retrieval statistics
        
        Args:
            result_count: Number of results returned
            start_time: Start time for timing calculation
        """
        self._retrieval_stats['total_retrievals'] += 1
        
        if result_count > 0:
            self._retrieval_stats['successful_retrievals'] += 1
        
        # Update rolling averages
        total = self._retrieval_stats['total_retrievals']
        
        # Average results per query
        prev_avg_results = self._retrieval_stats['avg_results_per_query']
        self._retrieval_stats['avg_results_per_query'] = (
            (prev_avg_results * (total - 1) + result_count) / total
        )
        
        # Average retrieval time (if timing available)
        if start_time:
            retrieval_time_ms = int((time.time() - start_time) * 1000)
            prev_avg_time = self._retrieval_stats['avg_retrieval_time_ms']
            self._retrieval_stats['avg_retrieval_time_ms'] = (
                (prev_avg_time * (total - 1) + retrieval_time_ms) / total
            )
    
    def get_retrieval_statistics(self) -> Dict[str, Any]:
        """
        Get retrieval performance statistics
        
        Returns:
            Dictionary of retrieval statistics
        """
        return {
            'connector_stats': self._retrieval_stats.copy(),
            'knowledge_source_stats': self.feedme_knowledge_source.get_search_statistics(),
            'last_performance': self._last_retrieval_performance.copy()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check of connector and dependencies
        
        Returns:
            Health status information
        """
        status = {
            'status': 'healthy',
            'connector': 'healthy',
            'components': {},
            'statistics': self.get_retrieval_statistics()
        }
        
        try:
            # Check knowledge source health
            knowledge_health = await self.feedme_knowledge_source.health_check()
            status['components']['knowledge_source'] = knowledge_health
            
            if knowledge_health['status'] != 'healthy':
                status['status'] = knowledge_health['status']
                
        except Exception as e:
            status['components']['knowledge_source'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            status['status'] = 'unhealthy'
        
        return status