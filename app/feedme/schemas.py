"""
FeedMe Pydantic Models

Data structures for customer support transcript ingestion and Q&A example extraction.
These models correspond to the database tables and API request/response formats.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator
import uuid


class ProcessingStatus(str, Enum):
    """Status of transcript processing"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class IssueType(str, Enum):
    """Types of customer issues"""
    ACCOUNT_SETUP = "account-setup"
    EMAIL_SYNC = "email-sync"
    PERFORMANCE = "performance"
    FEATURES = "features"
    BILLING = "billing"
    TECHNICAL_ISSUE = "technical-issue"
    HOW_TO = "how-to"
    TROUBLESHOOTING = "troubleshooting"
    OTHER = "other"


class ResolutionType(str, Enum):
    """Types of resolutions provided"""
    STEP_BY_STEP_GUIDE = "step-by-step-guide"
    CONFIGURATION_CHANGE = "configuration-change"
    WORKAROUND = "workaround"
    FEATURE_EXPLANATION = "feature-explanation"
    ESCALATION = "escalation"
    NO_RESOLUTION = "no-resolution"
    OTHER = "other"


# Base Models

class FeedMeConversationBase(BaseModel):
    """Base model for FeedMe conversations"""
    title: str = Field(..., min_length=1, max_length=255, description="Conversation title or subject")
    original_filename: Optional[str] = Field(None, description="Original uploaded filename")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    uploaded_by: Optional[str] = Field(None, description="User who uploaded the transcript")


class FeedMeExampleBase(BaseModel):
    """Base model for FeedMe Q&A examples"""
    question_text: str = Field(..., min_length=1, description="Customer question or issue description")
    answer_text: str = Field(..., min_length=1, description="Support agent response or solution")
    context_before: Optional[str] = Field(None, description="Context preceding the Q&A exchange")
    context_after: Optional[str] = Field(None, description="Context following the Q&A exchange")
    tags: List[str] = Field(default_factory=list, description="Categorical tags for the example")
    issue_type: Optional[IssueType] = Field(None, description="Type of customer issue")
    resolution_type: Optional[ResolutionType] = Field(None, description="Type of resolution provided")
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Quality confidence score")
    usefulness_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Usefulness rating")
    is_active: bool = Field(default=True, description="Whether example is active for retrieval")


# Create Models (for API requests)

class ConversationCreate(FeedMeConversationBase):
    """Model for creating new conversations"""
    raw_transcript: str = Field(..., min_length=1, description="Full transcript content")


class ExampleCreate(FeedMeExampleBase):
    """Model for creating new examples"""
    conversation_id: int = Field(..., description="ID of the parent conversation")


class TranscriptUploadRequest(BaseModel):
    """Model for transcript upload API requests"""
    title: str = Field(..., min_length=1, max_length=255, description="Conversation title")
    transcript_content: str = Field(..., min_length=1, description="Transcript content")
    uploaded_by: Optional[str] = Field(None, description="User uploading the transcript")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    auto_process: bool = Field(default=True, description="Whether to automatically process the transcript")

    @validator('transcript_content')
    def validate_transcript_content(cls, v):
        if len(v.strip()) < 10:
            raise ValueError('Transcript content must be at least 10 characters long')
        return v.strip()


# Update Models (for API requests)

