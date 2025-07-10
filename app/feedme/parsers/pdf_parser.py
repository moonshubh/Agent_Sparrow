"""
PDF Parser for FeedMe System

This module provides PDF parsing capabilities for extracting text and metadata
from PDF documents, particularly Zendesk ticket PDFs.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from abc import ABC, abstractmethod
import pdfplumber
from pypdf import PdfReader
import io

logger = logging.getLogger(__name__)


@dataclass
class PageContent:
    """Content extracted from a single PDF page"""
    page_number: int
    text: str
    char_count: int
    has_tables: bool = False
    table_data: Optional[List[List[str]]] = None


@dataclass
class PDFMetadata:
    """Metadata extracted from PDF document"""
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator: Optional[str] = None
    producer: Optional[str] = None
    creation_date: Optional[datetime] = None
    modification_date: Optional[datetime] = None
    pages: int = 0
    encrypted: bool = False


@dataclass
class ConversationThread:
    """Represents a conversation thread in PDF"""
    speaker: str
    role: str  # 'customer' or 'agent'
    content: str
    timestamp: Optional[datetime]
    page_number: int
    thread_id: str
    confidence: float


@dataclass
class PDFConversationResult:
    """Result of PDF parsing with conversation detection"""
    success: bool
    conversations: List[ConversationThread]
    metadata: PDFMetadata
    raw_text: str
    processing_time_ms: float
    error_message: Optional[str] = None
    warnings: List[str] = None


@dataclass
class PDFParseResult:
    """Complete result of PDF parsing operation"""
    success: bool
    pages: List[PageContent]
    metadata: PDFMetadata
    total_text: str
    total_chars: int
    processing_time_ms: float
    error_message: Optional[str] = None
    warnings: List[str] = None


class PDFParser(ABC):
    """
    High-performance PDF parser optimized for Zendesk ticket PDFs.
    
    Features:
    - Text extraction with page boundaries preserved
    - Metadata extraction
    - Table detection and extraction
    - Error handling for corrupted PDFs
    - Performance optimized for <300ms processing
    """
    
    def __init__(self, max_pages: int = 100, timeout_seconds: int = 30):
        self.max_pages = max_pages
        self.timeout_seconds = timeout_seconds
    
    @abstractmethod
    async def parse_pdf(self, file_content: bytes) -> PDFParseResult:
        """
        Parse PDF content and extract text with metadata.
        
        Args:
            file_content: Raw PDF file bytes
            
        Returns:
            PDFParseResult with extracted content and metadata
        """
        pass


class EnhancedPDFParser(PDFParser):
    """Enhanced PDF parser with conversation detection capabilities"""
    
    def __init__(self, max_pages: int = 100, timeout_seconds: int = 30):
        super().__init__(max_pages, timeout_seconds)
        
        # Conversation detection patterns
        self.conversation_patterns = [
            # Email thread patterns
            r'From:\s*(.+?)\s*<(.+?)>',
            r'To:\s*(.+?)\s*<(.+?)>',
            r'Subject:\s*(.+)',
            r'Date:\s*(.+)',
            # Zendesk ticket patterns
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+\(.*?\)\s*\n(.+?)(?=\n[A-Z][a-z]+\s+[A-Z][a-z]+|\Z)',
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(.+?)(?=\n[A-Z][a-z]+\s+[A-Z][a-z]+|\Z)',
            # Timestamp patterns
            r'(\w+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2})',
            r'(\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2})',
        ]
    
    async def parse_pdf_with_conversations(self, content: bytes) -> PDFConversationResult:
        """Parse PDF with conversation thread detection"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Extract basic text and pages
            basic_result = await self.parse_pdf(content)
            
            if not basic_result.success:
                return PDFConversationResult(
                    success=False,
                    conversations=[],
                    metadata=basic_result.metadata,
                    raw_text="",
                    processing_time_ms=0,
                    error_message=basic_result.error_message
                )
            
            # Detect conversation threads
            conversations = []
            for page in basic_result.pages:
                page_conversations = self._extract_conversations_from_page(page)
                conversations.extend(page_conversations)
            
            # Merge multi-page conversations
            merged_conversations = self._merge_conversation_threads(conversations)
            
            processing_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            
            return PDFConversationResult(
                success=True,
                conversations=merged_conversations,
                metadata=basic_result.metadata,
                raw_text=basic_result.total_text,
                processing_time_ms=processing_time_ms
            )
            
        except Exception as e:
            error_msg = f"Enhanced PDF parsing failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            processing_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            
            return PDFConversationResult(
                success=False,
                conversations=[],
                metadata=PDFMetadata(),
                raw_text="",
                processing_time_ms=processing_time_ms,
                error_message=error_msg
            )
    
    def _extract_conversations_from_page(self, page: PageContent) -> List[ConversationThread]:
        """Extract conversation threads from a single page"""
        conversations = []
        text = page.text
        
        # Strategy 1: Email thread detection
        email_threads = self._extract_email_threads(text, page.page_number)
        conversations.extend(email_threads)
        
        # Strategy 2: Zendesk ticket format detection
        if not email_threads:
            ticket_threads = self._extract_zendesk_threads(text, page.page_number)
            conversations.extend(ticket_threads)
        
        # Strategy 3: Generic Q&A pattern detection
        if not conversations:
            qa_threads = self._extract_qa_patterns(text, page.page_number)
            conversations.extend(qa_threads)
        
        return conversations
    
    def _extract_email_threads(self, text: str, page_num: int) -> List[ConversationThread]:
        """Extract email conversation threads"""
        threads = []
        
        # Split by email headers
        email_pattern = r'From:\s*(.+?)\s*<(.+?)>\s*\n.*?To:\s*(.+?)\s*<(.+?)>\s*\n.*?Subject:\s*(.+?)\s*\n.*?Date:\s*(.+?)\s*\n(.*?)(?=From:|$)'
        
        for match in re.finditer(email_pattern, text, re.DOTALL | re.IGNORECASE):
            from_name, from_email, to_name, to_email, subject, date_str, content = match.groups()
            
            # Determine role based on email address
            role = self._determine_role_from_email(from_email)
            
            # Parse timestamp
            timestamp = self._parse_timestamp(date_str)
            
            thread = ConversationThread(
                speaker=from_name.strip(),
                role=role,
                content=content.strip(),
                timestamp=timestamp,
                page_number=page_num,
                thread_id=f"email_{hash(from_email)}_{timestamp}",
                confidence=0.9
            )
            threads.append(thread)
        
        return threads
    
    def _extract_zendesk_threads(self, text: str, page_num: int) -> List[ConversationThread]:
        """Extract Zendesk ticket conversation threads"""
        threads = []
        
        # Pattern for Zendesk ticket format: "Name (Role) \n Date \n Content"
        zendesk_pattern = r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*(?:\((.+?)\))?\s*\n(.+?)\n(.*?)(?=\n[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*(?:\(|$)|\Z)'
        
        for match in re.finditer(zendesk_pattern, text, re.DOTALL):
            name, role_hint, date_str, content = match.groups()
            
            # Determine role
            role = self._determine_role_from_context(name, role_hint, content)
            
            # Parse timestamp
            timestamp = self._parse_timestamp(date_str)
            
            thread = ConversationThread(
                speaker=name.strip(),
                role=role,
                content=content.strip(),
                timestamp=timestamp,
                page_number=page_num,
                thread_id=f"zendesk_{hash(name)}_{timestamp}",
                confidence=0.85
            )
            threads.append(thread)
        
        return threads
    
    def _extract_qa_patterns(self, text: str, page_num: int) -> List[ConversationThread]:
        """Extract generic Q&A patterns as fallback"""
        threads = []
        
        # Simple pattern for alternating speakers
        lines = text.split('\n')
        current_speaker = None
        current_content = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if this line starts a new speaker
            speaker_match = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*[:\-]?\s*(.*)$', line)
            
            if speaker_match and len(speaker_match.group(1).split()) <= 3:
                # Save previous speaker's content
                if current_speaker and current_content:
                    content = '\n'.join(current_content).strip()
                    if len(content) > 20:  # Minimum content length
                        role = self._determine_role_from_context(current_speaker, None, content)
                        thread = ConversationThread(
                            speaker=current_speaker,
                            role=role,
                            content=content,
                            timestamp=None,
                            page_number=page_num,
                            thread_id=f"qa_{hash(current_speaker)}_{page_num}",
                            confidence=0.6
                        )
                        threads.append(thread)
                
                # Start new speaker
                current_speaker = speaker_match.group(1)
                current_content = [speaker_match.group(2)] if speaker_match.group(2) else []
            else:
                # Continue current speaker's content
                if current_speaker:
                    current_content.append(line)
        
        # Handle last speaker
        if current_speaker and current_content:
            content = '\n'.join(current_content).strip()
            if len(content) > 20:
                role = self._determine_role_from_context(current_speaker, None, content)
                thread = ConversationThread(
                    speaker=current_speaker,
                    role=role,
                    content=content,
                    timestamp=None,
                    page_number=page_num,
                    thread_id=f"qa_{hash(current_speaker)}_{page_num}",
                    confidence=0.6
                )
                threads.append(thread)
        
        return threads
    
    def _determine_role_from_email(self, email: str) -> str:
        """Determine role based on email address"""
        email_lower = email.lower()
        if any(domain in email_lower for domain in ['support', 'help', 'mailbird', 'agent']):
            return 'agent'
        return 'customer'
    
    def _determine_role_from_context(self, name: str, role_hint: str, content: str) -> str:
        """Determine role based on context clues"""
        # Check role hint first
        if role_hint and any(hint in role_hint.lower() for hint in ['support', 'agent', 'mailbird']):
            return 'agent'
        
        # Check content for agent patterns
        agent_patterns = [
            r'(?:I understand|I apologize|Thank you for|I appreciate)',
            r'(?:Let me help|I can help|I\'ll help|Here\'s how)',
            r'(?:Please try|Please follow|Please let me know)',
            r'(?:All the best|Best regards),\s*' + re.escape(name)
        ]
        
        agent_score = sum(1 for pattern in agent_patterns if re.search(pattern, content, re.IGNORECASE))
        
        return 'agent' if agent_score >= 2 else 'customer'
    
    def _parse_timestamp(self, date_str: str) -> Optional[datetime]:
        """Parse timestamp from various formats"""
        if not date_str:
            return None
        
        # Common datetime formats
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%m/%d/%Y %I:%M %p',
            '%d %b %Y %H:%M',
            '%B %d, %Y at %I:%M %p',
            '%b %d, %Y at %I:%M %p',
            '%B %d, %Y, %I:%M %p',
            '%m/%d/%y, %I:%M %p',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        
        return None
    
    def _merge_conversation_threads(self, conversations: List[ConversationThread]) -> List[ConversationThread]:
        """Merge conversation threads that span multiple pages"""
        if not conversations:
            return []
        
        # Sort by timestamp and page number
        sorted_conversations = sorted(conversations, key=lambda x: (x.timestamp or datetime.min, x.page_number))
        
        merged = []
        current_thread = None
        
        for conv in sorted_conversations:
            if self._should_merge_with_current(conv, current_thread):
                # Merge with current thread
                current_thread.content += f"\n\n{conv.content}"
                current_thread.confidence = max(current_thread.confidence, conv.confidence)
            else:
                # Start new thread
                if current_thread:
                    merged.append(current_thread)
                current_thread = conv
        
        # Add last thread
        if current_thread:
            merged.append(current_thread)
        
        return merged
    
    def _should_merge_with_current(self, conv: ConversationThread, current: Optional[ConversationThread]) -> bool:
        """Determine if conversation should be merged with current thread"""
        if not current:
            return False
        
        # Same speaker and close timestamps
        if (conv.speaker == current.speaker and 
            conv.timestamp and current.timestamp and
            abs((conv.timestamp - current.timestamp).total_seconds()) < 300):  # 5 minutes
            return True
        
        # Same speaker on consecutive pages
        if (conv.speaker == current.speaker and 
            conv.page_number == current.page_number + 1):
            return True
        
        return False
    
    async def parse_pdf(self, file_content: bytes) -> PDFParseResult:
        """
        Parse PDF content and extract text with metadata.
        
        Args:
            file_content: Raw PDF file bytes
            
        Returns:
            PDFParseResult with extracted content and metadata
        """
        start_time = asyncio.get_event_loop().time()
        warnings = []
        
        try:
            # Run CPU-intensive parsing in thread pool
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._parse_pdf_sync, file_content),
                timeout=self.timeout_seconds
            )
            
            processing_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            result.processing_time_ms = processing_time_ms
            
            # Log performance metrics
            logger.info(f"PDF parsed successfully: {result.metadata.pages} pages, "
                       f"{result.total_chars} chars in {processing_time_ms:.2f}ms")
            
            return result
            
        except asyncio.TimeoutError:
            error_msg = f"PDF parsing timed out after {self.timeout_seconds} seconds"
            logger.error(error_msg)
            return self._create_error_result(error_msg, start_time)
            
        except Exception as e:
            error_msg = f"PDF parsing failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return self._create_error_result(error_msg, start_time)
    
    def _parse_pdf_sync(self, file_content: bytes) -> PDFParseResult:
        """Synchronous PDF parsing implementation"""
        warnings = []
        pages = []
        
        # Extract metadata using pypdf
        metadata = self._extract_metadata(file_content)
        
        # Extract text using pdfplumber for better accuracy
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                # Limit pages to prevent memory issues
                num_pages = min(len(pdf.pages), self.max_pages)
                if len(pdf.pages) > self.max_pages:
                    warnings.append(f"PDF has {len(pdf.pages)} pages, processing first {self.max_pages}")
                
                metadata.pages = len(pdf.pages)
                
                # Extract text from each page
                for i, page in enumerate(pdf.pages[:num_pages], 1):
                    page_content = self._extract_page_content(page, i)
                    pages.append(page_content)
                
                # Combine all text
                total_text = "\n\n".join(p.text for p in pages if p.text)
                total_chars = sum(p.char_count for p in pages)
                
                return PDFParseResult(
                    success=True,
                    pages=pages,
                    metadata=metadata,
                    total_text=total_text,
                    total_chars=total_chars,
                    processing_time_ms=0,  # Will be set by async wrapper
                    warnings=warnings if warnings else None
                )
                
        except Exception as e:
            raise Exception(f"Failed to extract text: {str(e)}")
    
    def _extract_metadata(self, file_content: bytes) -> PDFMetadata:
        """Extract metadata from PDF using pypdf"""
        metadata = PDFMetadata()
        
        try:
            reader = PdfReader(io.BytesIO(file_content))
            
            # Basic info
            metadata.pages = len(reader.pages)
            metadata.encrypted = reader.is_encrypted
            
            # Document info if available
            if reader.metadata:
                info = reader.metadata
                metadata.title = self._safe_str(info.get('/Title'))
                metadata.author = self._safe_str(info.get('/Author'))
                metadata.subject = self._safe_str(info.get('/Subject'))
                metadata.creator = self._safe_str(info.get('/Creator'))
                metadata.producer = self._safe_str(info.get('/Producer'))
                
                # Parse dates
                if '/CreationDate' in info:
                    metadata.creation_date = self._parse_pdf_date(info['/CreationDate'])
                if '/ModDate' in info:
                    metadata.modification_date = self._parse_pdf_date(info['/ModDate'])
                    
        except Exception as e:
            logger.warning(f"Failed to extract metadata: {str(e)}")
            
        return metadata
    
    def _extract_page_content(self, page, page_number: int) -> PageContent:
        """Extract content from a single page"""
        try:
            # Extract text
            text = page.extract_text() or ""
            
            # Clean up text
            text = self._clean_text(text)
            
            # Check for tables
            tables = page.extract_tables()
            has_tables = bool(tables)
            table_data = None
            
            if has_tables and tables:
                # Convert first table to list format
                table_data = tables[0] if tables else None
                
                # Add table content to text
                table_text = self._format_table_as_text(table_data)
                if table_text:
                    text += f"\n\n[Table Content]\n{table_text}"
            
            return PageContent(
                page_number=page_number,
                text=text,
                char_count=len(text),
                has_tables=has_tables,
                table_data=table_data
            )
            
        except Exception as e:
            logger.warning(f"Failed to extract content from page {page_number}: {str(e)}")
            return PageContent(
                page_number=page_number,
                text="[Page extraction failed]",
                char_count=0
            )
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize extracted text"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Remove leading/trailing whitespace
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            # Normalize internal whitespace
            line = ' '.join(line.split())
            
            cleaned_lines.append(line)
        
        # Join with single newlines
        return '\n'.join(cleaned_lines)
    
    def _format_table_as_text(self, table_data: List[List[str]]) -> str:
        """Format table data as readable text"""
        if not table_data:
            return ""
        
        lines = []
        for row in table_data:
            if row and any(cell for cell in row if cell):
                # Join non-empty cells with | separator
                row_text = " | ".join(str(cell) if cell else "" for cell in row)
                lines.append(row_text)
        
        return '\n'.join(lines)
    
    def _safe_str(self, value: Any) -> Optional[str]:
        """Safely convert PDF metadata value to string"""
        if value is None:
            return None
        
        try:
            # Handle bytes
            if isinstance(value, bytes):
                return value.decode('utf-8', errors='ignore')
            
            # Convert to string
            return str(value)
        except (UnicodeDecodeError, TypeError):
            return None
    
    def _parse_pdf_date(self, date_string: Any) -> Optional[datetime]:
        """Parse PDF date format (D:YYYYMMDDHHmmSS)"""
        if not date_string:
            return None
        
        try:
            # Convert to string if needed
            if hasattr(date_string, 'original_bytes'):
                date_str = date_string.original_bytes.decode('utf-8', errors='ignore')
            else:
                date_str = str(date_string)
            
            # Remove D: prefix if present
            if date_str.startswith('D:'):
                date_str = date_str[2:]
            
            # Parse basic format (might have timezone info at end)
            # Take first 14 characters for YYYYMMDDHHmmSS
            date_str = date_str[:14]
            
            if len(date_str) >= 8:
                # At minimum parse YYYYMMDD
                year = int(date_str[0:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])
                
                hour = int(date_str[8:10]) if len(date_str) >= 10 else 0
                minute = int(date_str[10:12]) if len(date_str) >= 12 else 0
                second = int(date_str[12:14]) if len(date_str) >= 14 else 0
                
                return datetime(year, month, day, hour, minute, second)
                
        except Exception as e:
            logger.debug(f"Failed to parse PDF date '{date_string}': {str(e)}")
            
        return None
    
    def _create_error_result(self, error_message: str, start_time: float) -> PDFParseResult:
        """Create error result object"""
        processing_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        
        return PDFParseResult(
            success=False,
            pages=[],
            metadata=PDFMetadata(),
            total_text="",
            total_chars=0,
            processing_time_ms=processing_time_ms,
            error_message=error_message
        )


# Convenience function for direct usage
async def parse_pdf_file(file_path: str) -> PDFParseResult:
    """Parse a PDF file from disk"""
    parser = EnhancedPDFParser()
    
    with open(file_path, 'rb') as f:
        content = f.read()
    
    return await parser.parse_pdf(content)