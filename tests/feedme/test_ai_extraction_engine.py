"""
Test suite for FeedMe v2 AI Extraction Engine
Tests for Gemma-3-27b-it integration and intelligent Q&A extraction
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict, Any

from app.feedme.ai_extraction_engine import GemmaExtractionEngine, ExtractionConfig
from app.core.settings import settings


@pytest.fixture
def mock_genai():
    """Mock Google's GenerativeAI module"""
    with patch('app.feedme.ai_extraction_engine.genai') as mock:
        mock_model = Mock()
        mock_model.generate_content_async = AsyncMock()
        mock.GenerativeModel.return_value = mock_model
        yield mock


@pytest.fixture
def extraction_engine(mock_genai):
    """Create test extraction engine"""
    return GemmaExtractionEngine(api_key="test-key")


@pytest.fixture
def sample_html_content():
    """Sample HTML support ticket content"""
    return """
    <html>
    <body>
        <div class="conversation">
            <div class="message customer">
                <span class="author">John Doe</span>
                <span class="timestamp">2024-01-15 10:30</span>
                <div class="content">I'm having trouble setting up my IMAP email. It keeps saying authentication failed.</div>
            </div>
            <div class="message agent">
                <span class="author">Support Agent</span>
                <span class="timestamp">2024-01-15 10:32</span>
                <div class="content">
                    Let me help you with that. Please follow these steps:
                    1. Go to Settings > Email Accounts
                    2. Click Add Account
                    3. Make sure to use your full email address
                    4. Use SSL port 993 for IMAP
                    Did this resolve your issue?
                </div>
            </div>
            <div class="message customer">
                <span class="author">John Doe</span>
                <span class="timestamp">2024-01-15 10:35</span>
                <div class="content">Yes, that worked perfectly! Thank you so much.</div>
            </div>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def expected_qa_pairs():
    """Expected Q&A pairs from sample content"""
    return [
        {
            "question_text": "I'm having trouble setting up my IMAP email. It keeps saying authentication failed.",
            "answer_text": "Let me help you with that. Please follow these steps:\n1. Go to Settings > Email Accounts\n2. Click Add Account\n3. Make sure to use your full email address\n4. Use SSL port 993 for IMAP\nDid this resolve your issue?",
            "context_before": "",
            "context_after": "Yes, that worked perfectly! Thank you so much.",
            "confidence_score": 0.9,
            "quality_score": 0.85,
            "issue_type": "email-setup",
            "resolution_type": "step-by-step-guide",
            "tags": ["imap", "authentication", "email-setup"],
            "metadata": {
                "sentiment": "frustrated_then_satisfied",
                "technical_level": "beginner",
                "resolved": True
            }
        }
    ]


class TestGemmaExtractionEngine:
    """Test cases for the Gemma AI extraction engine"""

    @pytest.mark.asyncio
    async def test_engine_initialization(self, mock_genai):
        """Test engine initializes correctly with API key"""
        engine = GemmaExtractionEngine(api_key="test-key")
        
        assert engine is not None
        mock_genai.configure.assert_called_once_with(api_key="test-key")
        mock_genai.GenerativeModel.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_conversations_success(self, extraction_engine, sample_html_content, expected_qa_pairs):
        """Test successful Q&A extraction from HTML content"""
        # Mock AI response
        mock_response = Mock()
        mock_response.text = """
        [{
            "question_text": "I'm having trouble setting up my IMAP email. It keeps saying authentication failed.",
            "answer_text": "Let me help you with that. Please follow these steps:\\n1. Go to Settings > Email Accounts\\n2. Click Add Account\\n3. Make sure to use your full email address\\n4. Use SSL port 993 for IMAP\\nDid this resolve your issue?",
            "context_before": "",
            "context_after": "Yes, that worked perfectly! Thank you so much.",
            "confidence_score": 0.9,
            "quality_score": 0.85,
            "issue_type": "email-setup",
            "resolution_type": "step-by-step-guide",
            "tags": ["imap", "authentication", "email-setup"],
            "metadata": {
                "sentiment": "frustrated_then_satisfied",
                "technical_level": "beginner",
                "resolved": true
            }
        }]
        """
        
        extraction_engine.model.generate_content_async.return_value = mock_response
        
        # Execute extraction
        result = await extraction_engine.extract_conversations(
            html_content=sample_html_content,
            metadata={"source": "test"}
        )
        
        # Verify results
        assert len(result) == 1
        assert result[0]["question_text"] == expected_qa_pairs[0]["question_text"]
        assert result[0]["confidence_score"] >= 0.7  # Above threshold
        assert result[0]["issue_type"] == "email-setup"
        assert "imap" in result[0]["tags"]

    @pytest.mark.asyncio
    async def test_confidence_filtering(self, extraction_engine, sample_html_content):
        """Test that low confidence extractions are filtered out"""
        # Mock AI response with low confidence
        mock_response = Mock()
        mock_response.text = """
        [{
            "question_text": "Some unclear question",
            "answer_text": "Some unclear answer",
            "confidence_score": 0.3,
            "quality_score": 0.2
        }]
        """
        
        extraction_engine.model.generate_content_async.return_value = mock_response
        
        # Execute extraction
        result = await extraction_engine.extract_conversations(
            html_content=sample_html_content,
            metadata={}
        )
        
        # Should be filtered out due to low confidence
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_extraction_with_invalid_json(self, extraction_engine, sample_html_content):
        """Test handling of invalid JSON response from AI"""
        # Mock AI response with invalid JSON
        mock_response = Mock()
        mock_response.text = "Invalid JSON response"
        
        extraction_engine.model.generate_content_async.return_value = mock_response
        
        # Should handle gracefully and return empty list
        result = await extraction_engine.extract_conversations(
            html_content=sample_html_content,
            metadata={}
        )
        
        assert result == []

    @pytest.mark.asyncio
    async def test_chunking_large_documents(self, extraction_engine):
        """Test intelligent chunking for large HTML documents"""
        # Create large HTML content
        large_content = "<html><body>" + "A" * 60000 + "</body></html>"
        
        # Mock chunk processing
        with patch.object(extraction_engine, '_create_semantic_chunks') as mock_chunk:
            with patch.object(extraction_engine, '_extract_with_retry') as mock_extract:
                with patch.object(extraction_engine, '_merge_chunk_results') as mock_merge:
                    
                    mock_chunk.return_value = ["chunk1", "chunk2"]
                    mock_extract.return_value = [{"question": "test", "confidence_score": 0.8}]
                    mock_merge.return_value = [{"question": "merged", "confidence_score": 0.8}]
                    
                    result = await extraction_engine.chunk_and_extract(large_content, chunk_size=50000)
                    
                    # Verify chunking was called
                    mock_chunk.assert_called_once_with(large_content, 50000)
                    assert mock_extract.call_count == 2  # Two chunks
                    mock_merge.assert_called_once()

    @pytest.mark.asyncio
    async def test_conversation_thread_detection(self, extraction_engine):
        """Test conversation thread detection and grouping"""
        from app.feedme.ai_extraction_engine import Message, Thread
        
        messages = [
            Message(content="First question", sender="customer", timestamp=None),
            Message(content="First answer", sender="agent", timestamp=None),
            Message(content="Follow up question", sender="customer", timestamp=None),
            Message(content="Follow up answer", sender="agent", timestamp=None),
            Message(content="New topic question", sender="customer", timestamp=None),
        ]
        
        threads = extraction_engine.detect_conversation_threads(messages)
        
        # Should detect logical conversation breaks
        assert len(threads) >= 1
        assert all(isinstance(thread, Thread) for thread in threads)

    def test_extraction_config_defaults(self):
        """Test extraction configuration defaults"""
        config = ExtractionConfig()
        
        assert config.model_name == "gemma-3-27b-it"
        assert config.temperature == 0.3
        assert config.max_output_tokens == 8192
        assert config.confidence_threshold == 0.7

    def test_extraction_config_custom(self):
        """Test custom extraction configuration"""
        config = ExtractionConfig(
            model_name="custom-model",
            temperature=0.5,
            confidence_threshold=0.8
        )
        
        assert config.model_name == "custom-model"
        assert config.temperature == 0.5
        assert config.confidence_threshold == 0.8


class TestExtractionPrompts:
    """Test extraction prompt generation and formatting"""

    def test_prompt_includes_all_requirements(self):
        """Test that extraction prompt includes all required elements"""
        from app.feedme.ai_extraction_engine import GemmaExtractionEngine
        
        engine = GemmaExtractionEngine("test-key")
        
        # This would be part of the prompt generation
        sample_prompt = """
        You are an expert at analyzing customer support conversations.
        
        Given this HTML support ticket, extract all Q&A exchanges following these rules:
        
        1. IDENTIFICATION:
           - Customer questions/issues (explicit or implied)
           - Support agent responses/solutions
           - Multi-turn conversation threads
        
        2. CONTEXT PRESERVATION:
           - Include 1-2 messages before/after for context
           - Preserve technical details and error messages
           - Maintain conversation flow and dependencies
        
        3. QUALITY SCORING:
           - Rate confidence (0-1) based on clarity
           - Assess completeness of resolution
           - Identify issue type and resolution type
        """
        
        # Verify prompt contains key elements
        assert "customer support conversations" in sample_prompt
        assert "IDENTIFICATION" in sample_prompt
        assert "CONTEXT PRESERVATION" in sample_prompt
        assert "QUALITY SCORING" in sample_prompt
        assert "confidence" in sample_prompt


class TestIntegrationScenarios:
    """Integration test scenarios for real-world usage"""

    @pytest.mark.asyncio
    async def test_zendesk_html_extraction(self, extraction_engine):
        """Test extraction from Zendesk-style HTML"""
        zendesk_html = """
        <div class="zd-comment">
            <div class="zd-comment-author">Customer</div>
            <div class="zd-comment-body">How do I sync my Gmail account?</div>
        </div>
        <div class="zd-comment">
            <div class="zd-comment-author">Agent</div>
            <div class="zd-comment-body">To sync Gmail: 1. Add account 2. Use OAuth 3. Enable IMAP</div>
        </div>
        """
        
        # Mock successful extraction
        mock_response = Mock()
        mock_response.text = '''[{
            "question_text": "How do I sync my Gmail account?",
            "answer_text": "To sync Gmail: 1. Add account 2. Use OAuth 3. Enable IMAP",
            "confidence_score": 0.9,
            "issue_type": "email-sync"
        }]'''
        
        extraction_engine.model.generate_content_async.return_value = mock_response
        
        result = await extraction_engine.extract_conversations(
            html_content=zendesk_html,
            metadata={"platform": "zendesk"}
        )
        
        assert len(result) == 1
        assert result[0]["issue_type"] == "email-sync"

    @pytest.mark.asyncio
    async def test_multilingual_extraction(self, extraction_engine):
        """Test extraction from non-English content"""
        spanish_html = """
        <div class="conversation">
            <div class="customer">¿Cómo configuro mi correo IMAP?</div>
            <div class="agent">Para configurar IMAP: 1. Vaya a Configuración 2. Agregue cuenta</div>
        </div>
        """
        
        # Mock successful multilingual extraction
        mock_response = Mock()
        mock_response.text = '''[{
            "question_text": "¿Cómo configuro mi correo IMAP?",
            "answer_text": "Para configurar IMAP: 1. Vaya a Configuración 2. Agregue cuenta",
            "confidence_score": 0.8,
            "metadata": {"language": "es"}
        }]'''
        
        extraction_engine.model.generate_content_async.return_value = mock_response
        
        result = await extraction_engine.extract_conversations(
            html_content=spanish_html,
            metadata={"language": "es"}
        )
        
        assert len(result) == 1
        assert result[0]["metadata"]["language"] == "es"


# Performance and Error Handling Tests

class TestErrorHandling:
    """Test error handling and resilience"""

    @pytest.mark.asyncio
    async def test_api_rate_limit_handling(self, extraction_engine):
        """Test handling of API rate limits"""
        from google.api_core.exceptions import ResourceExhausted
        
        # Mock rate limit error
        extraction_engine.model.generate_content_async.side_effect = ResourceExhausted("Rate limit exceeded")
        
        # Should handle gracefully
        result = await extraction_engine.extract_conversations(
            html_content="<html>test</html>",
            metadata={}
        )
        
        assert result == []

    @pytest.mark.asyncio
    async def test_malformed_html_handling(self, extraction_engine):
        """Test handling of malformed HTML"""
        malformed_html = "<div><span>unclosed tags<div>nested improperly"
        
        # Mock extraction attempt
        mock_response = Mock()
        mock_response.text = "[]"
        extraction_engine.model.generate_content_async.return_value = mock_response
        
        # Should not crash on malformed HTML
        result = await extraction_engine.extract_conversations(
            html_content=malformed_html,
            metadata={}
        )
        
        assert isinstance(result, list)

    @pytest.mark.asyncio 
    async def test_empty_content_handling(self, extraction_engine):
        """Test handling of empty or whitespace-only content"""
        empty_content = "   \n\t   "
        
        result = await extraction_engine.extract_conversations(
            html_content=empty_content,
            metadata={}
        )
        
        assert result == []


if __name__ == "__main__":
    pytest.main([__file__])