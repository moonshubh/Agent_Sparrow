"""
Attachment Sanitizer for OCR and Screenshot Processing

This module provides secure handling and sanitization of attachments including
images, screenshots, and OCR text output. Ensures no raw attachment data or
PII from attachments persists in the system.

Security Design:
- Sanitizes OCR text for PII before processing
- Redacts sensitive information from attachment summaries
- Secure temporary file handling with guaranteed cleanup
- Validates image formats and prevents malicious files
- Memory-efficient processing for large attachments
"""

import base64
import hashlib
import io
import logging
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from PIL import Image
import magic
from dataclasses import dataclass
from contextlib import contextmanager

from .sanitizer import LogSanitizer, SanitizationConfig, RedactionLevel
from .cleanup import LogCleanupManager

logger = logging.getLogger(__name__)


@dataclass
class AttachmentConfig:
    """Configuration for attachment processing."""
    max_file_size: int = 50 * 1024 * 1024  # 50MB max
    max_image_dimension: int = 10000  # Max width/height
    allowed_mime_types: List[str] = None
    enable_ocr: bool = True
    sanitize_ocr_text: bool = True
    store_thumbnails_only: bool = True
    thumbnail_max_size: Tuple[int, int] = (800, 800)
    validate_magic_bytes: bool = True  # Check file magic bytes
    strip_exif_data: bool = True  # Remove EXIF metadata


