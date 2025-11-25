"""
FeedMe Folder Endpoints

Folder management operations for organizing conversations.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.settings import settings
from app.db.supabase.client import get_supabase_client
from app.feedme.security import (
    SecureFolderNameModel,
    SecurityValidator,
    SecurityAuditLogger,
    limiter,
    SECURITY_CONFIG,
)
from app.feedme.schemas import ConversationListResponse

from .schemas import (
    FeedMeFolder,
    FolderCreate,
    FolderUpdate,
    FolderListResponse,
    AssignFolderRequest,
)
from .helpers import get_feedme_supabase_client, supabase_client

logger = logging.getLogger(__name__)
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
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    client = get_feedme_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="FeedMe service is temporarily unavailable.")

    try:
        folder_data = await client.get_folders_with_stats()

        folders = []
        for folder_dict in folder_data:
            if folder_dict['id'] is None:
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
                    created_by="system"
                )
                new_folder['conversation_count'] = 0
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
async def create_folder(request: Request, folder_data: FolderCreate):
    """Create a new folder for organizing conversations."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    client_ip = _get_client_ip(request)

    try:
        try:
            validated_folder = SecureFolderNameModel(name=folder_data.name)
            folder_data.name = validated_folder.name
        except ValueError as e:
            audit_logger.log_validation_failure("folder_name", folder_data.name, str(e), client_ip)
            raise HTTPException(status_code=400, detail=str(e))

        if folder_data.description:
            folder_data.description = SecurityValidator.sanitize_text(
                folder_data.description,
                strip_html=True
            )[:SECURITY_CONFIG["MAX_DESCRIPTION_LENGTH"]]

        # Attempt insert - let DB unique constraint handle race conditions
        # The pre-check is a courtesy to provide better error messages in common cases
        existing_folders = await supabase_client._exec(
            lambda: supabase_client.client.table('feedme_folders')
            .select('id')
            .eq('name', folder_data.name)
            .execute()
        )

        if existing_folders.data and len(existing_folders.data) > 0:
            raise HTTPException(status_code=409, detail="Folder name already exists")

        try:
            folder_result = await supabase_client.insert_folder(
                name=folder_data.name,
                color=folder_data.color,
                description=folder_data.description,
                created_by=folder_data.created_by
            )
        except Exception as insert_error:
            # Check for unique constraint violation (race condition)
            error_str = str(insert_error).lower()
            if "unique" in error_str or "duplicate" in error_str or "23505" in error_str:
                raise HTTPException(status_code=409, detail="Folder name already exists")
            raise

        folder_result['conversation_count'] = 0
        logger.info(f"Created folder: {folder_data.name}")
        return FeedMeFolder(**folder_result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating folder: {e}")
        raise HTTPException(status_code=500, detail="Failed to create folder")


@router.put("/folders/{folder_id}", response_model=FeedMeFolder)
async def update_folder(folder_id: int, folder_data: FolderUpdate):
    """Update an existing folder's name, color, or description."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        existing_folder_response = await supabase_client._exec(
            lambda: supabase_client.client.table('feedme_folders')
            .select('*')
            .eq('id', folder_id)
            .execute()
        )

        if not existing_folder_response.data or len(existing_folder_response.data) == 0:
            raise HTTPException(status_code=404, detail="Folder not found")

        existing_folder = existing_folder_response.data[0]

        # Validate and sanitize name if provided
        validated_name = None
        if folder_data.name and folder_data.name != existing_folder['name']:
            try:
                validated_folder = SecureFolderNameModel(name=folder_data.name)
                validated_name = validated_folder.name
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            name_conflict_response = await supabase_client._exec(
                lambda: supabase_client.client.table('feedme_folders')
                .select('id')
                .eq('name', validated_name)
                .neq('id', folder_id)
                .execute()
            )

            if name_conflict_response.data and len(name_conflict_response.data) > 0:
                raise HTTPException(status_code=409, detail="Folder name already exists")

        # Sanitize description if provided
        sanitized_description = None
        if folder_data.description is not None:
            sanitized_description = SecurityValidator.sanitize_text(
                folder_data.description,
                strip_html=True
            )[:SECURITY_CONFIG["MAX_DESCRIPTION_LENGTH"]]

        update_data = {}
        if validated_name is not None:
            update_data['name'] = validated_name
        elif folder_data.name is not None and folder_data.name == existing_folder['name']:
            # Name unchanged, keep it
            pass
        if folder_data.color is not None:
            update_data['color'] = folder_data.color
        if sanitized_description is not None:
            update_data['description'] = sanitized_description

        if not update_data:
            count_response = await supabase_client._exec(
                lambda: supabase_client.client.table('feedme_conversations')
                .select('id', count='exact')
                .eq('folder_id', folder_id)
                .execute()
            )
            existing_folder['conversation_count'] = count_response.count or 0
            return FeedMeFolder(**existing_folder)

        updated_folder = await supabase_client.update_folder(folder_id, update_data)
        if not updated_folder:
            raise HTTPException(status_code=500, detail="Failed to update folder")

        count_response = await supabase_client._exec(
            lambda: supabase_client.client.table('feedme_conversations')
            .select('id', count='exact')
            .eq('folder_id', folder_id)
            .execute()
        )

        updated_folder['conversation_count'] = count_response.count or 0
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
    move_conversations_to: Optional[int] = Query(None, description="Folder ID to move conversations to")
):
    """Delete a folder and optionally move its conversations."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        client = get_supabase_client()

        folder_response = await client._exec(
            lambda: client.client.table('feedme_folders')
            .select('*')
            .eq('id', folder_id)
            .execute()
        )

        if not folder_response.data or len(folder_response.data) == 0:
            raise HTTPException(status_code=404, detail="Folder not found")

        folder = folder_response.data[0]

        count_response = await client._exec(
            lambda: client.client.table('feedme_conversations')
            .select('id', count='exact')
            .eq('folder_id', folder_id)
            .eq('is_active', True)
            .execute()
        )

        conversation_count = count_response.count or 0

        if move_conversations_to is not None:
            target_folder_response = await client._exec(
                lambda: client.client.table('feedme_folders')
                .select('id')
                .eq('id', move_conversations_to)
                .execute()
            )

            if not target_folder_response.data:
                raise HTTPException(status_code=404, detail="Target folder not found")

        if conversation_count > 0:
            await client._exec(
                lambda: client.client.table('feedme_conversations')
                .update({
                    'folder_id': move_conversations_to,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                })
                .eq('folder_id', folder_id)
                .execute()
            )

        await client.delete_folder(folder_id)
        logger.info(f"Deleted folder {folder_id}, moved {conversation_count} conversations")

        return {
            "folder_id": folder_id,
            "folder_name": folder['name'],
            "conversations_moved": conversation_count,
            "moved_to_folder_id": move_conversations_to,
            "message": f"Folder '{folder['name']}' deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting folder {folder_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete folder")


@router.post("/folders/assign")
async def assign_conversations_to_folder(assign_request: AssignFolderRequest):
    """Assign multiple conversations to a folder or remove them from folders."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        client = get_supabase_client()

        folder_name = None
        if assign_request.folder_id is not None:
            folder_response = await client._exec(
                lambda: client.client.table('feedme_folders')
                .select('name')
                .eq('id', assign_request.folder_id)
                .execute()
            )

            if not folder_response.data:
                raise HTTPException(status_code=404, detail="Folder not found")
            folder_name = folder_response.data[0]['name']

        if assign_request.conversation_ids:
            conversations_response = await client._exec(
                lambda: client.client.table('feedme_conversations')
                .select('id')
                .in_('id', assign_request.conversation_ids)
                .eq('is_active', True)
                .execute()
            )

            existing_ids = [row['id'] for row in conversations_response.data]
            missing_ids = set(assign_request.conversation_ids) - set(existing_ids)

            if missing_ids:
                raise HTTPException(status_code=404, detail=f"Conversations not found: {list(missing_ids)}")

            await client.bulk_assign_conversations_to_folder(
                conversation_ids=assign_request.conversation_ids,
                folder_id=assign_request.folder_id
            )

            updated_count = len(existing_ids)
            action = f"assigned to folder '{folder_name}'" if folder_name else "removed from folders"
            logger.info(f"Successfully {action} {updated_count} conversations")

            return {
                "folder_id": assign_request.folder_id,
                "folder_name": folder_name,
                "conversation_ids": existing_ids,
                "updated_count": updated_count,
                "action": action,
                "message": f"Successfully {action} {updated_count} conversations"
            }
        else:
            return {
                "folder_id": assign_request.folder_id,
                "folder_name": folder_name,
                "conversation_ids": [],
                "updated_count": 0,
                "action": "no conversations provided",
                "message": "No conversations were provided for assignment"
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning conversations to folder: {e}")
        raise HTTPException(status_code=500, detail="Failed to assign conversations to folder")


@router.get("/folders/{folder_id}/conversations", response_model=ConversationListResponse)
async def list_folder_conversations(
    folder_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page")
):
    """Get all conversations in a specific folder."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        client = get_supabase_client()

        folder_response = await client._exec(
            lambda: client.client.table('feedme_folders')
            .select('name')
            .eq('id', folder_id)
            .execute()
        )

        if not folder_response.data:
            raise HTTPException(status_code=404, detail="Folder not found")

        count_response = await client._exec(
            lambda: client.client.table('feedme_conversations')
            .select('id', count='exact')
            .eq('folder_id', folder_id)
            .eq('is_active', True)
            .execute()
        )

        total_count = count_response.count or 0

        offset = (page - 1) * page_size
        conversations_response = await client._exec(
            lambda: client.client.table('feedme_conversations')
            .select('*')
            .eq('folder_id', folder_id)
            .eq('is_active', True)
            .order('updated_at', desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )

        conversations = []
        for row in conversations_response.data:
            conversations.append({
                'id': row['id'],
                'title': row['title'],
                'processing_status': row.get('processing_status', 'pending'),
                'total_examples': row.get('total_examples', 0),
                'created_at': row['created_at'],
                'metadata': row.get('metadata', {})
            })

        return ConversationListResponse(
            conversations=conversations,
            total_count=total_count,
            page=page,
            page_size=page_size,
            has_next=offset + len(conversations) < total_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing conversations for folder {folder_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list folder conversations")
