"""
FeedMe v2.0 Optimized Repository
High-performance repository with advanced querying capabilities for Phase 2
"""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
import numpy as np

from app.db.connection_manager import get_connection_manager

logger = logging.getLogger(__name__)


class OptimizedFeedMeRepository:
    """High-performance repository with optimized queries for FeedMe v2.0 Phase 2"""
    
    def __init__(self):
        self.connection_manager = get_connection_manager()
        self.expected_embedding_dimension = 384
    
    def search_examples_hybrid(
        self,
        query: str,
        embedding: np.ndarray,
        limit: int = 10,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        min_confidence: float = 0.7,
        timeout: float = 10.0,
        include_performance_metrics: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining vector similarity and full-text search with advanced filtering
        
        Args:
            query: Text query for full-text search
            embedding: Query embedding vector for similarity search
            limit: Maximum number of results to return
            offset: Number of results to skip (for pagination)
            filters: Additional filters to apply
            min_confidence: Minimum confidence score threshold
            timeout: Query timeout in seconds
            include_performance_metrics: Include performance metrics in results
            
        Returns:
            List of search results with combined scores
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        
        if limit <= 0:
            raise ValueError("Limit must be positive")
            
        if len(embedding) != self.expected_embedding_dimension:
            raise ValueError(f"Expected embedding dimension {self.expected_embedding_dimension}, got {len(embedding)}")
        
        # Build dynamic filter conditions
        filter_conditions = []
        params = {
            'embedding': embedding.tolist(),
            'query': query,
            'limit': limit,
            'offset': offset,
            'min_confidence': min_confidence
        }
        
        if filters:
            if 'issue_category' in filters:
                filter_conditions.append("e.issue_category = %(issue_category)s")
                params['issue_category'] = filters['issue_category']
            
            if 'platform' in filters:
                filter_conditions.append("c.platform = %(platform)s")
                params['platform'] = filters['platform']
                
            if 'min_quality' in filters:
                filter_conditions.append("e.overall_quality_score >= %(min_quality)s")
                params['min_quality'] = filters['min_quality']
        
        # Add base conditions
        filter_conditions.extend([
            "e.is_active = true",
            "e.confidence_score >= %(min_confidence)s"
        ])
        
        where_clause = " AND ".join(filter_conditions)
        
        # Optimized hybrid search query with proper scoring
        sql = f"""
        WITH vector_search AS (
            SELECT 
                e.id,
                e.question_text,
                e.answer_text,
                e.confidence_score,
                e.usefulness_score,
                COALESCE(e.overall_quality_score, 0) as overall_quality_score,
                COALESCE(e.feedback_score, 0.5) as feedback_score,
                e.usage_count,
                e.issue_category,
                e.tags,
                e.created_at,
                1 - (e.combined_embedding <=> %(embedding)s::vector) as vector_score
            FROM feedme_examples_v2 e
            JOIN feedme_conversations_v2 c ON e.conversation_id = c.id
            WHERE {where_clause}
            ORDER BY e.combined_embedding <=> %(embedding)s::vector
            LIMIT %(limit)s * 2
        ),
        text_search AS (
            SELECT 
                e.id,
                ts_rank(e.search_text, plainto_tsquery('english', %(query)s)) as text_score
            FROM feedme_examples_v2 e
            JOIN feedme_conversations_v2 c ON e.conversation_id = c.id
            WHERE e.search_text @@ plainto_tsquery('english', %(query)s)
              AND {where_clause}
            ORDER BY ts_rank(e.search_text, plainto_tsquery('english', %(query)s)) DESC
            LIMIT %(limit)s * 2
        )
        SELECT DISTINCT
            e.id,
            e.question_text,
            e.answer_text,
            e.confidence_score,
            e.usefulness_score,
            COALESCE(e.overall_quality_score, 0) as overall_quality_score,
            COALESCE(e.feedback_score, 0.5) as feedback_score,
            e.usage_count,
            e.issue_category,
            e.tags,
            e.created_at,
            COALESCE(v.vector_score, 0) as vector_score,
            COALESCE(t.text_score, 0) as text_score,
            -- Combined score with 70% vector, 30% text weighting
            (COALESCE(v.vector_score, 0) * 0.7 + COALESCE(t.text_score, 0) * 0.3) as combined_score
        FROM feedme_examples_v2 e
        LEFT JOIN vector_search v ON e.id = v.id
        LEFT JOIN text_search t ON e.id = t.id
        JOIN feedme_conversations_v2 c ON e.conversation_id = c.id
        WHERE (v.id IS NOT NULL OR t.id IS NOT NULL)
          AND {where_clause}
        ORDER BY combined_score DESC
        LIMIT %(limit)s
        OFFSET %(offset)s
        """
        
        try:
            start_time = time.time() if include_performance_metrics else None
            
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    results = cur.fetchall()
            
            processed_results = []
            for row in results:
                result = dict(row)
                
                # Convert arrays to lists for JSON serialization
                if result.get('tags'):
                    result['tags'] = list(result['tags'])
                
                # Add performance metrics if requested
                if include_performance_metrics and start_time:
                    result['query_time_ms'] = int((time.time() - start_time) * 1000)
                
                processed_results.append(result)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Database error in hybrid search: {e}")
            raise

    def vector_similarity_search(
        self,
        embedding: np.ndarray,
        limit: int = 10,
        min_similarity: float = 0.7,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Pure vector similarity search with optimized performance"""
        
        if len(embedding) != self.expected_embedding_dimension:
            raise ValueError(f"Expected embedding dimension {self.expected_embedding_dimension}, got {len(embedding)}")
        
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
        
        where_clause = " AND ".join(filter_conditions)
        
        sql = f"""
        SELECT 
            e.id,
            e.question_text,
            e.answer_text,
            e.confidence_score,
            e.issue_category,
            e.tags,
            1 - (e.combined_embedding <=> %(embedding)s::vector) as vector_score
        FROM feedme_examples_v2 e
        WHERE {where_clause}
          AND 1 - (e.combined_embedding <=> %(embedding)s::vector) >= %(min_similarity)s
        ORDER BY e.combined_embedding <=> %(embedding)s::vector
        LIMIT %(limit)s
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    results = cur.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error in vector similarity search: {e}")
            raise

    def full_text_search(
        self,
        query: str,
        limit: int = 10,
        enable_stemming: bool = False
    ) -> List[Dict[str, Any]]:
        """Pure full-text search with PostgreSQL's text search capabilities"""
        
        if not query or len(query.strip()) < 2:
            raise ValueError("Query must be at least 2 characters long")
        
        # Choose query function based on stemming preference
        query_func = "to_tsquery" if enable_stemming else "plainto_tsquery"
        
        sql = f"""
        SELECT 
            e.id,
            e.question_text,
            e.answer_text,
            e.confidence_score,
            e.issue_category,
            e.tags,
            ts_rank(e.search_text, {query_func}('english', %(query)s)) as text_score
        FROM feedme_examples_v2 e
        WHERE e.search_text @@ {query_func}('english', %(query)s)
          AND e.is_active = true
        ORDER BY ts_rank(e.search_text, {query_func}('english', %(query)s)) DESC
        LIMIT %(limit)s
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {'query': query, 'limit': limit})
                    results = cur.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error in full-text search: {e}")
            raise

    def get_conversations_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Get conversations within date range (leverages partitioning)"""
        
        filter_conditions = []
        params = {
            'start_date': start_date,
            'end_date': end_date
        }
        
        if filters:
            if 'platform' in filters:
                filter_conditions.append("platform = %(platform)s")
                params['platform'] = filters['platform']
            
            if 'processing_status' in filters:
                filter_conditions.append("processing_status = %(processing_status)s")
                params['processing_status'] = filters['processing_status']
        
        where_clause = ""
        if filter_conditions:
            where_clause = "AND " + " AND ".join(filter_conditions)
        
        sql = f"""
        SELECT 
            id,
            title,
            platform,
            processing_status,
            total_examples,
            COALESCE(extraction_quality_score, 0) as extraction_quality_score,
            created_at,
            -- Include partition information for debugging
            tableoid::regclass::text as partition_name
        FROM feedme_conversations_v2
        WHERE created_at >= %(start_date)s 
          AND created_at < %(end_date)s
          {where_clause}
        ORDER BY created_at DESC
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    results = cur.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error in date range query: {e}")
            raise

    def get_analytics_dashboard(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get analytics data from materialized view"""
        
        sql = """
        SELECT 
            date,
            total_conversations,
            total_examples_extracted,
            avg_extraction_quality,
            avg_processing_time_ms,
            successful_extractions,
            failed_extractions,
            avg_word_count,
            avg_message_count,
            platforms_used
        FROM feedme_analytics_dashboard
        WHERE date >= %(start_date)s AND date <= %(end_date)s
        ORDER BY date DESC
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {
                        'start_date': start_date.date(),
                        'end_date': end_date.date()
                    })
                    results = cur.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error in analytics query: {e}")
            raise

    def explain_query_plan(self, query: str) -> List[Dict[str, Any]]:
        """Get query execution plan for performance analysis"""
        
        explain_sql = f"EXPLAIN (FORMAT JSON, ANALYZE) {query}"
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(explain_sql)
                    results = cur.fetchall()
            return [{'query_plan': str(row[0])} for row in results]
        except Exception as e:
            logger.error(f"Error in query plan analysis: {e}")
            raise

    def get_example(self, example_id: int) -> Optional[Dict[str, Any]]:
        """Get single example by ID"""
        
        sql = """
        SELECT 
            id,
            question_text,
            answer_text,
            combined_embedding,
            confidence_score,
            issue_category,
            tags,
            created_at
        FROM feedme_examples_v2
        WHERE id = %(example_id)s AND is_active = true
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {'example_id': example_id})
                    result = cur.fetchone()
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error fetching example {example_id}: {e}")
            return None

    def find_similar_examples(
        self,
        embedding: Union[np.ndarray, List[float]],
        exclude_id: int,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Find similar examples by embedding similarity"""
        
        if isinstance(embedding, np.ndarray):
            embedding = embedding.tolist()
        
        sql = """
        SELECT 
            id,
            question_text,
            answer_text,
            1 - (combined_embedding <=> %(embedding)s::vector) as similarity_score
        FROM feedme_examples_v2
        WHERE id != %(exclude_id)s 
          AND is_active = true
        ORDER BY combined_embedding <=> %(embedding)s::vector
        LIMIT %(limit)s
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {
                        'embedding': embedding,
                        'exclude_id': exclude_id,
                        'limit': limit
                    })
                    results = cur.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error finding similar examples: {e}")
            raise

    def increment_usage_count(self, example_id: int) -> bool:
        """Increment usage count for an example"""
        
        sql = """
        UPDATE feedme_examples_v2 
        SET 
            usage_count = usage_count + 1,
            last_used_at = NOW(),
            updated_at = NOW()
        WHERE id = %(example_id)s AND is_active = true
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {'example_id': example_id})
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Error incrementing usage count for example {example_id}: {e}")
            return False

    def refresh_materialized_views(self) -> bool:
        """Refresh all materialized views for updated analytics"""
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT refresh_feedme_analytics()")
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error refreshing materialized views: {e}")
            return False

    def get_table_statistics(self) -> List[Dict[str, Any]]:
        """Get table size and performance statistics"""
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM get_feedme_table_stats()")
                    results = cur.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting table statistics: {e}")
            return []

    # ===========================
    # Approval Workflow Methods
    # ===========================

    async def create_temp_example(self, temp_example_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new temp example for approval workflow"""
        
        sql = """
        INSERT INTO feedme_temp_examples (
            conversation_id, question_text, answer_text, context_before, context_after,
            question_embedding, answer_embedding, combined_embedding,
            extraction_method, extraction_confidence, ai_model_used,
            approval_status, priority, auto_approved, auto_approval_reason,
            extraction_timestamp
        ) VALUES (
            %(conversation_id)s, %(question_text)s, %(answer_text)s, 
            %(context_before)s, %(context_after)s,
            %(question_embedding)s, %(answer_embedding)s, %(combined_embedding)s,
            %(extraction_method)s, %(extraction_confidence)s, %(ai_model_used)s,
            %(approval_status)s, %(priority)s, %(auto_approved)s, %(auto_approval_reason)s,
            %(extraction_timestamp)s
        ) RETURNING *
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, temp_example_data)
                    result = cur.fetchone()
                    conn.commit()
                    return dict(result)
        except Exception as e:
            logger.error(f"Error creating temp example: {e}")
            raise

    async def get_temp_example(self, temp_example_id: int) -> Optional[Dict[str, Any]]:
        """Get temp example by ID"""
        
        sql = """
        SELECT * FROM feedme_temp_examples 
        WHERE id = %(temp_example_id)s
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {'temp_example_id': temp_example_id})
                    result = cur.fetchone()
                    return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting temp example {temp_example_id}: {e}")
            return None

    async def update_temp_example(self, temp_example_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update temp example"""
        
        # Build dynamic update query
        set_clauses = []
        params = {'temp_example_id': temp_example_id}
        
        for key, value in update_data.items():
            set_clauses.append(f"{key} = %({key})s")
            params[key] = value
        
        if not set_clauses:
            raise ValueError("No update data provided")
        
        sql = f"""
        UPDATE feedme_temp_examples 
        SET {', '.join(set_clauses)}, updated_at = NOW()
        WHERE id = %(temp_example_id)s
        RETURNING *
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    result = cur.fetchone()
                    conn.commit()
                    return dict(result)
        except Exception as e:
            logger.error(f"Error updating temp example {temp_example_id}: {e}")
            raise

    async def get_temp_examples_by_status(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 10
    ) -> Dict[str, Any]:
        """Get temp examples with filtering and pagination"""
        
        filter_conditions = []
        params = {
            'limit': page_size,
            'offset': (page - 1) * page_size
        }
        
        if filters:
            if 'approval_status' in filters:
                filter_conditions.append("approval_status = %(approval_status)s")
                params['approval_status'] = filters['approval_status']
            
            if 'assigned_reviewer' in filters:
                filter_conditions.append("assigned_reviewer = %(assigned_reviewer)s")
                params['assigned_reviewer'] = filters['assigned_reviewer']
            
            if 'priority' in filters:
                filter_conditions.append("priority = %(priority)s")
                params['priority'] = filters['priority']
            
            if 'min_confidence' in filters:
                filter_conditions.append("extraction_confidence >= %(min_confidence)s")
                params['min_confidence'] = filters['min_confidence']
        
        where_clause = ""
        if filter_conditions:
            where_clause = "WHERE " + " AND ".join(filter_conditions)
        
        # Get total count
        count_sql = f"SELECT COUNT(*) FROM feedme_temp_examples {where_clause}"
        
        # Get paginated results
        data_sql = f"""
        SELECT * FROM feedme_temp_examples 
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get total count
                    cur.execute(count_sql, params)
                    total = cur.fetchone()[0]
                    
                    # Get paginated data
                    cur.execute(data_sql, params)
                    items = [dict(row) for row in cur.fetchall()]
                    
                    return {
                        'items': items,
                        'total': total,
                        'page': page,
                        'page_size': page_size,
                        'total_pages': (total + page_size - 1) // page_size
                    }
        except Exception as e:
            logger.error(f"Error getting temp examples by status: {e}")
            raise

    async def get_temp_examples_by_ids(self, temp_example_ids: List[int]) -> List[Dict[str, Any]]:
        """Get multiple temp examples by IDs"""
        
        sql = """
        SELECT * FROM feedme_temp_examples 
        WHERE id = ANY(%(temp_example_ids)s)
        ORDER BY id
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {'temp_example_ids': temp_example_ids})
                    results = cur.fetchall()
                    return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting temp examples by IDs: {e}")
            raise

    async def create_review_history(self, history_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create review history record"""
        
        sql = """
        INSERT INTO feedme_review_history (
            temp_example_id, reviewer_id, action, review_notes,
            confidence_assessment, time_spent_minutes,
            previous_status, new_status, changes_made
        ) VALUES (
            %(temp_example_id)s, %(reviewer_id)s, %(action)s, %(review_notes)s,
            %(confidence_assessment)s, %(time_spent_minutes)s,
            %(previous_status)s, %(new_status)s, %(changes_made)s
        ) RETURNING *
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, history_data)
                    result = cur.fetchone()
                    conn.commit()
                    return dict(result)
        except Exception as e:
            logger.error(f"Error creating review history: {e}")
            raise

    async def move_to_production(self, temp_example_id: int) -> bool:
        """Move approved temp example to production table"""
        
        sql = """
        WITH moved_example AS (
            DELETE FROM feedme_temp_examples 
            WHERE id = %(temp_example_id)s AND approval_status = 'approved'
            RETURNING *
        )
        INSERT INTO feedme_examples_v2 (
            conversation_id, question_text, answer_text, context_before, context_after,
            question_embedding, answer_embedding, combined_embedding,
            issue_category, tags, confidence_score, usefulness_score,
            reviewer_confidence_score, reviewer_usefulness_score,
            is_active, approval_status, reviewed_by, reviewed_at,
            created_at, updated_at
        )
        SELECT 
            conversation_id, question_text, answer_text, context_before, context_after,
            question_embedding, answer_embedding, combined_embedding,
            'general', ARRAY[]::text[], extraction_confidence, 
            COALESCE(reviewer_usefulness_score, 0.8),
            COALESCE(reviewer_confidence_score, extraction_confidence),
            COALESCE(reviewer_usefulness_score, 0.8),
            true, 'approved', reviewer_id, reviewed_at,
            created_at, updated_at
        FROM moved_example
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {'temp_example_id': temp_example_id})
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Error moving temp example {temp_example_id} to production: {e}")
            return False

    async def get_approval_metrics(
        self, 
        start_date: datetime, 
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get approval workflow metrics"""
        
        sql = """
        SELECT 
            COUNT(*) FILTER (WHERE approval_status = 'pending') as total_pending,
            COUNT(*) FILTER (WHERE approval_status = 'approved') as total_approved,
            COUNT(*) FILTER (WHERE approval_status = 'rejected') as total_rejected,
            COUNT(*) FILTER (WHERE approval_status = 'revision_requested') as total_revision_requested,
            COUNT(*) FILTER (WHERE auto_approved = true) as total_auto_approved,
            AVG(EXTRACT(EPOCH FROM (reviewed_at - created_at))/3600.0) 
                FILTER (WHERE reviewed_at IS NOT NULL) as avg_review_time_hours,
            AVG(extraction_confidence) as avg_extraction_confidence,
            AVG(reviewer_confidence_score) FILTER (WHERE reviewer_confidence_score IS NOT NULL) as avg_reviewer_confidence
        FROM feedme_temp_examples
        WHERE created_at >= %(start_date)s AND created_at <= %(end_date)s
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {'start_date': start_date, 'end_date': end_date})
                    result = cur.fetchone()
                    return dict(result) if result else {}
        except Exception as e:
            logger.error(f"Error getting approval metrics: {e}")
            raise

    async def get_reviewer_workload(self) -> Dict[str, Any]:
        """Get reviewer workload information"""
        
        sql = """
        SELECT 
            assigned_reviewer as reviewer_id,
            COUNT(*) FILTER (WHERE approval_status = 'pending') as pending_count,
            COUNT(*) as total_reviewed,
            AVG(EXTRACT(EPOCH FROM (reviewed_at - created_at))/3600.0) 
                FILTER (WHERE reviewed_at IS NOT NULL) as avg_review_time_hours,
            COUNT(*) FILTER (WHERE DATE(reviewed_at) = CURRENT_DATE) as reviews_today,
            COUNT(*) FILTER (WHERE reviewed_at >= DATE_TRUNC('week', NOW())) as reviews_this_week
        FROM feedme_temp_examples
        WHERE assigned_reviewer IS NOT NULL
        GROUP BY assigned_reviewer
        ORDER BY pending_count DESC
        """
        
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    reviewers = [dict(row) for row in cur.fetchall()]
                    
                    return {
                        'reviewers': reviewers,
                        'total_pending': sum(r['pending_count'] for r in reviewers),
                        'avg_workload': sum(r['pending_count'] for r in reviewers) / len(reviewers) if reviewers else 0
                    }
        except Exception as e:
            logger.error(f"Error getting reviewer workload: {e}")
            raise
    
    def get_repository_statistics(self) -> Dict[str, Any]:
        """
        Get repository statistics for health checks
        
        Returns:
            Dictionary with repository statistics
        """
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get total examples count
                    cur.execute("SELECT COUNT(*) as total_examples FROM feedme_examples WHERE is_active = true")
                    total_examples = cur.fetchone()[0]
                    
                    # Get total conversations count
                    cur.execute("SELECT COUNT(*) as total_conversations FROM feedme_conversations")
                    total_conversations = cur.fetchone()[0]
                    
                    # Get examples with embeddings count
                    cur.execute("SELECT COUNT(*) as examples_with_embeddings FROM feedme_examples WHERE combined_embedding IS NOT NULL AND is_active = true")
                    examples_with_embeddings = cur.fetchone()[0]
                    
                    return {
                        'total_examples': total_examples,
                        'total_conversations': total_conversations,
                        'examples_with_embeddings': examples_with_embeddings,
                        'embedding_coverage': examples_with_embeddings / max(1, total_examples)
                    }
        
        except Exception as e:
            logger.error(f"Error getting repository statistics: {e}")
            return {
                'total_examples': 0,
                'total_conversations': 0,
                'examples_with_embeddings': 0,
                'embedding_coverage': 0.0
            }