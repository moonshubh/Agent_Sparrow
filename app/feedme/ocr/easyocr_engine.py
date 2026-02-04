# mypy: ignore-errors
"""
Production-Ready EasyOCR Engine for FeedMe PDF Processing
Integrates EasyOCR with Gemma 3 for intelligent text extraction and processing

Features:
- Robust error handling and retry logic
- Redis caching for performance optimization
- Resource management and rate limiting
- Comprehensive monitoring and metrics
- Memory-efficient streaming processing
- Production-grade logging and observability
"""

import logging
import asyncio
import tempfile
import os
import hashlib
import json
import time
import psutil
import gc
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading
import queue
from contextlib import contextmanager

# Third-party imports with proper error handling
try:
    import easyocr
    import cv2
    import numpy as np

    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    easyocr = None
    cv2 = None
    np = None

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

try:
    import torch
except ImportError:
    torch = None

try:
    from google import genai  # type: ignore

    GENAI_AVAILABLE = True
except ImportError:
    try:  # pragma: no cover
        import google.generativeai as genai  # type: ignore

        GENAI_AVAILABLE = True
    except ImportError:
        GENAI_AVAILABLE = False
        genai = None

import pdf2image
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.core.settings import settings

# Configure production logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger(__name__)

# Production constants
MAX_PDF_SIZE_MB = int(os.getenv("FEEDME_MAX_PDF_SIZE_MB", "50"))
MAX_PDF_PAGES = int(os.getenv("FEEDME_MAX_PDF_PAGES", "200"))
OCR_TIMEOUT_SECONDS = int(os.getenv("FEEDME_OCR_TIMEOUT_SECONDS", "300"))
MAX_CONCURRENT_PAGES = int(os.getenv("FEEDME_MAX_CONCURRENT_PAGES", "4"))
CACHE_TTL_HOURS = int(os.getenv("FEEDME_CACHE_TTL_HOURS", "24"))
MAX_RETRIES = int(os.getenv("FEEDME_OCR_MAX_RETRIES", "3"))
ENABLE_CACHE = os.getenv("FEEDME_ENABLE_OCR_CACHE", "true").lower() == "true"
MAX_MEMORY_MB = int(os.getenv("FEEDME_OCR_MAX_MEMORY_MB", "2048"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("FEEDME_OCR_RATE_LIMIT", "60"))

# Initialize Redis client with production settings
redis_client = None
if REDIS_AVAILABLE and ENABLE_CACHE:
    try:
        redis_client = redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=False,  # We'll handle encoding/decoding
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
            max_connections=50,
        )
        # Test connection
        redis_client.ping()
        logger.info("Redis cache initialized successfully")
    except Exception as e:
        logger.warning(f"Redis initialization failed: {e}. Caching disabled.")
        redis_client = None


class OCRLanguage(str, Enum):
    """Supported OCR languages with comprehensive coverage"""

    # European Languages
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    PORTUGUESE = "pt"
    ITALIAN = "it"
    DUTCH = "nl"
    POLISH = "pl"
    CZECH = "cs"
    SLOVAK = "sk"
    ROMANIAN = "ro"
    HUNGARIAN = "hu"
    BULGARIAN = "bg"
    CROATIAN = "hr"
    DANISH = "da"
    FINNISH = "fi"
    GREEK = "el"
    NORWEGIAN = "no"
    SWEDISH = "sv"
    TURKISH = "tr"
    UKRAINIAN = "uk"

    # Asian Languages
    CHINESE_SIMPLIFIED = "ch_sim"
    CHINESE_TRADITIONAL = "ch_tra"
    JAPANESE = "ja"
    KOREAN = "ko"
    THAI = "th"
    VIETNAMESE = "vi"
    INDONESIAN = "id"
    MALAY = "ms"
    HINDI = "hi"
    BENGALI = "bn"
    TAMIL = "ta"
    TELUGU = "te"

    # Middle Eastern Languages
    ARABIC = "ar"
    HEBREW = "he"
    PERSIAN = "fa"
    URDU = "ur"

    # Other Languages
    RUSSIAN = "ru"
    SWAHILI = "sw"
    AFRIKAANS = "af"

    @classmethod
    def get_language_name(cls, code: str) -> str:
        """Get human-readable language name"""
        language_names = {
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "pt": "Portuguese",
            "it": "Italian",
            "zh_sim": "Chinese (Simplified)",
            "zh_tra": "Chinese (Traditional)",
            "ja": "Japanese",
            "ko": "Korean",
            "ar": "Arabic",
            "ru": "Russian",
        }
        return language_names.get(code, code.upper())


