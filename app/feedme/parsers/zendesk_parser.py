"""
Enhanced Zendesk Ticket Parser for FeedMe System

Specialized parser for extracting conversations from Zendesk ticket PDFs
with support for various Zendesk export formats and conversation patterns.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class ZendeskTicket:
    """Parsed Zendesk ticket data"""
    ticket_number: str
    subject: str
    submitted_date: Optional[datetime]
    requester_name: str
    requester_email: str
    assignee: Optional[str]
    status: str
    priority: str
    group: Optional[str]
    license_key: Optional[str]
    country: Optional[str]
    nature_of_enquiry: Optional[str]
    refund_reason: Optional[str]
    conversations: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class ZendeskTicketParser:
    """Specialized parser for Zendesk ticket PDFs"""
    
    def __init__(self):
        self.logger = logger
        
        # Common Zendesk field patterns
        self.field_patterns = {
            'ticket_number': r'#(\d+)\s+(.+?)(?:\n|$)',
            'submitted': r'Submitted\s*\n*([^\n]+)',
            'requester': r'Requester\s*\n*([^<]+?)\s*<([^>]+)>',
            'assignee': r'Assignee\s*\n*([^\n]+)',
            'status': r'Status\s*\n*([^\n]+)',
            'priority': r'Priority\s*\n*([^\n]+)',
            'group': r'Group\s*\n*([^\n]+)',
            'license_key': r'License Key Identifier\s*\n*([^\n]+)',
            'country': r'Country\s*\n*([^\n]+)',
            'nature_of_enquiry': r'Nature of enquiry\s*\n*([^\n]+)',
            'refund_reason': r'Refund Reason\s*\n*([^\n]+)'
        }
        
        # Support agent indicators
        self.support_agent_indicators = [
            'Support', 'Agent', 'Team', 'Mailbird', 'Customer Happiness',
            'Customer Success', 'Technical Support', '@mailbird.com'
        ]
        
        # Customer indicators
        self.customer_indicators = [
            'LLC', 'Inc', 'Corp', 'Company', 'Consulting',
            '@gmail.com', '@yahoo.com', '@hotmail.com', '@outlook.com'
        ]
    
    def parse_zendesk_pdf(self, text: str) -> Optional[ZendeskTicket]:
        """
        Parse a Zendesk ticket PDF and extract structured data
        
        Args:
            text: Raw text content from PDF
            
        Returns:
            ZendeskTicket object or None if parsing fails
        """
        try:
            # Extract ticket metadata
            metadata = self._extract_metadata(text)
            
            # Extract conversations
            conversations = self._extract_conversations(text)
            
            # Build ticket object
            ticket = ZendeskTicket(
                ticket_number=metadata.get('ticket_number', ''),
                subject=metadata.get('subject', ''),
                submitted_date=metadata.get('submitted_date'),
                requester_name=metadata.get('requester_name', ''),
                requester_email=metadata.get('requester_email', ''),
                assignee=metadata.get('assignee'),
                status=metadata.get('status', ''),
                priority=metadata.get('priority', ''),
                group=metadata.get('group'),
                license_key=metadata.get('license_key'),
                country=metadata.get('country'),
                nature_of_enquiry=metadata.get('nature_of_enquiry'),
                refund_reason=metadata.get('refund_reason'),
                conversations=conversations,
                metadata=metadata
            )
            
            self.logger.info(f"Successfully parsed Zendesk ticket #{ticket.ticket_number} with {len(conversations)} conversations")
            return ticket
            
        except Exception as e:
            self.logger.error(f"Failed to parse Zendesk ticket: {e}")
            return None
    
    def _extract_metadata(self, text: str) -> Dict[str, Any]:
        """Extract ticket metadata from header section"""
        metadata = {}
        
        # Extract ticket number and subject
        ticket_match = re.search(self.field_patterns['ticket_number'], text)
        if ticket_match:
            metadata['ticket_number'] = ticket_match.group(1)
            metadata['subject'] = ticket_match.group(2).strip()
        
        # Extract submitted date
        submitted_match = re.search(self.field_patterns['submitted'], text)
        if submitted_match:
            date_str = submitted_match.group(1).strip()
            metadata['submitted_date'] = self._parse_zendesk_date(date_str)
        
        # Extract requester
        requester_match = re.search(self.field_patterns['requester'], text)
        if requester_match:
            metadata['requester_name'] = requester_match.group(1).strip()
            metadata['requester_email'] = requester_match.group(2).strip()
        
        # Extract other fields
        for field, pattern in self.field_patterns.items():
            if field not in ['ticket_number', 'submitted', 'requester']:
                match = re.search(pattern, text)
                if match:
                    metadata[field] = match.group(1).strip()
        
        return metadata
    
    def _extract_conversations(self, text: str) -> List[Dict[str, Any]]:
        """Extract conversation threads from ticket content"""
        conversations = []
        
        # Pattern 1: Standard Zendesk format "Name Date at Time"
        pattern1 = r'([A-Z][^\n]+?)\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}(?:\s*[AP]M)?)\s*\n((?:(?![A-Z][^\n]+?\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}).*\n)*)'
        
        for match in re.finditer(pattern1, text, re.MULTILINE):
            speaker = match.group(1).strip()
            date_str = match.group(2).strip()
            content = match.group(3).strip()
            
            # Skip empty content
            if not content or len(content) < 10:
                continue
            
            # Parse timestamp
            timestamp = self._parse_conversation_date(date_str)
            
            # Determine role
            role = self._determine_speaker_role(speaker, content)
            
            # Clean content
            cleaned_content = self._clean_conversation_content(content)
            
            conversation = {
                'speaker': speaker,
                'role': role,
                'timestamp': timestamp.isoformat() if timestamp else None,
                'content': cleaned_content,
                'raw_content': content,
                'confidence': 0.9
            }
            
            conversations.append(conversation)
        
        # Pattern 2: Email reply format
        if not conversations:
            conversations.extend(self._extract_email_format(text))
        
        return conversations
    
    def _parse_zendesk_date(self, date_str: str) -> Optional[datetime]:
        """Parse Zendesk date formats"""
        date_formats = [
            "%B %d, %Y at %I:%M",  # July 29, 2025 at 11:32
            "%B %d, %Y at %H:%M",  # July 29, 2025 at 23:32
            "%b %d, %Y at %I:%M %p",  # Jul 29, 2025 at 11:32 AM
            "%b %d, %Y at %H:%M",  # Jul 29, 2025 at 23:32
            "%Y-%m-%d %H:%M:%S",  # 2025-07-29 11:32:00
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        
        self.logger.warning(f"Could not parse date: {date_str}")
        return None
    
    def _parse_conversation_date(self, date_str: str) -> Optional[datetime]:
        """Parse conversation timestamp formats"""
        # Handle formats like "August 2, 2025 at 04:04" or "August 2, 2025 at 12:34"
        date_formats = [
            "%B %d, %Y at %H:%M",  # August 2, 2025 at 04:04 (24-hour)
            "%B %d, %Y at %I:%M",  # August 2, 2025 at 04:04 (12-hour)
            "%B %d, %Y at %I:%M %p",  # August 2, 2025 at 04:04 PM
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        
        return self._parse_zendesk_date(date_str)
    
    def _determine_speaker_role(self, speaker: str, content: str) -> str:
        """Determine if speaker is customer or support agent"""
        speaker_lower = speaker.lower()
        content_lower = content.lower()
        
        # Check support agent indicators
        for indicator in self.support_agent_indicators:
            if indicator.lower() in speaker_lower:
                return 'agent'
        
        # Check if content contains support language
        support_phrases = [
            "i hope this message finds you well",
            "my name is",
            "customer happiness team",
            "customer support",
            "i'm here to help",
            "let me know if",
            "feel free to",
            "please don't hesitate",
            "we would like to offer",
            "all the best"
        ]
        
        for phrase in support_phrases:
            if phrase in content_lower:
                return 'agent'
        
        # Check customer indicators
        for indicator in self.customer_indicators:
            if indicator.lower() in speaker_lower:
                return 'customer'
        
        # Default based on position (first message usually from customer)
        return 'customer'
    
    def _clean_conversation_content(self, content: str) -> str:
        """Clean and normalize conversation content"""
        # Remove email signatures
        content = re.sub(r'_{10,}.*?From:.*?$', '', content, flags=re.DOTALL | re.MULTILINE)
        
        # Remove "Support Software by Zendesk" footer
        content = re.sub(r'Support Software by Zendesk.*$', '', content, flags=re.MULTILINE)
        
        # Remove URLs that are just ticket references
        content = re.sub(r'https://mailbird\.zendesk\.com/tickets/\d+/print.*$', '', content, flags=re.MULTILINE)
        
        # Remove excessive whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = re.sub(r' {2,}', ' ', content)
        
        return content.strip()
    
    def _extract_email_format(self, text: str) -> List[Dict[str, Any]]:
        """Extract conversations from email reply format"""
        conversations = []
        
        # Pattern for email format
        email_pattern = r'From:\s*([^<]+?)\s*<([^>]+)>\s*\nSent:\s*([^\n]+)\s*\nTo:\s*([^<]+?)\s*<([^>]+)>\s*\nSubject:\s*([^\n]+)\s*\n(.*?)(?=From:|$)'
        
        for match in re.finditer(email_pattern, text, re.DOTALL | re.MULTILINE):
            from_name = match.group(1).strip()
            from_email = match.group(2).strip()
            date_str = match.group(3).strip()
            content = match.group(7).strip()
            
            # Parse timestamp
            timestamp = self._parse_email_date(date_str)
            
            # Determine role based on email
            role = 'agent' if '@mailbird' in from_email.lower() else 'customer'
            
            conversation = {
                'speaker': from_name,
                'role': role,
                'email': from_email,
                'timestamp': timestamp.isoformat() if timestamp else None,
                'content': self._clean_conversation_content(content),
                'confidence': 0.85
            }
            
            conversations.append(conversation)
        
        return conversations
    
    def _parse_email_date(self, date_str: str) -> Optional[datetime]:
        """Parse email date formats"""
        # Example: "Friday, August 1, 2025 10:04:27 PM"
        date_formats = [
            "%A, %B %d, %Y %I:%M:%S %p",
            "%a, %b %d, %Y %I:%M:%S %p",
            "%A, %B %d, %Y %H:%M:%S",
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        
        return None
    
    def extract_qa_pairs(self, ticket: ZendeskTicket) -> List[Dict[str, Any]]:
        """
        Extract Q&A pairs from parsed ticket conversations
        
        Returns list of Q&A pairs with metadata
        """
        qa_pairs = []
        conversations = ticket.conversations
        
        i = 0
        while i < len(conversations) - 1:
            current = conversations[i]
            next_conv = conversations[i + 1]
            
            # Look for customer question followed by agent response
            if current['role'] == 'customer' and next_conv['role'] == 'agent':
                qa_pair = {
                    'question': current['content'],
                    'answer': next_conv['content'],
                    'customer_name': current['speaker'],
                    'agent_name': next_conv['speaker'],
                    'timestamp': next_conv['timestamp'],
                    'ticket_number': ticket.ticket_number,
                    'ticket_subject': ticket.subject,
                    'metadata': {
                        'license_key': ticket.license_key,
                        'country': ticket.country,
                        'priority': ticket.priority,
                        'nature_of_enquiry': ticket.nature_of_enquiry
                    }
                }
                
                qa_pairs.append(qa_pair)
                i += 2  # Skip the processed pair
            else:
                i += 1
        
        return qa_pairs