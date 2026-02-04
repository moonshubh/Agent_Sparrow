"""
OCR Fallback Processor for FeedMe System

This module provides OCR capabilities for handling image-heavy or low-quality PDFs
where standard text extraction fails or produces poor results.
"""

import logging
import asyncio
import io
import time
import re
from typing import List, Optional, Dict, Any, Tuple, Set
from dataclasses import dataclass

from .word_corpus import WordCorpusLoader
from .ocr_config import OCRConfigManager

logger = logging.getLogger(__name__)

# OCR dependencies - with graceful fallback if not available
try:
    import pytesseract  # type: ignore[import-untyped]
    from PIL import Image

    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning(
        "OCR dependencies not available (pytesseract, PIL). OCR fallback disabled "
        "(Gemini PDF extraction does not use OCR)."
    )

try:
    import fitz  # type: ignore[import-not-found]

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning(
        "PyMuPDF not available. OCR fallback disabled (Gemini PDF extraction does not use OCR)."
    )

OCR_ENABLED = TESSERACT_AVAILABLE and PYMUPDF_AVAILABLE


@dataclass
class OCRResult:
    """Result of OCR processing"""

    text: str
    confidence: float
    page_number: int
    method: str  # 'tesseract', 'fallback', etc.
    processing_time_ms: float


