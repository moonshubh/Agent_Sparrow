"""
Supabase Authentication Endpoints
Production-ready auth endpoints with comprehensive security features.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone
import logging
import re

from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.supabase_auth import get_auth_client, SupabaseAuthClient
from app.core.settings import settings

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Security scheme
security = HTTPBearer(auto_error=False)

router = APIRouter()


# Request/Response Models

class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        # Check for uppercase letter
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        
        # Check for lowercase letter
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        
        # Check for digit
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        
        # Check for special character
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character (!@#$%^&*(),.?":{}|<>)')
        
        return v


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class OAuthRequest(BaseModel):
    provider: str  # 'google', 'github', etc.
    redirect_to: Optional[str] = None
    scopes: Optional[str] = None


class PasswordResetRequest(BaseModel):
    email: EmailStr
    redirect_to: Optional[str] = None


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: Dict[str, Any]


class SignUpResponse(BaseModel):
    message: str
    user: Dict[str, Any]


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    created_at: datetime
    last_sign_in_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class OAuthResponse(BaseModel):
    provider_url: str


class MessageResponse(BaseModel):
    message: str


# Helper Functions

def get_client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Extract client IP and User-Agent from request."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Get current user ID from JWT token.
    Used as a dependency for protected endpoints.
    """
    if settings.skip_auth:
        # Development mode - return configurable development user ID
        return getattr(settings, 'development_user_id', 'dev-user-id')
        
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    auth_client = get_auth_client()
    token_data = await auth_client.verify_jwt(credentials.credentials)
    
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = token_data.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user_id


# Auth Endpoints

@router.post("/signup", response_model=SignUpResponse)
@limiter.limit("5/minute")
async def sign_up(
    request: Request,
    signup_request: SignUpRequest,
    auth_client: SupabaseAuthClient = Depends(get_auth_client)
):
    """
    Sign up a new user with email and password.
    
    Rate limited to 5 attempts per minute per IP.
    """
    ip_address, user_agent = get_client_info(request)
    
    try:
        # Prepare metadata
        metadata = {}
        if signup_request.full_name:
            metadata["full_name"] = signup_request.full_name
            
        user, error = await auth_client.sign_up(
            email=signup_request.email,
            password=signup_request.password,
            metadata=metadata,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error
            )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sign up failed"
            )
        
        # For email confirmation flow, we might not get a session immediately
        return {
            "message": "Sign up successful. Please check your email for verification.",
            "user": {
                "id": user.id,
                "email": user.email,
                "created_at": user.created_at
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sign up error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sign up failed"
        )


@router.post("/signin", response_model=AuthResponse)
@limiter.limit("10/minute")
async def sign_in(
    request: Request,
    signin_request: SignInRequest,
    auth_client: SupabaseAuthClient = Depends(get_auth_client)
):
    """
    Sign in with email and password.
    
    Rate limited to 10 attempts per minute per IP.
    """
    ip_address, user_agent = get_client_info(request)
    
    try:
        session, error = await auth_client.sign_in_with_password(
            email=signin_request.email,
            password=signin_request.password,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error
            )
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sign in failed"
            )
        
        return {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "expires_in": session.expires_in,
            "user": {
                "id": session.user.id,
                "email": session.user.email,
                "full_name": session.user.user_metadata.get("full_name"),
                "created_at": session.user.created_at,
                "last_sign_in_at": session.user.last_sign_in_at,
                "metadata": session.user.user_metadata
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sign in error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sign in failed"
        )


@router.post("/oauth", response_model=OAuthResponse)
@limiter.limit("20/minute")
async def oauth_signin(
    request: Request,
    oauth_request: OAuthRequest,
    auth_client: SupabaseAuthClient = Depends(get_auth_client)
):
    """
    Get OAuth provider URL for sign in.
    
    Rate limited to 20 attempts per minute per IP.
    """
    ip_address, user_agent = get_client_info(request)
    
    try:
        provider_url, error = await auth_client.sign_in_with_oauth(
            provider=oauth_request.provider,
            redirect_to=oauth_request.redirect_to,
            scopes=oauth_request.scopes,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error
            )
        
        if not provider_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to generate OAuth URL"
            )
        
        return {"provider_url": provider_url}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth initialization failed"
        )


