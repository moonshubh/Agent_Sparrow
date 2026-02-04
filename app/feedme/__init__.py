"""
FeedMe - Customer Support Transcript Ingestion System

This module provides functionality for ingesting customer support transcripts,
parsing them into Q&A examples, and making them available for retrieval
alongside the knowledge base.
"""

from .schemas import (
    FeedMeConversation,
    ConversationCreate,
    ConversationUpdate,
    TranscriptUploadRequest,
    ProcessingStatus,
)

__all__ = [
    "FeedMeConversation",
    "ConversationCreate",
    "ConversationUpdate",
    "TranscriptUploadRequest",
    "ProcessingStatus",
]
