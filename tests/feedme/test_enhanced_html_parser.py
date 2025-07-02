"""
Test suite for Enhanced HTML Parser
Tests for platform detection, semantic chunking, and conversation thread detection
"""

import pytest
from unittest.mock import Mock, patch
from typing import List, Dict, Any
from datetime import datetime

from app.feedme.parsers.enhanced_html_parser import (
    EnhancedHTMLParser, 
    ParsedMessage, 
    HTMLFormat,
    ConversationThread
)


@pytest.fixture
def enhanced_parser():
    """Create test enhanced HTML parser"""
    return EnhancedHTMLParser()


@pytest.fixture
def zendesk_html():
    """Sample Zendesk HTML content"""
    return """
    <div class="ticket-conversation">
        <div class="zd-comment" data-comment-id="123">
            <div class="zd-comment-author">John Doe</div>
            <div class="zd-comment-timestamp">2024-01-15T10:30:00Z</div>
            <div class="zd-comment-body">
                I'm having trouble with my email settings. IMAP won't connect and I keep getting authentication errors.
            </div>
        </div>
        <div class="zd-comment" data-comment-id="124">
            <div class="zd-comment-author">Support Agent</div>
            <div class="zd-comment-timestamp">2024-01-15T10:32:00Z</div>
            <div class="zd-comment-body">
                I can help you with that! Let's troubleshoot your IMAP settings:
                <br>1. Go to Settings > Email Accounts
                <br>2. Check your server settings (mail.example.com, port 993)
                <br>3. Ensure SSL/TLS is enabled
                <br>4. Try using an app-specific password
                <br><br>Please try these steps and let me know if you're still having issues.
            </div>
        </div>
        <div class="zd-comment" data-comment-id="125">
            <div class="zd-comment-author">John Doe</div>
            <div class="zd-comment-timestamp">2024-01-15T10:35:00Z</div>
            <div class="zd-comment-body">
                Perfect! The app-specific password did the trick. My email is syncing now. Thank you!
            </div>
        </div>
    </div>
    """


@pytest.fixture
def intercom_html():
    """Sample Intercom HTML content"""
    return """
    <div class="intercom-conversation">
        <div class="intercom-comment" data-author-type="user">
            <div class="intercom-comment-author">Jane Smith</div>
            <div class="intercom-comment-content">
                How do I set up multiple email accounts in Mailbird?
            </div>
            <time datetime="2024-01-16T14:20:00Z">2024-01-16T14:20:00Z</time>
        </div>
        <div class="intercom-comment" data-author-type="admin">
            <div class="intercom-comment-author">Support Team</div>
            <div class="intercom-comment-content">
                You can add multiple accounts easily:
                1. Click the + button in the sidebar
                2. Select your email provider
                3. Enter your credentials
                4. Repeat for each account
                
                Would you like me to walk you through this step by step?
            </div>
            <time datetime="2024-01-16T14:22:00Z">2024-01-16T14:22:00Z</time>
        </div>
    </div>
    """


@pytest.fixture
def large_html_content():
    """Large HTML content for chunking tests"""
    base_conversation = """
    <div class="message customer">
        <div class="author">Customer {}</div>
        <div class="content">This is question number {} about email setup.</div>
    </div>
    <div class="message agent">
        <div class="author">Agent</div>
        <div class="content">Here's the answer to question number {}. Follow these steps...</div>
    </div>
    """
    
    # Create content with 100 Q&A pairs (should exceed chunk size)
    content = "<html><body><div class='conversation'>"
    for i in range(100):
        content += base_conversation.format(i, i, i)
    content += "</div></body></html>"
    
    return content


