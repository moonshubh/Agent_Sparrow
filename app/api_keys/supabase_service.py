"""
Supabase-compatible API key service.
Handles API key operations using Supabase as the backend.
"""

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
import uuid

from app.api_keys.schemas import (
    APIKeyType, APIKeyOperation, APIKeyRecord, DecryptedAPIKey,
    APIKeyInfo, APIKeyCreateRequest, APIKeyUpdateRequest,
    APIKeyListResponse, APIKeyCreateResponse, APIKeyUpdateResponse,
    APIKeyDeleteResponse, APIKeyValidateResponse, APIKeyTestResponse,
    APIKeyStatus, APIKeyAuditLog
)
from app.core.encryption import encryption_service
from app.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class SupabaseAPIKeyService:
    """Service for managing user API keys with Supabase backend."""
    
    def __init__(self):
        self.supabase = get_supabase_client()
    
    async def create_or_update_api_key(
        self, 
        user_id: str, 
        request: APIKeyCreateRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> APIKeyCreateResponse:
        """Create or update an API key for a user."""
        try:
            # Validate API key format
            if not encryption_service.is_valid_api_key_format(request.api_key_type, request.api_key):
                return APIKeyCreateResponse(
                    success=False,
                    message=f"Invalid {request.api_key_type} API key format"
                )
            
            # Encrypt the API key and compute masked version
            encrypted_key = encryption_service.encrypt_api_key(user_id, request.api_key)
            masked_key = encryption_service.mask_api_key(request.api_key)
            
            # Check if key already exists (check both user_uuid and user_id for compatibility)
            api_key_type_str = request.api_key_type.value if isinstance(request.api_key_type, APIKeyType) else request.api_key_type
            
            existing_response = self.supabase.client.table("user_api_keys")\
                .select("*")\
                .or_(f"user_uuid.eq.{user_id},user_id.eq.{user_id}")\
                .eq("api_key_type", api_key_type_str)\
                .execute()
            
            current_time = datetime.now(timezone.utc).isoformat()
            
            if existing_response.data:
                # Update existing key
                update_data = {
                    "encrypted_key": encrypted_key,
                    "masked_key": masked_key,
                    "key_name": request.key_name,
                    "updated_at": current_time,
                    "is_active": True
                }
                
                response = self.supabase.client.table("user_api_keys")\
                    .update(update_data)\
                    .or_(f"user_uuid.eq.{user_id},user_id.eq.{user_id}")\
                    .eq("api_key_type", api_key_type_str)\
                    .execute()
                
                operation = APIKeyOperation.UPDATE
                api_key_data = existing_response.data[0]
                api_key_data.update(update_data)
            else:
                # Create new key (set both user_uuid and user_id for compatibility)
                insert_data = {
                    "user_uuid": user_id,
                    "user_id": user_id,  # Also set user_id for backward compatibility
                    "api_key_type": api_key_type_str,
                    "encrypted_key": encrypted_key,
                    "masked_key": masked_key,
                    "key_name": request.key_name,
                    "is_active": True,
                    "created_at": current_time,
                    "updated_at": current_time
                }
                
                response = self.supabase.client.table("user_api_keys")\
                    .insert(insert_data)\
                    .execute()
                
                operation = APIKeyOperation.CREATE
                api_key_data = response.data[0]
            
            # Log the operation
            await self._log_operation(
                user_id=user_id,
                api_key_type=api_key_type_str,
                operation=operation,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            # Return response with API key info
            api_key_info = APIKeyInfo(
                id=api_key_data["id"],
                api_key_type=APIKeyType(api_key_data["api_key_type"]),
                key_name=api_key_data["key_name"],
                is_active=api_key_data["is_active"],
                created_at=self._parse_iso_datetime(api_key_data["created_at"]),
                updated_at=self._parse_iso_datetime(api_key_data["updated_at"]),
                last_used_at=self._parse_iso_datetime(api_key_data["last_used_at"]) if api_key_data.get("last_used_at") else None,
                masked_key=api_key_data.get("masked_key", "****")
            )
            
            return APIKeyCreateResponse(
                success=True,
                message=f"{request.api_key_type} API key {'updated' if operation == APIKeyOperation.UPDATE else 'created'} successfully",
                api_key_info=api_key_info
            )
            
        except Exception as e:
            logger.error(f"Error creating/updating API key for user {user_id}: {str(e)}")
            return APIKeyCreateResponse(
                success=False,
                message="An error occurred while saving the API key"
            )
    
    async def get_user_api_keys(self, user_id: str) -> APIKeyListResponse:
        """Get all API keys for a user (masked for security)."""
        try:
            response = self.supabase.client.table("user_api_keys")\
                .select("id, api_key_type, key_name, is_active, created_at, updated_at, last_used_at, encrypted_key, masked_key")\
                .eq("user_uuid", user_id)\
                .execute()
            
            api_key_infos = []
            for key_data in response.data:
                # Use pre-computed masked key if available, otherwise fallback
                masked_key = key_data.get("masked_key")
                if not masked_key:
                    # Fallback: decrypt just to get the masked version (for legacy records)
                    try:
                        decrypted_key = encryption_service.decrypt_api_key(user_id, key_data["encrypted_key"])
                        masked_key = encryption_service.mask_api_key(decrypted_key)
                    except Exception:
                        masked_key = "****"
                
                api_key_infos.append(APIKeyInfo(
                    id=key_data["id"],
                    api_key_type=key_data["api_key_type"],
                    key_name=key_data["key_name"],
                    is_active=key_data["is_active"],
                    created_at=self._parse_iso_datetime(key_data["created_at"]),
                    updated_at=self._parse_iso_datetime(key_data["updated_at"]),
                    last_used_at=self._parse_iso_datetime(key_data["last_used_at"]) if key_data.get("last_used_at") else None,
                    masked_key=masked_key
                ))
            
            return APIKeyListResponse(
                api_keys=api_key_infos,
                total_count=len(api_key_infos)
            )
            
        except Exception as e:
            logger.error(f"Error retrieving API keys for user {user_id}: {str(e)}")
            return APIKeyListResponse(api_keys=[], total_count=0)
    
    async def get_decrypted_api_key(
        self, 
        user_id: str, 
        api_key_type: APIKeyType,
        fallback_env_var: Optional[str] = None
    ) -> Optional[str]:
        """
        Get decrypted API key for a user and type.
        Falls back to environment variable if user key not found and fallback is provided.
        """
        try:
            # Log the user_id to debug the format
            logger.info(f"Fetching API key for user_id: {user_id} (type: {type(user_id).__name__}, length: {len(str(user_id))})")
            logger.info(f"API key type requested: {api_key_type}")
            
            # Try to get user-specific key first (check both user_uuid and user_id)
            # Convert enum to string value for database query
            api_key_type_str = api_key_type.value if isinstance(api_key_type, APIKeyType) else api_key_type
            
            response = self.supabase.client.table("user_api_keys")\
                .select("encrypted_key, is_active")\
                .or_(f"user_uuid.eq.{user_id},user_id.eq.{user_id}")\
                .eq("api_key_type", api_key_type_str)\
                .eq("is_active", True)\
                .execute()
            
            logger.info(f"Database query returned {len(response.data)} results")
            
            if response.data:
                key_data = response.data[0]
                # Update last used timestamp
                await self._update_last_used(user_id, api_key_type)
                
                # Decrypt and return
                decrypted_key = encryption_service.decrypt_api_key(user_id, key_data["encrypted_key"])
                logger.info(f"Successfully retrieved user's {api_key_type} API key (preview: {decrypted_key[:8]}...{decrypted_key[-4:]})")
                return decrypted_key
            
            # If no user key found, try fallback
            logger.info(f"No user API key found for {api_key_type}, trying fallback: {fallback_env_var}")
            return self._get_fallback_env_key(user_id, api_key_type, fallback_env_var)
            
        except Exception as e:
            logger.error(f"Error retrieving API key for user {user_id}, type {api_key_type}: {str(e)}")
            
            # Try fallback on error too
            return self._get_fallback_env_key(user_id, api_key_type, fallback_env_var, log_usage=False)
    
    async def delete_api_key(
        self,
        user_id: str,
        api_key_type: APIKeyType,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> APIKeyDeleteResponse:
        """Delete an API key."""
        try:
            api_key_type_str = api_key_type.value if isinstance(api_key_type, APIKeyType) else api_key_type
            response = self.supabase.client.table("user_api_keys")\
                .delete()\
                .or_(f"user_uuid.eq.{user_id},user_id.eq.{user_id}")\
                .eq("api_key_type", api_key_type_str)\
                .execute()
            
            if not response.data:
                return APIKeyDeleteResponse(
                    success=False,
                    message=f"No {api_key_type} API key found"
                )
            
            # Log the operation
            await self._log_operation(
                user_id=user_id,
                api_key_type=api_key_type,
                operation=APIKeyOperation.DELETE,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            return APIKeyDeleteResponse(
                success=True,
                message=f"{api_key_type} API key deleted successfully"
            )
            
        except Exception as e:
            logger.error(f"Error deleting API key for user {user_id}: {str(e)}")
            return APIKeyDeleteResponse(
                success=False,
                message="An error occurred while deleting the API key"
            )
    
    async def get_api_key_status(self, user_id: str) -> APIKeyStatus:
        """Get status of all API key types for a user."""
        try:
            response = self.supabase.client.table("user_api_keys")\
                .select("api_key_type, is_active")\
                .or_(f"user_uuid.eq.{user_id},user_id.eq.{user_id}")\
                .eq("is_active", True)\
                .execute()
            
            configured_types = {item["api_key_type"] for item in response.data}
            
            gemini_configured = APIKeyType.GEMINI in configured_types
            tavily_configured = APIKeyType.TAVILY in configured_types
            firecrawl_configured = APIKeyType.FIRECRAWL in configured_types
            
            return APIKeyStatus(
                user_id=user_id,
                gemini_configured=gemini_configured,
                tavily_configured=tavily_configured,
                firecrawl_configured=firecrawl_configured,
                all_required_configured=gemini_configured,  # Only Gemini is required
                last_validation_check=None
            )
            
        except Exception as e:
            logger.error(f"Error getting API key status for user {user_id}: {str(e)}")
            return APIKeyStatus(
                user_id=user_id,
                gemini_configured=False,
                tavily_configured=False,
                firecrawl_configured=False,
                all_required_configured=False,
                last_validation_check=None
            )
    
    def validate_api_key_format(
        self, 
        api_key_type: APIKeyType, 
        api_key: str
    ) -> APIKeyValidateResponse:
        """Validate API key format."""
        is_valid = encryption_service.is_valid_api_key_format(api_key_type, api_key)
        
        return APIKeyValidateResponse(
            is_valid=is_valid,
            message="API key format is valid" if is_valid else f"Invalid {api_key_type} API key format"
        )
    
    # Private helper methods
    
    async def _update_last_used(self, user_id: str, api_key_type: APIKeyType):
        """Update last used timestamp for an API key."""
        try:
            api_key_type_str = api_key_type.value if isinstance(api_key_type, APIKeyType) else api_key_type
            self.supabase.client.table("user_api_keys")\
                .update({"last_used_at": datetime.now(timezone.utc).isoformat()})\
                .or_(f"user_uuid.eq.{user_id},user_id.eq.{user_id}")\
                .eq("api_key_type", api_key_type_str)\
                .execute()
        except Exception as e:
            logger.debug(f"Failed to update last_used timestamp: {e}")
    
    async def _log_operation(
        self,
        user_id: str,
        api_key_type: APIKeyType,
        operation: APIKeyOperation,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        additional_details: Optional[Dict[str, Any]] = None
    ):
        """Log API key operation for audit trail."""
        try:
            # Convert enums to strings for database storage
            api_key_type_str = api_key_type.value if isinstance(api_key_type, APIKeyType) else api_key_type
            operation_str = operation.value if isinstance(operation, APIKeyOperation) else operation
            
            operation_details = {
                "api_key_type": api_key_type_str,
                "operation": operation_str,
            }
            if additional_details:
                operation_details.update(additional_details)
            
            self.supabase.client.table("api_key_audit_log").insert({
                "user_uuid": user_id,
                "user_id": user_id,  # Also set user_id for backward compatibility
                "api_key_type": api_key_type_str,
                "operation": operation_str,
                "operation_details": operation_details,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "created_at": datetime.now(timezone.utc).isoformat()
            }).execute()
            
        except Exception as e:
            logger.error(f"Failed to log API key operation: {e}")
    
    async def _log_fallback_usage(
        self,
        user_id: str,
        api_key_type: APIKeyType,
        fallback_env_var: str
    ):
        """Log when fallback environment variable is used."""
        try:
            # Convert enum to string if needed
            api_key_type_str = api_key_type.value if isinstance(api_key_type, APIKeyType) else api_key_type
            
            await self._log_operation(
                user_id=user_id,
                api_key_type=api_key_type_str,
                operation=APIKeyOperation.USE,
                additional_details={
                    "fallback": True,
                    "env_var": fallback_env_var
                }
            )
        except Exception as e:
            logger.debug(f"Failed to log fallback usage: {e}")
    
    def _parse_iso_datetime(self, iso_string: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string with fallback for 'Z' suffix."""
        if not iso_string:
            return None
            
        try:
            # Try direct parsing first (works in Python 3.11+)
            return datetime.fromisoformat(iso_string)
        except ValueError:
            # Fallback for older Python versions or non-standard formats
            try:
                return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
            except ValueError:
                logger.warning(f"Failed to parse datetime string: {iso_string}")
                return None
    
    def _get_fallback_env_key(
        self, 
        user_id: str, 
        api_key_type: APIKeyType, 
        fallback_env_var: Optional[str],
        log_usage: bool = True
    ) -> Optional[str]:
        """Get fallback environment variable API key with optional usage logging."""
        if not fallback_env_var:
            logger.info(f"No fallback env var specified for {api_key_type}")
            return None
            
        fallback_key = os.getenv(fallback_env_var)
        if fallback_key:
            logger.info(f"Using fallback {fallback_env_var} for {api_key_type} (preview: {fallback_key[:8]}...{fallback_key[-4:]})")
        else:
            logger.info(f"Fallback env var {fallback_env_var} is not set")
        if fallback_key and log_usage:
            # Log fallback usage for monitoring (fire and forget)
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule the coroutine to run
                    asyncio.create_task(self._log_fallback_usage(user_id, api_key_type, fallback_env_var))
            except Exception:
                # Logging failure shouldn't break the functionality
                pass
                
        return fallback_key


# Global service instance with thread-safe singleton
_api_key_service: Optional[SupabaseAPIKeyService] = None
_service_lock = threading.Lock()


def get_api_key_service() -> SupabaseAPIKeyService:
    """Get thread-safe singleton API key service instance."""
    global _api_key_service
    if _api_key_service is None:
        with _service_lock:
            # Double-check locking pattern
            if _api_key_service is None:
                _api_key_service = SupabaseAPIKeyService()
    return _api_key_service