class OCRFallbackProcessor:
    """OCR fallback for poor-quality PDF text extraction"""

    def __init__(self, confidence_threshold: float = 0.7):
        self.confidence_threshold = confidence_threshold
        self.tesseract_config = "--oem 3 --psm 6"  # Optimized for text blocks
        self.enabled = OCR_ENABLED

        # Initialize configuration and word corpus managers
        self.config_manager = OCRConfigManager()
        self.word_loader = WordCorpusLoader()
        self._word_corpus: Optional[Set[str]] = None

        if not self.enabled:
            logger.warning(
                "OCR fallback processor disabled due to missing dependencies"
            )

    async def process_pdf_with_ocr(self, pdf_bytes: bytes) -> List[OCRResult]:
        """Process PDF with OCR fallback"""
        if not self.enabled:
            logger.warning("OCR processing requested but dependencies not available")
            return []

        try:
            # Use asyncio to run OCR in thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._ocr_pdf_sync, pdf_bytes)
        except Exception as e:
            logger.error(f"OCR processing failed: {e}")
            return []

    def _ocr_pdf_sync(self, pdf_bytes: bytes) -> List[OCRResult]:
        """Synchronous OCR processing"""
        results = []

        # Open PDF with PyMuPDF for image extraction
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        try:
            for page_num in range(len(doc)):
                page = doc[page_num]

                # Extract images from page
                image_list = page.get_images()

                if image_list:
                    # Process images with OCR
                    for img_index, img in enumerate(image_list):
                        ocr_result = self._ocr_image_from_page(page, img, page_num + 1)
                        if ocr_result:
                            results.append(ocr_result)
                else:
                    # No images, try rendering page as image
                    ocr_result = self._ocr_rendered_page(page, page_num + 1)
                    if ocr_result:
                        results.append(ocr_result)
        finally:
            doc.close()

        return results

    def _ocr_image_from_page(self, page, img_ref, page_num: int) -> Optional[OCRResult]:
        """Extract text from image using OCR"""
        start_time = time.perf_counter()

        try:
            # Get image data
            xref = img_ref[0]
            base_image = page.parent.extract_image(xref)
            image_bytes = base_image["image"]

            # Convert to PIL Image
            image = Image.open(io.BytesIO(image_bytes))

            # Perform OCR
            text = pytesseract.image_to_string(image, config=self.tesseract_config)

            # Get confidence score
            confidence_data = pytesseract.image_to_data(
                image, output_type=pytesseract.Output.DICT
            )
            confidences = [
                int(conf) for conf in confidence_data["conf"] if int(conf) > 0
            ]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            if avg_confidence >= self.confidence_threshold * 100:
                return OCRResult(
                    text=text.strip(),
                    confidence=avg_confidence / 100,
                    page_number=page_num,
                    method="tesseract",
                    processing_time_ms=processing_time_ms,
                )
        except Exception as e:
            logger.debug(f"OCR failed for image on page {page_num}: {e}")

        return None

    def _ocr_rendered_page(self, page, page_num: int) -> Optional[OCRResult]:
        """OCR entire page by rendering it as image"""
        start_time = time.perf_counter()

        try:
            # Render page as image
            pixmap = page.get_pixmap(dpi=300)  # High DPI for better OCR
            img_data = pixmap.tobytes("png")

            # Convert to PIL Image
            image = Image.open(io.BytesIO(img_data))

            # Perform OCR
            text = pytesseract.image_to_string(image, config=self.tesseract_config)

            # Simple confidence estimation based on text characteristics
            confidence = self._estimate_text_confidence(text)

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            if confidence >= self.confidence_threshold:
                return OCRResult(
                    text=text.strip(),
                    confidence=confidence,
                    page_number=page_num,
                    method="tesseract_render",
                    processing_time_ms=processing_time_ms,
                )
        except Exception as e:
            logger.debug(f"OCR failed for rendered page {page_num}: {e}")

        return None

    def _count_valid_dictionary_words(self, text: str) -> Tuple[int, int]:
        """Count valid dictionary words in text using configurable word corpus"""
        # Load word corpus if not cached
        if self._word_corpus is None:
            config = self.config_manager.get_config()
            self._word_corpus = self.word_loader.get_word_corpus(
                use_nltk=config.use_nltk_corpus, min_word_length=config.min_word_length
            )

        # Split text into words and clean them
        words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
        if not words:
            return 0, 0

        # Count valid dictionary words using the corpus
        valid_words = sum(
            1
            for word in words
            if self.word_loader.is_valid_word(word, self._word_corpus)
        )

        return valid_words, len(words)

    def _estimate_text_confidence(self, text: str) -> float:
        """Estimate confidence based on text characteristics and dictionary word matching"""
        if not text.strip():
            return 0.0

        # Get configuration for thresholds and weights
        config = self.config_manager.get_config()
        weights = config.confidence_weights

        # Simple heuristics for text quality
        word_count = len(text.split())
        char_count = len(text)

        # Penalize very short or very long strings using configurable thresholds
        if word_count < config.min_word_count or char_count < config.min_char_count:
            return config.low_text_confidence

        # Check for reasonable character distribution
        alpha_ratio = sum(c.isalpha() for c in text) / len(text)
        digit_ratio = sum(c.isdigit() for c in text) / len(text)
        space_ratio = sum(c.isspace() for c in text) / len(text)

        # Count valid dictionary words
        valid_words, total_words = self._count_valid_dictionary_words(text)
        valid_word_ratio = valid_words / total_words if total_words > 0 else 0.0

        # Calculate weighted confidence score using configurable weights
        confidence = (
            weights.valid_word_ratio * valid_word_ratio
            + weights.alpha_ratio * min(alpha_ratio * weights.alpha_ratio_scale, 1.0)
            + weights.space_ratio * min(space_ratio * weights.space_ratio_scale, 1.0)
        )

        # Apply additional penalties for suspicious patterns using configurable thresholds
        if digit_ratio > weights.high_digit_threshold:
            confidence *= weights.high_digit_penalty

        # Ensure confidence is clamped between 0.0 and 1.0
        return max(0.0, min(1.0, confidence))

    def should_use_ocr(self, text_extraction_result: str, page_content: str) -> bool:
        """Determine if OCR should be used based on text extraction quality"""
        if not self.enabled:
            return False

        # Get configuration for thresholds
        config = self.config_manager.get_config()

        # Check if text extraction produced very little text
        if len(text_extraction_result.strip()) < config.poor_extraction_threshold:
            return True

        # Check for signs of poor extraction (too many special characters)
        special_char_ratio = sum(
            1 for c in text_extraction_result if not c.isalnum() and not c.isspace()
        ) / len(text_extraction_result)
        if special_char_ratio > config.special_char_ratio_threshold:
            return True

        # Check for garbled text patterns
        garbled_patterns = [
            r"[^\x00-\x7F]{5,}",  # Long sequences of non-ASCII
            r"[A-Z]{20,}",  # Very long uppercase sequences
            r"[a-z]{30,}",  # Very long lowercase sequences
            r"[0-9]{15,}",  # Very long number sequences
        ]

        for pattern in garbled_patterns:
            if re.search(pattern, text_extraction_result):
                return True

        return False

    async def enhance_text_with_ocr(self, original_text: str, pdf_bytes: bytes) -> str:
        """Enhance poor-quality text extraction with OCR"""
        if not self.enabled:
            return original_text

        try:
            ocr_results = await self.process_pdf_with_ocr(pdf_bytes)

            if not ocr_results:
                return original_text

            # Combine OCR results by page
            ocr_text_by_page: dict[int, list[str]] = {}
            for result in ocr_results:
                page_num = result.page_number
                if page_num not in ocr_text_by_page:
                    ocr_text_by_page[page_num] = []
                ocr_text_by_page[page_num].append(result.text)

            # Merge OCR text with original text
            enhanced_text = original_text
            for page_num in sorted(ocr_text_by_page.keys()):
                ocr_page_text = "\n".join(ocr_text_by_page[page_num])
                if ocr_page_text.strip():
                    enhanced_text += f"\n\n[OCR Page {page_num}]\n{ocr_page_text}"

            logger.info(
                f"Enhanced text with OCR: {len(original_text)} → {len(enhanced_text)} characters"
            )
            return enhanced_text

        except Exception as e:
            logger.error(f"OCR enhancement failed: {e}")
            return original_text

    def get_ocr_status(self) -> Dict[str, Any]:
        """Get OCR system status"""
        return {
            "enabled": self.enabled,
            "tesseract_available": TESSERACT_AVAILABLE,
            "pymupdf_available": PYMUPDF_AVAILABLE,
            "confidence_threshold": self.confidence_threshold,
        }


# Convenience functions for direct usage
async def ocr_pdf_if_needed(
    pdf_bytes: bytes, extracted_text: str, threshold: float = 0.7
) -> str:
    """OCR PDF if extracted text quality is poor"""
    processor = OCRFallbackProcessor(confidence_threshold=threshold)

    if processor.should_use_ocr(extracted_text, ""):
        return await processor.enhance_text_with_ocr(extracted_text, pdf_bytes)

    return extracted_text


def is_ocr_available() -> bool:
    """Check if OCR functionality is available"""
    return OCR_ENABLED
