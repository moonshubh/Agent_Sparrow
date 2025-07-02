"""
FeedMe v2.0 Hybrid Search Engine
Combines vector similarity and full-text search for optimal results
"""

import logging
import time
import asyncio
from typing import List, Dict, Any, Optional
import numpy as np

from .vector_search import VectorSearchEngine
from .text_search import TextSearchEngine

logger = logging.getLogger(__name__)


class HybridSearchEngine:
    """Advanced hybrid search combining vector and text search"""
    
    def __init__(self, vector_weight: float = 0.7, text_weight: float = 0.3):
        """
        Initialize hybrid search engine
        
        Args:
            vector_weight: Weight for vector similarity scores (0-1)
            text_weight: Weight for text search scores (0-1)
        """
        self.vector_engine = VectorSearchEngine()
        self.text_engine = TextSearchEngine()
        
        # Validate weights
        if not (0 <= vector_weight <= 1 and 0 <= text_weight <= 1):
            raise ValueError("Weights must be between 0 and 1")
        
        if abs(vector_weight + text_weight - 1.0) > 0.001:
            raise ValueError("Vector and text weights must sum to 1.0")
        
        self.vector_weight = vector_weight
        self.text_weight = text_weight
        
        # Performance tracking
        self._last_search_performance = {}
    
    def search(
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
        Perform hybrid search combining vector and text search
        
        Args:
            query: Text query for full-text search
            query_embedding: Embedding vector for similarity search
            limit: Maximum number of results
            filters: Additional filters to apply
            min_confidence: Minimum confidence threshold
            enable_stemming: Enable stemming in text search
            track_performance: Track detailed performance metrics
            
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
            # Perform vector search
            vector_start = time.time() if track_performance else None
            vector_results = self.vector_engine.search(
                embedding=query_embedding,
                limit=search_limit,
                filters=filters,
                include_metadata=True
            )
            vector_time = (time.time() - vector_start) if track_performance else 0
            
            # Perform text search
            text_start = time.time() if track_performance else None
            text_results = self.text_engine.search(
                query=query,
                limit=search_limit,
                filters=filters,
                enable_stemming=enable_stemming
            )
            text_time = (time.time() - text_start) if track_performance else 0
            
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
                    'final_results_count': len(combined_results)
                }
            
            return combined_results
            
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            
            # Graceful degradation - try individual searches
            try:
                logger.info("Attempting fallback to vector search only")
                return self.vector_engine.search(
                    embedding=query_embedding,
                    limit=limit,
                    filters=filters
                )
            except Exception as vector_error:
                logger.error(f"Vector search fallback failed: {vector_error}")
                
                try:
                    logger.info("Attempting fallback to text search only")
                    return self.text_engine.search(
                        query=query,
                        limit=limit,
                        filters=filters
                    )
                except Exception as text_error:
                    logger.error(f"Text search fallback failed: {text_error}")
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
            vector_results: Results from vector search
            text_results: Results from text search
            limit: Maximum number of final results
            
        Returns:
            Combined and ranked results
        """
        # Create lookup for vector scores
        vector_scores = {result['id']: result['vector_score'] for result in vector_results}
        
        # Create lookup for text scores
        text_scores = {result['id']: result['text_score'] for result in text_results}
        
        # Merge results by ID
        all_ids = set(vector_scores.keys()) | set(text_scores.keys())
        
        # Get full result data (prefer vector results, fallback to text)
        results_by_id = {}
        for result in vector_results:
            results_by_id[result['id']] = result
        
        for result in text_results:
            if result['id'] not in results_by_id:
                results_by_id[result['id']] = result
        
        # Calculate combined scores and build final results
        combined_results = []
        
        for result_id in all_ids:
            if result_id not in results_by_id:
                continue
            
            result = results_by_id[result_id].copy()
            
            # Get individual scores
            vector_score = vector_scores.get(result_id, 0.0)
            text_score = text_scores.get(result_id, 0.0)
            
            # Normalize text scores (ts_rank can vary widely)
            if text_score > 0:
                text_score = min(text_score, 1.0)  # Cap at 1.0
            
            # Calculate combined score
            combined_score = (vector_score * self.vector_weight + 
                            text_score * self.text_weight)
            
            # Add scores to result
            result['vector_score'] = vector_score
            result['text_score'] = text_score
            result['combined_score'] = combined_score
            result['search_type'] = 'hybrid'
            
            # Determine primary match type
            if vector_score > text_score:
                result['primary_match'] = 'semantic'
            else:
                result['primary_match'] = 'textual'
            
            combined_results.append(result)
        
        # Sort by combined score
        combined_results.sort(key=lambda x: x['combined_score'], reverse=True)
        
        # Return top results
        return combined_results[:limit]
    
    def search_with_fallback(
        self,
        query: str,
        query_embedding: Optional[np.ndarray] = None,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search with automatic fallback when one method fails
        
        Args:
            query: Text query
            query_embedding: Optional embedding vector
            limit: Maximum results
            filters: Additional filters
            
        Returns:
            Search results using best available method
        """
        # Try hybrid search if embedding is available
        if query_embedding is not None:
            try:
                return self.search(
                    query=query,
                    query_embedding=query_embedding,
                    limit=limit,
                    filters=filters
                )
            except Exception as e:
                logger.warning(f"Hybrid search failed, falling back to text search: {e}")
        
        # Fallback to text search only
        try:
            results = self.text_engine.search(
                query=query,
                limit=limit,
                filters=filters
            )
            
            # Add hybrid metadata
            for result in results:
                result['vector_score'] = 0.0
                result['combined_score'] = result.get('text_score', 0.0)
                result['search_type'] = 'text_fallback'
                result['primary_match'] = 'textual'
            
            return results
            
        except Exception as e:
            logger.error(f"All search methods failed: {e}")
            return []
    
    def get_search_suggestions(
        self,
        query: str,
        limit: int = 5
    ) -> Dict[str, Any]:
        """Get search suggestions and query expansions"""
        
        try:
            # Get text search suggestions
            text_suggestions = self.text_engine.search_with_suggestions(
                query=query,
                limit=0,  # Only get suggestions
                suggestion_limit=limit
            )
            
            # Get popular categories
            categories = self.text_engine.search_categories(limit=10)
            
            return {
                'query_suggestions': text_suggestions['suggestions'],
                'popular_categories': [cat['issue_category'] for cat in categories[:5]],
                'category_details': categories
            }
            
        except Exception as e:
            logger.error(f"Error getting search suggestions: {e}")
            return {'query_suggestions': [], 'popular_categories': [], 'category_details': []}
    
    def analyze_search_quality(
        self,
        query: str,
        query_embedding: Optional[np.ndarray] = None,
        sample_size: int = 20
    ) -> Dict[str, Any]:
        """
        Analyze search quality and provide insights
        
        Args:
            query: Search query
            query_embedding: Optional query embedding
            sample_size: Number of results to analyze
            
        Returns:
            Search quality analysis
        """
        analysis = {
            'query': query,
            'has_embedding': query_embedding is not None,
            'text_analysis': {},
            'vector_analysis': {},
            'hybrid_performance': {}
        }
        
        try:
            # Analyze text search
            text_results = self.text_engine.search(query, limit=sample_size)
            analysis['text_analysis'] = {
                'result_count': len(text_results),
                'avg_score': np.mean([r.get('text_score', 0) for r in text_results]) if text_results else 0,
                'score_distribution': self._analyze_score_distribution([r.get('text_score', 0) for r in text_results])
            }
            
            # Analyze vector search if embedding available
            if query_embedding is not None:
                vector_results = self.vector_engine.search(query_embedding, limit=sample_size)
                analysis['vector_analysis'] = {
                    'result_count': len(vector_results),
                    'avg_score': np.mean([r.get('vector_score', 0) for r in vector_results]) if vector_results else 0,
                    'score_distribution': self._analyze_score_distribution([r.get('vector_score', 0) for r in vector_results])
                }
                
                # Analyze hybrid performance
                hybrid_results = self.search(query, query_embedding, limit=sample_size, track_performance=True)
                analysis['hybrid_performance'] = {
                    'result_count': len(hybrid_results),
                    'avg_combined_score': np.mean([r.get('combined_score', 0) for r in hybrid_results]) if hybrid_results else 0,
                    'performance_metrics': self._last_search_performance
                }
            
        except Exception as e:
            logger.error(f"Error in search quality analysis: {e}")
            analysis['error'] = str(e)
        
        return analysis
    
    def _analyze_score_distribution(self, scores: List[float]) -> Dict[str, float]:
        """Analyze score distribution"""
        if not scores:
            return {'min': 0, 'max': 0, 'median': 0, 'std': 0}
        
        scores_array = np.array(scores)
        return {
            'min': float(np.min(scores_array)),
            'max': float(np.max(scores_array)),
            'median': float(np.median(scores_array)),
            'std': float(np.std(scores_array))
        }
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get last search performance metrics"""
        return self._last_search_performance.copy()
    
    def update_weights(self, vector_weight: float, text_weight: float):
        """
        Update search weights
        
        Args:
            vector_weight: New vector weight
            text_weight: New text weight
        """
        if not (0 <= vector_weight <= 1 and 0 <= text_weight <= 1):
            raise ValueError("Weights must be between 0 and 1")
        
        if abs(vector_weight + text_weight - 1.0) > 0.001:
            raise ValueError("Vector and text weights must sum to 1.0")
        
        self.vector_weight = vector_weight
        self.text_weight = text_weight
        
        logger.info(f"Updated search weights: vector={vector_weight}, text={text_weight}")
    
    def get_search_statistics(self) -> Dict[str, Any]:
        """Get search engine statistics"""
        
        try:
            vector_stats = self.vector_engine.get_embedding_statistics()
            text_categories = self.text_engine.search_categories(limit=10)
            
            return {
                'vector_statistics': vector_stats,
                'text_categories': len(text_categories),
                'search_weights': {
                    'vector_weight': self.vector_weight,
                    'text_weight': self.text_weight
                },
                'available_categories': [cat['issue_category'] for cat in text_categories]
            }
            
        except Exception as e:
            logger.error(f"Error getting search statistics: {e}")
            return {}