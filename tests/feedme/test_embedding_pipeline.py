"""
Test suite for FeedMe Embedding Pipeline
Tests for multi-faceted embedding generation and optimization
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch, AsyncMock
from typing import List, Dict, Any

from app.feedme.embeddings.embedding_pipeline import FeedMeEmbeddingPipeline
from app.feedme.schemas import FeedMeExample


@pytest.fixture
def embedding_pipeline():
    """Create test embedding pipeline"""
    with patch('app.feedme.embeddings.embedding_pipeline.SentenceTransformer') as mock_transformer:
        mock_model = Mock()
        mock_model.encode.return_value = np.random.rand(384)  # Mock 384-dim embedding
        mock_transformer.return_value = mock_model
        
        pipeline = FeedMeEmbeddingPipeline()
        pipeline.model = mock_model
        return pipeline


@pytest.fixture
def sample_qa_pairs():
    """Sample Q&A pairs for testing"""
    return [
        {
            'id': 1,
            'question_text': 'How do I set up IMAP email in Mailbird?',
            'answer_text': 'To set up IMAP: 1. Go to Settings 2. Add Account 3. Enter server details 4. Use SSL port 993',
            'context_before': 'Customer is having trouble with email setup',
            'context_after': 'Customer confirmed it worked',
            'tags': ['imap', 'email-setup', 'configuration'],
            'confidence_score': 0.9
        },
        {
            'id': 2,
            'question_text': 'Why is my email not syncing?',
            'answer_text': 'Email sync issues can be caused by: 1. Network problems 2. Server settings 3. Authentication errors',
            'context_before': 'Previous conversation about email problems',
            'context_after': 'Escalated to technical team',
            'tags': ['sync', 'troubleshooting', 'email'],
            'confidence_score': 0.8
        }
    ]


class TestFeedMeEmbeddingPipeline:
    """Test cases for the embedding pipeline"""

    def test_pipeline_initialization(self, embedding_pipeline):
        """Test pipeline initializes correctly"""
        assert embedding_pipeline is not None
        assert embedding_pipeline.dimension == 384
        assert hasattr(embedding_pipeline, 'model')

    @pytest.mark.asyncio
    async def test_generate_embeddings(self, embedding_pipeline, sample_qa_pairs):
        """Test embedding generation for Q&A pairs"""
        result = await embedding_pipeline.generate_embeddings(sample_qa_pairs)
        
        assert len(result) == 2
        
        # Check first pair has all embedding types
        first_pair = result[0]
        assert 'question_embedding' in first_pair
        assert 'answer_embedding' in first_pair
        assert 'combined_embedding' in first_pair
        
        # Check embedding dimensions
        assert len(first_pair['question_embedding']) == 384
        assert len(first_pair['answer_embedding']) == 384
        assert len(first_pair['combined_embedding']) == 384
        
        # Verify model was called for each embedding type
        assert embedding_pipeline.model.encode.call_count >= 6  # 3 types × 2 pairs

    @pytest.mark.asyncio
    async def test_combined_embedding_format(self, embedding_pipeline, sample_qa_pairs):
        """Test combined embedding includes all context"""
        result = await embedding_pipeline.generate_embeddings(sample_qa_pairs)
        
        # Verify the model was called with combined text format
        call_args = embedding_pipeline.model.encode.call_args_list
        
        # Find combined embedding calls (should include context)
        combined_calls = [call for call in call_args if 'Question:' in str(call[0][0])]
        assert len(combined_calls) >= 2
        
        # Check format includes all components
        combined_text = combined_calls[0][0][0]
        assert 'Question:' in combined_text
        assert 'Context:' in combined_text
        assert 'Answer:' in combined_text
        assert 'Resolution:' in combined_text

    @pytest.mark.asyncio
    async def test_embedding_normalization(self, embedding_pipeline, sample_qa_pairs):
        """Test embeddings are normalized"""
        # Mock normalized embeddings
        normalized_embedding = np.random.rand(384)
        normalized_embedding = normalized_embedding / np.linalg.norm(normalized_embedding)
        embedding_pipeline.model.encode.return_value = normalized_embedding
        
        result = await embedding_pipeline.generate_embeddings(sample_qa_pairs)
        
        # Verify normalize_embeddings=True was passed
        call_args = embedding_pipeline.model.encode.call_args_list
        for call in call_args:
            assert call[1]['normalize_embeddings'] is True

    @pytest.mark.asyncio
    async def test_batch_processing(self, embedding_pipeline):
        """Test efficient batch processing of multiple Q&A pairs"""
        # Create larger batch
        large_batch = []
        for i in range(50):
            large_batch.append({
                'id': i,
                'question_text': f'Question {i}',
                'answer_text': f'Answer {i}',
                'context_before': f'Context before {i}',
                'context_after': f'Context after {i}'
            })
        
        result = await embedding_pipeline.generate_embeddings(large_batch)
        
        assert len(result) == 50
        # Each item should have all embedding types
        for item in result:
            assert 'question_embedding' in item
            assert 'answer_embedding' in item
            assert 'combined_embedding' in item

    @pytest.mark.asyncio
    async def test_empty_context_handling(self, embedding_pipeline):
        """Test handling of Q&A pairs with missing context"""
        qa_pairs = [{
            'id': 1,
            'question_text': 'Test question',
            'answer_text': 'Test answer',
            'context_before': None,
            'context_after': ''
        }]
        
        result = await embedding_pipeline.generate_embeddings(qa_pairs)
        
        assert len(result) == 1
        assert 'combined_embedding' in result[0]
        
        # Should handle None/empty context gracefully
        call_args = embedding_pipeline.model.encode.call_args_list
        combined_call = [call for call in call_args if 'Question:' in str(call[0][0])][0]
        combined_text = combined_call[0][0]
        
        # Should not include 'None' in text
        assert 'None' not in combined_text

    def test_embedding_dimension_validation(self):
        """Test validation of embedding dimensions"""
        with patch('app.feedme.embeddings.embedding_pipeline.SentenceTransformer') as mock_transformer:
            mock_model = Mock()
            # Return wrong dimension
            mock_model.encode.return_value = np.random.rand(256)  # Wrong dimension
            mock_transformer.return_value = mock_model
            
            pipeline = FeedMeEmbeddingPipeline()
            pipeline.model = mock_model
            
            # Should validate and potentially raise error or adjust
            assert pipeline.dimension == 384  # Expected dimension


class TestEmbeddingOptimization:
    """Test embedding optimization features"""

    @pytest.mark.asyncio
    async def test_embedding_caching(self, embedding_pipeline, sample_qa_pairs):
        """Test caching of embeddings for identical content"""
        # Mock Redis cache
        with patch('app.feedme.embeddings.embedding_pipeline.redis_client') as mock_redis:
            mock_redis.get.return_value = None  # Cache miss first time
            mock_redis.setex.return_value = True  # Cache set success
            
            # First call should generate embeddings
            result1 = await embedding_pipeline.generate_embeddings(sample_qa_pairs)
            
            # Mock cache hit for second call
            cached_embedding = np.random.rand(384).tolist()
            mock_redis.get.return_value = cached_embedding
            
            result2 = await embedding_pipeline.generate_embeddings(sample_qa_pairs)
            
            # Should have called cache operations
            assert mock_redis.get.called
            assert mock_redis.setex.called

    @pytest.mark.asyncio
    async def test_embedding_quality_scoring(self, embedding_pipeline, sample_qa_pairs):
        """Test quality scoring based on embedding characteristics"""
        # Add quality scoring to pipeline
        embedding_pipeline.enable_quality_scoring = True
        
        result = await embedding_pipeline.generate_embeddings(sample_qa_pairs)
        
        for pair in result:
            # Should add quality scores based on embedding analysis
            assert 'embedding_quality_score' in pair
            assert 0.0 <= pair['embedding_quality_score'] <= 1.0

    @pytest.mark.asyncio
    async def test_similarity_preprocessing(self, embedding_pipeline, sample_qa_pairs):
        """Test preprocessing for similarity search optimization"""
        result = await embedding_pipeline.generate_embeddings(sample_qa_pairs)
        
        # Should optimize embeddings for similarity search
        for pair in result:
            # Check embeddings are unit vectors (normalized)
            question_norm = np.linalg.norm(pair['question_embedding'])
            answer_norm = np.linalg.norm(pair['answer_embedding'])
            combined_norm = np.linalg.norm(pair['combined_embedding'])
            
            # Should be close to 1.0 (normalized)
            assert abs(question_norm - 1.0) < 0.1
            assert abs(answer_norm - 1.0) < 0.1
            assert abs(combined_norm - 1.0) < 0.1


class TestModelIntegration:
    """Test integration with different embedding models"""

    def test_alternative_model_initialization(self):
        """Test initialization with alternative embedding models"""
        with patch('app.feedme.embeddings.embedding_pipeline.SentenceTransformer') as mock_transformer:
            # Test with different model
            pipeline = FeedMeEmbeddingPipeline(model_name='all-mpnet-base-v2')
            
            mock_transformer.assert_called_with('all-mpnet-base-v2')

    @pytest.mark.asyncio
    async def test_model_error_handling(self, embedding_pipeline, sample_qa_pairs):
        """Test handling of model errors during embedding generation"""
        # Mock model error
        embedding_pipeline.model.encode.side_effect = Exception("Model error")
        
        # Should handle gracefully
        result = await embedding_pipeline.generate_embeddings(sample_qa_pairs)
        
        # Should return original pairs without embeddings or empty list
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_model_performance_monitoring(self, embedding_pipeline, sample_qa_pairs):
        """Test performance monitoring during embedding generation"""
        with patch('app.feedme.embeddings.embedding_pipeline.time') as mock_time:
            mock_time.time.side_effect = [0, 1, 2, 3]  # Mock time progression
            
            result = await embedding_pipeline.generate_embeddings(sample_qa_pairs)
            
            # Should have timing information
            assert 'processing_time' in result[0] or hasattr(embedding_pipeline, 'last_processing_time')


class TestSpecializedEmbeddings:
    """Test specialized embedding types and features"""

    @pytest.mark.asyncio
    async def test_semantic_embeddings(self, embedding_pipeline, sample_qa_pairs):
        """Test semantic-focused embeddings for better search"""
        # Enable semantic optimization
        embedding_pipeline.enable_semantic_optimization = True
        
        result = await embedding_pipeline.generate_embeddings(sample_qa_pairs)
        
        # Should generate semantic-optimized embeddings
        for pair in result:
            assert 'semantic_embedding' in pair
            assert len(pair['semantic_embedding']) == 384

    @pytest.mark.asyncio
    async def test_domain_specific_embeddings(self, embedding_pipeline, sample_qa_pairs):
        """Test domain-specific embeddings for support conversations"""
        # Configure for support domain
        embedding_pipeline.domain = 'customer_support'
        
        result = await embedding_pipeline.generate_embeddings(sample_qa_pairs)
        
        # Should apply domain-specific processing
        for pair in result:
            # Check for domain-specific preprocessing
            assert 'domain_processed' in pair.get('metadata', {})

    @pytest.mark.asyncio
    async def test_multilingual_embeddings(self, embedding_pipeline):
        """Test embedding generation for non-English content"""
        multilingual_pairs = [
            {
                'id': 1,
                'question_text': '¿Cómo configuro mi correo IMAP?',
                'answer_text': 'Para configurar IMAP: 1. Vaya a Configuración 2. Agregue cuenta',
                'metadata': {'language': 'es'}
            },
            {
                'id': 2,
                'question_text': 'Comment configurer IMAP?',
                'answer_text': 'Pour configurer IMAP: 1. Allez dans Paramètres 2. Ajoutez un compte',
                'metadata': {'language': 'fr'}
            }
        ]
        
        result = await embedding_pipeline.generate_embeddings(multilingual_pairs)
        
        assert len(result) == 2
        # Should handle different languages
        for pair in result:
            assert 'question_embedding' in pair
            assert 'answer_embedding' in pair


if __name__ == "__main__":
    pytest.main([__file__])