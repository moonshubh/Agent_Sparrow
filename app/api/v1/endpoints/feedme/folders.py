"""
FeedMe Folder Endpoints

Folder management operations for organizing conversations.
"""

import logging
from typing import Any, List, Optional

from postgrest.base_request_builder import CountMethod

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.security import TokenPayload
from app.core.settings import settings
from app.db.supabase.client import get_supabase_client
from app.feedme.security import (
    SecureFolderNameModel,
    SecurityValidator,
    SecurityAuditLogger,
    limiter,
    SECURITY_CONFIG,
)
from app.feedme.schemas import ConversationListResponse, FeedMeConversation

from .schemas import (
    FeedMeFolder,
    FolderCreate,
    FolderUpdate,
    FolderListResponse,
    AssignFolderRequest,
)
from .helpers import (
    get_feedme_settings,
    get_feedme_supabase_client,
    record_feedme_action_audit,
    supabase_client,
)
from .auth import require_feedme_admin

logger = logging.getLogger(__name__)

COUNT_EXACT: CountMethod = CountMethod.exact
audit_logger = SecurityAuditLogger()

router = APIRouter(tags=["FeedMe"])


def _get_client_ip(request: Request) -> str:
    """Safely extract client IP from request, handling proxy scenarios."""
    # Check X-Forwarded-For header first (common with reverse proxies)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()
    # Fall back to direct client connection
    if request.client is not None:
        return request.client.host
    return "unknown"


