"""Multimodal attachment processing for Agent Sparrow.

Handles images and PDFs as proper multimodal content blocks for Gemini vision API,
while preserving text attachment behavior.
"""

from __future__ import annotations

import base64
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from app.agents.orchestration.orchestration.state import Attachment


# MIME type categories
IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
PDF_MIME_TYPES = {"application/pdf"}
TEXT_MIME_TYPES = {
    "text/plain",
    "text/csv",
    "text/html",
    "text/markdown",
    "text/xml",
    "application/json",
    "application/xml",
    "application/javascript",
}

# File extensions that indicate text content even with application/octet-stream
TEXT_EXTENSIONS = (".log", ".txt", ".csv", ".json", ".xml", ".md", ".yaml", ".yml")

# Size limits
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_PDF_SIZE = 10 * 1024 * 1024  # 10MB
MAX_ATTACHMENTS = 10  # Increased for tickets with multiple attachments
MAX_BASE64_CHARS = 5_000_000  # ~3.75MB raw data when base64 encoded
MAX_TEXT_CHARS = 3_500_000  # ~3.5MB for log files - Gemini, Grok support large context

# Base64 pattern for validation
BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


@dataclass
class ProcessedAttachments:
    """Result of processing attachments for multimodal content."""

    text_content: Optional[str] = None
    """Inlined text from text file attachments."""

    multimodal_blocks: List[Dict[str, Any]] = field(default_factory=list)
    """LangChain-compatible image_url content blocks for images/PDFs."""

    skipped: List[Dict[str, Any]] = field(default_factory=list)
    """Attachments that couldn't be processed with reasons."""

    @property
    def has_multimodal(self) -> bool:
        """Check if any multimodal content blocks were created."""
        return len(self.multimodal_blocks) > 0

    @property
    def has_any_content(self) -> bool:
        """Check if any content was processed."""
        return self.has_multimodal or bool(self.text_content)


