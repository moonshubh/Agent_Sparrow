"""
MB-Sparrow - Primary Agent LLM Factory

This module provides factory methods for instantiating LLM models
based on the selected model type, supporting Gemini and OpenRouter models.
"""

import os
import logging
from typing import Optional, Dict, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from .llm_registry import SupportedModel, get_model_info

logger = logging.getLogger(__name__)


class LLMFactory:
    """
    Factory class for creating LLM instances based on the selected model.
    
    Handles authentication and configuration for different providers:
    - Google Gemini models via ChatGoogleGenerativeAI
    - OpenRouter models via ChatOpenAI with custom base URL
    """
    
    @staticmethod
    def build_llm(
        model: SupportedModel,
        **kwargs: Any
    ) -> BaseChatModel:
        """
        Create an LLM instance for the specified model.
        
        Args:
            model: The model to instantiate
            **kwargs: Additional parameters to pass to the model constructor
            
        Returns:
            Configured LLM instance
            
        Raises:
            ValueError: If the model is not supported
            EnvironmentError: If required API keys are missing
        """
        model_info = get_model_info(model)
        
        # Use model configuration to determine provider type
        from app.core.model_config import get_model_config
        config = get_model_config(model.value)
        
        # Determine provider based on model configuration
        if model.value.startswith("gemini"):
            return LLMFactory._build_gemini_model(model, model_info, **kwargs)
        elif model.value.startswith("kimi") or "openrouter" in config.name.lower():
            return LLMFactory._build_openrouter_model(model, model_info, **kwargs)
        else:
            raise ValueError(f"Unsupported model: {model}. Supported models: {config.name}")
    
    @staticmethod
    def _build_gemini_model(
        model: SupportedModel,
        model_info: Dict[str, Any],
        **kwargs: Any
    ) -> ChatGoogleGenerativeAI:
        """
        Build a Google Gemini model instance.
        
        Args:
            model: The Gemini model to instantiate
            model_info: Model metadata
            **kwargs: Additional parameters (including optional api_key)
            
        Returns:
            Configured ChatGoogleGenerativeAI instance
            
        Raises:
            EnvironmentError: If no API key is provided
        """
        # Check for API key in kwargs first, then fall back to environment
        api_key = kwargs.pop("api_key", None) or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "API key is required for Gemini models. Pass via api_key parameter or set GOOGLE_API_KEY environment variable"
            )
        
        # Extract model name without provider prefix
        model_name = model.value.split("/")[-1]
        
        logger.info(f"Initializing Gemini model: {model_name}")
        
        # Default parameters for Gemini models
        default_params = {
            "model": model_name,
            "google_api_key": api_key,
            "convert_system_message_to_human": True,
            "max_output_tokens": kwargs.get("max_tokens", 2048),
            "temperature": kwargs.get("temperature", 0.3),
        }
        
        # Remove parameters that shouldn't be passed to constructor
        kwargs.pop("max_tokens", None)
        kwargs.pop("temperature", None)
        
        # Merge with any additional kwargs
        params = {**default_params, **kwargs}
        
        return ChatGoogleGenerativeAI(**params)
    
    @staticmethod
    def _build_openrouter_model(
        model: SupportedModel,
        model_info: Dict[str, Any],
        **kwargs: Any
    ) -> ChatOpenAI:
        """
        Build an OpenRouter model instance using the OpenAI-compatible API.
        
        Args:
            model: The OpenRouter model to instantiate
            model_info: Model metadata
            **kwargs: Additional parameters (including optional api_key)
            
        Returns:
            Configured ChatOpenAI instance with OpenRouter base URL
            
        Raises:
            EnvironmentError: If no API key is provided
        """
        # Check for API key in kwargs first, then fall back to environment
        api_key = kwargs.pop("api_key", None) or os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "API key is required for OpenRouter models. Pass via api_key parameter or set OPENROUTER_API_KEY environment variable"
            )
        
        logger.info(f"Initializing OpenRouter model: {model.value}")
        
        # Get model configuration for provider settings
        from app.core.model_config import get_model_config
        model_config = get_model_config(model.value)
        provider_config = model_config.provider_config
        
        # Default parameters for OpenRouter models using configuration
        default_params = {
            "model": model.value,
            "openai_api_key": api_key,
            "base_url": provider_config.get("base_url", "https://openrouter.ai/api/v1"),
            "max_tokens": kwargs.get("max_tokens", model_config.max_tokens),
            "temperature": kwargs.get("temperature", model_config.default_temperature),
            "default_headers": provider_config.get("headers", {
                "HTTP-Referer": "https://mailbird.com",
                "X-Title": "MB-Sparrow Primary Agent"
            })
        }
        
        # Remove parameters that are already in default_params
        kwargs.pop("max_tokens", None)
        kwargs.pop("temperature", None)
        
        # Merge with any additional kwargs
        params = {**default_params, **kwargs}
        
        return ChatOpenAI(**params)
    
    @staticmethod
    def validate_api_keys(model: SupportedModel) -> bool:
        """
        Check if the required API keys are present for the specified model.
        
        Args:
            model: The model to validate API keys for
            
        Returns:
            True if required API keys are present, False otherwise
        """
        # Use model configuration to determine required API keys
        from app.core.model_config import get_model_config
        model_config = get_model_config(model.value)
        
        # Check for Gemini models
        if model.value.startswith("gemini"):
            return bool(os.getenv("GOOGLE_API_KEY"))
        
        # Check for OpenRouter-based models
        provider_config = model_config.provider_config
        if provider_config.get("provider") == "openrouter":
            api_key_env = provider_config.get("api_key_env", "OPENROUTER_API_KEY")
            return bool(os.getenv(api_key_env))
        
        # Default fallback
        return False


# Convenience function for direct usage
def build_llm(model: SupportedModel, **kwargs: Any) -> BaseChatModel:
    """
    Convenience function to build an LLM instance.
    
    Args:
        model: The model to instantiate
        **kwargs: Additional parameters to pass to the model
        
    Returns:
        Configured LLM instance
    """
    return LLMFactory.build_llm(model, **kwargs)