class AttachmentSanitizer:
    """
    Secure attachment sanitizer for processing images and documents.

    Handles various attachment types with focus on privacy and security,
    ensuring no sensitive data from attachments persists in the system.
    """

    SAFE_IMAGE_FORMATS = {'PNG', 'JPEG', 'JPG', 'GIF', 'BMP', 'WEBP'}
    SAFE_DOCUMENT_FORMATS = {'PDF', 'TXT', 'LOG'}

    # Magic byte signatures for file validation
    MAGIC_BYTES = {
        b'\xFF\xD8\xFF': 'jpeg',
        b'\x89\x50\x4E\x47': 'png',
        b'\x47\x49\x46\x38': 'gif',
        b'\x42\x4D': 'bmp',
        b'\x25\x50\x44\x46': 'pdf',
        b'\x52\x49\x46\x46': 'webp',  # RIFF header for WebP
    }

    def __init__(
        self,
        config: Optional[AttachmentConfig] = None,
        sanitizer: Optional[LogSanitizer] = None,
        cleanup_manager: Optional[LogCleanupManager] = None
    ):
        """
        Initialize attachment sanitizer.

        Args:
            config: Optional configuration
            sanitizer: Optional log sanitizer instance
            cleanup_manager: Optional cleanup manager instance
        """
        self.config = config or AttachmentConfig()

        # Set default allowed MIME types if not provided
        if self.config.allowed_mime_types is None:
            self.config.allowed_mime_types = [
                'image/png', 'image/jpeg', 'image/jpg', 'image/gif',
                'image/bmp', 'image/webp', 'application/pdf',
                'text/plain', 'text/log'
            ]

        # Initialize sanitizer with paranoid settings for attachments
        self.sanitizer = sanitizer or LogSanitizer(
            SanitizationConfig(redaction_level=RedactionLevel.PARANOID)
        )

        self.cleanup_manager = cleanup_manager or LogCleanupManager()
        self._magic = magic.Magic(mime=True) if self.config.validate_magic_bytes else None

        logger.info("AttachmentSanitizer initialized with secure defaults")

    def _validate_magic_bytes(self, data: bytes) -> Optional[str]:
        """
        Validate file magic bytes to prevent file type spoofing.

        Args:
            data: File data bytes

        Returns:
            Detected file type or None if invalid
        """
        if not self.config.validate_magic_bytes:
            return "unknown"

        # Check magic bytes
        for magic_bytes, file_type in self.MAGIC_BYTES.items():
            if data.startswith(magic_bytes):
                return file_type

        # Use python-magic for deeper inspection
        if self._magic:
            try:
                mime_type = self._magic.from_buffer(data[:8192])
                return mime_type
            except Exception as e:
                logger.warning(f"Magic byte detection failed: {e}")

        return None

    def _validate_file_safety(self, file_path: Path) -> Tuple[bool, str]:
        """
        Validate file safety before processing.

        Args:
            file_path: Path to file

        Returns:
            Tuple of (is_safe, reason)
        """
        try:
            # Check file exists
            if not file_path.exists():
                return False, "File does not exist"

            # Check file size
            file_size = file_path.stat().st_size
            if file_size > self.config.max_file_size:
                return False, f"File too large: {file_size} bytes"

            if file_size == 0:
                return False, "File is empty"

            # Read first chunk for validation
            with open(file_path, 'rb') as f:
                header = f.read(8192)

            # Validate magic bytes
            if self.config.validate_magic_bytes:
                file_type = self._validate_magic_bytes(header)
                if not file_type:
                    return False, "Invalid file type detected"

            # Check for embedded scripts or executables
            dangerous_patterns = [
                b'<script', b'javascript:', b'vbscript:',
                b'onload=', b'onerror=', b'.exe', b'.dll',
                b'cmd.exe', b'powershell', b'/bin/sh'
            ]

            for pattern in dangerous_patterns:
                if pattern in header.lower():
                    return False, f"Potentially malicious content detected"

            # Check MIME type
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type and mime_type not in self.config.allowed_mime_types:
                return False, f"Disallowed MIME type: {mime_type}"

            return True, "File validated successfully"

        except Exception as e:
            logger.error(f"File validation error: {e}")
            return False, f"Validation error: {str(e)}"

    def _strip_exif_data(self, image: Image.Image) -> Image.Image:
        """
        Strip EXIF and other metadata from image.

        Args:
            image: PIL Image object

        Returns:
            Image with metadata stripped
        """
        if not self.config.strip_exif_data:
            return image

        try:
            # Create new image without metadata
            data = list(image.getdata())
            image_without_exif = Image.new(image.mode, image.size)
            image_without_exif.putdata(data)

            # Preserve only safe attributes
            if hasattr(image, 'info'):
                safe_info = {}
                safe_keys = ['dpi', 'transparency']
                for key in safe_keys:
                    if key in image.info:
                        safe_info[key] = image.info[key]
                image_without_exif.info = safe_info

            return image_without_exif

        except Exception as e:
            logger.warning(f"Failed to strip EXIF data: {e}")
            return image

    def _create_safe_thumbnail(self, image: Image.Image) -> Image.Image:
        """
        Create a safe thumbnail of the image.

        Args:
            image: Original image

        Returns:
            Thumbnail image
        """
        try:
            # Create thumbnail
            thumbnail = image.copy()
            thumbnail.thumbnail(
                self.config.thumbnail_max_size,
                Image.Resampling.LANCZOS
            )

            # Convert to RGB if necessary (removes alpha channel)
            if thumbnail.mode not in ('RGB', 'L'):
                thumbnail = thumbnail.convert('RGB')

            return thumbnail

        except Exception as e:
            logger.error(f"Thumbnail creation failed: {e}")
            raise

    @contextmanager
    def process_image_safely(self, file_path: Path):
        """
        Context manager for safe image processing.

        Args:
            file_path: Path to image file

        Yields:
            Processed safe image or None if validation fails
        """
        image = None
        temp_file = None

        try:
            # Validate file safety
            is_safe, reason = self._validate_file_safety(file_path)
            if not is_safe:
                logger.warning(f"Image validation failed: {reason}")
                yield None
                return

            # Open and validate image
            image = Image.open(file_path)

            # Check image dimensions
            width, height = image.size
            if width > self.config.max_image_dimension or height > self.config.max_image_dimension:
                logger.warning(f"Image too large: {width}x{height}")
                yield None
                return

            # Check for decompression bombs
            pixels = width * height
            if pixels > 100_000_000:  # 100 megapixels
                logger.warning("Image might be a decompression bomb")
                yield None
                return

            # Strip EXIF data
            image = self._strip_exif_data(image)

            # Create thumbnail if configured
            if self.config.store_thumbnails_only:
                image = self._create_safe_thumbnail(image)

            # Save to temporary file
            with self.cleanup_manager.temporary_file(suffix='.png') as temp_path:
                image.save(temp_path, 'PNG', optimize=True)
                yield image

        except Exception as e:
            logger.error(f"Image processing error: {e}")
            yield None

        finally:
            # Cleanup
            if image:
                image.close()

    def sanitize_ocr_text(self, text: str) -> Tuple[str, Dict[str, int]]:
        """
        Sanitize OCR text output for PII and sensitive information.

        Args:
            text: Raw OCR text

        Returns:
            Tuple of (sanitized text, redaction statistics)
        """
        if not text:
            return "", {}

        # Apply paranoid sanitization
        sanitized_text, stats = self.sanitizer.sanitize(text)

        # Additional OCR-specific sanitization
        # Remove potential barcode/QR code data
        sanitized_text = self._redact_code_patterns(sanitized_text)

        # Remove potential document IDs
        sanitized_text = self._redact_document_ids(sanitized_text)

        return sanitized_text, stats

    def _redact_code_patterns(self, text: str) -> str:
        """Redact barcode and QR code patterns."""
        import re

        # Barcode patterns (various formats)
        barcode_patterns = [
            r'\b\d{8,13}\b',  # EAN-8, EAN-13, UPC
            r'\b[A-Z0-9]{10,}\b',  # Code 128, Code 39
            r'\|\|\|\s*\|\s*\|\|\s*\|',  # Visual barcode representation
        ]

        for pattern in barcode_patterns:
            text = re.sub(pattern, '[REDACTED_CODE]', text)

        return text

    def _redact_document_ids(self, text: str) -> str:
        """Redact document identifiers and reference numbers."""
        import re

        # Document ID patterns
        doc_patterns = [
            r'(?i)(?:doc|document|ref|reference|id|case|ticket|invoice|order)[\s#:]*[A-Z0-9-]{6,}',
            r'(?i)patient[\s#:]*[A-Z0-9-]{6,}',  # Medical records
            r'(?i)account[\s#:]*[A-Z0-9-]{6,}',  # Account numbers
        ]

        for pattern in doc_patterns:
            text = re.sub(pattern, '[REDACTED_DOCUMENT_ID]', text)

        return text

    def process_attachment(
        self,
        file_path: Path,
        attachment_type: str = "auto"
    ) -> Dict[str, Any]:
        """
        Process an attachment with full sanitization.

        Args:
            file_path: Path to attachment file
            attachment_type: Type of attachment or "auto" for detection

        Returns:
            Sanitized attachment metadata
        """
        result = {
            'status': 'failed',
            'file_hash': None,
            'sanitized_content': None,
            'metadata': {},
            'redaction_stats': {}
        }

        try:
            # Generate file hash for reference (not storing file content)
            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            result['file_hash'] = file_hash[:16]  # Truncated hash

            # Validate file
            is_safe, reason = self._validate_file_safety(file_path)
            if not is_safe:
                result['error'] = reason
                return result

            # Detect type if auto
            if attachment_type == "auto":
                mime_type, _ = mimetypes.guess_type(str(file_path))
                if mime_type and mime_type.startswith('image/'):
                    attachment_type = "image"
                elif mime_type in ['application/pdf', 'text/plain']:
                    attachment_type = "document"
                else:
                    attachment_type = "unknown"

            # Process based on type
            if attachment_type == "image":
                result.update(self._process_image_attachment(file_path))
            elif attachment_type == "document":
                result.update(self._process_document_attachment(file_path))
            else:
                result['error'] = f"Unsupported attachment type: {attachment_type}"

        except Exception as e:
            logger.error(f"Attachment processing error: {e}")
            result['error'] = "Processing failed"

        return result

    def _process_image_attachment(self, file_path: Path) -> Dict[str, Any]:
        """Process image attachment with sanitization."""
        result = {}

        with self.process_image_safely(file_path) as image:
            if image is None:
                result['error'] = "Image processing failed"
                return result

            # Generate safe metadata
            result['metadata'] = {
                'width': image.width,
                'height': image.height,
                'format': image.format or 'unknown',
                'mode': image.mode,
            }

            # If OCR is enabled, extract and sanitize text
            if self.config.enable_ocr:
                try:
                    import pytesseract
                    ocr_text = pytesseract.image_to_string(image)
                    sanitized_text, stats = self.sanitize_ocr_text(ocr_text)
                    result['sanitized_content'] = sanitized_text
                    result['redaction_stats'] = stats
                except ImportError:
                    logger.warning("pytesseract not available for OCR")
                except Exception as e:
                    logger.error(f"OCR failed: {e}")

            result['status'] = 'success'

        return result

    def _process_document_attachment(self, file_path: Path) -> Dict[str, Any]:
        """Process document attachment with sanitization."""
        result = {}

        try:
            # Read document content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(1024 * 1024)  # Read up to 1MB

            # Sanitize content
            sanitized_content, stats = self.sanitizer.sanitize(content)

            result['sanitized_content'] = sanitized_content[:10000]  # Limit size
            result['redaction_stats'] = stats
            result['status'] = 'success'

        except Exception as e:
            logger.error(f"Document processing error: {e}")
            result['error'] = "Document processing failed"

        return result

    def create_attachment_summary(
        self,
        attachments: List[Dict[str, Any]]
    ) -> str:
        """
        Create a sanitized summary of attachments.

        Args:
            attachments: List of processed attachment results

        Returns:
            Sanitized summary text
        """
        if not attachments:
            return "No attachments processed."

        summary_parts = []

        for idx, attachment in enumerate(attachments, 1):
            if attachment.get('status') == 'success':
                metadata = attachment.get('metadata', {})
                stats = attachment.get('redaction_stats', {})

                part = f"Attachment {idx}: "

                if metadata:
                    if 'width' in metadata:
                        part += f"Image ({metadata['width']}x{metadata['height']})"
                    else:
                        part += "Document"

                if stats:
                    total_redactions = sum(stats.values())
                    if total_redactions > 0:
                        part += f" - {total_redactions} items redacted"

                summary_parts.append(part)
            else:
                summary_parts.append(
                    f"Attachment {idx}: Failed - {attachment.get('error', 'Unknown error')}"
                )

        return "\n".join(summary_parts)