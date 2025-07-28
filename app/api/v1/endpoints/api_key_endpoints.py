"""
API endpoints for secure API key management with Supabase authentication.
"""

from typing import Optional
import ipaddress
from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.endpoints.auth import get_current_user_id
from app.api_keys.supabase_service import get_api_key_service, SupabaseAPIKeyService
from app.api_keys.schemas import (
    APIKeyType, APIKeyCreateRequest, APIKeyUpdateRequest,
    APIKeyListResponse, APIKeyCreateResponse, APIKeyUpdateResponse,
    APIKeyDeleteResponse, APIKeyValidateRequest, APIKeyValidateResponse,
    APIKeyStatus
)
from app.core.settings import settings

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


def get_client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Extract client IP and user agent from request."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    return ip_address, user_agent


def verify_internal_access(request: Request, x_internal_token: Optional[str] = Header(None)):
    """Verify that request is from authorized internal service."""
    client_ip = request.client.host if request.client else None
    
    # Check internal API token
    expected_token = getattr(settings, 'internal_api_token', None)
    if expected_token and x_internal_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API token"
        )
    
    # Check IP whitelist for internal networks
    if client_ip:
        try:
            ip = ipaddress.ip_address(client_ip)
            # Allow local/private networks
            allowed_networks = [
                ipaddress.ip_network('127.0.0.0/8'),    # Localhost
                ipaddress.ip_network('10.0.0.0/8'),     # Private Class A
                ipaddress.ip_network('172.16.0.0/12'),  # Private Class B
                ipaddress.ip_network('192.168.0.0/16'), # Private Class C
                ipaddress.ip_network('::1/128'),        # IPv6 localhost
                ipaddress.ip_network('fc00::/7'),       # IPv6 private
            ]
            
            # Check if IP is in any allowed network
            if not any(ip in network for network in allowed_networks):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: external IP not allowed for internal endpoint"
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid IP address format"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to determine client IP address"
        )


@router.post("/", response_model=APIKeyCreateResponse)
@limiter.limit("10/minute")
async def create_or_update_api_key(
    request: Request,
    api_key_request: APIKeyCreateRequest,
    user_id: str = Depends(get_current_user_id),
    service: SupabaseAPIKeyService = Depends(get_api_key_service)
):
    """
    Create or update an API key for the current user.
    
    Rate limited to 10 requests per minute per IP.
    """
    ip_address, user_agent = get_client_info(request)
    
    response = await service.create_or_update_api_key(
        user_id=user_id,
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
@limiter.limit("60/minute")
async def list_api_keys(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    service: SupabaseAPIKeyService = Depends(get_api_key_service)
):
    """
    List all API keys for the current user (masked for security).
    
    Rate limited to 60 requests per minute per IP.
    """
    return await service.get_user_api_keys(user_id)


@router.put("/{api_key_type}", response_model=APIKeyUpdateResponse)
@limiter.limit("10/minute")
async def update_api_key(
    request: Request,
    api_key_type: APIKeyType,
    update_request: APIKeyUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: SupabaseAPIKeyService = Depends(get_api_key_service)
):
    """
    Update an existing API key.
    
    Rate limited to 10 requests per minute per IP.
    """
    ip_address, user_agent = get_client_info(request)
    
    # Create request with the API key type from path
    create_request = APIKeyCreateRequest(
        api_key_type=api_key_type,
        api_key=update_request.api_key,
        key_name=update_request.key_name
    )
    
    # Call service directly and return response
    response = await service.create_or_update_api_key(
        user_id=user_id,
        request=create_request,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    if not response.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=response.message
        )
    
    # Return service response directly as APIKeyUpdateResponse (same structure)
    return APIKeyUpdateResponse(
        success=response.success,
        message=response.message,
        api_key_info=response.api_key_info
    )


@router.delete("/{api_key_type}", response_model=APIKeyDeleteResponse)
@limiter.limit("10/minute")
async def delete_api_key(
    request: Request,
    api_key_type: APIKeyType,
    user_id: str = Depends(get_current_user_id),
    service: SupabaseAPIKeyService = Depends(get_api_key_service)
):
    """
    Delete an API key.
    
    Rate limited to 10 requests per minute per IP.
    """
    ip_address, user_agent = get_client_info(request)
    
    response = await service.delete_api_key(
        user_id=user_id,
        api_key_type=api_key_type,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    if not response.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=response.message
        )
    
    return response


@router.post("/validate", response_model=APIKeyValidateResponse)
@limiter.limit("30/minute")
async def validate_api_key_format(
    request: Request,
    validate_request: APIKeyValidateRequest,
    user_id: str = Depends(get_current_user_id),
    service: SupabaseAPIKeyService = Depends(get_api_key_service)
):
    """
    Validate API key format without storing it.
    
    Rate limited to 30 requests per minute per IP.
    """
    return service.validate_api_key_format(
        api_key_type=validate_request.api_key_type,
        api_key=validate_request.api_key
    )


@router.get("/status", response_model=APIKeyStatus)
@limiter.limit("60/minute")
async def get_api_key_status(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    service: SupabaseAPIKeyService = Depends(get_api_key_service)
):
    """
    Get API key configuration status for the current user.
    
    Rate limited to 60 requests per minute per IP.
    """
    return await service.get_api_key_status(user_id)


# Secured internal endpoint for agents to get decrypted keys
@router.get("/internal/{api_key_type}")
async def get_api_key_internal(
    request: Request,
    api_key_type: APIKeyType,
    user_id: str,
    service: SupabaseAPIKeyService = Depends(get_api_key_service),
    _: None = Depends(verify_internal_access)  # Security check
):
    """
    INTERNAL ONLY: Get decrypted API key for agent use.
    
    Security Features:
    - IP whitelist: Only internal/private network IPs allowed
    - Token authentication: Requires X-Internal-Token header
    - Network isolation: Should be behind internal firewall
    
    This endpoint should only be accessible from internal services.
    """
    # Define fallback environment variables
    fallback_map = {
        APIKeyType.GEMINI: "GEMINI_API_KEY",
        APIKeyType.TAVILY: "TAVILY_API_KEY", 
        APIKeyType.FIRECRAWL: "FIRECRAWL_API_KEY"
    }
    
    api_key = await service.get_decrypted_api_key(
        user_id=user_id,
        api_key_type=api_key_type,
        fallback_env_var=fallback_map.get(api_key_type)
    )
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {api_key_type} API key configured for user"
        )
    
    return {"api_key": api_key}