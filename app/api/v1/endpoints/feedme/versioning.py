"""
FeedMe Versioning Endpoints

Version control operations for conversation editing and history.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.feedme.schemas import (
    ConversationVersion,
    VersionListResponse,
    VersionDiff,
    ConversationEditRequest,
    ConversationRevertRequest,
    EditResponse,
    RevertResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["FeedMe"])


@router.put("/conversations/{conversation_id}/edit", response_model=EditResponse)
async def edit_conversation(
    conversation_id: int, edit_request: ConversationEditRequest
):
    """
    Edit a conversation and create a new version.

    Creates new version with edited content, optionally triggers reprocessing,
    and maintains version history.
    """
    try:
        from app.feedme.versioning_service import get_versioning_service

        versioning_service = get_versioning_service()
        result = await versioning_service.edit_conversation(
            conversation_id, edit_request
        )

        logger.info(
            f"Successfully edited conversation {conversation_id}, new version: {result.new_version}"
        )
        return result

    except ValueError as e:
        logger.warning(f"Validation error editing conversation {conversation_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error editing conversation {conversation_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to edit conversation")


@router.get(
    "/conversations/{conversation_id}/versions", response_model=VersionListResponse
)
async def get_conversation_versions(conversation_id: int):
    """
    Get all versions of a conversation.

    Returns list of all versions ordered by version number (newest first),
    total version count, and currently active version number.
    """
    try:
        from app.feedme.versioning_service import get_versioning_service

        versioning_service = get_versioning_service()
        result = await versioning_service.get_conversation_versions(conversation_id)

        logger.info(
            f"Retrieved {result.total_count} versions for conversation {conversation_id}"
        )
        return result

    except ValueError as e:
        logger.warning(f"Conversation {conversation_id} not found: {e}")
        raise HTTPException(status_code=404, detail="Conversation not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error getting versions for conversation {conversation_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="Failed to get conversation versions"
        )


@router.get(
    "/conversations/{conversation_id}/versions/{version_1}/diff/{version_2}",
    response_model=VersionDiff,
)
async def get_version_diff(conversation_id: int, version_1: int, version_2: int):
    """
    Generate diff between two versions of a conversation.

    Shows added, removed, and modified lines with diff statistics
    for UI display.
    """
    try:
        from app.feedme.versioning_service import get_versioning_service

        versioning_service = get_versioning_service()

        v1 = await versioning_service.get_version_by_number(conversation_id, version_1)
        v2 = await versioning_service.get_version_by_number(conversation_id, version_2)

        if not v1:
            raise HTTPException(
                status_code=404, detail=f"Version {version_1} not found"
            )
        if not v2:
            raise HTTPException(
                status_code=404, detail=f"Version {version_2} not found"
            )

        diff = await versioning_service.generate_diff(v1, v2)

        logger.info(f"Generated diff between versions {version_1} and {version_2}")
        return diff

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating diff for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate version diff")


@router.post(
    "/conversations/{conversation_id}/revert/{target_version}",
    response_model=RevertResponse,
)
async def revert_conversation(
    conversation_id: int, target_version: int, revert_request: ConversationRevertRequest
):
    """
    Revert a conversation to a previous version.

    Creates new version with content from target version, maintains
    audit trail, and optionally triggers reprocessing.
    """
    try:
        from app.feedme.versioning_service import get_versioning_service

        if revert_request.target_version != target_version:
            raise HTTPException(
                status_code=400, detail="Target version in path must match request body"
            )

        versioning_service = get_versioning_service()
        result = await versioning_service.revert_conversation(
            conversation_id, revert_request
        )

        logger.info(
            f"Reverted conversation {conversation_id} to version {target_version}"
        )
        return result

    except ValueError as e:
        logger.warning(
            f"Validation error reverting conversation {conversation_id}: {e}"
        )
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error reverting conversation {conversation_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to revert conversation")


@router.get(
    "/conversations/{conversation_id}/versions/{version_number}",
    response_model=ConversationVersion,
)
async def get_specific_version(conversation_id: int, version_number: int):
    """
    Get a specific version of a conversation.

    Returns complete version data including content, metadata,
    timestamps, and user information.
    """
    try:
        from app.feedme.versioning_service import get_versioning_service

        versioning_service = get_versioning_service()
        version = await versioning_service.get_version_by_number(
            conversation_id, version_number
        )

        if not version:
            raise HTTPException(
                status_code=404,
                detail=f"Version {version_number} not found for conversation {conversation_id}",
            )

        logger.info(
            f"Retrieved version {version_number} for conversation {conversation_id}"
        )
        return version

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting version {version_number}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get conversation version"
        )
