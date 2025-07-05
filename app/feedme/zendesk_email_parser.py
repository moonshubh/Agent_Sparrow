"""
Zendesk Email Parser for FeedMe v2.0
High-performance parser for extracting clean Q&A pairs from Zendesk HTML emails

This module provides:
- Fast HTML parsing using selectolax with lxml fallback
- Intelligent noise removal for Zendesk-specific patterns
- Clean extraction of customer/agent interactions
- Performance optimized for <150ms on 100-message threads
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# Primary parser - fast and efficient
try:
    from selectolax.parser import HTMLParser as SelectolaxParser
    SELECTOLAX_AVAILABLE = True
except ImportError:
    SELECTOLAX_AVAILABLE = False
    logging.warning("selectolax not available, using lxml fallback")

# Fallback parser
from lxml import html as lxml_html
from lxml.html.clean import Cleaner

logger = logging.getLogger(__name__)


class InteractionRole(str, Enum):
    """Role of the interaction participant"""
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"


@dataclass
class Interaction:
    """Represents a single interaction in a Zendesk conversation"""
    content: str
    role: InteractionRole
    timestamp: Optional[datetime] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_html: Optional[str] = None
    thread_position: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for compatibility with existing pipeline"""
        return {
            'content': self.content,
            'role': self.role.value,
            'sender': self.sender_name or self.sender_email or 'Unknown',
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'metadata': self.metadata,
            'position': self.thread_position
        }


