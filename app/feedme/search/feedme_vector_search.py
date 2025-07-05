"""
FeedMe v3.0 Unified Vector Search Engine - Supabase Only
High-performance vector similarity search using pgvector on Supabase
"""

import logging
import time
import asyncio
from typing import List, Dict, Any, Optional
import numpy as np

from app.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class FeedMeVectorSearch:
    """Unified vector similarity search engine using Supabase only"""
    
    def __init__(self):
        self.expected_dimension = 384
        self._supabase_client = None
    
    @property
    def supabase_client(self):
        """Lazy load Supabase client"""
        if self._supabase_client is None:
            self._supabase_client = get_supabase_client()
        return self._supabase_client
    
    async def search(
        self,
        embedding: np.ndarray,
        limit: int = 10,
        min_similarity: float = 0.7,
        filters: Optional[Dict[str, Any]] = None,
        include_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search on Supabase
        
        Args:
            embedding: Query embedding vector
            limit: Maximum number of results
            min_similarity: Minimum similarity score threshold
            filters: Additional filters to apply
            include_metadata: Include metadata in results
            
        Returns:
            List of search results with similarity scores
        """
        if len(embedding) != self.expected_dimension:
            raise ValueError(f"Expected embedding dimension {self.expected_dimension}, got {len(embedding)}")
        
        try:
            start_time = time.time()
            
            # Convert filters for Supabase
            supabase_filters = {}
            if filters:
                if 'min_confidence' in filters:
                    supabase_filters['min_confidence'] = filters['min_confidence']
                if 'issue_category' in filters:
                    supabase_filters['issue_type'] = filters['issue_category']
                if 'created_after' in filters:
                    supabase_filters['created_after'] = filters['created_after'].isoformat()
            
            # Search using Supabase client
            results = await self.supabase_client.search_examples(
                query_embedding=embedding.tolist(),
                limit=limit,
                similarity_threshold=min_similarity,
                filters=supabase_filters
            )
            
            search_time = time.time() - start_time
            
            # Process results to match expected format
            processed_results = []
            for result in results:
                processed_result = {
                    'id': result['id'],
                    'question_text': result['question_text'],
                    'answer_text': result['answer_text'],
                    'confidence_score': result.get('confidence_score', 0.8),
                    'vector_score': result.get('similarity', 0.0),
                    'search_type': 'vector',
                    'search_source': 'supabase',
                    'search_time_ms': int(search_time * 1000)
                }
                
                if include_metadata:
                    processed_result.update({
                        'issue_category': result.get('issue_type'),
                        'tags': result.get('tags', []),
                        'usage_count': result.get('usefulness_score', 0) * 10,  # Approximate usage
                        'created_at': result.get('created_at'),
                        'conversation_id': result.get('conversation_id'),
                        'overall_quality_score': result.get('confidence_score', 0.8)
                    })
                
                processed_results.append(processed_result)
            
            logger.debug(f"Supabase vector search found {len(processed_results)} results in {search_time:.3f}s")
            return processed_results
            
        except Exception as e:
            logger.error(f"Error in Supabase vector similarity search: {e}")
            raise
    
    async def find_similar_by_text(
        self,
        text: str,
        embedding_model,
        limit: int = 5,
        exclude_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Find similar examples by generating embedding from text
        
        Args:
            text: Text to find similar content for
            embedding_model: Model to generate embeddings
            limit: Maximum number of results
            exclude_ids: IDs to exclude from results
            
        Returns:
            List of similar examples
        """
        try:
            # Generate embedding from text
            embedding = embedding_model.encode(text, normalize_embeddings=True)
            
            # Perform vector search
            results = await self.search(
                embedding=embedding,
                limit=limit * 2 if exclude_ids else limit,  # Get more to account for exclusions
                min_similarity=0.5,  # Lower threshold for similarity
                include_metadata=True
            )
            
            # Filter out excluded IDs
            if exclude_ids:
                results = [r for r in results if r['id'] not in exclude_ids]
                results = results[:limit]
            
            return results
            
        except Exception as e:
            logger.error(f"Error finding similar by text: {e}")
            return []
    
    async def get_embedding_statistics(self) -> Dict[str, Any]:
        """Get statistics about the vector search index from Supabase"""
        try:
            # Use Supabase health check to get basic stats
            health_info = await self.supabase_client.health_check()
            
            return {
                'source': 'supabase',
                'status': health_info.get('status', 'unknown'),
                'total_examples': health_info.get('stats', {}).get('total_examples', 0),
                'examples_with_embeddings': health_info.get('stats', {}).get('examples_with_embeddings', 0)
            }
            
        except Exception as e:
            logger.error(f"Error getting embedding statistics from Supabase: {e}")
            return {
                'source': 'supabase',
                'status': 'error',
                'error': str(e)
            }
    
    async def batch_similarity_search(
        self,
        embeddings: List[np.ndarray],
        limit_per_query: int = 5
    ) -> List[List[Dict[str, Any]]]:
        """
        Perform batch similarity search for multiple embeddings
        
        Args:
            embeddings: List of query embeddings
            limit_per_query: Limit per individual query
            
        Returns:
            List of result lists, one for each input embedding
        """
        results = []
        
        for embedding in embeddings:
            try:
                search_results = await self.search(
                    embedding=embedding,
                    limit=limit_per_query,
                    min_similarity=0.6,
                    include_metadata=False  # Faster for batch operations
                )
                results.append(search_results)
            except Exception as e:
                logger.error(f"Error in batch search for embedding: {e}")
                results.append([])
        
        return results
    
    async def find_diverse_results(
        self,
        embedding: np.ndarray,
        limit: int = 10,
        diversity_threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        Find diverse results by avoiding too-similar examples
        
        Args:
            embedding: Query embedding
            limit: Maximum number of results
            diversity_threshold: Minimum diversity score between results
            
        Returns:
            List of diverse search results
        """
        # Get more results than needed
        candidates = await self.search(
            embedding=embedding,
            limit=limit * 3,
            min_similarity=0.5,
            include_metadata=True
        )
        
        if not candidates:
            return []
        
        # Select diverse results
        selected = [candidates[0]]  # Always include the best match
        
        for candidate in candidates[1:]:
            if len(selected) >= limit:
                break
            
            # For now, use a simple approach - can be enhanced later
            # Just ensure we don't have exact duplicates
            is_diverse = True
            for selected_result in selected:
                if candidate['id'] == selected_result['id']:
                    is_diverse = False
                    break
            
            if is_diverse:
                selected.append(candidate)
        
        return selected