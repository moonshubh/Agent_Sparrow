"""
FeedMe Transcript Parser

Utilities for parsing customer support transcripts and extracting Q&A examples.
Supports multiple transcript formats and uses AI to identify meaningful exchanges.
"""

import logging
import os
import re
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from bs4 import BeautifulSoup

from app.core.settings import settings

logger = logging.getLogger(__name__)


class TranscriptFormat(str, Enum):
    """Supported transcript formats"""
    AUTO = "auto"  # Auto-detect format
    PLAIN_TEXT = "plain_text"  # Simple conversational text
    CHAT_LOG = "chat_log"  # Timestamped chat log format
    EMAIL_THREAD = "email_thread"  # Email conversation thread
    SUPPORT_TICKET = "support_ticket"  # Support ticket format
    HTML_ZENDESK = "html_zendesk"  # Zendesk HTML ticket format


class ParsingStrategy(str, Enum):
    """Parsing strategies for extracting Q&A pairs"""
    SIMPLE_PATTERN = "simple_pattern"  # Rule-based pattern matching
    AI_POWERED = "ai_powered"  # AI-powered extraction
    HYBRID = "hybrid"  # Combination of both approaches


class ExtractionQuality(str, Enum):
    """Quality levels for extracted examples"""
    HIGH = "high"  # Clear, well-formed Q&A pairs
    MEDIUM = "medium"  # Acceptable but may need review
    LOW = "low"  # Poor quality, should be filtered out


class ExtractedQA(BaseModel):
    """Represents an extracted Q&A pair from a transcript"""
    question: str = Field(..., description="Customer question or issue description")
    answer: str = Field(..., description="Support agent response or solution")
    context_before: Optional[str] = Field(None, description="Context preceding the Q&A")
    context_after: Optional[str] = Field(None, description="Context following the Q&A")
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Extraction confidence")
    quality: ExtractionQuality = Field(default=ExtractionQuality.MEDIUM, description="Quality assessment")
    tags: List[str] = Field(default_factory=list, description="Automatically detected tags")
    issue_type: Optional[str] = Field(None, description="Detected issue category")
    resolution_type: Optional[str] = Field(None, description="Type of resolution provided")
    start_position: int = Field(default=0, description="Character position in original transcript")
    end_position: int = Field(default=0, description="End character position in original transcript")


class TranscriptParsingResult(BaseModel):
    """Result of transcript parsing operation"""
    original_text: str = Field(..., description="Original transcript content")
    detected_format: TranscriptFormat = Field(..., description="Detected transcript format")
    parsing_strategy: ParsingStrategy = Field(..., description="Strategy used for parsing")
    extracted_examples: List[ExtractedQA] = Field(..., description="Extracted Q&A examples")
    total_examples: int = Field(..., description="Total number of examples extracted")
    high_quality_count: int = Field(default=0, description="Number of high-quality examples")
    processing_time_seconds: float = Field(default=0.0, description="Time taken to process")
    errors: List[str] = Field(default_factory=list, description="Parsing errors encountered")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional parsing metadata")


