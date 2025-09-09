"""
Synchronous user context helpers for Celery tasks.
Provides blocking API key retrieval when async context is unavailable.
"""

import asyncio
import os
from typing import Optional

from app.api_keys.supabase_service import get_api_key_service
from app.api_keys.schemas import APIKeyType


def get_user_api_key_sync(user_id: str, api_key_type: APIKeyType) -> Optional[str]:
    """
    Synchronously get user-specific API key for Celery tasks.
    
    Args:
        user_id: User ID to retrieve key for
        api_key_type: Type of API key to retrieve
        
    Returns:
        API key if found, None otherwise
    """
    try:
        # Run async service call synchronously
        api_key_service = get_api_key_service()
        
        # Create new event loop for sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            api_key = loop.run_until_complete(
                api_key_service.get_decrypted_api_key(
                    user_id=user_id,
                    api_key_type=api_key_type,
                    fallback_env_var=None  # We'll handle fallback separately
                )
            )
            
            # If no user key, fall back to environment
            if not api_key:
                fallback_map = {
                    APIKeyType.GEMINI: "GEMINI_API_KEY",
                    APIKeyType.TAVILY: "TAVILY_API_KEY",
                    APIKeyType.FIRECRAWL: "FIRECRAWL_API_KEY"
                }
                
                env_var = fallback_map.get(api_key_type)
                if env_var:
                    api_key = os.getenv(env_var)
            
            return api_key
            
        finally:
            loop.close()
            
    except Exception as e:
        # Log error and return None
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error retrieving {api_key_type} API key for user {user_id}: {e}")
        return None


def get_user_gemini_api_key_sync(user_id: str) -> Optional[str]:
    """Get user-specific Gemini API key synchronously."""
    return get_user_api_key_sync(user_id, APIKeyType.GEMINI)


def get_user_tavily_api_key_sync(user_id: str) -> Optional[str]:
    """Get user-specific Tavily API key synchronously."""
    return get_user_api_key_sync(user_id, APIKeyType.TAVILY)


def get_user_firecrawl_api_key_sync(user_id: str) -> Optional[str]:
    """Get user-specific Firecrawl API key synchronously."""
    return get_user_api_key_sync(user_id, APIKeyType.FIRECRAWL)