class ZendeskEmailParser:
    """
    High-performance Zendesk email parser optimized for customer support transcripts
    """
    
    # Zendesk-specific noise patterns to remove
    # CRITICAL FIX: Do NOT remove zd-comment divs - they contain the actual conversation!
    NOISE_PATTERNS = [
        # Email signatures (but be more specific to avoid removing content)
        (re.compile(r'--\s*\n(?:Best regards|Sincerely|Thanks|Sent from my iPhone|Get Outlook).*?(?=\n\n|\n[A-Z]|$)', re.DOTALL | re.IGNORECASE), ''),
        # "On [date] wrote:" headers (but preserve the content after)
        (re.compile(r'On\s+\w+,\s+\w+\s+\d+,\s+\d{4}(?:\s+at\s+\d+:\d+\s*[AP]M)?,.*?wrote:\s*', re.IGNORECASE), ''),
        # "View this ticket" links only
        (re.compile(r'(?:View\s+this\s+ticket|Click\s+here\s+to\s+view)\s+(?:in\s+Zendesk\s*)?:?\s*https?://[^\s]+', re.IGNORECASE), ''),
        # Email footers with unsubscribe links
        (re.compile(r'(?:To\s+unsubscribe|Manage\s+your\s+subscription|Email\s+preferences).*?(?=\n\n|$)', re.DOTALL | re.IGNORECASE), ''),
        # Email header lines (but not conversation content)
        (re.compile(r'^(?:From|To|Subject|Date):\s*.*?\n', re.MULTILINE), ''),
        # Base64 image data
        (re.compile(r'data:image/[^;]+;base64,[^\s"\']+', re.IGNORECASE), '[IMAGE]'),
        # Multiple consecutive newlines
        (re.compile(r'\n{3,}'), '\n\n'),
        # Trailing whitespace
        (re.compile(r'[ \t]+$', re.MULTILINE), ''),
    ]
    
    # Zendesk comment structure patterns
    ZENDESK_COMMENT_SELECTORS = [
        'div.zd-comment',
        'div.zd-liquid-comment', 
        'div.event',
        'article.comment',
        'div[data-comment-id]',
        'div.ticket-comment',
        'div.comment-wrapper'
    ]
    
    # Agent identification patterns
    AGENT_PATTERNS = [
        re.compile(r'@(?:mailbird|support|help|team|agent)', re.IGNORECASE),
        re.compile(r'(?:support|customer\s+service|help\s+desk)\s+team', re.IGNORECASE),
        re.compile(r'\(mailbird\s+(?:support|team|agent)\)', re.IGNORECASE),
    ]
    
    def __init__(self, use_selectolax: bool = True):
        """
        Initialize parser with preferred parsing library
        
        Args:
            use_selectolax: Use selectolax if available (faster), otherwise lxml
        """
        self.use_selectolax = use_selectolax and SELECTOLAX_AVAILABLE
        
        if self.use_selectolax:
            logger.info("Using selectolax parser (high performance)")
        else:
            logger.info("Using lxml parser (fallback)")
            # Configure lxml cleaner for safe HTML parsing
            self.lxml_cleaner = Cleaner(
                scripts=True,
                javascript=True,
                comments=False,  # Keep comments for metadata
                style=False,     # Keep styles for better extraction
                inline_style=False,
                links=False,
                meta=False,
                page_structure=False,
                processing_instructions=True,
                embedded=True,
                frames=True,
                forms=False,
                annoying_tags=False,
                remove_unknown_tags=False,
                safe_attrs_only=False
            )
    
    def parse(self, html_content: str) -> List[Interaction]:
        """
        Parse Zendesk HTML email and extract clean interactions
        
        Args:
            html_content: Raw HTML content from Zendesk
            
        Returns:
            List of Interaction objects representing the conversation
        """
        if not html_content or not html_content.strip():
            logger.warning("Empty HTML content provided")
            return []
        
        # Measure performance
        import time
        start_time = time.time()
        
        try:
            # Pre-process HTML to remove noise
            cleaned_html = self._preprocess_html(html_content)
            
            # Extract interactions based on parser
            if self.use_selectolax:
                interactions = self._parse_with_selectolax(cleaned_html)
            else:
                interactions = self._parse_with_lxml(cleaned_html)
            
            # Post-process interactions
            interactions = self._postprocess_interactions(interactions)
            
            # Log performance
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"Parsed {len(interactions)} interactions in {elapsed_ms:.1f}ms")
            
            return interactions
            
        except Exception as e:
            logger.error(f"Error parsing Zendesk email: {e}")
            # Fallback to basic text extraction
            return self._fallback_text_extraction(html_content)
    
    def _preprocess_html(self, html_content: str) -> str:
        """Apply noise removal patterns before parsing"""
        cleaned = html_content
        
        # Apply all noise patterns
        for pattern, replacement in self.NOISE_PATTERNS:
            cleaned = pattern.sub(replacement, cleaned)
        
        return cleaned
    
    def _parse_with_selectolax(self, html_content: str) -> List[Interaction]:
        """Parse using selectolax (faster)"""
        interactions = []
        parser = SelectolaxParser(html_content)
        
        # Try to find Zendesk comment structures
        for selector in self.ZENDESK_COMMENT_SELECTORS:
            comments = parser.css(selector)
            if comments:
                logger.debug(f"Found {len(comments)} comments using selector: {selector}")
                break
        else:
            # Fallback to generic message detection
            comments = parser.css('div.message, div.comment, article, blockquote')
        
        thread_position = 0
        for comment in comments:
            # Extract comment metadata
            metadata = self._extract_selectolax_metadata(comment)
            
            # Extract text content
            text_content = comment.text(strip=True)
            if not text_content or len(text_content) < 10:
                continue
            
            # Clean the text
            text_content = self._clean_text_content(text_content)
            
            # Determine role
            role = self._determine_role(text_content, metadata)
            
            # Extract sender info
            sender_name, sender_email = self._extract_sender_info_selectolax(comment)
            
            # Extract timestamp
            timestamp = self._extract_timestamp_selectolax(comment)
            
            interaction = Interaction(
                content=text_content,
                role=role,
                timestamp=timestamp,
                sender_name=sender_name,
                sender_email=sender_email,
                metadata=metadata,
                raw_html=str(comment.html),
                thread_position=thread_position
            )
            
            interactions.append(interaction)
            thread_position += 1
        
        # Clean up parser (selectolax doesn't need explicit cleanup)
        
        return interactions
    
    def _parse_with_lxml(self, html_content: str) -> List[Interaction]:
        """Parse using lxml (fallback)"""
        interactions = []
        
        # Clean HTML for safety
        cleaned_html = self.lxml_cleaner.clean_html(html_content)
        tree = lxml_html.fromstring(cleaned_html)
        
        # Try Zendesk selectors
        comments = None
        for selector in self.ZENDESK_COMMENT_SELECTORS:
            comments = tree.cssselect(selector)
            if comments:
                logger.debug(f"Found {len(comments)} comments using selector: {selector}")
                break
        
        if not comments:
            # Fallback to XPath for more complex selection
            comments = tree.xpath('//div[contains(@class, "comment") or contains(@class, "message") or contains(@class, "event")]')
        
        thread_position = 0
        for comment in comments:
            # Extract metadata
            metadata = self._extract_lxml_metadata(comment)
            
            # Extract text content
            text_content = ' '.join(comment.itertext()).strip()
            if not text_content or len(text_content) < 10:
                continue
            
            # Clean the text
            text_content = self._clean_text_content(text_content)
            
            # Determine role
            role = self._determine_role(text_content, metadata)
            
            # Extract sender info
            sender_name, sender_email = self._extract_sender_info_lxml(comment)
            
            # Extract timestamp
            timestamp = self._extract_timestamp_lxml(comment)
            
            interaction = Interaction(
                content=text_content,
                role=role,
                timestamp=timestamp,
                sender_name=sender_name,
                sender_email=sender_email,
                metadata=metadata,
                raw_html=lxml_html.tostring(comment, encoding='unicode'),
                thread_position=thread_position
            )
            
            interactions.append(interaction)
            thread_position += 1
        
        return interactions
    
    def _clean_text_content(self, text: str) -> str:
        """Clean extracted text content"""
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        # Remove common Zendesk artifacts
        artifacts = [
            'Click here to add a comment',
            'Type your comment here',
            'Add internal note',
            '▾',  # Dropdown indicators
            '...',  # Loading indicators
        ]
        
        for artifact in artifacts:
            text = text.replace(artifact, '')
        
        return text.strip()
    
    def _determine_role(self, text: str, metadata: Dict[str, Any]) -> InteractionRole:
        """Determine if interaction is from customer or agent"""
        # Check metadata first
        if metadata.get('is_public') is False:
            return InteractionRole.AGENT
        
        if metadata.get('author_role') in ['agent', 'admin', 'staff']:
            return InteractionRole.AGENT
        
        # Enhanced agent detection for Zendesk emails
        agent_indicators = [
            # Signature patterns
            r'All the best,\s*[A-Z][a-z]+ [A-Z][a-z]+',
            r'Best regards,\s*[A-Z][a-z]+ [A-Z][a-z]+',
            r'[A-Z][a-z]+ [A-Z][a-z]+\s*\(Mailbird\)',
            r'[A-Z][a-z]+ [A-Z][a-z]+\s*\(.*Support.*\)',
            # Professional language patterns
            r'(?:I understand|I apologize|Thank you for|I appreciate)',
            r'(?:Let me help|I can help|I\'ll help|Here\'s how)',
            r'(?:Please try|Please follow|Please let me know)',
            r'(?:I recommend|I suggest|I advise)',
            # Solution patterns
            r'(?:Here are the steps|Follow these steps|To resolve)',
            r'(?:You can|You should|Try this)',
            # Mailbird-specific
            r'(?:Mailbird|support\.getmailbird\.com)',
        ]
        
        # Count agent indicators
        agent_score = 0
        for pattern in agent_indicators:
            if re.search(pattern, text, re.IGNORECASE):
                agent_score += 1
        
        # Check for explicit customer indicators
        customer_indicators = [
            r'(?:I have a problem|I\'m having trouble|I need help)',
            r'(?:Can you help|Please help|Could you)',
            r'(?:It doesn\'t work|Not working|Broken)',
            r'(?:I tried|I attempted|I followed)',
            # Frustrated language
            r'(?:annoyed|frustrated|confused|waste of time)',
        ]
        
        customer_score = 0
        for pattern in customer_indicators:
            if re.search(pattern, text, re.IGNORECASE):
                customer_score += 1
        
        # Check original patterns for additional agent detection
        for pattern in self.AGENT_PATTERNS:
            if pattern.search(text):
                agent_score += 2  # Weight these higher
        
        # Check for system messages
        system_indicators = ['automated', 'system', 'notification', 'status changed']
        if any(indicator in text.lower() for indicator in system_indicators):
            return InteractionRole.SYSTEM
        
        # Determine role based on scores
        if agent_score >= 2 or agent_score > customer_score:
            return InteractionRole.AGENT
        elif customer_score > 0:
            return InteractionRole.CUSTOMER
        
        # Default to customer for unclear cases
        return InteractionRole.CUSTOMER
    
    def _extract_selectolax_metadata(self, element) -> Dict[str, Any]:
        """Extract metadata from selectolax element"""
        metadata = {}
        
        # Extract data attributes
        if hasattr(element, 'attrs'):
            for attr, value in element.attrs.items():
                if attr.startswith('data-'):
                    metadata[attr[5:]] = value
        
        # Extract CSS classes
        css_classes = element.attrs.get('class', '').split()
        metadata['css_classes'] = css_classes
        
        # Check for internal/public status
        if 'internal' in css_classes or 'private' in css_classes:
            metadata['is_public'] = False
        
        return metadata
    
    def _extract_lxml_metadata(self, element) -> Dict[str, Any]:
        """Extract metadata from lxml element"""
        metadata = {}
        
        # Extract data attributes
        for attr, value in element.attrib.items():
            if attr.startswith('data-'):
                metadata[attr[5:]] = value
        
        # Extract CSS classes
        css_classes = element.get('class', '').split()
        metadata['css_classes'] = css_classes
        
        # Check for internal/public status
        if 'internal' in css_classes or 'private' in css_classes:
            metadata['is_public'] = False
        
        return metadata
    
    def _extract_sender_info_selectolax(self, element) -> Tuple[Optional[str], Optional[str]]:
        """Extract sender name and email from selectolax element"""
        sender_name = None
        sender_email = None
        
        # Look for author information in standard places
        author_elem = element.css_first('.author, .comment-author, [data-author-name]')
        if author_elem:
            sender_name = author_elem.text(strip=True)
        
        # Look for email in standard places
        email_elem = element.css_first('.email, [data-author-email]')
        if email_elem:
            sender_email = email_elem.text(strip=True)
        
        # Enhanced text-based extraction for Zendesk emails
        text = element.text()
        
        # Extract email addresses from anywhere in the text
        if not sender_email:
            email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
            if email_match:
                sender_email = email_match.group(1)
        
        # Extract sender name from signature patterns
        if not sender_name:
            signature_patterns = [
                r'All the best,\s*([A-Z][a-z]+(?: [A-Z][a-z]+)*)',
                r'Best regards,\s*([A-Z][a-z]+(?: [A-Z][a-z]+)*)',
                r'Thanks,\s*([A-Z][a-z]+)',
                r'Sincerely,\s*([A-Z][a-z]+(?: [A-Z][a-z]+)*)',
                r'([A-Z][a-z]+ [A-Z][a-z]+)\s*\(Mailbird\)',
                r'([A-Z][a-z]+ [A-Z][a-z]+)\s*\(.*Support.*\)'
            ]
            
            for pattern in signature_patterns:
                match = re.search(pattern, text)
                if match:
                    sender_name = match.group(1).strip()
                    break
        
        # Extract from greeting patterns (who is being addressed)
        if not sender_name:
            greeting_patterns = [
                r'(?:Hi|Hello|Hey)\s+([A-Z][a-z]+)',
                r'Dear\s+([A-Z][a-z]+)',
            ]
            
            for pattern in greeting_patterns:
                match = re.search(pattern, text)
                if match:
                    # This is who is being addressed, not the sender
                    # But useful for context
                    break
        
        # Look in parent elements for structured data (tables, etc.)
        if not sender_name and not sender_email:
            # Get the HTML content to search in parent context
            html_content = str(element.html) if hasattr(element, 'html') else ""
            
            # Look for email in HTML
            if not sender_email:
                email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', html_content)
                if email_match:
                    sender_email = email_match.group(1)
        
        return sender_name, sender_email
    
    def _extract_sender_info_lxml(self, element) -> Tuple[Optional[str], Optional[str]]:
        """Extract sender name and email from lxml element"""
        sender_name = None
        sender_email = None
        
        # Look for author information
        author_elems = element.cssselect('.author, .comment-author, [data-author-name]')
        if author_elems:
            sender_name = author_elems[0].text_content().strip()
        
        # Look for email
        email_elems = element.cssselect('.email, [data-author-email]')
        if email_elems:
            sender_email = email_elems[0].text_content().strip()
        
        # Extract from text patterns
        if not sender_email:
            text = element.text_content()
            email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
            if email_match:
                sender_email = email_match.group(1)
        
        return sender_name, sender_email
    
    def _extract_timestamp_selectolax(self, element) -> Optional[datetime]:
        """Extract timestamp from selectolax element"""
        # Look for time elements
        time_elem = element.css_first('time, .timestamp, .date, [data-timestamp]')
        if time_elem:
            # Try datetime attribute first
            datetime_str = time_elem.attrs.get('datetime')
            if datetime_str:
                return self._parse_datetime(datetime_str)
            
            # Try data-timestamp
            timestamp = time_elem.attrs.get('data-timestamp')
            if timestamp:
                try:
                    return datetime.fromtimestamp(int(timestamp))
                except:
                    pass
            
            # Try text content
            return self._parse_datetime(time_elem.text(strip=True))
        
        return None
    
    def _extract_timestamp_lxml(self, element) -> Optional[datetime]:
        """Extract timestamp from lxml element"""
        # Look for time elements
        time_elems = element.cssselect('time, .timestamp, .date, [data-timestamp]')
        if time_elems:
            time_elem = time_elems[0]
            
            # Try datetime attribute first
            datetime_str = time_elem.get('datetime')
            if datetime_str:
                return self._parse_datetime(datetime_str)
            
            # Try data-timestamp
            timestamp = time_elem.get('data-timestamp')
            if timestamp:
                try:
                    return datetime.fromtimestamp(int(timestamp))
                except:
                    pass
            
            # Try text content
            return self._parse_datetime(time_elem.text_content().strip())
        
        return None
    
    def _parse_datetime(self, datetime_str: str) -> Optional[datetime]:
        """Parse datetime from various formats"""
        if not datetime_str:
            return None
        
        # Common datetime formats
        formats = [
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%m/%d/%Y %I:%M %p',
            '%d %b %Y %H:%M',
            '%B %d, %Y at %I:%M %p',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(datetime_str, fmt)
            except:
                continue
        
        return None
    
    def _postprocess_interactions(self, interactions: List[Interaction]) -> List[Interaction]:
        """Post-process interactions to ensure quality"""
        processed = []
        
        for interaction in interactions:
            # Skip empty or too short interactions
            if len(interaction.content) < 20:
                continue
            
            # Skip duplicate consecutive messages
            if processed and processed[-1].content == interaction.content:
                continue
            
            # Merge system messages with next interaction if appropriate
            if interaction.role == InteractionRole.SYSTEM and processed:
                # Add as metadata to previous interaction
                processed[-1].metadata['system_note'] = interaction.content
                continue
            
            processed.append(interaction)
        
        return processed
    
    def _fallback_text_extraction(self, html_content: str) -> List[Interaction]:
        """Basic text extraction when parsing fails"""
        try:
            # Strip all HTML tags
            text = re.sub(r'<[^>]+>', ' ', html_content)
            text = ' '.join(text.split())
            
            # Split into paragraphs
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
            
            interactions = []
            for i, para in enumerate(paragraphs):
                if len(para) < 20:
                    continue
                
                # Simple role detection
                role = InteractionRole.AGENT if any(p.search(para) for p in self.AGENT_PATTERNS) else InteractionRole.CUSTOMER
                
                interactions.append(Interaction(
                    content=para,
                    role=role,
                    thread_position=i
                ))
            
            return interactions
            
        except Exception as e:
            logger.error(f"Fallback extraction failed: {e}")
            return []


def extract_qa_pairs(interactions: List[Interaction]) -> List[Dict[str, Any]]:
    """
    Convert interactions to Q&A pairs for the AI extraction engine
    Enhanced to handle email thread structure and mixed conversation patterns
    
    Args:
        interactions: List of parsed interactions
        
    Returns:
        List of Q&A pair dictionaries compatible with existing pipeline
    """
    qa_pairs = []
    
    # Strategy 1: Look for customer question followed by agent answer
    i = 0
    while i < len(interactions):
        current = interactions[i]
        
        # Look for customer question followed by agent answer
        if current.role == InteractionRole.CUSTOMER and i + 1 < len(interactions):
            next_interaction = interactions[i + 1]
            
            if next_interaction.role == InteractionRole.AGENT:
                # Extract context
                context_before = interactions[i - 1].content if i > 0 else ""
                context_after = interactions[i + 2].content if i + 2 < len(interactions) else ""
                
                qa_pair = {
                    'question_text': current.content,
                    'answer_text': next_interaction.content,
                    'context_before': context_before,
                    'context_after': context_after,
                    'confidence_score': 0.85,  # High confidence for clear Q&A pattern
                    'metadata': {
                        'customer_email': current.sender_email,
                        'agent_name': next_interaction.sender_name,
                        'timestamp': current.timestamp.isoformat() if current.timestamp else None,
                        'source': 'zendesk_email'
                    }
                }
                qa_pairs.append(qa_pair)
                i += 2  # Skip the answer we just processed
                continue
        
        i += 1
    
    # Strategy 2: Look for customer issues/problems even if not followed immediately by agent response
    # In email threads, the agent response might be earlier in the thread
    customer_issues = []
    agent_responses = []
    
    for interaction in interactions:
        content_lower = interaction.content.lower()
        
        # Identify customer issues/questions
        if interaction.role == InteractionRole.CUSTOMER:
            issue_indicators = [
                'problem', 'issue', 'trouble', 'error', 'not working', 'broken',
                'can\'t', 'cannot', 'unable', 'won\'t', 'doesn\'t', 'failed',
                'help', 'please', '?', 'how', 'why', 'what'
            ]
            
            issue_score = sum(1 for indicator in issue_indicators if indicator in content_lower)
            
            if issue_score >= 2 or '?' in interaction.content:
                customer_issues.append(interaction)
        
        # Identify agent solutions/responses
        elif interaction.role == InteractionRole.AGENT:
            solution_indicators = [
                'try', 'follow', 'steps', 'solution', 'resolve', 'fix',
                'here\'s how', 'you can', 'please try', 'i recommend',
                'to solve', 'to fix'
            ]
            
            solution_score = sum(1 for indicator in solution_indicators if indicator in content_lower)
            
            if solution_score >= 2:
                agent_responses.append(interaction)
    
    # Match customer issues with agent responses based on content similarity
    for customer_issue in customer_issues:
        # Check if we already paired this in Strategy 1
        already_paired = any(qa['question_text'] == customer_issue.content for qa in qa_pairs)
        if already_paired:
            continue
        
        # Find the best matching agent response
        best_response = None
        best_similarity = 0
        
        for agent_response in agent_responses:
            # Simple similarity based on common words
            customer_words = set(customer_issue.content.lower().split())
            agent_words = set(agent_response.content.lower().split())
            
            # Remove common stop words
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
            customer_words -= stop_words
            agent_words -= stop_words
            
            if customer_words and agent_words:
                similarity = len(customer_words.intersection(agent_words)) / len(customer_words.union(agent_words))
                
                if similarity > best_similarity and similarity > 0.1:  # At least 10% word overlap
                    best_similarity = similarity
                    best_response = agent_response
        
        if best_response:
            qa_pair = {
                'question_text': customer_issue.content,
                'answer_text': best_response.content,
                'context_before': '',
                'context_after': '',
                'confidence_score': 0.7 + (best_similarity * 0.2),  # 0.7-0.9 based on similarity
                'metadata': {
                    'customer_email': customer_issue.sender_email,
                    'agent_name': best_response.sender_name,
                    'timestamp': customer_issue.timestamp.isoformat() if customer_issue.timestamp else None,
                    'source': 'zendesk_email',
                    'extraction_method': 'similarity_matching',
                    'similarity_score': best_similarity
                }
            }
            qa_pairs.append(qa_pair)
    
    return qa_pairs