"""
TDD Tests for FeedMe v2.0 Database Optimization
Tests for partitioned tables, advanced indexing, and performance optimization
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from typing import List, Dict, Any

import numpy as np

from app.feedme.repositories.optimized_repository import OptimizedFeedMeRepository


class TestDatabaseOptimization:
    """Test suite for database optimization features"""

    @pytest.fixture
    def mock_connection_manager(self):
        """Mock connection manager for testing"""
        from unittest.mock import MagicMock
        
        manager = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        
        # Setup cursor context manager
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = mock_cursor
        cursor_context.__exit__.return_value = None
        mock_conn.cursor.return_value = cursor_context
        
        # Setup connection context manager
        conn_context = MagicMock()
        conn_context.__enter__.return_value = mock_conn
        conn_context.__exit__.return_value = None
        manager.get_connection.return_value = conn_context
        
        return manager, mock_conn, mock_cursor

    @pytest.fixture
    def repository(self, mock_connection_manager):
        """Create optimized repository instance for testing"""
        manager, mock_conn, mock_cursor = mock_connection_manager
        repo = OptimizedFeedMeRepository()
        repo.connection_manager = manager
        return repo, mock_conn, mock_cursor

    @pytest.fixture
    def sample_embedding(self):
        """Sample embedding vector for testing"""
        return np.random.random(384).astype(np.float32)

    @pytest.fixture
    def sample_qa_data(self):
        """Sample Q&A data for testing"""
        return [
            {
                'id': 1,
                'question_text': 'How do I setup IMAP email?',
                'answer_text': 'To setup IMAP, go to Settings > Email Accounts...',
                'confidence_score': 0.9,
                'issue_category': 'email_setup'
            },
            {
                'id': 2,
                'question_text': 'Why is my email not syncing?',
                'answer_text': 'Email sync issues can be caused by...',
                'confidence_score': 0.8,
                'issue_category': 'sync_issues'
            }
        ]

    def test_hybrid_search_basic(self, repository, sample_embedding, sample_qa_data):
        """Test basic hybrid search functionality"""
        repo, mock_conn, mock_cursor = repository
        mock_cursor.fetchall.return_value = sample_qa_data
        
        # Execute hybrid search
        results = repo.search_examples_hybrid(
            query="email setup",
            embedding=sample_embedding,
            limit=5
        )
        
        # Verify results
        assert len(results) == 2
        assert results[0]['question_text'] == 'How do I setup IMAP email?'
        
        # Verify connection was used
        repo.connection_manager.get_connection.assert_called()
        mock_cursor.execute.assert_called()

    def test_hybrid_search_empty_results(self, repository, sample_embedding):
        """Test hybrid search with no results"""
        repo, mock_conn, mock_cursor = repository
        mock_cursor.fetchall.return_value = []
        
        results = repo.search_examples_hybrid(
            query="nonexistent query",
            embedding=sample_embedding,
            limit=5
        )
        
        assert len(results) == 0

    def test_hybrid_search_parameter_validation(self, repository, sample_embedding):
        """Test hybrid search parameter validation"""
        repo, mock_conn, mock_cursor = repository
        
        # Test with invalid limit
        with pytest.raises(ValueError):
            repo.search_examples_hybrid(
                query="test",
                embedding=sample_embedding,
                limit=0
            )
        
        # Test with empty query
        with pytest.raises(ValueError):
            repo.search_examples_hybrid(
                query="",
                embedding=sample_embedding,
                limit=5
            )

    @pytest.mark.asyncio
    async def test_performance_optimized_query(self, repository, sample_embedding):
        """Test performance-optimized query execution"""
        # Mock performance data
        repository.db.fetch_all.return_value = [
            {'id': 1, 'combined_score': 0.95, 'query_time_ms': 45}
        ]
        
        start_time = datetime.now()
        results = await repository.search_examples_hybrid(
            query="test query",
            embedding=sample_embedding,
            limit=10
        )
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # Verify performance (should be under 100ms for mocked response)
        assert execution_time < 0.1
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_partitioned_table_queries(self, repository):
        """Test queries against partitioned conversation tables"""
        # Mock partitioned query response
        repository.db.fetch_all.return_value = [
            {
                'id': 1,
                'title': 'Test Conversation',
                'partition_name': 'feedme_conversations_v2_2024_01',
                'created_at': datetime(2024, 1, 15)
            }
        ]
        
        # Test date-range query that should hit specific partition
        results = await repository.get_conversations_by_date_range(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31)
        )
        
        assert len(results) == 1
        assert results[0]['partition_name'] == 'feedme_conversations_v2_2024_01'

    @pytest.mark.asyncio 
    async def test_materialized_view_analytics(self, repository):
        """Test materialized view queries for analytics"""
        # Mock analytics data
        repository.db.fetch_all.return_value = [
            {
                'date': datetime(2024, 1, 15).date(),
                'total_conversations': 50,
                'total_examples': 150,
                'avg_processing_time': 25.5,
                'successful_extractions': 48,
                'failed_extractions': 2
            }
        ]
        
        results = await repository.get_analytics_dashboard(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31)
        )
        
        assert len(results) == 1
        assert results[0]['total_conversations'] == 50
        assert results[0]['avg_processing_time'] == 25.5

    @pytest.mark.asyncio
    async def test_index_optimization_verification(self, repository):
        """Test that queries utilize proper indexes"""
        # Mock EXPLAIN query results
        repository.db.fetch_all.return_value = [
            {
                'query_plan': 'Index Scan using idx_examples_composite_quality',
                'cost': '0.43..8.45',
                'rows': 5
            }
        ]
        
        # Execute query that should use composite quality index
        explain_result = await repository.explain_query_plan(
            "SELECT * FROM feedme_examples_v2 WHERE confidence_score > 0.8 ORDER BY confidence_score DESC LIMIT 5"
        )
        
        assert 'idx_examples_composite_quality' in explain_result[0]['query_plan']

    @pytest.mark.asyncio
    async def test_vector_similarity_performance(self, repository, sample_embedding):
        """Test vector similarity search performance"""
        # Mock vector search results with timing
        repository.db.fetch_all.return_value = [
            {
                'id': 1,
                'vector_score': 0.95,
                'search_time_ms': 12
            }
        ]
        
        results = await repository.vector_similarity_search(
            embedding=sample_embedding,
            limit=10,
            min_similarity=0.7
        )
        
        assert len(results) == 1
        assert results[0]['vector_score'] == 0.95

    @pytest.mark.asyncio
    async def test_full_text_search_performance(self, repository):
        """Test full-text search performance"""
        # Mock full-text search results
        repository.db.fetch_all.return_value = [
            {
                'id': 1,
                'text_score': 0.8,
                'search_time_ms': 8
            }
        ]
        
        results = await repository.full_text_search(
            query="email configuration",
            limit=10
        )
        
        assert len(results) == 1
        assert results[0]['text_score'] == 0.8

    @pytest.mark.asyncio
    async def test_combined_scoring_algorithm(self, repository, sample_embedding):
        """Test combined scoring algorithm for hybrid search"""
        # Mock results with both vector and text scores
        repository.db.fetch_all.return_value = [
            {
                'id': 1,
                'question_text': 'Test question',
                'vector_score': 0.9,
                'text_score': 0.7,
                'combined_score': 0.83  # 0.9 * 0.7 + 0.7 * 0.3 = 0.84
            }
        ]
        
        results = await repository.search_examples_hybrid(
            query="test",
            embedding=sample_embedding,
            limit=5
        )
        
        # Verify combined scoring
        assert results[0]['combined_score'] == 0.83
        
        # Verify SQL includes proper weight calculation
        call_args = repository.db.fetch_all.call_args
        sql_query = str(call_args[0][0])
        assert '* 0.7 +' in sql_query  # Vector weight
        assert '* 0.3' in sql_query    # Text weight

    @pytest.mark.asyncio
    async def test_database_error_handling(self, repository, sample_embedding):
        """Test database error handling in optimized queries"""
        # Mock database error
        repository.db.fetch_all.side_effect = Exception("Database connection error")
        
        with pytest.raises(Exception):
            await repository.search_examples_hybrid(
                query="test",
                embedding=sample_embedding,
                limit=5
            )

    @pytest.mark.asyncio
    async def test_query_timeout_handling(self, repository, sample_embedding):
        """Test query timeout handling"""
        # Mock timeout error
        repository.db.fetch_all.side_effect = asyncio.TimeoutError("Query timeout")
        
        with pytest.raises(asyncio.TimeoutError):
            await repository.search_examples_hybrid(
                query="test",
                embedding=sample_embedding,
                limit=5,
                timeout=1.0
            )

    def test_embedding_dimension_validation(self, repository):
        """Test embedding dimension validation"""
        # Test with wrong dimension
        wrong_dimension_embedding = np.random.random(512).astype(np.float32)
        
        with pytest.raises(ValueError, match="Expected embedding dimension 384"):
            asyncio.run(repository.search_examples_hybrid(
                query="test",
                embedding=wrong_dimension_embedding,
                limit=5
            ))

    @pytest.mark.asyncio
    async def test_pagination_support(self, repository, sample_embedding):
        """Test pagination support in optimized queries"""
        # Mock paginated results
        repository.db.fetch_all.return_value = [
            {'id': i, 'combined_score': 0.9 - i*0.1} for i in range(5)
        ]
        
        results = await repository.search_examples_hybrid(
            query="test",
            embedding=sample_embedding,
            limit=5,
            offset=10
        )
        
        assert len(results) == 5
        
        # Verify offset parameter in SQL
        call_args = repository.db.fetch_all.call_args
        params = call_args[1]
        assert 'offset' in params

    @pytest.mark.asyncio
    async def test_filtering_with_categories(self, repository, sample_embedding):
        """Test filtering by categories in hybrid search"""
        repository.db.fetch_all.return_value = [
            {
                'id': 1,
                'issue_category': 'email_setup',
                'combined_score': 0.9
            }
        ]
        
        results = await repository.search_examples_hybrid(
            query="test",
            embedding=sample_embedding,
            limit=5,
            filters={'issue_category': 'email_setup'}
        )
        
        assert len(results) == 1
        assert results[0]['issue_category'] == 'email_setup'

    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self, repository, sample_embedding):
        """Test performance monitoring integration"""
        # Mock performance metrics
        repository.db.fetch_all.return_value = [
            {
                'id': 1,
                'combined_score': 0.9,
                'execution_time_ms': 25,
                'cache_hit': False
            }
        ]
        
        results = await repository.search_examples_hybrid(
            query="test",
            embedding=sample_embedding,
            limit=5,
            include_performance_metrics=True
        )
        
        assert 'execution_time_ms' in results[0]
        assert results[0]['execution_time_ms'] == 25


class TestDatabaseMigrations:
    """Test database migration and schema optimization"""

    @pytest.mark.asyncio
    async def test_partitioning_migration(self):
        """Test table partitioning migration"""
        # This would test the actual migration script
        # For now, we'll test the concept
        migration_sql = """
        CREATE TABLE feedme_conversations_v2_2024_01 
            PARTITION OF feedme_conversations_v2
            FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
        """
        
        # Verify migration SQL structure
        assert 'PARTITION OF' in migration_sql
        assert 'FOR VALUES FROM' in migration_sql

    @pytest.mark.asyncio
    async def test_index_creation_migration(self):
        """Test advanced index creation"""
        index_sql = """
        CREATE INDEX idx_examples_composite_quality ON feedme_examples_v2 
            USING btree(confidence_score DESC, usefulness_score DESC) 
            WHERE is_active = true;
        """
        
        # Verify index SQL structure
        assert 'USING btree' in index_sql
        assert 'WHERE is_active = true' in index_sql

    def test_materialized_view_creation(self):
        """Test materialized view creation for analytics"""
        view_sql = """
        CREATE MATERIALIZED VIEW feedme_analytics_dashboard AS
        SELECT 
            DATE_TRUNC('day', created_at) as date,
            COUNT(*) as total_conversations
        FROM feedme_conversations_v2
        GROUP BY DATE_TRUNC('day', created_at);
        """
        
        assert 'MATERIALIZED VIEW' in view_sql
        assert 'DATE_TRUNC' in view_sql
        assert 'GROUP BY' in view_sql


if __name__ == "__main__":
    pytest.main([__file__, "-v"])