class TranscriptParser:
    """Main transcript parser class"""

    def __init__(self, preview_char_limit: int | None = None):
        self.ai_model = None
        self.preview_char_limit = preview_char_limit or int(os.getenv("FEEDME_TRANSCRIPT_PREVIEW_CHARS", "3000"))
        self._initialize_ai_model()
    
    def _initialize_ai_model(self):
        """Initialize AI model for powered parsing"""
        try:
            if settings.gemini_api_key:
                self.ai_model = ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash",
                    temperature=0.1,  # Low temperature for consistent extraction
                    google_api_key=settings.gemini_api_key
                )
                logger.info("Initialized AI model for transcript parsing")
            else:
                logger.warning("No Gemini API key found - AI-powered parsing disabled")
        except Exception as e:
            logger.error(f"Failed to initialize AI model: {e}")
            self.ai_model = None
    
    def parse_transcript(
        self,
        transcript: str,
        transcript_format: TranscriptFormat = TranscriptFormat.AUTO,
        parsing_strategy: ParsingStrategy = ParsingStrategy.HYBRID,
        max_examples: int = None
    ) -> TranscriptParsingResult:
        """
        Parse a transcript and extract Q&A examples
        
        Args:
            transcript: Raw transcript content
            transcript_format: Expected format (auto-detect if AUTO)
            parsing_strategy: Strategy to use for extraction
            max_examples: Maximum number of examples to extract
            
        Returns:
            TranscriptParsingResult with extracted examples
        """
        start_time = datetime.now()
        
        if max_examples is None:
            max_examples = settings.feedme_max_examples_per_conversation
        
        logger.info(f"Starting transcript parsing (strategy: {parsing_strategy.value}, max_examples: {max_examples})")
        
        try:
            # Detect format if auto
            if transcript_format == TranscriptFormat.AUTO:
                transcript_format = self._detect_format(transcript)
            
            # Clean and preprocess transcript
            cleaned_transcript = self._preprocess_transcript(transcript, transcript_format)
            
            # Extract Q&A examples based on strategy
            if parsing_strategy == ParsingStrategy.SIMPLE_PATTERN:
                examples = self._extract_with_patterns(cleaned_transcript, transcript_format)
            elif parsing_strategy == ParsingStrategy.AI_POWERED:
                examples = self._extract_with_ai(cleaned_transcript, transcript_format)
            else:  # HYBRID
                examples = self._extract_hybrid(cleaned_transcript, transcript_format)
            
            # Limit examples if needed
            if len(examples) > max_examples:
                # Sort by confidence score and take the best ones
                examples.sort(key=lambda x: x.confidence_score, reverse=True)
                examples = examples[:max_examples]
            
            # Calculate quality metrics
            high_quality_count = len([ex for ex in examples if ex.quality == ExtractionQuality.HIGH])
            processing_time = (datetime.now() - start_time).total_seconds()
            
            result = TranscriptParsingResult(
                original_text=transcript,
                detected_format=transcript_format,
                parsing_strategy=parsing_strategy,
                extracted_examples=examples,
                total_examples=len(examples),
                high_quality_count=high_quality_count,
                processing_time_seconds=processing_time,
                metadata={
                    "original_length": len(transcript),
                    "cleaned_length": len(cleaned_transcript),
                    "avg_confidence": sum(ex.confidence_score for ex in examples) / len(examples) if examples else 0.0
                }
            )
            
            logger.info(f"Parsing completed: {len(examples)} examples extracted in {processing_time:.2f}s")
            return result
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error parsing transcript: {e}")
            
            return TranscriptParsingResult(
                original_text=transcript,
                detected_format=transcript_format,
                parsing_strategy=parsing_strategy,
                extracted_examples=[],
                total_examples=0,
                processing_time_seconds=processing_time,
                errors=[str(e)]
            )
    
    def _detect_format(self, transcript: str) -> TranscriptFormat:
        """Auto-detect transcript format based on content patterns"""
        
        # Check for HTML Zendesk format first (before other patterns)
        if "<html" in transcript[:500].lower() and "zd-comment" in transcript:
            return TranscriptFormat.HTML_ZENDESK
        
        # Check for timestamp patterns (chat log)
        timestamp_patterns = [
            r'\d{1,2}:\d{2}',  # HH:MM
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\[\d{2}:\d{2}\]',  # [HH:MM]
        ]
        
        if any(re.search(pattern, transcript) for pattern in timestamp_patterns):
            return TranscriptFormat.CHAT_LOG
        
        # Check for email patterns
        email_patterns = [
            r'From:.*@',
            r'To:.*@',
            r'Subject:',
            r'Reply to this email'
        ]
        
        if any(re.search(pattern, transcript, re.IGNORECASE) for pattern in email_patterns):
            return TranscriptFormat.EMAIL_THREAD
        
        # Check for support ticket patterns
        ticket_patterns = [
            r'Ticket #\d+',
            r'Case #\d+',
            r'Priority:',
            r'Status:'
        ]
        
        if any(re.search(pattern, transcript, re.IGNORECASE) for pattern in ticket_patterns):
            return TranscriptFormat.SUPPORT_TICKET
        
        # Default to plain text
        return TranscriptFormat.PLAIN_TEXT
    
    def _preprocess_transcript(self, transcript: str, format_type: TranscriptFormat) -> str:
        """Clean and preprocess transcript based on format"""
        
        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', transcript.strip())
        
        # Format-specific cleaning
        if format_type == TranscriptFormat.CHAT_LOG:
            # Remove timestamps for cleaner text
            cleaned = re.sub(r'\[\d{2}:\d{2}\]', '', cleaned)
            cleaned = re.sub(r'\d{1,2}:\d{2}', '', cleaned)
        
        elif format_type == TranscriptFormat.EMAIL_THREAD:
            # Remove email headers
            cleaned = re.sub(r'^(From|To|Subject|Date):.*$', '', cleaned, flags=re.MULTILINE)
            # Remove email signatures
            cleaned = re.sub(r'--\s*\n.*', '', cleaned, flags=re.DOTALL)
        
        elif format_type == TranscriptFormat.SUPPORT_TICKET:
            # Remove ticket metadata
            cleaned = re.sub(r'^(Ticket|Case|Priority|Status).*?:', '', cleaned, flags=re.MULTILINE)
        
        # Remove excessive newlines
        cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
        
        return cleaned.strip()
    
    def _extract_with_patterns(self, transcript: str, format_type: TranscriptFormat) -> List[ExtractedQA]:
        """Extract Q&A pairs using rule-based pattern matching"""
        
        examples = []
        
        # Common patterns for customer questions
        question_patterns = [
            r'(?:Customer|User|Client):\s*(.+?)(?=(?:Agent|Support|Rep):|$)',
            r'(?:Question|Issue|Problem):\s*(.+?)(?=(?:Answer|Solution|Response):|$)',
            r'[Hh]ow (?:do|can) I (.+?)\?',
            r'[Ww]hy (?:is|does|can\'t) (.+?)\?',
            r'[Cc]an you help (?:me )?(.+?)\?'
        ]
        
        # Common patterns for agent responses
        answer_patterns = [
            r'(?:Agent|Support|Rep):\s*(.+?)(?=(?:Customer|User|Client):|$)',
            r'(?:Answer|Solution|Response):\s*(.+?)(?=(?:Question|Issue|Problem):|$)',
            r'(?:To (?:fix|solve|resolve) this|Here\'s how)(.+?)(?:\n\n|$)'
        ]
        
        # Simple alternating pattern matching
        lines = transcript.split('\n')
        current_question = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Check if this line contains a question
            for pattern in question_patterns:
                match = re.search(pattern, line, re.IGNORECASE | re.DOTALL)
                if match:
                    current_question = match.group(1).strip()
                    break
            
            # Check if this line contains an answer (and we have a pending question)
            if current_question:
                for pattern in answer_patterns:
                    match = re.search(pattern, line, re.IGNORECASE | re.DOTALL)
                    if match:
                        answer = match.group(1).strip()
                        
                        # Create Q&A pair
                        qa = ExtractedQA(
                            question=current_question,
                            answer=answer,
                            context_before=self._get_context(lines, max(0, i-2), i),
                            context_after=self._get_context(lines, i+1, min(len(lines), i+3)),
                            confidence_score=0.7,  # Pattern matching confidence
                            quality=self._assess_quality(current_question, answer),
                            start_position=0,  # Would need more sophisticated tracking
                            end_position=0
                        )
                        
                        examples.append(qa)
                        current_question = None
                        break
        
        return examples
    
    def _extract_with_ai(self, transcript: str, format_type: TranscriptFormat) -> List[ExtractedQA]:
        """Extract Q&A pairs using AI-powered analysis"""
        
        if not self.ai_model:
            logger.warning("AI model not available, falling back to pattern matching")
            return self._extract_with_patterns(transcript, format_type)
        
        examples = []
        
        try:
            # Prepare AI prompt for Q&A extraction
            prompt = f"""
            Analyze the following customer support transcript and extract meaningful Question-Answer pairs.
            
            Format: {format_type.value}
            
            For each Q&A pair you identify, provide:
            1. The customer's question or issue description
            2. The support agent's answer or solution
            3. A confidence score (0.0-1.0) for how clear this Q&A pair is
            4. Tags that categorize the issue (e.g., "email-setup", "sync-issue", "account-problem")
            5. Issue type (e.g., "technical-issue", "account-setup", "how-to")
            
            Return the results in JSON format as an array of objects with fields:
            - question (string)
            - answer (string)  
            - confidence (number)
            - tags (array of strings)
            - issue_type (string)
            
            Transcript:
            {transcript[:self.preview_char_limit]}  # Limit to avoid token limits
            """
            
            response = self.ai_model.invoke(prompt)
            
            # Parse AI response
            try:
                # Extract JSON from response
                json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
                if json_match:
                    qa_data = json.loads(json_match.group(0))
                    
                    for item in qa_data:
                        qa = ExtractedQA(
                            question=item.get('question', '').strip(),
                            answer=item.get('answer', '').strip(),
                            confidence_score=min(1.0, max(0.0, item.get('confidence', 0.5))),
                            tags=item.get('tags', []),
                            issue_type=item.get('issue_type'),
                            quality=self._assess_quality(item.get('question', ''), item.get('answer', ''))
                        )
                        
                        if qa.question and qa.answer:
                            examples.append(qa)
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI response as JSON: {e}")
                # Fallback to pattern matching
                return self._extract_with_patterns(transcript, format_type)
        
        except Exception as e:
            logger.error(f"AI extraction failed: {e}")
            # Fallback to pattern matching
            return self._extract_with_patterns(transcript, format_type)
        
        return examples
    
    def _extract_hybrid(self, transcript: str, format_type: TranscriptFormat) -> List[ExtractedQA]:
        """Extract Q&A pairs using hybrid approach (patterns + AI)"""
        
        # For HTML Zendesk format, use dedicated parser
        if format_type == TranscriptFormat.HTML_ZENDESK:
            try:
                html_parser = HtmlZendeskParser(transcript)
                html_examples = html_parser.parse()
                if html_examples:
                    logger.info(f"HtmlZendeskParser extracted {len(html_examples)} examples")
                    return html_examples
                else:
                    logger.warning("HtmlZendeskParser found no examples, falling back to hybrid extraction")
            except Exception as e:
                logger.error(f"HtmlZendeskParser failed: {e}, falling back to hybrid extraction")
        
        # Start with pattern-based extraction
        pattern_examples = self._extract_with_patterns(transcript, format_type)
        
        # If we have AI available and pattern matching found few results, try AI
        if self.ai_model and len(pattern_examples) < 3:
            ai_examples = self._extract_with_ai(transcript, format_type)
            
            # Merge results, preferring higher confidence scores
            all_examples = pattern_examples + ai_examples
            
            # Remove duplicates based on question similarity
            unique_examples = []
            for example in all_examples:
                is_duplicate = False
                for existing in unique_examples:
                    if self._questions_similar(example.question, existing.question):
                        # Keep the one with higher confidence
                        if example.confidence_score > existing.confidence_score:
                            unique_examples.remove(existing)
                            unique_examples.append(example)
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    unique_examples.append(example)
            
            return unique_examples
        
        return pattern_examples
    
    def _get_context(self, lines: List[str], start: int, end: int) -> str:
        """Extract context from surrounding lines"""
        context_lines = lines[start:end]
        return ' '.join(line.strip() for line in context_lines if line.strip())
    
    def _assess_quality(self, question: str, answer: str) -> ExtractionQuality:
        """Assess the quality of an extracted Q&A pair"""
        
        # Basic quality checks
        if len(question) < 10 or len(answer) < 10:
            return ExtractionQuality.LOW
        
        if len(question) > 500 or len(answer) > 1000:
            return ExtractionQuality.LOW
        
        # Check for meaningful content
        question_words = len(question.split())
        answer_words = len(answer.split())
        
        if question_words < 3 or answer_words < 5:
            return ExtractionQuality.LOW
        
        # Check for question indicators
        question_indicators = ['?', 'how', 'why', 'what', 'when', 'where', 'can', 'could', 'would', 'help']
        has_question_indicator = any(indicator in question.lower() for indicator in question_indicators)
        
        # Check for solution indicators
        solution_indicators = ['try', 'click', 'go to', 'set', 'configure', 'enable', 'disable', 'follow']
        has_solution_indicator = any(indicator in answer.lower() for indicator in solution_indicators)
        
        if has_question_indicator and has_solution_indicator:
            return ExtractionQuality.HIGH
        elif has_question_indicator or has_solution_indicator:
            return ExtractionQuality.MEDIUM
        else:
            return ExtractionQuality.LOW
    
    def _questions_similar(self, q1: str, q2: str, threshold: float = 0.8) -> bool:
        """Check semantic similarity between two questions."""

        from difflib import SequenceMatcher

        ratio = SequenceMatcher(None, q1.lower(), q2.lower()).ratio()
        return ratio >= threshold


