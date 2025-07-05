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
    SENDING_RECEIVING = "sending/receiving"  # Added: AI-generated value
    AVAILABILITY = "availability"  # Added: AI-generated value
    OTHER = "other"


class ResolutionType(str, Enum):
    """Types of resolutions provided"""
    STEP_BY_STEP_GUIDE = "step-by-step-guide"
    CONFIGURATION_CHANGE = "configuration-change"
    WORKAROUND = "workaround"
    FEATURE_EXPLANATION = "feature-explanation"
    ESCALATION = "escalation"
    NO_RESOLUTION = "no-resolution"
    TROUBLESHOOTING = "troubleshooting"  # Added: AI-generated value  
    DATA_REQUEST = "data_request"  # Added: AI-generated value
    TICKET_HOLD = "ticket_hold"  # Added: AI-generated value
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
            raise ValueError("Transcript content must be at least 10 characters long")
        return v


# Update Models (for API requests)

class ConversationUpdate(BaseModel):
    """Model for updating conversations"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    metadata: Optional[Dict[str, Any]] = None
    processing_status: Optional[ProcessingStatus] = None
    error_message: Optional[str] = None
    total_examples: Optional[int] = Field(None, ge=0)


class ExampleUpdate(FeedMeExampleBase):
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


# Analytics Models

class ConversationStats(BaseModel):
    """Aggregated statistics for conversations."""
    total_conversations: int
    total_examples: int
    pending_processing: int
    processing_failed: int
    pending_approval: int
    approved: int
    rejected: int

class AnalyticsResponse(BaseModel):
    """Response model for analytics data."""
    conversation_stats: ConversationStats
    top_tags: Dict[str, int]
    issue_type_distribution: Dict[str, int]
    quality_metrics: Dict[str, float]
    last_updated: datetime


# Approval Workflow Models

class ApprovalRequest(BaseModel):
    """Request model for approving a conversation."""
    approved_by: str = Field(..., description="The ID or name of the user who approved the conversation.")
    approval_notes: Optional[str] = Field(None, description="Optional notes for the approval.")
    tags: Optional[List[str]] = Field(None, description="Optional tags to add or update.")

class RejectionRequest(BaseModel):
    """Request model for rejecting a conversation."""
    rejected_by: str = Field(..., description="The ID or name of the user who rejected the conversation.")
    rejection_reason: str = Field(..., description="The reason for the rejection.")
    rejection_notes: Optional[str] = Field(None, description="Optional additional notes for the rejection.")

class ApprovalResponse(BaseModel):
    """Response model for an approval or rejection action."""
    conversation: "FeedMeConversation"
    approval_status: str
    message: str

class DeleteConversationResponse(BaseModel):
    """Response model for deleting a conversation."""
    message: str
    deleted_conversation_id: int
    deleted_examples_count: int

class BulkApprovalRequest(BaseModel):
    """Request model for bulk approving conversations."""
    conversation_ids: List[int] = Field(..., min_items=1, description="A list of conversation IDs to approve.")
    approved_by: str = Field(..., description="The ID or name of the user performing the bulk approval.")
    approval_notes: Optional[str] = Field(None, description="Optional notes for the bulk approval.")

class BulkApprovalResponse(BaseModel):
    """Response model for a bulk approval operation."""
    approved_ids: List[int]
    failed_ids: Dict[int, str]
    message: str


# Versioning Models

class ConversationVersion(BaseModel):
    """Represents a single version of a conversation's transcript."""
    id: int
    conversation_id: int
    version_number: int
    transcript_content: str
    created_at: datetime
    created_by: Optional[str] = None
    change_description: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True

class VersionListResponse(BaseModel):
    """Response model for a list of conversation versions."""
    versions: List[ConversationVersion]
    total_count: int
    active_version: int

class VersionDiff(BaseModel):
    """Response model for the difference between two versions."""
    diff_html: str
    additions: int
    deletions: int
    version_1_id: int
    version_2_id: int

class ConversationEditRequest(BaseModel):
    """Request model for editing a conversation transcript."""
    transcript_content: str = Field(..., min_length=1, description="The new transcript content.")
    edit_reason: str = Field(..., min_length=1, description="The reason for the edit.")
    user_id: str = Field(..., description="The ID of the user performing the edit.")

class EditResponse(BaseModel):
    """Response model after successfully editing a conversation."""
    conversation_id: int
    new_version: int
    new_version_uuid: UUID
    message: str

