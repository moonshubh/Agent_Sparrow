"""
FeedMe Pydantic Models

Data structures for customer support transcript ingestion and Q&A example extraction.
These models correspond to the database tables and API request/response formats.
"""

from typing import Dict, List, Optional, Any
from uuid import UUID
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator, field_validator
import uuid

from app.core.settings import settings


class ProcessingStatus(str, Enum):
    """Status of transcript processing"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingStage(str, Enum):
    """Detailed stage within the processing pipeline"""
    QUEUED = "queued"
    PARSING = "parsing"
    AI_EXTRACTION = "ai_extraction"
    EMBEDDING_GENERATION = "embedding_generation"
    QUALITY_ASSESSMENT = "quality_assessment"
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
    COMMUNICATION = "communication"  # Added: AI-generated value
    EMAIL_SENDING = "email sending"  # Added: AI-generated value
    TICKET_MANAGEMENT = "ticket management"  # Added: AI-generated value
    GENERAL = "general"  # Added: AI-generated value
    TECHNICAL_PDF = "technical-pdf"  # Added: AI-generated value for PDF extraction
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
    DATA_REQUEST_SPACE = "data request"  # Added: AI-generated value with space
    TICKET_HOLD = "ticket_hold"  # Added: AI-generated value
    TICKET_HOLD_SPACE = "ticket hold"  # Added: AI-generated value with space
    CLARIFICATION = "clarification"  # Added: AI-generated value
    RESOLVED = "resolved"  # Added: AI-generated value
    PENDING = "pending"  # Added: AI-generated value for PDF extraction
    INFORMATION_PROVIDED = "information_provided"  # Added: AI-generated value for PDF extraction
    OTHER = "other"


# Base Models

class ProcessingMethod(str, Enum):
    """Methods for processing conversation content"""
    # Legacy/compatible values
    PDF_OCR = "pdf_ocr"
    MANUAL_TEXT = "manual_text" 
    TEXT_PASTE = "text_paste"
    # Extended values used by processing tasks
    PDF_AI = "pdf_ai"
    PDF_TEXT = "pdf_text"


class FeedMeConversationBase(BaseModel):
    """Base model for FeedMe conversations - restructured for PDF+text workflow"""
    title: str = Field(..., min_length=1, max_length=255, description="Conversation title or subject")
    original_filename: Optional[str] = Field(None, description="Original uploaded filename")
    extracted_text: Optional[str] = Field(None, description="Unified text content extracted from PDF or manually entered")
    processing_method: ProcessingMethod = Field(default=ProcessingMethod.PDF_OCR, description="Method used to process content")
    extraction_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="OCR confidence score for PDF extractions")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    uploaded_by: Optional[str] = Field(None, description="User who uploaded the content")
    approved_by: Optional[str] = Field(None, description="User who approved the extracted text")
    approved_at: Optional[datetime] = Field(None, description="Timestamp when text was approved")


# Create Models (for API requests)

class ConversationCreate(FeedMeConversationBase):
    """Model for creating new conversations"""
    raw_transcript: str = Field(..., min_length=1, description="Full transcript content")
    mime_type: Optional[str] = Field(None, description="MIME type of the uploaded file")
    pages: Optional[int] = Field(None, description="Number of pages in PDF documents")
    pdf_metadata: Optional[Dict[str, Any]] = Field(None, description="PDF metadata (author, creation date, etc.)")


# Q&A Example models removed - system now uses unified text canvas


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
    """Model for updating conversations - updated for unified text workflow"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    extracted_text: Optional[str] = Field(None, description="Updated unified text content")
    processing_method: Optional[ProcessingMethod] = None
    extraction_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    metadata: Optional[Dict[str, Any]] = None
    processing_status: Optional[ProcessingStatus] = None
    error_message: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


# Analytics Models - Updated for unified text workflow

