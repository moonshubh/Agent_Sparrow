"""
FeedMe Local Schemas

Local request/response models specific to the FeedMe endpoints module.
Core schemas are imported from app.feedme.schemas.
"""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator


class FeedMeFolder(BaseModel):
    """Folder for organizing conversations."""

    id: int
    name: str
    color: str
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    conversation_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class FolderCreate(BaseModel):
    """Request model for creating a folder."""

    name: str
    color: str = "#0095ff"
    description: Optional[str] = None
    created_by: Optional[str] = None


class FolderUpdate(BaseModel):
    """Request model for updating a folder."""

    name: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None


class AssignFolderRequest(BaseModel):
    """Request model for assigning conversations to a folder."""

    folder_id: Optional[int] = None  # None to remove from folder
    conversation_ids: List[int]

    @field_validator("conversation_ids")
    def validate_conversation_ids(cls, values: List[int]) -> List[int]:
        if not values:
            raise ValueError("At least one conversation id is required")
        if len(values) > 50:
            raise ValueError("Maximum 50 conversation ids can be assigned per request")
        return values


class FolderListResponse(BaseModel):
    """Response model for listing folders."""

    folders: List[FeedMeFolder]
    total_count: int


class SupabaseApprovalRequest(BaseModel):
    """Request model for Supabase-based approval."""

    approved_by: str
    example_ids: Optional[List[int]] = None  # None means all examples
    reviewer_notes: Optional[str] = None
