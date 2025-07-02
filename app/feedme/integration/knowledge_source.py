"""
FeedMe v2.0 Knowledge Source Integration

Provides knowledge retrieval capabilities for the Primary Agent system
using FeedMe's hybrid search engine and Q&A repository.
"""

import logging
import time
import asyncio
from typing import List, Dict, Any, Optional
import numpy as np
from sentence_transformers import SentenceTransformer

from app.feedme.search.hybrid_search_engine import HybridSearchEngine
from app.feedme.repositories.optimized_repository import OptimizedFeedMeRepository
from app.core.settings import settings

logger = logging.getLogger(__name__)


class FeedMeKnowledgeSource:
    """
    Knowledge source integration for FeedMe Q&A repository
    
    Provides search capabilities for the Primary Agent system with:
    - Hybrid semantic and text search
    - Context-aware filtering
    - Usage tracking and analytics
    - Performance optimization
    """
    
    def __init__(self, repository: Optional[OptimizedFeedMeRepository] = None):
        """
        Initialize FeedMe knowledge source
        
        Args:
            repository: Optional repository instance (for testing)
        """
        self.repository = repository or OptimizedFeedMeRepository()
        self.search_engine = HybridSearchEngine()
        
        # Initialize embedding model for query encoding
        self.embedding_model = None
        self._embedding_model_name = getattr(settings, 'FEEDME_EMBEDDING_MODEL', 'all-MiniLM-L12-v2')
        
        # Performance tracking
        self._search_stats = {
            'total_searches': 0,
            'total_results_returned': 0,
            'avg_search_time_ms': 0,
            'cache_hits': 0
        }
        
        # Configuration
        self.default_confidence_threshold = getattr(settings, 'FEEDME_SIMILARITY_THRESHOLD', 0.7)
        self.max_retrieval_results = getattr(settings, 'FEEDME_MAX_RETRIEVAL_RESULTS', 5)
        
        logger.info("Initialized FeedMe knowledge source")
    
    async def _ensure_embedding_model(self):
        """Lazy initialize embedding model"""
        if self.embedding_model is None:
            try:
                self.embedding_model = SentenceTransformer(self._embedding_model_name)
                logger.info(f"Initialized embedding model: {self._embedding_model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize embedding model: {e}")
                raise
    
    async def search(
        self,
        query: str,
        context: Dict[str, Any],
        limit: int = 5,
        min_confidence: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search FeedMe knowledge base for relevant Q&A pairs
        
        Args:
            query: Search query text
            context: Context information from Primary Agent
            limit: Maximum number of results to return
            min_confidence: Minimum confidence threshold for results
            
        Returns:
            List of relevant Q&A examples with metadata
        """
        start_time = time.time()
        
        try:
            await self._ensure_embedding_model()
            
            # Generate query embedding
            query_embedding = await self._encode_query(query)
            
            # Build search filters from context
            filters = self._build_search_filters(context, min_confidence)
            
            # Perform hybrid search
            results = self._perform_search(
                query=query,
                query_embedding=query_embedding,
                filters=filters,
                limit=limit
            )
            
            # Track usage for retrieved examples
            await self._track_usage(results)
            
            # Update statistics
            search_time_ms = int((time.time() - start_time) * 1000)
            self._update_search_stats(len(results), search_time_ms)
            
            logger.debug(f"FeedMe search completed: query='{query}', results={len(results)}, time={search_time_ms}ms")
            
            return results
            
        except Exception as e:
            logger.error(f"Error in FeedMe knowledge search: {e}")
            return []
    
    async def _encode_query(self, query: str) -> np.ndarray:
        """
        Encode query text to embedding vector
        
        Args:
            query: Query text to encode
            
        Returns:
            Query embedding vector
        """
        try:
            # Check for cached embedding (simple implementation)
            # In production, this could use Redis or in-memory cache
            
            # Encode query (handle both sync and async models)
            if hasattr(self.embedding_model, 'encode') and callable(self.embedding_model.encode):
                if asyncio.iscoroutinefunction(self.embedding_model.encode):
                    embedding = await self.embedding_model.encode(query)
                else:
                    embedding = self.embedding_model.encode(
                        query,
                        normalize_embeddings=True,
                        convert_to_numpy=True
                    )
            else:
                # Fallback for mock objects
                embedding = self.embedding_model.encode(query)
            
            # Ensure it's a numpy array
            if not isinstance(embedding, np.ndarray):
                if hasattr(embedding, 'numpy'):
                    embedding = embedding.numpy()
                else:
                    embedding = np.array(embedding)
            
            return embedding.astype(np.float32)
            
        except Exception as e:
            logger.error(f"Error encoding query: {e}")
            # Return zero vector as fallback
            return np.zeros(384, dtype=np.float32)
    
    def _build_search_filters(
        self,
        context: Dict[str, Any],
        min_confidence: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Build search filters from Primary Agent context
        
        Args:
            context: Context from Primary Agent
            min_confidence: Optional confidence override
            
        Returns:
            Search filters dictionary
        """
        filters = {}
        
        # Set confidence threshold
        filters['min_confidence'] = min_confidence or self.default_confidence_threshold
        
        # Map context fields to search filters
        if 'detected_category' in context:
            filters['issue_category'] = context['detected_category']
        elif 'detected_intent' in context:
            filters['issue_category'] = context['detected_intent']
        
        if 'user_platform' in context:
            filters['platform'] = context['user_platform']
        elif 'customer_context' in context and 'platform' in context['customer_context']:
            filters['platform'] = context['customer_context']['platform']
        
        # Add emotional state for prioritization
        if 'customer_emotion' in context or 'emotional_state' in context:
            emotion = context.get('customer_emotion') or context.get('emotional_state')
            if emotion in ['frustrated', 'angry', 'urgent']:
                # Lower confidence threshold for urgent cases
                filters['min_confidence'] = max(0.6, filters['min_confidence'] - 0.1)
        
        # Filter for active examples only
        filters['is_active'] = True
        
        return filters
    
    def _perform_search(
        self,
        query: str,
        query_embedding: np.ndarray,
        filters: Dict[str, Any],
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Perform actual search using hybrid search engine
        
        Args:
            query: Search query text
            query_embedding: Query embedding vector
            filters: Search filters
            limit: Maximum results
            
        Returns:
            Search results
        """
        try:
            # Use repository's hybrid search method (note: it's sync, not async)
            results = self.repository.search_examples_hybrid(
                query=query,
                embedding=query_embedding,
                filters=filters,
                limit=min(limit, self.max_retrieval_results),
                min_confidence=filters.get('min_confidence', self.default_confidence_threshold)
            )
            
            # Ensure results have required fields
            formatted_results = []
            for result in results:
                formatted_result = {
                    'id': result.get('id'),
                    'question_text': result.get('question_text', ''),
                    'answer_text': result.get('answer_text', ''),
                    'combined_score': result.get('combined_score', 0.0),
                    'confidence_score': result.get('confidence_score', 0.0),
                    'issue_type': result.get('issue_type', 'general'),
                    'tags': result.get('tags', []),
                    'usage_count': result.get('usage_count', 0),
                    'last_used_at': result.get('last_used_at'),
                    'context_before': result.get('context_before'),
                    'context_after': result.get('context_after'),
                    'vector_score': result.get('vector_score', 0.0),
                    'text_score': result.get('text_score', 0.0),
                    'search_type': result.get('search_type', 'hybrid'),
                    'primary_match': result.get('primary_match', 'semantic')
                }
                formatted_results.append(formatted_result)
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error performing FeedMe search: {e}")
            return []
    
    async def _track_usage(self, results: List[Dict[str, Any]]):
        """
        Track usage of retrieved examples
        
        Args:
            results: Search results to track
        """
        if not results:
            return
        
        try:
            # Track usage for all retrieved examples
            tasks = []
            for result in results:
                example_id = result.get('id')
                if example_id:
                    task = self.repository.increment_usage_count(example_id)
                    tasks.append(task)
            
            # Execute usage tracking concurrently
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.debug(f"Tracked usage for {len(tasks)} examples")
                
        except Exception as e:
            logger.error(f"Error tracking example usage: {e}")
    
    def _update_search_stats(self, result_count: int, search_time_ms: int):
        """
        Update search performance statistics
        
        Args:
            result_count: Number of results returned
            search_time_ms: Search time in milliseconds
        """
        self._search_stats['total_searches'] += 1
        self._search_stats['total_results_returned'] += result_count
        
        # Update rolling average of search time
        total_searches = self._search_stats['total_searches']
        prev_avg = self._search_stats['avg_search_time_ms']
        self._search_stats['avg_search_time_ms'] = (
            (prev_avg * (total_searches - 1) + search_time_ms) / total_searches
        )
    
    async def get_related_conversations(
        self,
        example_id: int,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Get conversations related to a specific example
        
        Args:
            example_id: ID of the reference example
            limit: Maximum number of related examples
            
        Returns:
            List of related conversation examples
        """
        try:
            # Get the reference example
            reference_example = await self.repository.get_example(example_id)
            if not reference_example:
                logger.warning(f"Reference example not found: {example_id}")
                return []
            
            # Get similar examples based on combined embedding
            reference_embedding = reference_example.get('combined_embedding')
            if not reference_embedding:
                logger.warning(f"Reference example has no embedding: {example_id}")
                return []
            
            # Find similar examples
            similar_examples = await self.repository.find_similar_examples(
                reference_embedding=np.array(reference_embedding),
                exclude_id=example_id,
                limit=limit,
                min_similarity=0.75
            )
            
            return similar_examples
            
        except Exception as e:
            logger.error(f"Error getting related conversations: {e}")
            return []
    
    def get_search_statistics(self) -> Dict[str, Any]:
        """
        Get knowledge source search statistics
        
        Returns:
            Dictionary of search statistics
        """
        return self._search_stats.copy()
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check of knowledge source components
        
        Returns:
            Health status information
        """
        status = {
            'status': 'healthy',
            'components': {},
            'statistics': self.get_search_statistics()
        }
        
        try:
            # Check embedding model
            await self._ensure_embedding_model()
            status['components']['embedding_model'] = {
                'status': 'healthy',
                'model_name': self._embedding_model_name
            }
        except Exception as e:
            status['components']['embedding_model'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            status['status'] = 'degraded'
        
        try:
            # Check repository connection
            # Simple check by attempting to get repository stats
            repo_stats = await self.repository.get_repository_statistics()
            status['components']['repository'] = {
                'status': 'healthy',
                'total_examples': repo_stats.get('total_examples', 0)
            }
        except Exception as e:
            status['components']['repository'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            status['status'] = 'unhealthy'
        
        return status