class ConversationStats(BaseModel):
    """Aggregated statistics for conversations - updated for unified text workflow"""
    total_conversations: int
    pending_processing: int
    processing_failed: int
    pending_approval: int
    approved: int
    rejected: int
    pdf_processed: int = Field(default=0, description="Conversations processed via PDF OCR")
    manual_text: int = Field(default=0, description="Conversations with manually entered text")
    avg_extraction_confidence: Optional[float] = Field(None, description="Average OCR extraction confidence")

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


# Search functionality removed - FeedMe system now focuses on PDF OCR and manual text processing only


# Database Models (full representations)

class FeedMeConversation(FeedMeConversationBase):
    """Complete FeedMe conversation model"""
    id: int = Field(..., description="Unique conversation ID")
    uuid: UUID = Field(..., description="Globally unique identifier for the conversation")
    
    # Transcript content
    raw_transcript: str = Field(..., description="Raw transcript content")
    
    # File format and metadata
    mime_type: Optional[str] = Field(None, description="MIME type of the uploaded file")
    pages: Optional[int] = Field(None, description="Number of pages in PDF documents")
    pdf_metadata: Optional[Dict[str, Any]] = Field(None, description="PDF metadata (author, creation date, etc.)")
    
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


# FeedMeExample class removed - system now uses unified text canvas approach


# API Response Models


class ConversationProcessingStatus(BaseModel):
    """Processing status payload shared between HTTP and WebSocket layers"""

    conversation_id: int
    status: ProcessingStatus
    stage: ProcessingStage
    progress_percentage: int = Field(default=0, ge=0, le=100)
    message: Optional[str] = None
    error_message: Optional[str] = None

    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    processing_time_ms: Optional[int] = None

    metadata: Dict[str, Any] = Field(default_factory=dict)

class ConversationListResponse(BaseModel):
    """Response for listing conversations"""
    conversations: List[FeedMeConversation] = Field(..., description="List of conversations")
    total_count: int = Field(..., description="Total number of conversations")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of conversations per page")
    has_next: bool = Field(..., description="Whether there are more pages available")


# ExampleListResponse removed - system now uses unified text canvas approach

class ConversationDetailResponse(FeedMeConversation):
    """Detailed view of a single conversation - updated for unified text workflow"""
    # No examples field - conversation content is stored as unified text in extracted_text


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
    color: str = Field(default="#0095ff", description="Folder color in hex format")
    created_by: Optional[str] = Field(default="system", description="User who created the folder")


