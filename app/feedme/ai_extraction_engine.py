"""
FeedMe v2.0 AI Extraction Engine
Advanced Q&A extraction using Google's Gemma-3-27b-it model for intelligent conversation parsing
"""

import json
import logging
import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

import google.generativeai as genai
from bs4 import BeautifulSoup
from google.api_core.exceptions import ResourceExhausted, InvalidArgument

from app.core.settings import settings
from app.feedme.schemas import ProcessingStatus, IssueType, ResolutionType

logger = logging.getLogger(__name__)


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
        """Estimate token count (rough approximation: 1 token ≈ 4 characters)"""
        return len(text) // 4
        
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
        oldest_in_window = min(self.token_usage, key=lambda x: x[0])[0] if self.token_usage else time.time()
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

    async def extract_conversations(
        self, 
        html_content: str,
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract Q&A pairs with advanced context understanding"""
        
        if not html_content or not html_content.strip():
            logger.warning("Empty HTML content provided for extraction")
            return []
        
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
                return self._fallback_pattern_extraction(html_content)
            
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
                return self._fallback_pattern_extraction(html_content)
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
                error_msg = str(e)
                
                # Check if it's a quota/rate limit error
                if "quota" in error_msg.lower() or "rate" in error_msg.lower():
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
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for conversation boundaries (common email/chat patterns)
            conversation_markers = [
                'div.zd-liquid-comment',  # Zendesk comments
                'div.email-message',      # Email messages
                'div.message',            # Generic messages
                'table.message',          # Table-based messages
                'blockquote',             # Quoted text
                'p[style*="margin-top"]'  # Styled separators
            ]
            
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
        """Merge and deduplicate Q&A pairs from multiple chunks"""
        
        seen_questions = set()
        merged_pairs = []
        
        for pair in pairs:
            question = pair.get('question_text', '').strip().lower()
            
            # Simple deduplication based on question similarity
            if question and question not in seen_questions:
                # Check for partial duplicates (questions that are very similar)
                is_duplicate = False
                for seen_q in seen_questions:
                    if len(question) > 10 and len(seen_q) > 10:
                        # Check if questions are very similar (simple word overlap)
                        q_words = set(question.split())
                        seen_words = set(seen_q.split())
                        overlap = len(q_words.intersection(seen_words)) / len(q_words.union(seen_words))
                        
                        if overlap > 0.8:  # 80% word overlap threshold
                            is_duplicate = True
                            break
                
                if not is_duplicate:
                    seen_questions.add(question)
                    merged_pairs.append(pair)
        
        logger.info(f"Merged {len(pairs)} pairs into {len(merged_pairs)} unique pairs")
        return merged_pairs

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


class FallbackExtractor:
    """Fallback pattern-based extractor when AI is unavailable"""
    
    def __init__(self):
        self.qa_patterns = [
            # Question patterns
            (r'(?i)(how\s+(?:do|can)\s+i|what\s+(?:is|are)|why\s+(?:is|are|do)|when\s+(?:do|should))', 'question'),
            # Problem statements
            (r'(?i)(problem|issue|error|trouble|can\'t|cannot|unable|won\'t|doesn\'t)', 'question'),
            # Solution patterns
            (r'(?i)(try|follow|go\s+to|click|select|configure|set)', 'answer'),
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