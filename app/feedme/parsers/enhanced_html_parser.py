"""
Enhanced HTML Parser for FeedMe v2.0
Production-grade HTML parser with multi-platform support and semantic chunking
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


class HTMLFormat(str, Enum):
    """Detected HTML format types"""
    ZENDESK = "zendesk"
    INTERCOM = "intercom" 
    FRESHDESK = "freshdesk"
    GENERIC_CHAT = "generic_chat"
    EMAIL_THREAD = "email_thread"
    UNKNOWN = "unknown"


class MessageRole(str, Enum):
    """Role of the message sender"""
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass
class ParsedMessage:
    """Represents a parsed message from HTML"""
    content: str
    sender: str
    role: str
    timestamp: Optional[datetime] = None
    attachments: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    html_element: Optional[Tag] = None
    position: int = 0


@dataclass
class ConversationThread:
    """Represents a conversation thread"""
    messages: List[ParsedMessage]
    topic_keywords: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class EnhancedHTMLParser:
    """Production-grade HTML parser with multi-format support"""
    
    # Platform-specific selectors
    PLATFORM_SELECTORS = {
        'zendesk': {
            'message': '.zd-comment',
            'sender': '.zd-comment-author',
            'timestamp': '.zd-comment-timestamp',
            'content': '.zd-comment-body',
            'attachments': '.attachment-link'
        },
        'intercom': {
            'message': '.intercom-comment',
            'sender': '.intercom-comment-author',
            'timestamp': 'time[datetime]',
            'content': '.intercom-comment-content',
            'attachments': '.intercom-attachment'
        },
        'freshdesk': {
            'message': '.thread-message',
            'sender': '.agent-name, .customer-name',
            'timestamp': '.timestamp',
            'content': '.message-content',
            'attachments': '.attachment-item'
        },
        'generic': {
            'message': '.message, .chat-message, .conversation-message',
            'sender': '.sender, .author, .user-name',
            'timestamp': '.timestamp, .time, .date',
            'content': '.content, .text, .body',
            'attachments': '.attachment, .file'
        }
    }
    
    def __init__(self):
        # Role identification patterns
        self.agent_patterns = [
            r'(support|agent|representative|team|staff|admin|moderator)',
            r'@.*\.(com|org|net)',  # Email domains often indicate agents
            r'\(.*support.*\)',
            r'\(.*team.*\)',
            r'\(.*agent.*\)'
        ]
        
        self.customer_patterns = [
            r'(customer|user|client|member)',
            r'^\w+\s+\w+$',  # Typical name format
            r'user\d+',  # Generic user IDs
        ]
        
        # Timestamp patterns
        self.timestamp_patterns = [
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?',  # ISO format
            r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',     # Standard format
            r'\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}',     # US format
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s*(AM|PM)?'
        ]

    def parse(self, html_content: str) -> Dict[str, Any]:
        """Parse HTML with automatic platform detection"""
        
        if not html_content or not html_content.strip():
            return {
                'platform': HTMLFormat.UNKNOWN,
                'messages': [],
                'metadata': {'error': 'Empty content'}
            }
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Detect platform
            platform = self._detect_platform(soup)
            
            # Extract messages using appropriate selectors
            messages = self._extract_messages(soup, platform)
            
            # Post-process for quality
            messages = self._clean_and_validate(messages)
            
            # Extract conversation metadata
            metadata = self._extract_metadata(soup, messages)
            
            return {
                'platform': platform,
                'messages': messages,
                'metadata': metadata
            }
            
        except Exception as e:
            logger.error(f"Error parsing HTML: {e}")
            return {
                'platform': HTMLFormat.UNKNOWN,
                'messages': [],
                'metadata': {'error': str(e)}
            }

    def _detect_platform(self, soup: BeautifulSoup) -> HTMLFormat:
        """Detect platform based on HTML structure"""
        
        html_str = str(soup).lower()
        
        # Check for Zendesk indicators
        if any(indicator in html_str for indicator in ['zd-comment', 'zendesk', 'zd-']):
            return HTMLFormat.ZENDESK
        
        # Check for Intercom indicators    
        if any(indicator in html_str for indicator in ['intercom-comment', 'intercom', 'ic-']):
            return HTMLFormat.INTERCOM
            
        # Check for Freshdesk indicators
        if any(indicator in html_str for indicator in ['freshdesk', 'thread-message', 'fd-']):
            return HTMLFormat.FRESHDESK
            
        # Check for email thread indicators
        if any(indicator in html_str for indicator in ['email-thread', 'mail-', 'from:', 'to:']):
            return HTMLFormat.EMAIL_THREAD
            
        # Check for generic chat indicators
        if any(indicator in html_str for indicator in [
            'chat-message', 'conversation', 'message', 'chat-'
        ]):
            return HTMLFormat.GENERIC_CHAT
            
        return HTMLFormat.UNKNOWN

    def _extract_messages(self, soup: BeautifulSoup, platform: HTMLFormat) -> List[ParsedMessage]:
        """Extract messages using platform-specific selectors"""
        
        messages = []
        
        try:
            if platform == HTMLFormat.ZENDESK:
                messages = self._extract_zendesk_messages(soup)
            elif platform == HTMLFormat.INTERCOM:
                messages = self._extract_intercom_messages(soup)
            elif platform == HTMLFormat.FRESHDESK:
                messages = self._extract_freshdesk_messages(soup)
            elif platform == HTMLFormat.EMAIL_THREAD:
                messages = self._extract_email_messages(soup)
            else:
                # Generic extraction for unknown platforms
                messages = self._extract_generic_messages(soup)
                
        except Exception as e:
            logger.error(f"Error extracting messages for platform {platform}: {e}")
            # Fallback to generic extraction
            messages = self._extract_generic_messages(soup)
        
        return messages

    def _extract_zendesk_messages(self, soup: BeautifulSoup) -> List[ParsedMessage]:
        """Extract messages from Zendesk HTML"""
        
        messages = []
        selectors = self.PLATFORM_SELECTORS['zendesk']
        
        message_elements = soup.select(selectors['message'])
        
        for i, element in enumerate(message_elements):
            try:
                # Extract sender
                sender_elem = element.select_one(selectors['sender'])
                sender = sender_elem.get_text(strip=True) if sender_elem else "Unknown"
                
                # Extract content
                content_elem = element.select_one(selectors['content'])
                content = content_elem.get_text(separator=' ', strip=True) if content_elem else ""
                
                # Extract timestamp
                timestamp_elem = element.select_one(selectors['timestamp'])
                timestamp = self._parse_timestamp(
                    timestamp_elem.get_text(strip=True) if timestamp_elem else ""
                )
                
                # Extract attachments
                attachments = self._extract_attachments(element, selectors['attachments'])
                
                # Identify role
                role = self._identify_role(sender)
                
                if content:  # Only add messages with content
                    message = ParsedMessage(
                        content=content,
                        sender=sender,
                        role=role.value,
                        timestamp=timestamp,
                        attachments=attachments,
                        html_element=element,
                        position=i
                    )
                    messages.append(message)
                    
            except Exception as e:
                logger.warning(f"Error extracting Zendesk message {i}: {e}")
                continue
        
        return messages

    def _extract_intercom_messages(self, soup: BeautifulSoup) -> List[ParsedMessage]:
        """Extract messages from Intercom HTML"""
        
        messages = []
        selectors = self.PLATFORM_SELECTORS['intercom']
        
        message_elements = soup.select(selectors['message'])
        
        for i, element in enumerate(message_elements):
            try:
                # Extract sender
                sender_elem = element.select_one(selectors['sender'])
                sender = sender_elem.get_text(strip=True) if sender_elem else "Unknown"
                
                # Extract content
                content_elem = element.select_one(selectors['content'])
                content = content_elem.get_text(separator=' ', strip=True) if content_elem else ""
                
                # Extract timestamp
                timestamp_elem = element.select_one(selectors['timestamp'])
                timestamp_str = ""
                if timestamp_elem:
                    timestamp_str = timestamp_elem.get('datetime') or timestamp_elem.get_text(strip=True)
                timestamp = self._parse_timestamp(timestamp_str)
                
                # Check for role indicators in element attributes
                role = MessageRole.CUSTOMER
                if element.get('data-author-type') == 'admin':
                    role = MessageRole.AGENT
                else:
                    role = self._identify_role(sender)
                
                # Extract attachments
                attachments = self._extract_attachments(element, selectors['attachments'])
                
                if content:  # Only add messages with content
                    message = ParsedMessage(
                        content=content,
                        sender=sender,
                        role=role.value,
                        timestamp=timestamp,
                        attachments=attachments,
                        html_element=element,
                        position=i
                    )
                    messages.append(message)
                    
            except Exception as e:
                logger.warning(f"Error extracting Intercom message {i}: {e}")
                continue
        
        return messages

    def _extract_freshdesk_messages(self, soup: BeautifulSoup) -> List[ParsedMessage]:
        """Extract messages from Freshdesk HTML"""
        
        messages = []
        selectors = self.PLATFORM_SELECTORS['freshdesk']
        
        message_elements = soup.select(selectors['message'])
        
        for i, element in enumerate(message_elements):
            try:
                # Extract sender
                sender_elem = element.select_one(selectors['sender'])
                sender = sender_elem.get_text(strip=True) if sender_elem else "Unknown"
                
                # Extract content
                content_elem = element.select_one(selectors['content'])
                content = content_elem.get_text(separator=' ', strip=True) if content_elem else ""
                
                # Extract timestamp
                timestamp_elem = element.select_one(selectors['timestamp'])
                timestamp = self._parse_timestamp(
                    timestamp_elem.get_text(strip=True) if timestamp_elem else ""
                )
                
                # Identify role
                role = self._identify_role(sender)
                
                # Extract attachments
                attachments = self._extract_attachments(element, selectors['attachments'])
                
                if content:  # Only add messages with content
                    message = ParsedMessage(
                        content=content,
                        sender=sender,
                        role=role.value,
                        timestamp=timestamp,
                        attachments=attachments,
                        html_element=element,
                        position=i
                    )
                    messages.append(message)
                    
            except Exception as e:
                logger.warning(f"Error extracting Freshdesk message {i}: {e}")
                continue
        
        return messages

    def _extract_email_messages(self, soup: BeautifulSoup) -> List[ParsedMessage]:
        """Extract messages from email thread HTML"""
        
        messages = []
        
        # Look for email-specific patterns
        email_blocks = soup.find_all(['div', 'article', 'section'], 
                                   class_=re.compile(r'(email|mail|message)'))
        
        for i, element in enumerate(email_blocks):
            try:
                # Extract sender (look for From: pattern)
                sender = "Unknown"
                from_pattern = element.find(text=re.compile(r'From:', re.IGNORECASE))
                if from_pattern and from_pattern.parent:
                    sender_text = from_pattern.parent.get_text()
                    sender_match = re.search(r'From:\s*([^\n<]+)', sender_text, re.IGNORECASE)
                    if sender_match:
                        sender = sender_match.group(1).strip()
                
                # Extract content
                content = element.get_text(separator=' ', strip=True)
                
                # Clean up content (remove headers)
                content = re.sub(r'From:.*?\n', '', content, flags=re.IGNORECASE)
                content = re.sub(r'To:.*?\n', '', content, flags=re.IGNORECASE)
                content = re.sub(r'Subject:.*?\n', '', content, flags=re.IGNORECASE)
                content = content.strip()
                
                # Extract timestamp
                timestamp = None
                date_pattern = element.find(text=re.compile(r'\d{1,2}/\d{1,2}/\d{4}'))
                if date_pattern:
                    timestamp = self._parse_timestamp(date_pattern)
                
                # Identify role
                role = self._identify_role(sender)
                
                if content and len(content) > 10:  # Only add substantial messages
                    message = ParsedMessage(
                        content=content,
                        sender=sender,
                        role=role.value,
                        timestamp=timestamp,
                        html_element=element,
                        position=i
                    )
                    messages.append(message)
                    
            except Exception as e:
                logger.warning(f"Error extracting email message {i}: {e}")
                continue
        
        return messages

    def _extract_generic_messages(self, soup: BeautifulSoup) -> List[ParsedMessage]:
        """Generic message extraction for unknown formats"""
        
        messages = []
        selectors = self.PLATFORM_SELECTORS['generic']
        
        # Try multiple selector patterns
        message_elements = []
        for selector in selectors['message'].split(', '):
            elements = soup.select(selector.strip())
            message_elements.extend(elements)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_elements = []
        for elem in message_elements:
            elem_id = id(elem)
            if elem_id not in seen:
                seen.add(elem_id)
                unique_elements.append(elem)
        
        for i, element in enumerate(unique_elements):
            try:
                # Extract sender
                sender = "Unknown"
                for selector in selectors['sender'].split(', '):
                    sender_elem = element.select_one(selector.strip())
                    if sender_elem:
                        sender = sender_elem.get_text(strip=True)
                        break
                
                # Extract content
                content = ""
                for selector in selectors['content'].split(', '):
                    content_elem = element.select_one(selector.strip())
                    if content_elem:
                        content = content_elem.get_text(separator=' ', strip=True)
                        break
                
                # If no specific content selector worked, use element text
                if not content:
                    content = element.get_text(separator=' ', strip=True)
                
                # Extract timestamp
                timestamp = None
                for selector in selectors['timestamp'].split(', '):
                    timestamp_elem = element.select_one(selector.strip())
                    if timestamp_elem:
                        timestamp_str = timestamp_elem.get_text(strip=True)
                        timestamp = self._parse_timestamp(timestamp_str)
                        break
                
                # Identify role
                role = self._identify_role(sender)
                
                # Extract attachments
                attachments = self._extract_attachments(element, selectors['attachments'])
                
                if content and len(content) > 5:  # Only add messages with substantial content
                    message = ParsedMessage(
                        content=content,
                        sender=sender,
                        role=role.value,
                        timestamp=timestamp,
                        attachments=attachments,
                        html_element=element,
                        position=i
                    )
                    messages.append(message)
                    
            except Exception as e:
                logger.warning(f"Error extracting generic message {i}: {e}")
                continue
        
        return messages

    def _identify_role(self, sender: str) -> MessageRole:
        """Identify role based on sender name"""
        
        if not sender:
            return MessageRole.UNKNOWN
        
        sender_lower = sender.lower()
        
        # Check for agent patterns
        for pattern in self.agent_patterns:
            if re.search(pattern, sender_lower):
                return MessageRole.AGENT
        
        # Check for customer patterns
        for pattern in self.customer_patterns:
            if re.search(pattern, sender_lower):
                return MessageRole.CUSTOMER
        
        # Default heuristics
        if any(word in sender_lower for word in ['support', 'team', 'agent', 'admin']):
            return MessageRole.AGENT
        
        return MessageRole.CUSTOMER

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp from various formats"""
        
        if not timestamp_str:
            return None
        
        # Clean timestamp string
        timestamp_str = timestamp_str.strip()
        
        # Try common formats
        formats = [
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%m/%d/%Y %H:%M',
            '%d/%m/%Y %H:%M',
            '%B %d, %Y %H:%M %p',
            '%B %d, %Y %I:%M %p'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue
        
        # Try regex patterns for flexible parsing
        for pattern in self.timestamp_patterns:
            match = re.search(pattern, timestamp_str, re.IGNORECASE)
            if match:
                try:
                    matched_str = match.group(0)
                    # Try to parse the matched string
                    for fmt in formats:
                        try:
                            return datetime.strptime(matched_str, fmt)
                        except ValueError:
                            continue
                except Exception:
                    continue
        
        logger.debug(f"Could not parse timestamp: {timestamp_str}")
        return None

    def _extract_attachments(self, element: Tag, attachment_selector: str) -> List[str]:
        """Extract attachment information from message element"""
        
        attachments = []
        
        try:
            # Find attachment elements
            attachment_elements = element.select(attachment_selector)
            
            for attach_elem in attachment_elements:
                # Look for links or file names
                link = attach_elem.find('a')
                if link:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    if href or text:
                        attachments.append(href or text)
                else:
                    # Get text content as filename
                    text = attach_elem.get_text(strip=True)
                    if text:
                        attachments.append(text)
        
        except Exception as e:
            logger.debug(f"Error extracting attachments: {e}")
        
        return attachments

    def _clean_and_validate(self, messages: List[ParsedMessage]) -> List[ParsedMessage]:
        """Clean and validate extracted messages"""
        
        cleaned_messages = []
        
        for message in messages:
            try:
                # Clean content
                content = message.content.strip()
                
                # Remove excessive whitespace
                content = re.sub(r'\s+', ' ', content)
                
                # Skip messages that are too short
                if len(content) < 5:
                    continue
                
                # Skip system messages or automated responses
                if any(phrase in content.lower() for phrase in [
                    'auto-reply', 'out of office', 'do not reply'
                ]):
                    continue
                
                # Update message with cleaned content
                message.content = content
                cleaned_messages.append(message)
                
            except Exception as e:
                logger.warning(f"Error cleaning message: {e}")
                continue
        
        return cleaned_messages

    def _extract_metadata(self, soup: BeautifulSoup, messages: List[ParsedMessage]) -> Dict[str, Any]:
        """Extract conversation metadata"""
        
        metadata = {
            'message_count': len(messages),
            'participants': [],
            'total_word_count': 0,
            'conversation_duration': 0.0,
            'detected_language': 'en'
        }
        
        try:
            # Extract participants
            senders = set()
            word_count = 0
            timestamps = []
            
            for message in messages:
                senders.add(message.sender)
                word_count += len(message.content.split())
                if message.timestamp:
                    timestamps.append(message.timestamp)
            
            metadata['participants'] = list(senders)
            metadata['total_word_count'] = word_count
            
            # Calculate conversation duration
            if len(timestamps) >= 2:
                duration = (max(timestamps) - min(timestamps)).total_seconds()
                metadata['conversation_duration'] = duration
            
            # Detect language (simple heuristic)
            combined_text = ' '.join(msg.content for msg in messages[:3])
            if any(word in combined_text.lower() for word in ['como', 'que', 'es', 'para']):
                metadata['detected_language'] = 'es'
            elif any(word in combined_text.lower() for word in ['comment', 'que', 'pour', 'dans']):
                metadata['detected_language'] = 'fr'
            
        except Exception as e:
            logger.warning(f"Error extracting metadata: {e}")
        
        return metadata

    def detect_conversation_threads(self, messages: List[ParsedMessage]) -> List[ConversationThread]:
        """Group messages into logical conversation threads"""
        
        if not messages:
            return []
        
        threads = []
        current_thread = []
        
        for i, message in enumerate(messages):
            if self._is_new_thread(message, current_thread):
                if current_thread:
                    thread = self._create_thread(current_thread)
                    threads.append(thread)
                current_thread = [message]
            else:
                current_thread.append(message)
        
        # Add the last thread
        if current_thread:
            thread = self._create_thread(current_thread)
            threads.append(thread)
        
        return threads

    def _is_new_thread(self, message: ParsedMessage, current_thread: List[ParsedMessage]) -> bool:
        """Determine if message starts a new conversation thread"""
        
        if not current_thread:
            return False
        
        last_message = current_thread[-1]
        
        # Time gap detection
        if message.timestamp and last_message.timestamp:
            time_gap = (message.timestamp - last_message.timestamp).total_seconds()
            if time_gap > 3600:  # 1 hour gap
                return True
        
        # Topic change detection
        keywords = ['new', 'different', 'another', 'also', 'separately']
        if any(keyword in message.content.lower() for keyword in keywords):
            return True
        
        return False

    def _create_thread(self, messages: List[ParsedMessage]) -> ConversationThread:
        """Create conversation thread from messages"""
        
        topic_keywords = self._extract_topic_keywords(messages)
        
        start_time = None
        end_time = None
        
        timestamps = [msg.timestamp for msg in messages if msg.timestamp]
        if timestamps:
            start_time = min(timestamps)
            end_time = max(timestamps)
        
        return ConversationThread(
            messages=messages,
            topic_keywords=topic_keywords,
            start_time=start_time,
            end_time=end_time
        )

    def _extract_topic_keywords(self, messages: List[ParsedMessage]) -> List[str]:
        """Extract topic keywords from thread messages"""
        
        # Combine message content
        combined_text = ' '.join(msg.content for msg in messages)
        
        # Common support keywords
        support_keywords = [
            'email', 'imap', 'smtp', 'sync', 'account', 'password', 'login',
            'settings', 'configuration', 'error', 'problem', 'issue',
            'calendar', 'contacts', 'attachment', 'notification', 'setup'
        ]
        
        found_keywords = []
        for keyword in support_keywords:
            if keyword in combined_text.lower():
                found_keywords.append(keyword)
        
        return found_keywords[:5]  # Return top 5 keywords

    def _create_semantic_chunks(self, content: str, chunk_size: int) -> List[str]:
        """Create semantic chunks that preserve conversation boundaries"""
        
        if len(content) <= chunk_size:
            return [content]
        
        # Implementation for semantic chunking
        # This would be implemented based on HTML structure preservation
        chunks = []
        
        # Simple implementation - split by major HTML boundaries
        major_tags = ['<div class="conversation">', '<div class="zd-comment">', 
                     '<div class="intercom-comment">', '<article>', '<section>']
        
        current_chunk = ""
        lines = content.split('\n')
        
        for line in lines:
            if len(current_chunk) + len(line) > chunk_size and current_chunk:
                # Check if this is a good breaking point
                if any(tag in line for tag in major_tags):
                    chunks.append(current_chunk)
                    current_chunk = line + '\n'
                else:
                    current_chunk += line + '\n'
            else:
                current_chunk += line + '\n'
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks