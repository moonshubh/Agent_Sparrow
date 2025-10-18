"""
Local Development Authentication Bypass
WARNING: This is for local testing only - NEVER use in production!
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Any

from fastapi import APIRouter, Body, HTTPException, Query, status
from pydantic import BaseModel
import jwt

from app.core.settings import settings

router = APIRouter()

# Only enable these endpoints in local development
if not os.getenv("ENABLE_LOCAL_AUTH_BYPASS", "false").lower() == "true":
    router = APIRouter()  # Empty router if not in local mode


class LocalSignInRequest(BaseModel):
    email: str = "dev@localhost.com"
    password: str = "dev"


class LocalAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: Dict[str, Any]


def create_local_jwt_token(user_id: str, email: str) -> tuple[str, str, int]:
    """Create a local JWT token for testing."""
    
    # Access token payload
    access_payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "session_id": f"local-session-{user_id}",
        "app_metadata": {
            "provider": "local",
            "providers": ["local"]
        },
        "user_metadata": {
            "full_name": "Local Dev User",
            "avatar_url": None
        }
    }
    
    # Refresh token payload
    refresh_payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=7),
        "session_id": f"local-session-{user_id}"
    }
    
    # Create tokens
    access_token = jwt.encode(
        access_payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    
    refresh_token = jwt.encode(
        refresh_payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    
    expires_in = settings.jwt_access_token_expire_minutes * 60
    
    return access_token, refresh_token, expires_in


@router.post("/local-signin", response_model=LocalAuthResponse)
async def local_sign_in(request: LocalSignInRequest):
    """
    Local development sign-in endpoint.
    Accepts any email/password and returns a valid JWT token.
    
    WARNING: This bypasses all authentication - ONLY for local testing!
    """
    
    if not os.getenv("ENABLE_LOCAL_AUTH_BYPASS", "false").lower() == "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local auth bypass is not enabled"
        )
    
    # Use the email as user ID for consistency
    user_id = settings.development_user_id or "dev-user-123"
    
    # Create local JWT tokens
    access_token, refresh_token, expires_in = create_local_jwt_token(
        user_id=user_id,
        email=request.email
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "user": {
            "id": user_id,
            "email": request.email,
            "full_name": "Local Dev User",
            "created_at": datetime.utcnow().isoformat(),
            "last_sign_in_at": datetime.utcnow().isoformat(),
            "metadata": {
                "full_name": "Local Dev User",
                "environment": "local",
                "bypass_enabled": True
            }
        }
    }


@router.get("/local-user")
async def get_local_user():
    """
    Get the local development user information.
    """
    
    if not os.getenv("ENABLE_LOCAL_AUTH_BYPASS", "false").lower() == "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local auth bypass is not enabled"
        )
    
    user_id = settings.development_user_id or "dev-user-123"
    
    return {
        "id": user_id,
        "email": "dev@localhost.com",
        "full_name": "Local Dev User",
        "created_at": datetime.utcnow().isoformat(),
        "last_sign_in_at": datetime.utcnow().isoformat(),
        "metadata": {
            "full_name": "Local Dev User",
            "environment": "local",
            "bypass_enabled": True
        }
    }


class LocalValidateRequest(BaseModel):
    token: str


@router.post("/local-validate")
async def validate_local_token(
    payload: LocalValidateRequest | None = Body(default=None),
    token: str | None = Query(default=None),
):
    """
    Validate a local JWT token.
    """
    
    if not os.getenv("ENABLE_LOCAL_AUTH_BYPASS", "false").lower() == "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local auth bypass is not enabled"
        )
    
    # Accept token from JSON body or query param for flexibility
    token_value = (payload.token if payload else None) or token
    if not token_value:
        # Gracefully report missing token so the frontend can re-issue without logging 422 errors
        return {"valid": False, "error": "Missing token"}

    try:
        payload = jwt.decode(
            token_value,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        
        return {
            "valid": True,
            "user_id": payload.get("sub"),
            "email": payload.get("email"),
            "expires_at": datetime.fromtimestamp(payload.get("exp", 0)).isoformat()
        }
    except jwt.ExpiredSignatureError:
        return {"valid": False, "error": "Token expired"}
    except jwt.InvalidTokenError as e:
        return {"valid": False, "error": str(e)}
