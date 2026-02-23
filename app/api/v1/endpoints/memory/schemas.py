"""
Memory UI API Schemas

Pydantic V2 schemas for the Memory UI system API endpoints.
These schemas support CRUD operations on memories, entity/relationship management,
duplicate detection workflows, user feedback, and export functionality.

Database tables:
- memories: Core memory storage with content, embedding (3072-dim), confidence_score
- memory_entities: Extracted entities (product, feature, issue, solution, etc.)
- memory_relationships: Entity relationships (RESOLVED_BY, AFFECTS, etc.)
- memory_duplicate_candidates: Duplicate detection queue
- memory_feedback: User feedback tracking
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# =============================================================================
# Enums
# =============================================================================


class SourceType(str, Enum):
    """Source type indicating how the memory was created."""

    AUTO_EXTRACTED = "auto_extracted"
    """Memory automatically extracted from conversation by the agent."""

    MANUAL = "manual"
    """Memory manually added by a user via the Memory UI."""


class FeedbackType(str, Enum):
    """Types of feedback that can be submitted for a memory."""

    THUMBS_UP = "thumbs_up"
    """Positive feedback indicating the memory was helpful."""

    THUMBS_DOWN = "thumbs_down"
    """Negative feedback indicating the memory was not helpful."""

    RESOLUTION_SUCCESS = "resolution_success"
    """Feedback indicating the memory successfully helped resolve an issue."""

    RESOLUTION_FAILURE = "resolution_failure"
    """Feedback indicating the memory failed to help resolve an issue."""


class EntityType(str, Enum):
    """Types of entities that can be extracted from memories."""

    PRODUCT = "product"
    """A product or service referenced in the memory."""

    FEATURE = "feature"
    """A specific feature of a product or service."""

    ISSUE = "issue"
    """A problem or issue described in the memory."""

    SOLUTION = "solution"
    """A resolution or fix for an issue."""

    CUSTOMER = "customer"
    """A customer or user type."""

    PLATFORM = "platform"
    """An operating system or platform (Windows, macOS, iOS, etc.)."""

    VERSION = "version"
    """A version number or release identifier."""

    ERROR = "error"
    """A specific error code/message or error category."""


class RelationshipType(str, Enum):
    """Types of relationships between entities."""

    RESOLVED_BY = "RESOLVED_BY"
    """The source entity (issue) is resolved by the target entity (solution)."""

    AFFECTS = "AFFECTS"
    """The source entity affects the target entity."""

    REQUIRES = "REQUIRES"
    """The source entity requires the target entity."""

    CAUSED_BY = "CAUSED_BY"
    """The source entity (issue) is caused by the target entity."""

    REPORTED_BY = "REPORTED_BY"
    """The source entity (issue) was reported by the target entity (customer)."""

    WORKS_ON = "WORKS_ON"
    """The source entity (solution) works on the target entity (platform)."""

    RELATED_TO = "RELATED_TO"
    """General relationship between entities."""

    SUPERSEDES = "SUPERSEDES"
    """The source entity supersedes or replaces the target entity."""


class ExportFormat(str, Enum):
    """Supported export formats for memories."""

    JSON = "json"
    """Export as JSON format."""


# =============================================================================
# Auth / Meta Schemas
# =============================================================================


class MemoryMeResponse(BaseModel):
    """Identity/role info for the Memory UI."""

    sub: Optional[str] = Field(default=None, description="User ID (subject).")
    roles: List[str] = Field(default_factory=list, description="Roles for the user.")
    is_admin: bool = Field(default=False, description="Whether the user is an admin.")


# =============================================================================
# Request Schemas
# =============================================================================


class AddMemoryRequest(BaseModel):
    """
    Request schema for adding a new memory to the system.

    This is used when manually adding memories via the Memory UI or
    when programmatically adding memories from external sources.
    """

    content: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="The memory content text. Will be embedded using Gemini embeddings (3072-dim).",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata to attach to the memory (e.g., source URL, tags, context).",
    )
    source_type: Literal["auto_extracted", "manual"] = Field(
        default="manual",
        description="How the memory was created. 'manual' for UI additions, 'auto_extracted' for agent-generated.",
    )
    agent_id: str = Field(
        default="primary", description="The agent ID this memory belongs to."
    )
    tenant_id: str = Field(
        default="mailbot", description="The tenant ID for multi-tenant isolation."
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Ensure content is not empty or whitespace-only."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Content cannot be empty or whitespace-only")
        return stripped

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "content": "To resolve IMAP sync issues, users should check their server settings and ensure port 993 is open.",
                "metadata": {"source": "support_ticket", "ticket_id": "12345"},
                "source_type": "manual",
                "agent_id": "primary",
                "tenant_id": "mailbot",
            }
        }
    )


class UpdateMemoryRequest(BaseModel):
    """
    Request schema for updating an existing memory.

    At least one field must be provided. Content updates will trigger
    re-embedding of the memory.
    """

    content: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=50000,
        description="Updated memory content. If provided, the embedding will be regenerated.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Updated metadata. Replaces existing metadata entirely if provided.",
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: Optional[str]) -> Optional[str]:
        """Ensure content is not empty or whitespace-only if provided."""
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Content cannot be empty or whitespace-only")
            return stripped
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "content": "Updated: To resolve IMAP sync issues on macOS, users should check System Preferences > Network.",
                "metadata": {
                    "source": "support_ticket",
                    "ticket_id": "12345",
                    "updated": True,
                },
            }
        }
    )


class UpdateRelationshipRequest(BaseModel):
    """Request schema for updating relationship metadata (admin-only)."""

    source_entity_id: UUID = Field(
        ...,
        description="Source entity ID (UUID).",
    )
    target_entity_id: UUID = Field(
        ...,
        description="Target entity ID (UUID).",
    )
    relationship_type: RelationshipType = Field(
        ...,
        description="Relationship type.",
    )
    weight: float = Field(
        ...,
        ge=0,
        le=10,
        description="Relationship strength 0-10.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source_entity_id": "00000000-0000-0000-0000-000000000001",
                "target_entity_id": "00000000-0000-0000-0000-000000000002",
                "relationship_type": "RELATED_TO",
                "weight": 4.2,
            }
        }
    )


class MergeRelationshipsRequest(BaseModel):
    """Request schema for merging multiple relationships into one (admin-only)."""

    relationship_ids: List[UUID] = Field(
        ...,
        min_length=2,
        description="Relationship IDs to merge (2+). These will be merged destructively.",
    )
    source_entity_id: UUID = Field(
        ..., description="Merged relationship source entity ID."
    )
    target_entity_id: UUID = Field(
        ..., description="Merged relationship target entity ID."
    )
    relationship_type: RelationshipType = Field(
        ..., description="Merged relationship type."
    )
    weight: float = Field(
        ...,
        ge=0,
        le=10,
        description="Merged relationship weight 0-10.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "relationship_ids": [
                    "550e8400-e29b-41d4-a716-446655440000",
                    "550e8400-e29b-41d4-a716-446655440001",
                ],
                "source_entity_id": "00000000-0000-0000-0000-000000000001",
                "target_entity_id": "00000000-0000-0000-0000-000000000002",
                "relationship_type": "RELATED_TO",
                "weight": 3.2,
            }
        }
    )


class SplitRelationshipPreviewRequest(BaseModel):
    """Request schema for AI-assisted split preview (admin-only)."""

    max_memories: int = Field(
        default=60,
        ge=1,
        le=250,
        description="Maximum number of distinct memories to consider for clustering.",
    )
    max_clusters: int = Field(
        default=4,
        ge=2,
        le=8,
        description="Maximum number of clusters to try when choosing k.",
    )
    cluster_count: Optional[int] = Field(
        default=None,
        ge=2,
        le=8,
        description="Optional fixed cluster count (overrides auto selection).",
    )
    samples_per_cluster: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Number of memory samples to include per cluster.",
    )
    use_ai: bool = Field(
        default=True,
        description="If true and an LLM is configured, enrich clusters with AI labels.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "max_memories": 60,
                "max_clusters": 4,
                "cluster_count": None,
                "samples_per_cluster": 3,
                "use_ai": True,
            }
        }
    )


class SplitRelationshipCommitCluster(BaseModel):
    """Cluster definition for split commit (admin-only)."""

    name: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Human-readable cluster label (not persisted).",
    )
    source_entity_id: UUID = Field(
        ..., description="Cluster relationship source entity ID."
    )
    target_entity_id: UUID = Field(
        ..., description="Cluster relationship target entity ID."
    )
    relationship_type: RelationshipType = Field(
        ..., description="Cluster relationship type."
    )
    weight: float = Field(
        ..., ge=0, le=10, description="Cluster relationship weight 0-10."
    )
    memory_ids: List[UUID] = Field(
        ...,
        min_length=1,
        description="Memory IDs supporting this cluster (used to compute occurrence_count).",
    )


class SplitRelationshipCommitRequest(BaseModel):
    """Request schema for split commit (admin-only)."""

    clusters: List[SplitRelationshipCommitCluster] = Field(
        ...,
        min_length=1,
        description="Clusters to commit as relationships.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "clusters": [
                    {
                        "name": "Fix steps",
                        "source_entity_id": "00000000-0000-0000-0000-000000000001",
                        "target_entity_id": "00000000-0000-0000-0000-000000000002",
                        "relationship_type": "RESOLVED_BY",
                        "weight": 6.5,
                        "memory_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                    }
                ]
            }
        }
    )


class MergeMemoriesRequest(BaseModel):
    """
    Request schema for merging duplicate memories.

    Used when the duplicate detection system identifies two memories as potential
    duplicates and a user chooses to merge them.
    """

    duplicate_candidate_id: UUID = Field(
        ...,
        description="ID of the duplicate candidate record from memory_duplicate_candidates table.",
    )
    keep_memory_id: UUID = Field(
        ...,
        description="ID of the memory to keep (the 'primary' memory that will absorb the other).",
    )
    merge_content: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="Optional merged content. If not provided, the kept memory's content is preserved.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "duplicate_candidate_id": "550e8400-e29b-41d4-a716-446655440000",
                "keep_memory_id": "550e8400-e29b-41d4-a716-446655440001",
                "merge_content": "Combined knowledge about IMAP sync issues and their resolutions.",
            }
        }
    )


class MergeMemoriesArbitraryRequest(BaseModel):
    """Request schema for merging an explicit list of memory IDs into one."""

    keep_memory_id: UUID = Field(..., description="ID of the memory to keep.")
    merge_memory_ids: List[UUID] = Field(
        ...,
        min_length=1,
        description="Memory IDs to merge into keep_memory_id (these will be deleted).",
    )
    merge_content: Optional[str] = Field(
        default=None,
        max_length=50000,
        description=(
            "Optional merged content to store on keep_memory_id. "
            "If omitted, the keep memory's content is preserved."
        ),
    )


class SubmitFeedbackRequest(BaseModel):
    """
    Request schema for submitting feedback on a memory.

    Feedback affects the memory's confidence score and helps improve
    the quality of agent responses over time.
    """

    feedback_type: Literal[
        "thumbs_up", "thumbs_down", "resolution_success", "resolution_failure"
    ] = Field(..., description="Type of feedback being submitted.")
    session_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="ID of the chat session where this feedback was given.",
    )
    ticket_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="ID of the support ticket associated with this feedback.",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Optional notes or comments explaining the feedback.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "feedback_type": "resolution_success",
                "session_id": "session-12345",
                "ticket_id": "TICKET-67890",
                "notes": "This memory helped resolve the customer's issue on first contact.",
            }
        }
    )


class ExportFilters(BaseModel):
    """
    Filter options for memory exports.

    All filters are optional and can be combined to narrow down the export.
    """

    entity_types: Optional[List[str]] = Field(
        default=None,
        description="Filter to only include memories with entities of these types.",
    )
    min_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score threshold (0.0 to 1.0).",
    )
    created_after: Optional[datetime] = Field(
        default=None, description="Only include memories created after this timestamp."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entity_types": ["issue", "solution"],
                "min_confidence": 0.7,
                "created_after": "2025-01-01T00:00:00Z",
            }
        }
    )


class ExportMemoriesRequest(BaseModel):
    """
    Request schema for exporting memories.

    Creates an async export job that generates a downloadable file.
    """

    format: Literal["json"] = Field(
        default="json", description="Export format. Currently only JSON is supported."
    )
    filters: Optional[ExportFilters] = Field(
        default=None, description="Optional filters to apply to the export."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "format": "json",
                "filters": {
                    "entity_types": ["issue", "solution"],
                    "min_confidence": 0.5,
                },
            }
        }
    )


class DismissDuplicateRequest(BaseModel):
    """
    Request schema for dismissing a duplicate candidate.

    Used when a user determines that two memories are not actually duplicates.
    """

    notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Optional notes explaining why this is not a duplicate.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "notes": "These memories describe different issues despite similar wording."
            }
        }
    )


# =============================================================================
# Response Schemas
# =============================================================================


class AddMemoryResponse(BaseModel):
    """
    Response schema for successfully adding a memory.

    Includes information about entities and relationships that were
    automatically extracted from the memory content.
    """

    id: UUID = Field(..., description="Unique identifier of the created memory.")
    content: str = Field(..., description="The memory content that was stored.")
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Initial confidence score (typically 0.5 for new memories).",
    )
    source_type: str = Field(
        ..., description="How the memory was created ('manual' or 'auto_extracted')."
    )
    entities_extracted: int = Field(
        ...,
        ge=0,
        description="Number of entities automatically extracted from the content.",
    )
    relationships_created: int = Field(
        ...,
        ge=0,
        description="Number of relationships created between extracted entities.",
    )
    created_at: datetime = Field(
        ..., description="Timestamp when the memory was created."
    )

    model_config = ConfigDict(from_attributes=True)


class UpdateMemoryResponse(BaseModel):
    """Response schema for successfully updating a memory."""

    id: UUID = Field(..., description="Unique identifier of the updated memory.")
    content: str = Field(..., description="The updated memory content.")
    updated_at: datetime = Field(
        ..., description="Timestamp when the memory was last updated."
    )

    model_config = ConfigDict(from_attributes=True)


class DeleteMemoryResponse(BaseModel):
    """
    Response schema for successfully deleting a memory.

    Includes cleanup statistics for related entities and relationships.
    """

    deleted: bool = Field(
        ..., description="Whether the memory was successfully deleted."
    )
    entities_orphaned: int = Field(
        ...,
        ge=0,
        description="Number of entities that became orphaned (no longer connected to any memory).",
    )
    relationships_removed: int = Field(
        ...,
        ge=0,
        description="Number of relationships that were removed with the memory.",
    )

    model_config = ConfigDict(from_attributes=True)


class MergeMemoriesResponse(BaseModel):
    """
    Response schema for successfully merging memories.

    One memory is kept (potentially with merged content) and the other is deleted.
    """

    merged_memory_id: UUID = Field(
        ..., description="ID of the memory that was kept after the merge."
    )
    deleted_memory_id: UUID = Field(
        ..., description="ID of the memory that was deleted during the merge."
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Updated confidence score of the merged memory.",
    )
    entities_transferred: int = Field(
        ...,
        ge=0,
        description="Number of entities transferred from the deleted memory to the kept memory.",
    )

    model_config = ConfigDict(from_attributes=True)


class MergeMemoriesArbitraryResponse(BaseModel):
    """Response schema for merging multiple explicit memories into one."""

    merged_memory_id: UUID = Field(..., description="ID of the memory that was kept.")
    deleted_memory_ids: List[UUID] = Field(
        default_factory=list,
        description="IDs of memories that were merged and deleted.",
    )
    duplicate_candidate_ids: List[UUID] = Field(
        default_factory=list,
        description="Duplicate candidate IDs created/used to perform the merges.",
    )
    confidence_score: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Updated confidence score reported by the merge function (best-effort).",
    )
    entities_transferred: int = Field(
        default=0,
        ge=0,
        description="Total entities transferred across merges (best-effort).",
    )

    model_config = ConfigDict(from_attributes=True)


class SubmitFeedbackResponse(BaseModel):
    """
    Response schema for successfully submitting feedback.

    Feedback is recorded and the memory's confidence score is updated accordingly.
    """

    feedback_id: UUID = Field(
        ..., description="Unique identifier of the created feedback record."
    )
    new_confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="The memory's updated confidence score after applying the feedback.",
    )

    model_config = ConfigDict(from_attributes=True)


class ExportMemoriesResponse(BaseModel):
    """
    Response schema for initiating a memory export.

    The export is processed asynchronously. Use the download_url to retrieve
    the file once it's ready.
    """

    export_id: UUID = Field(..., description="Unique identifier of the export job.")
    download_url: str = Field(
        ...,
        description="URL to download the export file (available when processing completes).",
    )
    memory_count: int = Field(
        ..., ge=0, description="Number of memories included in the export."
    )
    entity_count: int = Field(
        ..., ge=0, description="Number of entities included in the export."
    )
    relationship_count: int = Field(
        ..., ge=0, description="Number of relationships included in the export."
    )

    model_config = ConfigDict(from_attributes=True)


class DismissDuplicateResponse(BaseModel):
    """Response schema for successfully dismissing a duplicate candidate."""

    candidate_id: UUID = Field(
        ..., description="ID of the duplicate candidate that was dismissed."
    )
    status: str = Field(
        ...,
        description="New status of the duplicate candidate (typically 'dismissed').",
    )

    model_config = ConfigDict(from_attributes=True)


class MemoryStatsResponse(BaseModel):
    """
    Response schema for memory system statistics.

    Provides an overview of the memory system's current state including
    counts, confidence distribution, and entity/relationship type breakdowns.
    """

    # Count statistics
    total_memories: int = Field(
        ..., ge=0, description="Total number of memories in the system."
    )
    total_entities: int = Field(
        ..., ge=0, description="Total number of extracted entities."
    )
    total_relationships: int = Field(
        ..., ge=0, description="Total number of entity relationships."
    )
    pending_duplicates: int = Field(
        ..., ge=0, description="Number of duplicate candidates awaiting review."
    )

    # Confidence distribution
    high_confidence: int = Field(
        ..., ge=0, description="Number of memories with confidence >= 0.7."
    )
    medium_confidence: int = Field(
        ..., ge=0, description="Number of memories with confidence >= 0.4 and < 0.7."
    )
    low_confidence: int = Field(
        ..., ge=0, description="Number of memories with confidence < 0.4."
    )

    # Type breakdowns
    entity_types: Dict[str, int] = Field(
        ...,
        description="Count of entities by type (e.g., {'issue': 50, 'solution': 45}).",
    )
    relationship_types: Dict[str, int] = Field(
        ...,
        description="Count of relationships by type (e.g., {'RESOLVED_BY': 30, 'AFFECTS': 20}).",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "total_memories": 1250,
                "total_entities": 3420,
                "total_relationships": 1890,
                "pending_duplicates": 15,
                "high_confidence": 890,
                "medium_confidence": 280,
                "low_confidence": 80,
                "entity_types": {
                    "issue": 520,
                    "solution": 480,
                    "product": 350,
                    "feature": 290,
                    "error": 180,
                },
                "relationship_types": {
                    "RESOLVED_BY": 450,
                    "AFFECTS": 380,
                    "RELATED_TO": 520,
                    "CAUSED_BY": 210,
                },
            }
        },
    )


class MemoryRecord(BaseModel):
    """Read model for Memory UI records (excludes embeddings)."""

    id: UUID
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source_type: str
    review_status: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    confidence_score: float
    retrieval_count: int
    last_retrieved_at: Optional[datetime] = None
    feedback_positive: int
    feedback_negative: int
    resolution_success_count: int
    resolution_failure_count: int
    agent_id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemoryListResponse(BaseModel):
    """Paginated response for memory list endpoints."""

    items: List[MemoryRecord] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class MemoryEntityRecord(BaseModel):
    """Read model for memory_entities rows."""

    id: UUID
    entity_type: EntityType
    entity_name: str
    normalized_name: str
    display_label: Optional[str] = None
    first_seen_at: datetime
    last_seen_at: datetime
    last_modified_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    occurrence_count: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GraphNodeRecord(BaseModel):
    """Read model for graph node payloads (frontend-friendly field names)."""

    id: UUID
    entityType: EntityType
    entityName: str
    displayLabel: str
    occurrenceCount: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
    firstSeenAt: Optional[datetime] = None
    lastSeenAt: Optional[datetime] = None
    acknowledgedAt: Optional[datetime] = None
    lastModifiedAt: Optional[datetime] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    color: Optional[str] = None
    size: Optional[float] = None
    hasEditedMemory: bool = False
    editedMemoryCount: int = 0


class GraphLinkRecord(BaseModel):
    """Read model for graph link payloads (frontend-friendly field names)."""

    id: UUID
    source: UUID
    target: UUID
    relationshipType: RelationshipType
    weight: float
    occurrenceCount: int
    acknowledgedAt: Optional[datetime] = None
    lastModifiedAt: Optional[datetime] = None
    hasEditedProvenance: bool = False


class GraphDataResponse(BaseModel):
    """Graph payload with enriched edit provenance metadata."""

    nodes: List[GraphNodeRecord] = Field(default_factory=list)
    links: List[GraphLinkRecord] = Field(default_factory=list)


class MemoryRelationshipRecord(BaseModel):
    """Read model for memory_relationships rows."""

    id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relationship_type: RelationshipType
    weight: float
    occurrence_count: int
    source_memory_id: Optional[UUID] = None
    first_seen_at: datetime
    last_seen_at: datetime
    last_modified_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MergeRelationshipsResponse(BaseModel):
    """Response schema for merging relationships (admin-only)."""

    merged_relationship: MemoryRelationshipRecord = Field(
        ...,
        description="The merged relationship record that remains after the operation.",
    )
    deleted_relationship_ids: List[UUID] = Field(
        ...,
        description="Relationship IDs deleted during the merge.",
    )


class DeleteRelationshipResponse(BaseModel):
    """Response schema for deleting a relationship (admin-only)."""

    deleted: bool = Field(..., description="Whether the relationship was deleted.")
    relationship_id: UUID = Field(..., description="Relationship ID that was deleted.")


class SplitRelationshipClusterSample(BaseModel):
    """Lightweight memory sample shown in split preview UI (excludes embeddings)."""

    id: UUID
    content_preview: str = Field(
        ...,
        description="Truncated memory content preview for review.",
    )
    confidence_score: Optional[float] = None
    created_at: Optional[datetime] = None


class SplitRelationshipClusterSuggestion(BaseModel):
    """AI (or heuristic) suggestion for a cluster of memories supporting an edge."""

    cluster_id: int = Field(..., ge=0)
    name: str = Field(..., max_length=120)
    source_entity_id: UUID
    target_entity_id: UUID
    relationship_type: RelationshipType
    weight: float = Field(..., ge=0, le=10)
    occurrence_count: int = Field(..., ge=1)
    memory_ids: List[UUID] = Field(default_factory=list)
    samples: List[SplitRelationshipClusterSample] = Field(default_factory=list)


class SplitRelationshipPreviewResponse(BaseModel):
    """Response schema for split preview (admin-only)."""

    relationship_id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    existing_relationship_ids: List[UUID] = Field(
        default_factory=list,
        description="Existing relationship IDs connecting the entity pair.",
    )
    clusters: List[SplitRelationshipClusterSuggestion] = Field(default_factory=list)
    used_ai: bool = Field(
        default=False,
        description="Whether an LLM was used to generate the labels.",
    )
    ai_model_id: Optional[str] = Field(
        default=None,
        description="LLM model ID used for enrichment (when used_ai is true).",
    )
    ai_error: Optional[str] = Field(
        default=None,
        description="High-level reason AI enrichment was skipped/failed.",
    )


class RelationshipAnalysisRequest(BaseModel):
    """Request schema for relationship analysis (admin-only)."""

    max_direct_memories: int = Field(
        default=40,
        ge=1,
        le=120,
        description="Max provenance memories to analyze from the selected edge.",
    )
    max_neighbor_edges: int = Field(
        default=6,
        ge=0,
        le=20,
        description="Max neighbor edges to include per endpoint entity.",
    )
    max_neighbor_memories: int = Field(
        default=18,
        ge=0,
        le=80,
        description="Max provenance memories to include from neighbor edges.",
    )
    use_ai: bool = Field(
        default=True,
        description="Whether to call an LLM for analysis (falls back to heuristic summary when disabled).",
    )


class RelationshipChecklistItem(BaseModel):
    """A single checklist item used to review/improve a relationship."""

    id: str = Field(
        ...,
        description="Stable identifier for the checklist item (unique within this analysis).",
        min_length=1,
        max_length=64,
    )
    title: str = Field(
        ...,
        description="Short, human-friendly checkbox label.",
        min_length=1,
        max_length=140,
    )
    category: str = Field(
        ...,
        description="Checklist category (e.g., evidence, direction, type, hygiene).",
        min_length=1,
        max_length=32,
    )
    why: Optional[str] = Field(
        default=None,
        description="Optional rationale shown under the checkbox.",
        max_length=420,
    )
    memory_ids: List[UUID] = Field(
        default_factory=list,
        description="Optional memory IDs referenced by this checklist item (evidence to review).",
    )
    entity_ids: List[UUID] = Field(
        default_factory=list,
        description="Optional entity IDs referenced by this checklist item (nodes to inspect).",
    )


class RelationshipSuggestedAction(BaseModel):
    """A single suggested, executable action for relationship/memory hygiene."""

    id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=180)
    kind: Literal[
        "update_relationship",
        "merge_relationships",
        "split_relationship_commit",
        "update_memory",
        "delete_memory",
        "merge_memories_arbitrary",
        "delete_relationship",
    ] = Field(..., description="Action kind (discriminant).")
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    destructive: bool = Field(default=False)
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Action payload; schema depends on `kind`.",
    )
    memory_ids: List[UUID] = Field(default_factory=list)
    entity_ids: List[UUID] = Field(default_factory=list)
    relationship_ids: List[UUID] = Field(default_factory=list)


class RelationshipAnalysisResponse(BaseModel):
    """Response schema for relationship analysis (admin-only)."""

    relationship_id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    checklist: List[RelationshipChecklistItem] = Field(
        default_factory=list,
        description="AI-generated review checklist for this relationship.",
    )
    analysis_markdown: str = Field(
        ...,
        description="Artifact-style analysis rendered as Markdown.",
    )
    used_ai: bool = Field(
        default=False,
        description="Whether an LLM was used to produce analysis_markdown.",
    )
    ai_model_id: Optional[str] = Field(
        default=None,
        description="LLM model ID used for analysis (when used_ai is true).",
    )
    ai_error: Optional[str] = Field(
        default=None,
        description="High-level reason AI analysis was skipped/failed.",
    )
    direct_memory_count: int = Field(
        default=0,
        description="Number of direct provenance memories included in the prompt.",
    )
    neighbor_edge_count: int = Field(
        default=0,
        description="Number of neighbor edges included in the prompt.",
    )
    neighbor_memory_count: int = Field(
        default=0,
        description="Number of neighbor-edge memories included in the prompt.",
    )
    actions: List[RelationshipSuggestedAction] = Field(
        default_factory=list,
        description="Suggested executable actions derived from the analysis.",
    )


class SplitRelationshipCommitResponse(BaseModel):
    """Response schema for split commit (admin-only)."""

    source_entity_id: UUID
    target_entity_id: UUID
    deleted_relationship_ids: List[UUID] = Field(default_factory=list)
    created_relationships: List[MemoryRelationshipRecord] = Field(default_factory=list)


class DuplicateCandidateRecord(BaseModel):
    """Read model for duplicate candidates (optionally expanded with memories)."""

    id: UUID
    memory_id_1: Optional[UUID] = None
    memory_id_2: Optional[UUID] = None
    similarity_score: float
    status: str
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    merge_target_id: Optional[UUID] = None
    detected_at: datetime
    detection_method: str
    notes: Optional[str] = None
    created_at: datetime

    memory1: Optional[MemoryRecord] = None
    memory2: Optional[MemoryRecord] = None

    model_config = ConfigDict(from_attributes=True)


class ImportMemorySourcesRequest(BaseModel):
    """Admin request to backfill Memory UI from existing knowledge sources."""

    include_issue_resolutions: bool = Field(
        default=True,
        description="Import rows from the issue_resolutions pattern store.",
    )
    include_playbook_entries: bool = Field(
        default=True,
        description="Import rows from playbook_learned_entries (pending/approved).",
    )
    include_playbook_files: bool = Field(
        default=False,
        description="Import workspace /playbooks/* files from the LangGraph store table.",
    )
    playbook_statuses: Optional[List[str]] = Field(
        default=None,
        description="Optional status filter (e.g., ['approved','pending_review']). Defaults to approved+pending_review.",
    )
    limit: int = Field(
        default=200,
        ge=1,
        le=2000,
        description="Max rows to import per source (ordered by created_at desc).",
    )
    include_playbook_embeddings: bool = Field(
        default=False,
        description="If true, generate embeddings for imported playbook entries (costly).",
    )
    include_mem0_primary: bool = Field(
        default=False,
        description=(
            "Import existing mem0 primary facts into the Memory UI schema for admin review "
            "(no embeddings; uses deterministic UUIDs)."
        ),
    )


class ImportMemorySourcesResponse(BaseModel):
    """Counts returned from an import run."""

    issue_resolutions_imported: int = Field(default=0, ge=0)
    issue_resolutions_skipped: int = Field(default=0, ge=0)
    issue_resolutions_failed: int = Field(default=0, ge=0)

    playbook_entries_imported: int = Field(default=0, ge=0)
    playbook_entries_skipped: int = Field(default=0, ge=0)
    playbook_entries_failed: int = Field(default=0, ge=0)

    playbook_files_imported: int = Field(default=0, ge=0)
    playbook_files_skipped: int = Field(default=0, ge=0)
    playbook_files_failed: int = Field(default=0, ge=0)

    mem0_primary_imported: int = Field(default=0, ge=0)
    mem0_primary_skipped: int = Field(default=0, ge=0)
    mem0_primary_failed: int = Field(default=0, ge=0)


class ImportZendeskTaggedRequest(BaseModel):
    """Admin request to queue Zendesk ticket ingestion for Memory UI."""

    tag: str = Field(
        default="mb_playbook",
        description="Zendesk tag to filter tickets for ingestion.",
    )
    limit: int = Field(
        default=200,
        ge=1,
        le=2000,
        description="Max tickets to enqueue for processing.",
    )


class BackfillZendeskMemoriesV2Request(BaseModel):
    """Admin request to queue V2 backfill for existing unedited Zendesk memories."""

    limit: int = Field(
        default=5000,
        ge=1,
        le=50000,
        description="Maximum memories to scan during this backfill run.",
    )
    dry_run: bool = Field(
        default=False,
        description="If true, only report candidate counts without writing updates.",
    )
    created_at_from: Optional[datetime] = Field(
        default=None,
        description=(
            "Optional lower-bound (inclusive) filter for memory created_at timestamps. "
            "Use UTC for deterministic date windows."
        ),
    )
    created_at_to: Optional[datetime] = Field(
        default=None,
        description=(
            "Optional upper-bound (exclusive) filter for memory created_at timestamps. "
            "Use UTC for deterministic date windows."
        ),
    )
    reprocess_mode: Literal["live_zendesk_refetch", "metadata_only"] = Field(
        default="live_zendesk_refetch",
        description=(
            "Backfill strategy. live_zendesk_refetch performs ticket re-fetch + re-summary; "
            "metadata_only reuses persisted memory metadata."
        ),
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> "BackfillZendeskMemoriesV2Request":
        if self.created_at_from and self.created_at_to:
            if self.created_at_from >= self.created_at_to:
                raise ValueError("created_at_from must be earlier than created_at_to")
        return self


class ImportZendeskTaggedResponse(BaseModel):
    """Response for queued Zendesk import task."""

    queued: bool = Field(default=True)
    task_id: Optional[str] = Field(default=None)
    message: str = Field(default="Zendesk import queued")
    status_url: Optional[str] = Field(
        default=None,
        description="Optional endpoint path to poll the queued import task status.",
    )


class ImportZendeskTaggedTaskResult(BaseModel):
    """Normalized result payload for a completed Zendesk import task."""

    imported: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    tag: str = Field(default="mb_playbook")
    processed_tickets: int = Field(default=0, ge=0)
    imported_memory_ids: List[str] = Field(default_factory=list)
    failed_ticket_ids: List[str] = Field(default_factory=list)
    failure_reasons: Dict[str, str] = Field(default_factory=dict)
    candidate_memory_ids: List[str] = Field(default_factory=list)
    updated_memory_ids: List[str] = Field(default_factory=list)
    skipped_memory_ids: List[str] = Field(default_factory=list)
    failed_memory_ids: List[str] = Field(default_factory=list)
    would_update_memory_ids: List[str] = Field(default_factory=list)
    eligible: Optional[int] = Field(default=None, ge=0)
    dry_run: Optional[bool] = Field(default=None)
    scan_limit: Optional[int] = Field(default=None, ge=0)
    would_update: Optional[int] = Field(default=None, ge=0)
    reprocess_mode: Optional[str] = Field(default=None)
    created_at_from: Optional[str] = Field(default=None)
    created_at_to: Optional[str] = Field(default=None)
    run_id: Optional[str] = Field(default=None)


class ImportZendeskTaggedTaskStatusResponse(BaseModel):
    """Task status payload for queued Zendesk tagged imports."""

    task_id: str
    status: str = Field(default="PENDING")
    ready: bool = Field(default=False)
    successful: bool = Field(default=False)
    failed: bool = Field(default=False)
    message: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)
    result: Optional[ImportZendeskTaggedTaskResult] = Field(default=None)
