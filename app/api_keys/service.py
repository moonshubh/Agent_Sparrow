"""
Service layer for secure API key management.
Handles all business logic for API key operations.
"""

# mypy: ignore-errors

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, delete, and_
from sqlalchemy.exc import IntegrityError

from app.api_keys.schemas import (
    APIKeyType,
    APIKeyOperation,
    DecryptedAPIKey,
    APIKeyInfo,
    APIKeyCreateRequest,
    APIKeyUpdateRequest,
    APIKeyListResponse,
    APIKeyCreateResponse,
    APIKeyUpdateResponse,
    APIKeyDeleteResponse,
    APIKeyValidateResponse,
    APIKeyStatus,
)
from app.core.encryption import encryption_service
from app.db.models import UserAPIKey, APIKeyAuditLog as AuditLogModel

logger = logging.getLogger(__name__)


class APIKeyService:
    """Service for managing user API keys securely."""

    def __init__(self, db: Session):
        self.db = db

    def create_or_update_api_key(
        self,
        user_id: str,
        request: APIKeyCreateRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> APIKeyCreateResponse:
        """
        Create or update an API key for a user.
        """
        try:
            # Validate API key format
            if not encryption_service.is_valid_api_key_format(
                request.api_key_type, request.api_key
            ):
                return APIKeyCreateResponse(
                    success=False,
                    message=f"Invalid {request.api_key_type} API key format",
                )

            # Encrypt the API key
            encrypted_key = encryption_service.encrypt_api_key(user_id, request.api_key)

            # Check if key already exists with row-level locking for concurrency control
            existing_key = self.db.execute(
                select(UserAPIKey)
                .where(
                    and_(
                        UserAPIKey.user_id == user_id,
                        UserAPIKey.api_key_type == request.api_key_type,
                    )
                )
                .with_for_update()
            ).scalar_one_or_none()

            if existing_key:
                # Update existing key
                existing_key.encrypted_key = encrypted_key
                existing_key.key_name = request.key_name
                existing_key.updated_at = datetime.now(timezone.utc)
                existing_key.is_active = True
                operation = APIKeyOperation.UPDATE
            else:
                # Create new key
                # Note: Database should have UNIQUE constraint on (user_id, api_key_type) to prevent duplicates
                new_key = UserAPIKey(
                    user_id=user_id,
                    api_key_type=request.api_key_type,
                    encrypted_key=encrypted_key,
                    key_name=request.key_name,
                    is_active=True,
                )
                self.db.add(new_key)
                existing_key = new_key
                operation = APIKeyOperation.CREATE

            try:
                self.db.commit()
            except IntegrityError as e:
                self.db.rollback()
                logger.error(f"Integrity error during API key operation: {e}")
                raise ValueError(
                    f"Failed to save API key due to constraint violation: {e}"
                )
            except Exception as e:
                self.db.rollback()
                logger.error(f"Unexpected error during API key operation: {e}")
                raise

            # Log the operation
            self._log_operation(
                user_id=user_id,
                api_key_type=request.api_key_type,
                operation=operation,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Return response with API key info
            api_key_info = APIKeyInfo(
                id=existing_key.id,
                api_key_type=existing_key.api_key_type,
                key_name=existing_key.key_name,
                is_active=existing_key.is_active,
                created_at=existing_key.created_at,
                updated_at=existing_key.updated_at,
                last_used_at=existing_key.last_used_at,
                masked_key=encryption_service.mask_api_key(request.api_key),
            )

            return APIKeyCreateResponse(
                success=True,
                message=f"{request.api_key_type} API key {'updated' if operation == APIKeyOperation.UPDATE else 'created'} successfully",
                api_key_info=api_key_info,
            )

        except Exception as e:
            self.db.rollback()
            logger.error(
                f"Error creating/updating API key for user {user_id}: {str(e)}"
            )
            return APIKeyCreateResponse(
                success=False, message="An error occurred while saving the API key"
            )

    def get_user_api_keys(self, user_id: str) -> APIKeyListResponse:
        """
        Get all API keys for a user (masked for security).
        """
        try:
            keys = (
                self.db.execute(select(UserAPIKey).where(UserAPIKey.user_id == user_id))
                .scalars()
                .all()
            )

            api_key_infos = []
            for key in keys:
                # Decrypt just to get the masked version
                try:
                    decrypted_key = encryption_service.decrypt_api_key(
                        user_id, key.encrypted_key
                    )
                    masked_key = encryption_service.mask_api_key(decrypted_key)
                except Exception:
                    masked_key = "****"

                api_key_infos.append(
                    APIKeyInfo(
                        id=key.id,
                        api_key_type=key.api_key_type,
                        key_name=key.key_name,
                        is_active=key.is_active,
                        created_at=key.created_at,
                        updated_at=key.updated_at,
                        last_used_at=key.last_used_at,
                        masked_key=masked_key,
                    )
                )

            return APIKeyListResponse(
                api_keys=api_key_infos, total_count=len(api_key_infos)
            )

        except Exception as e:
            logger.error(f"Error retrieving API keys for user {user_id}: {str(e)}")
            return APIKeyListResponse(api_keys=[], total_count=0)

    def update_api_key(
        self,
        user_id: str,
        api_key_type: APIKeyType,
        request: APIKeyUpdateRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> APIKeyUpdateResponse:
        """
        Update an existing API key.
        """
        try:
            # Find the existing key
            existing_key = self.db.execute(
                select(UserAPIKey).where(
                    and_(
                        UserAPIKey.user_id == user_id,
                        UserAPIKey.api_key_type == api_key_type,
                    )
                )
            ).scalar_one_or_none()

            if not existing_key:
                return APIKeyUpdateResponse(
                    success=False, message=f"No {api_key_type} API key found"
                )

            # Update fields
            if request.api_key:
                if not encryption_service.is_valid_api_key_format(
                    api_key_type, request.api_key
                ):
                    return APIKeyUpdateResponse(
                        success=False, message=f"Invalid {api_key_type} API key format"
                    )
                existing_key.encrypted_key = encryption_service.encrypt_api_key(
                    user_id, request.api_key
                )

            if request.key_name is not None:
                existing_key.key_name = request.key_name

            if request.is_active is not None:
                existing_key.is_active = request.is_active

            existing_key.updated_at = datetime.now(timezone.utc)

            self.db.commit()

            # Log the operation
            self._log_operation(
                user_id=user_id,
                api_key_type=api_key_type,
                operation=APIKeyOperation.UPDATE,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Get masked key for response
            try:
                decrypted_key = encryption_service.decrypt_api_key(
                    user_id, existing_key.encrypted_key
                )
                masked_key = encryption_service.mask_api_key(decrypted_key)
            except Exception:
                masked_key = "****"

            api_key_info = APIKeyInfo(
                id=existing_key.id,
                api_key_type=existing_key.api_key_type,
                key_name=existing_key.key_name,
                is_active=existing_key.is_active,
                created_at=existing_key.created_at,
                updated_at=existing_key.updated_at,
                last_used_at=existing_key.last_used_at,
                masked_key=masked_key,
            )

            return APIKeyUpdateResponse(
                success=True,
                message=f"{api_key_type} API key updated successfully",
                api_key_info=api_key_info,
            )

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating API key for user {user_id}: {str(e)}")
            return APIKeyUpdateResponse(
                success=False, message="An error occurred while updating the API key"
            )

    def delete_api_key(
        self,
        user_id: str,
        api_key_type: APIKeyType,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> APIKeyDeleteResponse:
        """
        Delete an API key for a user.
        """
        try:
            # Find and delete the key
            result = self.db.execute(
                delete(UserAPIKey).where(
                    and_(
                        UserAPIKey.user_id == user_id,
                        UserAPIKey.api_key_type == api_key_type,
                    )
                )
            )

            if result.rowcount == 0:
                return APIKeyDeleteResponse(
                    success=False, message=f"No {api_key_type} API key found"
                )

            self.db.commit()

            # Log the operation
            self._log_operation(
                user_id=user_id,
                api_key_type=api_key_type,
                operation=APIKeyOperation.DELETE,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            return APIKeyDeleteResponse(
                success=True, message=f"{api_key_type} API key deleted successfully"
            )

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting API key for user {user_id}: {str(e)}")
            return APIKeyDeleteResponse(
                success=False, message="An error occurred while deleting the API key"
            )

    def get_decrypted_api_key(
        self, user_id: str, api_key_type: APIKeyType
    ) -> Optional[DecryptedAPIKey]:
        """
        Get decrypted API key for internal use by agents.
        This should only be called by the agent system.
        """
        try:
            key_record = self.db.execute(
                select(UserAPIKey).where(
                    and_(
                        UserAPIKey.user_id == user_id,
                        UserAPIKey.api_key_type == api_key_type,
                        UserAPIKey.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()

            if not key_record:
                return None

            # Decrypt the key
            decrypted_key = encryption_service.decrypt_api_key(
                user_id, key_record.encrypted_key
            )

            # Update last used timestamp
            key_record.last_used_at = datetime.now(timezone.utc)
            self.db.commit()

            # Log usage
            self._log_operation(
                user_id=user_id,
                api_key_type=api_key_type,
                operation=APIKeyOperation.USE,
            )

            return DecryptedAPIKey(
                api_key_type=key_record.api_key_type,
                api_key=decrypted_key,
                key_name=key_record.key_name,
                is_active=key_record.is_active,
                last_used_at=key_record.last_used_at,
            )

        except Exception as e:
            logger.error(
                f"Error retrieving decrypted API key for user {user_id}: {str(e)}"
            )
            return None

    def validate_api_key_format(
        self, api_key_type: APIKeyType, api_key: str
    ) -> APIKeyValidateResponse:
        """
        Validate API key format without storing it.
        """
        try:
            is_valid = encryption_service.is_valid_api_key_format(api_key_type, api_key)

            format_requirements = {
                APIKeyType.GEMINI: "Should start with 'AIza' and be 39 characters long",
                APIKeyType.OPENAI: "Should start with 'sk-' (or 'sk-proj-') and be at least 20 characters",
                APIKeyType.TAVILY: "Should be 32-40 alphanumeric characters",
                APIKeyType.FIRECRAWL: "Should start with 'fc-' and be at least 20 characters",
            }

            return APIKeyValidateResponse(
                is_valid=is_valid,
                message=(
                    "Valid API key format" if is_valid else "Invalid API key format"
                ),
                format_requirements=format_requirements.get(api_key_type),
            )

        except Exception as e:
            logger.error(f"Error validating API key format: {str(e)}")
            return APIKeyValidateResponse(
                is_valid=False, message="Error validating API key format"
            )

    def get_api_key_status(self, user_id: str) -> APIKeyStatus:
        """
        Get overall API key configuration status for a user.
        """
        try:
            keys = (
                self.db.execute(
                    select(UserAPIKey).where(
                        and_(
                            UserAPIKey.user_id == user_id,
                            UserAPIKey.is_active.is_(True),
                        )
                    )
                )
                .scalars()
                .all()
            )

            key_types = {key.api_key_type for key in keys}

            return APIKeyStatus(
                user_id=user_id,
                gemini_configured=APIKeyType.GEMINI in key_types,
                openai_configured=APIKeyType.OPENAI in key_types,
                tavily_configured=APIKeyType.TAVILY in key_types,
                firecrawl_configured=APIKeyType.FIRECRAWL in key_types,
                all_required_configured=APIKeyType.GEMINI
                in key_types,  # Only Gemini is required
                last_validation_check=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(f"Error getting API key status for user {user_id}: {str(e)}")
            return APIKeyStatus(
                user_id=user_id,
                gemini_configured=False,
                openai_configured=False,
                tavily_configured=False,
                firecrawl_configured=False,
                all_required_configured=False,
                last_validation_check=datetime.now(timezone.utc),
            )

    def _log_operation(
        self,
        user_id: str,
        api_key_type: APIKeyType,
        operation: APIKeyOperation,
        operation_details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """
        Log API key operation for audit purposes.
        """
        try:
            audit_log = AuditLogModel(
                user_id=user_id,
                api_key_type=api_key_type,
                operation=operation,
                operation_details=operation_details,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.add(audit_log)
            self.db.commit()
        except Exception as e:
            logger.error(f"Error logging API key operation: {str(e)}")
            # Don't fail the main operation if logging fails
            pass
