"""
Supabase Client Wrapper for FeedMe Integration

Provides typed helpers for Supabase operations including folder management,
conversation persistence, and example synchronization.
"""

import os
import logging
import threading
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import asyncio
from contextlib import asynccontextmanager

# Note: supabase-py must be installed: pip install supabase
from supabase import create_client, Client
from postgrest.exceptions import APIError

from app.db.cache import get_analytics_cache, CACHE_TTL

logger = logging.getLogger(__name__)


class SupabaseConfig:
    """Configuration for Supabase connection"""
    def __init__(self):
        raw_url = os.environ.get('SUPABASE_URL', '')
        raw_anon = os.environ.get('SUPABASE_ANON_KEY', '')
        raw_service = os.environ.get('SUPABASE_SERVICE_KEY', '')

        self.url = raw_url.strip() or None
        self.anon_key = raw_anon.strip() or None
        self.service_key = raw_service.strip() or None  # Optional for admin operations
        
        if not self.url or not self.anon_key:
            logger.warning(
                "Supabase not configured. FeedMe functionality will be limited. "
                "Set SUPABASE_URL and SUPABASE_ANON_KEY environment variables for full functionality."
            )
            # Set None values to indicate mock mode
            self.url = None
            self.anon_key = None
            self.key = None
            self.mock_mode = True
        else:
            # Use service key if available for server-side operations
            self.key = self.service_key if self.service_key else self.anon_key
            self.mock_mode = False