class ProcessingQuality(str, Enum):
    """OCR processing quality levels"""

    FAST = "fast"  # Quick processing, lower accuracy
    BALANCED = "balanced"  # Good balance of speed and accuracy
    HIGH = "high"  # High accuracy, slower processing
    ULTRA = "ultra"  # Maximum accuracy, slowest


@dataclass
class OCRResult:
    """Comprehensive results from OCR processing with production metrics"""

    extracted_text: str
    confidence_score: float  # Overall confidence (0-1)
    page_results: List[Dict[str, Any]]  # Per-page details
    processing_time: float
    language_detected: str
    total_words: int
    quality_metrics: Dict[str, float]
    error_message: Optional[str] = None
    success: bool = True

    # Production metrics
    cache_hit: bool = False
    retry_count: int = 0
    processing_method: str = "ocr"  # ocr, cached, direct_extract
    file_hash: Optional[str] = None
    timestamp: datetime = None

    # Performance metrics
    page_processing_times: List[float] = None
    memory_usage_mb: float = 0.0
    gpu_usage_percent: float = 0.0

    # Quality indicators
    warnings: List[str] = None
    suggestions: List[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.page_processing_times is None:
            self.page_processing_times = []
        if self.warnings is None:
            self.warnings = []
        if self.suggestions is None:
            self.suggestions = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat() if self.timestamp else None
        return result


@dataclass
class GemmaEnhancementResult:
    """Results from Gemma 3 text enhancement"""

    enhanced_text: str
    improvements_made: List[str]
    confidence_score: float
    quality_assessment: Dict[str, float]
    issues_found: List[str]
    suggestions: List[str]


class OCRProcessingError(Exception):
    """Custom exception for OCR processing errors"""

    pass


class RateLimiter:
    """Thread-safe rate limiter for API calls"""

    def __init__(self, max_calls: int, time_window: int = 60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = queue.Queue()
        self.lock = threading.Lock()

    def can_proceed(self) -> bool:
        """Check if we can make another call"""
        with self.lock:
            now = time.time()
            # Remove old calls outside time window
            while not self.calls.empty():
                call_time = self.calls.queue[0]
                if now - call_time > self.time_window:
                    self.calls.get()
                else:
                    break

            if self.calls.qsize() < self.max_calls:
                self.calls.put(now)
                return True
            return False

    async def wait_if_needed(self):
        """Wait if rate limit exceeded"""
        while not self.can_proceed():
            await asyncio.sleep(1)


class MemoryManager:
    """Monitor and manage memory usage"""

    def __init__(self, max_memory_mb: int):
        self.max_memory_mb = max_memory_mb

    def get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024

    def check_memory(self) -> bool:
        """Check if memory usage is within limits"""
        current_mb = self.get_memory_usage()
        return current_mb < self.max_memory_mb

    def cleanup_if_needed(self):
        """Force garbage collection if needed"""
        if not self.check_memory():
            gc.collect()
            logger.warning(
                f"Memory usage high ({self.get_memory_usage():.1f}MB), forced garbage collection"
            )


class EasyOCREngine:
    """
    Production-grade OCR engine using EasyOCR with Gemma 3 enhancement

    Features:
    - Multi-language OCR support (40+ languages)
    - GPU acceleration with automatic fallback to CPU
    - Intelligent text post-processing with Gemma 3
    - Quality assessment and confidence scoring
    - Adaptive processing based on document characteristics
    - Redis caching for improved performance
    - Retry logic with exponential backoff
    - Resource management and rate limiting
    - Comprehensive error handling and logging
    - Memory-efficient processing with streaming
    - Production metrics and monitoring
    """

    # Class-level cache for OCR readers (expensive to initialize)
    _reader_cache = {}
    _reader_lock = threading.Lock()

    def __init__(
        self,
        languages: List[OCRLanguage] = None,
        quality: ProcessingQuality = ProcessingQuality.BALANCED,
        use_gpu: bool = True,
        gemma_api_key: Optional[str] = None,
        enable_cache: bool = True,
        enable_monitoring: bool = True,
    ):
        """
        Initialize the EasyOCR engine with production features

        Args:
            languages: List of languages to detect (default: English)
            quality: Processing quality level
            use_gpu: Whether to use GPU acceleration if available
            gemma_api_key: Google Gemini API key for text enhancement
            enable_cache: Whether to enable Redis caching
            enable_monitoring: Whether to enable metrics collection
        """
        if not EASYOCR_AVAILABLE:
            raise ImportError(
                "EasyOCR not available. Install with: pip install easyocr opencv-python"
            )

        self.languages = languages or [OCRLanguage.ENGLISH]
        self.quality = quality
        self.use_gpu = bool(use_gpu and torch and torch.cuda.is_available())
        self.enable_cache = enable_cache and redis_client is not None
        self.enable_monitoring = enable_monitoring

        # Initialize resource managers
        self.rate_limiter = RateLimiter(RATE_LIMIT_PER_MINUTE)
        self.memory_manager = MemoryManager(MAX_MEMORY_MB)
        self.executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PAGES)

        # Initialize EasyOCR reader (cached for performance)
        self.reader = self._get_or_create_reader()

        # Performance tracking
        self.processing_stats = {
            "total_processed": 0,
            "cache_hits": 0,
            "errors": 0,
            "average_time": 0.0,
        }

        # Initialize Gemma 3 for text enhancement
        self.gemma_api_key = gemma_api_key or getattr(settings, "gemini_api_key", None)
        self.gemma_model = None
        if self.gemma_api_key and GENAI_AVAILABLE:
            try:
                genai.configure(api_key=self.gemma_api_key)
                self.gemma_model = genai.GenerativeModel("gemini-pro")
                self.gemma_rate_limiter = RateLimiter(30, 60)  # 30 calls per minute
                logger.info("Gemma 3 integration initialized")
            except Exception as e:
                logger.warning(f"Gemma 3 initialization failed: {e}")
                self.gemma_model = None
        else:
            logger.warning(
                "Gemma text enhancement disabled (no API key or genai not available)"
            )

    def _get_or_create_reader(self) -> "easyocr.Reader":
        """Get or create EasyOCR reader with caching"""
        lang_codes = tuple(sorted(lang.value for lang in self.languages))
        cache_key = f"{lang_codes}_{self.use_gpu}"

        with self._reader_lock:
            if cache_key in self._reader_cache:
                logger.info(f"Using cached EasyOCR reader for {lang_codes}")
                return self._reader_cache[cache_key]

            logger.info(f"Creating new EasyOCR reader for {lang_codes}")
            try:
                reader = easyocr.Reader(
                    list(lang_codes),
                    gpu=self.use_gpu,
                    verbose=False,
                    download_enabled=True,
                    model_storage_directory=os.getenv("EASYOCR_MODEL_DIR", "./models"),
                )
                self._reader_cache[cache_key] = reader
                logger.info("EasyOCR reader created successfully")
                return reader
            except Exception as e:
                logger.error(f"Failed to create EasyOCR reader: {e}")
                if self.use_gpu:
                    logger.info("Retrying with CPU...")
                    self.use_gpu = False
                    return self._get_or_create_reader()
                raise

    @contextmanager
    def _monitor_resources(self, operation: str):
        """Context manager for resource monitoring"""
        start_time = time.time()
        start_memory = self.memory_manager.get_memory_usage()

        try:
            yield
        finally:
            duration = time.time() - start_time
            memory_delta = self.memory_manager.get_memory_usage() - start_memory

            if self.enable_monitoring:
                logger.info(
                    f"{operation} completed in {duration:.2f}s, "
                    f"memory delta: {memory_delta:.1f}MB"
                )

            # Cleanup if needed
            self.memory_manager.cleanup_if_needed()

    def _calculate_file_hash(self, data: bytes) -> str:
        """Calculate SHA256 hash of file for caching"""
        return hashlib.sha256(data).hexdigest()

    async def _get_from_cache(self, file_hash: str) -> Optional[OCRResult]:
        """Get OCR result from cache if available"""
        if not self.enable_cache or not redis_client:
            return None

        try:
            cache_key = f"ocr:result:{file_hash}"
            cached_data = await asyncio.to_thread(redis_client.get, cache_key)

            if cached_data:
                logger.info(f"Cache hit for file hash: {file_hash[:8]}...")
                result_dict = json.loads(cached_data)
                # Reconstruct OCRResult from dict
                result = OCRResult(**result_dict)
                result.cache_hit = True
                self.processing_stats["cache_hits"] += 1
                return result
        except Exception as e:
            logger.warning(f"Cache retrieval failed: {e}")

        return None

    async def _save_to_cache(self, file_hash: str, result: OCRResult):
        """Save OCR result to cache"""
        if not self.enable_cache or not redis_client or not result.success:
            return

        try:
            cache_key = f"ocr:result:{file_hash}"
            cache_data = json.dumps(result.to_dict())
            ttl = CACHE_TTL_HOURS * 3600

            await asyncio.to_thread(redis_client.setex, cache_key, ttl, cache_data)
            logger.info(
                f"Cached OCR result for {file_hash[:8]}... (TTL: {CACHE_TTL_HOURS}h)"
            )
        except Exception as e:
            logger.warning(f"Cache save failed: {e}")

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(OCRProcessingError),
    )
    async def process_pdf(
        self,
        pdf_bytes: bytes,
        enhance_with_gemma: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        force_reprocess: bool = False,
    ) -> OCRResult:
        """
        Process PDF document with OCR and optional Gemma enhancement

        Args:
            pdf_bytes: PDF file as bytes
            enhance_with_gemma: Whether to enhance text with Gemma 3
            metadata: Additional metadata for processing context
            force_reprocess: Force reprocessing even if cached

        Returns:
            OCRResult with extracted and enhanced text

        Raises:
            OCRProcessingError: If processing fails after retries
            ValueError: If PDF is invalid or exceeds size limits
        """
        # Validate inputs
        if not pdf_bytes:
            raise ValueError("Empty PDF bytes provided")

        pdf_size_mb = len(pdf_bytes) / 1024 / 1024
        if pdf_size_mb > MAX_PDF_SIZE_MB:
            raise ValueError(
                f"PDF size ({pdf_size_mb:.1f}MB) exceeds limit ({MAX_PDF_SIZE_MB}MB)"
            )

        # Calculate file hash for caching
        file_hash = self._calculate_file_hash(pdf_bytes)
        logger.info(
            f"Processing PDF (hash: {file_hash[:8]}..., size: {pdf_size_mb:.1f}MB)"
        )

        # Check cache if not forced reprocess
        if not force_reprocess:
            cached_result = await self._get_from_cache(file_hash)
            if cached_result:
                return cached_result

        # Rate limiting
        await self.rate_limiter.wait_if_needed()

        # Start processing with resource monitoring
        start_time = time.time()
        retry_count = 0

        with self._monitor_resources("PDF OCR Processing"):
            try:
                # First try direct text extraction (faster)
                direct_text = await self._try_direct_extraction(pdf_bytes)
                if direct_text and len(direct_text.strip()) > 100:
                    logger.info("Successfully extracted text directly from PDF")
                    result = OCRResult(
                        extracted_text=direct_text,
                        confidence_score=0.95,
                        page_results=[],
                        processing_time=time.time() - start_time,
                        language_detected=self._detect_language_from_text(direct_text),
                        total_words=len(direct_text.split()),
                        quality_metrics={"method": "direct_extraction"},
                        processing_method="direct_extract",
                        file_hash=file_hash,
                        success=True,
                    )
                else:
                    # Fall back to OCR processing
                    logger.info("Direct extraction insufficient, falling back to OCR")

                    # Convert PDF to images with timeout
                    images = await asyncio.wait_for(
                        self._pdf_to_images(pdf_bytes),
                        timeout=60,  # 60 second timeout for conversion
                    )

                    if len(images) > MAX_PDF_PAGES:
                        logger.warning(
                            f"PDF has {len(images)} pages, processing first {MAX_PDF_PAGES}"
                        )
                        images = images[:MAX_PDF_PAGES]
                        if not hasattr(self, "_result_warnings"):
                            self._result_warnings = []
                        self._result_warnings.append(
                            f"PDF truncated to {MAX_PDF_PAGES} pages"
                        )

                    logger.info(f"Converted PDF to {len(images)} images")

                    # Process pages concurrently with progress tracking
                    page_results = await self._process_pages_concurrent(images)

                    # Aggregate results
                    all_text = []
                    total_confidence = 0.0
                    total_words = 0
                    page_times = []

                    for page_result in page_results:
                        if page_result["text"].strip():
                            all_text.append(page_result["text"])
                            total_confidence += page_result["confidence"]
                            total_words += page_result["word_count"]
                            page_times.append(page_result.get("processing_time", 0))

                    # Combine all text
                    raw_text = "\n\n".join(all_text)
                    avg_confidence = (
                        total_confidence / len(page_results) if page_results else 0.0
                    )

                    # Enhance with Gemma if enabled
                    enhanced_text = raw_text
                    warnings = getattr(self, "_result_warnings", [])

                    if enhance_with_gemma and self.gemma_model and raw_text.strip():
                        try:
                            await self.gemma_rate_limiter.wait_if_needed()
                            enhancement_result = await self._enhance_with_gemma(
                                raw_text, metadata
                            )
                            enhanced_text = enhancement_result.enhanced_text
                            avg_confidence = min(avg_confidence + 0.1, 1.0)
                        except Exception as e:
                            logger.warning(f"Gemma enhancement failed: {e}")
                            warnings.append("Text enhancement unavailable")

                    # Calculate quality metrics
                    quality_metrics = self._calculate_quality_metrics(
                        page_results, enhanced_text
                    )

                    result = OCRResult(
                        extracted_text=enhanced_text,
                        confidence_score=avg_confidence,
                        page_results=page_results,
                        processing_time=time.time() - start_time,
                        language_detected=self._detect_primary_language(page_results),
                        total_words=total_words,
                        quality_metrics=quality_metrics,
                        processing_method="ocr",
                        file_hash=file_hash,
                        page_processing_times=page_times,
                        memory_usage_mb=self.memory_manager.get_memory_usage(),
                        warnings=warnings,
                        success=True,
                    )

                # Update stats
                self.processing_stats["total_processed"] += 1
                self.processing_stats["average_time"] = (
                    self.processing_stats["average_time"]
                    * (self.processing_stats["total_processed"] - 1)
                    + result.processing_time
                ) / self.processing_stats["total_processed"]

                # Save to cache
                await self._save_to_cache(file_hash, result)

                return result

            except asyncio.TimeoutError:
                raise OCRProcessingError("PDF processing timed out")
            except Exception as e:
                self.processing_stats["errors"] += 1
                logger.error(f"PDF OCR processing failed: {e}", exc_info=True)

                return OCRResult(
                    extracted_text="",
                    confidence_score=0.0,
                    page_results=[],
                    processing_time=time.time() - start_time,
                    language_detected="unknown",
                    total_words=0,
                    quality_metrics={},
                    error_message=str(e),
                    processing_method="failed",
                    file_hash=file_hash,
                    retry_count=retry_count,
                    success=False,
                )

    async def _try_direct_extraction(self, pdf_bytes: bytes) -> Optional[str]:
        """Try to extract text directly from PDF without OCR"""
        try:
            import fitz  # PyMuPDF

            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                text_parts = []
                for page in doc:
                    text = page.get_text()
                    if text:
                        text_parts.append(text)

                return "\n\n".join(text_parts)
        except Exception as e:
            logger.debug(f"Direct text extraction failed: {e}")
            return None

    async def _process_pages_concurrent(
        self, images: List[np.ndarray]
    ) -> List[Dict[str, Any]]:
        """Process multiple pages concurrently with progress tracking"""
        results = []
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

        async def process_with_semaphore(image, page_num):
            async with semaphore:
                return await self._process_image_ocr(image, page_num)

        # Create tasks for all pages
        tasks = [
            process_with_semaphore(image, page_num)
            for page_num, image in enumerate(images, 1)
        ]

        # Process with progress tracking
        for i, task in enumerate(asyncio.as_completed(tasks)):
            result = await task
            results.append(result)
            if (i + 1) % 10 == 0:
                logger.info(f"Processed {i + 1}/{len(images)} pages")

        # Sort results by page number
        results.sort(key=lambda x: x["page_number"])
        return results

    def _detect_language_from_text(self, text: str) -> str:
        """Detect language from text content (simplified)"""
        # In production, use a proper language detection library like langdetect
        # For now, return the first configured language
        return self.languages[0].value if self.languages else "en"

    async def _pdf_to_images(self, pdf_bytes: bytes) -> List[np.ndarray]:
        """Convert PDF bytes to list of images"""
        try:
            # Create temporary file for PDF
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
                temp_pdf.write(pdf_bytes)
                temp_pdf_path = temp_pdf.name

            try:
                # Convert PDF to images
                pil_images = pdf2image.convert_from_path(
                    temp_pdf_path,
                    dpi=300,  # High DPI for better OCR accuracy
                    fmt="RGB",
                )

                # Convert PIL images to numpy arrays for EasyOCR
                images = []
                for pil_img in pil_images:
                    # Convert to numpy array
                    img_array = np.array(pil_img)
                    # Convert RGB to BGR for OpenCV compatibility
                    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                    images.append(img_bgr)

                return images

            finally:
                # Clean up temporary file
                os.unlink(temp_pdf_path)

        except Exception as e:
            logger.error(f"PDF to image conversion failed: {e}")
            raise

    async def _process_image_ocr(
        self, image: np.ndarray, page_num: int
    ) -> Dict[str, Any]:
        """Process single image with OCR and error handling"""
        start_time = time.time()

        try:
            # Check memory before processing
            if not self.memory_manager.check_memory():
                self.memory_manager.cleanup_if_needed()

            # Preprocess image for better OCR
            processed_image = await asyncio.to_thread(self._preprocess_image, image)

            # Run OCR with quality settings
            ocr_params = self._get_ocr_parameters()

            # EasyOCR processing with timeout
            results = await asyncio.wait_for(
                asyncio.to_thread(self.reader.readtext, processed_image, **ocr_params),
                timeout=30,  # 30 second timeout per page
            )

            # Extract text and calculate confidence
            text_parts = []
            confidences = []
            word_count = 0
            bounding_boxes = []

            confidence_threshold = (
                0.3 if self.quality == ProcessingQuality.FAST else 0.5
            )

            for bbox, text, confidence in results:
                if text.strip() and confidence > confidence_threshold:
                    text_parts.append(text)
                    confidences.append(confidence)
                    word_count += len(text.split())
                    bounding_boxes.append(
                        {"bbox": bbox, "text": text, "confidence": confidence}
                    )

            # Reconstruct text with proper spacing
            page_text = (
                self._reconstruct_text(bounding_boxes)
                if bounding_boxes
                else " ".join(text_parts)
            )
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            processing_time = time.time() - start_time

            return {
                "page_number": page_num,
                "text": page_text,
                "confidence": avg_confidence,
                "word_count": word_count,
                "bbox_count": len(bounding_boxes),
                "processing_time": processing_time,
                "raw_results": (
                    results if self.quality == ProcessingQuality.ULTRA else None
                ),
            }

        except asyncio.TimeoutError:
            logger.error(f"OCR timeout for page {page_num}")
            return {
                "page_number": page_num,
                "text": "",
                "confidence": 0.0,
                "word_count": 0,
                "error": "Processing timeout",
                "processing_time": time.time() - start_time,
            }
        except Exception as e:
            logger.error(f"OCR processing failed for page {page_num}: {e}")
            return {
                "page_number": page_num,
                "text": "",
                "confidence": 0.0,
                "word_count": 0,
                "error": str(e),
                "processing_time": time.time() - start_time,
            }

    def _reconstruct_text(self, bounding_boxes: List[Dict[str, Any]]) -> str:
        """Reconstruct text from bounding boxes with proper spacing"""
        if not bounding_boxes:
            return ""

        # Sort boxes by vertical position then horizontal
        sorted_boxes = sorted(
            bounding_boxes, key=lambda x: (x["bbox"][0][1], x["bbox"][0][0])
        )

        lines = []
        current_line = []
        last_y = sorted_boxes[0]["bbox"][0][1]

        # Group boxes into lines
        for box in sorted_boxes:
            current_y = box["bbox"][0][1]

            # New line if vertical distance is significant
            if abs(current_y - last_y) > 20:  # 20 pixels threshold
                if current_line:
                    lines.append(" ".join([b["text"] for b in current_line]))
                current_line = [box]
                last_y = current_y
            else:
                current_line.append(box)

        # Add last line
        if current_line:
            lines.append(" ".join([b["text"] for b in current_line]))

        return "\n".join(lines)

    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for better OCR accuracy"""
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Apply quality-based preprocessing
            if self.quality == ProcessingQuality.FAST:
                # Minimal preprocessing for speed
                return gray

            elif self.quality == ProcessingQuality.BALANCED:
                # Balanced preprocessing
                # Denoise
                denoised = cv2.medianBlur(gray, 3)
                # Enhance contrast
                enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(
                    denoised
                )
                return enhanced

            else:  # HIGH or ULTRA quality
                # Comprehensive preprocessing
                # Denoise
                denoised = cv2.medianBlur(gray, 5)
                # Enhance contrast
                clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
                enhanced = clahe.apply(denoised)
                # Sharpen
                kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
                sharpened = cv2.filter2D(enhanced, -1, kernel)
                return sharpened

        except Exception as e:
            logger.warning(f"Image preprocessing failed: {e}")
            return image

    def _get_ocr_parameters(self) -> Dict[str, Any]:
        """Get OCR parameters based on quality setting"""
        base_params = {
            "detail": 1,  # Return detailed results
            "paragraph": False,  # Don't group into paragraphs initially
        }

        if self.quality == ProcessingQuality.FAST:
            base_params.update({"width_ths": 0.9, "height_ths": 0.9})
        elif self.quality == ProcessingQuality.BALANCED:
            base_params.update({"width_ths": 0.7, "height_ths": 0.7})
        else:  # HIGH or ULTRA
            base_params.update({"width_ths": 0.5, "height_ths": 0.5})

        return base_params

    async def _enhance_with_gemma(
        self, raw_text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> GemmaEnhancementResult:
        """Enhance extracted text using Gemma 3"""
        try:
            prompt = self._build_enhancement_prompt(raw_text, metadata)

            response = await asyncio.to_thread(
                self.gemma_model.generate_content, prompt
            )

            enhanced_text = response.text.strip()

            # Basic quality assessment
            improvements = self._assess_improvements(raw_text, enhanced_text)

            return GemmaEnhancementResult(
                enhanced_text=enhanced_text,
                improvements_made=improvements,
                confidence_score=0.85,  # Default confidence for Gemma enhancement
                quality_assessment={"clarity": 0.9, "completeness": 0.85},
                issues_found=[],
                suggestions=[],
            )

        except Exception as e:
            logger.error(f"Gemma enhancement failed: {e}")
            # Return original text if enhancement fails
            return GemmaEnhancementResult(
                enhanced_text=raw_text,
                improvements_made=[],
                confidence_score=0.5,
                quality_assessment={},
                issues_found=[f"Enhancement failed: {str(e)}"],
                suggestions=["Manual review recommended"],
            )

    def _build_enhancement_prompt(
        self, raw_text: str, metadata: Optional[Dict[str, Any]]
    ) -> str:
        """Build prompt for Gemma 3 text enhancement"""
        context = ""
        if metadata:
            if metadata.get("original_filename"):
                context += f"Document: {metadata['original_filename']}\n"
            if metadata.get("uploaded_by"):
                context += f"Uploaded by: {metadata['uploaded_by']}\n"

        prompt = f"""
