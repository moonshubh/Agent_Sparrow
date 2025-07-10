"""
Pydantic schemas for secure API key management.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum

class APIKeyType(str, Enum):
    """Supported API key types."""
    GEMINI = "gemini"
    TAVILY = "tavily"
    FIRECRAWL = "firecrawl"

class APIKeyOperation(str, Enum):
    """Audit log operations."""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    USE = "USE"
    VALIDATE = "VALIDATE"

# Request schemas
class APIKeyCreateRequest(BaseModel):
    """Request to create/update an API key."""
    api_key_type: APIKeyType = Field(..., description="Type of API key")
    api_key: str = Field(..., min_length=1, description="The API key value")
    key_name: Optional[str] = Field(None, max_length=100, description="User-friendly name")
    
    @validator('api_key')
    def validate_api_key(cls, v):
        if not v or not v.strip():
            raise ValueError("API key cannot be empty")
        return v.strip()
    
    @validator('key_name')
    def validate_key_name(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                return None
        return v

class APIKeyUpdateRequest(BaseModel):
    """Request to update an API key."""
    api_key: Optional[str] = Field(None, min_length=1, description="New API key value")
    key_name: Optional[str] = Field(None, max_length=100, description="User-friendly name")
    is_active: Optional[bool] = Field(None, description="Whether the key is active")
    
    @validator('api_key')
    def validate_api_key(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("API key cannot be empty")
        return v

class APIKeyValidateRequest(BaseModel):
    """Request to validate an API key format."""
    api_key_type: APIKeyType = Field(..., description="Type of API key")
    api_key: str = Field(..., min_length=1, description="The API key to validate")

# Response schemas
class APIKeyInfo(BaseModel):
    """API key information (without exposing the actual key)."""
    id: int
    api_key_type: APIKeyType
    key_name: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime]
    masked_key: str = Field(..., description="Masked API key for display")
    
    class Config:
        from_attributes = True

class APIKeyListResponse(BaseModel):
    """Response for listing user's API keys."""
    api_keys: List[APIKeyInfo]
    total_count: int

class APIKeyCreateResponse(BaseModel):
    """Response after creating an API key."""
    success: bool
    message: str
    api_key_info: Optional[APIKeyInfo] = None

class APIKeyUpdateResponse(BaseModel):
    """Response after updating an API key."""
    success: bool
    message: str
    api_key_info: Optional[APIKeyInfo] = None

class APIKeyDeleteResponse(BaseModel):
    """Response after deleting an API key."""
    success: bool
    message: str

class APIKeyValidateResponse(BaseModel):
    """Response for API key validation."""
    is_valid: bool
    message: str
    format_requirements: Optional[str] = None

class APIKeyTestResponse(BaseModel):
    """Response for testing API key connectivity."""
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None

# Audit log schemas
class APIKeyAuditLog(BaseModel):
    """Audit log entry."""
    id: int
    user_id: str
    api_key_type: APIKeyType
    operation: APIKeyOperation
    operation_details: Optional[Dict[str, Any]]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class APIKeyAuditLogResponse(BaseModel):
    """Response for audit log queries."""
    logs: List[APIKeyAuditLog]
    total_count: int
    page: int
    page_size: int

# Internal schemas (for backend use)
class APIKeyRecord(BaseModel):
    """Internal representation of API key record."""
    id: int
    user_id: str
    api_key_type: APIKeyType
    encrypted_key: str
    key_name: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class DecryptedAPIKey(BaseModel):
    """Decrypted API key for internal use."""
    api_key_type: APIKeyType
    api_key: str
    key_name: Optional[str]
    is_active: bool
    last_used_at: Optional[datetime]

# Configuration schemas
class APIKeyConfiguration(BaseModel):
    """Configuration for API key requirements."""
    gemini_required: bool = True
    tavily_required: bool = False
    firecrawl_required: bool = False
    allow_empty_keys: bool = False

class APIKeyStatus(BaseModel):
    """Overall API key status for a user."""
    user_id: str
    gemini_configured: bool
    tavily_configured: bool
    firecrawl_configured: bool
    all_required_configured: bool
    last_validation_check: Optional[datetime]