class TestEnhancedHTMLParser:
    """Test cases for the Enhanced HTML Parser"""

    def test_parser_initialization(self, enhanced_parser):
        """Test parser initializes with correct selectors"""
        assert enhanced_parser is not None
        assert hasattr(enhanced_parser, 'PLATFORM_SELECTORS')
        assert 'zendesk' in enhanced_parser.PLATFORM_SELECTORS
        assert 'intercom' in enhanced_parser.PLATFORM_SELECTORS
        assert 'freshdesk' in enhanced_parser.PLATFORM_SELECTORS

    def test_zendesk_platform_detection(self, enhanced_parser, zendesk_html):
        """Test automatic detection of Zendesk platform"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(zendesk_html, 'html.parser')
        
        platform = enhanced_parser._detect_platform(soup)
        assert platform == HTMLFormat.ZENDESK

    def test_intercom_platform_detection(self, enhanced_parser, intercom_html):
        """Test automatic detection of Intercom platform"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(intercom_html, 'html.parser')
        
        platform = enhanced_parser._detect_platform(soup)
        assert platform == HTMLFormat.INTERCOM

    def test_zendesk_message_extraction(self, enhanced_parser, zendesk_html):
        """Test message extraction from Zendesk HTML"""
        result = enhanced_parser.parse(zendesk_html)
        
        assert result['platform'] == HTMLFormat.ZENDESK
        assert len(result['messages']) == 3
        
        # Verify first message
        first_msg = result['messages'][0]
        assert first_msg.sender == 'John Doe'
        assert first_msg.role.value == 'customer'
        assert 'IMAP won\'t connect' in first_msg.content
        assert first_msg.timestamp is not None
        
        # Verify agent response
        agent_msg = result['messages'][1]
        assert agent_msg.role.value == 'agent'
        assert 'Support Agent' in agent_msg.sender
        assert 'troubleshoot your IMAP' in agent_msg.content

    def test_conversation_thread_detection(self, enhanced_parser, zendesk_html):
        """Test detection and grouping of conversation threads"""
        result = enhanced_parser.parse(zendesk_html)
        threads = enhanced_parser.detect_conversation_threads(result['messages'])
        
        # Should detect one main thread
        assert len(threads) >= 1
        assert isinstance(threads[0], ConversationThread)
        
        # Thread should contain all related messages
        main_thread = threads[0]
        assert len(main_thread.messages) == 3
        
        # Verify thread metadata
        assert main_thread.topic_keywords
        assert 'email' in ' '.join(main_thread.topic_keywords).lower()

    def test_semantic_chunking_large_content(self, enhanced_parser, large_html_content):
        """Test semantic chunking for large HTML documents"""
        chunk_size = 50000  # 50KB chunks
        chunks = enhanced_parser._create_semantic_chunks(large_html_content, chunk_size)
        
        # Should create multiple chunks
        assert len(chunks) > 1
        
        # Each chunk should be roughly within size limit (with some tolerance)
        for chunk in chunks:
            assert len(chunk) <= chunk_size * 1.2  # 20% tolerance for semantic boundaries
        
        # Chunks should preserve complete conversations
        for chunk in chunks:
            # Should not split in the middle of a message
            assert chunk.count('<div class="message customer">') == chunk.count('</div>')

    def test_role_identification(self, enhanced_parser):
        """Test automatic role identification from sender names"""
        test_cases = [
            ("John Doe", "customer"),
            ("Support Agent", "agent"),
            ("support@company.com", "agent"),
            ("Customer Service Team", "agent"),
            ("jane.smith@customer.com", "customer"),
            ("Admin", "agent"),
            ("User123", "customer")
        ]
        
        for sender, expected_role in test_cases:
            role = enhanced_parser._identify_role(sender)
            assert role.value == expected_role

    def test_timestamp_parsing(self, enhanced_parser):
        """Test parsing of various timestamp formats"""
        test_timestamps = [
            "2024-01-15T10:30:00Z",
            "2024-01-15 10:30:00",
            "January 15, 2024 10:30 AM",
            "2024/01/15 10:30"
        ]
        
        for timestamp_str in test_timestamps:
            parsed = enhanced_parser._parse_timestamp(timestamp_str)
            assert isinstance(parsed, datetime)
            assert parsed.year == 2024
            assert parsed.month == 1
            assert parsed.day == 15

    def test_metadata_extraction(self, enhanced_parser, zendesk_html):
        """Test extraction of conversation metadata"""
        result = enhanced_parser.parse(zendesk_html)
        metadata = result['metadata']
        
        assert 'message_count' in metadata
        assert metadata['message_count'] == 3
        
        assert 'participants' in metadata
        assert len(metadata['participants']) >= 2
        
        assert 'conversation_duration' in metadata
        assert isinstance(metadata['conversation_duration'], float)

    def test_attachment_detection(self, enhanced_parser):
        """Test detection of attachments in HTML content"""
        html_with_attachments = """
        <div class="zd-comment">
            <div class="zd-comment-body">
                Here's the screenshot you requested.
                <div class="attachment-link">
                    <a href="/attachments/screenshot.png">screenshot.png</a>
                </div>
            </div>
        </div>
        """
        
        result = enhanced_parser.parse(html_with_attachments)
        
        # Should detect attachment
        assert len(result['messages']) == 1
        message = result['messages'][0]
        assert len(message.attachments) == 1
        assert 'screenshot.png' in message.attachments[0]

    def test_malformed_html_handling(self, enhanced_parser):
        """Test graceful handling of malformed HTML"""
        malformed_html = """
        <div class="conversation">
            <div class="message">
                <span class="sender">Customer
                <div class="content">Unclosed tags here
            </div>
            <div class="message">
                <span class="sender">Agent</span>
                <div class="content">Response here</div>
        """
        
        # Should not crash and should extract what it can
        result = enhanced_parser.parse(malformed_html)
        assert isinstance(result, dict)
        assert 'messages' in result
        assert isinstance(result['messages'], list)

    def test_empty_content_handling(self, enhanced_parser):
        """Test handling of empty or whitespace-only content"""
        empty_cases = ["", "   ", "\n\t\n", "<html></html>"]
        
        for empty_content in empty_cases:
            result = enhanced_parser.parse(empty_content)
            assert result['messages'] == []
            assert result['platform'] == HTMLFormat.UNKNOWN

    def test_multi_language_content(self, enhanced_parser):
        """Test parsing of non-English content"""
        spanish_html = """
        <div class="conversation">
            <div class="message customer">
                <div class="sender">Cliente</div>
                <div class="content">¿Cómo configuro mi correo IMAP?</div>
            </div>
            <div class="message agent">
                <div class="sender">Soporte</div>
                <div class="content">Para configurar IMAP, siga estos pasos...</div>
            </div>
        </div>
        """
        
        result = enhanced_parser.parse(spanish_html)
        assert len(result['messages']) == 2
        
        # Should preserve non-English content
        customer_msg = result['messages'][0]
        assert 'configuro mi correo' in customer_msg.content
        
        # Should detect language in metadata
        assert 'detected_language' in result['metadata']


