import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# Configuration from environment variables
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 30))
SKIP_AUTH: bool = os.getenv("SKIP_AUTH", "false").lower() in {"1", "true", "yes"}

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
