"""
FeedMe v2.0 AI Extraction Engine
Advanced Q&A extraction using Google's Gemma-3-27b-it model for intelligent conversation parsing
"""

import json
import logging
import asyncio
import time
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

import google.generativeai as genai
from bs4 import BeautifulSoup
from google.api_core.exceptions import ResourceExhausted, InvalidArgument

from app.core.settings import settings
from app.feedme.schemas import ProcessingStatus, IssueType, ResolutionType

logger = logging.getLogger(__name__)

# Import Zendesk email parser
try:
    from app.feedme.zendesk_email_parser import ZendeskEmailParser, extract_qa_pairs
    ZENDESK_PARSER_AVAILABLE = True
except ImportError:
    ZENDESK_PARSER_AVAILABLE = False
    logger.warning("Zendesk email parser not available")


@dataclass
class ExtractionConfig:
    """Configuration for AI extraction engine with intelligent rate limiting"""
    model_name: str = "gemma-3-27b-it"  # Use Google's Gemma-3-27b-it model
    temperature: float = 0.3                
    max_output_tokens: int = 8192
    confidence_threshold: float = 0.7
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # Intelligent rate limiting for Gemini free tier (15k tokens/minute)
    max_tokens_per_minute: int = 12000  # Conservative 80% of 15k limit
    max_tokens_per_chunk: int = 8000    # Max tokens per single request
    chunk_overlap_tokens: int = 500     # Overlap between chunks for context
    rate_limit_window: int = 60         # Rate limit window in seconds
    
    # Progressive retry strategy for rate limits
    rate_limit_base_delay: float = 30.0      # Base delay for rate limits
    rate_limit_max_delay: float = 300.0      # Max delay (5 minutes)
    rate_limit_backoff_factor: float = 1.5   # Exponential backoff factor
    
    # Chunking strategy
    enable_smart_chunking: bool = True       # Enable intelligent chunking
    chunk_by_conversations: bool = True      # Try to chunk by conversation boundaries
    min_chunk_size: int = 1000              # Minimum chunk size in characters
    max_chunk_size: int = 40000             # Maximum chunk size in characters
    
    # Fallback processing configuration
    enable_fallback_processing: bool = True  # Enable pattern-based fallback when AI fails
    
    # Configurable conversation markers for different platforms
    conversation_markers: List[str] = field(default_factory=lambda: [
        'div.zd-liquid-comment',  # Zendesk comments
        'div.email-message',      # Email messages
        'div.message',            # Generic messages
        'table.message',          # Table-based messages
        'blockquote',             # Quoted text
        'p[style*="margin-top"]'  # Styled separators
    ])


class ExtractionMethod(str, Enum):
    """Extraction method types"""
    AI_POWERED = "ai"
    PATTERN_BASED = "pattern"
    HYBRID = "hybrid"