@router.post("/signout", response_model=MessageResponse)
@limiter.limit("30/minute")
async def sign_out(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_client: SupabaseAuthClient = Depends(get_auth_client)
):
    """
    Sign out the current user.
    
    Rate limited to 30 attempts per minute per IP.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    ip_address, user_agent = get_client_info(request)
    
    try:
        error = await auth_client.sign_out(
            jwt_token=credentials.credentials,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error
            )
        
        return {"message": "Sign out successful"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sign out error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sign out failed"
        )


@router.post("/refresh", response_model=AuthResponse)
@limiter.limit("60/minute")
async def refresh_token(
    request: Request,
    refresh_token_value: str,
    auth_client: SupabaseAuthClient = Depends(get_auth_client)
):
    """
    Refresh access token using refresh token.
    
    Rate limited to 60 attempts per minute per IP.
    """
    ip_address, user_agent = get_client_info(request)
    
    try:
        session, error = await auth_client.refresh_token(
            refresh_token=refresh_token_value,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error
            )
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token refresh failed"
            )
        
        return {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "expires_in": session.expires_in,
            "user": {
                "id": session.user.id,
                "email": session.user.email,
                "full_name": session.user.user_metadata.get("full_name"),
                "created_at": session.user.created_at,
                "last_sign_in_at": session.user.last_sign_in_at,
                "metadata": session.user.user_metadata
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    reset_request: PasswordResetRequest,
    auth_client: SupabaseAuthClient = Depends(get_auth_client)
):
    """
    Send password reset email.
    
    Rate limited to 5 attempts per minute per IP.
    """
    ip_address, user_agent = get_client_info(request)
    
    try:
        error = await auth_client.reset_password_for_email(
            email=reset_request.email,
            redirect_to=reset_request.redirect_to,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error
            )
        
        return {"message": "Password reset email sent"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed"
        )


@router.get("/me", response_model=UserResponse)
@limiter.limit("100/minute")
async def get_current_user(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_client: SupabaseAuthClient = Depends(get_auth_client)
):
    """
    Get current user information.
    
    Rate limited to 100 requests per minute per IP.
    """
    try:
        user = await auth_client.get_user_from_token(credentials.credentials)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.user_metadata.get("full_name"),
            "created_at": user.created_at,
            "last_sign_in_at": user.last_sign_in_at,
            "metadata": user.user_metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user information"
        )


@router.put("/me", response_model=UserResponse)
@limiter.limit("20/minute")
async def update_current_user(
    request: Request,
    update_request: UpdateUserRequest,
    user_id: str = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_client: SupabaseAuthClient = Depends(get_auth_client)
):
    """
    Update current user information.
    
    Rate limited to 20 requests per minute per IP.
    """
    ip_address, user_agent = get_client_info(request)
    
    try:
        # Prepare attributes to update
        attributes = {}
        if update_request.full_name is not None:
            attributes["data"] = {"full_name": update_request.full_name}
        if update_request.metadata:
            if "data" not in attributes:
                attributes["data"] = {}
            attributes["data"].update(update_request.metadata)
        
        if not attributes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No attributes to update"
            )
        
        user, error = await auth_client.update_user(
            jwt_token=credentials.credentials,
            attributes=attributes,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error
            )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User update failed"
            )
        
        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.user_metadata.get("full_name"),
            "created_at": user.created_at,
            "last_sign_in_at": user.last_sign_in_at,
            "metadata": user.user_metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User update failed"
        )


"""
Rate Limiting Configuration:

This module uses SlowAPI for rate limiting authentication endpoints to prevent abuse.
Each endpoint has specific rate limits configured via @limiter.limit() decorators.

Exception Handling:
- APIRouter does not support exception_handler decorators (FastAPI limitation as of 2024)
- Rate limit exceptions are handled globally in app/main.py using @app.exception_handler()
- This ensures consistent error responses across all rate-limited endpoints

Global Exception Handlers (in main.py):
- RateLimitExceeded: Standard SlowAPI rate limit errors (429 status)
- RateLimitExceededException: Custom Gemini rate limiter errors (429 status)
- CircuitBreakerOpenException: Service temporarily unavailable (503 status)
- GeminiServiceUnavailableException: Gemini API downtime (503 status)

Rate Limits Applied:
- Sign Up: 5/minute - Prevents spam account creation
- Sign In: 10/minute - Balances security with usability
- OAuth Sign In: 20/minute - Higher limit for OAuth flows
- Sign Out: 30/minute - Higher limit as less security sensitive
- Token Refresh: 60/minute - Allows frequent refresh for active sessions
- Password Reset: 5/minute - Strict limit to prevent abuse
- Get Current User: 100/minute - High limit for frequent profile access
- Update User: 20/minute - Moderate limit for profile updates
"""