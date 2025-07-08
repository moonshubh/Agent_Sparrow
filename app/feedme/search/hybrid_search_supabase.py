"""
FeedMe v2.0 Hybrid Search Engine with Supabase Integration
Combines vector similarity and full-text search with Supabase support
"""

import logging
import time
import asyncio
from typing import List, Dict, Any, Optional
import numpy as np

from .feedme_vector_search import FeedMeVectorSearch

logger = logging.getLogger(__name__)


class HybridSearchEngineSupabase:
    """Advanced hybrid search combining vector and text search with Supabase"""
    
    def __init__(self, vector_weight: float = 1.0, text_weight: float = 0.0):
        """
        Initialize hybrid search engine with Supabase-only support
        Vector search only for now, text search to be implemented in Supabase
        
        Args:
            vector_weight: Weight for vector similarity scores (default 1.0)
            text_weight: Weight for text search scores (default 0.0 - not implemented)
        """
        self.vector_engine = FeedMeVectorSearch()
        
        # For now, we only support vector search
        self.vector_weight = 1.0
        self.text_weight = 0.0
        
        # Performance tracking
        self._last_search_performance = {}
    
    async def search(
        self,
        query: str,
        query_embedding: np.ndarray,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        min_confidence: float = 0.7,
        enable_stemming: bool = False,
        track_performance: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining vector and text search with Supabase
        
        Args:
            query: Text query for full-text search
            query_embedding: Embedding vector for similarity search
            limit: Maximum number of results
            filters: Additional filters to apply
            min_confidence: Minimum confidence threshold
            enable_stemming: Enable stemming in text search
            track_performance: Track detailed performance metrics
            search_supabase: Whether to search Supabase
            search_local: Whether to search local database
            
        Returns:
            List of search results with combined scores
        """
        start_time = time.time() if track_performance else None
        
        # Prepare search parameters
        search_limit = min(limit * 2, 50)  # Get more candidates for better merging
        
        # Apply confidence filter
        if filters is None:
            filters = {}
        filters['min_confidence'] = min_confidence
        
        try:
            # Perform vector search (Supabase only)
            vector_start = time.time() if track_performance else None
            vector_results = await self.vector_engine.search(
                embedding=query_embedding,
                limit=search_limit,
                min_similarity=min_confidence,
                filters=filters,
                include_metadata=True
            )
            vector_time = (time.time() - vector_start) if track_performance else 0
            
            # Text search not yet implemented in Supabase
            text_results = []
            text_time = 0
            
            # Combine results
            combine_start = time.time() if track_performance else None
            combined_results = self._combine_results(vector_results, text_results, limit)
            combine_time = (time.time() - combine_start) if track_performance else 0
            
            # Track performance if requested
            if track_performance:
                total_time = time.time() - start_time
                self._last_search_performance = {
                    'total_time_ms': int(total_time * 1000),
                    'vector_search_time_ms': int(vector_time * 1000),
                    'text_search_time_ms': int(text_time * 1000),
                    'combination_time_ms': int(combine_time * 1000),
                    'vector_results_count': len(vector_results),
                    'text_results_count': len(text_results),
                    'final_results_count': len(combined_results),
                    'sources_searched': {
                        'local': False,
                        'supabase': True
                    }
                }
            
            return combined_results
            
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            
            # Graceful degradation - try individual searches
            try:
                logger.info("Attempting fallback to vector search only")
                return await self.vector_engine.search(
                    embedding=query_embedding,
                    limit=limit,
                    min_similarity=min_confidence,
                    filters=filters
                )
            except Exception as vector_error:
                logger.error(f"Vector search fallback failed: {vector_error}")
                
                # Text search not available in Supabase-only mode
                logger.error("Text search not yet implemented for Supabase")
                
                return []
    
    def _combine_results(
        self,
        vector_results: List[Dict[str, Any]],
        text_results: List[Dict[str, Any]],
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Combine and rank results from vector and text search
        
        Args:
            vector_results: Results from vector search (may include Supabase results)
            text_results: Results from text search
            limit: Maximum number of final results
            
        Returns:
            Combined and ranked results
        """
        # Create lookup for vector scores by composite key (id + source)
        vector_scores = {}
        for result in vector_results:
            key = f"{result['id']}_{result.get('search_source', 'local')}"
            vector_scores[key] = result['vector_score']
        
        # Create lookup for text scores
        text_scores = {result['id']: result['text_score'] for result in text_results}
        
        # Merge results by ID, keeping track of source
        results_by_key = {}
        
        # Process vector results (includes both local and Supabase)
        for result in vector_results:
            key = f"{result['id']}_{result.get('search_source', 'local')}"
            results_by_key[key] = result
        
        # Process text results (local only)
        for result in text_results:
            key = f"{result['id']}_local"
            if key not in results_by_key:
                result['search_source'] = 'local'
                results_by_key[key] = result
        
        # Calculate combined scores and build final results
        combined_results = []
        
        for result_key, result in results_by_key.items():
            result = result.copy()
            
            # Get individual scores
            vector_score = vector_scores.get(result_key, 0.0)
            
            # Text score only applies to local results
            text_score = 0.0
            if result.get('search_source') == 'local':
                text_score = text_scores.get(result['id'], 0.0)
                if text_score > 0:
                    text_score = min(text_score, 1.0)  # Cap at 1.0
            
            # Calculate combined score
            if result.get('search_source') == 'supabase':
                # For Supabase results, use vector score only
                combined_score = vector_score
            else:
                # For local results, combine vector and text scores
                combined_score = (vector_score * self.vector_weight + 
                                text_score * self.text_weight)
            
            # Add scores to result
            result['vector_score'] = vector_score
            result['text_score'] = text_score
            result['combined_score'] = combined_score
            
            # Determine primary match type
            if vector_score > text_score:
                result['primary_match'] = 'semantic'
            elif text_score > vector_score:
                result['primary_match'] = 'textual'
            else:
                result['primary_match'] = 'balanced'
            
            combined_results.append(result)
        
        # Sort by combined score
        combined_results.sort(key=lambda x: x['combined_score'], reverse=True)
        
        # Apply final limit
        return combined_results[:limit]
    
    async def search_adaptive(
        self,
        query: str,
        query_embedding: np.ndarray,
        context: Dict[str, Any],
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Perform adaptive search based on context
        
        Args:
            query: Text query
            query_embedding: Query embedding
            context: Search context from Primary Agent
            limit: Maximum results
            
        Returns:
            Search results with adaptive weighting
        """
        # Determine adaptive weights based on context
        if context.get('query_type') == 'technical':
            # Technical queries benefit more from semantic search
            self.vector_weight = 0.8
            self.text_weight = 0.2
        elif context.get('query_type') == 'error_message':
            # Error messages benefit from exact text matching
            self.vector_weight = 0.5
            self.text_weight = 0.5
        else:
            # Default balanced weights
            self.vector_weight = 0.7
            self.text_weight = 0.3
        
        # Extract filters from context
        filters = {}
        if 'min_confidence' in context:
            filters['min_confidence'] = context['min_confidence']
        if 'issue_category' in context:
            filters['issue_category'] = context['issue_category']
        
        # Perform search (Supabase only)
        return await self.search(
            query=query,
            query_embedding=query_embedding,
            limit=limit,
            filters=filters,
            enable_stemming=context.get('enable_stemming', False),
            track_performance=True
        )
    
    def get_last_search_performance(self) -> Dict[str, Any]:
        """Get performance metrics from the last search"""
        return self._last_search_performance.copy()
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of search engines"""
        status = {
            'status': 'healthy',
            'engines': {
                'vector': 'unknown',
                'text': 'unknown'
            },
            'last_performance': self.get_last_search_performance()
        }
        
        # Check vector engine
        try:
            vector_stats = self.vector_engine.get_embedding_statistics()
            if vector_stats:
                status['engines']['vector'] = 'healthy'
        except Exception as e:
            status['engines']['vector'] = f'unhealthy: {str(e)}'
            status['status'] = 'degraded'
        
        # Text engine not available in Supabase-only mode
        status['engines']['text'] = 'not_implemented'
        
        return status