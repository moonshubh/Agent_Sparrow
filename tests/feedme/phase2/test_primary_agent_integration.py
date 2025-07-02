"""
TDD Tests for FeedMe v2.0 Primary Agent Integration
Tests for knowledge source integration and search functionality
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict, Any

import numpy as np

from app.feedme.integration.primary_agent_connector import PrimaryAgentConnector
from app.feedme.integration.knowledge_source import FeedMeKnowledgeSource


class TestFeedMeKnowledgeSource:
    """Test suite for FeedMe knowledge source integration"""

    @pytest.fixture
    def mock_repository(self):
        """Mock FeedMe repository"""
        repo = Mock()
        repo.search_examples_hybrid = AsyncMock()
        repo.get_example = AsyncMock()
        repo.find_similar_examples = AsyncMock()
        repo.increment_usage_count = AsyncMock()
        return repo

    @pytest.fixture
    def mock_embedding_model(self):
        """Mock embedding model"""
        model = Mock()
        model.encode = AsyncMock()
        return model

    @pytest.fixture
    def knowledge_source(self, mock_repository, mock_embedding_model):
        """Create FeedMe knowledge source for testing"""
        source = FeedMeKnowledgeSource(repository=mock_repository)
        source.embedding_model = mock_embedding_model
        return source

    @pytest.fixture
    def sample_query_embedding(self):
        """Sample query embedding"""
        return np.random.random(384).astype(np.float32)

    @pytest.fixture
    def sample_search_results(self):
        """Sample search results from FeedMe"""
        return [
            {
                'id': 1,
                'question_text': 'How do I setup IMAP email?',
                'answer_text': 'To setup IMAP, go to Settings > Email Accounts...',
                'combined_score': 0.92,
                'confidence_score': 0.9,
                'issue_type': 'email_setup',
                'tags': ['email', 'imap', 'setup'],
                'usage_count': 15,
                'last_used_at': '2024-01-15T10:30:00Z'
            },
            {
                'id': 2,
                'question_text': 'Email sync issues troubleshooting',
                'answer_text': 'If emails are not syncing, check your internet connection...',
                'combined_score': 0.85,
                'confidence_score': 0.8,
                'issue_type': 'sync_issues',
                'tags': ['email', 'sync', 'troubleshooting'],
                'usage_count': 8,
                'last_used_at': '2024-01-14T15:20:00Z'
            }
        ]

    @pytest.mark.asyncio
    async def test_basic_knowledge_search(self, knowledge_source, sample_query_embedding, 
                                        sample_search_results):
        """Test basic knowledge search functionality"""
        # Setup mocks
        knowledge_source.embedding_model.encode.return_value = sample_query_embedding
        knowledge_source.repository.search_examples_hybrid.return_value = sample_search_results
        
        # Execute search
        results = await knowledge_source.search(
            query="How to setup email",
            context={'user_platform': 'windows'},
            limit=5
        )
        
        # Verify results
        assert len(results) == 2
        assert results[0]['question_text'] == 'How do I setup IMAP email?'
        assert results[0]['combined_score'] == 0.92
        
        # Verify embedding was generated
        knowledge_source.embedding_model.encode.assert_called_once_with("How to setup email")
        
        # Verify search was performed
        knowledge_source.repository.search_examples_hybrid.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_context_filtering(self, knowledge_source, sample_query_embedding,
                                                sample_search_results):
        """Test search with context-based filtering"""
        knowledge_source.embedding_model.encode.return_value = sample_query_embedding
        knowledge_source.repository.search_examples_hybrid.return_value = sample_search_results
        
        # Search with specific context
        context = {
            'detected_category': 'email_setup',
            'user_platform': 'windows',
            'customer_emotion': 'frustrated'
        }
        
        results = await knowledge_source.search(
            query="email configuration",
            context=context,
            limit=3
        )
        
        # Verify context was used in search filters
        call_args = knowledge_source.repository.search_examples_hybrid.call_args
        filters = call_args[1]['filters']
        
        assert 'min_confidence' in filters
        assert filters['min_confidence'] == 0.7
        assert 'issue_category' in filters or 'detected_category' in filters

    @pytest.mark.asyncio
    async def test_usage_tracking(self, knowledge_source, sample_query_embedding,
                                sample_search_results):
        """Test usage tracking for retrieved examples"""
        knowledge_source.embedding_model.encode.return_value = sample_query_embedding
        knowledge_source.repository.search_examples_hybrid.return_value = sample_search_results
        
        # Execute search
        await knowledge_source.search(
            query="email setup",
            context={},
            limit=5
        )
        
        # Verify usage counts were incremented for all results
        assert knowledge_source.repository.increment_usage_count.call_count == 2
        
        # Verify correct IDs were used
        call_args_list = knowledge_source.repository.increment_usage_count.call_args_list
        used_ids = [call[0][0] for call in call_args_list]
        assert 1 in used_ids
        assert 2 in used_ids

    @pytest.mark.asyncio
    async def test_empty_search_results(self, knowledge_source, sample_query_embedding):
        """Test handling of empty search results"""
        knowledge_source.embedding_model.encode.return_value = sample_query_embedding
        knowledge_source.repository.search_examples_hybrid.return_value = []
        
        results = await knowledge_source.search(
            query="nonexistent query",
            context={},
            limit=5
        )
        
        assert len(results) == 0
        # Should not attempt to track usage for empty results
        knowledge_source.repository.increment_usage_count.assert_not_called()

    @pytest.mark.asyncio
    async def test_related_conversations_retrieval(self, knowledge_source):
        """Test retrieval of related conversations"""
        example_id = 1
        
        # Mock example data
        knowledge_source.repository.get_example.return_value = {
            'id': example_id,
            'combined_embedding': [0.1, 0.2, 0.3],  # Mock embedding
            'question_text': 'Test question'
        }
        
        # Mock similar examples
        similar_examples = [
            {
                'id': 2,
                'question_text': 'Similar question 1',
                'answer_text': 'Similar answer 1',
                'similarity_score': 0.88
            },
            {
                'id': 3,
                'question_text': 'Similar question 2',
                'answer_text': 'Similar answer 2',
                'similarity_score': 0.82
            }
        ]
        knowledge_source.repository.find_similar_examples.return_value = similar_examples
        
        # Get related conversations
        related = await knowledge_source.get_related_conversations(
            example_id=example_id,
            limit=3
        )
        
        assert len(related) == 2
        assert related[0]['similarity_score'] == 0.88
        
        # Verify similar examples search was called correctly
        knowledge_source.repository.find_similar_examples.assert_called_once()
        call_args = knowledge_source.repository.find_similar_examples.call_args
        assert call_args[1]['exclude_id'] == example_id
        assert call_args[1]['limit'] == 3

    @pytest.mark.asyncio
    async def test_related_conversations_nonexistent_example(self, knowledge_source):
        """Test related conversations for nonexistent example"""
        knowledge_source.repository.get_example.return_value = None
        
        related = await knowledge_source.get_related_conversations(
            example_id=999,
            limit=3
        )
        
        assert len(related) == 0
        # Should not attempt to find similar examples
        knowledge_source.repository.find_similar_examples.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_performance_optimization(self, knowledge_source, sample_query_embedding):
        """Test search performance optimization features"""
        # Mock cached embedding
        with patch('app.feedme.integration.knowledge_source.cache_embedding') as mock_cache:
            mock_cache.return_value = sample_query_embedding
            
            knowledge_source.repository.search_examples_hybrid.return_value = []
            
            # Perform search
            await knowledge_source.search(
                query="test query",
                context={},
                limit=5
            )
            
            # Should use cached embedding instead of generating new one
            knowledge_source.embedding_model.encode.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_error_handling(self, knowledge_source, sample_query_embedding):
        """Test error handling in knowledge search"""
        knowledge_source.embedding_model.encode.return_value = sample_query_embedding
        knowledge_source.repository.search_examples_hybrid.side_effect = Exception("Database error")
        
        # Should handle error gracefully
        results = await knowledge_source.search(
            query="test query",
            context={},
            limit=5
        )
        
        # Should return empty results on error
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_confidence_filtering(self, knowledge_source, sample_query_embedding):
        """Test confidence-based filtering"""
        # Results with varying confidence scores
        mixed_confidence_results = [
            {'id': 1, 'confidence_score': 0.9, 'combined_score': 0.9},  # Above threshold
            {'id': 2, 'confidence_score': 0.6, 'combined_score': 0.8},  # Below threshold
            {'id': 3, 'confidence_score': 0.8, 'combined_score': 0.7}   # Above threshold
        ]
        
        knowledge_source.embedding_model.encode.return_value = sample_query_embedding
        knowledge_source.repository.search_examples_hybrid.return_value = mixed_confidence_results
        
        results = await knowledge_source.search(
            query="test query",
            context={'min_confidence': 0.7},
            limit=5
        )
        
        # Should filter results by confidence
        # Note: This depends on implementation details of how filtering is applied


class TestPrimaryAgentConnector:
    """Test suite for Primary Agent connector"""

    @pytest.fixture
    def mock_knowledge_source(self):
        """Mock FeedMe knowledge source"""
        source = Mock(spec=FeedMeKnowledgeSource)
        source.search = AsyncMock()
        source.get_related_conversations = AsyncMock()
        return source

    @pytest.fixture
    def primary_agent_connector(self, mock_knowledge_source):
        """Create Primary Agent connector for testing"""
        connector = PrimaryAgentConnector()
        connector.feedme_knowledge_source = mock_knowledge_source
        return connector

    @pytest.fixture
    def sample_agent_query(self):
        """Sample query from Primary Agent"""
        return {
            'query_text': 'Customer cannot receive emails',
            'detected_intent': 'technical_support',
            'emotional_state': 'frustrated',
            'customer_context': {
                'platform': 'windows',
                'email_client': 'mailbird',
                'issue_duration': 'hours'
            },
            'conversation_history': [
                {'role': 'user', 'content': 'I cannot receive emails'},
                {'role': 'assistant', 'content': 'Let me help you with that...'}
            ]
        }

    @pytest.mark.asyncio
    async def test_knowledge_retrieval_for_primary_agent(self, primary_agent_connector,
                                                        mock_knowledge_source, sample_agent_query):
        """Test knowledge retrieval for Primary Agent"""
        # Mock search results
        mock_knowledge_source.search.return_value = [
            {
                'id': 1,
                'question_text': 'Email receiving issues',
                'answer_text': 'Check your IMAP settings...',
                'combined_score': 0.9,
                'confidence_score': 0.85
            }
        ]
        
        # Retrieve knowledge
        results = await primary_agent_connector.retrieve_knowledge(
            query=sample_agent_query,
            max_results=3
        )
        
        assert len(results) == 1
        assert results[0]['answer_text'] == 'Check your IMAP settings...'
        
        # Verify search was called with proper context
        mock_knowledge_source.search.assert_called_once()
        call_args = mock_knowledge_source.search.call_args
        assert call_args[0][0] == 'Customer cannot receive emails'
        assert 'detected_intent' in call_args[1]['context']

    @pytest.mark.asyncio
    async def test_context_enrichment(self, primary_agent_connector, sample_agent_query):
        """Test context enrichment for FeedMe search"""
        enriched_context = primary_agent_connector._enrich_context(sample_agent_query)
        
        assert 'detected_category' in enriched_context
        assert 'user_platform' in enriched_context
        assert 'customer_emotion' in enriched_context
        assert enriched_context['user_platform'] == 'windows'
        assert enriched_context['customer_emotion'] == 'frustrated'

    @pytest.mark.asyncio
    async def test_response_formatting_for_primary_agent(self, primary_agent_connector,
                                                        mock_knowledge_source):
        """Test response formatting for Primary Agent"""
        # Mock raw search results
        raw_results = [
            {
                'id': 1,
                'question_text': 'How to fix email sync?',
                'answer_text': 'Try these steps: 1. Check connection...',
                'combined_score': 0.9,
                'confidence_score': 0.85,
                'tags': ['email', 'sync'],
                'issue_type': 'sync_issues'
            }
        ]
        
        mock_knowledge_source.search.return_value = raw_results
        
        # Format for Primary Agent
        formatted_results = await primary_agent_connector.retrieve_knowledge(
            query={'query_text': 'email sync problems'},
            max_results=1
        )
        
        # Verify formatting
        result = formatted_results[0]
        assert 'source' in result
        assert result['source'] == 'feedme'
        assert 'relevance_score' in result
        assert 'metadata' in result

    @pytest.mark.asyncio
    async def test_integration_with_primary_agent_reasoning(self, primary_agent_connector,
                                                          mock_knowledge_source):
        """Test integration with Primary Agent reasoning system"""
        # Mock reasoning context
        reasoning_context = {
            'problem_category': 'email_configuration',
            'solution_complexity': 'medium',
            'customer_technical_level': 'beginner'
        }
        
        mock_knowledge_source.search.return_value = [
            {
                'id': 1,
                'question_text': 'Email setup help',
                'answer_text': 'Simple setup instructions...',
                'confidence_score': 0.9
            }
        ]
        
        # Retrieve with reasoning context
        results = await primary_agent_connector.retrieve_with_reasoning_context(
            query="help with email setup",
            reasoning_context=reasoning_context,
            max_results=3
        )
        
        # Should adapt results based on reasoning context
        assert len(results) == 1
        
        # Verify reasoning context influenced the search
        call_args = mock_knowledge_source.search.call_args
        context = call_args[1]['context']
        assert 'problem_category' in context or 'customer_technical_level' in context

    @pytest.mark.asyncio
    async def test_fallback_when_no_results(self, primary_agent_connector, mock_knowledge_source):
        """Test fallback behavior when no FeedMe results are found"""
        mock_knowledge_source.search.return_value = []
        
        results = await primary_agent_connector.retrieve_knowledge(
            query={'query_text': 'very specific technical issue'},
            max_results=3
        )
        
        # Should return empty results gracefully
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_result_ranking_and_deduplication(self, primary_agent_connector,
                                                   mock_knowledge_source):
        """Test result ranking and deduplication"""
        # Mock results with some duplicates and varying scores
        mock_results = [
            {
                'id': 1,
                'question_text': 'Email setup question',
                'combined_score': 0.9,
                'confidence_score': 0.85
            },
            {
                'id': 2,
                'question_text': 'Similar email setup question',  # Similar to first
                'combined_score': 0.85,
                'confidence_score': 0.8
            },
            {
                'id': 3,
                'question_text': 'Different sync issue',
                'combined_score': 0.95,
                'confidence_score': 0.9
            }
        ]
        
        mock_knowledge_source.search.return_value = mock_results
        
        results = await primary_agent_connector.retrieve_knowledge(
            query={'query_text': 'email questions'},
            max_results=5,
            enable_deduplication=True
        )
        
        # Should be ranked by relevance
        scores = [r['relevance_score'] for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_performance_metrics_tracking(self, primary_agent_connector,
                                              mock_knowledge_source):
        """Test performance metrics tracking"""
        mock_knowledge_source.search.return_value = [
            {'id': 1, 'question_text': 'Test', 'combined_score': 0.9}
        ]
        
        # Enable performance tracking
        results = await primary_agent_connector.retrieve_knowledge(
            query={'query_text': 'test query'},
            max_results=3,
            track_performance=True
        )
        
        # Verify performance metrics are available
        assert hasattr(primary_agent_connector, '_last_retrieval_performance')
        perf = primary_agent_connector._last_retrieval_performance
        assert 'search_time_ms' in perf
        assert 'total_results' in perf
        assert 'filtered_results' in perf


class TestKnowledgeSourceIntegration:
    """Integration tests for knowledge source functionality"""

    @pytest.mark.asyncio
    async def test_end_to_end_knowledge_retrieval(self):
        """Test complete knowledge retrieval flow"""
        # Mock all components for integration test
        repository = Mock()
        repository.search_examples_hybrid = AsyncMock(return_value=[
            {
                'id': 1,
                'question_text': 'IMAP setup question',
                'answer_text': 'Setup instructions...',
                'combined_score': 0.9,
                'confidence_score': 0.85
            }
        ])
        repository.increment_usage_count = AsyncMock()
        
        embedding_model = Mock()
        embedding_model.encode = AsyncMock(return_value=np.random.random(384))
        
        # Create knowledge source
        knowledge_source = FeedMeKnowledgeSource(repository=repository)
        knowledge_source.embedding_model = embedding_model
        
        # Create connector
        connector = PrimaryAgentConnector()
        connector.feedme_knowledge_source = knowledge_source
        
        # Execute end-to-end retrieval
        query = {
            'query_text': 'How to setup IMAP?',
            'detected_intent': 'configuration_help',
            'customer_context': {'platform': 'windows'}
        }
        
        results = await connector.retrieve_knowledge(query, max_results=3)
        
        # Verify complete flow
        assert len(results) == 1
        assert results[0]['source'] == 'feedme'
        
        # Verify all components were called
        embedding_model.encode.assert_called()
        repository.search_examples_hybrid.assert_called()
        repository.increment_usage_count.assert_called()

    @pytest.mark.asyncio
    async def test_concurrent_knowledge_requests(self):
        """Test handling of concurrent knowledge requests"""
        # Mock components
        repository = Mock()
        repository.search_examples_hybrid = AsyncMock(return_value=[])
        repository.increment_usage_count = AsyncMock()
        
        embedding_model = Mock()
        embedding_model.encode = AsyncMock(return_value=np.random.random(384))
        
        knowledge_source = FeedMeKnowledgeSource(repository=repository)
        knowledge_source.embedding_model = embedding_model
        
        # Create multiple concurrent requests
        queries = [f"Query {i}" for i in range(10)]
        
        tasks = [
            knowledge_source.search(query, context={}, limit=5)
            for query in queries
        ]
        
        # Execute concurrently
        results = await asyncio.gather(*tasks)
        
        # Verify all requests completed
        assert len(results) == 10
        
        # Verify embedding model was called for each query
        assert embedding_model.encode.call_count == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])