class ConversationRevertRequest(BaseModel):
    """Request model for reverting a conversation to a previous version."""
    target_version: int = Field(..., gt=0, description="The version number to revert to.")
    revert_reason: str = Field(..., min_length=1, description="The reason for the revert.")
    user_id: str = Field(..., description="The ID of the user performing the revert.")

class RevertResponse(BaseModel):
    """Response model after successfully reverting a conversation."""
    conversation_id: int
    reverted_to_version: int
    new_version: int
    new_version_uuid: UUID
    message: str


# Search Models

class FeedMeSearchResultItem(BaseModel):
    """A single item in a search result list."""
    id: int
    uuid: UUID
    title: str
    question_text: str
    answer_text: str
    similarity_score: float

    class Config:
        from_attributes = True

class SearchQuery(BaseModel):
    """Request model for performing a search."""
    query: str = Field(..., min_length=1, description="The text to search for.")
    top_k: int = Field(10, ge=1, le=50, description="The number of results to return.")

class FeedMeSearchResponse(BaseModel):
    """Response model for FeedMe search results."""
    query: str
    results: List[FeedMeSearchResultItem]
    total_found: int
    search_time_ms: float


# Database Models (full representations)

class FeedMeConversation(FeedMeConversationBase):
    """Complete FeedMe conversation model"""
    id: int = Field(..., description="Unique conversation ID")
    uuid: UUID = Field(..., description="Globally unique identifier for the conversation")
    
    # Transcript content
    raw_transcript: str = Field(..., description="Raw transcript content")
    
    # Processing status
    processing_status: ProcessingStatus = Field(default=ProcessingStatus.PENDING, description="Processing status")
    processing_started_at: Optional[datetime] = Field(None, description="Timestamp when processing started")
    processing_completed_at: Optional[datetime] = Field(None, description="Timestamp when processing completed")
    processing_time_ms: Optional[int] = Field(None, description="Processing duration in milliseconds")
    error_message: Optional[str] = Field(None, description="Error message if processing failed")
    
    # Approval workflow
    approval_status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, description="Approval status")
    approved_by: Optional[str] = Field(None, description="User who approved the conversation")
    approved_at: Optional[datetime] = Field(None, description="Timestamp of approval")
    
    # Extracted data
    summary: Optional[str] = Field(None, description="AI-generated summary")
    total_examples: int = Field(default=0, ge=0, description="Number of extracted examples")
    
    # Quality metrics
    quality_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Overall quality score")
    
    # Versioning
    version: int = Field(default=1, ge=1, description="Version number")
    is_latest_version: bool = Field(default=True, description="Whether this is the latest version")
    
    # Soft delete
    is_deleted: bool = Field(default=False, description="Whether the conversation is soft-deleted")
    deleted_at: Optional[datetime] = Field(None, description="Timestamp of soft deletion")
    
    # Example counts
    high_quality_examples: int = Field(default=0, ge=0, description="Number of high-quality examples")
    medium_quality_examples: int = Field(default=0, ge=0, description="Number of medium-quality examples")
    low_quality_examples: int = Field(default=0, ge=0, description="Number of low-quality examples")
    
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    class Config:
        from_attributes = True


class FeedMeExample(FeedMeExampleBase):
    """Complete FeedMe example model"""
    id: int = Field(..., description="Unique example ID")
    uuid: UUID = Field(..., description="Globally unique identifier for the example")
    conversation_id: int = Field(..., description="ID of the parent conversation")
    
    # Review and approval
    review_status: ReviewStatus = Field(default=ReviewStatus.PENDING, description="Review status")
    reviewed_by: Optional[str] = Field(None, description="User who reviewed the example")
    reviewed_at: Optional[datetime] = Field(None, description="Timestamp of review")
    reviewer_notes: Optional[str] = Field(None, description="Notes from the reviewer")
    
    # Versioning
    version: int = Field(default=1, ge=1, description="Version number")
    
    # AI-generated fields
    generated_by_model: Optional[str] = Field(None, description="Model that generated the example")
    
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    class Config:
        from_attributes = True


# API Response Models

class ConversationListResponse(BaseModel):
    """Response for listing conversations"""
    conversations: List[FeedMeConversation] = Field(..., description="List of conversations")
    total_count: int = Field(..., description="Total number of conversations")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of conversations per page")
    has_next: bool = Field(..., description="Whether there are more pages available")


class ExampleListResponse(BaseModel):
    """Response for listing examples"""
    examples: List[FeedMeExample] = Field(..., description="List of examples")
    total_examples: int = Field(..., description="Total number of examples")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of examples per page")
    total_pages: int = Field(..., description="Total number of pages")