class HtmlZendeskParser:
    """Parser for Zendesk HTML ticket exports"""
    
    def __init__(self, html: str):
        """Initialize parser with HTML content"""
        self.soup = BeautifulSoup(html, "html.parser")
        self.html = html
    
    def parse(self) -> List[ExtractedQA]:
        """
        Returns chronologically ordered ExtractedQA pairs where
        question.role == 'Customer' and answer.role == 'Support'.
        """
        try:
            messages = self._extract_messages()
            pairs = self._pair_messages(messages)
            logger.info(f"HtmlZendeskParser extracted {len(pairs)} Q&A pairs from {len(messages)} messages")
            return pairs
        except Exception as e:
            logger.error(f"Error parsing HTML Zendesk ticket: {e}")
            return []
    
    def _extract_messages(self) -> List[Dict[str, Any]]:
        """Extract all messages from the HTML ticket"""
        messages = []
        
        try:
            # a) Extract top-level body (not inside blockquote)
            body = self.soup.select_one("#html")
            if body:
                first_para = self._strip_quotes(body)
                if first_para.strip():
                    role = "Customer" if not self._is_support_sender() else "Support"
                    timestamp = self._header_timestamp()
                    messages.append({
                        "role": role,
                        "text": first_para.strip(),
                        "time": timestamp,
                        "source": "main_body"
                    })
            
            # b) Extract every div.zd-comment
            for comment_div in self.soup.select("div.zd-comment"):
                try:
                    # Find the author and timestamp paragraphs
                    author_tag = comment_div.find_previous("p")
                    time_tag = author_tag.find_next_sibling("p") if author_tag else None
                    
                    # Extract author information
                    author_raw = author_tag.get_text(" ", strip=True) if author_tag else ""
                    role = "Support" if "(Mailbird)" in author_raw else "Customer"
                    
                    # Extract message content
                    text = self._strip_html(comment_div)
                    
                    # Extract timestamp
                    timestamp = self._parse_timestamp(time_tag.get_text()) if time_tag else None
                    
                    if text.strip():  # Only add non-empty messages
                        messages.append({
                            "role": role,
                            "text": text.strip(),
                            "time": timestamp,
                            "source": "zd_comment",
                            "author": author_raw
                        })
                
                except Exception as e:
                    logger.warning(f"Error processing zd-comment: {e}")
                    continue
            
            # Sort messages by timestamp (chronological order)
            messages.sort(key=lambda m: m["time"] or datetime.min)
            
            logger.info(f"Extracted {len(messages)} messages from HTML ticket")
            return messages
            
        except Exception as e:
            logger.error(f"Error extracting messages from HTML: {e}")
            return []
    
    def _pair_messages(self, messages: List[Dict[str, Any]]) -> List[ExtractedQA]:
        """Pair customer questions with support answers"""
        pairs = []
        current_question = None
        
        for msg in messages:
            if msg["role"] == "Customer":
                current_question = msg
            elif msg["role"] == "Support" and current_question:
                try:
                    qa = ExtractedQA(
                        question=current_question["text"],
                        answer=msg["text"],
                        confidence_score=0.8,  # HTML parsing is generally reliable
                        quality=self._assess_quality(current_question["text"], msg["text"]),
                        context_before="",
                        context_after="",
                        tags=self._extract_tags(current_question["text"], msg["text"]),
                        issue_type=self._classify_issue(current_question["text"]),
                        resolution_type=self._classify_resolution(msg["text"]),
                        start_position=0,
                        end_position=0
                    )
                    pairs.append(qa)
                    current_question = None  # Reset after pairing
                except Exception as e:
                    logger.warning(f"Error creating ExtractedQA pair: {e}")
                    continue
        
        return pairs
    
    def _strip_html(self, element) -> str:
        """Strip HTML tags and return clean text"""
        if not element:
            return ""
        
        # Remove script and style elements completely
        for script in element(["script", "style"]):
            script.decompose()
        
        # Get text and clean up whitespace
        text = element.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text)
        return text
    
    def _strip_quotes(self, element) -> str:
        """Extract text while removing quoted content (blockquotes)"""
        if not element:
            return ""
        
        # Make a copy to avoid modifying the original
        element_copy = element.__copy__()
        
        # Remove all blockquote elements (quoted content)
        for blockquote in element_copy.select("blockquote"):
            blockquote.decompose()
        
        return self._strip_html(element_copy)
    
    def _header_timestamp(self) -> Optional[datetime]:
        """Extract timestamp from email header if available"""
        try:
            # Look for common email timestamp patterns in the header
            header_text = self.html[:1000]  # Check first 1000 chars
            
            # Common timestamp patterns
            patterns = [
                r'(\w+\s+\d{1,2},\s+\d{4})',  # "Jun 24, 2025"
                r'(\d{4}-\d{2}-\d{2})',       # "2025-06-24"
                r'(\d{1,2}/\d{1,2}/\d{4})'    # "6/24/2025"
            ]
            
            for pattern in patterns:
                match = re.search(pattern, header_text)
                if match:
                    return self._parse_timestamp(match.group(1))
            
            return datetime.now()  # Fallback to current time
            
        except Exception:
            return datetime.now()
    
    def _is_support_sender(self) -> bool:
        """Check if the main sender is from support team"""
        try:
            # Look for Mailbird indicators in the first part of the email
            header_section = self.html[:1000].lower()
            return "(mailbird)" in header_section or "mailbird" in header_section
        except Exception:
            return False
    
    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse various timestamp formats"""
        if not timestamp_str:
            return None
        
        try:
            # Common timestamp formats
            formats = [
                "%b %d, %Y, %H:%M UTC",     # "Jun 24, 2025, 11:11 UTC"
                "%b %d, %Y",                # "Jun 24, 2025"
                "%Y-%m-%d %H:%M:%S",        # "2025-06-24 11:11:00"
                "%Y-%m-%d",                 # "2025-06-24"
                "%m/%d/%Y",                 # "6/24/2025"
                "%d/%m/%Y",                 # "24/6/2025"
            ]
            
            # Clean the timestamp string
            clean_ts = timestamp_str.strip()
            
            for fmt in formats:
                try:
                    return datetime.strptime(clean_ts, fmt)
                except ValueError:
                    continue
            
            # If all formats fail, try a simple extraction
            logger.warning(f"Could not parse timestamp: {timestamp_str}")
            return datetime.now()
            
        except Exception as e:
            logger.warning(f"Error parsing timestamp '{timestamp_str}': {e}")
            return datetime.now()
    
    def _assess_quality(self, question: str, answer: str) -> ExtractionQuality:
        """Assess the quality of an extracted Q&A pair"""
        # Basic quality checks
        if len(question) < 10 or len(answer) < 10:
            return ExtractionQuality.LOW
        
        if len(question) > 500 or len(answer) > 1000:
            return ExtractionQuality.LOW
        
        # Check for meaningful content
        question_words = len(question.split())
        answer_words = len(answer.split())
        
        if question_words < 3 or answer_words < 5:
            return ExtractionQuality.LOW
        
        # Check for question indicators
        question_indicators = ['?', 'how', 'why', 'what', 'when', 'where', 'can', 'could', 'would', 'help', 'issue', 'problem']
        has_question_indicator = any(indicator in question.lower() for indicator in question_indicators)
        
        # Check for solution indicators
        solution_indicators = ['try', 'click', 'go to', 'set', 'configure', 'enable', 'disable', 'follow', 'solution', 'fix']
        has_solution_indicator = any(indicator in answer.lower() for indicator in solution_indicators)
        
        if has_question_indicator and has_solution_indicator:
            return ExtractionQuality.HIGH
        elif has_question_indicator or has_solution_indicator:
            return ExtractionQuality.MEDIUM
        else:
            return ExtractionQuality.LOW
    
    def _extract_tags(self, question: str, answer: str) -> List[str]:
        """Extract relevant tags from Q&A content"""
        tags = []
        combined_text = (question + " " + answer).lower()
        
        # Common Mailbird-related tags
        tag_patterns = {
            'email-setup': ['email', 'setup', 'account', 'configure'],
            'sync-issue': ['sync', 'synchron', 'download', 'fetch'],
            'performance': ['slow', 'lag', 'performance', 'speed'],
            'login': ['login', 'password', 'authentication', 'signin'],
            'folders': ['folder', 'directory', 'organize'],
            'contacts': ['contact', 'address book'],
            'calendar': ['calendar', 'appointment', 'meeting'],
            'attachment': ['attach', 'file', 'document'],
            'search': ['search', 'find', 'filter'],
            'notification': ['notification', 'alert', 'popup']
        }
        
        for tag, keywords in tag_patterns.items():
            if any(keyword in combined_text for keyword in keywords):
                tags.append(tag)
        
        return tags[:5]  # Limit to 5 tags
    
    def _classify_issue(self, question: str) -> Optional[str]:
        """Classify the type of issue based on question content"""
        question_lower = question.lower()
        
        if any(word in question_lower for word in ['setup', 'configure', 'install']):
            return 'account-setup'
        elif any(word in question_lower for word in ['sync', 'download', 'fetch']):
            return 'email-sync'
        elif any(word in question_lower for word in ['slow', 'lag', 'performance']):
            return 'performance'
        elif any(word in question_lower for word in ['how', 'guide', 'tutorial']):
            return 'how-to'
        elif any(word in question_lower for word in ['problem', 'issue', 'error', 'bug']):
            return 'technical-issue'
        else:
            return 'other'
    
    def _classify_resolution(self, answer: str) -> Optional[str]:
        """Classify the type of resolution provided"""
        answer_lower = answer.lower()
        
        if any(word in answer_lower for word in ['step 1', 'first', 'then', 'next', 'follow']):
            return 'step-by-step-guide'
        elif any(word in answer_lower for word in ['settings', 'configure', 'change', 'set']):
            return 'configuration-change'
        elif any(word in answer_lower for word in ['workaround', 'temporary', 'alternative']):
            return 'workaround'
        elif any(word in answer_lower for word in ['feature', 'designed', 'intended']):
            return 'feature-explanation'
        else:
            return 'other'


# Utility functions
def parse_transcript_file(file_path: str, **kwargs) -> TranscriptParsingResult:
    """Parse a transcript from a file"""
    parser = TranscriptParser()
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return parser.parse_transcript(content, **kwargs)


def parse_transcript_text(text: str, **kwargs) -> TranscriptParsingResult:
    """Parse a transcript from text string"""
    parser = TranscriptParser()
    return parser.parse_transcript(text, **kwargs)