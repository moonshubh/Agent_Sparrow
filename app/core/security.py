import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated, List, Union
import re
import html

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv
import httpx
import json
from jose import jwk
from jose.utils import base64url_decode
from app.core.settings import get_settings

# Configure logging if not already configured
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

logger = logging.getLogger(__name__)

load_dotenv()  # Load environment variables from .env file
settings = get_settings()

# Configuration from environment variables
# Do NOT fallback to default or settings-derived secrets to avoid committing any hardcoded values.
ALGORITHM = os.getenv("JWT_ALGORITHM", getattr(settings, "jwt_algorithm", "HS256"))
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", getattr(settings, "jwt_access_token_expire_minutes", 30)))
# Skip authentication entirely (local dev/testing)
SKIP_AUTH: bool = (os.getenv("SKIP_AUTH", "false").lower() in {"1", "true", "yes"}) or getattr(settings, "skip_auth", False)

# -----------------------------------------------------------------------------
# Supabase JWT verification configuration (production)
# -----------------------------------------------------------------------------
# If SUPABASE_URL is provided, we will verify incoming Bearer tokens against the
# Supabase project's JWKS endpoint and validate the audience/issuer.
# NOTE: Full validation logic will be added in a subsequent commit.
SUPABASE_URL: str | None = os.getenv("SUPABASE_URL") or getattr(settings, "supabase_url", None)
SUPABASE_JWT_AUD: str | None = os.getenv("SUPABASE_JWT_AUD", "authenticated")

# JWKS cache (module-level singletons)
_SUPABASE_JWKS: dict | None = None
_SUPABASE_JWKS_FETCHED_AT: datetime | None = None
_SUPABASE_JWKS_TTL_SECONDS: int = 24 * 60 * 60  # 24 hours

# Helper to fetch JWT signing key strictly from environment
def _jwt_signing_key() -> Optional[str]:
    key = os.getenv("JWT_SECRET_KEY")
    return key if key else None

# Allow local/dev bypass: if SKIP_AUTH=true or SUPABASE_URL configured, do not hard-fail on missing key
if not _jwt_signing_key() and not SUPABASE_URL and not SKIP_AUTH:
    raise EnvironmentError("Either JWT_SECRET_KEY or SUPABASE_URL must be configured.")

# SECRET_KEY already falls back to settings.jwt_secret_key for local dev
# In production, ensure a strong key via env or secrets manager.

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=not SKIP_AUTH)
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

class TokenPayload(BaseModel):
    sub: Optional[str] = None # Subject (usually user identifier)
    exp: Optional[int] = None # Expiration time
    # Add any other custom claims you need, e.g., roles
    roles: Optional[list[str]] = [] 

class Token(BaseModel):
    access_token: str
    token_type: str

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# Supabase JWT utilities
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

def _get_supabase_jwks() -> dict:
    """Fetch Supabase JWKS with simple in-memory 24 h cache."""
    global _SUPABASE_JWKS, _SUPABASE_JWKS_FETCHED_AT

    if _SUPABASE_JWKS and _SUPABASE_JWKS_FETCHED_AT:
        age = (datetime.now(timezone.utc) - _SUPABASE_JWKS_FETCHED_AT).total_seconds()
        if age < _SUPABASE_JWKS_TTL_SECONDS:
            return _SUPABASE_JWKS

    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is not configured")

    keys_url = f"{SUPABASE_URL}/auth/v1/keys"
    try:
        api_key = (
            os.getenv("SUPABASE_ANON_KEY")
            or os.getenv("SUPABASE_SERVICE_KEY")
            or getattr(settings, "supabase_anon_key", None)
            or getattr(settings, "supabase_service_key", None)
        )
        headers = {}
        if api_key:
            headers["apikey"] = api_key
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            logger.warning("SUPABASE_ANON_KEY/SUPABASE_SERVICE_KEY not set; JWKS fetch may fail")
        resp = httpx.get(keys_url, timeout=10, headers=headers or None)
        resp.raise_for_status()
        _SUPABASE_JWKS = resp.json()
        _SUPABASE_JWKS_FETCHED_AT = datetime.now(timezone.utc)
        return _SUPABASE_JWKS
    except Exception as exc:
        logger.error("Failed to fetch Supabase JWKS: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service unavailable")


