"""
FeedMe v2.0 Approval Workflow Schemas

Pydantic models for approval workflow data structures, validation, and API contracts.
"""

from datetime import datetime
from typing import List, Dict, Optional, Any, Union
from enum import Enum

from pydantic import BaseModel, Field, validator, ConfigDict, ValidationError
import numpy as np


class ApprovalState(str, Enum):
    """Approval states for temp examples"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"
    AUTO_APPROVED = "auto_approved"


class ApprovalAction(str, Enum):
    """Available approval actions"""
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REVISION = "request_revision"


class Priority(str, Enum):
    """Priority levels for review"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class RejectionReason(str, Enum):
    """Reasons for rejection"""
    POOR_QUALITY = "poor_quality"
    IRRELEVANT = "irrelevant"
    DUPLICATE = "duplicate"
    INCOMPLETE = "incomplete"
    INACCURATE = "inaccurate"
    POLICY_VIOLATION = "policy_violation"
    OTHER = "other"


# ===========================
# Core Data Models
# ===========================

class TempExampleCreate(BaseModel):
    """Schema for creating a new temp example"""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    conversation_id: int = Field(..., gt=0)
    question_text: str = Field(..., min_length=5, max_length=2000)
    answer_text: str = Field(..., min_length=10, max_length=5000)
    context_before: Optional[str] = Field(None, max_length=1000)
    context_after: Optional[str] = Field(None, max_length=1000)
    
    # AI extraction metadata
    extraction_confidence: float = Field(..., ge=0.0, le=1.0)
    ai_model_used: str = Field(..., min_length=1)
    extraction_method: str = Field(default="ai")
    
    # Optional categorization
    issue_category: Optional[str] = Field(None, max_length=50)
    tags: Optional[List[str]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @validator('question_text', 'answer_text')
    def validate_text_content(cls, v):
        """Validate text content for basic quality"""
        if not v or not v.strip():
            raise ValueError("Text content cannot be empty")
        
        # Basic content validation
        if len(v.split()) < 2:
            raise ValueError("Text content must contain at least 2 words")
        
        return v.strip()

    @validator('tags')
    def validate_tags(cls, v):
        """Validate tags list"""
        if v and len(v) > 10:
            raise ValueError("Maximum 10 tags allowed")
        
        # Clean and validate individual tags
        cleaned_tags = []
        for tag in v or []:
            tag = tag.strip().lower()
            if tag and len(tag) <= 30:
                cleaned_tags.append(tag)
        
        return cleaned_tags


class TempExampleUpdate(BaseModel):
    """Schema for updating a temp example"""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    question_text: Optional[str] = Field(None, min_length=5, max_length=2000)
    answer_text: Optional[str] = Field(None, min_length=10, max_length=5000)
    context_before: Optional[str] = Field(None, max_length=1000)
    context_after: Optional[str] = Field(None, max_length=1000)
    
    # Approval workflow fields
    assigned_reviewer: Optional[str] = Field(None, max_length=255)
    priority: Optional[Priority] = None
    
    # Quality assessments
    reviewer_confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    reviewer_usefulness_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    
    # Metadata updates
    tags: Optional[List[str]] = Field(None)
    metadata: Optional[Dict[str, Any]] = Field(None)


class TempExampleResponse(BaseModel):
    """Schema for temp example responses"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    conversation_id: int
    question_text: str
    answer_text: str
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    
    # Embeddings (excluded from API responses by default)
    question_embedding: Optional[List[float]] = Field(None, exclude=True)
    answer_embedding: Optional[List[float]] = Field(None, exclude=True)
    combined_embedding: Optional[List[float]] = Field(None, exclude=True)
    
    # AI extraction metadata
    extraction_method: str
    extraction_confidence: float
    ai_model_used: str
    extraction_timestamp: datetime
    
    # Approval workflow fields
    approval_status: ApprovalState
    assigned_reviewer: Optional[str] = None
    priority: Priority
    
    # Review information
    review_notes: Optional[str] = None
    rejection_reason: Optional[RejectionReason] = None
    revision_instructions: Optional[str] = None
    reviewer_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    
    # Quality assessments
    reviewer_confidence_score: Optional[float] = None
    reviewer_usefulness_score: Optional[float] = None
    
    # Auto-approval
    auto_approved: bool
    auto_approval_reason: Optional[str] = None
    
    # Metadata
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    created_at: datetime
    updated_at: datetime


# ===========================
# Workflow Decision Models
# ===========================

class ApprovalDecision(BaseModel):
    """Schema for approval decisions"""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    temp_example_id: int = Field(..., gt=0)
    action: ApprovalAction
    reviewer_id: str = Field(..., min_length=1, max_length=255)
    
    # Review details
    review_notes: Optional[str] = Field(None, max_length=2000)
    confidence_assessment: Optional[float] = Field(None, ge=0.0, le=1.0)
    time_spent_minutes: Optional[int] = Field(None, ge=0, le=480)  # Max 8 hours
    
    # Action-specific fields
    rejection_reason: Optional[RejectionReason] = None
    revision_instructions: Optional[str] = Field(None, max_length=1000)
    
    # Quality scores
    reviewer_confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    reviewer_usefulness_score: Optional[float] = Field(None, ge=0.0, le=1.0)

    def model_post_init(self, __context):
        """Validate rejection reason and revision instructions after model creation"""
        if self.action == ApprovalAction.REJECT and not self.rejection_reason:
            raise ValidationError.from_exception_data(
                self.__class__,
                [
                    {
                        "type": "missing",
                        "loc": ("rejection_reason",),
                        "msg": "Rejection reason is required for reject action",
                    }
                ],
            )
        
        if self.action == ApprovalAction.REQUEST_REVISION and not self.revision_instructions:
            raise ValidationError.from_exception_data(
                self.__class__,
                [
                    {
                        "type": "missing",
                        "loc": ("revision_instructions",),
                        "msg": "Revision instructions are required for revision request",
                    }
                ],
            )


class BulkApprovalRequest(BaseModel):
    """Schema for bulk approval operations"""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    temp_example_ids: List[int] = Field(..., min_items=1, max_items=100)
    action: ApprovalAction
    reviewer_id: str = Field(..., min_length=1, max_length=255)
    
    # Bulk review details
    review_notes: Optional[str] = Field(None, max_length=2000)
    
    # Action-specific fields
    rejection_reason: Optional[RejectionReason] = None
    revision_instructions: Optional[str] = Field(None, max_length=1000)

    @validator('temp_example_ids')
    def validate_unique_ids(cls, v):
        """Ensure all IDs are unique"""
        if len(v) != len(set(v)):
            raise ValueError("Duplicate temp example IDs are not allowed")
        return v


class BulkApprovalResponse(BaseModel):
    """Schema for bulk approval operation responses"""
    processed_count: int
    successful_count: int
    failed_count: int
    failures: List[Dict[str, Any]] = Field(default_factory=list)
    processing_time_ms: Optional[float] = None


# ===========================
# Analytics and Metrics
# ===========================

class WorkflowMetrics(BaseModel):
    """Schema for workflow metrics and analytics"""
    # Volume metrics
    total_pending: int
    total_approved: int
    total_rejected: int
    total_revision_requested: int
    total_auto_approved: int
    
    # Performance metrics
    approval_rate: float = Field(..., ge=0.0, le=1.0)
    rejection_rate: float = Field(..., ge=0.0, le=1.0)
    auto_approval_rate: float = Field(..., ge=0.0, le=1.0)
    
    # Time metrics
    avg_review_time_hours: Optional[float] = None
    median_review_time_hours: Optional[float] = None
    
    # Quality metrics
    avg_extraction_confidence: Optional[float] = None
    avg_reviewer_confidence: Optional[float] = None
    
    # Reviewer efficiency
    reviewer_efficiency: Dict[str, int] = Field(default_factory=dict)
    
    # Time period
    period_start: datetime
    period_end: datetime


class ReviewerWorkload(BaseModel):
    """Schema for reviewer workload information"""
    reviewer_id: str
    pending_count: int
    total_reviewed: int
    avg_review_time_hours: Optional[float] = None
    efficiency_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    
    # Recent activity
    reviews_today: int = 0
    reviews_this_week: int = 0


class ReviewerWorkloadSummary(BaseModel):
    """Schema for overall reviewer workload summary"""
    reviewers: List[ReviewerWorkload]
    total_pending: int
    avg_workload: float
    max_workload: int
    min_workload: int
    recommendations: List[str] = Field(default_factory=list)


# ===========================
# Configuration Models
# ===========================

class WorkflowConfig(BaseModel):
    """Configuration for approval workflow"""
    # Auto-approval thresholds
    auto_approval_threshold: float = Field(default=0.9, ge=0.5, le=1.0)
    high_confidence_threshold: float = Field(default=0.8, ge=0.5, le=1.0)
    require_review_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    
    # Workflow settings
    batch_size: int = Field(default=10, ge=1, le=100)
    max_pending_per_reviewer: int = Field(default=20, ge=5, le=100)
    enable_auto_assignment: bool = Field(default=True)
    
    # Time limits
    review_timeout_hours: int = Field(default=24, ge=1, le=168)  # Max 1 week
    escalation_timeout_hours: int = Field(default=48, ge=2, le=336)  # Max 2 weeks
    
    # Quality settings
    min_confidence_for_auto_approval: float = Field(default=0.9, ge=0.5, le=1.0)
    require_dual_review_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    @validator('high_confidence_threshold')
    def validate_threshold_order(cls, v, values):
        """Ensure thresholds are in correct order"""
        auto_threshold = values.get('auto_approval_threshold', 0.9)
        if v >= auto_threshold:
            raise ValueError("High confidence threshold must be less than auto approval threshold")
        return v


# ===========================
# API Response Models
# ===========================

class PaginatedTempExampleResponse(BaseModel):
    """Paginated response for temp examples"""
    items: List[TempExampleResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @validator('total_pages', always=True)
    def calculate_total_pages(cls, v, values):
        """Calculate total pages based on total and page_size"""
        total = values.get('total', 0)
        page_size = values.get('page_size', 10)
        return (total + page_size - 1) // page_size if total > 0 else 0


class ApprovalSummary(BaseModel):
    """Summary of approval status"""
    status: ApprovalState
    count: int
    percentage: float


class WorkflowSummary(BaseModel):
    """High-level workflow summary"""
    total_items: int
    status_breakdown: List[ApprovalSummary]
    avg_processing_time_hours: Optional[float] = None
    bottlenecks: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)