"""Pydantic models supporting global knowledge submissions and enhancements."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Literal, Optional, Tuple

from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_SOURCES = {"feedback", "correction"}
ALLOWED_ATTACHMENT_KINDS = {"link", "image"}
ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
    "image/svg+xml",
    "application/pdf",
    "text/html",
}
MAX_ATTACHMENT_COUNT = 5
MAX_METADATA_KEYS = 25
MAX_METADATA_DEPTH = 2
MAX_METADATA_LIST_ITEMS = 10
MAX_METADATA_STRING_LENGTH = 512
MAX_TEXT_LENGTH_DEFAULT = 4000
MAX_SUMMARY_TEXT_LENGTH = 2000


KindLiteral = Literal["feedback", "correction"]


def _sanitize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        trimmed = value.strip()
        if len(trimmed) > MAX_METADATA_STRING_LENGTH:
            return trimmed[: MAX_METADATA_STRING_LENGTH - 1] + "…"
        return trimmed
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_METADATA_STRING_LENGTH]


def sanitize_metadata(data: Dict[str, Any], *, _depth: int = 0) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}

    if _depth >= MAX_METADATA_DEPTH:
        return {}

    sanitized: Dict[str, Any] = {}
    for index, (key, value) in enumerate(data.items()):
        if index >= MAX_METADATA_KEYS:
            break
        if not isinstance(key, str):
            continue
        trimmed_key = key.strip()
        if not trimmed_key:
            continue
        if isinstance(value, dict):
            sanitized_value = sanitize_metadata(value, _depth=_depth + 1)
        elif isinstance(value, list):
            sanitized_value = []
            for item_index, item in enumerate(value):
                if item_index >= MAX_METADATA_LIST_ITEMS:
                    break
                if isinstance(item, dict):
                    sanitized_value.append(sanitize_metadata(item, _depth=_depth + 1))
                else:
                    sanitized_value.append(_sanitize_scalar(item))
        else:
            sanitized_value = _sanitize_scalar(value)

        sanitized[trimmed_key] = sanitized_value
    return sanitized


class Attachment(BaseModel):
    """Metadata describing user-provided attachments."""

    kind: Optional[str] = Field(default=None, max_length=20)
    url: Optional[str] = Field(default=None, max_length=2048)
    title: Optional[str] = Field(default=None, max_length=256)
    mime_type: Optional[str] = Field(default=None, alias="mime", max_length=128)

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe representation."""

        return self.model_dump(by_alias=True, exclude_none=True)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in ALLOWED_ATTACHMENT_KINDS:
            raise ValueError(f"Attachment kind '{value}' is not permitted")
        return normalized

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        candidate = value.strip()
        parsed = urlparse(candidate)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Attachment URLs must use HTTPS and include a host")
        return candidate

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return value.strip() or None

    @field_validator("mime_type")
    @classmethod
    def validate_mime(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in ALLOWED_MIME_TYPES:
            raise ValueError(f"Attachment MIME type '{value}' is not permitted")
        return normalized


class BaseSubmission(BaseModel):
    """Common fields shared by all submissions."""

    user_id: str = Field(max_length=128)
    attachments: List[Attachment] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def attachments_payload(self) -> List[Dict[str, Any]]:
        """Return attachments as JSON-serialisable dictionaries."""

        return [attachment.to_dict() for attachment in self.attachments]

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("user_id cannot be empty")
        return normalized

    @field_validator("attachments", mode="after")
    @classmethod
    def enforce_attachment_limits(cls, value: List[Attachment]) -> List[Attachment]:
        if len(value) > MAX_ATTACHMENT_COUNT:
            raise ValueError(f"A maximum of {MAX_ATTACHMENT_COUNT} attachments are allowed")
        return value

    @field_validator("metadata", mode="before")
    @classmethod
    def sanitize_metadata(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        return sanitize_metadata(value or {})


class FeedbackSubmission(BaseSubmission):
    """Submission from the /feedback slash command."""

    feedback_text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH_DEFAULT)
    selected_text: Optional[str] = Field(default=None, max_length=MAX_SUMMARY_TEXT_LENGTH)

    @property
    def kind(self) -> KindLiteral:
        return "feedback"

    @field_validator("feedback_text")
    @classmethod
    def normalize_feedback_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("feedback_text cannot be empty")
        return normalized

    @field_validator("selected_text")
    @classmethod
    def normalize_selected_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class CorrectionSubmission(BaseSubmission):
    """Submission from the /correct slash command."""

    incorrect_text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH_DEFAULT)
    corrected_text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH_DEFAULT)
    explanation: Optional[str] = Field(default=None, max_length=MAX_TEXT_LENGTH_DEFAULT)

    @property
    def kind(self) -> KindLiteral:
        return "correction"

    @field_validator("incorrect_text")
    @classmethod
    def normalize_incorrect_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("incorrect_text cannot be empty")
        return normalized

    @field_validator("corrected_text")
    @classmethod
    def normalize_corrected_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("corrected_text cannot be empty")
        return normalized

    @field_validator("explanation")
    @classmethod
    def normalize_explanation(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class EnhancedPayload(BaseModel):
    """Enhanced representation produced by the FeedbackEnhancer."""

    kind: KindLiteral
    summary: str = Field(max_length=MAX_SUMMARY_TEXT_LENGTH)
    key_facts: List[str] = Field(default_factory=list)
    normalized_pair: Optional[Dict[str, str]] = None
    tags: List[str] = Field(default_factory=list)
    raw_text: str = Field(max_length=MAX_TEXT_LENGTH_DEFAULT)
    attachments: List[Attachment] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embed_version: str = "v1"

    model_config = ConfigDict(validate_assignment=True, arbitrary_types_allowed=True)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: KindLiteral) -> KindLiteral:
        if value not in ALLOWED_SOURCES:
            raise ValueError(f"Enhanced payload kind '{value}' is not permitted")
        return value

    @property
    def store_namespace(self) -> Tuple[str, str]:
        """Namespace tuple used for LangGraph store writes."""

        return ("global_knowledge", self.kind)

    @property
    def store_key(self) -> str:
        """Return a deterministic store key derived from summary and raw text."""

        hasher = hashlib.sha256()
        hasher.update(self.kind.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(self.summary.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(self.raw_text.encode("utf-8"))
        return hasher.hexdigest()

    def to_store_item(self) -> Tuple[Tuple[str, str], str, Dict[str, Any]]:
        """Return namespace, key, and value dictionary for store upsert operations."""

        namespace = self.store_namespace
        key = self.store_key
        value = {
            "summary": self.summary,
            "key_facts": list(self.key_facts),
            "normalized_pair": self.normalized_pair,
            "tags": list(self.tags),
            "raw_text": self.raw_text,
            "metadata": dict(self.metadata),
            "attachments": [attachment.to_dict() for attachment in self.attachments],
            "embed_version": self.embed_version,
            "source": self.kind,
        }
        return namespace, key, value

    @field_validator("attachments", mode="after")
    @classmethod
    def enforce_attachment_limit(cls, value: List[Attachment]) -> List[Attachment]:
        if len(value) > MAX_ATTACHMENT_COUNT:
            raise ValueError(f"Enhanced payload supports up to {MAX_ATTACHMENT_COUNT} attachments")
        return value

    @field_validator("metadata", mode="before")
    @classmethod
    def sanitize_payload_metadata(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        return sanitize_metadata(value or {})


class PersistenceResult(BaseModel):
    """Result wrapper returned by persistence helpers."""

    supabase_row: Optional[Dict[str, Any]] = None
    enhanced: EnhancedPayload
    store_written: bool = False
    memory_written: bool = False

    model_config = ConfigDict(arbitrary_types_allowed=True)