class MultimodalProcessor:
    """Processes attachments into LangChain multimodal content format.

    Categorizes attachments by MIME type and builds appropriate content:
    - Images (PNG, JPEG, GIF, WebP) -> image_url content blocks
    - PDFs -> image_url content blocks (Gemini supports native PDF)
    - Text files -> inline text string

    Usage:
        processor = MultimodalProcessor()
        result = processor.process_attachments(state.attachments)

        if result.has_multimodal:
            # Build multimodal HumanMessage with result.multimodal_blocks
        elif result.text_content:
            # Use existing text-only SystemMessage approach
    """

    def __init__(
        self,
        max_attachments: int = MAX_ATTACHMENTS,
        max_image_size: int = MAX_IMAGE_SIZE,
        max_pdf_size: int = MAX_PDF_SIZE,
        max_base64_chars: int = MAX_BASE64_CHARS,
        max_text_chars: int = MAX_TEXT_CHARS,
    ):
        self.max_attachments = max_attachments
        self.max_image_size = max_image_size
        self.max_pdf_size = max_pdf_size
        self.max_base64_chars = max_base64_chars
        self.max_text_chars = max_text_chars

    def process_attachments(
        self,
        attachments: List["Attachment"],
    ) -> ProcessedAttachments:
        """Process attachments into multimodal content.

        Args:
            attachments: List of attachments to process.

        Returns:
            ProcessedAttachments with categorized content.
        """
        result = ProcessedAttachments()

        if not attachments:
            return result

        # Limit attachments
        in_scope = list(attachments)
        if len(in_scope) > self.max_attachments:
            logger.warning(
                "multimodal_attachment_limit",
                count=len(in_scope),
                limit=self.max_attachments,
            )
            in_scope = in_scope[: self.max_attachments]

        logger.info(
            "multimodal_processing_start",
            count=len(in_scope),
            names=[self._get_attr(att, "name") for att in in_scope],
        )

        text_parts: List[str] = []

        for att in in_scope:
            mime = self._get_mime(att)
            name = self._get_attr(att, "name") or "attachment"
            data_url = self._get_attr(att, "data_url")
            size = self._get_attr(att, "size") or 0

            if not data_url:
                result.skipped.append({"name": name, "reason": "missing_data_url"})
                continue

            # Categorize by MIME type
            if self._is_image_mime(mime):
                block = self._process_image(name, mime, data_url, size)
                if block:
                    result.multimodal_blocks.append(block)
                else:
                    result.skipped.append({"name": name, "reason": "image_processing_failed"})

            elif self._is_pdf_mime(mime):
                block = self._process_pdf(name, data_url, size)
                if block:
                    result.multimodal_blocks.append(block)
                else:
                    result.skipped.append({"name": name, "reason": "pdf_processing_failed"})

            elif self._is_text_mime(mime, name):
                text = self._process_text(name, data_url)
                if text:
                    text_parts.append(f"Attachment: {name}\n{text}")
                else:
                    result.skipped.append({"name": name, "reason": "text_decode_failed"})

            else:
                result.skipped.append({
                    "name": name,
                    "reason": "unsupported_mime_type",
                    "mime": mime,
                })

        # Combine text parts
        if text_parts:
            result.text_content = "\n\n".join(text_parts)

        logger.info(
            "multimodal_processing_complete",
            multimodal_count=len(result.multimodal_blocks),
            text_parts=len(text_parts),
            skipped_count=len(result.skipped),
        )

        return result

    def _process_image(
        self,
        name: str,
        mime: str,
        data_url: str,
        size: int,
    ) -> Optional[Dict[str, Any]]:
        """Process an image attachment into an image_url content block.

        Args:
            name: Attachment filename.
            mime: MIME type.
            data_url: Data URL with base64 content.
            size: File size in bytes.

        Returns:
            LangChain image_url content block, or None if processing failed.
        """
        # Size check
        if size > self.max_image_size:
            logger.warning(
                "image_too_large",
                name=name,
                size=size,
                limit=self.max_image_size,
            )
            return None

        # Extract base64 data
        base64_data = self._extract_base64(data_url)
        if not base64_data:
            logger.warning("image_base64_extraction_failed", name=name)
            return None

        # Validate base64 length
        if len(base64_data) > self.max_base64_chars:
            logger.warning(
                "image_base64_too_large",
                name=name,
                length=len(base64_data),
            )
            return None

        logger.info("image_processed", name=name, mime=mime)

        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{base64_data}"},
        }

    def _process_pdf(
        self,
        name: str,
        data_url: str,
        size: int,
    ) -> Optional[Dict[str, Any]]:
        """Process a PDF attachment into an image_url content block.

        Gemini 2.5 Flash supports native PDF input via image_url format.

        Args:
            name: Attachment filename.
            data_url: Data URL with base64 content.
            size: File size in bytes.

        Returns:
            LangChain image_url content block, or None if processing failed.
        """
        # Size check
        if size > self.max_pdf_size:
            logger.warning(
                "pdf_too_large",
                name=name,
                size=size,
                limit=self.max_pdf_size,
            )
            return None

        # Extract base64 data
        base64_data = self._extract_base64(data_url)
        if not base64_data:
            logger.warning("pdf_base64_extraction_failed", name=name)
            return None

        # Validate base64 length
        if len(base64_data) > self.max_base64_chars:
            logger.warning(
                "pdf_base64_too_large",
                name=name,
                length=len(base64_data),
            )
            return None

        logger.info("pdf_processed", name=name)

        return {
            "type": "image_url",
            "image_url": {"url": f"data:application/pdf;base64,{base64_data}"},
        }

    def _process_text(
        self,
        name: str,
        data_url: str,
    ) -> Optional[str]:
        """Process a text attachment into decoded text.

        Args:
            name: Attachment filename.
            data_url: Data URL with content.

        Returns:
            Decoded text content, or None if decoding failed.
        """
        # Parse data URL
        header: Optional[str] = None
        encoded: str = data_url
        is_base64 = False

        if data_url.startswith("data:"):
            try:
                header, encoded = data_url.split(",", 1)
                is_base64 = ";base64" in header.lower()
            except ValueError:
                return None

        # Normalize
        encoded_clean = urllib.parse.unquote(encoded or "")
        encoded_clean = re.sub(r"[\r\n\t ]+", "", encoded_clean)

        if len(encoded_clean) > self.max_base64_chars:
            logger.warning("text_base64_too_large", name=name)
            return None

        # Heuristic base64 detection
        if not is_base64:
            is_base64 = (
                bool(BASE64_PATTERN.fullmatch(encoded_clean))
                and len(encoded_clean) % 4 in (0, 2, 3)
            )

        try:
            if is_base64:
                padding_needed = (-len(encoded_clean)) % 4
                padded = encoded_clean + ("=" * padding_needed)
                raw = base64.b64decode(padded, validate=True)
                text = raw.decode("utf-8", errors="replace")
            else:
                text = encoded_clean
        except Exception as exc:
            logger.warning("text_decode_failed", name=name, error=str(exc))
            text = encoded_clean

        text = text.strip()
        if len(text) > self.max_text_chars:
            text = text[: self.max_text_chars - 3] + "..."

        return text if text else None

    def _extract_base64(self, data_url: str) -> Optional[str]:
        """Extract base64 data from a data URL.

        Args:
            data_url: Full data URL (data:mime;base64,...) or raw base64.

        Returns:
            Base64 string, or None if extraction failed.
        """
        if not data_url:
            return None

        if data_url.startswith("data:"):
            try:
                _, encoded = data_url.split(",", 1)
                return encoded.strip()
            except ValueError:
                return None

        # Assume raw base64
        return data_url.strip()

    def _is_image_mime(self, mime: Optional[str]) -> bool:
        """Check if MIME type is an image."""
        if not mime:
            return False
        return mime.lower() in IMAGE_MIME_TYPES

    def _is_pdf_mime(self, mime: Optional[str]) -> bool:
        """Check if MIME type is PDF."""
        if not mime:
            return False
        return mime.lower() in PDF_MIME_TYPES

    def _is_text_mime(self, mime: Optional[str], filename: Optional[str] = None) -> bool:
        """Check if MIME type indicates text content."""
        if mime:
            mime_lower = mime.lower()
            if mime_lower.startswith("text/"):
                return True
            if mime_lower in TEXT_MIME_TYPES:
                return True

            # Special case: octet-stream with text extension
            if mime_lower == "application/octet-stream" and filename:
                name_lower = filename.lower()
                if any(name_lower.endswith(ext) for ext in TEXT_EXTENSIONS):
                    return True

        return False

    def _get_mime(self, attachment: Any) -> str:
        """Get MIME type from attachment."""
        mime = self._get_attr(attachment, "mime_type")
        return str(mime).lower() if mime else ""

    def _get_attr(self, obj: Any, attr: str) -> Optional[Any]:
        """Get attribute from object or dict."""
        if isinstance(obj, dict):
            return obj.get(attr)
        return getattr(obj, attr, None)


# Module-level singleton
_default_processor: Optional[MultimodalProcessor] = None


def get_multimodal_processor() -> MultimodalProcessor:
    """Get the default multimodal processor instance."""
    global _default_processor
    if _default_processor is None:
        _default_processor = MultimodalProcessor()
    return _default_processor
