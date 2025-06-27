"""
Enhanced HTML Transcript Parser for FeedMe v2.0
Specialized parser for extracting Q&A pairs from HTML support transcripts

This module provides:
- Advanced HTML parsing for various formats (chat, email, tickets)
- Intelligent Q&A extraction with context preservation
- Confidence scoring and quality assessment
- Support for preview and approval workflow
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from bs4 import BeautifulSoup, Tag
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class MessageRole(str, Enum):
    """Role of the message sender"""
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class HTMLFormat(str, Enum):
    """Detected HTML format types"""
    ZENDESK = "zendesk"
    INTERCOM = "intercom"
    FRESHDESK = "freshdesk"
    GENERIC_CHAT = "generic_chat"
    EMAIL_THREAD = "email_thread"
    UNKNOWN = "unknown"


@dataclass
class Message:
    """Represents a single message in a conversation"""
    text: str
    role: MessageRole
    timestamp: Optional[datetime] = None
    sender_name: Optional[str] = None
    sender_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    html_element: Optional[Tag] = None
    position: int = 0


@dataclass
class QAPair:
    """Represents an extracted Q&A pair"""
    question: str
    answer: str
    question_message: Message
    answer_message: Message
    context_before: List[Message] = field(default_factory=list)
    context_after: List[Message] = field(default_factory=list)
    confidence_score: float = 0.0
    quality_score: float = 0.0
    tags: List[str] = field(default_factory=list)
    issue_type: Optional[str] = None
    resolution_type: Optional[str] = None
    extraction_method: str = "html"


class HTMLTranscriptParser:
    """
    Advanced HTML transcript parser with intelligent Q&A extraction
    """
    
    def __init__(self):
        self.format_detectors = {
            HTMLFormat.ZENDESK: self._detect_zendesk,
            HTMLFormat.INTERCOM: self._detect_intercom,
            HTMLFormat.FRESHDESK: self._detect_freshdesk,
            HTMLFormat.EMAIL_THREAD: self._detect_email,
            HTMLFormat.GENERIC_CHAT: self._detect_generic_chat
        }
        
        self.message_extractors = {
            HTMLFormat.ZENDESK: self._extract_zendesk_messages,
            HTMLFormat.INTERCOM: self._extract_intercom_messages,
            HTMLFormat.FRESHDESK: self._extract_freshdesk_messages,
            HTMLFormat.EMAIL_THREAD: self._extract_email_messages,
            HTMLFormat.GENERIC_CHAT: self._extract_generic_messages,
            HTMLFormat.UNKNOWN: self._extract_fallback_messages
        }
        
        self.role_patterns = {
            'agent': [
                r'(support|agent|representative|team|staff|admin|moderator)',
                r'@.*\.(com|org|net)',  # Email domains often indicate agents
                r'\(.*support.*\)',
                r'\(.*team.*\)',
                r'\(.*agent.*\)'
            ],
            'customer': [
                r'(customer|client|user|member)',
                r'^(?!.*@.*\.(com|org|net))',  # No corporate email
            ]
        }
        
        self.question_indicators = [
            r'\?$',  # Ends with question mark
            r'^(how|what|when|where|why|who|which|can|could|would|should|is|are|do|does|did)\b',
            r'\b(help|issue|problem|error|broken|failed|cannot|won\'t|doesn\'t|unable)\b',
            r'\b(please|need|want|trying|looking for|wondering)\b'
        ]
        
        self.answer_indicators = [
            r'\b(try|click|go to|set|configure|enable|disable|follow|check)\b',
            r'\b(solution|fix|resolve|workaround|steps?|instructions?)\b',
            r'\b(should|will|can|need to|have to|must)\b',
            r'^(to|for|yes|no|sure|certainly|absolutely)\b'
        ]
    
    def parse_html_transcript(self, html_content: str) -> List[Dict[str, Any]]:
        """
        Main entry point for parsing HTML transcripts
        
        Args:
            html_content: Raw HTML content
            
        Returns:
            List of Q&A pairs as dictionaries ready for database insertion
        """
        try:
            # Parse HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Detect format
            format_type = self._detect_format(soup)
            logger.info(f"Detected HTML format: {format_type.value}")
            
            # Extract messages
            messages = self._extract_messages(soup, format_type)
            logger.info(f"Extracted {len(messages)} messages")
            
            # Extract Q&A pairs
            qa_pairs = self._extract_qa_pairs(messages)
            logger.info(f"Extracted {len(qa_pairs)} Q&A pairs")
            
            # Convert to database format
            return self._convert_to_db_format(qa_pairs)
            
        except Exception as e:
            logger.error(f"Error parsing HTML transcript: {e}")
            return []
    
    def _detect_format(self, soup: BeautifulSoup) -> HTMLFormat:
        """Detect the HTML format type"""
        html_text = str(soup)[:5000].lower()  # Check first 5000 chars
        
        for format_type, detector in self.format_detectors.items():
            if detector(soup, html_text):
                return format_type
        
        return HTMLFormat.UNKNOWN
    
    def _detect_zendesk(self, soup: BeautifulSoup, html_text: str) -> bool:
        """Detect Zendesk format"""
        indicators = [
            'zd-comment' in html_text,
            'zd-liquid-comment' in html_text,
            'zendesk' in html_text,
            'mailbird.zendesk.com' in html_text,
            soup.find('div', class_='zd-comment') is not None,
            soup.find('table', class_='zd-liquid-comment') is not None,
            soup.find('div', id='mail_header') is not None,
            soup.find('div', id='mail_bodies') is not None
        ]
        return sum(bool(ind) for ind in indicators) >= 2
    
    def _detect_intercom(self, soup: BeautifulSoup, html_text: str) -> bool:
        """Detect Intercom format"""
        indicators = [
            'intercom' in html_text,
            'conversation__' in html_text,
            soup.find('div', {'class': re.compile('intercom|conversation__')}) is not None
        ]
        return any(indicators)
    
    def _detect_freshdesk(self, soup: BeautifulSoup, html_text: str) -> bool:
        """Detect Freshdesk format"""
        indicators = [
            'freshdesk' in html_text,
            'ticket-' in html_text,
            soup.find('div', {'class': re.compile('freshdesk|ticket-')}) is not None
        ]
        return any(indicators)
    
    def _detect_email(self, soup: BeautifulSoup, html_text: str) -> bool:
        """Detect email thread format"""
        indicators = [
            re.search(r'from:.*@', html_text),
            re.search(r'to:.*@', html_text),
            re.search(r'subject:', html_text),
            soup.find('div', {'class': re.compile('email|message|thread')}) is not None
        ]
        return sum(bool(ind) for ind in indicators) >= 2
    
    def _detect_generic_chat(self, soup: BeautifulSoup, html_text: str) -> bool:
        """Detect generic chat format"""
        indicators = [
            soup.find('div', {'class': re.compile('chat|message|msg|conversation')}) is not None,
            soup.find('span', {'class': re.compile('time|timestamp|date')}) is not None,
            soup.find('span', {'class': re.compile('sender|author|user|name')}) is not None,
            # More flexible detection for test format
            bool(soup.find_all('div', {'class': re.compile('message|content')})),
            bool(soup.find_all(class_='customer')),
            bool(soup.find_all(class_='agent'))
        ]
        return sum(bool(ind) for ind in indicators) >= 2
    
    def _extract_messages(self, soup: BeautifulSoup, format_type: HTMLFormat) -> List[Message]:
        """Extract messages based on detected format"""
        extractor = self.message_extractors.get(format_type, self._extract_fallback_messages)
        messages = extractor(soup)
        
        # Sort by timestamp if available, otherwise by position
        messages.sort(key=lambda m: (m.timestamp or datetime.min, m.position))
        
        return messages
    
    def _extract_zendesk_messages(self, soup: BeautifulSoup) -> List[Message]:
        """Extract messages from Zendesk email format with zd-liquid-comment tables"""
        messages = []
        position = 0
        
        # First, extract the initial message from the main HTML content (not in zd-liquid-comment)
        html_div = soup.find('div', id='html')
        if html_div:
            # Get the first message (usually the most recent reply)
            first_content = []
            
            # Look for content before the first blockquote (this is usually the new reply)
            for elem in html_div.children:
                if hasattr(elem, 'name'):
                    if elem.name == 'blockquote':
                        break  # Stop at first blockquote (quoted content)
                    if elem.name in ['p', 'div'] and elem.get_text(strip=True):
                        first_content.append(elem.get_text(strip=True))
            
            # Extract sender info from mail header
            mail_header = soup.find('div', id='mail_header')
            sender_name = None
            if mail_header:
                from_field = mail_header.find('div', class_='field')
                if from_field and 'From:' in from_field.get_text():
                    from_value = from_field.find('div', class_='value')
                    if from_value:
                        sender_name = self._extract_email_sender_name(from_value.get_text())
            
            if first_content:
                text = ' '.join(first_content)
                text = self._clean_text(text)
                
                if text and len(text) > 20:  # Only include substantial content
                    # Determine if sender is agent or customer
                    role = MessageRole.CUSTOMER  # Default for email sender
                    if sender_name and any(term in sender_name.lower() for term in ['support', 'mailbird', 'team']):
                        role = MessageRole.AGENT
                    
                    messages.append(Message(
                        text=text,
                        role=role,
                        sender_name=sender_name,
                        position=position,
                        html_element=html_div
                    ))
                    position += 1
        
        # Extract messages from zd-liquid-comment tables (Zendesk conversation history)
        zd_tables = soup.find_all('table', class_='zd-liquid-comment')
        
        for table in zd_tables:
            # Extract author name and role
            author_p = table.find('p', style=lambda x: x and 'font-size: 15px' in x)
            sender_name = None
            role = MessageRole.UNKNOWN
            
            if author_p:
                author_text = author_p.get_text(strip=True)
                sender_name = self._extract_zendesk_author_name(author_text)
                
                # Determine role based on the author text format
                if '(Mailbird)' in author_text or '(mailbird)' in author_text.lower():
                    role = MessageRole.AGENT
                elif any(term in author_text.lower() for term in ['support', 'team', 'agent']):
                    role = MessageRole.AGENT
                else:
                    role = MessageRole.CUSTOMER
            
            # Extract timestamp
            timestamp_p = table.find('p', style=lambda x: x and 'color: #bbbbbb' in x)
            timestamp = None
            if timestamp_p:
                timestamp_text = timestamp_p.get_text(strip=True)
                timestamp = self._parse_zendesk_timestamp(timestamp_text)
            
            # Extract message content from zd-comment div
            zd_comment = table.find('div', class_='zd-comment')
            if zd_comment:
                # Remove signature if present
                signature = zd_comment.find('div', class_='signature')
                if signature:
                    signature.decompose()
                
                text = self._clean_text(zd_comment.get_text())
                
                if text and len(text) > 10:  # Only include substantial content
                    messages.append(Message(
                        text=text,
                        role=role,
                        timestamp=timestamp,
                        sender_name=sender_name,
                        position=position,
                        html_element=zd_comment
                    ))
                    position += 1
        
        # Sort messages by timestamp if available, otherwise keep original order
        messages.sort(key=lambda m: (m.timestamp or datetime.min, m.position))
        
        # Re-assign positions after sorting
        for i, message in enumerate(messages):
            message.position = i
        
        return messages
    
    def _extract_intercom_messages(self, soup: BeautifulSoup) -> List[Message]:
        """Extract messages from Intercom format"""
        messages = []
        position = 0
        
        # Common Intercom selectors
        message_selectors = [
            'div.conversation__message',
            'div.message-body',
            'div[class*="conversation__"]',
            'article.message'
        ]
        
        for selector in message_selectors:
            elements = soup.select(selector)
            if elements:
                for elem in elements:
                    message = self._extract_message_from_element(elem, position)
                    if message:
                        messages.append(message)
                        position += 1
                break
        
        return messages
    
    def _extract_freshdesk_messages(self, soup: BeautifulSoup) -> List[Message]:
        """Extract messages from Freshdesk format"""
        messages = []
        position = 0
        
        # Common Freshdesk selectors
        message_selectors = [
            'div.ticket-message',
            'div.conversation-message',
            'div[class*="ticket-"]',
            'div.note'
        ]
        
        for selector in message_selectors:
            elements = soup.select(selector)
            if elements:
                for elem in elements:
                    message = self._extract_message_from_element(elem, position)
                    if message:
                        messages.append(message)
                        position += 1
                break
        
        return messages
    
    def _extract_email_messages(self, soup: BeautifulSoup) -> List[Message]:
        """Extract messages from email thread format"""
        messages = []
        position = 0
        
        # Look for email containers
        email_containers = soup.find_all(['div', 'table'], class_=re.compile('email|message|thread'))
        
        for container in email_containers:
            # Extract sender
            sender_elem = container.find(text=re.compile(r'From:|Sender:'))
            if sender_elem:
                sender_text = sender_elem.find_parent().get_text(strip=True)
                role = self._determine_role_from_email(sender_text)
                sender_name = self._extract_email_sender(sender_text)
            else:
                role = MessageRole.UNKNOWN
                sender_name = None
            
            # Extract timestamp
            date_elem = container.find(text=re.compile(r'Date:|Sent:'))
            timestamp = None
            if date_elem:
                date_text = date_elem.find_parent().get_text(strip=True)
                timestamp = self._parse_email_date(date_text)
            
            # Extract message body
            body_elem = container.find(['div', 'td'], class_=re.compile('body|content|text'))
            if body_elem:
                text = self._clean_text(body_elem.get_text())
                
                if text:
                    messages.append(Message(
                        text=text,
                        role=role,
                        timestamp=timestamp,
                        sender_name=sender_name,
                        position=position,
                        html_element=container
                    ))
                    position += 1
        
        return messages
    
    def _extract_generic_messages(self, soup: BeautifulSoup) -> List[Message]:
        """Extract messages from generic chat format"""
        messages = []
        position = 0
        
        # Try various common message selectors
        message_selectors = [
            'div.message',
            'div.chat-message', 
            'div[class*="message"]',
            'div.msg',
            'li.message',
            'div.chat-line',
            # Add selectors for test format
            'div.message.customer',
            'div.message.agent'
        ]
        
        for selector in message_selectors:
            elements = soup.select(selector)
            if elements:
                logger.info(f"Found {len(elements)} elements with selector: {selector}")
                for elem in elements:
                    message = self._extract_message_from_element(elem, position)
                    if message:
                        messages.append(message)
                        position += 1
                break
        
        # If no messages found, try fallback extraction
        if not messages:
            logger.info("No messages found with standard selectors, trying fallback")
            messages = self._extract_fallback_messages(soup)
        
        return messages
    
    def _extract_fallback_messages(self, soup: BeautifulSoup) -> List[Message]:
        """Fallback message extraction for unknown formats"""
        messages = []
        position = 0
        
        # Extract all text blocks
        text_elements = soup.find_all(['p', 'div', 'span'], string=True)
        
        current_text = []
        for elem in text_elements:
            text = elem.get_text(strip=True)
            if len(text) > 20:  # Minimum text length
                current_text.append(text)
                
                # Check if this looks like end of a message
                if any(text.endswith(p) for p in ['.', '?', '!']) or len(current_text) > 3:
                    full_text = ' '.join(current_text)
                    role = self._determine_role_from_content(full_text, soup)
                    
                    messages.append(Message(
                        text=full_text,
                        role=role,
                        position=position,
                        html_element=elem
                    ))
                    position += 1
                    current_text = []
        
        return messages
    
    def _extract_message_from_element(self, elem: Tag, position: int) -> Optional[Message]:
        """Extract message data from a generic HTML element"""
        # Extract text
        text = self._clean_text(elem.get_text())
        if not text or len(text) < 10:
            return None
        
        # Extract sender/author
        sender_elem = elem.find(['span', 'div'], class_=re.compile('sender|author|user|name'))
        sender_name = sender_elem.get_text(strip=True) if sender_elem else None
        
        # Extract timestamp
        time_elem = elem.find(['span', 'div', 'time'], class_=re.compile('time|timestamp|date'))
        timestamp = self._parse_timestamp(time_elem.get_text(strip=True)) if time_elem else None
        
        # Determine role
        role = self._determine_role_from_element(elem, sender_name)
        
        return Message(
            text=text,
            role=role,
            timestamp=timestamp,
            sender_name=sender_name,
            position=position,
            html_element=elem
        )
    
    def _extract_qa_pairs(self, messages: List[Message]) -> List[QAPair]:
        """Extract Q&A pairs from messages"""
        qa_pairs = []
        
        for i, message in enumerate(messages):
            # Check if this message is a question
            if self._is_question(message):
                # Look for answer in subsequent messages
                for j in range(i + 1, min(i + 5, len(messages))):  # Check next 5 messages
                    next_msg = messages[j]
                    
                    # Check if it's an answer from a different role
                    if next_msg.role != message.role and self._is_answer(next_msg, message):
                        # Extract context
                        context_before = messages[max(0, i-2):i]
                        context_after = messages[j+1:min(j+3, len(messages))]
                        
                        # Calculate scores
                        confidence = self._calculate_confidence(message, next_msg)
                        quality = self._assess_quality(message.text, next_msg.text)
                        
                        # Extract tags and categories
                        tags = self._extract_tags(message.text, next_msg.text)
                        issue_type = self._classify_issue(message.text)
                        resolution_type = self._classify_resolution(next_msg.text)
                        
                        qa_pairs.append(QAPair(
                            question=message.text,
                            answer=next_msg.text,
                            question_message=message,
                            answer_message=next_msg,
                            context_before=context_before,
                            context_after=context_after,
                            confidence_score=confidence,
                            quality_score=quality,
                            tags=tags,
                            issue_type=issue_type,
                            resolution_type=resolution_type
                        ))
                        
                        break  # Found answer, move to next question
        
        return qa_pairs
    
    def _is_question(self, message: Message) -> bool:
        """Determine if a message is a question"""
        text = message.text.lower()
        
        # Check question indicators
        for pattern in self.question_indicators:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        # Additional checks for customer messages
        if message.role == MessageRole.CUSTOMER:
            # Customer messages with certain keywords are likely questions
            if any(word in text for word in ['help', 'how', 'why', 'issue', 'problem', 'cannot']):
                return True
        
        return False
    
    def _is_answer(self, message: Message, question: Message) -> bool:
        """Determine if a message is an answer to a question"""
        text = message.text.lower()
        
        # Agent messages following customer questions are likely answers
        if question.role == MessageRole.CUSTOMER and message.role == MessageRole.AGENT:
            return True
        
        # Check answer indicators
        for pattern in self.answer_indicators:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        # Check if it references the question
        question_keywords = re.findall(r'\b\w{4,}\b', question.text.lower())
        if sum(1 for kw in question_keywords if kw in text) >= 2:
            return True
        
        return False
    
    def _calculate_confidence(self, question: Message, answer: Message) -> float:
        """Calculate confidence score for Q&A pair"""
        score = 0.5  # Base score
        
        # Role-based confidence
        if question.role == MessageRole.CUSTOMER and answer.role == MessageRole.AGENT:
            score += 0.3
        elif question.role != MessageRole.UNKNOWN and answer.role != MessageRole.UNKNOWN:
            score += 0.2
        
        # Timing-based confidence (answers shortly after questions)
        if question.timestamp and answer.timestamp:
            time_diff = (answer.timestamp - question.timestamp).total_seconds()
            if 0 < time_diff < 3600:  # Within an hour
                score += 0.1
        
        # Content-based confidence
        if question.text.strip().endswith('?'):
            score += 0.1
        
        # Length-based confidence
        if 20 < len(answer.text.split()) < 500:
            score += 0.1
        
        return min(score, 1.0)
    
    def _assess_quality(self, question: str, answer: str) -> float:
        """Assess quality of Q&A pair"""
        score = 0.0
        
        # Length checks
        q_words = len(question.split())
        a_words = len(answer.split())
        
        if 5 <= q_words <= 100 and 10 <= a_words <= 500:
            score += 0.3
        
        # Question quality
        if any(question.lower().startswith(qw) for qw in ['how', 'what', 'why', 'when', 'where']):
            score += 0.2
        
        # Answer quality
        action_words = ['click', 'go to', 'select', 'choose', 'enable', 'disable', 'configure']
        if any(word in answer.lower() for word in action_words):
            score += 0.3
        
        # Completeness
        if '1.' in answer or 'step' in answer.lower():
            score += 0.2  # Structured answer
        
        return min(score, 1.0)
    
    def _extract_tags(self, question: str, answer: str) -> List[str]:
        """Extract relevant tags from Q&A content"""
        tags = []
        combined_text = (question + " " + answer).lower()
        
        # Mailbird-specific tags
        tag_patterns = {
            'email-setup': ['email', 'account', 'setup', 'configure', 'imap', 'smtp'],
            'sync-issue': ['sync', 'synchronize', 'not updating', 'refresh'],
            'performance': ['slow', 'lag', 'freeze', 'crash', 'memory'],
            'login': ['login', 'password', 'authentication', 'sign in', 'credentials'],
            'ui-issue': ['display', 'interface', 'button', 'menu', 'window'],
            'search': ['search', 'find', 'filter', 'query'],
            'attachment': ['attachment', 'file', 'upload', 'download'],
            'notification': ['notification', 'alert', 'sound', 'popup'],
            'integration': ['calendar', 'contacts', 'app', 'integration'],
            'error': ['error', 'failed', 'exception', 'problem']
        }
        
        for tag, keywords in tag_patterns.items():
            if any(keyword in combined_text for keyword in keywords):
                tags.append(tag)
        
        return tags[:5]  # Limit to 5 tags
    
    def _classify_issue(self, question: str) -> Optional[str]:
        """Classify the type of issue"""
        q_lower = question.lower()
        
        issue_patterns = {
            'setup': ['setup', 'configure', 'install', 'add account'],
            'sync': ['sync', 'not updating', 'refresh', 'missing emails'],
            'authentication': ['login', 'password', 'cannot access', 'authentication'],
            'performance': ['slow', 'freeze', 'crash', 'not responding'],
            'feature-request': ['how to', 'can i', 'is it possible'],
            'bug': ['error', 'broken', 'not working', 'failed'],
            'ui': ['cannot see', 'missing button', 'display issue']
        }
        
        for issue_type, patterns in issue_patterns.items():
            if any(pattern in q_lower for pattern in patterns):
                return issue_type
        
        return 'other'
    
    def _classify_resolution(self, answer: str) -> Optional[str]:
        """Classify the type of resolution"""
        a_lower = answer.lower()
        
        resolution_patterns = {
            'step-by-step': ['step 1', 'follow these steps', 'first', 'then', 'finally'],
            'settings-change': ['go to settings', 'preferences', 'configure', 'change'],
            'troubleshooting': ['try', 'check if', 'make sure', 'verify'],
            'workaround': ['alternatively', 'as a workaround', 'temporary solution'],
            'explanation': ['this is because', 'the reason', 'designed to'],
            'escalation': ['i will', 'our team will', 'escalate', 'investigate']
        }
        
        for res_type, patterns in resolution_patterns.items():
            if any(pattern in a_lower for pattern in patterns):
                return res_type
        
        return 'other'
    
    def _convert_to_db_format(self, qa_pairs: List[QAPair]) -> List[Dict[str, Any]]:
        """Convert QAPair objects to database-ready format"""
        db_examples = []
        
        for qa in qa_pairs:
            db_examples.append({
                'question_text': qa.question,
                'answer_text': qa.answer,
                'context_before': ' '.join([m.text for m in qa.context_before]),
                'context_after': ' '.join([m.text for m in qa.context_after]),
                'confidence_score': qa.confidence_score,
                'tags': qa.tags,
                'issue_type': qa.issue_type,
                'resolution_type': qa.resolution_type,
                'extraction_method': qa.extraction_method,
                'extraction_confidence': qa.confidence_score,
                'metadata': {
                    'quality_score': qa.quality_score,
                    'question_role': qa.question_message.role.value,
                    'answer_role': qa.answer_message.role.value,
                    'question_timestamp': qa.question_message.timestamp.isoformat() if qa.question_message.timestamp else None,
                    'answer_timestamp': qa.answer_message.timestamp.isoformat() if qa.answer_message.timestamp else None
                }
            })
        
        return db_examples
    
    # Helper methods
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove common artifacts
        text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)  # Zero-width spaces
        text = re.sub(r'\xa0', ' ', text)  # Non-breaking spaces
        
        return text.strip()
    
    def _clone_without_blockquotes(self, element: Tag) -> Tag:
        """Clone element without blockquote children"""
        import copy
        clone = copy.copy(element)
        
        # Remove blockquotes
        for blockquote in clone.find_all('blockquote'):
            blockquote.decompose()
        
        return clone
    
    def _determine_role_from_content(self, text: str, soup: BeautifulSoup) -> MessageRole:
        """Determine role based on content analysis"""
        text_lower = text.lower()
        
        # Check for agent indicators
        for pattern in self.role_patterns['agent']:
            if re.search(pattern, text_lower):
                return MessageRole.AGENT
        
        # Check email headers in full HTML
        html_text = str(soup)[:1000].lower()
        if '@mailbird' in html_text or 'mailbird support' in html_text:
            return MessageRole.AGENT
        
        return MessageRole.CUSTOMER
    
    def _determine_role_from_element(self, elem: Tag, sender_name: Optional[str]) -> MessageRole:
        """Determine role from HTML element attributes"""
        # Check class attributes
        classes = elem.get('class', [])
        class_text = ' '.join(classes).lower()
        
        if any(ind in class_text for ind in ['agent', 'support', 'admin', 'staff']):
            return MessageRole.AGENT
        elif any(ind in class_text for ind in ['customer', 'user', 'client']):
            return MessageRole.CUSTOMER
        
        # Check sender name
        if sender_name:
            sender_lower = sender_name.lower()
            if any(ind in sender_lower for ind in ['support', 'team', 'agent', 'mailbird']):
                return MessageRole.AGENT
        
        # Check data attributes
        role_attr = elem.get('data-role') or elem.get('data-sender-type')
        if role_attr:
            if 'agent' in role_attr.lower():
                return MessageRole.AGENT
            elif 'customer' in role_attr.lower():
                return MessageRole.CUSTOMER
        
        return MessageRole.UNKNOWN
    
    def _determine_role_from_email(self, sender_text: str) -> MessageRole:
        """Determine role from email sender information"""
        if '@mailbird' in sender_text.lower() or 'support@' in sender_text.lower():
            return MessageRole.AGENT
        return MessageRole.CUSTOMER
    
    def _extract_sender_name(self, text: str) -> Optional[str]:
        """Extract sender name from text"""
        # Remove common prefixes
        text = re.sub(r'^(From|Sender|Author):\s*', '', text, flags=re.IGNORECASE)
        
        # Extract name before email
        email_match = re.search(r'^([^<@]+?)(?:\s*<|@)', text)
        if email_match:
            return email_match.group(1).strip()
        
        # Extract name in parentheses
        paren_match = re.search(r'\(([^)]+)\)', text)
        if paren_match:
            return paren_match.group(1).strip()
        
        return text.strip() if len(text) < 50 else None
    
    def _extract_email_sender(self, text: str) -> Optional[str]:
        """Extract sender from email header"""
        match = re.search(r'From:\s*([^<\n]+)', text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None
    
    def _extract_timestamp(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract timestamp from various sources"""
        # Look for meta tags
        date_meta = soup.find('meta', attrs={'name': 'date'})
        if date_meta and date_meta.get('content'):
            return self._parse_timestamp(date_meta['content'])
        
        # Look for time elements
        time_elem = soup.find('time')
        if time_elem:
            return self._parse_timestamp(time_elem.get_text(strip=True))
        
        # Look in headers
        header_text = str(soup)[:1000]
        date_patterns = [
            r'Date:\s*([^\n]+)',
            r'Sent:\s*([^\n]+)',
            r'(\d{4}-\d{2}-\d{2})',
            r'(\w+\s+\d{1,2},\s+\d{4})'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, header_text)
            if match:
                return self._parse_timestamp(match.group(1))
        
        return None
    
    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse various timestamp formats"""
        if not timestamp_str:
            return None
        
        # Clean timestamp
        timestamp_str = timestamp_str.strip()
        
        # Common formats
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
            "%b %d, %Y, %H:%M %Z",
            "%b %d, %Y, %H:%M",
            "%b %d, %Y",
            "%B %d, %Y, %H:%M",
            "%B %d, %Y",
            "%a, %d %b %Y %H:%M:%S %z",
            "%d %b %Y %H:%M:%S",
            "%d %b %Y %H:%M",
            "%d %b %Y"
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue
        
        # Try parsing with dateutil if available
        try:
            from dateutil import parser
            return parser.parse(timestamp_str)
        except:
            pass
        
        logger.warning(f"Could not parse timestamp: {timestamp_str}")
        return None
    
    def _parse_email_date(self, date_text: str) -> Optional[datetime]:
        """Parse date from email header"""
        match = re.search(r'Date:\s*([^\n]+)', date_text, re.IGNORECASE)
        if match:
            return self._parse_timestamp(match.group(1))
        return None
    
    def _extract_email_sender_name(self, from_text: str) -> Optional[str]:
        """Extract sender name from email From field"""
        # Handle formats like: "Anthony Bowen" <email@domain.com>
        match = re.search(r'^"?([^"<]+)"?\s*<', from_text)
        if match:
            return match.group(1).strip()
        
        # Handle formats like: Name <email> or just Name
        match = re.search(r'^([^<]+?)(?:\s*<|$)', from_text)
        if match:
            name = match.group(1).strip()
            return name if len(name) > 1 else None
        
        return None
    
    def _extract_zendesk_author_name(self, author_text: str) -> Optional[str]:
        """Extract author name from Zendesk author text"""
        # Handle formats like: "Shubham Patel (Mailbird)" or "Anthony Bowen"
        match = re.search(r'^([^(]+?)(?:\s*\(|$)', author_text)
        if match:
            return match.group(1).strip()
        return author_text.strip() if author_text else None
    
    def _parse_zendesk_timestamp(self, timestamp_text: str) -> Optional[datetime]:
        """Parse Zendesk timestamp format"""
        # Handle formats like: "Jun 24, 2025, 11:11 UTC"
        patterns = [
            r'(\w{3} \d{1,2}, \d{4}, \d{1,2}:\d{2} UTC)',
            r'(\w{3} \d{1,2}, \d{4} \d{1,2}:\d{2} UTC)',
            r'(\w{3} \d{1,2}, \d{4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, timestamp_text)
            if match:
                return self._parse_timestamp(match.group(1))
        
        return self._parse_timestamp(timestamp_text)