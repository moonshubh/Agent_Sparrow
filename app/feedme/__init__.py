"""
FeedMe - Customer Support Transcript Ingestion System

This module provides functionality for ingesting customer support transcripts,
parsing them into Q&A examples, and making them available for retrieval
alongside the knowledge base.
"""

from .schemas import (
    FeedMeConversation,
    FeedMeExample,
    ConversationCreate,
    ConversationUpdate,
    ExampleCreate,
    ExampleUpdate,
    TranscriptUploadRequest,
    ProcessingStatus,
    FeedMeSearchResult
)

__all__ = [
    'FeedMeConversation',
    'FeedMeExample', 
    'ConversationCreate',
    'ConversationUpdate',
    'ExampleCreate',
    'ExampleUpdate',
    'TranscriptUploadRequest',
    'ProcessingStatus',
    'FeedMeSearchResult'
]