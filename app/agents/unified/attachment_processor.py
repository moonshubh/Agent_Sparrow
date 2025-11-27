"""Attachment processing for Agent Sparrow.

Extracted from agent_sparrow.py to provide a single source of truth
for attachment handling, decoding, and validation.
"""

from __future__ import annotations

import base64
import re
import urllib.parse
from typing import Any, Callable, Coroutine, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from app.agents.orchestration.orchestration.state import Attachment


# Constants
MAX_ATTACHMENTS = 5
MAX_BASE64_CHARS = 2_500_000  # Prevent unbounded payloads
MAX_DECODED_CHARS = 120_000  # Limit decoded text size
SUMMARIZATION_THRESHOLD = 4_000  # When to summarize attachments

# Patterns
BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")

# Supported MIME types for text extraction
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

# File extensions that indicate text content even with application/octet-stream MIME
TEXT_EXTENSIONS = (".log", ".txt", ".csv", ".json", ".xml", ".md", ".yaml", ".yml")

# Log-like patterns
LOG_LEVEL_RE = re.compile(r"\b(INFO|WARN|WARNING|ERROR|ERR|DEBUG|TRACE|FATAL|CRITICAL)\b")
ISO_TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:\d{2})?\b")
STACK_RE = re.compile(r"(Traceback \(most recent call last\):|^\s*at\s+\S+\(.*:\d+\))", re.MULTILINE)


