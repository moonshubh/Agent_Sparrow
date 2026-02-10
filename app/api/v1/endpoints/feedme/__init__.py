"""
FeedMe API Endpoints Package

This package consolidates all FeedMe-related endpoints for customer support
transcript ingestion, processing, and management.

Modules:
- ingestion: File upload and processing initiation
- conversations: Conversations and examples CRUD operations
- versioning: Version control endpoints
- approval: Approval workflow endpoints
- folders: Folder management endpoints
- analytics: Analytics and usage statistics endpoints

Usage:
    from app.api.v1.endpoints.feedme import router
    app.include_router(router, prefix="/api/v1")
"""

from fastapi import APIRouter

from .ingestion import router as ingestion_router
from .conversations import router as conversations_router
from .versioning import router as versioning_router
from .approval import router as approval_router
from .folders import router as folders_router
from .analytics import router as analytics_router
from .workflow import router as workflow_router

# Create main router with prefix
router = APIRouter(
    prefix="/feedme",
    tags=["feedme"],
    responses={
        400: {"description": "Bad request - Invalid input"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden - Feature disabled"},
        413: {"description": "Request entity too large"},
        429: {"description": "Too many requests"},
        500: {"description": "Internal server error"},
    },
)

# Include all sub-routers
router.include_router(ingestion_router)
router.include_router(conversations_router)
router.include_router(versioning_router)
router.include_router(approval_router)
router.include_router(folders_router)
router.include_router(analytics_router)
router.include_router(workflow_router)

# Re-export commonly used items for backward compatibility
from .schemas import (  # noqa: E402
    FeedMeFolder,
    FolderCreate,
    FolderUpdate,
    FolderListResponse,
    AssignFolderRequest,
    SupabaseApprovalRequest,
)
from .helpers import (  # noqa: E402
    get_feedme_supabase_client,
    get_conversation_by_id,
    create_conversation_in_db,
    update_conversation_in_db,
    update_conversation_status,
    supabase_client,
    UNASSIGNED_FOLDER_ID,
)

__all__ = [
    "router",
    # Schemas
    "FeedMeFolder",
    "FolderCreate",
    "FolderUpdate",
    "FolderListResponse",
    "AssignFolderRequest",
    "SupabaseApprovalRequest",
    # Helpers
    "get_feedme_supabase_client",
    "get_conversation_by_id",
    "create_conversation_in_db",
    "update_conversation_in_db",
    "update_conversation_status",
    "supabase_client",
    "UNASSIGNED_FOLDER_ID",
]