class FolderUpdate(FolderBase):
    """Model for updating a folder"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = Field(None, description="Folder color in hex format")
    description: Optional[str] = Field(None, max_length=255, description="Folder description")


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


# Example review models removed - system now uses unified text canvas with conversation-level approval


# Text Approval Workflow Models (Added for Phase 2B)

class TextApprovalAction(str, Enum):
    """Actions for text approval workflow"""
    APPROVE = "approve"
    REJECT = "reject"
    EDIT_AND_APPROVE = "edit_and_approve"
    REQUEST_REPROCESS = "request_reprocess"


class TextApprovalRequest(BaseModel):
    """Request model for text approval decisions"""
    action: TextApprovalAction = Field(..., description="Approval action to take")
    reviewer_id: str = Field(..., min_length=1, description="ID of the reviewer")
    notes: Optional[str] = Field(None, description="Optional reviewer notes")
    edited_text: Optional[str] = Field(None, description="Edited text (required for edit_and_approve)")
    feedback: Optional[str] = Field(None, description="Feedback for rejection or reprocess requests")


class TextApprovalResponse(BaseModel):
    """Response model for text approval decisions"""
    action: str = Field(..., description="Action that was taken")
    conversation_id: int = Field(..., description="ID of the conversation")
    reviewer_id: str = Field(..., description="ID of the reviewer")
    timestamp: str = Field(..., description="Timestamp of the action")
    message: str = Field(..., description="Success message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional action details")


class ApprovalQueueSummary(BaseModel):
    """Summary of conversations in approval queue"""
    total_pending: int = Field(..., description="Total conversations pending approval")
    priority_breakdown: Dict[str, int] = Field(..., description="Breakdown by review priority (high/medium/low)")
    processing_method_breakdown: Dict[str, int] = Field(..., description="Breakdown by processing method")
    confidence_breakdown: Dict[str, int] = Field(..., description="Breakdown by extraction confidence level")


class ConversationApprovalPreview(BaseModel):
    """Enhanced conversation data for approval preview"""
    # Inherit all fields from FeedMeConversation
    id: int = Field(..., description="Unique conversation ID")
    title: str = Field(..., description="Conversation title")
    extracted_text: Optional[str] = Field(None, description="Extracted text content")
    processing_method: ProcessingMethod = Field(default=ProcessingMethod.PDF_OCR)
    extraction_confidence: Optional[float] = Field(None, description="Confidence score from OCR")
    approval_status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    
    # Approval-specific fields
    review_priority: str = Field(..., description="Review priority level (high/medium/low)")
    review_reason: str = Field(..., description="Reason for the review priority")
    text_stats: Dict[str, int] = Field(..., description="Text statistics (character count, word count, etc.)")
    approval_metadata: Dict[str, Any] = Field(..., description="Metadata for approval process")
    
    class Config:
        from_attributes = True


# Example-related schemas for Q&A pairs
class FeedMeExampleBase(BaseModel):
    """Base schema for FeedMe Q&A examples"""
    question_text: str
    answer_text: str
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    tags: List[str] = []
    issue_type: Optional[str] = None
    resolution_type: Optional[str] = None
    confidence_score: float = 0.5
    usefulness_score: float = 0.5
    is_active: bool = True


class ExampleCreate(FeedMeExampleBase):
    """Schema for creating a new example"""
    conversation_id: int


class ExampleUpdate(BaseModel):
    """Schema for updating an example"""
    question_text: Optional[str] = None
    answer_text: Optional[str] = None
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    tags: Optional[List[str]] = None
    issue_type: Optional[str] = None
    resolution_type: Optional[str] = None
    confidence_score: Optional[float] = None
    usefulness_score: Optional[float] = None
    is_active: Optional[bool] = None


class FeedMeExample(FeedMeExampleBase):
    """Complete schema for FeedMe Q&A example"""
    id: int
    conversation_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ExampleListResponse(BaseModel):
    """Response schema for listing examples"""
    examples: List[FeedMeExample]
    total_examples: int
    page: int
    page_size: int
    total_pages: int
    
    class Config:
        from_attributes = True


class ExampleReviewRequest(BaseModel):
    """Request schema for reviewing an example"""
    reviewed_by: str
    review_status: ReviewStatus
    reviewer_notes: Optional[str] = None
    question_text: Optional[str] = None
    answer_text: Optional[str] = None
    tags: Optional[List[str]] = None


class ExampleReviewResponse(BaseModel):
    """Response schema for example review"""
    example: FeedMeExample
    action: str
    timestamp: datetime


# Intelligence API Schemas

class ConversationSummaryRequest(BaseModel):
    """Request for conversation summarization"""
    conversation_text: str = Field(..., description="Full conversation text to summarize")
    max_length: int = Field(500, description="Maximum length of summary in characters")
    focus: str = Field("key_points", description="Summary focus: key_points, technical_issues, or resolution")
    
    @field_validator('focus')
    def validate_focus(cls, v):
        allowed_focus = ['key_points', 'technical_issues', 'resolution']
        if v not in allowed_focus:
            raise ValueError(f"Focus must be one of: {', '.join(allowed_focus)}")
        return v


class SentimentData(BaseModel):
    """Sentiment analysis data"""
    overall: str = Field(..., description="Overall sentiment: positive/neutral/negative/mixed")
    customer_start: str = Field(..., description="Customer sentiment at start")
    customer_end: str = Field(..., description="Customer sentiment at end")
    sentiment_shift: str = Field(..., description="Sentiment change: improved/unchanged/worsened")


class AgentPerformance(BaseModel):
    """Agent performance metrics"""
    empathy: str = Field(..., description="Empathy level: high/medium/low")
    technical_knowledge: str = Field(..., description="Technical knowledge: expert/proficient/basic")
    problem_solving: str = Field(..., description="Problem solving: excellent/good/needs_improvement")


class ConversationSummaryData(BaseModel):
    """Conversation summary data"""
    summary: str = Field(..., description="Concise summary of the conversation")
    sentiment: SentimentData = Field(..., description="Sentiment analysis")
    key_topics: List[str] = Field(..., description="Key topics discussed")
    technical_issues: List[str] = Field(..., description="Technical issues identified")
    resolution_status: str = Field(..., description="Resolution status")
    action_items: List[str] = Field(..., description="Action items identified")
    agent_performance: AgentPerformance = Field(..., description="Agent performance metrics")
    conversation_length: int = Field(..., description="Original conversation length")
    summarization_model: str = Field(..., description="Model used for summarization")
    focus_type: str = Field(..., description="Summary focus type")


class ConversationSummaryResponse(BaseModel):
    """Response for conversation summarization"""
    success: bool
    data: ConversationSummaryData
    confidence: float = Field(..., description="Confidence score for the summary")


class BatchAnalysisRequest(BaseModel):
    """Request for batch conversation analysis"""
    conversation_ids: Optional[List[int]] = Field(None, description="IDs of conversations to analyze")
    conversations: Optional[List[Dict[str, Any]]] = Field(None, description="Direct conversation data")
    analysis_type: str = Field("patterns", description="Analysis type: patterns, quality, or training_gaps")
    
    @field_validator('analysis_type')
    def validate_analysis_type(cls, v):
        allowed_types = ['patterns', 'quality', 'training_gaps']
        if v not in allowed_types:
            raise ValueError(f"Analysis type must be one of: {', '.join(allowed_types)}")
        return v


class CommonIssue(BaseModel):
    """Common issue identified in batch analysis"""
    issue: str
    frequency: int
    severity: str


class ResolutionPattern(BaseModel):
    """Resolution pattern identified"""
    pattern: str
    effectiveness: str
    examples: int


class KnowledgeGap(BaseModel):
    """Knowledge gap identified"""
    topic: str
    impact: str
    recommendation: str


class QualityMetrics(BaseModel):
    """Quality metrics for conversations"""
    average_resolution_quality: float
    response_appropriateness: float
    technical_accuracy: float


class AutomationOpportunity(BaseModel):
    """Automation opportunity identified"""
    scenario: str
    confidence: float
    potential_impact: str


class BatchAnalysisData(BaseModel):
    """Batch analysis results"""
    common_issues: List[CommonIssue]
    resolution_patterns: List[ResolutionPattern]
    knowledge_gaps: List[KnowledgeGap]
    quality_metrics: QualityMetrics
    training_recommendations: List[str]
    automation_opportunities: List[AutomationOpportunity]
    total_conversations_analyzed: int
    analysis_type: str
    analysis_model: str


class BatchAnalysisResponse(BaseModel):
    """Response for batch conversation analysis"""
    success: bool
    data: BatchAnalysisData
    insights_generated: int


class SmartSearchRequest(BaseModel):
    """Request for smart search"""
    query: str = Field(..., description="Natural language search query")
    limit: int = Field(10, description="Maximum number of results")
    filters: Optional[Dict[str, Any]] = Field(None, description="Additional filters")


class SmartSearchResult(BaseModel):
    """Individual smart search result"""
    id: int
    question_text: str
    answer_text: str
    relevance_score: float
    match_reason: str
    metadata: Optional[Dict[str, Any]] = None


class SmartSearchResponse(BaseModel):
    """Response for smart search"""
    success: bool
    query: str
    intent: str
    key_terms: List[str]
    results: List[SmartSearchResult]
    total_results: int
    suggestions: List[str]
    class Config:
        from_attributes = True
