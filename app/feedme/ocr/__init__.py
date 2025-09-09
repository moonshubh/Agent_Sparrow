"""
FeedMe OCR Module
Advanced OCR processing for PDF documents with EasyOCR and Gemma 3 enhancement
"""

from .easyocr_engine import (
    EasyOCREngine,
    OCRResult,
    GemmaEnhancementResult,
    OCRLanguage,
    ProcessingQuality,
    create_ocr_engine,
    EASYOCR_AVAILABLE
)

__all__ = [
    'EasyOCREngine',
    'OCRResult', 
    'GemmaEnhancementResult',
    'OCRLanguage',
    'ProcessingQuality',
    'create_ocr_engine',
    'EASYOCR_AVAILABLE'
]