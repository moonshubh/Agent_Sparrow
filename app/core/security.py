import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv
import httpx
import json
from jose import jwk
from jose.utils import base64url_decode

load_dotenv()  # Load environment variables from .env file

# Configuration from environment variables
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 30))
# Skip authentication entirely (local dev/testing)
SKIP_AUTH: bool = os.getenv("SKIP_AUTH", "false").lower() in {"1", "true", "yes"}

# -----------------------------------------------------------------------------
# Supabase JWT verification configuration (production)
# -----------------------------------------------------------------------------
# If SUPABASE_URL is provided, we will verify incoming Bearer tokens against the
# Supabase project's JWKS endpoint and validate the audience/issuer.
# NOTE: Full validation logic will be added in a subsequent commit.
SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
SUPABASE_JWT_AUD: str | None = os.getenv("SUPABASE_JWT_AUD", "authenticated")

# JWKS cache (module-level singletons)
_SUPABASE_JWKS: dict | None = None
_SUPABASE_JWKS_FETCHED_AT: datetime | None = None
_SUPABASE_JWKS_TTL_SECONDS: int = 24 * 60 * 60  # 24 hours

if not SECRET_KEY and not SUPABASE_URL and not SKIP_AUTH:
    raise EnvironmentError(
        "Either JWT_SECRET_KEY or SUPABASE_URL must be configured."
    )

if not SECRET_KEY:
    raise EnvironmentError("JWT_SECRET_KEY environment variable not set.")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

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
        resp = httpx.get(keys_url, timeout=10)
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

    return TokenPayload(sub=claims.get("sub"), exp=exp, roles=claims.get("role") or [])

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": int(expire.timestamp())}) # Ensure exp is an int timestamp
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> TokenPayload:
    if SKIP_AUTH:
        # Return a dummy user payload if authentication is skipped
        return TokenPayload(sub="skipped_auth_user", exp=int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()), roles=["admin"])
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_data = TokenPayload(**payload)
        if token_data.sub is None or token_data.exp is None:
            raise credentials_exception
        if datetime.fromtimestamp(token_data.exp, tz=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except (JWTError, ValidationError):
        raise credentials_exception
    return token_data

# Example of how to protect an endpoint:
# from fastapi import APIRouter
# router = APIRouter()
# @router.get("/users/me")
# async def read_users_me(current_user: Annotated[TokenPayload, Depends(get_current_user)]):
#     return {"user_id": current_user.sub, "roles": current_user.roles}
