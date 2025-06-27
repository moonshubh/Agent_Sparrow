"""
FeedMe Pydantic Models

Data structures for customer support transcript ingestion and Q&A example extraction.
These models correspond to the database tables and API request/response formats.
"""

from typing import Dict, List, Optional, Any
from uuid import UUID
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator
import uuid

from app.core.settings import settings


class ProcessingStatus(str, Enum):
    """Status of transcript processing"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalStatus(str, Enum):
    """Status of conversation approval workflow"""
    PENDING = "pending"
    PROCESSED = "processed"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class ReviewStatus(str, Enum):
    """Status of example review"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


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
        """
        Validates that the transcript content is at least 10 characters long after stripping whitespace.
        
        Raises:
            ValueError: If the stripped transcript content is shorter than 10 characters.
        
        Returns:
            str: The stripped transcript content.
        """
        if len(v.strip()) < 10:
            raise ValueError('Transcript content must be at least 10 characters long')
        # Max size configured via settings.FEEDME_MAX_FILE_SIZE_MB
        max_chars = settings.feedme_max_file_size_mb * 1024 * 1024
        if len(v) > max_chars:
            raise ValueError(f'Transcript content exceeds maximum size of {max_chars} characters')
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
    uuid: UUID = Field(..., description="Globally unique identifier for the conversation")
    raw_transcript: str = Field(..., description="Full transcript content")
    parsed_content: Optional[str] = Field(None, description="Cleaned/parsed transcript")
    uploaded_at: datetime = Field(..., description="Upload timestamp")
    processed_at: Optional[datetime] = Field(None, description="Processing completion timestamp")
    processing_status: ProcessingStatus = Field(default=ProcessingStatus.PENDING, description="Processing status")
    error_message: Optional[str] = Field(None, description="Error details if processing failed")
    total_examples: int = Field(default=0, ge=0, description="Number of examples extracted")
    
    # Approval workflow fields
    approval_status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, description="Approval workflow status")
    approved_by: Optional[str] = Field(None, description="User who approved/rejected the conversation")
    approved_at: Optional[datetime] = Field(None, description="Approval timestamp")
    rejected_at: Optional[datetime] = Field(None, description="Rejection timestamp")
    reviewer_notes: Optional[str] = Field(None, description="Notes from the reviewer")
    
    # Processing timeline fields
    processing_started_at: Optional[datetime] = Field(None, description="When processing started")
    processing_completed_at: Optional[datetime] = Field(None, description="When processing completed")
    processing_error: Optional[str] = Field(None, description="Detailed processing error information")
    processing_time_ms: Optional[int] = Field(None, description="Processing time in milliseconds")
    
    # Quality metrics
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Average quality score of examples")
    high_quality_examples: int = Field(default=0, ge=0, description="Number of high-quality examples")
    medium_quality_examples: int = Field(default=0, ge=0, description="Number of medium-quality examples")
    low_quality_examples: int = Field(default=0, ge=0, description="Number of low-quality examples")
    
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True  # Updated for Pydantic v2


class FeedMeExample(FeedMeExampleBase):
    """Complete FeedMe example model"""
    id: int = Field(..., description="Unique example ID")
    conversation_id: int = Field(..., description="Parent conversation ID")
    
    # Extraction fields
    extraction_method: str = Field(default="ai", description="Method used for extraction")
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Extraction confidence")
    source_position: int = Field(default=0, description="Position in source transcript")
    
    # Review fields
    reviewed_by: Optional[str] = Field(None, description="User who reviewed this example")
    reviewed_at: Optional[datetime] = Field(None, description="Review timestamp")
    review_status: ReviewStatus = Field(default=ReviewStatus.PENDING, description="Review status")
    
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True  # Updated for Pydantic v2


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
        from_attributes = True  # Updated for Pydantic v2


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
    max_results: int = Field(
        default=5,
        ge=1,
        le=settings.feedme_max_retrieval_results,
        description=f"Maximum number of results (up to {settings.feedme_max_retrieval_results})"
    )
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


# Phase 3: Versioning and Edit UI Schemas

