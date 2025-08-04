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

# HTML parsing functionality removed - PDF and manual text processing only


@dataclass
class ExtractionConfig:
    """Configuration for AI extraction engine with intelligent rate limiting"""
    model_name: str = "gemini-2.5-flash-lite"  # Use Google's Gemini 2.5 Flash Lite model
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
    
    # Configurable conversation markers for generic content
    conversation_markers: List[str] = field(default_factory=lambda: [
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


class GeminiExtractionEngine:
    """Advanced extraction engine using Google's Gemini 2.5 Flash Lite model"""
    
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
        
        # HTML parsing functionality removed - PDF and manual text processing only


    async def extract_conversations(
        self, 
        content: str,
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract Q&A pairs with advanced context understanding"""
        
        if not content or not content.strip():
            logger.warning("Empty content provided for extraction")
            return []
        
        # Check if this is PDF content
        if metadata.get('file_format') == 'pdf':
            return await self._extract_from_pdf(content, metadata)
        
        # Original HTML processing
        html_content = content
        
        # HTML parsing functionality removed - continue with standard extraction
        
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
        """Build comprehensive extraction prompt with enhanced intelligence"""
        
        platform = metadata.get('platform', 'unknown')
        language = metadata.get('language', 'en')
        
        prompt = f"""
You are an expert AI assistant specializing in customer support conversation analysis. Analyze this {platform} support ticket with advanced comprehension.

## Your Task
Extract high-quality Q&A pairs that can help resolve similar customer issues in the future. Focus on actionable solutions and clear problem-resolution mappings.

## Extraction Guidelines

### 1. INTELLIGENT IDENTIFICATION:
   - Recognize both explicit questions AND implicit problems (e.g., "My emails won't sync" = implicit question about fixing sync)
   - Identify root causes, not just symptoms
   - Detect follow-up questions and their relationship to the main issue
   - Understand technical jargon and customer language variations

### 2. CONTEXT & COHERENCE:
   - Preserve critical context that makes the solution understandable
   - Include setup steps, prerequisites, or conditions mentioned
   - Maintain cause-and-effect relationships
   - Capture multi-step solutions as complete units

### 3. QUALITY ASSESSMENT:
   - confidence_score: How clearly the Q&A pair addresses the issue (0.0-1.0)
   - quality_score: How useful this Q&A would be for future similar issues (0.0-1.0)
   - Only extract if confidence_score > 0.6

### 4. INTELLIGENT CATEGORIZATION:
   issue_type options: "login", "sync", "performance", "configuration", "error", "feature_request", "billing", "other"
   resolution_type options: "solved", "workaround", "escalated", "not_resolved", "user_error", "known_issue"

### 5. SENTIMENT ANALYSIS:
   - Customer sentiment: "frustrated", "neutral", "satisfied", "urgent", "confused"
   - Technical level: "beginner", "intermediate", "advanced"
   - Resolution effectiveness: true/false

### 6. CONVERSATION SUMMARIZATION:
   - Extract the core problem in one clear sentence
   - Summarize the solution in actionable steps
   - Note any important warnings or prerequisites

## Output Format
Return a JSON array where each object has:
{{
    "question_text": "Clear, concise problem statement",
    "answer_text": "Complete, actionable solution",
    "context_before": "Essential setup or background info",
    "context_after": "Results or follow-up confirmation",
    "confidence_score": 0.0-1.0,
    "quality_score": 0.0-1.0,
    "issue_type": "specific_category",
    "resolution_type": "resolution_status",
    "tags": ["relevant", "searchable", "keywords"],
    "metadata": {{
        "sentiment": "customer_emotion",
        "technical_level": "expertise_required",
        "resolved": true/false,
        "solution_steps": ["step1", "step2"],
        "warnings": ["important_notes"],
        "related_features": ["feature_names"]
    }}
}}

## Content to Analyze:

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




    async def _extract_from_pdf(self, pdf_base64_content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract Q&A pairs from PDF content with intelligent conversation detection"""
        
        try:
            # Import enhanced PDF parser
            from app.feedme.parsers.pdf_parser import EnhancedPDFParser
            from app.feedme.parsers.ocr_fallback import OCRFallbackProcessor
            
            # Convert base64 content back to bytes
            import base64
            pdf_bytes = base64.b64decode(pdf_base64_content)
            
            # Parse PDF with conversation detection
            parser = EnhancedPDFParser()
            conversation_result = await parser.parse_pdf_with_conversations(pdf_bytes)
            
            if not conversation_result.success:
                logger.error(f"PDF parsing failed: {conversation_result.error_message}")
                return []
            
            logger.info(f"PDF parsed successfully: {conversation_result.metadata.pages} pages, {len(conversation_result.conversations)} conversations")
            
            # Check if OCR enhancement is needed
            ocr_processor = OCRFallbackProcessor()
            if ocr_processor.should_use_ocr(conversation_result.raw_text, ""):
                logger.info("Poor text extraction detected, attempting OCR enhancement")
                enhanced_text = await ocr_processor.enhance_text_with_ocr(conversation_result.raw_text, pdf_bytes)
                conversation_result.raw_text = enhanced_text
            
            # Extract Q&A pairs from PDF conversations
            if conversation_result.conversations:
                qa_pairs = await self._extract_from_pdf_conversations(conversation_result, metadata)
            else:
                # Fallback to basic text extraction
                qa_pairs = await self._extract_qa_from_pdf_text(conversation_result, metadata)
            
            return qa_pairs
            
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            return []
    
    async def _extract_from_pdf_conversations(self, pdf_result, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract Q&A pairs from PDF conversations with intelligent processing"""
        
        if not pdf_result.conversations:
            # Fall back to basic PDF extraction
            return await self._extract_qa_from_pdf_text(pdf_result, metadata)
        
        # Group conversations by thread
        conversation_threads = self._group_conversations_by_thread(pdf_result.conversations)
        
        all_qa_pairs = []
        
        for thread in conversation_threads:
            # Extract Q&A pairs from each thread
            thread_qa_pairs = await self._extract_qa_from_thread(thread, metadata)
            all_qa_pairs.extend(thread_qa_pairs)
        
        # Apply intelligent deduplication
        if len(all_qa_pairs) > 1:
            all_qa_pairs = self._deduplicate_qa_pairs_semantic(all_qa_pairs)
        
        return all_qa_pairs

    def _group_conversations_by_thread(self, conversations) -> List[List]:
        """Group conversations into logical threads"""
        threads = []
        current_thread = []
        
        for conv in sorted(conversations, key=lambda x: (x.page_number, x.timestamp or datetime.min)):
            if self._should_start_new_thread(conv, current_thread):
                if current_thread:
                    threads.append(current_thread)
                    current_thread = []
            
            current_thread.append(conv)
        
        if current_thread:
            threads.append(current_thread)
        
        return threads

    def _should_start_new_thread(self, conv, current_thread) -> bool:
        """Determine if conversation should start a new thread"""
        if not current_thread:
            return False
        
        last_conv = current_thread[-1]
        
        # Time gap > 1 hour suggests new thread
        if conv.timestamp and last_conv.timestamp:
            time_diff = (conv.timestamp - last_conv.timestamp).total_seconds()
            if time_diff > 3600:  # 1 hour
                return True
        
        # Different page + different speaker suggests new thread
        if conv.page_number != last_conv.page_number and conv.speaker != last_conv.speaker:
            return True
        
        return False

    async def _extract_qa_from_thread(self, thread, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract Q&A pairs from a conversation thread"""
        
        # Create PDF-specific extraction prompt
        prompt = self._build_pdf_thread_prompt(thread, metadata)
        
        try:
            # Extract using AI
            response = await self._extract_with_retry(prompt)
            
            if response:
                qa_pairs = self._parse_extraction_response(response.text)
                
                # Add thread metadata
                for qa_pair in qa_pairs:
                    qa_pair['source_format'] = 'pdf'
                    qa_pair['thread_id'] = thread[0].thread_id
                    qa_pair['page_range'] = f"{thread[0].page_number}-{thread[-1].page_number}"
                    qa_pair['extraction_method'] = 'pdf_conversation_aware'
                
                return qa_pairs
        except Exception as e:
            logger.warning(f"AI extraction failed for thread {thread[0].thread_id}: {e}")
        
        # Fallback to pattern-based extraction
        return self._extract_qa_from_thread_pattern(thread)

    def _build_pdf_thread_prompt(self, thread, metadata: Dict[str, Any]) -> str:
        """Build PDF-specific extraction prompt for conversation thread"""
        
        thread_context = ""
        for conv in thread:
            role_label = "Customer" if conv.role == 'customer' else "Support Agent"
            timestamp = conv.timestamp.strftime("%Y-%m-%d %H:%M") if conv.timestamp else "Unknown time"
            
            thread_context += f"""
{role_label} ({conv.speaker}) - {timestamp}:
{conv.content}

"""
        
        return f"""
You are analyzing a customer support conversation from a PDF ticket.

**Conversation Thread:**
{thread_context}

**Task:** Extract clear question-answer pairs from this conversation thread.

**Instructions:**
1. Identify customer questions, issues, or requests
2. Find corresponding support agent responses or solutions
3. Preserve technical details and context
4. Consider the conversation flow and dependencies
5. Only extract complete, meaningful Q&A pairs

**Output Format:** Return JSON array of Q&A pairs:
```json
[
  {{
    "question_text": "Customer's question or issue",
    "answer_text": "Support agent's response or solution",
    "context_before": "Relevant context before the exchange",
    "context_after": "Relevant context after the exchange", 
    "confidence_score": 0.0-1.0,
    "issue_type": "technical|account|general|other",
    "resolution_type": "resolved|escalated|pending|information_provided",
    "tags": ["relevant", "keywords"]
  }}
]
```

Extract all relevant Q&A pairs from this conversation thread:
"""
    
    def _extract_qa_from_thread_pattern(self, thread) -> List[Dict[str, Any]]:
        """Pattern-based extraction fallback for conversation thread"""
        qa_pairs = []
        
        # Simple pattern matching for customer questions followed by agent answers
        for i, conv in enumerate(thread):
            if conv.role == 'customer' and i + 1 < len(thread):
                next_conv = thread[i + 1]
                if next_conv.role == 'agent':
                    qa_pair = {
                        'question_text': conv.content,
                        'answer_text': next_conv.content,
                        'context_before': thread[i - 1].content if i > 0 else "",
                        'context_after': thread[i + 2].content if i + 2 < len(thread) else "",
                        'confidence_score': 0.6,  # Lower confidence for pattern-based
                        'extraction_method': 'pdf_pattern',
                        'source_format': 'pdf',
                        'thread_id': conv.thread_id,
                        'page_range': f"{conv.page_number}-{next_conv.page_number}",
                        'issue_type': 'general',
                        'resolution_type': 'information_provided',
                        'tags': ['pdf_extraction', 'pattern_based']
                    }
                    qa_pairs.append(qa_pair)
        
        return qa_pairs

    def _deduplicate_qa_pairs_semantic(self, qa_pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Basic semantic deduplication for Q&A pairs"""
        if len(qa_pairs) <= 1:
            return qa_pairs
        
        # Simple deduplication based on question similarity
        unique_pairs = []
        seen_questions = set()
        
        for pair in qa_pairs:
            question = pair.get('question_text', '').strip().lower()
            
            # Create a simple signature for the question
            question_words = set(question.split())
            
            # Check if this question is similar to any we've seen
            is_duplicate = False
            for seen_q in seen_questions:
                seen_words = set(seen_q.split())
                if question_words and seen_words:
                    # Simple Jaccard similarity
                    similarity = len(question_words.intersection(seen_words)) / len(question_words.union(seen_words))
                    if similarity > 0.7:  # 70% similarity threshold
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                seen_questions.add(question)
                unique_pairs.append(pair)
        
        logger.info(f"Semantic deduplication: {len(qa_pairs)} → {len(unique_pairs)} pairs")
        return unique_pairs

    async def _extract_qa_from_pdf_text(self, parse_result, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract Q&A pairs from parsed PDF text using AI"""
        
        if not parse_result.total_text:
            logger.warning("No text extracted from PDF")
            return []
        
        # Build PDF-specific prompt
        pdf_prompt = self._build_pdf_extraction_prompt(parse_result, metadata)
        
        # Use intelligent chunking for large PDFs
        if parse_result.total_chars > self.config.max_tokens_per_chunk:
            return await self._chunked_pdf_extraction(parse_result, metadata)
        
        # Extract Q&A pairs using AI
        try:
            response = await self._extract_with_retry(pdf_prompt)
            if response:
                qa_pairs = self._parse_extraction_response(response.text)
                
                # Add PDF-specific metadata to each Q&A pair
                for qa_pair in qa_pairs:
                    qa_pair['source_format'] = 'pdf'
                    qa_pair['source_pages'] = parse_result.metadata.pages
                    qa_pair['extraction_method'] = 'pdf_ai'
                
                logger.info(f"Extracted {len(qa_pairs)} Q&A pairs from PDF")
                return qa_pairs
                
        except Exception as e:
            logger.error(f"AI extraction from PDF failed: {e}")
            
        # Fallback to pattern-based extraction
        return await self._fallback_pdf_pattern_extraction(parse_result.total_text)

    def _build_pdf_extraction_prompt(self, parse_result, metadata: Dict[str, Any]) -> str:
        """Build PDF-specific extraction prompt"""
        
        pdf_text = parse_result.total_text
        page_count = parse_result.metadata.pages
        
        return f"""
You are an expert at extracting customer support Q&A pairs from PDF documents.

**PDF Document Information:**
- Pages: {page_count}
- Characters: {parse_result.total_chars}
- Filename: {metadata.get('original_filename', 'Unknown')}

**PDF Content:**
{pdf_text}

**Task:** Extract clear question-answer pairs from this PDF document. This is likely a customer support ticket or email conversation.

**Instructions:**
1. Identify customer questions, issues, or requests
2. Find corresponding support agent responses or solutions
3. Look for conversation threads across pages
4. Preserve important context and technical details
5. Handle multi-page conversations that may span across page breaks

**Output Format:** Return a JSON array of question-answer pairs:
```json
[
  {{
    "question_text": "Customer's question or issue description",
    "answer_text": "Support agent's response or solution",
    "context_before": "Relevant context before the exchange",
    "context_after": "Relevant context after the exchange",
    "confidence_score": 0.0-1.0,
    "issue_type": "technical|account|billing|general|other",
    "resolution_type": "resolved|escalated|pending|information_provided|workaround",
    "tags": ["relevant", "topic", "keywords"]
  }}
]
```

**Quality Guidelines:**
- Only extract clear, meaningful Q&A pairs
- Maintain technical accuracy and context
- Focus on actionable information
- Skip navigation, headers, and boilerplate text
- Confidence score should reflect clarity and completeness

Extract all relevant Q&A pairs from this PDF document:
"""

    async def _chunked_pdf_extraction(self, parse_result, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle large PDF extraction with chunking"""
        
        all_qa_pairs = []
        
        # Process page by page for better context preservation
        for page in parse_result.pages:
            if not page.text or len(page.text) < 50:
                continue
                
            try:
                # Build prompt for this page
                page_prompt = self._build_page_extraction_prompt(page, metadata)
                
                # Extract Q&A pairs from this page
                response = await self._extract_with_retry(page_prompt)
                if response:
                    page_qa_pairs = self._parse_extraction_response(response.text)
                    
                    # Add page-specific metadata
                    for qa_pair in page_qa_pairs:
                        qa_pair['source_page'] = page.page_number
                        qa_pair['source_format'] = 'pdf'
                        qa_pair['extraction_method'] = 'pdf_ai_chunked'
                    
                    all_qa_pairs.extend(page_qa_pairs)
                    
            except Exception as e:
                logger.warning(f"Failed to extract from page {page.page_number}: {e}")
                continue
        
        logger.info(f"Chunked PDF extraction complete: {len(all_qa_pairs)} Q&A pairs from {len(parse_result.pages)} pages")
        return all_qa_pairs

    def _build_page_extraction_prompt(self, page, metadata: Dict[str, Any]) -> str:
        """Build extraction prompt for a single PDF page"""
        
        return f"""
You are extracting customer support Q&A pairs from page {page.page_number} of a PDF document.

**Page Content:**
{page.text}

**Task:** Extract clear question-answer pairs from this page. This is part of a customer support ticket or email conversation.

**Instructions:**
1. Look for customer questions, issues, or requests on this page
2. Find corresponding support agent responses or solutions
3. Preserve important context and technical details
4. Note if conversations appear to continue from previous pages or to next pages

**Output Format:** Return a JSON array of question-answer pairs:
```json
[
  {{
    "question_text": "Customer's question or issue description",
    "answer_text": "Support agent's response or solution",
    "context_before": "Relevant context before the exchange",
    "context_after": "Relevant context after the exchange",
    "confidence_score": 0.0-1.0,
    "issue_type": "technical|account|billing|general|other",
    "resolution_type": "resolved|escalated|pending|information_provided|workaround",
    "tags": ["relevant", "topic", "keywords"]
  }}
]
```

Extract all relevant Q&A pairs from this page:
"""

    async def _fallback_pdf_pattern_extraction(self, pdf_text: str) -> List[Dict[str, Any]]:
        """Fallback pattern-based extraction for PDF content"""
        
        qa_pairs = []
        
        # Split text into lines for pattern matching
        lines = pdf_text.split('\n')
        
        current_question = None
        current_answer = None
        
        # PDF-specific patterns
        question_patterns = [
            r'^(Customer|Client|User):\s*(.+)',
            r'^Q:\s*(.+)',
            r'^Question:\s*(.+)',
            r'(.+\?)\s*$',  # Lines ending with question mark
            r'^Issue:\s*(.+)',
            r'^Problem:\s*(.+)'
        ]
        
        answer_patterns = [
            r'^(Agent|Support|Admin|Rep):\s*(.+)',
            r'^A:\s*(.+)',
            r'^Answer:\s*(.+)',
            r'^Solution:\s*(.+)',
            r'^Resolution:\s*(.+)',
            r'^Response:\s*(.+)'
        ]
        
        for line in lines:
            line = line.strip()
            if len(line) < 10:
                continue
            
            # Check for question patterns
            question_match = None
            for pattern in question_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    question_match = match
                    break
            
            if question_match:
                current_question = question_match.group(-1).strip()
                continue
            
            # Check for answer patterns
            answer_match = None
            for pattern in answer_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    answer_match = match
                    break
            
            if answer_match and current_question:
                current_answer = answer_match.group(-1).strip()
                
                qa_pairs.append({
                    'question_text': current_question,
                    'answer_text': current_answer,
                    'confidence_score': 0.5,  # Lower confidence for pattern-based
                    'extraction_method': 'pdf_pattern',
                    'source_format': 'pdf',
                    'issue_type': 'general',
                    'resolution_type': 'information_provided',
                    'tags': ['pdf_extraction']
                })
                
                current_question = None
                current_answer = None
        
        logger.info(f"Pattern-based PDF extraction found {len(qa_pairs)} Q&A pairs")
        return qa_pairs

    def extract_conversations_sync(self, content: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Synchronous wrapper for async extract_conversations method
        
        This method provides a synchronous interface to the async extraction functionality
        for use in synchronous contexts like Celery tasks. Supports extracting Q&A pairs
        from both HTML content (e.g., Zendesk emails) and PDF content (provided as hex string).
        
        Args:
            content: Content to extract Q&A pairs from (HTML or PDF hex)
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
                result = loop.run_until_complete(self.extract_conversations(content, metadata))
                return result
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Sync extraction failed: {e}")
            # Fallback to pattern-based extraction
            logger.info("Falling back to pattern-based extraction")
            fallback = FallbackExtractor()
            return fallback.extract_qa_pairs(content)
    
    async def summarize_conversation(
        self, 
        conversation_text: str, 
        max_length: int = 500,
        focus: str = "key_points"
    ) -> Dict[str, Any]:
        """
        Generate intelligent conversation summary with sentiment and insights
        
        Args:
            conversation_text: Full conversation text to summarize
            max_length: Maximum length of summary in characters
            focus: Summary focus - "key_points", "technical_issues", "resolution"
            
        Returns:
            Dict containing summary, sentiment, key topics, and action items
        """
        try:
            # Create specialized summarization prompt
            prompt = f"""Analyze and summarize this customer support conversation.
Focus: {focus}
Maximum summary length: {max_length} characters

Conversation:
{conversation_text[:8000]}  # Limit input to avoid token limits

Provide a JSON response with:
{{
    "summary": "Concise summary focusing on {focus}",
    "sentiment": {{
        "overall": "positive/neutral/negative/mixed",
        "customer_start": "frustrated/confused/neutral/satisfied",
        "customer_end": "frustrated/confused/neutral/satisfied",
        "sentiment_shift": "improved/unchanged/worsened"
    }},
    "key_topics": ["topic1", "topic2", ...],
    "technical_issues": ["issue1", "issue2", ...],
    "resolution_status": "resolved/partial/unresolved/escalated",
    "action_items": ["action1", "action2", ...],
    "agent_performance": {{
        "empathy": "high/medium/low",
        "technical_knowledge": "expert/proficient/basic",
        "problem_solving": "excellent/good/needs_improvement"
    }}
}}"""

            # Call Gemini API
            response = await self._extract_with_retry(prompt)
            
            if not response:
                raise Exception("No response from AI model")
            
            # Parse JSON response
            summary_data = self._parse_json_response(response.text)
            
            # Add metadata
            summary_data['conversation_length'] = len(conversation_text)
            summary_data['summarization_model'] = self.config.model_name
            summary_data['focus_type'] = focus
            
            return {
                'success': True,
                'data': summary_data,
                'confidence': 0.9
            }
            
        except Exception as e:
            logger.error(f"Conversation summarization failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'data': {
                    'summary': 'Summary generation failed',
                    'sentiment': {'overall': 'unknown'}
                }
            }
    
    async def analyze_conversation_batch(
        self, 
        conversations: List[Dict[str, Any]], 
        analysis_type: str = "patterns"
    ) -> Dict[str, Any]:
        """
        Analyze a batch of conversations for patterns and insights
        
        Args:
            conversations: List of conversation dictionaries
            analysis_type: "patterns", "quality", "training_gaps"
            
        Returns:
            Dict containing batch analysis results
        """
        try:
            # Prepare batch for analysis
            batch_text = "\n\n---CONVERSATION BREAK---\n\n".join([
                f"Q: {conv.get('question_text', '')}\nA: {conv.get('answer_text', '')}"
                for conv in conversations[:20]  # Limit to prevent token overflow
            ])
            
            prompt = f"""Analyze this batch of customer support conversations for {analysis_type}.

Conversations:
{batch_text}

Provide a JSON response with:
{{
    "common_issues": [
        {{"issue": "description", "frequency": count, "severity": "high/medium/low"}}
    ],
    "resolution_patterns": [
        {{"pattern": "description", "effectiveness": "high/medium/low", "examples": count}}
    ],
    "knowledge_gaps": [
        {{"topic": "description", "impact": "high/medium/low", "recommendation": "action"}}
    ],
    "quality_metrics": {{
        "average_resolution_quality": 0.0-1.0,
        "response_appropriateness": 0.0-1.0,
        "technical_accuracy": 0.0-1.0
    }},
    "training_recommendations": ["recommendation1", "recommendation2", ...],
    "automation_opportunities": [
        {{"scenario": "description", "confidence": 0.0-1.0, "potential_impact": "description"}}
    ]
}}"""

            # Call Gemini API
            response = await self._extract_with_retry(prompt)
            
            if not response:
                raise Exception("No response from AI model")
            
            # Parse JSON response
            analysis_data = self._parse_json_response(response.text)
            
            # Add metadata
            analysis_data['total_conversations_analyzed'] = len(conversations)
            analysis_data['analysis_type'] = analysis_type
            analysis_data['analysis_model'] = self.config.model_name
            
            return {
                'success': True,
                'data': analysis_data,
                'insights_generated': len(analysis_data.get('common_issues', [])) + 
                                    len(analysis_data.get('knowledge_gaps', []))
            }
            
        except Exception as e:
            logger.error(f"Batch conversation analysis failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'data': {}
            }
    
    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON response from AI model with error handling"""
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
            return json.loads(cleaned_text)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response_text[:500]}...")
            return {}


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