@router.get("/folders", response_model=FolderListResponse)
async def list_folders():
    """Get all folders with conversation counts."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    client = get_feedme_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=503, detail="FeedMe service is temporarily unavailable."
        )

    try:
        folder_data = await client.get_folders_with_stats()

        folders = []
        for folder_dict in folder_data:
            if folder_dict["id"] is None:
                continue
            folders.append(FeedMeFolder(**folder_dict))

        logger.info(f"Found {len(folders)} folders")

        # Create default folder if none exist
        if not folders:
            try:
                new_folder = await client.insert_folder(
                    name="General",
                    color="#0095ff",
                    description="Default folder for conversations",
                    created_by="system",
                )
                new_folder["conversation_count"] = 0
                folders.append(FeedMeFolder(**new_folder))
            except Exception as e:
                logger.error(f"Failed to create default folder: {e}")

        return FolderListResponse(folders=folders, total_count=len(folders))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing folders: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.post("/folders", response_model=FeedMeFolder)
@limiter.limit("30/minute")
async def create_folder(
    request: Request,
    folder_data: FolderCreate,
    current_user: TokenPayload = Depends(require_feedme_admin),
):
    """Create a new folder for organizing conversations."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    client_ip = _get_client_ip(request)

    try:
        try:
            validated_folder = SecureFolderNameModel(name=folder_data.name)
            folder_data.name = validated_folder.name
        except ValueError as e:
            audit_logger.log_validation_failure(
                "folder_name", folder_data.name, str(e), client_ip
            )
            raise HTTPException(status_code=400, detail=str(e))

        if folder_data.description:
            folder_data.description = SecurityValidator.sanitize_text(
                folder_data.description, strip_html=True
            )[: SECURITY_CONFIG["MAX_DESCRIPTION_LENGTH"]]

        # Attempt insert - let DB unique constraint handle race conditions
        # The pre-check is a courtesy to provide better error messages in common cases
        existing_folders = await supabase_client._exec(
            lambda: supabase_client.client.table("feedme_folders")
            .select("id")
            .eq("name", folder_data.name)
            .execute()
        )

        if existing_folders.data and len(existing_folders.data) > 0:
            raise HTTPException(status_code=409, detail="Folder name already exists")

        try:
            folder_result = await supabase_client.insert_folder(
                name=folder_data.name,
                color=folder_data.color,
                description=folder_data.description,
                created_by=folder_data.created_by,
            )
        except Exception as insert_error:
            # Check for unique constraint violation (race condition)
            error_str = str(insert_error).lower()
            if (
                "unique" in error_str
                or "duplicate" in error_str
                or "23505" in error_str
            ):
                raise HTTPException(
                    status_code=409, detail="Folder name already exists"
                )
            raise

        folder_result["conversation_count"] = 0
        logger.info(f"Created folder: {folder_data.name}")
        await record_feedme_action_audit(
            action="create_folder",
            actor_id=current_user.sub,
            folder_id=folder_result.get("id"),
            after_state=folder_result,
        )
        return FeedMeFolder(**folder_result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating folder: {e}")
        raise HTTPException(status_code=500, detail="Failed to create folder")


@router.put("/folders/{folder_id}", response_model=FeedMeFolder)
async def update_folder(
    folder_id: int,
    folder_data: FolderUpdate,
    current_user: TokenPayload = Depends(require_feedme_admin),
):
    """Update an existing folder's name, color, or description."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        existing_folder_response = await supabase_client._exec(
            lambda: supabase_client.client.table("feedme_folders")
            .select("*")
            .eq("id", folder_id)
            .execute()
        )

        if not existing_folder_response.data or len(existing_folder_response.data) == 0:
            raise HTTPException(status_code=404, detail="Folder not found")

        existing_folder = existing_folder_response.data[0]

        # Validate and sanitize name if provided
        validated_name = None
        if folder_data.name and folder_data.name != existing_folder["name"]:
            try:
                validated_folder = SecureFolderNameModel(name=folder_data.name)
                validated_name = validated_folder.name
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            name_conflict_response = await supabase_client._exec(
                lambda: supabase_client.client.table("feedme_folders")
                .select("id")
                .eq("name", validated_name)
                .neq("id", folder_id)
                .execute()
            )

            if name_conflict_response.data and len(name_conflict_response.data) > 0:
                raise HTTPException(
                    status_code=409, detail="Folder name already exists"
                )

        # Sanitize description if provided
        sanitized_description = None
        if folder_data.description is not None:
            sanitized_description = SecurityValidator.sanitize_text(
                folder_data.description, strip_html=True
            )[: SECURITY_CONFIG["MAX_DESCRIPTION_LENGTH"]]

        update_data = {}
        if validated_name is not None:
            update_data["name"] = validated_name
        elif (
            folder_data.name is not None and folder_data.name == existing_folder["name"]
        ):
            # Name unchanged, keep it
            pass
        if folder_data.color is not None:
            update_data["color"] = folder_data.color
        if sanitized_description is not None:
            update_data["description"] = sanitized_description

        if not update_data:
            count_response = await supabase_client._exec(
                lambda: supabase_client.client.table("feedme_conversations")
                .select("id", count=COUNT_EXACT)
                .eq("folder_id", folder_id)
                .execute()
            )
            existing_folder["conversation_count"] = count_response.count or 0
            return FeedMeFolder(**existing_folder)

        updated_folder = await supabase_client.update_folder(folder_id, update_data)
        if not updated_folder:
            raise HTTPException(status_code=500, detail="Failed to update folder")

        count_response = await supabase_client._exec(
            lambda: supabase_client.client.table("feedme_conversations")
            .select("id", count=COUNT_EXACT)
            .eq("folder_id", folder_id)
            .execute()
        )

        updated_folder["conversation_count"] = count_response.count or 0
        await record_feedme_action_audit(
            action="update_folder",
            actor_id=current_user.sub,
            folder_id=folder_id,
            before_state=existing_folder,
            after_state=updated_folder,
        )
        logger.info(f"Updated folder {folder_id}")
        return FeedMeFolder(**updated_folder)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating folder {folder_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update folder")


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: int,
    move_conversations_to: Optional[int] = Query(
        None, description="Folder ID to move conversations to"
    ),
    current_user: TokenPayload = Depends(require_feedme_admin),
):
    """Delete a folder (blocked when the folder contains conversations)."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        client = get_supabase_client()

        folder_response = await client._exec(
            lambda: client.client.table("feedme_folders")
            .select("*")
            .eq("id", folder_id)
            .execute()
        )

        if not folder_response.data or len(folder_response.data) == 0:
            raise HTTPException(status_code=404, detail="Folder not found")

        folder = folder_response.data[0]

        count_response = await client._exec(
            lambda: client.client.table("feedme_conversations")
            .select("id", count=COUNT_EXACT)
            .eq("folder_id", folder_id)
            .eq("is_active", True)
            .execute()
        )

        conversation_count = count_response.count or 0

        settings_row = await get_feedme_settings()
        kb_folder_id = settings_row.get("kb_ready_folder_id")
        if isinstance(kb_folder_id, int) and kb_folder_id == folder_id:
            raise HTTPException(
                status_code=409,
                detail="Configured KB folder cannot be deleted. Update FeedMe settings first.",
            )

        if conversation_count > 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Folder contains {conversation_count} conversation(s). "
                    "Move conversations out before deletion."
                ),
            )

        await client.delete_folder(folder_id)
        await record_feedme_action_audit(
            action="delete_folder",
            actor_id=current_user.sub,
            folder_id=folder_id,
            before_state=folder,
        )
        logger.info(
            f"Deleted folder {folder_id}, moved {conversation_count} conversations"
        )

        return {
            "folder_id": folder_id,
            "folder_name": folder["name"],
            "conversations_moved": 0,
            "moved_to_folder_id": move_conversations_to,
            "message": f"Folder '{folder['name']}' deleted successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting folder {folder_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete folder")


