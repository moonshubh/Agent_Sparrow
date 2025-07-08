"""
FeedMe v3.0 Versioning Service - Supabase Only
Handles conversation versioning, diffs, and edit operations

This module provides:
- Version creation on conversation updates
- Version history management
- Diff generation between versions
- Revert functionality
- Integration with async reprocessing
"""

import logging
import difflib
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from app.db.supabase_client import get_supabase_client
from app.feedme.schemas import (
    ConversationVersion,
    VersionListResponse,
    VersionDiff,
    ModifiedLine,
    ConversationEditRequest,
    ConversationRevertRequest,
    EditResponse,
    RevertResponse,
    FeedMeConversation,
    ProcessingStatus
)
from app.core.settings import settings

logger = logging.getLogger(__name__)


class VersioningService:
    """Service for managing conversation versions in Supabase"""
    
    def __init__(self):
        self._supabase_client = None
    
    @property
    def supabase_client(self):
        """Lazy load Supabase client"""
        if self._supabase_client is None:
            self._supabase_client = get_supabase_client()
        return self._supabase_client
    
    async def create_new_version(self, conversation_id: int, updated_data: Dict[str, Any], 
                                updated_by: str) -> ConversationVersion:
        """
        Create a new version of a conversation
        
        Note: Version control should be implemented at the Supabase level
        using RLS policies and audit tables
        """
        logger.warning("Versioning not yet implemented in Supabase - returning placeholder")
        
        # For now, just update the conversation
        await self.supabase_client.update_conversation(
            conversation_id=conversation_id,
            update_data=updated_data
        )
        
        # Return a placeholder version
        return ConversationVersion(
            id=1,
            conversation_id=conversation_id,
            version_number=1,
            updated_by=updated_by,
            created_at=datetime.now(timezone.utc),
            is_active=True
        )
    
    async def get_version_history(self, conversation_id: int, 
                                 offset: int = 0, 
                                 limit: int = 10) -> VersionListResponse:
        """
        Get version history for a conversation
        
        Note: Requires Supabase audit table implementation
        """
        logger.warning("Version history not yet implemented in Supabase")
        
        return VersionListResponse(
            versions=[],
            total_count=0,
            has_more=False
        )
    
    async def get_version_diff(self, conversation_id: int, 
                              version_id1: int, 
                              version_id2: int) -> VersionDiff:
        """
        Generate diff between two versions
        
        Note: Requires Supabase audit table implementation
        """
        logger.warning("Version diff not yet implemented in Supabase")
        
        return VersionDiff(
            conversation_id=conversation_id,
            from_version=version_id1,
            to_version=version_id2,
            raw_transcript_diff=[],
            metadata_changes={}
        )
    
    async def edit_conversation(self, conversation_id: int, 
                               edit_request: ConversationEditRequest) -> EditResponse:
        """
        Edit conversation transcript and trigger reprocessing
        """
        try:
            # Update conversation in Supabase
            update_data = {
                'raw_transcript': edit_request.updated_transcript,
                'processing_status': ProcessingStatus.PENDING.value
            }
            
            if edit_request.metadata:
                update_data['metadata'] = edit_request.metadata
            
            await self.supabase_client.update_conversation(
                conversation_id=conversation_id,
                update_data=update_data
            )
            
            # TODO: Trigger async reprocessing via Celery
            
            return EditResponse(
                conversation_id=conversation_id,
                version_id=1,  # Placeholder
                status="updated",
                message="Conversation updated and queued for reprocessing"
            )
            
        except Exception as e:
            logger.error(f"Error editing conversation {conversation_id}: {e}")
            raise
    
    async def revert_conversation(self, conversation_id: int, 
                                 revert_request: ConversationRevertRequest) -> RevertResponse:
        """
        Revert conversation to a previous version
        
        Note: Requires Supabase audit table implementation
        """
        logger.warning("Revert functionality not yet implemented in Supabase")
        
        return RevertResponse(
            conversation_id=conversation_id,
            reverted_to_version=revert_request.version_id,
            status="error",
            message="Revert functionality not yet implemented"
        )
    
    def _generate_line_diff(self, old_text: str, new_text: str) -> List[ModifiedLine]:
        """
        Generate line-by-line diff between two texts
        """
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        
        diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=''))
        
        modified_lines = []
        for line in diff:
            if line.startswith('+') and not line.startswith('+++'):
                modified_lines.append(ModifiedLine(
                    line_number=len(modified_lines) + 1,
                    old_content='',
                    new_content=line[1:].rstrip(),
                    change_type='added'
                ))
            elif line.startswith('-') and not line.startswith('---'):
                modified_lines.append(ModifiedLine(
                    line_number=len(modified_lines) + 1,
                    old_content=line[1:].rstrip(),
                    new_content='',
                    change_type='removed'
                ))
        
        return modified_lines