class ConversationDetailResponse(FeedMeConversation):
    """Detailed view of a single conversation with its examples"""
    examples: List[FeedMeExample] = Field(default_factory=list, description="Examples extracted from the conversation")


class ConversationVersionSummary(BaseModel):
    """Summary of a single conversation version"""
    version: int = Field(..., description="Version number")
    created_at: datetime = Field(..., description="Timestamp of version creation")
    created_by: Optional[str] = Field(None, description="User who created this version")
    change_description: Optional[str] = Field(None, description="Description of changes in this version")


class ConversationVersionHistoryResponse(BaseModel):
    """Response containing the version history of a conversation"""
    conversation_id: int = Field(..., description="ID of the conversation")
    versions: List[ConversationVersionSummary] = Field(..., description="List of all versions")


class ConversationStatsDetail(BaseModel):
    """Detailed statistics for FeedMe conversations"""
    total_conversations: int = Field(..., description="Total number of conversations")
    total_examples: int = Field(..., description="Total number of examples")
    conversations_by_status: Dict[ProcessingStatus, int] = Field(..., description="Count of conversations by status")
    examples_by_review_status: Dict[ReviewStatus, int] = Field(..., description="Count of examples by review status")
    latest_upload: Optional[datetime] = Field(None, description="Timestamp of the latest upload")


class FolderBase(BaseModel):
    """Base model for a folder"""
    name: str = Field(..., min_length=1, max_length=100, description="Folder name")
    description: Optional[str] = Field(None, max_length=255, description="Folder description")


class FolderCreate(FolderBase):
    """Model for creating a new folder"""
    pass


class FolderUpdate(FolderBase):
    """Model for updating a folder"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)


class Folder(FolderBase):
    """Complete folder model"""
    id: int = Field(..., description="Unique folder ID")
    uuid: UUID = Field(..., description="Globally unique identifier for the folder")
    created_by: Optional[str] = Field(None, description="User who created the folder")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    conversation_count: int = Field(0, description="Number of conversations in this folder")
    
    class Config:
        from_attributes = True


class FolderListResponse(BaseModel):
    """Response for listing folders"""
    folders: List[Folder] = Field(..., description="List of folders")


class AddConversationToFolderRequest(BaseModel):
    """Request to add a conversation to a folder"""
    conversation_ids: List[int] = Field(..., description="List of conversation IDs to add")
    
    @validator('conversation_ids')
    def validate_conversation_ids(cls, v):
        if not v:
            raise ValueError("At least one conversation ID must be provided")
        return v


class FolderDetailResponse(Folder):
    """Detailed view of a folder with its conversations"""
    conversations: List[FeedMeConversation] = Field(..., description="List of conversations in the folder")


class SearchResult(BaseModel):
    """A single search result"""
    document_id: str = Field(..., description="ID of the source document (conversation or example)")
    document_type: str = Field(..., description="Type of document (conversation or example)")
    score: float = Field(..., description="Search relevance score")
    content: str = Field(..., description="Matching content snippet")
    metadata: Dict[str, Any] = Field(..., description="Document metadata")


class GeneralSearchResponse(BaseModel):
    """Response for a general search query"""
    query: str = Field(..., description="The original search query")
    results: List[SearchResult] = Field(..., description="List of search results")
    total_results: int = Field(..., description="Total number of results found")
    processing_time_ms: int = Field(..., description="Time taken to process the search in milliseconds")


class ConversationActionLog(BaseModel):
    """Log entry for an action taken on a conversation"""
    id: int = Field(..., description="Unique log ID")
    conversation_id: int = Field(..., description="ID of the conversation")
    action: str = Field(..., description="Action taken (e.g., 'created', 'approved', 'processed')")
    actor: Optional[str] = Field(None, description="User or system component performing the action")
    details: Optional[Dict[str, Any]] = Field(None, description="Details about the action")
    timestamp: datetime = Field(..., description="When the action was taken")


class DeleteConversationResponse(BaseModel):
    """Response after deleting a conversation"""
    conversation_id: int = Field(..., description="ID of the deleted conversation")
    title: str = Field(..., description="Title of the deleted conversation")
    examples_deleted: int = Field(..., description="Number of examples deleted")
    message: str = Field(..., description="Confirmation message")


class ConversationUploadResponse(BaseModel):
    """Response model for conversation uploads."""
    message: str
    conversation_id: int
    processing_status: ProcessingStatus


class ConversationStatusUpdate(BaseModel):
    """Request model to update a conversation's status."""
    processing_status: ProcessingStatus
    error_message: Optional[str] = None


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