class SupabaseClient:
    """
    Supabase client wrapper with typed operations for FeedMe integration
    """

    def __init__(self, config: Optional[SupabaseConfig] = None):
        self.config = config or SupabaseConfig()
        self._client: Optional[Client] = None
        self.mock_mode = getattr(self.config, 'mock_mode', False)
        
        if not self.mock_mode:
            self._initialize_client()
        else:
            logger.info("Running in mock mode - no Supabase connection")
    
    def _initialize_client(self):
        """Initialize Supabase client"""
        try:
            if self.config.url and self.config.key:
                self._client = create_client(self.config.url, self.config.key)
                logger.info("Supabase client initialized successfully")
            else:
                raise ValueError("Cannot initialize client without URL and key")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            self.mock_mode = True
            self._client = None
    
    @property
    def client(self) -> Client:
        """Get Supabase client instance"""
        if self.mock_mode:
            raise RuntimeError(
                "Supabase client not available in mock mode. "
                "Please configure SUPABASE_URL and SUPABASE_ANON_KEY environment variables."
            )
        if not self._client:
            self._initialize_client()
        return self._client

    # Lightweight mock query/table helpers so callers can continue in mock mode without blowing up
    class _MockQuery:
        def __init__(self):
            self.data = []
            self.count = 0

        # Passthrough chainers
        def select(self, *args, **kwargs): return self
        def insert(self, *args, **kwargs): return self
        def update(self, *args, **kwargs): return self
        def delete(self, *args, **kwargs): return self
        def eq(self, *args, **kwargs): return self
        def order(self, *args, **kwargs): return self
        def range(self, *args, **kwargs): return self
        def single(self, *args, **kwargs): return self
        def execute(self): return self

    class _MockTable(_MockQuery):
        pass

    def table(self, name: str):
        """
        Mirror supabase-py table() API. Returns a mock table in mock_mode to avoid attribute errors.
        """
        if self.mock_mode:
            logger.debug("Supabase mock_mode active - returning mock table for %s", name)
            return self._MockTable()
        return self.client.table(name)

    def rpc(self, fn_name: str, params: Optional[Dict[str, Any]] = None):
        """
        Mirror supabase-py rpc() API. Returns a mock query in mock_mode so callers can
        degrade gracefully when Supabase is not configured.
        """
        if self.mock_mode:
            logger.debug("Supabase mock_mode active - returning mock rpc for %s", fn_name)
            return self._MockQuery()
        if params is None:
            return self.client.rpc(fn_name)
        return self.client.rpc(fn_name, params)

    async def _exec(self, fn, timeout: float = 30):
        """Run blocking Supabase SDK call in a thread with a timeout."""
        try:
            loop = asyncio.get_running_loop()
            return await asyncio.wait_for(loop.run_in_executor(None, fn), timeout=timeout)
        except Exception as e:
            logger.error(f"Supabase exec failed: {e}")
            raise
    
    # =====================================================
    # GLOBAL KNOWLEDGE OPERATIONS
    # =====================================================

    async def insert_sparrow_feedback(
        self,
        *,
        user_id: str,
        feedback_text: str,
        selected_text: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Insert a feedback submission row and return the created record."""

        payload: Dict[str, Any] = {
            "user_id": user_id,
            "feedback_text": feedback_text,
            "selected_text": selected_text,
            "attachments": attachments or [],
            "metadata": metadata or {},
        }

        if embedding is not None:
            payload["embedding"] = embedding

        try:
            response = await self._exec(
                lambda: self.client.table("sparrow_feedback").insert(payload).execute()
            )

            if response.data:
                row = response.data[0]
                logger.debug(
                    "Inserted sparrow_feedback row (id=%s)",
                    row.get("id"),
                )
                return row

            logger.warning("Supabase insert_sparrow_feedback returned no data")
            return None
        except Exception as exc:
            logger.error("Failed to insert sparrow_feedback row: %s", exc)
            return None

    async def insert_sparrow_correction(
        self,
        *,
        user_id: str,
        incorrect_text: str,
        corrected_text: str,
        explanation: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Insert a correction submission row and return the created record."""

        payload: Dict[str, Any] = {
            "user_id": user_id,
            "incorrect_text": incorrect_text,
            "corrected_text": corrected_text,
            "explanation": explanation,
            "attachments": attachments or [],
            "metadata": metadata or {},
        }

        if embedding is not None:
            payload["embedding"] = embedding

        try:
            response = await self._exec(
                lambda: self.client.table("sparrow_corrections").insert(payload).execute()
            )

            if response.data:
                row = response.data[0]
                logger.debug(
                    "Inserted sparrow_corrections row (id=%s)",
                    row.get("id"),
                )
                return row

            logger.warning("Supabase insert_sparrow_correction returned no data")
            return None
        except Exception as exc:
            logger.error("Failed to insert sparrow_corrections row: %s", exc)
            return None

    async def list_sparrow_feedback(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        try:
            query = self.client.table("sparrow_feedback").select("*")
            if status:
                query = query.eq("status", status)
            response = await self._exec(
                lambda: query.order("created_at", desc=True).limit(limit).execute()
            )
            return response.data or []
        except Exception as exc:
            logger.error("Failed to list sparrow_feedback rows: %s", exc)
            return []

    async def list_sparrow_corrections(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        try:
            query = self.client.table("sparrow_corrections").select("*")
            if status:
                query = query.eq("status", status)
            response = await self._exec(
                lambda: query.order("created_at", desc=True).limit(limit).execute()
            )
            return response.data or []
        except Exception as exc:
            logger.error("Failed to list sparrow_corrections rows: %s", exc)
            return []

    async def get_sparrow_feedback(self, feedback_id: int) -> Optional[Dict[str, Any]]:
        try:
            response = await self._exec(
                lambda: self.client
                .table("sparrow_feedback")
                .select("*")
                .eq("id", feedback_id)
                .limit(1)
                .execute()
            )
            data = getattr(response, "data", None)
            if data:
                return data[0]
            return None
        except APIError as exc:
            if getattr(exc, "code", None) in {"PGRST116", "PGRST103"}:
                return None
            logger.error("Supabase error fetching sparrow_feedback id=%s: %s", feedback_id, exc)
            return None
        except Exception as exc:
            logger.error("Failed to fetch sparrow_feedback id=%s: %s", feedback_id, exc)
            return None

    async def get_sparrow_correction(self, correction_id: int) -> Optional[Dict[str, Any]]:
        try:
            response = await self._exec(
                lambda: self.client
                .table("sparrow_corrections")
                .select("*")
                .eq("id", correction_id)
                .limit(1)
                .execute()
            )
            data = getattr(response, "data", None)
            if data:
                return data[0]
            return None
        except APIError as exc:
            if getattr(exc, "code", None) in {"PGRST116", "PGRST103"}:
                return None
            logger.error("Supabase error fetching sparrow_corrections id=%s: %s", correction_id, exc)
            return None
        except Exception as exc:
            logger.error("Failed to fetch sparrow_corrections id=%s: %s", correction_id, exc)
            return None

    async def update_sparrow_feedback_status(
        self,
        feedback_id: int,
        *,
        status: str,
    ) -> Optional[Dict[str, Any]]:
        payload = {"status": status}
        try:
            response = await self._exec(
                lambda: self.client
                .table("sparrow_feedback")
                .update(payload)
                .eq("id", feedback_id)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as exc:
            logger.error("Failed to update sparrow_feedback id=%s: %s", feedback_id, exc)
            return None

    async def update_sparrow_correction_status(
        self,
        correction_id: int,
        *,
        status: str,
    ) -> Optional[Dict[str, Any]]:
        payload = {"status": status}
        try:
            response = await self._exec(
                lambda: self.client
                .table("sparrow_corrections")
                .update(payload)
                .eq("id", correction_id)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as exc:
            logger.error("Failed to update sparrow_corrections id=%s: %s", correction_id, exc)
            return None

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
            # Only include fields that exist in the database schema
            data = {
                "name": name,
                "color": color,
                "description": description,
                "created_by": created_by
            }
            
            # Remove None values to avoid database errors
            data = {k: v for k, v in data.items() if v is not None}
            
            response = await self._exec(lambda: self.client.table('feedme_folders').insert(data).execute())
            
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
        update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing folder with provided data
        
        Args:
            folder_id: The ID of the folder to update
            update_data: Dictionary containing fields to update
            
        Returns:
            Updated folder data if successful, None otherwise
        """
        try:
            # Filter valid fields for folder updates
            valid_fields = {'name', 'color', 'description', 'parent_id'}
            filtered_data = {k: v for k, v in update_data.items() if k in valid_fields}
            
            if not filtered_data:
                logger.warning(f"No valid fields to update for folder {folder_id}")
                return None
            
            # Add updated timestamp
            filtered_data['updated_at'] = datetime.now().isoformat()
            
            response = await self._exec(lambda: self.client.table('feedme_folders')
                .update(filtered_data)
                .eq('id', folder_id)
                .execute())
            
            if response.data and len(response.data) > 0:
                logger.info(f"Updated folder ID: {folder_id} with fields: {list(filtered_data.keys())}")
                return response.data[0]
            else:
                logger.warning(f"Folder {folder_id} not found for update")
                return None
                
        except Exception as e:
            logger.error(f"Error updating folder {folder_id}: {e}")
            raise
    
    async def delete_folder(self, folder_id: int) -> bool:
        """Delete a folder (cascades to child folders)"""
        try:
            response = await self._exec(lambda: self.client.table('feedme_folders')
                .delete()
                .eq('id', folder_id)
                .execute())
            
            logger.info(f"Deleted folder ID: {folder_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting folder: {e}")
            raise
    
    async def list_folders(self) -> List[Dict[str, Any]]:
        """List all folders with stats"""
        try:
            # Query the folder stats view for enriched data
            response = await self._exec(lambda: self.client.table('feedme_folder_stats')
                .select('*')
                .order('folder_path')
                .execute())
            
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
        uploaded_by: Optional[str] = None,
        mime_type: Optional[str] = None,
        pages: Optional[int] = None,
        pdf_metadata: Optional[Dict] = None,
        processing_method: Optional[str] = None
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
                "processing_status": "pending",
                "mime_type": mime_type,
                "pages": pages,
                "pdf_metadata": pdf_metadata,
                # Include processing method to avoid NULLs that break Pydantic enum validation
                "processing_method": processing_method or "pdf_ai",
            }
            
            response = await self._exec(lambda: self.client.table('feedme_conversations').insert(data).execute())
            
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
            # Use `maybe_single()` to explicitly request a single row. This returns
            # `None` when no rows are found instead of an empty list, which makes it
            # easier to distinguish between "not found" and other error cases.
            response = await self._exec(lambda: (
                self.client.table('feedme_conversations')
                .select('*')
                .eq('id', conversation_id)
                .maybe_single()
                .execute()
            ))

            if response.data:
                logger.info(f"Retrieved conversation {conversation_id}")
                return response.data

            # If we reach here, the conversation does not exist.
            logger.warning("Conversation %s not found", conversation_id)
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
            count_query = self.client.table('feedme_conversations').select('id', count='exact')
            
            # Apply filters
            if filters:
                if 'folder_id' in filters:
                    if filters['folder_id'] is None:
                        query = query.is_('folder_id', 'null')
                        count_query = count_query.is_('folder_id', 'null')
                    else:
                        query = query.eq('folder_id', filters['folder_id'])
                        count_query = count_query.eq('folder_id', filters['folder_id'])
                
                if 'processing_status' in filters:
                    query = query.eq('processing_status', filters['processing_status'])
                    count_query = count_query.eq('processing_status', filters['processing_status'])
                
                if 'uploaded_by' in filters:
                    query = query.eq('uploaded_by', filters['uploaded_by'])
                    count_query = count_query.eq('uploaded_by', filters['uploaded_by'])
            
            # Apply pagination
            query = query.order('created_at', desc=True)\
                         .range(offset, offset + limit - 1)
            
            response = await self._exec(lambda: query.execute())
            
            # Get total count for pagination
            count_response = await self._exec(lambda: count_query.execute())
            
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
            
            response = await self._exec(lambda: self.client.table('feedme_conversations')
                .update(updates)
                .eq('id', conversation_id)
                .execute())
            
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
        Delete a conversation and all its associated data
        
        Args:
            conversation_id: The ID of the conversation to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            # Delete associated text chunks first (if they exist)
            try:
                chunks_response = await self._exec(lambda: self.client.table('feedme_text_chunks')
                    .delete()
                    .eq('conversation_id', conversation_id)
                    .execute())
                chunks_count = len(chunks_response.data) if chunks_response.data else 0
            except Exception as e:
                # Table might not exist or have no chunks - that's OK
                logger.debug(f"No text chunks to delete for conversation {conversation_id}: {e}")
                chunks_count = 0

            # Delete associated examples next
            try:
                examples_response = await self._exec(lambda: self.client.table('feedme_examples')
                    .delete()
                    .eq('conversation_id', conversation_id)
                    .execute())
                examples_count = len(examples_response.data) if examples_response.data else 0
            except Exception as e:
                logger.debug(f"No examples to delete for conversation {conversation_id}: {e}")
                examples_count = 0
            
            # Then delete the conversation
            conversation_response = await self._exec(lambda: self.client.table('feedme_conversations')
                .delete()
                .eq('id', conversation_id)
                .execute())
            
            if conversation_response.data:
                logger.info(
                    f"Deleted conversation {conversation_id} with {chunks_count} text chunks and {examples_count} examples"
                )
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
            response = await self._exec(lambda: self.client.table('feedme_conversations')
                .update({"folder_id": folder_id})
                .eq('id', conversation_id)
                .execute())
            
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
            # Handle special case for UNASSIGNED_FOLDER_ID (0) - set to NULL
            effective_folder_id = None if folder_id == 0 else folder_id
            
            response = await self._exec(lambda: self.client.table('feedme_conversations')
                .update({"folder_id": effective_folder_id})
                .in_('id', conversation_ids)
                .execute())
            
            count = len(response.data) if response.data else 0
            logger.info(f"Assigned {count} conversations to folder {effective_folder_id} (input: {folder_id})")
            return count
            
        except Exception as e:
            logger.error(f"Error bulk assigning conversations: {e}")
            raise
    
    # =====================================================
    # EXAMPLE OPERATIONS
    # =====================================================
    
    async def get_example_by_id(self, example_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve an example by its ID from Supabase
        
        Args:
            example_id: The ID of the example to retrieve
            
        Returns:
            Dict containing example data if found, None otherwise
        """
        try:
            response = await self._exec(lambda: self.client.table('feedme_examples')
                .select('*')
                .eq('id', example_id)
                .execute())
            
            if response.data and len(response.data) > 0:
                logger.info(f"Retrieved example {example_id}")
                return response.data[0]
            else:
                logger.warning(f"Example {example_id} not found")
                return None
                
        except Exception as e:
            logger.error(f"Error retrieving example {example_id}: {e}")
            return None
    
    async def update_example(
        self,
        example_id: int,
        update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an example with new data
        
        Args:
            example_id: The ID of the example to update
            update_data: Dictionary of fields to update
            
        Returns:
            Updated example data if successful, None otherwise
        """
        try:
            # Add updated_at timestamp
            update_data['updated_at'] = datetime.now().isoformat()
            
            response = await self._exec(lambda: self.client.table('feedme_examples')
                .update(update_data)
                .eq('id', example_id)
                .execute())
            
            if response.data and len(response.data) > 0:
                logger.info(f"Updated example {example_id}")
                return response.data[0]
            else:
                logger.warning(f"Example {example_id} not found for update")
                return None
                
        except Exception as e:
            logger.error(f"Error updating example {example_id}: {e}")
            return None
    
    async def get_example_with_conversation(self, example_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve an example with its conversation data
        
        Args:
            example_id: The ID of the example to retrieve
            
        Returns:
            Dict containing example and conversation data if found, None otherwise
        """
        try:
            response = await self._exec(lambda: self.client.table('feedme_examples')
                .select('*, feedme_conversations(*)')
                .eq('id', example_id)
                .execute())
            
            if response.data and len(response.data) > 0:
                logger.info(f"Retrieved example {example_id} with conversation")
                return response.data[0]
            else:
                logger.warning(f"Example {example_id} not found")
                return None
                
        except Exception as e:
            logger.error(f"Error retrieving example {example_id} with conversation: {e}")
            return None
    
    async def delete_example(self, example_id: int) -> bool:
        """
        Delete an example and update conversation example count
        
        Args:
            example_id: The ID of the example to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            # First get the example to know which conversation to update
            example = await self.get_example_by_id(example_id)
            if not example:
                logger.warning(f"Example {example_id} not found for deletion")
                return False
            
            conversation_id = example['conversation_id']
            
            # Delete the example
            response = await self._exec(lambda: self.client.table('feedme_examples')
                .delete()
                .eq('id', example_id)
                .execute())
            
            if response.data:
                # Update conversation example count
                await self.update_conversation_example_count(conversation_id)
                logger.info(f"Deleted example {example_id}")
                return True
            else:
                logger.warning(f"Example {example_id} not found for deletion")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting example {example_id}: {e}")
            return False
    
    async def update_conversation_example_count(self, conversation_id: int) -> bool:
        """
        Update the total_examples count for a conversation
        
        Args:
            conversation_id: The ID of the conversation to update
            
        Returns:
            True if update was successful, False otherwise
        """
        try:
            # Count examples for this conversation
            count_response = await self._exec(lambda: self.client.table('feedme_examples')
                .select('id', count='exact')
                .eq('conversation_id', conversation_id)
                .execute())
            
            example_count = count_response.count if count_response.count is not None else 0
            
            # Update the conversation
            response = await self._exec(lambda: self.client.table('feedme_conversations')
                .update({'total_examples': example_count, 'updated_at': datetime.now().isoformat()})
                .eq('id', conversation_id)
                .execute())
            
            if response.data:
                logger.info(f"Updated conversation {conversation_id} example count to {example_count}")
                return True
            else:
                logger.warning(f"Conversation {conversation_id} not found for example count update")
                return False
                
        except Exception as e:
            logger.error(f"Error updating conversation {conversation_id} example count: {e}")
            return False
    
    async def get_conversation_by_id(self, conversation_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a conversation by its ID from Supabase
        Alias for get_conversation for API compatibility
        
        Args:
            conversation_id: The ID of the conversation to retrieve
            
        Returns:
            Dict containing conversation data if found, None otherwise
        """
        return await self.get_conversation(conversation_id)
    
    async def approve_examples(
        self,
        example_ids: List[int],
        approved_by: str
    ) -> List[Dict[str, Any]]:
        """
        Approve specific examples by ID
        
        Args:
            example_ids: List of example IDs to approve
            approved_by: User approving the examples
            
        Returns:
            List of approved examples
        """
        try:
            response = await self._exec(lambda: self.client.table('feedme_examples')
                .update({
                    "reviewed_at": datetime.utcnow().isoformat(),
                    "reviewed_by": approved_by,
                    "review_status": "approved",
                    "supabase_sync_status": "synced",
                    "supabase_sync_at": datetime.utcnow().isoformat()
                })
                .in_('id', example_ids)
                .execute())
            
            approved_examples = response.data if response.data else []
            logger.info(f"Approved {len(approved_examples)} examples")
            return approved_examples
            
        except Exception as e:
            logger.error(f"Error approving examples: {e}")
            raise
    
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
            
            response = await self._exec(lambda: self.client.table('feedme_examples').insert(examples).execute())
            
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
                    "reviewed_at": datetime.utcnow().isoformat(),
                    "reviewed_by": approved_by,
                    "review_status": "approved",
                    "supabase_sync_status": "synced",
                    "supabase_sync_at": datetime.utcnow().isoformat()
                })\
                .eq('conversation_id', conversation_id)
            
            # Filter by specific examples if provided
            if example_ids:
                query = query.in_('id', example_ids)
            
            response = await self._exec(lambda: query.execute())
            
            approved_count = len(response.data) if response.data else 0
            
            # Update conversation status to approved
            await self.update_conversation(conversation_id, {'approval_status': 'approved'})
            
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
            response = await self._exec(lambda: self.rpc('search_feedme_examples', params).execute())
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"Error searching examples: {e}")
            raise

    async def search_kb_articles(
        self,
        query_embedding: List[float],
        limit: int = 5,
        similarity_threshold: float = 0.25,
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search for Mailbird knowledge base articles via RPC.

        Args:
            query_embedding: 3072-dim embedding vector for the query
            limit: Maximum number of results to return
            similarity_threshold: Minimum cosine similarity (0..1)

        Returns:
            List of rows with keys: id, url, markdown, content, metadata, similarity
        """
        try:
            if self.mock_mode:
                logger.info("search_kb_articles called in mock mode; returning empty list")
                return []

            from app.db.embedding_config import EXPECTED_DIM as expected_dim
            if len(query_embedding) != expected_dim:
                logger.error(
                    "search_kb_articles received embedding with unexpected dimension %s (expected %s)",
                    len(query_embedding),
                    expected_dim,
                )
                return []

            # Clamp inputs to safe bounds
            try:
                limit = max(1, min(int(limit or 5), 50))
            except Exception:
                limit = 5
            try:
                similarity_threshold = float(similarity_threshold or 0.25)
                similarity_threshold = 0.0 if similarity_threshold < 0 else similarity_threshold
                similarity_threshold = 1.0 if similarity_threshold > 1 else similarity_threshold
            except Exception:
                similarity_threshold = 0.25

            params = {
                "query_embedding": query_embedding,
                "match_count": limit,
                "match_threshold": similarity_threshold,
            }

            response = await self._exec(lambda: self.rpc("search_mailbird_knowledge", params).execute())
            return response.data or []
        except APIError as e:
            try:
                dim = len(query_embedding) if isinstance(query_embedding, list) else None
            except Exception:
                dim = None
            params_val = params if "params" in locals() else None
            logger.error(
                "Supabase RPC error in search_mailbird_knowledge (dim=%s, count=%s): %s",
                dim,
                params_val.get("match_count") if isinstance(params_val, dict) else None,
                e,
            )
            return []
        except Exception as e:
            try:
                dim = len(query_embedding) if isinstance(query_embedding, list) else None
            except Exception:
                dim = None
            params_val = params if "params" in locals() else None
            logger.error(
                "Error searching knowledge base via RPC (dim=%s, count=%s): %s",
                dim,
                params_val.get("match_count") if isinstance(params_val, dict) else None,
                e,
            )
            return []
    
    # =====================================================
    # SYNC OPERATIONS
    # =====================================================

    async def search_web_snapshots(
        self,
        query_embedding: List[float],
        match_count: int = 5,
        match_threshold: float = 0.4,
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search for Tavily saved web research snapshots via RPC.

        Args:
            query_embedding: 3072-dim embedding vector for the query
            match_count: Maximum number of results to return
            match_threshold: Minimum cosine similarity (0..1)

        Returns:
            List of rows with keys: id, url, title, content, source_domain, published_at, similarity
        """
        try:
            if self.mock_mode:
                logger.info("search_web_snapshots called in mock mode; returning empty list")
                return []

            from app.db.embedding_config import EXPECTED_DIM as expected_dim
            if len(query_embedding) != expected_dim:
                logger.error(
                    "search_web_snapshots received embedding with unexpected dimension %s (expected %s)",
                    len(query_embedding),
                    expected_dim,
                )
                return []

            # Clamp inputs to safe bounds
            try:
                match_count = max(1, min(int(match_count or 5), 50))
            except Exception:
                match_count = 5
            try:
                match_threshold = float(match_threshold or 0.4)
                match_threshold = 0.0 if match_threshold < 0 else match_threshold
                match_threshold = 1.0 if match_threshold > 1 else match_threshold
            except Exception:
                match_threshold = 0.4

            params = {
                "query_embedding": query_embedding,
                "match_count": match_count,
                "match_threshold": match_threshold,
            }

            response = await self._exec(
                lambda: self.rpc("search_web_research_snapshots", params).execute()
            )
            return response.data or []
        except APIError as e:
            try:
                dim = len(query_embedding) if isinstance(query_embedding, list) else None
            except Exception:
                dim = None
            logger.error(
                "Supabase RPC error in search_web_research_snapshots (dim=%s, count=%s, threshold=%s): %s",
                dim,
                params.get("match_count") if isinstance(params, dict) else None,
                params.get("match_threshold") if isinstance(params, dict) else None,
                e,
            )
            return []
        except Exception as e:
            try:
                dim = len(query_embedding) if isinstance(query_embedding, list) else None
            except Exception:
                dim = None
            logger.error(
                "Error searching web research snapshots (dim=%s, count=%s, threshold=%s): %s",
                dim,
                params.get("match_count") if isinstance(params, dict) else None,
                params.get("match_threshold") if isinstance(params, dict) else None,
                e,
            )
            return []
    
    async def get_unsynced_examples(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get approved examples that haven't been synced to Supabase"""
        try:
            response = await self._exec(lambda: self.client.table('feedme_examples')
                .select('*')
                .eq('supabase_synced', False)
                .not_.is_('approved_at', 'null')
                .limit(limit)
                .execute())
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"Error getting unsynced examples: {e}")
            raise
    
    async def mark_examples_synced(self, example_ids: List[int]) -> int:
        """Mark examples as synced to Supabase"""
        try:
            response = await self._exec(lambda: self.client.table('feedme_examples')
                .update({
                    "supabase_synced": True,
                    "supabase_sync_at": datetime.utcnow().isoformat()
                })
                .in_('id', example_ids)
                .execute())
            
            count = len(response.data) if response.data else 0
            logger.info(f"Marked {count} examples as synced")
            return count
            
        except Exception as e:
            logger.error(f"Error marking examples as synced: {e}")
            raise
    
    # =====================================================
    # ADVANCED OPERATIONS FOR COMPLETE MIGRATION
    # =====================================================
    
    async def get_conversations_with_pagination(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        folder_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get paginated conversations with filtering
        
        Args:
            page: Page number (1-based)
            page_size: Number of items per page
            status: Filter by processing status
            uploaded_by: Filter by uploader
            folder_id: Filter by folder ID
            
        Returns:
            Dict with conversations, pagination, and stats
        """
        try:
            offset = (page - 1) * page_size
            
            # Build the query
            query = self.client.table('feedme_conversations').select('*')
            count_query = self.client.table('feedme_conversations').select('id', count='exact')
            
            # Apply filters
            if status:
                query = query.eq('processing_status', status)
                count_query = count_query.eq('processing_status', status)
            
            if uploaded_by:
                query = query.eq('uploaded_by', uploaded_by)
                count_query = count_query.eq('uploaded_by', uploaded_by)
            
            if folder_id is not None:
                if folder_id == 0:  # Special case for "no folder"
                    query = query.is_('folder_id', 'null')
                    count_query = count_query.is_('folder_id', 'null')
                else:
                    query = query.eq('folder_id', folder_id)
                    count_query = count_query.eq('folder_id', folder_id)
            
            # Execute with pagination
            query = query.order('created_at', desc=True).range(offset, offset + page_size - 1)
            
            # Get data and count in parallel
            response = await self._exec(lambda: query.execute())
            count_response = await self._exec(lambda: count_query.execute())
            
            total_count = count_response.count if count_response.count is not None else 0
            conversations = response.data if response.data else []
            
            return {
                "conversations": conversations,
                "total_count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": (total_count + page_size - 1) // page_size,
                "has_next": offset + page_size < total_count,
                "has_prev": page > 1
            }
            
        except Exception as e:
            logger.error(f"Error getting paginated conversations: {e}")
            return {
                "conversations": [],
                "total_count": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
                "has_next": False,
                "has_prev": False
            }
    
    async def get_conversation_analytics(self) -> Dict[str, Any]:
        """
        Get comprehensive conversation analytics using optimized RPC function.

        Uses database-side aggregation via get_conversation_analytics() RPC
        and Redis caching for improved performance (100x faster than client-side).

        Returns:
            Dict containing analytics data
        """
        # Check cache first
        cache = get_analytics_cache()
        cached = cache.get("conversation_analytics")
        if cached is not None:
            return cached

        try:
            # Use optimized RPC function for single-query aggregation
            response = await self._exec(lambda: self.rpc(
                'get_conversation_analytics'
            ).execute())

            if response.data:
                result = {
                    "total_conversations": response.data.get("total_conversations", 0),
                    "total_examples": response.data.get("total_examples", 0),
                    "total_text_chunks": response.data.get("total_text_chunks", 0),
                    "status_breakdown": response.data.get("status_breakdown", {}),
                    "approval_breakdown": response.data.get("approval_breakdown", {}),
                    "avg_quality_score": response.data.get("avg_quality_score", 0),
                    "generated_at": datetime.utcnow().isoformat()
                }
            else:
                result = {
                    "total_conversations": 0,
                    "total_examples": 0,
                    "total_text_chunks": 0,
                    "status_breakdown": {},
                    "approval_breakdown": {},
                    "avg_quality_score": 0,
                    "generated_at": datetime.utcnow().isoformat()
                }

            # Cache result
            cache.set("conversation_analytics", result)
            return result

        except Exception as e:
            logger.error(f"Error getting conversation analytics: {e}")
            return {
                "total_conversations": 0,
                "total_examples": 0,
                "total_text_chunks": 0,
                "status_breakdown": {},
                "approval_breakdown": {},
                "avg_quality_score": 0,
                "generated_at": datetime.utcnow().isoformat()
            }
    
    async def get_conversation_processing_stats(self, conversation_id: int) -> Dict[str, Any]:
        """
        Get detailed processing statistics for a conversation
        
        Args:
            conversation_id: The conversation ID
            
        Returns:
            Dict containing processing stats
        """
        try:
            # Get conversation with examples count
            conversation_response = await self._exec(lambda: self.client.table('feedme_conversations')
                .select('*')
                .eq('id', conversation_id)
                .execute())
            
            if not conversation_response.data:
                raise Exception(f"Conversation {conversation_id} not found")
            
            conversation = conversation_response.data[0]
            
            # Get examples stats
            examples_response = await self._exec(lambda: self.client.table('feedme_examples')
                .select('confidence_score, usefulness_score, review_status')
                .eq('conversation_id', conversation_id)
                .execute())
            
            examples = examples_response.data or []
            
            # Calculate stats
            total_examples = len(examples)
            high_quality = len([e for e in examples if e.get('confidence_score', 0) >= 0.8])
            medium_quality = len([e for e in examples if 0.5 <= e.get('confidence_score', 0) < 0.8])
            low_quality = len([e for e in examples if e.get('confidence_score', 0) < 0.5])
            
            avg_confidence = sum([e.get('confidence_score', 0) for e in examples]) / max(total_examples, 1)
            avg_usefulness = sum([e.get('usefulness_score', 0) for e in examples]) / max(total_examples, 1)
            
            # Review status breakdown
            review_stats = {}
            for example in examples:
                status = example.get('review_status', 'pending')
                review_stats[status] = review_stats.get(status, 0) + 1
            
            return {
                "conversation_id": conversation_id,
                "processing_status": conversation.get('processing_status'),
                "total_examples": total_examples,
                "quality_breakdown": {
                    "high_quality": high_quality,
                    "medium_quality": medium_quality,
                    "low_quality": low_quality
                },
                "average_scores": {
                    "confidence": round(avg_confidence, 3),
                    "usefulness": round(avg_usefulness, 3)
                },
                "review_breakdown": review_stats,
                "processing_time_ms": conversation.get('processing_time_ms'),
                "file_size_bytes": conversation.get('file_size_bytes')
            }
            
        except Exception as e:
            logger.error(f"Error getting conversation processing stats: {e}")
            raise
    
    async def get_approval_workflow_stats(self) -> Dict[str, Any]:
        """
        Get approval workflow statistics using optimized RPC function.

        Uses database-side aggregation via get_approval_workflow_stats() RPC
        and Redis caching for improved performance.

        Returns:
            Dict containing approval workflow stats
        """
        # Check cache first
        cache = get_analytics_cache()
        cached = cache.get("approval_workflow_stats")
        if cached is not None:
            return cached

        try:
            # Use optimized RPC function for single-query aggregation
            response = await self._exec(lambda: self.rpc(
                'get_approval_workflow_stats'
            ).execute())

            if response.data:
                conv_stats = response.data.get("conversation_stats", {})
                example_stats = response.data.get("example_stats", {})
                recent = response.data.get("recent_approvals", [])

                result = {
                    "conversation_approval": {
                        "total": conv_stats.get("total", 0),
                        "status_breakdown": {
                            "pending": conv_stats.get("pending", 0),
                            "approved": conv_stats.get("approved", 0),
                            "rejected": conv_stats.get("rejected", 0)
                        },
                        "unique_approvers": conv_stats.get("unique_approvers", 0)
                    },
                    "example_stats": {
                        "total": example_stats.get("total", 0),
                        "high_confidence": example_stats.get("high_confidence", 0),
                        "medium_confidence": example_stats.get("medium_confidence", 0),
                        "low_confidence": example_stats.get("low_confidence", 0),
                        "avg_confidence": example_stats.get("avg_confidence", 0)
                    },
                    "recent_approvals": recent or [],
                    "generated_at": datetime.utcnow().isoformat()
                }
            else:
                result = {
                    "conversation_approval": {
                        "total": 0,
                        "status_breakdown": {},
                        "unique_approvers": 0
                    },
                    "example_stats": {
                        "total": 0,
                        "high_confidence": 0,
                        "medium_confidence": 0,
                        "low_confidence": 0,
                        "avg_confidence": 0
                    },
                    "recent_approvals": [],
                    "generated_at": datetime.utcnow().isoformat()
                }

            # Cache result
            cache.set("approval_workflow_stats", result)
            return result

        except Exception as e:
            logger.error(f"Error getting approval workflow stats: {e}")
            return {
                "conversation_approval": {
                    "total": 0,
                    "status_breakdown": {},
                    "unique_approvers": 0,
                },
                "example_stats": {
                    "total": 0,
                    "high_confidence": 0,
                    "medium_confidence": 0,
                    "low_confidence": 0,
                    "avg_confidence": 0,
                },
                "recent_approvals": [],
                "generated_at": datetime.utcnow().isoformat(),
            }
    
    async def bulk_reprocess_conversations(self, conversation_ids: List[int]) -> Dict[str, Any]:
        """
        Bulk reprocess multiple conversations
        
        Args:
            conversation_ids: List of conversation IDs to reprocess
            
        Returns:
            Dict containing operation results
        """
        try:
            successful = []
            failed = []
            
            for conversation_id in conversation_ids:
                try:
                    cid = conversation_id  # capture current ID for async execution
                    # Reset conversation status
                    update_result = await self._exec(lambda cid=cid: self.client.table('feedme_conversations')
                        .update({
                            "processing_status": "pending",
                            "error_message": None,
                            "updated_at": datetime.now().isoformat()
                        })
                        .eq('id', cid)
                        .execute())
                    
                    if update_result.data:
                        successful.append(conversation_id)
                        logger.info(f"Queued conversation {conversation_id} for reprocessing")
                    else:
                        failed.append({
                            "id": conversation_id,
                            "error": "Conversation not found"
                        })
                        
                except Exception as e:
                    failed.append({
                        "id": conversation_id,
                        "error": str(e)
                    })
                    logger.error(f"Failed to reprocess conversation {conversation_id}: {e}")
            
            return {
                "successful": successful,
                "failed": failed,
                "total_requested": len(conversation_ids),
                "successful_count": len(successful),
                "failed_count": len(failed)
            }
            
        except Exception as e:
            logger.error(f"Error in bulk reprocess: {e}")
            raise

    # =====================================================
    # TEXT CHUNKS (FeedMe unified text embeddings)
    # =====================================================

    async def delete_text_chunks_for_conversation(self, conversation_id: int) -> int:
        """Delete existing text chunks for a conversation"""
        try:
            response = await self._exec(lambda: self.client.table('feedme_text_chunks')
                .delete()
                .eq('conversation_id', conversation_id)
                .execute())
            return len(response.data) if response.data else 0
        except Exception as e:
            logger.error(f"Failed to delete text chunks for conversation {conversation_id}: {e}")
            return 0

    async def insert_text_chunk(self, conversation_id: int, folder_id: Optional[int], chunk_index: int, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Insert a text chunk row (without embedding)"""
        try:
            data = {
                'conversation_id': conversation_id,
                'folder_id': folder_id,
                'chunk_index': chunk_index,
                'content': content,
                'metadata': metadata or {}
            }
            response = await self._exec(lambda: self.client.table('feedme_text_chunks').insert(data).execute())
            if response.data:
                return response.data[0]
            raise Exception('No data from insert_text_chunk')
        except Exception as e:
            logger.error(f"Failed to insert text chunk: {e}")
            raise

    async def update_text_chunk_embedding(self, chunk_id: int, embedding: list[float]) -> bool:
        """Update chunk embedding vector"""
        try:
            response = await self._exec(lambda: self.client.table('feedme_text_chunks').update({ 'embedding': embedding }).eq('id', chunk_id).execute())
            return bool(response.data)
        except Exception as e:
            logger.error(f"Failed to update text chunk embedding: {e}")
            return False

    async def search_text_chunks(self, query_embedding: list[float], match_count: int = 10, folder_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search text chunks via RPC similarity function."""
        try:
            # Validate embedding dimension early to avoid RPC call and client access
            from app.db.embedding_config import EXPECTED_DIM as expected_dim
            if len(query_embedding) != expected_dim:
                logger.error(
                    "search_text_chunks received embedding with unexpected dimension %s (expected %s)",
                    len(query_embedding), expected_dim
                )
                return []

            # Clamp inputs to safe bounds
            try:
                match_count = max(1, min(int(match_count or 10), 50))
            except Exception:
                match_count = 10

            params = {
                'query_embedding': query_embedding,
                'match_count': match_count,
                'filter_folder_id': folder_id
            }
            result = await self._exec(lambda: self.rpc('search_feedme_text_chunks', params).execute())
            return result.data or []
        except Exception as e:
            try:
                dim = len(query_embedding) if isinstance(query_embedding, list) else None
            except Exception:
                dim = None
            logger.error(
                "Text chunk search failed (function=search_feedme_text_chunks dim=%s, count=%s, folder_id=%s): %s",
                dim,
                match_count,
                folder_id,
                e,
            )
            return []

    async def get_conversations_by_ids(self, conversation_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Fetch multiple conversations by their IDs.

        Returns a dict keyed by conversation id for fast hydration and only
        selects required fields to minimize payload size.

        Selected fields:
          id, title, metadata, extracted_text, approval_status,
          processing_status, folder_id, created_at
        """
        result: Dict[int, Dict[str, Any]] = {}
        if not conversation_ids:
            return result
        try:
            response = await self._exec(lambda: (
                self.client
                .table('feedme_conversations')
                .select('id,title,metadata,extracted_text,approval_status,processing_status,folder_id,created_at')
                .in_('id', conversation_ids)
                .execute()
            ))
            for row in (response.data or []):
                try:
                    cid = int(row.get('id'))
                except Exception:
                    # Skip rows without valid id
                    continue
                result[cid] = row
            return result
        except Exception as e:
            logger.error(f"Error fetching conversations by ids: {e}")
            return result
    
    async def get_feedme_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive FeedMe system summary using optimized RPC function.

        Uses database-side aggregation via get_feedme_summary() RPC
        and Redis caching for improved performance.

        Returns:
            Dict containing system summary
        """
        # Check cache first
        cache = get_analytics_cache()
        cached = cache.get("feedme_summary")
        if cached is not None:
            return cached

        try:
            # Use optimized RPC function for single-query aggregation
            response = await self._exec(lambda: self.rpc(
                'get_feedme_summary'
            ).execute())

            if response.data:
                conv_data = response.data.get("conversations", {})
                example_data = response.data.get("examples", {})
                folder_data = response.data.get("folders", {})
                chunk_data = response.data.get("text_chunks", {})

                processing_stats = conv_data.get("by_processing_status", {})
                approval_stats = conv_data.get("by_approval_status", {})

                result = {
                    "overview": {
                        "total_conversations": conv_data.get("total", 0),
                        "total_examples": example_data.get("total", 0),
                        "total_folders": folder_data.get("total", 0),
                        "total_text_chunks": chunk_data.get("total", 0),
                        "examples_from_conversations": conv_data.get("total_examples_sum", 0)
                    },
                    "processing_status": processing_stats,
                    "approval_status": approval_stats,
                    "example_stats": {
                        "avg_confidence": example_data.get("avg_confidence", 0)
                    },
                    "system_health": {
                        "pending_processing": processing_stats.get("pending", 0),
                        "failed_processing": processing_stats.get("failed", 0),
                        "pending_approval": approval_stats.get("pending", 0) + approval_stats.get("processed", 0),
                        "active_conversations": conv_data.get("active", 0)
                    },
                    "generated_at": datetime.utcnow().isoformat()
                }
            else:
                result = {
                    "overview": {
                        "total_conversations": 0,
                        "total_examples": 0,
                        "total_folders": 0,
                        "total_text_chunks": 0,
                        "examples_from_conversations": 0
                    },
                    "processing_status": {},
                    "approval_status": {},
                    "example_stats": {"avg_confidence": 0},
                    "system_health": {
                        "pending_processing": 0,
                        "failed_processing": 0,
                        "pending_approval": 0,
                        "active_conversations": 0
                    },
                    "generated_at": datetime.utcnow().isoformat()
                }

            # Cache result
            cache.set("feedme_summary", result)
            return result

        except Exception as e:
            logger.error(f"Error getting FeedMe summary: {e}")
            return {
                "overview": {
                    "total_conversations": 0,
                    "total_examples": 0,
                    "total_folders": 0,
                    "total_text_chunks": 0,
                    "examples_from_conversations": 0,
                },
                "processing_status": {},
                "approval_status": {},
                "example_stats": {"avg_confidence": 0},
                "system_health": {
                    "pending_processing": 0,
                    "failed_processing": 0,
                    "pending_approval": 0,
                    "active_conversations": 0,
                },
                "generated_at": datetime.utcnow().isoformat(),
            }
    
    async def get_folders_with_stats(self) -> List[Dict[str, Any]]:
        """
        Get all folders with conversation statistics
        
        Returns:
            List of folders with stats
        """
        try:
            # Fetch folders along with aggregated conversation counts in a single query
            # The `feedme_conversations(count)` syntax leverages the PostgREST relation that exists
            # via the foreign key between feedme_conversations.folder_id and feedme_folders.id.
            folders_response = await self._exec(lambda: (
                self.client
                .table('feedme_folders')
                .select('id,name,color,description,created_by,created_at,updated_at,feedme_conversations(count)')
                .order('name')
                .execute()
            ))

            folders: List[Dict[str, Any]] = []
            for record in folders_response.data or []:
                related_counts = record.pop('feedme_conversations', []) or []
                count_value = 0
                if isinstance(related_counts, list) and related_counts:
                    raw_count = related_counts[0].get('count')
                    if isinstance(raw_count, int):
                        count_value = raw_count

                record['conversation_count'] = count_value
                folders.append(record)

            # Add special "No Folder" entry (conversations without folder assignment)
            no_folder_response = await self._exec(lambda: (
                self.client
                .table('feedme_conversations')
                .select('id', count='exact')
                .is_('folder_id', 'null')
                .execute()
            ))

            folders.insert(0, {
                'id': None,
                'name': 'No Folder',
                'color': '#6B7280',
                'description': 'Conversations not assigned to any folder',
                'conversation_count': no_folder_response.count or 0,
                'created_at': None,
                'updated_at': None,
                'created_by': None
            })

            return folders
            
        except Exception as e:
            logger.error(f"Error getting folders with stats: {e}")
            raise
    
    async def validate_folder_exists(self, folder_id: int) -> bool:
        """
        Check if a folder exists
        
        Args:
            folder_id: The folder ID to validate
            
        Returns:
            True if folder exists, False otherwise
        """
        try:
            response = await self._exec(lambda: self.client.table('feedme_folders')
                .select('id')
                .eq('id', folder_id)
                .execute())
            
            return bool(response.data)
            
        except Exception as e:
            logger.error(f"Error validating folder {folder_id}: {e}")
            return False
    
    async def move_conversations_to_folder(
        self,
        conversation_ids: List[int],
        target_folder_id: Optional[int]
    ) -> Dict[str, Any]:
        """
        Move multiple conversations to a folder
        
        Args:
            conversation_ids: List of conversation IDs to move
            target_folder_id: Target folder ID (None for no folder)
            
        Returns:
            Dict containing operation results
        """
        try:
            # Validate target folder exists (if not None)
            if target_folder_id is not None:
                folder_exists = await self.validate_folder_exists(target_folder_id)
                if not folder_exists:
                    raise Exception(f"Target folder {target_folder_id} does not exist")
            
            # Perform bulk update
            response = await self._exec(lambda: self.client.table('feedme_conversations')
                .update({
                    "folder_id": target_folder_id,
                    "updated_at": datetime.now().isoformat()
                })
                .in_('id', conversation_ids)
                .execute())
            
            updated_count = len(response.data) if response.data else 0
            
            return {
                "updated_count": updated_count,
                "requested_count": len(conversation_ids),
                "target_folder_id": target_folder_id,
                "conversation_ids": conversation_ids
            }
            
        except Exception as e:
            logger.error(f"Error moving conversations to folder: {e}")
            raise

    # =====================================================
    # UTILITY METHODS
    # =====================================================
    
    async def _update_conversation_status(self, conversation_id: int, status: str):
        """Update conversation processing status"""
        try:
            await self._exec(lambda: self.client.table('feedme_conversations')
                .update({"processing_status": status})
                .eq('id', conversation_id)
                .execute())
        except Exception as e:
            logger.warning(f"Failed to update conversation status: {e}")
    
    async def update_conversation_status(
        self,
        conversation_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Update conversation status and error message
        
        Args:
            conversation_id: The ID of the conversation to update
            status: New processing status
            error_message: Optional error message
            
        Returns:
            True if update was successful, False otherwise
        """
        try:
            update_data = {
                "processing_status": status,
                "updated_at": datetime.now().isoformat()
            }
            
            if error_message is not None:
                update_data["error_message"] = error_message
            
            response = await self._exec(lambda: self.client.table('feedme_conversations')
                .update(update_data)
                .eq('id', conversation_id)
                .execute())
            
            if response.data:
                logger.info(f"Updated conversation {conversation_id} status to {status}")
                return True
            else:
                logger.warning(f"Conversation {conversation_id} not found for status update")
                return False
                
        except Exception as e:
            logger.error(f"Error updating conversation {conversation_id} status: {e}")
            return False

    async def record_processing_update(
        self,
        conversation_id: int,
        status: str,
        stage: str,
        progress: int,
        message: str,
        error_message: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        metadata_overrides: Optional[Dict[str, Any]] = None,
        processed_at: Optional[datetime] = None
    ) -> bool:
        """Persist processing progress details to Supabase"""
        try:
            metadata: Dict[str, Any] = {}
            existing = await self._exec(lambda: self.client.table('feedme_conversations')
                .select('metadata')
                .eq('id', conversation_id)
                .maybe_single()
                .execute())

            if existing and existing.data and isinstance(existing.data, dict):
                metadata = existing.data.get('metadata') or {}

            tracker = metadata.get('processing_tracker', {})
            tracker.update({
                'status': status,
                'stage': stage,
                'progress': int(progress),
                'message': message,
                'updated_at': datetime.now(timezone.utc).isoformat()
            })

            if error_message:
                tracker['error'] = error_message
            elif 'error' in tracker:
                tracker.pop('error')

            if metadata_overrides:
                tracker.update(metadata_overrides)

            metadata['processing_tracker'] = tracker

            update_data = {
                'processing_status': status,
                'metadata': metadata,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            if error_message is not None:
                update_data['error_message'] = error_message

            if processing_time_ms is not None:
                update_data['processing_time_ms'] = processing_time_ms

            if processed_at is not None:
                update_data['processed_at'] = processed_at.isoformat() if isinstance(processed_at, datetime) else processed_at

            await self._exec(lambda: self.client.table('feedme_conversations')
                .update(update_data)
                .eq('id', conversation_id)
                .execute())

            return True
        except Exception as e:
            logger.error(f"Error recording processing update for conversation {conversation_id}: {e}")
            return False
    
    async def bulk_update_examples(
        self,
        example_ids: List[int],
        update_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Update multiple examples with the same data
        
        Args:
            example_ids: List of example IDs to update
            update_data: Dictionary of fields to update
            
        Returns:
            List of updated examples
        """
        try:
            # Add updated_at timestamp
            update_data['updated_at'] = datetime.now().isoformat()
            
            response = await self._exec(lambda: self.client.table('feedme_examples')
                .update(update_data)
                .in_('id', example_ids)
                .execute())
            
            updated_examples = response.data if response.data else []
            logger.info(f"Bulk updated {len(updated_examples)} examples")
            return updated_examples
            
        except Exception as e:
            logger.error(f"Error bulk updating examples: {e}")
            raise
    
    async def get_examples_by_conversation(
        self,
        conversation_id: int,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get all examples for a conversation
        
        Args:
            conversation_id: The conversation ID
            limit: Maximum number of examples to return
            offset: Number of examples to skip
            
        Returns:
            List of examples
        """
        try:
            query = self.client.table('feedme_examples')\
                .select('*')\
                .eq('conversation_id', conversation_id)\
                .order('created_at', desc=False)
            
            if limit is not None:
                query = query.range(offset, offset + limit - 1)
            
            response = await self._exec(lambda: query.execute())
            
            examples = response.data if response.data else []
            logger.info(f"Retrieved {len(examples)} examples for conversation {conversation_id}")
            return examples
            
        except Exception as e:
            logger.error(f"Error getting examples for conversation {conversation_id}: {e}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Supabase connection health"""
        try:
            # Test basic query
            response = await self._exec(
                lambda: self.client.table('feedme_folders')
                .select('*', count='exact')
                .limit(0)
                .execute()
            )
            
            # Test vector extension
            vector_test = await self._exec(lambda: self.rpc('test_vector_extension').execute())
            
            return {
                "status": "healthy",
                "folders_count": response.count or 0,
                "vector_extension": vector_test.data if vector_test else False,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# Global client instance with thread-safe initialization
_supabase_client: Optional[SupabaseClient] = None
_supabase_client_lock = threading.Lock()


def get_supabase_client() -> SupabaseClient:
    """Get or create global Supabase client instance (thread-safe).

    Uses double-checked locking pattern to ensure thread-safe singleton
    initialization while minimizing lock contention for normal access.
    """
    global _supabase_client

    # Fast path - no lock needed if already initialized
    if _supabase_client is not None:
        return _supabase_client

    # Slow path - double-checked locking for thread safety
    with _supabase_client_lock:
        if _supabase_client is None:
            _supabase_client = SupabaseClient()

    return _supabase_client


def clear_supabase_client() -> None:
    """Clear the global Supabase client for shutdown cleanup."""
    global _supabase_client
    with _supabase_client_lock:
        _supabase_client = None


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
    'clear_supabase_client',
    'supabase_transaction'
]
