"""
Dynamic agent configuration with user API keys.
Provides per-user API key injection into agent workflows.
"""

import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from app.api_keys.service import APIKeyService
from app.api_keys.schemas import APIKeyType
from app.db.session import get_session
from app.core.settings import get_settings
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AgentConfigurationManager:
    """
    Manages dynamic configuration of agents with user-specific API keys.
    """

    def __init__(self):
        self.settings = get_settings()

    async def get_user_api_configuration(
        self, user_id: str, db_session: Optional[Session] = None
    ) -> Dict[str, Optional[str]]:
        """
        Get user's API configuration for all services.

        Args:
            user_id: User identifier for API key lookup
            db_session: Optional database session for reuse; creates new session if None

        Returns:
            Dict with API keys for each service or None if not configured
        """
        config: Dict[str, Optional[str]] = {
            "gemini_api_key": None,
            "tavily_api_key": None,
            "firecrawl_api_key": None,
        }

        try:
            # Use provided session or create new one
            if db_session:
                service = APIKeyService(db_session)
                return await self._load_api_keys(service, user_id, config)
            else:
                with get_session() as db:
                    service = APIKeyService(db)
                    return await self._load_api_keys(service, user_id, config)

        except Exception as e:
            logger.error(f"Failed to load API configuration: {e}")
            return config

    async def _load_api_keys(
        self, service: APIKeyService, user_id: str, config: Dict[str, Optional[str]]
    ) -> Dict[str, Optional[str]]:
        """Helper method to load API keys from service."""
        # Get Gemini API key (required)
        gemini_key = service.get_decrypted_api_key(user_id, APIKeyType.GEMINI)
        if gemini_key:
            config["gemini_api_key"] = gemini_key.api_key

        # Get Tavily API key (optional)
        tavily_key = service.get_decrypted_api_key(user_id, APIKeyType.TAVILY)
        if tavily_key:
            config["tavily_api_key"] = tavily_key.api_key

        # Get Firecrawl API key (optional)
        firecrawl_key = service.get_decrypted_api_key(user_id, APIKeyType.FIRECRAWL)
        if firecrawl_key:
            config["firecrawl_api_key"] = firecrawl_key.api_key

        logger.info("API configuration loaded successfully")
        return config

    async def get_gemini_config(self, user_id: str) -> Dict[str, Any]:
        """
        Get Gemini API configuration for a user.
        Falls back to system default if user hasn't configured their own key.
        """
        try:
            with get_session() as db:
                service = APIKeyService(db)
                user_key = service.get_decrypted_api_key(user_id, APIKeyType.GEMINI)

                if user_key and user_key.api_key:
                    return {
                        "api_key": user_key.api_key,
                        "source": "user",
                        "key_name": user_key.key_name,
                    }
                elif self.settings.gemini_api_key:
                    return {
                        "api_key": self.settings.gemini_api_key,
                        "source": "system",
                        "key_name": "System Default",
                    }
                else:
                    return {"api_key": None, "source": "none", "key_name": None}

        except Exception as e:
            logger.error(f"Failed to get Gemini config for user {user_id}: {e}")
            # Fallback to system key
            return {
                "api_key": self.settings.gemini_api_key,
                "source": "system_fallback",
                "key_name": "System Fallback",
            }

    async def get_tavily_config(self, user_id: str) -> Dict[str, Any]:
        """
        Get Tavily API configuration for a user.
        Returns None if neither user nor system key is available.
        """
        try:
            with get_session() as db:
                service = APIKeyService(db)
                user_key = service.get_decrypted_api_key(user_id, APIKeyType.TAVILY)

                if user_key and user_key.api_key:
                    return {
                        "api_key": user_key.api_key,
                        "source": "user",
                        "key_name": user_key.key_name,
                    }
                else:
                    # No system default for Tavily - it's optional
                    return {"api_key": None, "source": "none", "key_name": None}

        except Exception as e:
            logger.error(f"Failed to get Tavily config for user {user_id}: {e}")
            return {"api_key": None, "source": "error", "key_name": None}

    async def get_firecrawl_config(self, user_id: str) -> Dict[str, Any]:
        """
        Get Firecrawl API configuration for a user.
        Returns None if neither user nor system key is available.
        """
        try:
            with get_session() as db:
                service = APIKeyService(db)
                user_key = service.get_decrypted_api_key(user_id, APIKeyType.FIRECRAWL)

                if user_key and user_key.api_key:
                    return {
                        "api_key": user_key.api_key,
                        "source": "user",
                        "key_name": user_key.key_name,
                    }
                else:
                    # No system default for Firecrawl - it's optional
                    return {"api_key": None, "source": "none", "key_name": None}

        except Exception as e:
            logger.error(f"Failed to get Firecrawl config for user {user_id}: {e}")
            return {"api_key": None, "source": "error", "key_name": None}

    @asynccontextmanager
    async def agent_context(self, user_id: str):
        """
        Context manager that provides agent configuration for a user session.
        """
        config = await self.get_user_api_configuration(user_id)

        # Set environment variables temporarily for the context
        original_env = {}
        try:
            import os

            # Store original values
            for key in ["GEMINI_API_KEY", "TAVILY_API_KEY", "FIRECRAWL_API_KEY"]:
                original_env[key] = os.environ.get(key)

            # Set user-specific values
            if config["gemini_api_key"]:
                os.environ["GEMINI_API_KEY"] = config["gemini_api_key"]
            if config["tavily_api_key"]:
                os.environ["TAVILY_API_KEY"] = config["tavily_api_key"]
            if config["firecrawl_api_key"]:
                os.environ["FIRECRAWL_API_KEY"] = config["firecrawl_api_key"]

            yield config

        finally:
            # Restore original environment
            import os

            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def validate_required_keys(
        self, config: Dict[str, Optional[str]]
    ) -> Dict[str, bool]:
        """
        Validate that required API keys are present.

        Returns:
            Dict indicating which services are properly configured
        """
        return {
            "gemini": config["gemini_api_key"] is not None,
            "tavily": True,  # Optional service
            "firecrawl": True,  # Optional service
            "can_use_ai": config["gemini_api_key"] is not None,
            "can_use_web_search": config["tavily_api_key"] is not None,
            "can_use_web_scraping": config["firecrawl_api_key"] is not None,
        }


# Global instance
agent_config_manager = AgentConfigurationManager()


# Helper functions for easy integration
async def get_user_agent_config(user_id: str) -> Dict[str, Optional[str]]:
    """Convenience function to get user's agent configuration."""
    return await agent_config_manager.get_user_api_configuration(user_id)


async def get_user_gemini_key(user_id: str) -> Optional[str]:
    """Get user's Gemini API key or system fallback."""
    config = await agent_config_manager.get_gemini_config(user_id)
    return config.get("api_key")


async def get_user_tavily_key(user_id: str) -> Optional[str]:
    """Get user's Tavily API key."""
    config = await agent_config_manager.get_tavily_config(user_id)
    return config.get("api_key")


async def get_user_firecrawl_key(user_id: str) -> Optional[str]:
    """Get user's Firecrawl API key."""
    config = await agent_config_manager.get_firecrawl_config(user_id)
    return config.get("api_key")


@asynccontextmanager
async def user_agent_context(user_id: str):
    """Context manager for user-specific agent configuration."""
    async with agent_config_manager.agent_context(user_id) as config:
        yield config
