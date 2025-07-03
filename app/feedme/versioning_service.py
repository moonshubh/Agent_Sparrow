"""
FeedMe v2.0 Phase 3: Versioning Service
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
import psycopg2.extras

from app.db.connection_manager import get_connection_manager, with_db_connection
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
    """Service for managing conversation versions"""
    
    def __init__(self):
        self.connection_manager = get_connection_manager()
    
    @with_db_connection()
    def create_new_version(self, conn, conversation_id: int, updated_data: Dict[str, Any], 
                          updated_by: str) -> ConversationVersion:
        """
        Create a new version of a conversation
        
        Process:
        1. Deactivate current active version
        2. Get next version number
        3. Create new version record
        4. Return new version
        """
        try:
            with conn.cursor() as cur:
                # Get current active version data
                cur.execute("""
                    SELECT * FROM feedme_conversations 
                    WHERE id = %s AND is_active = true
                """, (conversation_id,))
                
                current_version_row = cur.fetchone()
                if not current_version_row:
                    raise ValueError(f"No active conversation found with id {conversation_id}")
                
                current_version = dict(current_version_row)
                
                # Deactivate current version
                cur.execute("""
                    UPDATE feedme_conversations 
                    SET is_active = false, updated_at = now()
                    WHERE id = %s
                """, (conversation_id,))
                
                # Get next version number
                cur.execute("""
                    SELECT MAX(version) + 1 as next_version 
                    FROM feedme_conversations 
                    WHERE uuid = %s
                """, (current_version['uuid'],))
                
                next_version = cur.fetchone()['next_version'] or 1
                
                # Merge updated data with current version
                new_data = {**current_version}
                new_data.update(updated_data)
                new_data.update({
                    'version': next_version,
                    'is_active': True,
                    'updated_by': updated_by,
                    'updated_at': datetime.now(timezone.utc),
                    'created_at': datetime.now(timezone.utc)  # New version creation time
                })
                
                # Remove id to create new record
                new_data.pop('id')
                
                # Insert new version
                # Define allowed columns
                ALLOWED_COLUMNS = {
                    'uuid', 'title', 'raw_transcript', 'metadata', 'version',
                    'is_active', 'updated_by', 'updated_at', 'created_at',
                    # ... add other allowed columns
                }

                # Validate columns
                columns_to_insert = [col for col in new_data.keys() if col in ALLOWED_COLUMNS]
                if len(columns_to_insert) != len(new_data):
                    invalid_cols = set(new_data.keys()) - ALLOWED_COLUMNS
                    raise ValueError(f"Invalid columns: {invalid_cols}")

                columns = ', '.join(columns_to_insert)
                placeholders = ', '.join(['%s'] * len(columns_to_insert))
                values = [new_data[col] for col in columns_to_insert]

                cur.execute(f"""
                    INSERT INTO feedme_conversations ({columns})
                    VALUES ({placeholders})
                    RETURNING *
                """, values)
                
                new_version_row = cur.fetchone()
                conn.commit()
                
                logger.info(f"Created version {next_version} for conversation {conversation_id}")
                return ConversationVersion(**dict(new_version_row))
                
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create new version for conversation {conversation_id}: {e}")
            raise
    
    def get_conversation_versions(self, conversation_id: int) -> VersionListResponse:
        """Get all versions of a conversation"""
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                    # Get the UUID for this conversation
                    cur.execute("""
                        SELECT uuid FROM feedme_conversations 
                        WHERE id = %s LIMIT 1
                    """, (conversation_id,))
                    
                    result = cur.fetchone()
                    if not result:
                        raise ValueError(f"Conversation {conversation_id} not found")
                    
                    conversation_uuid = result['uuid']
                    
                    # Get all versions for this conversation UUID, excluding deleted ones
                    cur.execute("""
                        SELECT * FROM feedme_conversations 
                        WHERE uuid = %s AND (is_deleted IS NULL OR is_deleted = false)
                        ORDER BY version DESC
                    """, (conversation_uuid,))
                    
                    version_rows = cur.fetchall()
                    versions = [ConversationVersion(**dict(row)) for row in version_rows]
                    
                    # Get active version number
                    active_version = next((v.version for v in versions if v.is_active), None)
                    
                    return VersionListResponse(
                        versions=versions,
                        total_count=len(versions),
                        active_version=active_version or versions[0].version if versions else 1
                    )
                
        except Exception as e:
            logger.error(f"Failed to get versions for conversation {conversation_id}: {e}")
            raise
    
    def get_version_by_number(self, conversation_id: int, version_number: int) -> Optional[ConversationVersion]:
        """Get a specific version of a conversation"""
        try:
            with self.connection_manager.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                    # Get the UUID for this conversation
                    cur.execute("""
                        SELECT uuid FROM feedme_conversations 
                        WHERE id = %s LIMIT 1
                    """, (conversation_id,))
                    
                    result = cur.fetchone()
                    if not result:
                        return None
                    
                    conversation_uuid = result['uuid']
                    
                    # Get specific version
                    cur.execute("""
                        SELECT * FROM feedme_conversations 
                        WHERE uuid = %s AND version = %s
                    """, (conversation_uuid, version_number))
                    
                    version_row = cur.fetchone()
                    if version_row:
                        return ConversationVersion(**dict(version_row))
                    return None
                
        except Exception as e:
            logger.error(f"Failed to get version {version_number} for conversation {conversation_id}: {e}")
            raise
    
    def generate_diff(self, version_1: ConversationVersion, version_2: ConversationVersion) -> VersionDiff:
        """Generate diff between two versions"""
        try:
            # Split content into lines
            lines_1 = version_1.raw_transcript.splitlines()
            lines_2 = version_2.raw_transcript.splitlines()
            
            # Generate unified diff
            diff_generator = difflib.unified_diff(
                lines_1, lines_2,
                fromfile=f"Version {version_1.version}",
                tofile=f"Version {version_2.version}",
                lineterm=""
            )
            
            # Parse diff output
            added_lines = []
            removed_lines = []
            modified_lines = []
            unchanged_lines = []
            
            # Use difflib.SequenceMatcher for more detailed analysis
            matcher = difflib.SequenceMatcher(None, lines_1, lines_2)
            
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == 'equal':
                    unchanged_lines.extend(lines_1[i1:i2])
                elif tag == 'delete':
                    removed_lines.extend(lines_1[i1:i2])
                elif tag == 'insert':
                    added_lines.extend(lines_2[j1:j2])
                elif tag == 'replace':
                    # Handle modified lines
                    old_lines = lines_1[i1:i2]
                    new_lines = lines_2[j1:j2]
                    
                    for idx, (old, new) in enumerate(zip(old_lines, new_lines)):
                        modified_lines.append(ModifiedLine(
                            line_number=i1 + idx + 1,
                            original=old,
                            modified=new
                        ))
                    
                    # Handle remaining lines if lists are different lengths
                    if len(old_lines) > len(new_lines):
                        removed_lines.extend(old_lines[len(new_lines):])
                    elif len(new_lines) > len(old_lines):
                        added_lines.extend(new_lines[len(old_lines):])
            
            # Calculate statistics
            stats = {
                "added_count": len(added_lines),
                "removed_count": len(removed_lines),
                "modified_count": len(modified_lines),
                "unchanged_count": len(unchanged_lines),
                "total_changes": len(added_lines) + len(removed_lines) + len(modified_lines)
            }
            
            return VersionDiff(
                from_version=version_1.version,
                to_version=version_2.version,
                added_lines=added_lines,
                removed_lines=removed_lines,
                modified_lines=modified_lines,
                unchanged_lines=unchanged_lines,
                stats=stats
            )
            
        except Exception as e:
            logger.error(f"Failed to generate diff between versions {version_1.version} and {version_2.version}: {e}")
            raise
    
    async def edit_conversation(self, conversation_id: int, edit_request: ConversationEditRequest) -> EditResponse:
        """Edit a conversation and optionally trigger reprocessing"""
        try:
            # Prepare update data
            update_data = {}
            if edit_request.title is not None:
                update_data['title'] = edit_request.title
            if edit_request.raw_transcript is not None:
                update_data['raw_transcript'] = edit_request.raw_transcript
            if edit_request.metadata is not None:
                update_data['metadata'] = edit_request.metadata
            
            # Create new version
            new_version = self.create_new_version(
                conversation_id=conversation_id,
                updated_data=update_data,
                updated_by=edit_request.updated_by
            )
            
            # Convert to FeedMeConversation
            conversation = FeedMeConversation(
                id=new_version.id,
                uuid=new_version.uuid,
                title=new_version.title,
                raw_transcript=new_version.raw_transcript,
                metadata=new_version.metadata,
                is_active=new_version.is_active,
                version=new_version.version,
                updated_by=new_version.updated_by,
                created_at=new_version.created_at,
                updated_at=new_version.updated_at
            )
            
            task_id = None
            reprocessing = False
            
            # Trigger reprocessing if requested and async processing is enabled
            if edit_request.reprocess and settings.feedme_async_processing:
                try:
                    from app.feedme.tasks import process_transcript
                    task = process_transcript.delay(new_version.id, edit_request.updated_by)
                    task_id = task.id
                    reprocessing = True
                    
                    logger.info(f"Triggered reprocessing for edited conversation {conversation_id}, task: {task_id}")
                except Exception as e:
                    logger.warning(f"Failed to trigger reprocessing: {e}")
            
            return EditResponse(
                conversation=conversation,
                new_version=new_version.version,
                task_id=task_id,
                reprocessing=reprocessing
            )
            
        except Exception as e:
            logger.error(f"Failed to edit conversation {conversation_id}: {e}")
            raise
    
    async def revert_conversation(self, conversation_id: int, revert_request: ConversationRevertRequest) -> RevertResponse:
        """Revert conversation to a previous version"""
        try:
            # Get the target version
            target_version = self.get_version_by_number(conversation_id, revert_request.target_version)
            if not target_version:
                raise ValueError(f"Version {revert_request.target_version} not found")
            
            # Create new version with target version's content
            update_data = {
                'title': target_version.title,
                'raw_transcript': target_version.raw_transcript,
                'metadata': {
                    **target_version.metadata,
                    'reverted_from_version': revert_request.target_version,
                    'revert_reason': revert_request.reason,
                    'revert_timestamp': datetime.now(timezone.utc).isoformat()
                }
            }
            
            new_version = self.create_new_version(
                conversation_id=conversation_id,
                updated_data=update_data,
                updated_by=revert_request.reverted_by
            )
            
            # The UUID is consistent across all versions, so we can get it from the target version
            # This avoids an extra database query.
            conversation_uuid = target_version.uuid
            
            # Convert to FeedMeConversation
            conversation = FeedMeConversation(
                id=new_version.id,
                uuid=conversation_uuid,  # Use the actual UUID from the database
                title=new_version.title,
                raw_transcript=new_version.raw_transcript,
                metadata=new_version.metadata,
                is_active=new_version.is_active,
                version=new_version.version,
                updated_by=new_version.updated_by,
                created_at=new_version.created_at,
                updated_at=new_version.updated_at,
                # Required fields from FeedMeConversationBase
                original_filename=new_version.metadata.get('original_filename'),
                uploaded_by=new_version.updated_by,
                # Required fields from FeedMeConversation
                uploaded_at=new_version.created_at,  # Use created_at as fallback
                processing_status='completed',  # Default status
                total_examples=0  # Will be updated during processing
            )
            
            task_id = None
            reprocessing = False
            
            # Trigger reprocessing if requested and async processing is enabled
            if revert_request.reprocess and settings.feedme_async_processing:
                try:
                    from app.feedme.tasks import process_transcript
                    task = process_transcript.delay(new_version.id, revert_request.reverted_by)
                    task_id = task.id
                    reprocessing = True
                    
                    logger.info(f"Triggered reprocessing for reverted conversation {conversation_id}, task: {task_id}")
                except Exception as e:
                    logger.warning(f"Failed to trigger reprocessing: {e}")
            
            return RevertResponse(
                conversation=conversation,
                new_version=new_version.version,
                reverted_to_version=revert_request.target_version,
                task_id=task_id,
                reprocessing=reprocessing
            )
            
        except Exception as e:
            logger.error(f"Failed to revert conversation {conversation_id}: {e}")
            raise


# Global service instance
_versioning_service: Optional[VersioningService] = None


def get_versioning_service() -> VersioningService:
    """Get the global versioning service instance"""
    global _versioning_service
    
    if _versioning_service is None:
        _versioning_service = VersioningService()
    
    return _versioning_service