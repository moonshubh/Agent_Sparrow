"""
Supabase Client Wrapper for FeedMe Integration

Provides typed helpers for Supabase operations including folder management,
conversation persistence, and example synchronization.
"""

import os
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import asyncio
from contextlib import asynccontextmanager

# Note: supabase-py must be installed: pip install supabase
from supabase import create_client, Client
from postgrest.exceptions import APIError

logger = logging.getLogger(__name__)


class SupabaseConfig:
    """Configuration for Supabase connection"""
    def __init__(self):
        self.url = os.environ.get('SUPABASE_URL')
        self.anon_key = os.environ.get('SUPABASE_ANON_KEY')
        self.service_key = os.environ.get('SUPABASE_SERVICE_KEY')  # Optional for admin operations
        
        if not self.url or not self.anon_key:
            raise ValueError(
                "Missing Supabase configuration. "
                "Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables."
            )
        
        # Use service key if available for server-side operations
        self.key = self.service_key if self.service_key else self.anon_key


class SupabaseClient:
    """
    Supabase client wrapper with typed operations for FeedMe integration
    """
    
    def __init__(self, config: Optional[SupabaseConfig] = None):
        self.config = config or SupabaseConfig()
        self._client: Optional[Client] = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Supabase client"""
        try:
            self._client = create_client(self.config.url, self.config.key)
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise
    
    @property
    def client(self) -> Client:
        """Get Supabase client instance"""
        if not self._client:
            self._initialize_client()
        return self._client
    
    # =====================================================
    # FOLDER OPERATIONS
    # =====================================================
    
    async def insert_folder(
        self, 
        name: str, 
        color: str = "#0095ff",
        description: Optional[str] = None,
        parent_id: Optional[int] = None,
        created_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new folder
        
        Args:
            name: Folder name
            color: Hex color code (default: Mailbird blue)
            description: Optional folder description
            parent_id: Parent folder ID for nested folders
            created_by: User who created the folder
            
        Returns:
            Created folder data
        """
        try:
            data = {
                "name": name,
                "color": color,
                "description": description,
                "parent_id": parent_id,
                "created_by": created_by
            }
            
            response = self.client.table('feedme_folders').insert(data).execute()
            
            if response.data:
                logger.info(f"Created folder: {name} (ID: {response.data[0]['id']})")
                return response.data[0]
            else:
                raise Exception("No data returned from folder creation")
                
        except APIError as e:
            logger.error(f"Supabase API error creating folder: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating folder: {e}")
            raise
    
    async def update_folder(
        self,
        folder_id: int,
        name: Optional[str] = None,
        color: Optional[str] = None,
        description: Optional[str] = None,
        parent_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Update an existing folder"""
        try:
            data = {}
            if name is not None:
                data["name"] = name
            if color is not None:
                data["color"] = color
            if description is not None:
                data["description"] = description
            if parent_id is not None:
                data["parent_id"] = parent_id
            
            response = self.client.table('feedme_folders')\
                .update(data)\
                .eq('id', folder_id)\
                .execute()
            
            if response.data:
                logger.info(f"Updated folder ID: {folder_id}")
                return response.data[0]
            else:
                raise Exception(f"Folder {folder_id} not found")
                
        except Exception as e:
            logger.error(f"Error updating folder: {e}")
            raise
    
    async def delete_folder(self, folder_id: int) -> bool:
        """Delete a folder (cascades to child folders)"""
        try:
            response = self.client.table('feedme_folders')\
                .delete()\
                .eq('id', folder_id)\
                .execute()
            
            logger.info(f"Deleted folder ID: {folder_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting folder: {e}")
            raise
    
    async def list_folders(self) -> List[Dict[str, Any]]:
        """List all folders with stats"""
        try:
            # Query the folder stats view for enriched data
            response = self.client.table('feedme_folder_stats')\
                .select('*')\
                .order('folder_path')\
                .execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"Error listing folders: {e}")
            raise
    
    # =====================================================
    # CONVERSATION OPERATIONS
    # =====================================================
    
    async def insert_conversation(
        self,
        title: str,
        raw_transcript: str,
        original_filename: Optional[str] = None,
        folder_id: Optional[int] = None,
        metadata: Optional[Dict] = None,
        uploaded_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new conversation"""
        try:
            data = {
                "title": title,
                "raw_transcript": raw_transcript,
                "original_filename": original_filename,
                "folder_id": folder_id,
                "metadata": metadata or {},
                "uploaded_by": uploaded_by,
                "processing_status": "pending"
            }
            
            response = self.client.table('feedme_conversations').insert(data).execute()
            
            if response.data:
                logger.info(f"Created conversation: {title} (ID: {response.data[0]['id']})")
                return response.data[0]
            else:
                raise Exception("No data returned from conversation creation")
                
        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            raise
    
    async def get_conversation(self, conversation_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a conversation by its ID from Supabase
        
        Args:
            conversation_id: The ID of the conversation to retrieve
            
        Returns:
            Dict containing conversation data if found, None otherwise
        """
        try:
            response = self.client.table('feedme_conversations')\
                .select('*')\
                .eq('id', conversation_id)\
                .execute()
            
            if response.data and len(response.data) > 0:
                logger.info(f"Retrieved conversation {conversation_id}")
                return response.data[0]
            else:
                logger.warning(f"Conversation {conversation_id} not found")
                return None
                
        except Exception as e:
            logger.error(f"Error retrieving conversation {conversation_id}: {e}")
            return None
    
    async def list_conversations(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        List conversations with optional filtering and pagination
        
        Args:
            filters: Optional filters to apply (folder_id, processing_status, etc.)
            limit: Maximum number of conversations to return
            offset: Number of conversations to skip (for pagination)
            
        Returns:
            Dict containing conversations list and pagination info
        """
        try:
            query = self.client.table('feedme_conversations').select('*')
            
            # Apply filters
            if filters:
                if 'folder_id' in filters:
                    if filters['folder_id'] is None:
                        query = query.is_('folder_id', 'null')
                    else:
                        query = query.eq('folder_id', filters['folder_id'])
                
                if 'processing_status' in filters:
                    query = query.eq('processing_status', filters['processing_status'])
                
                if 'uploaded_by' in filters:
                    query = query.eq('uploaded_by', filters['uploaded_by'])
            
            # Apply pagination
            query = query.order('created_at', desc=True)\
                         .range(offset, offset + limit - 1)
            
            response = query.execute()
            
            # Get total count for pagination
            count_response = self.client.table('feedme_conversations')\
                .select('id', count='exact')\
                .execute()
            
            total_count = count_response.count if count_response.count else 0
            
            logger.info(f"Listed {len(response.data)} conversations (total: {total_count})")
            
            return {
                'conversations': response.data or [],
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < total_count
            }
            
        except Exception as e:
            logger.error(f"Error listing conversations: {e}")
            return {
                'conversations': [],
                'total_count': 0,
                'limit': limit,
                'offset': offset,
                'has_more': False
            }
    
    async def update_conversation(
        self,
        conversation_id: int,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update a conversation with new data
        
        Args:
            conversation_id: The ID of the conversation to update
            updates: Dictionary of fields to update
            
        Returns:
            Updated conversation data if successful, None otherwise
        """
        try:
            # Add updated_at timestamp
            updates['updated_at'] = datetime.now().isoformat()
            
            response = self.client.table('feedme_conversations')\
                .update(updates)\
                .eq('id', conversation_id)\
                .execute()
            
            if response.data and len(response.data) > 0:
                logger.info(f"Updated conversation {conversation_id}")
                return response.data[0]
            else:
                logger.warning(f"Conversation {conversation_id} not found for update")
                return None
                
        except Exception as e:
            logger.error(f"Error updating conversation {conversation_id}: {e}")
            return None
    
    async def delete_conversation(self, conversation_id: int) -> bool:
        """
        Delete a conversation and all its associated examples
        
        Args:
            conversation_id: The ID of the conversation to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            # First delete associated examples
            examples_response = self.client.table('feedme_examples')\
                .delete()\
                .eq('conversation_id', conversation_id)\
                .execute()
            
            # Then delete the conversation
            conversation_response = self.client.table('feedme_conversations')\
                .delete()\
                .eq('id', conversation_id)\
                .execute()
            
            if conversation_response.data:
                examples_count = len(examples_response.data) if examples_response.data else 0
                logger.info(f"Deleted conversation {conversation_id} and {examples_count} examples")
                return True
            else:
                logger.warning(f"Conversation {conversation_id} not found for deletion")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting conversation {conversation_id}: {e}")
            return False
    
    async def update_conversation_folder(
        self,
        conversation_id: int,
        folder_id: Optional[int]
    ) -> Dict[str, Any]:
        """Move conversation to a different folder"""
        try:
            response = self.client.table('feedme_conversations')\
                .update({"folder_id": folder_id})\
                .eq('id', conversation_id)\
                .execute()
            
            if response.data:
                logger.info(f"Moved conversation {conversation_id} to folder {folder_id}")
                return response.data[0]
            else:
                raise Exception(f"Conversation {conversation_id} not found")
                
        except Exception as e:
            logger.error(f"Error updating conversation folder: {e}")
            raise
    
    async def bulk_assign_conversations_to_folder(
        self,
        conversation_ids: List[int],
        folder_id: Optional[int]
    ) -> int:
        """Assign multiple conversations to a folder"""
        try:
            response = self.client.table('feedme_conversations')\
                .update({"folder_id": folder_id})\
                .in_('id', conversation_ids)\
                .execute()
            
            count = len(response.data) if response.data else 0
            logger.info(f"Assigned {count} conversations to folder {folder_id}")
            return count
            
        except Exception as e:
            logger.error(f"Error bulk assigning conversations: {e}")
            raise
    
    # =====================================================
    # EXAMPLE OPERATIONS
    # =====================================================
    
    async def insert_examples(
        self,
        examples: List[Dict[str, Any]],
        mark_approved: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Insert multiple Q&A examples
        
        Args:
            examples: List of example dictionaries
            mark_approved: Whether to mark as approved
            
        Returns:
            List of created examples
        """
        try:
            # Note: Approval fields temporarily disabled until migration is applied
            # TODO: Re-enable after adding approval columns to Supabase table
            
            response = self.client.table('feedme_examples').insert(examples).execute()
            
            if response.data:
                logger.info(f"Inserted {len(response.data)} examples")
                return response.data
            else:
                raise Exception("No data returned from examples insertion")
                
        except Exception as e:
            logger.error(f"Error inserting examples: {e}")
            raise
    
    async def approve_conversation_examples(
        self,
        conversation_id: int,
        approved_by: str,
        example_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Approve examples from a conversation
        
        Args:
            conversation_id: Conversation ID
            approved_by: User approving the examples
            example_ids: Specific example IDs to approve (None = all)
            
        Returns:
            Approval summary
        """
        try:
            # Build the query
            query = self.client.table('feedme_examples')\
                .update({
                    "approved_at": datetime.utcnow().isoformat(),
                    "approved_by": approved_by,
                    "supabase_synced": True,
                    "supabase_sync_at": datetime.utcnow().isoformat()
                })\
                .eq('conversation_id', conversation_id)
            
            # Filter by specific examples if provided
            if example_ids:
                query = query.in_('id', example_ids)
            
            response = query.execute()
            
            approved_count = len(response.data) if response.data else 0
            
            # Update conversation status
            await self._update_conversation_status(conversation_id, 'approved')
            
            return {
                "conversation_id": conversation_id,
                "approved_count": approved_count,
                "approved_by": approved_by,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error approving examples: {e}")
            raise
    
    async def search_examples(
        self,
        query_embedding: List[float],
        limit: int = 5,
        similarity_threshold: float = 0.7,
        folder_ids: Optional[List[int]] = None,
        only_approved: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search for examples
        
        Args:
            query_embedding: Query vector embedding
            limit: Maximum results to return
            similarity_threshold: Minimum similarity score
            folder_ids: Filter by specific folders
            only_approved: Only search approved examples
            
        Returns:
            List of similar examples with scores
        """
        try:
            # Build RPC call for vector search
            params = {
                "query_embedding": query_embedding,
                "match_threshold": similarity_threshold,
                "match_count": limit
            }
            
            # Add filters
            filters = []
            if only_approved:
                filters.append("approved_at IS NOT NULL")
            if folder_ids:
                # Join with conversations to filter by folder
                filters.append(f"conversation_id IN (SELECT id FROM feedme_conversations WHERE folder_id = ANY(ARRAY[{','.join(map(str, folder_ids))}]))")
            
            if filters:
                params["filter"] = " AND ".join(filters)
            
            # Call vector search function (needs to be created in Supabase)
            response = self.client.rpc('search_feedme_examples', params).execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"Error searching examples: {e}")
            raise
    
    # =====================================================
    # SYNC OPERATIONS
    # =====================================================
    
    async def get_unsynced_examples(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get approved examples that haven't been synced to Supabase"""
        try:
            response = self.client.table('feedme_examples')\
                .select('*')\
                .eq('supabase_synced', False)\
                .not_.is_('approved_at', 'null')\
                .limit(limit)\
                .execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"Error getting unsynced examples: {e}")
            raise
    
    async def mark_examples_synced(self, example_ids: List[int]) -> int:
        """Mark examples as synced to Supabase"""
        try:
            response = self.client.table('feedme_examples')\
                .update({
                    "supabase_synced": True,
                    "supabase_sync_at": datetime.utcnow().isoformat()
                })\
                .in_('id', example_ids)\
                .execute()
            
            count = len(response.data) if response.data else 0
            logger.info(f"Marked {count} examples as synced")
            return count
            
        except Exception as e:
            logger.error(f"Error marking examples as synced: {e}")
            raise
    
    # =====================================================
    # UTILITY METHODS
    # =====================================================
    
    async def _update_conversation_status(self, conversation_id: int, status: str):
        """Update conversation processing status"""
        try:
            self.client.table('feedme_conversations')\
                .update({"processing_status": status})\
                .eq('id', conversation_id)\
                .execute()
        except Exception as e:
            logger.warning(f"Failed to update conversation status: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Supabase connection health"""
        try:
            # Test basic query
            response = self.client.table('feedme_folders').select('count').execute()
            
            # Test vector extension
            vector_test = self.client.rpc('test_vector_extension').execute()
            
            return {
                "status": "healthy",
                "folders_count": response.data[0]['count'] if response.data else 0,
                "vector_extension": vector_test.data if vector_test else False,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# Global client instance
_supabase_client: Optional[SupabaseClient] = None


def get_supabase_client() -> SupabaseClient:
    """Get or create global Supabase client instance"""
    global _supabase_client
    
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
    
    return _supabase_client


@asynccontextmanager
async def supabase_transaction():
    """
    Context manager for Supabase transactions
    Note: Supabase doesn't have native transaction support via REST API,
    so this is a placeholder for future enhancement
    """
    client = get_supabase_client()
    try:
        yield client
    except Exception as e:
        logger.error(f"Transaction error: {e}")
        raise


# Export main components
__all__ = [
    'SupabaseClient',
    'SupabaseConfig',
    'get_supabase_client',
    'supabase_transaction'
]