class ConversationUpdate(BaseModel):
    """Model for updating conversations"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    metadata: Optional[Dict[str, Any]] = None
    processing_status: Optional[ProcessingStatus] = None
    error_message: Optional[str] = None
    total_examples: Optional[int] = Field(None, ge=0)


class ExampleUpdate(BaseModel):
    """Model for updating examples"""
    question_text: Optional[str] = Field(None, min_length=1)
    answer_text: Optional[str] = Field(None, min_length=1)
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    tags: Optional[List[str]] = None
    issue_type: Optional[IssueType] = None
    resolution_type: Optional[ResolutionType] = None
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    usefulness_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    is_active: Optional[bool] = None


# Database Models (full representations)

class FeedMeConversation(FeedMeConversationBase):
    """Complete FeedMe conversation model"""
    id: int = Field(..., description="Unique conversation ID")
    raw_transcript: str = Field(..., description="Full transcript content")
    parsed_content: Optional[str] = Field(None, description="Cleaned/parsed transcript")
    uploaded_at: datetime = Field(..., description="Upload timestamp")
    processed_at: Optional[datetime] = Field(None, description="Processing completion timestamp")
    processing_status: ProcessingStatus = Field(default=ProcessingStatus.PENDING, description="Processing status")
    error_message: Optional[str] = Field(None, description="Error details if processing failed")
    total_examples: int = Field(default=0, ge=0, description="Number of examples extracted")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        orm_mode = True


class FeedMeExample(FeedMeExampleBase):
    """Complete FeedMe example model"""
    id: int = Field(..., description="Unique example ID")
    conversation_id: int = Field(..., description="Parent conversation ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        orm_mode = True


# Search and Retrieval Models

class FeedMeSearchResult(BaseModel):
    """Model for FeedMe similarity search results"""
    id: int = Field(..., description="Example ID")
    conversation_id: int = Field(..., description="Parent conversation ID")
    conversation_title: str = Field(..., description="Parent conversation title")
    question_text: str = Field(..., description="Customer question")
    answer_text: str = Field(..., description="Support agent response")
    context_before: Optional[str] = Field(None, description="Context before the Q&A")
    context_after: Optional[str] = Field(None, description="Context after the Q&A")
    tags: List[str] = Field(default_factory=list, description="Example tags")
    issue_type: Optional[IssueType] = Field(None, description="Issue type")
    resolution_type: Optional[ResolutionType] = Field(None, description="Resolution type")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Similarity score for the search")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Quality confidence score")
    usefulness_score: float = Field(..., ge=0.0, le=1.0, description="Usefulness rating")
    source_type: str = Field(default="feedme", description="Source type identifier")

    class Config:
        orm_mode = True


# API Response Models

class ConversationListResponse(BaseModel):
    """Response model for conversation listing"""
    conversations: List[FeedMeConversation] = Field(..., description="List of conversations")
    total_count: int = Field(..., ge=0, description="Total number of conversations")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Number of items per page")
    has_next: bool = Field(..., description="Whether there are more pages")


class ExampleListResponse(BaseModel):
    """Response model for example listing"""
    examples: List[FeedMeExample] = Field(..., description="List of examples")
    total_count: int = Field(..., ge=0, description="Total number of examples")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Number of items per page")
    has_next: bool = Field(..., description="Whether there are more pages")


class ProcessingStatusResponse(BaseModel):
    """Response model for processing status"""
    conversation_id: int = Field(..., description="Conversation ID")
    status: ProcessingStatus = Field(..., description="Current processing status")
    progress_percentage: float = Field(..., ge=0.0, le=100.0, description="Processing progress")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    examples_extracted: int = Field(default=0, ge=0, description="Number of examples extracted so far")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")


class SearchQuery(BaseModel):
    """Model for FeedMe search requests"""
    query: str = Field(..., min_length=1, description="Search query text")
    max_results: int = Field(default=5, ge=1, le=20, description="Maximum number of results")
    min_similarity: float = Field(default=0.7, ge=0.0, le=1.0, description="Minimum similarity threshold")
    issue_types: Optional[List[IssueType]] = Field(None, description="Filter by issue types")
    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    include_inactive: bool = Field(default=False, description="Include inactive examples")


class SearchResponse(BaseModel):
    """Response model for FeedMe search"""
    query: str = Field(..., description="Original search query")
    results: List[FeedMeSearchResult] = Field(..., description="Search results")
    total_found: int = Field(..., ge=0, description="Total number of results found")
    search_time_ms: float = Field(..., ge=0, description="Search execution time in milliseconds")


# Analytics Models

class ConversationStats(BaseModel):
    """Statistics for conversations"""
    total_conversations: int = Field(..., ge=0)
    processed_conversations: int = Field(..., ge=0)
    failed_conversations: int = Field(..., ge=0)
    pending_conversations: int = Field(..., ge=0)
    average_examples_per_conversation: float = Field(..., ge=0)
    total_examples: int = Field(..., ge=0)
    active_examples: int = Field(..., ge=0)


class TagStats(BaseModel):
    """Statistics for tags"""
    tag: str = Field(..., description="Tag name")
    count: int = Field(..., ge=0, description="Number of examples with this tag")
    percentage: float = Field(..., ge=0, le=100, description="Percentage of total examples")


class IssueTypeStats(BaseModel):
    """Statistics for issue types"""
    issue_type: IssueType = Field(..., description="Issue type")
    count: int = Field(..., ge=0, description="Number of examples of this type")
    percentage: float = Field(..., ge=0, le=100, description="Percentage of total examples")
    average_confidence: float = Field(..., ge=0, le=1, description="Average confidence score")


class AnalyticsResponse(BaseModel):
    """Comprehensive analytics response"""
    conversation_stats: ConversationStats = Field(..., description="Conversation statistics")
    top_tags: List[TagStats] = Field(..., description="Most common tags")
    issue_type_distribution: List[IssueTypeStats] = Field(..., description="Issue type distribution")
    quality_metrics: Dict[str, float] = Field(..., description="Quality and usefulness metrics")
    last_updated: datetime = Field(..., description="When analytics were last calculated")