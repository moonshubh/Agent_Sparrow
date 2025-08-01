"""
API Key Service for MB-Sparrow Agent System

Provides centralized API key management with proper error handling,
logging, and model-specific key selection logic.
"""

import logging
from typing import Optional, Dict, Any, Tuple
from enum import Enum

from langchain_core.messages import AIMessage
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)


class APIKeyType(Enum):
    """Supported API key types."""
    GEMINI = "gemini"
    OPENROUTER = "openrouter"


class SupportedModel(Enum):
    """Supported model types for API key selection."""
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    KIMI_K2 = "kimi-k2"


class APIKeyService:
    """
    Centralized API key management service.
    
    Handles model-specific API key selection, fallback logic,
    error handling, and user guidance generation.
    """
    
    # Model to API key type mapping
    MODEL_KEY_MAPPING: Dict[SupportedModel, list[APIKeyType]] = {
        SupportedModel.GEMINI_2_5_FLASH: [APIKeyType.GEMINI],
        SupportedModel.GEMINI_2_5_PRO: [APIKeyType.GEMINI],
        SupportedModel.KIMI_K2: [APIKeyType.OPENROUTER, APIKeyType.GEMINI],  # OpenRouter first, fallback to Gemini
    }
    
    # User guidance templates
    GUIDANCE_TEMPLATES = {
        APIKeyType.GEMINI: {
            "title": "Configure Gemini API Key",
            "steps": [
                "Go to Settings in the application",
                "Navigate to the API Keys section", 
                "Enter your Google Gemini API key (get one at https://makersuite.google.com/app/apikey)",
                "Save your settings and try again"
            ],
            "additional_info": "Your API key should start with 'AIza' and be 39 characters long."
        },
        APIKeyType.OPENROUTER: {
            "title": "Configure OpenRouter API Key",
            "steps": [
                "Go to Settings in the application",
                "Navigate to the API Keys section",
                "Enter your OpenRouter API key (get one at https://openrouter.ai/keys)",
                "Save your settings and try again"
            ],
            "additional_info": "OpenRouter provides access to multiple AI models including Kimi K2."
        }
    }

    def __init__(self):
        """Initialize the API key service."""
        self._key_retrievers = {}
        self._initialize_key_retrievers()
    
    def _initialize_key_retrievers(self):
        """Initialize API key retrieval functions."""
        try:
            from app.core.user_context import get_user_gemini_key, get_user_openrouter_key
            self._key_retrievers[APIKeyType.GEMINI] = get_user_gemini_key
            self._key_retrievers[APIKeyType.OPENROUTER] = get_user_openrouter_key
            logger.info("Successfully initialized API key retrievers")
        except ImportError as e:
            logger.error(f"Failed to import API key retrievers: {e}")
            logger.warning("API key service will not be able to retrieve user keys - all model requests will fail")
            self._key_retrievers = {}
            # Create placeholder functions that return None
            self._key_retrievers[APIKeyType.GEMINI] = lambda: None
            self._key_retrievers[APIKeyType.OPENROUTER] = lambda: None
        except Exception as e:
            logger.error(f"Unexpected error during API key retriever initialization: {e}")
            self._key_retrievers = {}
            # Create placeholder functions that return None
            self._key_retrievers[APIKeyType.GEMINI] = lambda: None
            self._key_retrievers[APIKeyType.OPENROUTER] = lambda: None

    async def get_api_key_for_model(
        self, 
        model: SupportedModel, 
        user_query: str = "",
        span: Optional[Any] = None
    ) -> Tuple[Optional[str], Optional[AIMessage]]:
        """
        Get appropriate API key for the specified model.
        
        Args:
            model: The model requiring an API key
            user_query: User query for logging context (first 100 chars)
            span: OpenTelemetry span for tracing
            
        Returns:
            Tuple of (api_key, error_message). If api_key is None, 
            error_message contains user guidance.
        """
        if model not in self.MODEL_KEY_MAPPING:
            error_msg = f"Unsupported model: {model.value}"
            logger.error(error_msg)
            if span:
                span.set_attribute("error", error_msg)
                span.set_status(Status(StatusCode.ERROR, "Unsupported model"))
            return None, AIMessage(content=f"Model {model.value} is not supported.")
        
        key_types = self.MODEL_KEY_MAPPING[model]
        query_context = user_query[:100] if user_query else "unknown query"
        
        # Try each key type in order
        for key_type in key_types:
            try:
                if key_type not in self._key_retrievers:
                    logger.warning(f"No retriever available for key type: {key_type.value}")
                    continue
                    
                api_key = await self._key_retrievers[key_type]()
                if api_key:
                    logger.info(f"Using {key_type.value} API key for model {model.value}")
                    return api_key, None
                else:
                    logger.debug(f"No {key_type.value} API key available")
                    
            except Exception as e:
                logger.error(f"Error retrieving {key_type.value} API key: {e}")
                continue
        
        # No API key found - generate user guidance
        error_msg = f"No API key available for {model.value} model"
        logger.warning(f"{error_msg} - user_query: {query_context}...")
        
        if span:
            span.set_attribute("error", error_msg)
            span.set_status(Status(StatusCode.ERROR, "No API key"))
        
        guidance_message = self._generate_user_guidance(model, key_types)
        return None, AIMessage(content=guidance_message)
    
    def _generate_user_guidance(self, model: SupportedModel, key_types: list[APIKeyType]) -> str:
        """
        Generate user-friendly guidance for API key configuration.
        
        Args:
            model: The model that needs an API key
            key_types: List of supported key types for this model
            
        Returns:
            Formatted guidance message
        """
        if not key_types:
            return f"No API key configuration available for {model.value}."
        
        guidance_parts = [f"To use {model.value}, please configure an API key:\n"]
        
        # Handle multiple key type options
        if len(key_types) > 1:
            for i, key_type in enumerate(key_types, 1):
                template = self.GUIDANCE_TEMPLATES.get(key_type)
                if not template:
                    continue
                    
                option_label = "Recommended" if i == 1 else "Alternative"
                guidance_parts.append(f"\n**Option {i} - {template['title']} ({option_label}):**")
                
                for step_num, step in enumerate(template['steps'], 1):
                    guidance_parts.append(f"{step_num}. {step}")
                
                if template.get('additional_info'):
                    guidance_parts.append(f"\n{template['additional_info']}")
        else:
            # Single key type
            key_type = key_types[0]
            template = self.GUIDANCE_TEMPLATES.get(key_type)
            if template:
                for step_num, step in enumerate(template['steps'], 1):
                    guidance_parts.append(f"{step_num}. {step}")
                
                if template.get('additional_info'):
                    guidance_parts.append(f"\n{template['additional_info']}")
        
        return "\n".join(guidance_parts)
    
    def is_model_supported(self, model_name: str) -> bool:
        """
        Check if a model is supported by the API key service.
        
        Args:
            model_name: Name of the model to check
            
        Returns:
            True if model is supported, False otherwise
        """
        try:
            model_enum = SupportedModel(model_name)
            return model_enum in self.MODEL_KEY_MAPPING
        except ValueError:
            return False
    
    def get_supported_models(self) -> list[str]:
        """
        Get list of all supported model names.
        
        Returns:
            List of supported model names
        """
        return [model.value for model in self.MODEL_KEY_MAPPING.keys()]
    
    def get_required_key_types_for_model(self, model_name: str) -> list[str]:
        """
        Get required API key types for a model.
        
        Args:
            model_name: Name of the model
            
        Returns:
            List of required key type names, empty if model not supported
        """
        try:
            model_enum = SupportedModel(model_name)
            key_types = self.MODEL_KEY_MAPPING.get(model_enum, [])
            return [key_type.value for key_type in key_types]
        except ValueError:
            return []


# Global service instance
_api_key_service: Optional[APIKeyService] = None


def get_api_key_service() -> APIKeyService:
    """
    Get global API key service instance.
    
    Returns:
        APIKeyService instance
    """
    global _api_key_service
    if _api_key_service is None:
        _api_key_service = APIKeyService()
    return _api_key_service


async def get_api_key_for_model(
    model_name: str, 
    user_query: str = "",
    span: Optional[Any] = None
) -> Tuple[Optional[str], Optional[AIMessage]]:
    """
    Convenience function to get API key for a model.
    
    Args:
        model_name: Name of the model
        user_query: User query for context
        span: OpenTelemetry span for tracing
        
    Returns:
        Tuple of (api_key, error_message)
    """
    service = get_api_key_service()
    
    try:
        model_enum = SupportedModel(model_name)
    except ValueError:
        error_msg = f"Unsupported model: {model_name}"
        logger.error(error_msg)
        if span:
            span.set_attribute("error", error_msg)
            span.set_status(Status(StatusCode.ERROR, "Unsupported model"))
        return None, AIMessage(content=error_msg)
    
    return await service.get_api_key_for_model(model_enum, user_query, span)