class ConversationVersion(BaseModel):
    """Individual version of a conversation"""
    id: int = Field(..., description="Database ID")
    conversation_id: int = Field(..., description="Parent conversation ID")
    version: int = Field(..., description="Version number")
    title: str = Field(..., description="Conversation title at this version")
    raw_transcript: str = Field(..., description="Transcript content at this version")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Version metadata")
    is_active: bool = Field(..., description="Whether this is the active version")
    updated_by: Optional[str] = Field(None, description="User who created this version")
    created_at: datetime = Field(..., description="When this version was created")
    updated_at: datetime = Field(..., description="When this version was last modified")
    
    class Config:
        from_attributes = True


class VersionListResponse(BaseModel):
    """Response for listing conversation versions"""
    versions: List[ConversationVersion] = Field(..., description="List of versions")
    total_count: int = Field(..., description="Total number of versions")
    active_version: int = Field(..., description="Currently active version number")


class DiffLine(BaseModel):
    """Individual line in a diff"""
    line_number: Optional[int] = Field(None, description="Line number in source")
    content: str = Field(..., description="Line content")
    change_type: str = Field(..., description="Type of change: 'added', 'removed', 'modified', 'unchanged'")


class ModifiedLine(BaseModel):
    """Modified line showing before and after"""
    line_number: int = Field(..., description="Line number")
    original: str = Field(..., description="Original content")
    modified: str = Field(..., description="Modified content")


class VersionDiff(BaseModel):
    """Diff between two conversation versions"""
    from_version: int = Field(..., description="Source version number")
    to_version: int = Field(..., description="Target version number")
    added_lines: List[str] = Field(default_factory=list, description="Lines added in target version")
    removed_lines: List[str] = Field(default_factory=list, description="Lines removed from source version")
    modified_lines: List[ModifiedLine] = Field(default_factory=list, description="Lines modified between versions")
    unchanged_lines: List[str] = Field(default_factory=list, description="Lines that remained the same")
    stats: Dict[str, int] = Field(default_factory=dict, description="Diff statistics")


