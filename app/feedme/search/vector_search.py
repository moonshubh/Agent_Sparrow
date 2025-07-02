"""
FeedMe v2.0 Vector Search Engine
High-performance vector similarity search using pgvector
"""

import logging
import time
from typing import List, Dict, Any, Optional
import numpy as np

from app.db.connection_manager import get_connection_manager

logger = logging.getLogger(__name__)


class VectorSearchEngine:
    """High-performance vector similarity search engine"""
    
    def __init__(self):
        self.connection_manager = get_connection_manager()
        self.expected_dimension = 384
    
    def search(
        self,
        embedding: np.ndarray,
        limit: int = 10,
        min_similarity: float = 0.7,
        filters: Optional[Dict[str, Any]] = None,
        include_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search
        
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
        
        # Build filter conditions
        filter_conditions = ["e.is_active = true"]
        params = {
            'embedding': embedding.tolist(),
            'limit': limit,
            'min_similarity': min_similarity
        }
        
        if filters:
            if 'issue_category' in filters:
                filter_conditions.append("e.issue_category = %(issue_category)s")
                params['issue_category'] = filters['issue_category']
            
            if 'min_confidence' in filters:
                filter_conditions.append("e.confidence_score >= %(min_confidence)s")
                params['min_confidence'] = filters['min_confidence']
                
            if 'created_after' in filters:
                filter_conditions.append("e.created_at >= %(created_after)s")
                params['created_after'] = filters['created_after']
        
        where_clause = " AND ".join(filter_conditions)
        
        # Select fields based on metadata requirement
        select_fields = """
            e.id,
            e.question_text,
            e.answer_text,
            e.confidence_score,
            1 - (e.combined_embedding <=> %(embedding)s::vector) as vector_score
        """
        
        if include_metadata:
            select_fields += """,
            e.issue_category,
            e.tags,
            e.usage_count,
            e.created_at,
            COALESCE(e.overall_quality_score, 0) as overall_quality_score
            """
        
        sql = f"""
        SELECT {select_fields}
        FROM feedme_examples_v2 e
        WHERE {where_clause}
          AND 1 - (e.combined_embedding <=> %(embedding)s::vector) >= %(min_similarity)s
        ORDER BY e.combined_embedding <=> %(embedding)s::vector
        LIMIT %(limit)s
        """
        
        try:
            start_time = time.time()
            
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    results = cur.fetchall()
            
            search_time = time.time() - start_time
            
            processed_results = []
            for row in results:
                result = dict(row)
                
                # Convert arrays to lists
                if result.get('tags'):
                    result['tags'] = list(result['tags'])
                
                # Add search metadata
                result['search_type'] = 'vector'
                result['search_time_ms'] = int(search_time * 1000)
                
                processed_results.append(result)
            
            logger.debug(f"Vector search found {len(processed_results)} results in {search_time:.3f}s")
            return processed_results
            
        except Exception as e:
            logger.error(f"Error in vector similarity search: {e}")
            raise

    def find_similar_by_text(
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
            
            # Build exclusion filter
            filters = {}
            if exclude_ids:
                # We'll handle exclusion in the query
                pass
            
            # Perform vector search
            results = self.search(
                embedding=embedding,
                limit=limit * 2 if exclude_ids else limit,  # Get more to account for exclusions
                min_similarity=0.5,  # Lower threshold for similarity
                filters=filters,
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

    def get_embedding_statistics(self) -> Dict[str, Any]:
        """Get statistics about the vector search index"""
        
        sql = """
        SELECT 
            COUNT(*) as total_examples,
            COUNT(*) FILTER (WHERE combined_embedding IS NOT NULL) as examples_with_embeddings,
            AVG(1 - (combined_embedding <=> combined_embedding)) as avg_self_similarity,
            COUNT(DISTINCT issue_category) as unique_categories
        FROM feedme_examples_v2
        WHERE is_active = true
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    result = cur.fetchone()
            
            return dict(result) if result else {}
            
        except Exception as e:
            logger.error(f"Error getting embedding statistics: {e}")
            return {}

    def batch_similarity_search(
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
                search_results = self.search(
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

    def find_diverse_results(
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
        candidates = self.search(
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
            
            # Check diversity against already selected results
            is_diverse = True
            candidate_emb = np.array(candidate.get('combined_embedding', []))
            
            for selected_result in selected:
                selected_emb = np.array(selected_result.get('combined_embedding', []))
                
                if len(candidate_emb) > 0 and len(selected_emb) > 0:
                    # Calculate cosine similarity
                    similarity = np.dot(candidate_emb, selected_emb) / (
                        np.linalg.norm(candidate_emb) * np.linalg.norm(selected_emb)
                    )
                    
                    if similarity > diversity_threshold:
                        is_diverse = False
                        break
            
            if is_diverse:
                selected.append(candidate)
        
        return selected