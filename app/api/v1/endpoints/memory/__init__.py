"""
Memory UI API Endpoints Package

This package provides endpoints for memory management operations
including CRUD operations, feedback submission, and admin actions.

Database tables:
- memories: Core memory storage with content, embedding (3072-dim), confidence_score
- memory_entities: Extracted entities (product, feature, issue, solution, etc.)
- memory_relationships: Entity relationships (RESOLVED_BY, AFFECTS, etc.)
- memory_duplicate_candidates: Duplicate detection queue
- memory_feedback: User feedback tracking

Endpoints:
- POST /add - Add new memory (authenticated)
- PUT /{memory_id} - Update memory (admin only)
- DELETE /{memory_id} - Delete memory (admin only)
- POST /merge - Merge duplicate memories (admin only)
- POST /{memory_id}/feedback - Submit feedback (authenticated)
- PUT /relationships/{relationship_id} - Update relationship metadata (admin only)
- POST /relationships/merge - Merge relationships (admin only)
- POST /relationships/{relationship_id}/split/preview - Preview relationship split (admin only)
- POST /relationships/{relationship_id}/split/commit - Commit relationship split (admin only)
- POST /entities/{entity_id}/acknowledge - Mark entity as reviewed (authenticated)
- POST /relationships/{relationship_id}/acknowledge - Mark relationship as reviewed (authenticated)
- POST /export - Export memories (admin only)
- POST /duplicate/{candidate_id}/dismiss - Dismiss duplicate (admin only)
- GET /stats - Get memory statistics (authenticated)

Usage:
    from app.api.v1.endpoints.memory import router
    app.include_router(router, prefix="/api/v1/memory")
"""

from fastapi import APIRouter

# Import the router from endpoints module
from .endpoints import router as memory_router

# Re-export schemas for convenient imports
from .schemas import (
    # Request schemas
    AddMemoryRequest,
    UpdateMemoryRequest,
    UpdateRelationshipRequest,
    MergeRelationshipsRequest,
    SplitRelationshipPreviewRequest,
    SplitRelationshipCommitRequest,
    MergeMemoriesRequest,
    SubmitFeedbackRequest,
    ExportMemoriesRequest,
    ExportFilters,
    DismissDuplicateRequest,
    # Response schemas
    AddMemoryResponse,
    UpdateMemoryResponse,
    DeleteMemoryResponse,
    MergeRelationshipsResponse,
    SplitRelationshipPreviewResponse,
    SplitRelationshipCommitResponse,
    MergeMemoriesResponse,
    SubmitFeedbackResponse,
    ExportMemoriesResponse,
    DismissDuplicateResponse,
    MemoryStatsResponse,
    # Enums
    SourceType,
    FeedbackType,
    EntityType,
    RelationshipType,
    ExportFormat,
)

# Create main router with prefix
router = APIRouter(
    prefix="/memory",
    tags=["memory"],
    responses={
        400: {"description": "Bad request - Invalid input"},
        401: {"description": "Unauthorized - Authentication required"},
        403: {"description": "Forbidden - Admin access required"},
        404: {"description": "Not found"},
        500: {"description": "Internal server error"},
    },
)

# Include the endpoints router
router.include_router(memory_router)

__all__ = [
    # Router
    "router",
    # Request schemas
    "AddMemoryRequest",
    "UpdateMemoryRequest",
    "UpdateRelationshipRequest",
    "MergeRelationshipsRequest",
    "SplitRelationshipPreviewRequest",
    "SplitRelationshipCommitRequest",
    "MergeMemoriesRequest",
    "SubmitFeedbackRequest",
    "ExportMemoriesRequest",
    "ExportFilters",
    "DismissDuplicateRequest",
    # Response schemas
    "AddMemoryResponse",
    "UpdateMemoryResponse",
    "DeleteMemoryResponse",
    "MergeRelationshipsResponse",
    "SplitRelationshipPreviewResponse",
    "SplitRelationshipCommitResponse",
    "MergeMemoriesResponse",
    "SubmitFeedbackResponse",
    "ExportMemoriesResponse",
    "DismissDuplicateResponse",
    "MemoryStatsResponse",
    # Enums
    "SourceType",
    "FeedbackType",
    "EntityType",
    "RelationshipType",
    "ExportFormat",
]