class AttachmentProcessor:
    """Single source of truth for attachment handling.

    Handles:
    - Decoding data URLs (base64 and plain text)
    - Validating attachments (MIME type, size)
    - Inlining attachments into prompts
    - Summarizing large attachments

    Usage:
        processor = AttachmentProcessor()

        # Decode a single attachment
        text = processor.decode_data_url(data_url)

        # Process all attachments for prompt injection
        inline_text = await processor.inline_attachments(
            attachments,
            summarizer=helper.summarize,
        )
    """

    def __init__(
        self,
        max_attachments: int = MAX_ATTACHMENTS,
        max_base64_chars: int = MAX_BASE64_CHARS,
        max_decoded_chars: int = MAX_DECODED_CHARS,
        summarization_threshold: int = SUMMARIZATION_THRESHOLD,
    ):
        """Initialize the processor.

        Args:
            max_attachments: Maximum number of attachments to process.
            max_base64_chars: Maximum base64 payload size before rejection.
            max_decoded_chars: Maximum decoded text size before truncation.
            summarization_threshold: Inline text size that triggers summarization.
        """
        self.max_attachments = max_attachments
        self.max_base64_chars = max_base64_chars
        self.max_decoded_chars = max_decoded_chars
        self.summarization_threshold = summarization_threshold

    def decode_data_url(
        self,
        data_url: str,
        max_chars: Optional[int] = None,
    ) -> Optional[str]:
        """Decode a data URL (or raw base64/text) to text.

        Handles:
        - Full data URLs: data:text/plain;base64,SGVsbG8=
        - Raw base64 strings: SGVsbG8=
        - Plain text (URL-encoded or not)

        Args:
            data_url: The data URL or raw content to decode.
            max_chars: Maximum characters to return (truncates with ellipsis).

        Returns:
            Decoded text, or None if decoding failed or content too large.
        """
        max_chars = max_chars or self.max_decoded_chars
        header: Optional[str] = None
        encoded: str = data_url
        is_base64 = False

        # Accept both full data URLs and raw base64/text blobs
        if data_url.startswith("data:"):
            try:
                header, encoded = data_url.split(",", 1)
                is_base64 = ";base64" in header.lower()
            except ValueError:
                return None

        # Normalize encoding (strip whitespace/newlines and URL escapes)
        encoded_clean = urllib.parse.unquote(encoded or "")
        encoded_clean = re.sub(r"[\r\n\t ]+", "", encoded_clean)

        # Guard against unbounded payloads
        if len(encoded_clean) > self.max_base64_chars:
            logger.warning("attachment_base64_too_large", length=len(encoded_clean))
            return None

        # Heuristic: if no explicit header, guess base64 when payload looks base64-like
        if not is_base64:
            is_base64 = (
                bool(BASE64_PATTERN.fullmatch(encoded_clean))
                and len(encoded_clean) % 4 in (0, 2, 3)
            )

        text: Optional[str]
        try:
            if is_base64:
                # Add padding if needed
                padding_needed = (-len(encoded_clean)) % 4
                padded = encoded_clean + ("=" * padding_needed)
                raw = base64.b64decode(padded, validate=True)
                text = raw.decode("utf-8", errors="replace")
            else:
                text = encoded_clean
        except Exception as exc:
            # Last resort: treat as URL-decoded plain text
            logger.warning(
                "attachment_base64_decode_failed",
                error=str(exc),
                sample=encoded_clean[:64],
            )
            text = encoded_clean

        if text is None:
            return None

        text = text.strip()
        if len(text) > max_chars:
            return text[: max_chars - 1] + "..."

        return text

    def validate_attachment(
        self,
        attachment: "Attachment",
    ) -> tuple[bool, Optional[str]]:
        """Validate an attachment for processing.

        Args:
            attachment: The attachment to validate.

        Returns:
            Tuple of (is_valid, reason_if_invalid).
        """
        # Extract fields (handle both object and dict)
        mime = self._get_attr(attachment, "mime_type")
        name = self._get_attr(attachment, "name")
        data_url = self._get_attr(attachment, "data_url")

        if not data_url:
            return False, "missing_data_url"

        # Check MIME type
        if not self.is_text_mime(mime, name):
            return False, f"non_text_mime:{mime}"

        return True, None

    def is_text_mime(
        self,
        mime: Optional[str],
        filename: Optional[str] = None,
    ) -> bool:
        """Check if MIME type indicates text content.

        Some browsers upload .log files as application/octet-stream,
        so we also check the filename extension.
        """
        if mime:
            mime_lower = str(mime).lower()
            if mime_lower.startswith("text/"):
                return True
            if mime_lower in TEXT_MIME_TYPES:
                return True

            # Special case: octet-stream with text-like extension
            if mime_lower == "application/octet-stream" and filename:
                name_lower = str(filename).lower()
                if any(name_lower.endswith(ext) for ext in TEXT_EXTENSIONS):
                    logger.info(
                        "attachment_treated_as_text",
                        name=filename,
                        mime=mime,
                    )
                    return True

        return False

    async def inline_attachments(
        self,
        attachments: List["Attachment"],
        summarizer: Optional[Callable[[str, int], Coroutine[Any, Any, Optional[str]]]] = None,
        summarizer_timeout: float = 8.0,
    ) -> Optional[str]:
        """Process attachments and create inline text for prompt injection.

        Args:
            attachments: List of attachments to process.
            summarizer: Optional async function to summarize long content.
                        Signature: async def summarize(text: str, budget_tokens: int) -> Optional[str]
            summarizer_timeout: Timeout for summarizer calls.

        Returns:
            Inline text ready for prompt injection, or None if no valid attachments.
        """
        import asyncio

        if not attachments:
            return None

        # Limit attachments
        attachments_in_scope = list(attachments)
        if len(attachments_in_scope) > self.max_attachments:
            logger.warning(
                "attachment_limit_exceeded",
                count=len(attachments_in_scope),
                limit=self.max_attachments,
            )
            attachments_in_scope = attachments_in_scope[: self.max_attachments]

        logger.info(
            "attachments_received",
            count=len(attachments_in_scope),
            names=[self._get_attr(att, "name") for att in attachments_in_scope],
        )

        # Process each attachment
        attachment_blocks: List[str] = []
        for att in attachments_in_scope:
            mime = self._get_attr(att, "mime_type")
            name = self._get_attr(att, "name")
            data_url = self._get_attr(att, "data_url")

            if not data_url:
                logger.info("attachment_skipped", name=name, reason="missing_data_url")
                continue

            if not self.is_text_mime(mime, name):
                logger.info(
                    "attachment_skipped",
                    name=name,
                    reason="non_text_mime",
                    mime=mime,
                )
                continue

            text = self.decode_data_url(str(data_url))
            if not text:
                logger.info(
                    "attachment_skipped",
                    name=name,
                    reason="decode_failed",
                    mime=mime,
                )
                continue

            header = f"Attachment: {name or 'log.txt'}"
            attachment_blocks.append(f"{header}\n{text}")

        if not attachment_blocks:
            return None

        inline = "\n\n".join(attachment_blocks)

        # Summarize if too long
        if len(inline) > self.summarization_threshold and summarizer:
            try:
                summary = await asyncio.wait_for(
                    summarizer(inline, 900),  # budget_tokens
                    timeout=summarizer_timeout,
                )
                if summary:
                    inline = f"Summarized attachments:\n{summary}"
            except asyncio.TimeoutError:
                logger.warning("attachment_summarization_timeout")
            except Exception as exc:
                logger.warning("attachment_summarization_failed", error=str(exc))

        logger.info(
            "inline_attachments_injected",
            count=len(attachment_blocks),
            chars=len(inline),
        )

        return inline

    def _looks_like_log_text(self, text: str) -> tuple[bool, Dict[str, Any]]:
        """Heuristically detect log-like content in decoded text."""
        sample = text[:20000]
        signals = {
            "timestamps": len(ISO_TS_RE.findall(sample)),
            "levels": len(LOG_LEVEL_RE.findall(sample)),
            "stack": len(STACK_RE.findall(sample)),
        }
        strong_signal = signals["levels"] >= 3 or signals["timestamps"] >= 5 or signals["stack"] >= 2
        multi_signal = sum(1 for val in signals.values() if val > 0) >= 2
        return strong_signal or multi_signal, {"signals": signals}

    def detect_log_attachments(self, attachments: List["Attachment"]) -> Dict[str, Any]:
        """Detect whether provided attachments look like logs."""
        candidates: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        for att in attachments or []:
            mime = self._get_attr(att, "mime_type")
            name = (self._get_attr(att, "name") or "").lower()
            data_url = self._get_attr(att, "data_url")

            if not data_url:
                continue

            if not self.is_text_mime(mime, name):
                skipped.append({"name": name, "mime": mime, "reason": "non_text_mime"})
                continue

            looks_like_log = False
            detail: Dict[str, Any] = {"signals": {}}

            if name.endswith(".log") or (name.endswith(".txt") and "log" in name):
                looks_like_log = True
            else:
                sample = self.decode_data_url(str(data_url), max_chars=8000) or ""
                if sample:
                    looks_like_log, detail = self._looks_like_log_text(sample)

            if looks_like_log:
                candidates.append({"name": name, "mime": mime, **detail})

        return {
            "has_log": bool(candidates),
            "candidates": candidates,
            "non_text_skipped": skipped,
        }

    def extract_log_content(self, text: str) -> str:
        """Extract meaningful content from log text.

        Performs basic cleanup and filtering for log-specific content.
        """
        # Remove excessive blank lines
        lines = text.splitlines()
        cleaned_lines = []
        prev_blank = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if not prev_blank:
                    cleaned_lines.append("")
                prev_blank = True
            else:
                cleaned_lines.append(line)
                prev_blank = False

        return "\n".join(cleaned_lines)

    def _get_attr(self, obj: Any, attr: str) -> Optional[Any]:
        """Get attribute from object or dict."""
        if isinstance(obj, dict):
            return obj.get(attr)
        return getattr(obj, attr, None)


# Module-level instance for convenience
_default_processor: Optional[AttachmentProcessor] = None


def get_attachment_processor() -> AttachmentProcessor:
    """Get the default attachment processor instance."""
    global _default_processor
    if _default_processor is None:
        _default_processor = AttachmentProcessor()
    return _default_processor
