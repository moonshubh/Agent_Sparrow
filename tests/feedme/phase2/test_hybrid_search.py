"""
TDD Tests for FeedMe v2.0 Hybrid Search System
Tests for vector similarity search, full-text search, and combined scoring
"""

import pytest
from unittest.mock import Mock, patch
from typing import List, Dict, Any

import numpy as np

from app.feedme.search.hybrid_search_engine import HybridSearchEngine
from app.feedme.search.vector_search import VectorSearchEngine
from app.feedme.search.text_search import TextSearchEngine


class TestHybridSearchEngine:
    """Test suite for hybrid search engine"""

    @pytest.fixture
    def mock_vector_engine(self):
        """Mock vector search engine"""
        engine = Mock(spec=VectorSearchEngine)
        engine.search = Mock()
        return engine

    @pytest.fixture
    def mock_text_engine(self):
        """Mock text search engine"""
        engine = Mock(spec=TextSearchEngine)
        engine.search = Mock()
        return engine

    @pytest.fixture
    def hybrid_engine(self, mock_vector_engine, mock_text_engine):
        """Create hybrid search engine for testing"""
        engine = HybridSearchEngine()
        engine.vector_engine = mock_vector_engine
        engine.text_engine = mock_text_engine
        return engine

    @pytest.fixture
    def sample_query_embedding(self):
        """Sample query embedding"""
        return np.random.random(384).astype(np.float32)

    @pytest.fixture
    def sample_vector_results(self):
        """Sample vector search results"""
        return [
            {
                'id': 1,
                'question_text': 'How to setup IMAP?',
                'answer_text': 'Go to Settings > Email Accounts...',
                'vector_score': 0.92,
                'confidence_score': 0.9
            },
            {
                'id': 2,
                'question_text': 'Email sync issues',
                'answer_text': 'Check your internet connection...',
                'vector_score': 0.85,
                'confidence_score': 0.8
            }
        ]

    @pytest.fixture
    def sample_text_results(self):
        """Sample text search results"""
        return [
            {
                'id': 1,
                'question_text': 'How to setup IMAP?',
                'answer_text': 'Go to Settings > Email Accounts...',
                'text_score': 0.78,
                'rank': 1
            },
            {
                'id': 3,
                'question_text': 'IMAP configuration problems',
                'answer_text': 'Make sure your server settings are correct...',
                'text_score': 0.72,
                'rank': 2
            }
        ]

    def test_basic_hybrid_search(self, hybrid_engine, sample_query_embedding, 
                                sample_vector_results, sample_text_results):
        """Test basic hybrid search functionality"""
        # Setup mock responses
        hybrid_engine.vector_engine.search.return_value = sample_vector_results
        hybrid_engine.text_engine.search.return_value = sample_text_results
        
        # Execute hybrid search
        results = hybrid_engine.search(
            query="IMAP setup",
            query_embedding=sample_query_embedding,
            limit=5
        )
        
        # Verify results
        assert len(results) > 0
        assert 'combined_score' in results[0]
        assert 'question_text' in results[0]
        
        # Verify both engines were called
        hybrid_engine.vector_engine.search.assert_called_once()
        hybrid_engine.text_engine.search.assert_called_once()

    def test_score_combination_algorithm(self, hybrid_engine, sample_query_embedding,
                                       sample_vector_results, sample_text_results):
        """Test score combination algorithm"""
        hybrid_engine.vector_engine.search.return_value = sample_vector_results
        hybrid_engine.text_engine.search.return_value = sample_text_results
        
        # Set specific weights
        hybrid_engine.vector_weight = 0.7
        hybrid_engine.text_weight = 0.3
        
        results = hybrid_engine.search(
            query="IMAP setup",
            query_embedding=sample_query_embedding,
            limit=5
        )
        
        # Verify score combination for matching items (id=1)
        matching_result = next(r for r in results if r['id'] == 1)
        expected_score = 0.92 * 0.7 + 0.78 * 0.3  # vector * 0.7 + text * 0.3
        assert abs(matching_result['combined_score'] - expected_score) < 0.01

    def test_result_deduplication(self, hybrid_engine, sample_query_embedding,
                                 sample_vector_results, sample_text_results):
        """Test deduplication of results from both engines"""
        hybrid_engine.vector_engine.search.return_value = sample_vector_results
        hybrid_engine.text_engine.search.return_value = sample_text_results
        
        results = hybrid_engine.search(
            query="IMAP setup",
            query_embedding=sample_query_embedding,
            limit=5
        )
        
        # Should have 3 unique results (2 from vector + 1 unique from text)
        result_ids = [r['id'] for r in results]
        assert len(result_ids) == len(set(result_ids))  # No duplicates
        assert 1 in result_ids  # ID 1 should be present (from both searches)
        assert 2 in result_ids  # ID 2 should be present (vector only)
        assert 3 in result_ids  # ID 3 should be present (text only)

    def test_empty_vector_results(self, hybrid_engine, sample_query_embedding,
                                 sample_text_results):
        """Test hybrid search when vector search returns no results"""
        hybrid_engine.vector_engine.search.return_value = []
        hybrid_engine.text_engine.search.return_value = sample_text_results
        
        results = hybrid_engine.search(
            query="test query",
            query_embedding=sample_query_embedding,
            limit=5
        )
        
        # Should still return text results
        assert len(results) == len(sample_text_results)
        for result in results:
            assert 'text_score' in result
            assert result.get('vector_score') == 0.0  # Default for missing vector score

    def test_empty_text_results(self, hybrid_engine, sample_query_embedding,
                               sample_vector_results):
        """Test hybrid search when text search returns no results"""
        hybrid_engine.vector_engine.search.return_value = sample_vector_results
        hybrid_engine.text_engine.search.return_value = []
        
        results = hybrid_engine.search(
            query="test query",
            query_embedding=sample_query_embedding,
            limit=5
        )
        
        # Should still return vector results
        assert len(results) == len(sample_vector_results)
        for result in results:
            assert 'vector_score' in result
            assert result.get('text_score') == 0.0  # Default for missing text score

    def test_search_filters(self, hybrid_engine, sample_query_embedding):
        """Test search with filters"""
        # Mock filtered results
        filtered_vector_results = [
            {
                'id': 1,
                'question_text': 'How to setup IMAP?',
                'issue_category': 'email_setup',
                'vector_score': 0.92
            }
        ]
        
        hybrid_engine.vector_engine.search.return_value = filtered_vector_results
        hybrid_engine.text_engine.search.return_value = []
        
        results = hybrid_engine.search(
            query="IMAP setup",
            query_embedding=sample_query_embedding,
            filters={'issue_category': 'email_setup'},
            limit=5
        )
        
        # Verify filters were passed to both engines
        vector_call_args = hybrid_engine.vector_engine.search.call_args
        text_call_args = hybrid_engine.text_engine.search.call_args
        
        # Check that issue_category filter was passed (along with automatically added min_confidence)
        assert vector_call_args[1]['filters']['issue_category'] == 'email_setup'
        assert text_call_args[1]['filters']['issue_category'] == 'email_setup'
        assert 'min_confidence' in vector_call_args[1]['filters']
        assert 'min_confidence' in text_call_args[1]['filters']

    def test_confidence_threshold_filtering(self, hybrid_engine, sample_query_embedding):
        """Test filtering by confidence threshold"""
        # Results with varying confidence scores
        mixed_confidence_results = [
            {'id': 1, 'vector_score': 0.9, 'confidence_score': 0.8},  # Above threshold
            {'id': 2, 'vector_score': 0.8, 'confidence_score': 0.6},  # Below threshold
            {'id': 3, 'vector_score': 0.7, 'confidence_score': 0.9},  # Above threshold
        ]
        
        hybrid_engine.vector_engine.search.return_value = mixed_confidence_results
        hybrid_engine.text_engine.search.return_value = []
        
        results = hybrid_engine.search(
            query="test query",
            query_embedding=sample_query_embedding,
            min_confidence=0.7,
            limit=5
        )
        
        # Verify the min_confidence filter was passed to the engines
        vector_call_args = hybrid_engine.vector_engine.search.call_args
        text_call_args = hybrid_engine.text_engine.search.call_args
        
        assert vector_call_args[1]['filters']['min_confidence'] == 0.7
        assert text_call_args[1]['filters']['min_confidence'] == 0.7
        
        # Since we mocked the vector engine to return all results, 
        # actual filtering would happen at the database level
        assert len(results) == len(mixed_confidence_results)

    def test_search_performance_tracking(self, hybrid_engine, sample_query_embedding,
                                        sample_vector_results, sample_text_results):
        """Test search performance tracking"""
        hybrid_engine.vector_engine.search.return_value = sample_vector_results
        hybrid_engine.text_engine.search.return_value = sample_text_results
        
        # Enable performance tracking
        results = hybrid_engine.search(
            query="test query",
            query_embedding=sample_query_embedding,
            limit=5,
            track_performance=True
        )
        
        # Verify performance metadata is included
        assert hasattr(hybrid_engine, '_last_search_performance')
        perf = hybrid_engine._last_search_performance
        assert 'total_time_ms' in perf
        assert 'vector_search_time_ms' in perf
        assert 'text_search_time_ms' in perf
        assert 'combination_time_ms' in perf

    def test_error_handling_vector_search_failure(self, hybrid_engine, sample_query_embedding,
                                                  sample_text_results):
        """Test error handling when vector search fails"""
        hybrid_engine.vector_engine.search.side_effect = Exception("Vector search failed")
        hybrid_engine.text_engine.search.return_value = sample_text_results
        
        # Should gracefully handle vector search failure and return text results
        results = hybrid_engine.search(
            query="test query",
            query_embedding=sample_query_embedding,
            limit=5
        )
        
        assert len(results) == len(sample_text_results)
        # Should log the error but continue with text search

    def test_error_handling_text_search_failure(self, hybrid_engine, sample_query_embedding,
                                               sample_vector_results):
        """Test error handling when text search fails"""
        hybrid_engine.vector_engine.search.return_value = sample_vector_results
        hybrid_engine.text_engine.search.side_effect = Exception("Text search failed")
        
        # Should gracefully handle text search failure and return vector results
        results = hybrid_engine.search(
            query="test query",
            query_embedding=sample_query_embedding,
            limit=5
        )
        
        assert len(results) == len(sample_vector_results)

    def test_search_result_ranking(self, hybrid_engine, sample_query_embedding):
        """Test proper ranking of combined search results"""
        # Create results with known scores for testing ranking
        vector_results = [
            {'id': 1, 'vector_score': 0.9, 'question_text': 'High vector score'},
            {'id': 2, 'vector_score': 0.7, 'question_text': 'Medium vector score'}
        ]
        
        text_results = [
            {'id': 3, 'text_score': 0.95, 'question_text': 'High text score'},
            {'id': 1, 'text_score': 0.6, 'question_text': 'High vector score'}  # Same as vector result
        ]
        
        hybrid_engine.vector_engine.search.return_value = vector_results
        hybrid_engine.text_engine.search.return_value = text_results
        hybrid_engine.vector_weight = 0.5
        hybrid_engine.text_weight = 0.5
        
        results = hybrid_engine.search(
            query="test query",
            query_embedding=sample_query_embedding,
            limit=5
        )
        
        # Verify results are sorted by combined score (descending)
        scores = [r['combined_score'] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_weight_validation(self, hybrid_engine):
        """Test validation of search weights"""
        # Test invalid weights using update_weights method
        with pytest.raises(ValueError):
            hybrid_engine.update_weights(1.5, 0.3)  # vector_weight > 1.0
        
        with pytest.raises(ValueError):
            hybrid_engine.update_weights(0.7, -0.1)  # text_weight < 0.0
        
        with pytest.raises(ValueError):
            hybrid_engine.update_weights(0.8, 0.8)  # Sum > 1.0
        
        # Test valid weights
        hybrid_engine.update_weights(0.6, 0.4)
        assert hybrid_engine.vector_weight == 0.6
        assert hybrid_engine.text_weight == 0.4


class TestVectorSearchEngine:
    """Test suite for vector search engine"""

    @pytest.fixture
    def vector_engine(self):
        """Create vector search engine for testing"""
        engine = VectorSearchEngine()
        engine.connection_manager = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        engine.connection_manager.get_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        engine.connection_manager.get_connection.return_value.__exit__ = Mock(return_value=None)
        return engine, mock_conn, mock_cursor

    @pytest.fixture
    def sample_embedding(self):
        """Sample embedding for testing"""
        return np.random.random(384).astype(np.float32)

    def test_basic_vector_search(self, vector_engine, sample_embedding):
        """Test basic vector similarity search"""
        engine, mock_conn, mock_cursor = vector_engine
        # Mock database results
        mock_cursor.fetchall.return_value = [
            {
                'id': 1,
                'question_text': 'Test question',
                'answer_text': 'Test answer',
                'vector_score': 0.92
            }
        ]
        
        results = engine.search(
            embedding=sample_embedding,
            limit=5
        )
        
        assert len(results) == 1
        assert results[0]['vector_score'] == 0.92
        
        # Verify SQL query uses pgvector cosine distance operator
        call_args = mock_cursor.execute.call_args
        sql_query = str(call_args[0][0])
        assert '<=>' in sql_query  # pgvector cosine distance operator

    def test_vector_search_with_filters(self, vector_engine, sample_embedding):
        """Test vector search with filters"""
        engine, mock_conn, mock_cursor = vector_engine
        mock_cursor.fetchall.return_value = []
        
        engine.search(
            embedding=sample_embedding,
            filters={'issue_category': 'email_setup'},
            limit=5
        )
        
        # Verify filters are included in query
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        assert 'issue_category' in params

    def test_embedding_dimension_validation(self, vector_engine):
        """Test embedding dimension validation"""
        engine, mock_conn, mock_cursor = vector_engine
        wrong_dimension = np.random.random(512).astype(np.float32)
        
        with pytest.raises(ValueError, match="Expected embedding dimension"):
            engine.search(embedding=wrong_dimension, limit=5)


class TestTextSearchEngine:
    """Test suite for text search engine"""

    @pytest.fixture
    def text_engine(self):
        """Create text search engine for testing"""
        engine = TextSearchEngine()
        engine.connection_manager = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        engine.connection_manager.get_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        engine.connection_manager.get_connection.return_value.__exit__ = Mock(return_value=None)
        return engine, mock_conn, mock_cursor

    def test_basic_text_search(self, text_engine):
        """Test basic full-text search"""
        engine, mock_conn, mock_cursor = text_engine
        # Mock database results
        mock_cursor.fetchall.return_value = [
            {
                'id': 1,
                'question_text': 'Email setup question',
                'answer_text': 'Setup instructions',
                'text_score': 0.85
            }
        ]
        
        results = engine.search(
            query="email setup",
            limit=5
        )
        
        assert len(results) == 1
        assert results[0]['text_score'] == 0.85
        
        # Verify text search query
        call_args = mock_cursor.execute.call_args
        sql_query = str(call_args[0][0])
        assert 'ts_rank' in sql_query
        assert 'plainto_tsquery' in sql_query

    def test_text_search_with_stemming(self, text_engine):
        """Test text search with stemming"""
        engine, mock_conn, mock_cursor = text_engine
        mock_cursor.fetchall.return_value = []
        
        engine.search(
            query="emails setting up",  # Should match "email setup"
            limit=5,
            enable_stemming=True
        )
        
        # Verify stemming is enabled in query
        call_args = mock_cursor.execute.call_args
        sql_query = str(call_args[0][0])
        assert 'to_tsquery' in sql_query  # More advanced query for stemming

    def test_text_search_ranking(self, text_engine):
        """Test text search ranking"""
        engine, mock_conn, mock_cursor = text_engine
        results_with_ranks = [
            {'id': 1, 'text_score': 0.9, 'rank': 1},
            {'id': 2, 'text_score': 0.7, 'rank': 2},
            {'id': 3, 'text_score': 0.5, 'rank': 3}
        ]
        
        mock_cursor.fetchall.return_value = results_with_ranks
        
        results = engine.search(
            query="test query",
            limit=5
        )
        
        # Verify results are properly ranked
        scores = [r['text_score'] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_query_validation(self, text_engine):
        """Test query validation"""
        engine, mock_conn, mock_cursor = text_engine
        with pytest.raises(ValueError):
            engine.search(query="", limit=5)  # Empty query
        
        with pytest.raises(ValueError):
            engine.search(query="a", limit=5)  # Too short


if __name__ == "__main__":
    pytest.main([__file__, "-v"])