"""
API endpoints for secure API key management.
"""

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import get_current_user, TokenPayload
from app.db.session import get_db
from app.api_keys.service import APIKeyService
from app.api_keys.schemas import (
    APIKeyType, APIKeyCreateRequest, APIKeyUpdateRequest,
    APIKeyListResponse, APIKeyCreateResponse, APIKeyUpdateResponse,
    APIKeyDeleteResponse, APIKeyValidateRequest, APIKeyValidateResponse,
    APIKeyStatus, APIKeyAuditLogResponse
)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])
security = HTTPBearer()

def is_internal_request(request: Request) -> bool:
    """
    Check if the request is from an internal service.
    
    This checks:
    1. If the request comes from localhost/internal network
    2. If there's a valid internal service token header
    """
    # Check if request is from localhost or internal network
    client_host = request.client.host if request.client else None
    internal_ips = {"127.0.0.1", "localhost", "::1"}
    
    # Also check for internal service header token
    internal_token = request.headers.get("X-Internal-Service-Token")
    expected_internal_token = "internal-service-secret"  # Should be from environment variable
    
    return (client_host in internal_ips) or (internal_token == expected_internal_token)

def get_api_key_service(db: Session = Depends(get_db)) -> APIKeyService:
    """Get API key service instance."""
    return APIKeyService(db)

def get_client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Extract client IP and user agent from request."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    return ip_address, user_agent

@router.post("/", response_model=APIKeyCreateResponse)
async def create_or_update_api_key(
    request: Request,
    api_key_request: APIKeyCreateRequest,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: APIKeyService = Depends(get_api_key_service)
):
    """
    Create or update an API key for the current user.
    """
    ip_address, user_agent = get_client_info(request)
    
    response = service.create_or_update_api_key(
        user_id=current_user.sub,
        request=api_key_request,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    if not response.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=response.message
        )
    
    return response

@router.get("/", response_model=APIKeyListResponse)
async def list_api_keys(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: APIKeyService = Depends(get_api_key_service)
):
    """
    List all API keys for the current user (masked for security).
    """
    return service.get_user_api_keys(current_user.sub)

@router.put("/{api_key_type}", response_model=APIKeyUpdateResponse)
async def update_api_key(
    request: Request,
    api_key_type: APIKeyType,
    update_request: APIKeyUpdateRequest,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: APIKeyService = Depends(get_api_key_service)
):
    """
    Update an existing API key.
    """
    ip_address, user_agent = get_client_info(request)
    
    response = service.update_api_key(
        user_id=current_user.sub,
        api_key_type=api_key_type,
        request=update_request,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    if not response.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=response.message
        )
    
    return response

@router.delete("/{api_key_type}", response_model=APIKeyDeleteResponse)
async def delete_api_key(
    request: Request,
    api_key_type: APIKeyType,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: APIKeyService = Depends(get_api_key_service)
):
    """
    Delete an API key.
    """
    ip_address, user_agent = get_client_info(request)
    
    response = service.delete_api_key(
        user_id=current_user.sub,
        api_key_type=api_key_type,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    if not response.success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=response.message
        )
    
    return response

@router.post("/validate", response_model=APIKeyValidateResponse)
async def validate_api_key_format(
    validate_request: APIKeyValidateRequest,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: APIKeyService = Depends(get_api_key_service)
):
    """
    Validate API key format without storing it.
    """
    return service.validate_api_key_format(
        api_key_type=validate_request.api_key_type,
        api_key=validate_request.api_key
    )

@router.get("/status", response_model=APIKeyStatus)
async def get_api_key_status(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: APIKeyService = Depends(get_api_key_service)
):
    """
    Get overall API key configuration status.
    """
    return service.get_api_key_status(current_user.sub)

# Internal endpoint for agents to retrieve decrypted keys
@router.get("/internal/{api_key_type}")
async def get_decrypted_api_key(
    api_key_type: APIKeyType,
    request: Request,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: APIKeyService = Depends(get_api_key_service)
):
    """
    Internal endpoint for agents to retrieve decrypted API keys.
    This endpoint should only be accessible by the backend services.
    """
    # Verify this is an internal request
    if not is_internal_request(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only accessible to internal services"
        )
    
    decrypted_key = service.get_decrypted_api_key(
        user_id=current_user.sub,
        api_key_type=api_key_type
    )
    
    if not decrypted_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active {api_key_type} API key found"
        )
    
    return {
        "api_key": decrypted_key.api_key,
        "key_name": decrypted_key.key_name,
        "is_active": decrypted_key.is_active
    }

# Rate limiting decorator could be added here
# @router.middleware("http")
# async def rate_limit_middleware(request: Request, call_next):
#     # Implement rate limiting logic
#     pass