@router.post("/folders/assign")
async def assign_conversations_to_folder(
    assign_request: AssignFolderRequest,
    current_user: TokenPayload = Depends(require_feedme_admin),
):
    """Assign multiple conversations to a folder or remove them from folders."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        client = get_supabase_client()
        requested_ids = list(dict.fromkeys(assign_request.conversation_ids))
        if len(requested_ids) > 50:
            raise HTTPException(
                status_code=400,
                detail="Maximum 50 conversation ids can be assigned per request",
            )

        target_folder_id = assign_request.folder_id
        effective_folder_id = None if target_folder_id == 0 else target_folder_id
        folder_name = None
        if effective_folder_id is not None:
            folder_response = await client._exec(
                lambda: client.client.table("feedme_folders")
                .select("name")
                .eq("id", effective_folder_id)
                .execute()
            )

            if not folder_response.data:
                raise HTTPException(status_code=404, detail="Folder not found")
            folder_name = folder_response.data[0]["name"]
        else:
            folder_name = "Unassigned"

        conversations_response = await client._exec(
            lambda: client.client.table("feedme_conversations")
            .select("id,folder_id")
            .in_("id", requested_ids)
            .execute()
        )
        existing_by_id: dict[int, dict[str, Any]] = {
            int(row["id"]): row for row in (conversations_response.data or [])
        }
        failed: list[dict[str, Any]] = []
        assignable_ids: list[int] = []
        for conversation_id in requested_ids:
            if conversation_id not in existing_by_id:
                failed.append({"conversation_id": conversation_id, "reason": "not_found"})
                continue
            assignable_ids.append(conversation_id)

        if assignable_ids:
            await client.bulk_assign_conversations_to_folder(
                conversation_ids=assignable_ids,
                folder_id=effective_folder_id,
            )
        assigned_count = len(assignable_ids)
        requested_count = len(requested_ids)
        action = (
            f"assigned to folder '{folder_name}'"
            if effective_folder_id is not None
            else "removed from folders"
        )
        await record_feedme_action_audit(
            action="assign_folder",
            actor_id=current_user.sub,
            folder_id=effective_folder_id,
            after_state={
                "folder_id": effective_folder_id,
                "assigned_count": assigned_count,
                "requested_count": requested_count,
                "failed": failed,
            },
        )
        logger.info("Folder assignment completed: %s/%s", assigned_count, requested_count)

        return {
            "folder_id": effective_folder_id,
            "folder_name": folder_name,
            "conversation_ids": assignable_ids,
            "assigned_count": assigned_count,
            "requested_count": requested_count,
            "failed": failed,
            "partial_success": bool(failed),
            "action": action,
            "message": f"Assigned {assigned_count} of {requested_count} conversation(s)",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning conversations to folder: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to assign conversations to folder"
        )


@router.get(
    "/folders/{folder_id}/conversations", response_model=ConversationListResponse
)
async def list_folder_conversations(
    folder_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
):
    """Get all conversations in a specific folder."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        client = get_supabase_client()

        folder_response = await client._exec(
            lambda: client.client.table("feedme_folders")
            .select("name")
            .eq("id", folder_id)
            .execute()
        )

        if not folder_response.data:
            raise HTTPException(status_code=404, detail="Folder not found")

        count_response = await client._exec(
            lambda: client.client.table("feedme_conversations")
            .select("id", count=COUNT_EXACT)
            .eq("folder_id", folder_id)
            .eq("is_active", True)
            .execute()
        )

        total_count = count_response.count or 0

        offset = (page - 1) * page_size
        conversations_response = await client._exec(
            lambda: client.client.table("feedme_conversations")
            .select("*")
            .eq("folder_id", folder_id)
            .eq("is_active", True)
            .order("updated_at", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )

        conversations: List[FeedMeConversation] = []
        for row in conversations_response.data:
            try:
                conversations.append(FeedMeConversation(**row))
            except Exception as e:
                logger.error(
                    "Failed to parse conversation row %s: %s", row.get("id"), e
                )

        return ConversationListResponse(
            conversations=conversations,
            total_count=total_count,
            page=page,
            page_size=page_size,
            has_next=offset + len(conversations) < total_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing conversations for folder {folder_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to list folder conversations"
        )