def _verify_supabase_jwt(token: str) -> TokenPayload:
    """Verify Supabase JWT using cached JWKS."""
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token header") from exc

    kid = unverified_header.get("kid")
    if kid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing kid")

    jwks = _get_supabase_jwks()
    jwk_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if jwk_data is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token key")

    public_key = jwk.construct(jwk_data)

    # Verify signature manually
    message, encoded_signature = token.rsplit(".", 1)
    decoded_signature = base64url_decode(encoded_signature.encode())
    if not public_key.verify(message.encode(), decoded_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

    # Decode claims
    try:
        claims = jwt.get_unverified_claims(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")

    # Validate issuer
    expected_issuer = f"{SUPABASE_URL}/auth/v1"
    if claims.get("iss") != expected_issuer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token issuer")

    # Validate audience
    aud = claims.get("aud")
    if SUPABASE_JWT_AUD and aud != SUPABASE_JWT_AUD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token audience")

    # Validate exp
    exp = claims.get("exp")
    if exp is None or datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")

    # Extract roles from multiple possible locations in the claims
    roles = []
    
    # Check direct "role" claim (string or list)
    if "role" in claims:
        role_claim = claims["role"]
        if isinstance(role_claim, str):
            roles = [role_claim]
        elif isinstance(role_claim, list):
            roles = role_claim
    # Check direct "roles" claim (typically a list)
    elif "roles" in claims:
        roles_claim = claims["roles"]
        if isinstance(roles_claim, list):
            roles = roles_claim
        elif isinstance(roles_claim, str):
            roles = [roles_claim]
    # Check app_metadata.roles (Supabase pattern)
    elif "app_metadata" in claims and isinstance(claims["app_metadata"], dict):
        app_metadata = claims["app_metadata"]
        if "roles" in app_metadata:
            app_roles = app_metadata["roles"]
            if isinstance(app_roles, list):
                roles = app_roles
            elif isinstance(app_roles, str):
                roles = [app_roles]
        elif "role" in app_metadata:
            app_role = app_metadata["role"]
            if isinstance(app_role, str):
                roles = [app_role]
            elif isinstance(app_role, list):
                roles = app_role
    
    return TokenPayload(sub=claims.get("sub"), exp=exp, roles=roles)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": int(expire.timestamp())}) # Ensure exp is an int timestamp
    key = _jwt_signing_key()
    if not key:
        raise EnvironmentError("JWT_SECRET_KEY must be set to create access tokens.")
    encoded_jwt = jwt.encode(to_encode, key, algorithm=ALGORITHM)
    return encoded_jwt

def _dev_user_id() -> str:
    from uuid import UUID

    dev_id = getattr(settings, "development_user_id", "00000000-0000-0000-0000-000000000000")
    dev_id = (dev_id or "").strip()

    if not dev_id:
        return "00000000-0000-0000-0000-000000000000"

    try:
        # Validate UUID format (raises ValueError if invalid)
        UUID(dev_id)
        return dev_id
    except Exception:
        logger.warning(
            "[AUTH] DEVELOPMENT_USER_ID is not a valid UUID. Using default development user id instead."
        )
        return "00000000-0000-0000-0000-000000000000"


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> TokenPayload:
    if SKIP_AUTH:
        # Return a deterministic development user payload when auth is bypassed
        logger.debug("[AUTH] Skipping authentication - SKIP_AUTH=true")
        dev_user = _dev_user_id()
        return TokenPayload(
            sub=dev_user,
            exp=int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            roles=["admin"],
        )
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # First, try Supabase JWT validation if configured
    if SUPABASE_URL:
        try:
            logger.debug("[AUTH] Attempting Supabase JWT validation")
            token_data = _verify_supabase_jwt(token)
            logger.info(f"[AUTH] Supabase JWT validated successfully for user: {token_data.sub}")
            return token_data
        except HTTPException as e:
            logger.warning(f"[AUTH] Supabase JWT validation failed: {e.detail}")
            # Fall through to try local JWT validation
        except Exception as e:
            logger.error(f"[AUTH] Unexpected error in Supabase JWT validation: {e}")
            # Fall through to try local JWT validation
    
    # Fallback to local JWT validation
    try:
        logger.debug("[AUTH] Attempting local JWT validation")
        key = _jwt_signing_key()
        if not key:
            raise credentials_exception
        payload = jwt.decode(token, key, algorithms=[ALGORITHM])
        token_data = TokenPayload(**payload)
        if token_data.sub is None or token_data.exp is None:
            logger.warning("[AUTH] Token missing sub or exp claim")
            raise credentials_exception
        if datetime.fromtimestamp(token_data.exp, tz=timezone.utc) < datetime.now(timezone.utc):
            logger.warning("[AUTH] Token has expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        logger.info(f"[AUTH] Local JWT validated successfully for user: {token_data.sub}")
        return token_data
    except (JWTError, ValidationError) as e:
        logger.error(f"[AUTH] JWT validation error: {e}")
        raise credentials_exception

async def get_optional_current_user(token: Optional[str] = Depends(optional_oauth2_scheme)) -> Optional[TokenPayload]:
    """Get current user if token is provided, otherwise return None.
    
    This is useful for endpoints that should work both with and without authentication.
    When authenticated, user-specific features are enabled.
    When not authenticated, a default/anonymous experience is provided.
    """
    if SKIP_AUTH:
        # Return a deterministic development user payload when auth is bypassed
        logger.debug("[AUTH-OPTIONAL] Skipping authentication - SKIP_AUTH=true")
        dev_user = _dev_user_id()
        return TokenPayload(
            sub=dev_user,
            exp=int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            roles=["admin"],
        )
    
    if not token:
        logger.debug("[AUTH-OPTIONAL] No token provided, returning None")
        return None
    
    try:
        # Try to validate the token
        return await get_current_user(token)
    except HTTPException:
        # If validation fails, return None instead of raising
        logger.debug("[AUTH-OPTIONAL] Token validation failed, returning None")
        return None

# Example of how to protect an endpoint:
# from fastapi import APIRouter
# router = APIRouter()
# @router.get("/users/me")
# async def read_users_me(current_user: Annotated[TokenPayload, Depends(get_current_user)]):
#     return {"user_id": current_user.sub, "roles": current_user.roles}


# -----------------------------------------------------------------------------
# Input Sanitization Functions
# -----------------------------------------------------------------------------

def sanitize_input(text: str, max_length: int = 10000) -> str:
    """
    Sanitize user input to prevent XSS and injection attacks.
    
    Args:
        text: The input text to sanitize
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text safe for storage and display
    """
    if not text:
        return ""
    
    # Truncate to max length
    text = text[:max_length]
    
    # HTML escape to prevent XSS
    text = html.escape(text)
    
    # Remove any potential script tags or javascript
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)
    
    # Remove SQL injection attempts
    sql_patterns = [
        r'\b(union|select|insert|update|delete|drop|create|alter|exec|execute)\b',
        r'--',
        r'/\*.*?\*/',
        r'\x00',  # Null bytes
    ]
    
    for pattern in sql_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    return text.strip()