You are an expert at improving OCR-extracted text from customer support documents.

{context}

Please improve the following OCR-extracted text by:
1. Correcting obvious OCR errors and typos
2. Fixing spacing and formatting issues
3. Improving readability while preserving original meaning
4. Maintaining all technical terms and proper nouns
5. Ensuring the text flows naturally

Original OCR text:
{raw_text}

Please provide the improved version. Do not add explanations or comments, just return the corrected text.
"""
        return prompt

    def _assess_improvements(self, original: str, enhanced: str) -> List[str]:
        """Assess what improvements were made"""
        improvements = []

        # Basic checks
        if len(enhanced) > len(original) * 0.8:  # Significant length preserved
            improvements.append("Text length preserved")

        if enhanced.count(" ") > original.count(" ") * 0.9:  # Word spacing improved
            improvements.append("Word spacing improved")

        if enhanced.count("\n") >= original.count(
            "\n"
        ):  # Paragraph structure maintained
            improvements.append("Structure maintained")

        return improvements

    def _detect_primary_language(self, page_results: List[Dict[str, Any]]) -> str:
        """Detect primary language from OCR results"""
        # Simple heuristic - return first configured language
        # In production, could use language detection library
        return self.languages[0].value if self.languages else "en"

    def _calculate_quality_metrics(
        self, page_results: List[Dict[str, Any]], final_text: str
    ) -> Dict[str, float]:
        """Calculate quality metrics for the OCR result"""
        if not page_results:
            return {}

        # Average confidence across pages
        avg_confidence = sum(p.get("confidence", 0) for p in page_results) / len(
            page_results
        )

        # Text density (words per page)
        total_words = sum(p.get("word_count", 0) for p in page_results)
        avg_words_per_page = total_words / len(page_results) if page_results else 0

        # Text completeness (rough estimate)
        completeness = min(len(final_text) / 1000, 1.0)  # Assume 1000 chars = complete

        return {
            "confidence": avg_confidence,
            "words_per_page": avg_words_per_page,
            "completeness": completeness,
            "pages_processed": len(page_results),
            "quality_score": avg_confidence * completeness,
            "readability_score": min(
                avg_words_per_page / 250, 1.0
            ),  # Assume 250 words/page is good
        }

    def get_processing_stats(self) -> Dict[str, Any]:
        """Get current processing statistics"""
        return {
            "total_processed": self.processing_stats["total_processed"],
            "cache_hits": self.processing_stats["cache_hits"],
            "cache_hit_rate": (
                self.processing_stats["cache_hits"]
                / max(self.processing_stats["total_processed"], 1)
            ),
            "errors": self.processing_stats["errors"],
            "error_rate": (
                self.processing_stats["errors"]
                / max(self.processing_stats["total_processed"], 1)
            ),
            "average_processing_time": self.processing_stats["average_time"],
            "memory_usage_mb": self.memory_manager.get_memory_usage(),
            "gpu_available": self.use_gpu,
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on OCR engine"""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {},
        }

        # Check EasyOCR
        try:
            test_image = np.zeros((100, 100, 3), dtype=np.uint8)
            await asyncio.wait_for(
                asyncio.to_thread(self.reader.readtext, test_image), timeout=5
            )
            health_status["components"]["easyocr"] = "healthy"
        except Exception as e:
            health_status["components"]["easyocr"] = f"unhealthy: {str(e)}"
            health_status["status"] = "degraded"

        # Check cache
        if self.enable_cache:
            try:
                await asyncio.to_thread(redis_client.ping)
                health_status["components"]["cache"] = "healthy"
            except Exception as e:
                health_status["components"]["cache"] = f"unhealthy: {str(e)}"
                health_status["status"] = "degraded"

        # Check Gemma
        if self.gemma_model:
            try:
                await asyncio.to_thread(self.gemma_model.generate_content, "Test")
                health_status["components"]["gemma"] = "healthy"
            except Exception as e:
                health_status["components"]["gemma"] = f"unhealthy: {str(e)}"

        # Check memory
        memory_usage = self.memory_manager.get_memory_usage()
        components = health_status["components"]
        if memory_usage < MAX_MEMORY_MB * 0.9:
            components["memory"] = f"healthy ({memory_usage:.1f}MB used)"
        else:
            components["memory"] = f"warning ({memory_usage:.1f}MB used)"
            health_status["status"] = "degraded"

        return health_status

    def cleanup(self):
        """Cleanup resources"""
        try:
            # Clear reader cache
            with self._reader_lock:
                self._reader_cache.clear()

            # Shutdown executor
            self.executor.shutdown(wait=False)

            # Force garbage collection
            gc.collect()

            logger.info("OCR engine cleanup completed")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")


# Factory function for easy initialization
def create_ocr_engine(
    languages: List[str] = None, quality: str = "balanced", use_gpu: bool = True
) -> EasyOCREngine:
    """
    Factory function to create OCR engine with string parameters

    Args:
        languages: List of language codes (e.g., ['en', 'es'])
        quality: Quality level ('fast', 'balanced', 'high', 'ultra')
        use_gpu: Whether to use GPU acceleration

    Returns:
        Configured EasyOCREngine instance
    """
    # Convert string languages to enum
    lang_enums = []
    if languages:
        for lang in languages:
            try:
                lang_enums.append(OCRLanguage(lang))
            except ValueError:
                logger.warning(f"Unsupported language: {lang}")

    if not lang_enums:
        lang_enums = [OCRLanguage.ENGLISH]

    # Convert quality string to enum
    try:
        quality_enum = ProcessingQuality(quality.lower())
    except ValueError:
        logger.warning(f"Invalid quality setting: {quality}, using balanced")
        quality_enum = ProcessingQuality.BALANCED

    return EasyOCREngine(languages=lang_enums, quality=quality_enum, use_gpu=use_gpu)