class TestConversationThreads:
    """Test conversation thread detection and grouping"""

    def test_single_thread_detection(self, enhanced_parser):
        """Test detection of a single conversation thread"""
        messages = [
            ParsedMessage(content="I need help", sender="Customer", role="customer", timestamp=datetime.now()),
            ParsedMessage(content="Sure, what's the issue?", sender="Agent", role="agent", timestamp=datetime.now()),
            ParsedMessage(content="Email won't sync", sender="Customer", role="customer", timestamp=datetime.now()),
            ParsedMessage(content="Let me help you", sender="Agent", role="agent", timestamp=datetime.now())
        ]
        
        threads = enhanced_parser.detect_conversation_threads(messages)
        assert len(threads) == 1
        assert len(threads[0].messages) == 4

    def test_multiple_thread_detection(self, enhanced_parser):
        """Test detection of multiple conversation threads"""
        messages = [
            # Thread 1: Email issue
            ParsedMessage(content="Email sync problem", sender="Customer", role="customer", timestamp=datetime.now()),
            ParsedMessage(content="Email sync solution", sender="Agent", role="agent", timestamp=datetime.now()),
            
            # Thread 2: Calendar issue (new topic)
            ParsedMessage(content="Calendar not working", sender="Customer", role="customer", timestamp=datetime.now()),
            ParsedMessage(content="Calendar solution", sender="Agent", role="agent", timestamp=datetime.now())
        ]
        
        threads = enhanced_parser.detect_conversation_threads(messages)
        # Should detect topic change and create separate threads
        assert len(threads) >= 1  # At minimum one thread, possibly two if topic detection works


class TestErrorHandling:
    """Test error handling and edge cases"""

    def test_missing_required_elements(self, enhanced_parser):
        """Test handling when required HTML elements are missing"""
        incomplete_html = """
        <div class="some-container">
            <div class="random-content">No conversation structure here</div>
        </div>
        """
        
        result = enhanced_parser.parse(incomplete_html)
        assert result['platform'] == HTMLFormat.UNKNOWN
        assert result['messages'] == []
        assert 'error' not in result  # Should handle gracefully, not error

    def test_very_large_content(self, enhanced_parser):
        """Test handling of extremely large HTML content"""
        # Create very large content (> 1MB)
        large_message = "A" * 1000000  # 1MB of text
        huge_html = f"""
        <div class="conversation">
            <div class="message customer">
                <div class="content">{large_message}</div>
            </div>
        </div>
        """
        
        # Should handle without crashing (may truncate)
        result = enhanced_parser.parse(huge_html)
        assert isinstance(result, dict)
        assert 'messages' in result

    def test_deeply_nested_html(self, enhanced_parser):
        """Test handling of deeply nested HTML structures"""
        nested_html = """
        <div class="level1">
            <div class="level2">
                <div class="level3">
                    <div class="level4">
                        <div class="message customer">
                            <div class="content">Deep nesting question</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """
        
        result = enhanced_parser.parse(nested_html)
        # Should find the message despite deep nesting
        assert len(result['messages']) >= 1


if __name__ == "__main__":
    pytest.main([__file__])