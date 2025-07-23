"""
User context management for request-scoped user information.
Provides user context throughout the agent execution pipeline.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from contextvars import ContextVar
import logging
import os

from app.api_keys.supabase_service import get_api_key_service
from app.api_keys.schemas import APIKeyType

logger = logging.getLogger(__name__)

# Context variable to store user context across async calls
_user_context: ContextVar[Optional['UserContext']] = ContextVar('user_context', default=None)


@dataclass
class UserContext:
    """
    User context containing authentication and configuration information.
    """
    user_id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    # Cached API keys (loaded on demand)
    _api_keys_cache: Dict[APIKeyType, Optional[str]] = field(default_factory=dict)
    
    async def get_api_key(
        self, 
        api_key_type: APIKeyType,
        fallback_env_var: Optional[str] = None
    ) -> Optional[str]:
        """
        Get user-specific API key with caching.
        
        Args:
            api_key_type: Type of API key to retrieve
            fallback_env_var: Environment variable to fall back to if user key not found
            
        Returns:
            API key if found, None otherwise
        """
        # Check cache first
        if api_key_type in self._api_keys_cache:
            return self._api_keys_cache[api_key_type]
        
        try:
            api_key_service = get_api_key_service()
            api_key = await api_key_service.get_decrypted_api_key(
                user_id=self.user_id,
                api_key_type=api_key_type,
                fallback_env_var=fallback_env_var
            )
            
            # Cache the result (even if None to avoid repeated lookups)
            self._api_keys_cache[api_key_type] = api_key
            
            return api_key
            
        except Exception as e:
            logger.error(f"Error retrieving API key {api_key_type} for user {self.user_id}: {e}")
            
            # Try fallback directly if provided
            if fallback_env_var:
                fallback_key = os.getenv(fallback_env_var)
                self._api_keys_cache[api_key_type] = fallback_key
                return fallback_key
                
            return None
    
    async def get_gemini_api_key(self) -> Optional[str]:
        """Get Gemini API key (with system fallback)."""
        return await self.get_api_key(APIKeyType.GEMINI, "GEMINI_API_KEY")
    
    async def get_tavily_api_key(self) -> Optional[str]:
        """Get Tavily API key (with system fallback)."""
        return await self.get_api_key(APIKeyType.TAVILY, "TAVILY_API_KEY")
    
    async def get_firecrawl_api_key(self) -> Optional[str]:
        """Get Firecrawl API key (with system fallback)."""
        return await self.get_api_key(APIKeyType.FIRECRAWL, "FIRECRAWL_API_KEY")
    
    def clear_api_key_cache(self):
        """Clear the API key cache (useful after key updates)."""
        self._api_keys_cache = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "full_name": self.full_name,
            "metadata": self.metadata
        }


def get_current_user_context() -> Optional[UserContext]:
    """
    Get the current user context from the context variable.
    
    Returns:
        UserContext if set, None otherwise
    """
    return _user_context.get()


def set_user_context(user_context: UserContext) -> None:
    """
    Set the current user context.
    
    Args:
        user_context: UserContext to set
    """
    _user_context.set(user_context)


@asynccontextmanager
async def user_context_scope(user_context: UserContext):
    """
    Context manager for setting user context within a scope.
    
    Usage:
        async with user_context_scope(user_context):
            # User context is available here
            await some_agent_function()
    """
    token = _user_context.set(user_context)
    try:
        yield user_context
    finally:
        _user_context.reset(token)


def require_user_context() -> UserContext:
    """
    Get the current user context, raising an error if not set.
    
    Returns:
        UserContext
        
    Raises:
        RuntimeError: If no user context is set
    """
    user_context = get_current_user_context()
    if user_context is None:
        raise RuntimeError("No user context set. Ensure authentication is properly configured.")
    return user_context


async def create_user_context_from_user_id(
    user_id: str,
    email: Optional[str] = None,
    full_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> UserContext:
    """
    Create a UserContext from basic user information.
    
    Args:
        user_id: User ID
        email: User email
        full_name: User full name
        metadata: Additional metadata
        
    Returns:
        UserContext instance
    """
    return UserContext(
        user_id=user_id,
        email=email,
        full_name=full_name,
        metadata=metadata
    )


# Utility functions for common use cases

async def get_user_gemini_key() -> Optional[str]:
    """Get Gemini API key for current user."""
    user_context = get_current_user_context()
    if not user_context:
        # Fall back to environment variable
        return os.getenv("GEMINI_API_KEY")
    
    return await user_context.get_gemini_api_key()


async def get_user_tavily_key() -> Optional[str]:
    """Get Tavily API key for current user."""
    user_context = get_current_user_context()
    if not user_context:
        return None
    
    return await user_context.get_tavily_api_key()


async def get_user_firecrawl_key() -> Optional[str]:
    """Get Firecrawl API key for current user."""
    user_context = get_current_user_context()
    if not user_context:
        return None
    
    return await user_context.get_firecrawl_api_key()


def get_current_user_id() -> Optional[str]:
    """Get current user ID from context."""
    user_context = get_current_user_context()
    return user_context.user_id if user_context else None


def is_user_authenticated() -> bool:
    """Check if a user is currently authenticated."""
    return get_current_user_context() is not None