class RateLimitTracker:
    """Track token usage and enforce rate limits"""
    
    def __init__(self, config: ExtractionConfig):
        self.config = config
        self.token_usage = []  # List of (timestamp, tokens_used)
        self.last_request_time = 0
        
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count with dynamic ratio based on content characteristics"""
        import re
        
        # Analyze content characteristics
        text_length = len(text)
        if text_length == 0:
            return 0
            
        # Count different content types
        code_patterns = len(re.findall(r'[{}()[\];=\-+*/<>]', text))
        special_chars = len(re.findall(r'[^\w\s]', text))
        whitespace = len(re.findall(r'\s', text))
        numbers = len(re.findall(r'\d', text))
        
        # Calculate content type ratios
        code_ratio = code_patterns / text_length
        special_ratio = special_chars / text_length
        
        # Dynamic token estimation based on content type
        if code_ratio > 0.1:  # High code content
            # Code has more special tokens, ratio closer to 3
            return text_length // 3
        elif special_ratio > 0.15:  # High special character content
            # Special characters often tokenize differently
            return int(text_length // 3.5)
        else:
            # Regular text content
            # Use better approximation: English ~4, other languages ~3-3.5
            non_ascii = len([c for c in text if ord(c) > 127])
            if non_ascii / text_length > 0.1:  # Significant non-English content
                return int(text_length // 3.2)
            else:
                return text_length // 4
        
    def get_current_minute_usage(self) -> int:
        """Get token usage in current minute"""
        current_time = time.time()
        minute_ago = current_time - self.config.rate_limit_window
        
        # Remove old entries and calculate current usage
        self.token_usage = [(ts, tokens) for ts, tokens in self.token_usage if ts > minute_ago]
        return sum(tokens for _, tokens in self.token_usage)
        
    def can_make_request(self, estimated_tokens: int) -> Tuple[bool, float]:
        """Check if request can be made, return (can_proceed, delay_needed)"""
        current_usage = self.get_current_minute_usage()
        
        if current_usage + estimated_tokens <= self.config.max_tokens_per_minute:
            return True, 0.0
            
        # Calculate delay needed
        oldest_in_window = min(self.token_usage, key=lambda x: x[0])[0] if self.token_usage else (time.time() - self.config.rate_limit_window)
        delay_needed = (oldest_in_window + self.config.rate_limit_window) - time.time()
        
        return False, max(0, delay_needed)
        
    def record_usage(self, tokens_used: int):
        """Record token usage"""
        self.token_usage.append((time.time(), tokens_used))
        self.last_request_time = time.time()
        
    async def wait_for_rate_limit(self, delay: float):
        """Wait for rate limit with progress logging"""
        if delay > 0:
            logger.info(f"Rate limit reached, waiting {delay:.1f}s before next request")
            await asyncio.sleep(delay)


@dataclass
class Message:
    """Represents a single message in a conversation"""
    content: str
    sender: str
    timestamp: Optional[datetime] = None
    role: str = "unknown"  # 'customer' or 'agent'
    attachments: List[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []
        if self.metadata is None:
            self.metadata = {}


@dataclass 
class Thread:
    """Represents a conversation thread"""
    messages: List[Message]
    topic_keywords: List[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def __post_init__(self):
        if self.topic_keywords is None:
            self.topic_keywords = []


class GemmaExtractionEngine:
    """Advanced extraction engine using Google's Gemma-3-27b-it model"""
    
    def __init__(self, api_key: Optional[str] = None, config: Optional[ExtractionConfig] = None):
        self.config = config or ExtractionConfig()
        self.api_key = api_key or settings.gemini_api_key
        self.rate_limiter = RateLimitTracker(self.config)
        
        if not self.api_key:
            raise ValueError("Google AI API key is required for extraction engine")
        
        # Configure Google AI
        genai.configure(api_key=self.api_key)
        
        # Initialize model
        self.model = genai.GenerativeModel(
            model_name=self.config.model_name,
            generation_config={
                "temperature": self.config.temperature,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": self.config.max_output_tokens,
            }
        )
        
        logger.info(f"Initialized AI extraction engine with model: {self.config.model_name}")
        logger.info(f"Rate limiting: {self.config.max_tokens_per_minute} tokens/minute, max {self.config.max_tokens_per_chunk} tokens/chunk")
        
        # Initialize Zendesk parser if available
        self.zendesk_parser = ZendeskEmailParser() if ZENDESK_PARSER_AVAILABLE else None

    def _is_zendesk_email(self, html_content: str, metadata: Dict[str, Any]) -> bool:
        """
        Detect if HTML content is from a Zendesk email
        
        Args:
            html_content: HTML content to check
            metadata: Additional metadata that might indicate source
            
        Returns:
            True if content appears to be from Zendesk
        """
        # Check metadata first
        if metadata.get('platform', '').lower() == 'zendesk':
            return True
        
        if metadata.get('source', '').lower() in ['zendesk', 'zendesk_email']:
            return True
        
        # Check filename if available
        filename = metadata.get('original_filename', '').lower()
        if 'zendesk' in filename:
            return True
        
        # Check HTML content for Zendesk indicators
        zendesk_indicators = [
            'class="zd-comment"',
            'class="zd-liquid-comment"',
            'zendesk.com',
            'ticket.zendesk.com',
            'data-comment-id=',
            'class="event-list"',
            'id="ticket-comments"',
            'View this ticket in Zendesk',
            'Zendesk Support'
        ]
        
        # Quick check without parsing
        html_lower = html_content[:5000].lower()  # Check first 5KB
        for indicator in zendesk_indicators:
            if indicator.lower() in html_lower:
                logger.info(f"Detected Zendesk email based on indicator: {indicator}")
                return True
        
        return False

    async def extract_conversations(
        self, 
        html_content: str,
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract Q&A pairs with advanced context understanding"""
        
        if not html_content or not html_content.strip():
            logger.warning("Empty HTML content provided for extraction")
            return []
        
        # Check if this is a Zendesk email and use specialized parser
        if self.zendesk_parser and self._is_zendesk_email(html_content, metadata):
            logger.info("Detected Zendesk email, using specialized parser for preprocessing")
            
            try:
                # Parse with Zendesk parser first
                interactions = self.zendesk_parser.parse(html_content)
                logger.info(f"Zendesk parser extracted {len(interactions)} interactions")
                
                if interactions:
                    # Convert interactions to Q&A pairs
                    zendesk_qa_pairs = extract_qa_pairs(interactions)
                    logger.info(f"Converted to {len(zendesk_qa_pairs)} Q&A pairs")
                    
                    # If we have good Q&A pairs from structured parsing, enhance with AI
                    if zendesk_qa_pairs:
                        # Create a simplified prompt for AI enhancement
                        enhancement_prompt = self._build_enhancement_prompt(zendesk_qa_pairs, metadata)
                        
                        # Use AI to enhance the extracted Q&A pairs
                        try:
                            response = await self._extract_with_retry(enhancement_prompt)
                            if response:
                                enhanced_pairs = self._parse_extraction_response(response.text)
                                # Merge AI enhancements with structured extraction
                                final_pairs = self._merge_structured_and_ai_pairs(zendesk_qa_pairs, enhanced_pairs)
                                logger.info(f"AI enhancement complete: {len(final_pairs)} final Q&A pairs")
                                return final_pairs
                        except Exception as e:
                            logger.warning(f"AI enhancement failed: {e}, using structured extraction only")
                            return zendesk_qa_pairs
                    
                    # If no Q&A pairs from structured parsing, create clean HTML for AI
                    else:
                        # Convert interactions to clean HTML for AI processing
                        clean_html = self._interactions_to_html(interactions)
                        html_content = clean_html
                        logger.info("No Q&A pairs from structured parsing, using cleaned interactions for AI extraction")
                
            except Exception as e:
                logger.error(f"Zendesk parser failed: {e}, falling back to standard extraction")
                # Continue with standard extraction
        
        # Estimate token usage and determine if chunking is needed
        estimated_tokens = self.rate_limiter.estimate_tokens(html_content)
        
        if estimated_tokens > self.config.max_tokens_per_chunk or len(html_content) > self.config.max_chunk_size:
            logger.info(f"Large content detected ({estimated_tokens} estimated tokens), using intelligent chunking strategy")
            return await self.intelligent_chunk_and_extract(html_content, metadata)
        
        # Generate extraction prompt
        extraction_prompt = self._build_extraction_prompt(html_content, metadata)
        
        try:
            # Call AI model with retry logic
            response = await self._extract_with_retry(extraction_prompt)
            
            # Handle fallback processing if rate limited
            if response is None:
                logger.info("AI model rate limited, falling back to pattern-based extraction")
                return await self._fallback_pattern_extraction(html_content)
            
            # Parse and validate extracted Q&As
            extracted_pairs = self._parse_extraction_response(response.text)
            
            # Apply confidence filtering
            high_quality_pairs = [
                pair for pair in extracted_pairs 
                if pair.get('confidence_score', 0) >= self.config.confidence_threshold
            ]
            
            logger.info(f"Extracted {len(high_quality_pairs)} high-quality Q&A pairs from {len(extracted_pairs)} total")
            return high_quality_pairs
            
        except Exception as e:
            logger.error(f"Error during AI extraction: {e}")
            if self.config.enable_fallback_processing:
                logger.info("AI extraction failed, falling back to pattern-based extraction")
                return await self._fallback_pattern_extraction(html_content)
            return []

    def _build_extraction_prompt(self, html_content: str, metadata: Dict[str, Any]) -> str:
        """Build comprehensive extraction prompt"""
        
        platform = metadata.get('platform', 'unknown')
        language = metadata.get('language', 'en')
        
        prompt = f"""
You are an expert at analyzing customer support conversations from {platform} platform.

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

4. METADATA EXTRACTION:
   - Product features mentioned
   - Error codes or technical identifiers
   - Customer sentiment/urgency

Format each Q&A as valid JSON with these fields:
{{
    "question_text": "...",
    "answer_text": "...",
    "context_before": "...",
    "context_after": "...",
    "confidence_score": 0.0-1.0,
    "quality_score": 0.0-1.0,
    "issue_type": "category",
    "resolution_type": "type",
    "tags": ["tag1", "tag2"],
    "metadata": {{
        "sentiment": "...",
        "technical_level": "...",
        "resolved": true/false
    }}
}}

Return a JSON array of Q&A pairs. If no valid Q&A pairs found, return [].

HTML Content:
{html_content}
"""
        return prompt

    async def _extract_with_retry(self, prompt: str) -> Any:
        """Extract with intelligent rate limiting and retry logic"""
        
        # Estimate tokens for this request
        estimated_tokens = self.rate_limiter.estimate_tokens(prompt)
        
        for attempt in range(self.config.max_retries):
            # Check rate limits before making request
            can_proceed, delay_needed = self.rate_limiter.can_make_request(estimated_tokens)
            
            if not can_proceed:
                logger.info(f"Rate limit would be exceeded, waiting {delay_needed:.1f}s before request")
                await self.rate_limiter.wait_for_rate_limit(delay_needed)
            
            try:
                # Make the API request
                response = await self.model.generate_content_async(prompt)
                
                # Record successful token usage
                self.rate_limiter.record_usage(estimated_tokens)
                logger.debug(f"API request successful, used ~{estimated_tokens} tokens")
                
                return response
                
            except ResourceExhausted as e:
                # More robust rate limit error detection
                is_rate_limit_error = False
                
                # Check for specific error codes in details
                if hasattr(e, 'details') and e.details:
                    for detail in e.details:
                        if hasattr(detail, 'reason') and detail.reason in ['RESOURCE_EXHAUSTED', 'RATE_LIMIT_EXCEEDED', 'QUOTA_EXCEEDED']:
                            is_rate_limit_error = True
                            break
                
                # Fallback to string checking if no details available
                if not is_rate_limit_error:
                    error_msg = str(e).lower()
                    is_rate_limit_error = any(term in error_msg for term in ['quota', 'rate', 'resource_exhausted', 'rate_limit'])
                
                if is_rate_limit_error:
                    # Calculate progressive delay for rate limits
                    base_delay = self.config.rate_limit_base_delay
                    delay_multiplier = self.config.rate_limit_backoff_factor ** attempt
                    wait_time = min(base_delay * delay_multiplier, self.config.rate_limit_max_delay)
                    
                    if attempt < self.config.max_retries - 1:
                        logger.warning(f"Rate limit/quota exceeded, waiting {wait_time:.1f}s before retry (attempt {attempt + 1})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Rate limit exceeded after {self.config.max_retries} attempts")
                        raise
                else:
                    # Other resource exhausted errors
                    if attempt < self.config.max_retries - 1:
                        wait_time = self.config.retry_delay * (2 ** attempt)
                        logger.warning(f"Resource exhausted, retrying in {wait_time}s (attempt {attempt + 1})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise
                    
            except InvalidArgument as e:
                logger.error(f"Invalid argument error: {e}")
                raise
                
            except Exception as e:
                if attempt < self.config.max_retries - 1:
                    wait_time = self.config.retry_delay * (attempt + 1)
                    logger.warning(f"Extraction error: {e}, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Extraction failed after {self.config.max_retries} attempts: {e}")
                    raise
        
        raise Exception("Maximum retries exceeded")

    def _parse_extraction_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse and validate AI response"""
        
        try:
            # Check for None response
            if response_text is None:
                logger.error("Response text is None")
                return []
            
            # Clean response text
            cleaned_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if cleaned_text.startswith('```json'):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.endswith('```'):
                cleaned_text = cleaned_text[:-3]
            
            cleaned_text = cleaned_text.strip()
            
            # Parse JSON
            parsed_data = json.loads(cleaned_text)
            
            # Ensure it's a list
            if isinstance(parsed_data, dict):
                parsed_data = [parsed_data]
            elif not isinstance(parsed_data, list):
                logger.error(f"Unexpected response format: {type(parsed_data)}")
                return []
            
            # Validate and clean each Q&A pair
            validated_pairs = []
            for pair in parsed_data:
                if self._validate_qa_pair(pair):
                    # Standardize fields
                    standardized_pair = {
                        'question_text': pair.get('question_text', ''),
                        'answer_text': pair.get('answer_text', ''),
                        'context_before': pair.get('context_before', ''),
                        'context_after': pair.get('context_after', ''),
                        'confidence_score': float(pair.get('confidence_score', 0.5)),
                        'quality_score': float(pair.get('quality_score', pair.get('confidence_score', 0.5))),
                        'issue_type': pair.get('issue_type'),
                        'resolution_type': pair.get('resolution_type'),
                        'tags': pair.get('tags', []),
                        'metadata': pair.get('metadata', {}),
                        'extraction_method': 'ai'
                    }
                    validated_pairs.append(standardized_pair)
            
            return validated_pairs
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response_text[:500]}...")
            return []
        except Exception as e:
            logger.error(f"Error parsing extraction response: {e}")
            return []

    def _validate_qa_pair(self, pair: Dict[str, Any]) -> bool:
        """Validate extracted Q&A pair"""
        
        # Check required fields
        if not isinstance(pair, dict):
            return False
        
        question = pair.get('question_text', '').strip()
        answer = pair.get('answer_text', '').strip()
        
        # Must have both question and answer
        if not question or not answer:
            return False
        
        # Minimum length requirements
        if len(question) < 10 or len(answer) < 10:
            return False
        
        # Confidence score validation
        confidence = pair.get('confidence_score', 0)
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            return False
        
        return True

    async def intelligent_chunk_and_extract(self, html_content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Intelligent chunking with rate limiting and conversation boundary awareness"""
        
        # Split content into manageable chunks
        chunks = self._create_intelligent_chunks(html_content)
        logger.info(f"Split large content into {len(chunks)} intelligent chunks")
        
        all_pairs = []
        total_tokens_used = 0
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
            
            # Estimate tokens for this chunk
            estimated_tokens = self.rate_limiter.estimate_tokens(chunk)
            total_tokens_used += estimated_tokens
            
            try:
                # Process each chunk with rate limiting
                chunk_prompt = self._build_extraction_prompt(chunk, metadata)
                response = await self._extract_with_retry(chunk_prompt)
                
                if response:
                    chunk_pairs = self._parse_extraction_response(response.text)
                    all_pairs.extend(chunk_pairs)
                    logger.info(f"Chunk {i+1} extracted {len(chunk_pairs)} Q&A pairs")
                else:
                    logger.warning(f"Chunk {i+1} processing failed")
                
            except Exception as e:
                logger.error(f"Chunk {i+1} processing failed: {e}")
                continue
        
        # Merge and deduplicate pairs
        merged_pairs = self._merge_and_deduplicate_pairs(all_pairs)
        
        logger.info(f"Intelligent chunking complete: {len(merged_pairs)} unique pairs from {len(all_pairs)} total, ~{total_tokens_used} tokens used")
        return merged_pairs
    
    def _create_intelligent_chunks(self, html_content: str) -> List[str]:
        """Create intelligent chunks respecting conversation boundaries and token limits"""
        
        if not self.config.enable_smart_chunking:
            # Simple character-based chunking
            return self._simple_character_chunks(html_content)
        
        try:
            # Try to parse HTML and find conversation boundaries
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Use configurable conversation markers
            conversation_markers = self.config.conversation_markers
            
            chunks = []
            current_chunk = ""
            
            # Try to split by conversation markers
            for marker in conversation_markers:
                elements = soup.select(marker)
                if elements and len(elements) > 1:
                    for element in elements:
                        element_text = str(element)
                        
                        # Check if adding this element would exceed chunk size
                        if (len(current_chunk) + len(element_text)) > self.config.max_chunk_size:
                            if current_chunk.strip():
                                chunks.append(current_chunk)
                                current_chunk = ""
                        
                        current_chunk += element_text + "\n"
                    
                    # Add remaining content
                    if current_chunk.strip():
                        chunks.append(current_chunk)
                    
                    # If we got reasonable chunks, return them
                    if len(chunks) > 1 and all(len(c) > self.config.min_chunk_size for c in chunks):
                        logger.info(f"Created {len(chunks)} conversation-aware chunks using {marker}")
                        return chunks
            
            # If conversation-aware chunking failed, fall back to character chunking
            logger.info("Conversation-aware chunking failed, using character-based chunking")
            return self._simple_character_chunks(html_content)
            
        except Exception as e:
            logger.warning(f"Intelligent chunking failed: {e}, falling back to simple chunking")
            return self._simple_character_chunks(html_content)
    
    def _simple_character_chunks(self, content: str) -> List[str]:
        """Simple character-based chunking with overlap"""
        
        chunks = []
        chunk_size = self.config.max_chunk_size
        overlap = self.config.chunk_overlap_tokens * 4  # Approximate character overlap
        
        start = 0
        while start < len(content):
            end = start + chunk_size
            
            # Try to break at word boundary
            if end < len(content):
                # Look for nearest word boundary within 100 chars
                for i in range(end, max(end - 100, start), -1):
                    if content[i].isspace():
                        end = i
                        break
            
            chunk = content[start:end]
            if len(chunk.strip()) > self.config.min_chunk_size:
                chunks.append(chunk)
            
            start = end - overlap if end < len(content) else end
        
        return chunks
    
    def _merge_and_deduplicate_pairs(self, pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge and deduplicate Q&A pairs from multiple chunks using advanced similarity detection"""
        import re
        from difflib import SequenceMatcher
        
        # Simple stop words (could be enhanced with NLTK in the future)
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 
            'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 
            'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'i', 'you', 'he', 
            'she', 'it', 'we', 'they', 'this', 'that', 'these', 'those', 'what', 'where', 'when', 
            'why', 'how', 'who', 'which'
        }
        
        def normalize_question(text: str) -> str:
            """Normalize question text for better comparison"""
            # Convert to lowercase and remove extra whitespace
            text = re.sub(r'\s+', ' ', text.lower().strip())
            # Remove punctuation except question marks and apostrophes
            text = re.sub(r'[^\w\s\?\']+', ' ', text)
            # Basic lemmatization substitutions (simplified)
            text = re.sub(r'\b(are|is|was|were)\b', 'be', text)
            text = re.sub(r'\b(have|has|had)\b', 'have', text)
            text = re.sub(r'\b(do|does|did)\b', 'do', text)
            return text.strip()
        
        def get_normalized_words(text: str) -> set:
            """Extract normalized words excluding stop words"""
            normalized = normalize_question(text)
            words = set(normalized.split())
            return words - stop_words
        
        def calculate_similarity(q1: str, q2: str) -> float:
            """Calculate similarity using multiple methods"""
            # Method 1: Normalized word overlap (Jaccard similarity)
            words1 = get_normalized_words(q1)
            words2 = get_normalized_words(q2)
            
            if not words1 or not words2:
                return 0.0
                
            jaccard = len(words1.intersection(words2)) / len(words1.union(words2))
            
            # Method 2: Sequence similarity (considers word order)
            norm1 = normalize_question(q1)
            norm2 = normalize_question(q2)
            sequence_sim = SequenceMatcher(None, norm1, norm2).ratio()
            
            # Method 3: Length-adjusted similarity
            len_ratio = min(len(norm1), len(norm2)) / max(len(norm1), len(norm2))
            
            # Combine similarities with weights
            combined_similarity = (jaccard * 0.5 + sequence_sim * 0.3 + len_ratio * 0.2)
            
            return combined_similarity
        
        seen_questions = []
        merged_pairs = []
        
        for pair in pairs:
            question = pair.get('question_text', '').strip()
            
            if not question or len(question) < 5:  # Skip very short questions
                continue
                
            # Check for duplicates using enhanced similarity
            is_duplicate = False
            for seen_q in seen_questions:
                similarity = calculate_similarity(question, seen_q)
                
                # Use dynamic threshold based on question length
                base_threshold = 0.85 if len(question) > 50 else 0.75
                
                if similarity > base_threshold:
                    is_duplicate = True
                    break
                    
            if not is_duplicate:
                seen_questions.append(question)
                merged_pairs.append(pair)
        
        logger.info(f"Merged {len(pairs)} pairs into {len(merged_pairs)} unique pairs")
        return merged_pairs

    async def _fallback_pattern_extraction(self, html_content: str) -> List[Dict[str, Any]]:
        """Fallback to pattern-based extraction when AI processing fails"""
        try:
            fallback_extractor = FallbackExtractor()
            pairs = fallback_extractor.extract_qa_pairs(html_content)
            
            # Convert FallbackExtractor results to match AI extraction format
            standardized_pairs = []
            for pair in pairs:
                standardized_pair = {
                    'question_text': pair.get('question_text', ''),
                    'answer_text': pair.get('answer_text', ''),
                    'context_before': '',
                    'context_after': '',
                    'confidence_score': pair.get('confidence_score', 0.6),
                    'quality_score': pair.get('confidence_score', 0.6),
                    'issue_type': None,
                    'resolution_type': None,
                    'tags': [],
                    'metadata': {'fallback_extraction': True},
                    'extraction_method': 'pattern'
                }
                standardized_pairs.append(standardized_pair)
            
            logger.info(f"Fallback extraction completed: {len(standardized_pairs)} pairs extracted")
            return standardized_pairs
            
        except Exception as e:
            logger.error(f"Fallback extraction failed: {e}")
            return []

    async def chunk_and_extract(self, html_content: str, chunk_size: int = 50000, concurrency_limit: int = 3) -> List[Dict[str, Any]]:
        """Handle large HTML files by intelligent chunking"""
        
        chunks = self._create_semantic_chunks(html_content, chunk_size)
        logger.info(f"Split large content into {len(chunks)} chunks")
        
        # Process chunks with controlled concurrency
        semaphore = asyncio.Semaphore(concurrency_limit)
        
        async def process_chunk(chunk: str) -> List[Dict[str, Any]]:
            async with semaphore:
                return await self._extract_with_retry(
                    self._build_extraction_prompt(chunk, {})
                )
        
        # Process chunks
        tasks = [process_chunk(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge results
        all_pairs = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Chunk {i} processing failed: {result}")
                continue
            
            try:
                pairs = self._parse_extraction_response(result.text)
                all_pairs.extend(pairs)
            except Exception as e:
                logger.error(f"Error parsing chunk {i} result: {e}")
                continue
        
        return self._merge_chunk_results(all_pairs)

    def _create_semantic_chunks(self, content: str, chunk_size: int) -> List[str]:
        """Create semantic chunks that preserve conversation boundaries"""
        
        if len(content) <= chunk_size:
            return [content]
        
        chunks = []
        current_chunk = ""
        
        # Split by conversation boundaries first
        conversation_markers = [
            '<div class="conversation">',
            '<div class="zd-comment">',
            '<div class="intercom-comment">',
            '<div class="message">',
            '<article',
            '<section'
        ]
        
        # Simple chunking that tries to preserve HTML structure
        lines = content.split('\n')
        
        for line in lines:
            # Check if adding this line would exceed chunk size
            if len(current_chunk) + len(line) > chunk_size and current_chunk:
                # Look for a good break point
                if any(marker in line for marker in conversation_markers):
                    chunks.append(current_chunk)
                    current_chunk = line + '\n'
                else:
                    current_chunk += line + '\n'
            else:
                current_chunk += line + '\n'
        
        # Add the last chunk
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

    def _merge_chunk_results(self, all_pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge and deduplicate results from multiple chunks"""
        
        # Simple deduplication based on question similarity
        unique_pairs = []
        seen_questions = set()
        
        for pair in all_pairs:
            question = pair.get('question_text', '').strip().lower()
            
            # Simple deduplication - could be enhanced with similarity matching
            question_key = question[:100]  # First 100 chars as key
            
            if question_key not in seen_questions:
                seen_questions.add(question_key)
                unique_pairs.append(pair)
        
        # Sort by confidence score
        unique_pairs.sort(key=lambda x: x.get('confidence_score', 0), reverse=True)
        
        logger.info(f"Merged {len(all_pairs)} pairs into {len(unique_pairs)} unique pairs")
        return unique_pairs

    def detect_conversation_threads(self, messages: List[Message]) -> List[Thread]:
        """Group messages into logical conversation threads"""
        
        if not messages:
            return []
        
        threads = []
        current_thread = []
        
        for i, msg in enumerate(messages):
            if self._is_new_thread(msg, current_thread):
                if current_thread:
                    thread = Thread(
                        messages=current_thread,
                        topic_keywords=self._extract_topic_keywords(current_thread),
                        start_time=current_thread[0].timestamp,
                        end_time=current_thread[-1].timestamp
                    )
                    threads.append(thread)
                current_thread = [msg]
            else:
                current_thread.append(msg)
        
        # Add the last thread
        if current_thread:
            thread = Thread(
                messages=current_thread,
                topic_keywords=self._extract_topic_keywords(current_thread),
                start_time=current_thread[0].timestamp,
                end_time=current_thread[-1].timestamp
            )
            threads.append(thread)
        
        return threads

    def _is_new_thread(self, message: Message, current_thread: List[Message]) -> bool:
        """Determine if message starts a new conversation thread"""
        
        if not current_thread:
            return False
        
        # Simple heuristics for thread detection
        last_msg = current_thread[-1]
        
        # Time gap detection
        if message.timestamp and last_msg.timestamp:
            time_gap = (message.timestamp - last_msg.timestamp).total_seconds()
            if time_gap > 3600:  # 1 hour gap
                return True
        
        # Topic change detection (simplified)
        keywords = ['issue', 'problem', 'question', 'help', 'how', 'why', 'when']
        if any(keyword in message.content.lower() for keyword in keywords):
            # Check if this looks like a new topic
            return True
        
        return False

    def _extract_topic_keywords(self, messages: List[Message]) -> List[str]:
        """Extract topic keywords from a thread"""
        
        # Combine all message content
        combined_text = ' '.join(msg.content for msg in messages)
        
        # Simple keyword extraction (could use more sophisticated NLP)
        common_support_terms = [
            'email', 'imap', 'smtp', 'sync', 'account', 'password', 'login',
            'settings', 'configuration', 'error', 'problem', 'issue',
            'calendar', 'contacts', 'attachment', 'notification'
        ]
        
        found_keywords = []
        for term in common_support_terms:
            if term in combined_text.lower():
                found_keywords.append(term)
        
        return found_keywords[:5]  # Return top 5 keywords

    def _build_enhancement_prompt(self, qa_pairs: List[Dict[str, Any]], metadata: Dict[str, Any]) -> str:
        """
        Build prompt to enhance pre-extracted Q&A pairs with AI
        
        Args:
            qa_pairs: Q&A pairs extracted by Zendesk parser
            metadata: Additional metadata
            
        Returns:
            Prompt for AI enhancement
        """
        prompt = f"""
You are an expert at enhancing customer support Q&A pairs.

Given these pre-extracted Q&A pairs from a Zendesk support ticket, enhance them by:
1. Improving clarity and completeness
2. Adding confidence and quality scores
3. Categorizing the issue type and resolution type
4. Extracting relevant tags and metadata
5. Ensuring technical accuracy

Pre-extracted Q&A pairs:
"""
        
        for i, pair in enumerate(qa_pairs[:10]):  # Limit to first 10 for token efficiency
            prompt += f"""
Q&A Pair {i+1}:
Question: {pair['question_text']}
Answer: {pair['answer_text']}
Context Before: {pair.get('context_before', 'N/A')}
Context After: {pair.get('context_after', 'N/A')}
"""
        
        prompt += """

For each Q&A pair, provide enhanced version with:
- Improved question/answer text (if needed)
- confidence_score (0-1)
- quality_score (0-1)
- issue_type (e.g., "email_configuration", "sync_issue", etc.)
- resolution_type (e.g., "settings_change", "troubleshooting", etc.)
- tags (relevant keywords)
- metadata (sentiment, technical_level, resolved status)

Return as JSON array matching the original structure but with enhancements.
"""
        return prompt

    def _merge_structured_and_ai_pairs(
        self, 
        structured_pairs: List[Dict[str, Any]], 
        ai_pairs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge structured extraction with AI enhancements
        
        Args:
            structured_pairs: Q&A pairs from Zendesk parser
            ai_pairs: Enhanced pairs from AI
            
        Returns:
            Merged Q&A pairs with best of both approaches
        """
        merged = []
        
        # Create mapping of AI pairs by question similarity
        ai_map = {}
        for ai_pair in ai_pairs:
            # Use first 100 chars of normalized question as key
            key = ai_pair.get('question_text', '')[:100].lower().strip()
            ai_map[key] = ai_pair
        
        for struct_pair in structured_pairs:
            # Try to find matching AI enhancement
            key = struct_pair.get('question_text', '')[:100].lower().strip()
            ai_enhancement = ai_map.get(key)
            
            if ai_enhancement:
                # Merge with AI enhancements
                merged_pair = {
                    'question_text': ai_enhancement.get('question_text', struct_pair['question_text']),
                    'answer_text': ai_enhancement.get('answer_text', struct_pair['answer_text']),
                    'context_before': struct_pair.get('context_before', ''),
                    'context_after': struct_pair.get('context_after', ''),
                    'confidence_score': ai_enhancement.get('confidence_score', struct_pair.get('confidence_score', 0.8)),
                    'quality_score': ai_enhancement.get('quality_score', 0.8),
                    'issue_type': ai_enhancement.get('issue_type'),
                    'resolution_type': ai_enhancement.get('resolution_type'),
                    'tags': ai_enhancement.get('tags', []),
                    'metadata': {
                        **struct_pair.get('metadata', {}),
                        **ai_enhancement.get('metadata', {}),
                        'extraction_method': 'zendesk_ai_hybrid'
                    }
                }
            else:
                # Use structured extraction as-is
                merged_pair = {
                    **struct_pair,
                    'extraction_method': 'zendesk_structured',
                    'quality_score': struct_pair.get('confidence_score', 0.8)
                }
            
            merged.append(merged_pair)
        
        return merged

    def _interactions_to_html(self, interactions: List['Interaction']) -> str:
        """
        Convert Zendesk interactions to clean HTML for AI processing
        
        Args:
            interactions: List of parsed interactions
            
        Returns:
            Clean HTML representation
        """
        html_parts = ['<div class="conversation">']
        
        for interaction in interactions:
            role_class = f"message-{interaction.role.value}"
            sender = interaction.sender_name or interaction.sender_email or "Unknown"
            
            html_parts.append(f'''
<div class="message {role_class}">
    <div class="sender">{sender} ({interaction.role.value})</div>
    <div class="content">{interaction.content}</div>
    {f'<div class="timestamp">{interaction.timestamp}</div>' if interaction.timestamp else ''}
</div>
''')
        
        html_parts.append('</div>')
        
        return '\n'.join(html_parts)

    def extract_conversations_sync(self, html_content: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Synchronous wrapper for async extract_conversations method
        
        This method provides a synchronous interface to the async extraction functionality
        for use in synchronous contexts like Celery tasks.
        
        Args:
            html_content: HTML content to extract Q&A pairs from
            metadata: Optional metadata dictionary
            
        Returns:
            List of extracted Q&A pairs
        """
        if metadata is None:
            metadata = {}
            
        try:
            # Use asyncio.run to execute the async method in a new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.extract_conversations(html_content, metadata))
                return result
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Sync extraction failed: {e}")
            # Fallback to pattern-based extraction
            logger.info("Falling back to pattern-based extraction")
            fallback = FallbackExtractor()
            return fallback.extract_qa_pairs(html_content)


class FallbackExtractor:
    """Fallback pattern-based extractor when AI is unavailable"""
    
    def __init__(self):
        self.qa_patterns = [
            # Question patterns
            (re.compile(r'(?i)(how\s+(?:do|can)\s+i|what\s+(?:is|are)|why\s+(?:is|are|do)|when\s+(?:do|should))'), 'question'),
            # Problem statements
            (re.compile(r'(?i)(problem|issue|error|trouble|can\'t|cannot|unable|won\'t|doesn\'t)'), 'question'),
            # Solution patterns
            (re.compile(r'(?i)(try|follow|go\s+to|click|select|configure|set)'), 'answer'),
        ]
    
    def extract_qa_pairs(self, html_content: str) -> List[Dict[str, Any]]:
        """Pattern-based Q&A extraction as fallback"""
        
        # This is a simplified implementation
        # In production, would include more sophisticated pattern matching
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract text content
        text_elements = soup.find_all(text=True)
        
        qa_pairs = []
        current_question = None
        
        for text in text_elements:
            text = text.strip()
            if len(text) < 20:  # Skip short text
                continue
            
            # Check if it looks like a question
            if any(pattern[0].search(text) for pattern in self.qa_patterns if pattern[1] == 'question'):
                current_question = text
            # Check if it looks like an answer and we have a pending question
            elif current_question and any(pattern[0].search(text) for pattern in self.qa_patterns if pattern[1] == 'answer'):
                qa_pairs.append({
                    'question_text': current_question,
                    'answer_text': text,
                    'confidence_score': 0.6,  # Lower confidence for pattern-based
                    'extraction_method': 'pattern'
                })
                current_question = None
        
        return qa_pairs