class ConversationEditRequest(BaseModel):
    """Request to edit a conversation"""
    title: Optional[str] = Field(None, description="Updated title")
    raw_transcript: Optional[str] = Field(None, description="Updated transcript content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Updated metadata")
    updated_by: str = Field(..., description="User making the edit")
    reprocess: bool = Field(default=False, description="Whether to reprocess after edit")

    @validator('raw_transcript')
    def validate_transcript(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Transcript content cannot be empty")
        return v

    @validator('updated_by')
    def validate_updated_by(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("updated_by is required")
        return v


class ConversationRevertRequest(BaseModel):
    """Request to revert a conversation to a previous version"""
    target_version: int = Field(..., description="Version to revert to")
    reverted_by: str = Field(..., description="User performing the revert")
    reason: Optional[str] = Field(None, description="Reason for reverting")
    reprocess: bool = Field(default=True, description="Whether to reprocess after revert")

    @validator('target_version')
    def validate_target_version(cls, v):
        if v < 1:
            raise ValueError("Target version must be 1 or greater")
        return v

    @validator('reverted_by')
    def validate_reverted_by(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("reverted_by is required")
        return v


class EditResponse(BaseModel):
    """Response after editing a conversation"""
    conversation: FeedMeConversation = Field(..., description="Updated conversation")
    new_version: int = Field(..., description="New version number created")
    task_id: Optional[str] = Field(None, description="Celery task ID if reprocessing")
    reprocessing: bool = Field(..., description="Whether reprocessing was triggered")


class RevertResponse(BaseModel):
    """Response after reverting a conversation"""
    conversation: FeedMeConversation = Field(..., description="Reverted conversation")
    new_version: int = Field(..., description="New version number created")
    reverted_to_version: int = Field(..., description="Version that was reverted to")
    task_id: Optional[str] = Field(None, description="Celery task ID if reprocessing")
    reprocessing: bool = Field(..., description="Whether reprocessing was triggered")


# Approval Workflow Models

class ApprovalRequest(BaseModel):
    """Request to approve a conversation"""
    approved_by: str = Field(..., description="User approving the conversation")
    reviewer_notes: Optional[str] = Field(None, description="Optional notes about the approval")
    
    @validator('approved_by')
    def validate_approved_by(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("approved_by is required")
        return v


class RejectionRequest(BaseModel):
    """Request to reject a conversation"""
    rejected_by: str = Field(..., description="User rejecting the conversation")
    reviewer_notes: str = Field(..., description="Required notes about the rejection")
    
    @validator('rejected_by')
    def validate_rejected_by(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("rejected_by is required")
        return v
    
    @validator('reviewer_notes')
    def validate_reviewer_notes(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("reviewer_notes is required for rejections")
        return v


class ApprovalResponse(BaseModel):
    """Response after approving/rejecting a conversation"""
    conversation: FeedMeConversation = Field(..., description="Updated conversation")
    action: str = Field(..., description="Action taken (approved/rejected)")
    timestamp: datetime = Field(..., description="When the action was taken")


class DeleteConversationResponse(BaseModel):
    """Response after deleting a conversation"""
    conversation_id: int = Field(..., description="ID of the deleted conversation")
    title: str = Field(..., description="Title of the deleted conversation")
    examples_deleted: int = Field(..., description="Number of examples deleted")
    message: str = Field(..., description="Confirmation message")


class ApprovalWorkflowStats(BaseModel):
    """Statistics for approval workflow"""
    total_conversations: int = Field(..., description="Total number of conversations")
    pending_approval: int = Field(..., description="Conversations awaiting initial processing")
    awaiting_review: int = Field(..., description="Conversations processed and awaiting review")
    approved: int = Field(..., description="Approved conversations")
    rejected: int = Field(..., description="Rejected conversations")
    published: int = Field(..., description="Published conversations")
    currently_processing: int = Field(..., description="Conversations currently being processed")
    processing_failed: int = Field(..., description="Conversations with processing failures")
    avg_quality_score: Optional[float] = Field(None, description="Average quality score")
    avg_processing_time_ms: Optional[float] = Field(None, description="Average processing time")


class BulkApprovalRequest(BaseModel):
    """Request for bulk approval operations"""
    conversation_ids: List[int] = Field(..., description="List of conversation IDs to process")
    action: str = Field(..., description="Action to take (approve/reject)")
    approved_by: str = Field(..., description="User performing the bulk operation")
    reviewer_notes: Optional[str] = Field(None, description="Notes for the bulk operation")
    
    @validator('conversation_ids')
    def validate_conversation_ids(cls, v):
        if not v or len(v) == 0:
            raise ValueError("At least one conversation ID is required")
        if len(v) > 50:  # Reasonable limit for bulk operations
            raise ValueError("Maximum 50 conversations can be processed at once")
        return v
    
    @validator('action')
    def validate_action(cls, v):
        if v not in ['approve', 'reject']:
            raise ValueError("Action must be 'approve' or 'reject'")
        return v


class BulkApprovalResponse(BaseModel):
    """Response for bulk approval operations"""
    successful: List[int] = Field(..., description="Successfully processed conversation IDs")
    failed: List[Dict[str, Any]] = Field(..., description="Failed operations with error details")
    total_requested: int = Field(..., description="Total number of conversations requested")
    total_successful: int = Field(..., description="Total number successfully processed")
    action_taken: str = Field(..., description="Action that was taken")


class ExampleReviewRequest(BaseModel):
    """Request to review an individual example"""
    reviewed_by: str = Field(..., description="User reviewing the example")
    review_status: ReviewStatus = Field(..., description="Review decision")
    reviewer_notes: Optional[str] = Field(None, description="Optional notes about the review")
    
    # Optional edits to the example
    question_text: Optional[str] = Field(None, description="Updated question text")
    answer_text: Optional[str] = Field(None, description="Updated answer text")
    tags: Optional[List[str]] = Field(None, description="Updated tags")
    
    @validator('reviewed_by')
    def validate_reviewed_by(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("reviewed_by is required")
        return v


class ExampleReviewResponse(BaseModel):
    """Response after reviewing an example"""
    example: FeedMeExample = Field(..., description="Updated example")
    action: str = Field(..., description="Action taken")
    timestamp: datetime = Field(..., description="When the review was completed")