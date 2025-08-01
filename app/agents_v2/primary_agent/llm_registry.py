"""
MB-Sparrow - Primary Agent LLM Registry

This module defines the supported LLM models for the Primary Agent,
allowing users to choose between Gemini Flash, Gemini Pro, and Kimi K2.
"""

from enum import Enum


class SupportedModel(str, Enum):
    """
    Enumeration of supported models for the Primary Agent.
    
    Each model has different characteristics:
    - GEMINI_FLASH: Default model with thinking capabilities (8K output, 1M context)
    - GEMINI_PRO: Advanced reasoning with extended output (65K output, 1M context) 
    - KIMI_K2: 1T parameter MoE model optimized for coding (8K output, 128K context)
    """
    GEMINI_FLASH = "google/gemini-2.5-flash"
    GEMINI_PRO = "google/gemini-2.5-pro"
    KIMI_K2 = "moonshotai/kimi-k2"


# Default model for the Primary Agent
DEFAULT_MODEL = SupportedModel.GEMINI_FLASH

# Model metadata for UI display and rate limiting
MODEL_METADATA = {
    SupportedModel.GEMINI_FLASH: {
        "display_name": "Gemini 2.5 Flash",
        "description": "Fast and efficient with thinking capabilities (default)",
        "rpm_limit": 10,  # Actual Google API free tier limit
        "rpd_limit": 250,  # Requests per day limit
        "context_window": 1048576,  # 1M tokens context
        "max_output_tokens": 8192,  # Based on Google documentation
        "provider": "google",
        "required_env_var": "GEMINI_API_KEY",
        "pricing": {
            "input_tokens_per_1k": 0.00015,  # $0.15 per 1M tokens
            "output_tokens_per_1k": 0.0006   # $0.60 per 1M tokens
        }
    },
    SupportedModel.GEMINI_PRO: {
        "display_name": "Gemini 2.5 Pro",
        "description": "Advanced reasoning with extended output capabilities", 
        "rpm_limit": 5,  # Actual Google API free tier limit
        "rpd_limit": 100,  # Requests per day limit
        "context_window": 1048576,  # 1M tokens context
        "max_output_tokens": 65000,  # Significantly higher output capacity
        "provider": "google",
        "required_env_var": "GEMINI_API_KEY",
        "pricing": {
            "input_tokens_per_1k": 0.00125,  # $1.25 per 1M tokens (up to 200K)
            "output_tokens_per_1k": 0.01     # $10 per 1M tokens
        }
    },
    SupportedModel.KIMI_K2: {
        "display_name": "Kimi K2 (MoE)",
        "description": "1T parameter MoE model with excellent coding capabilities",
        "rpm_limit": 20,  # Free tier limit on OpenRouter
        "rpd_limit": 1000,  # Estimated based on OpenRouter free tier
        "context_window": 128000,  # 128K tokens context
        "max_output_tokens": 8192,  # Standard output limit for most models
        "provider": "openrouter",
        "required_env_var": "OPENROUTER_API_KEY",
        "pricing": {
            "input_tokens_per_1k": 0.00015,  # $0.15 per 1M tokens
            "output_tokens_per_1k": 0.0025   # $2.50 per 1M tokens
        }
    }
}


def get_model_info(model: SupportedModel) -> dict:
    """
    Get metadata for a specific model.
    
    Args:
        model: The model to get information for
        
    Returns:
        Dictionary containing model metadata
    """
    return MODEL_METADATA.get(model, MODEL_METADATA[DEFAULT_MODEL])


def validate_model_id(model_id: str) -> SupportedModel:
    """
    Validate and return a SupportedModel enum from a string ID.
    
    Args:
        model_id: String representation of the model ID
        
    Returns:
        SupportedModel enum value
        
    Raises:
        ValueError: If the model ID is not supported
    """
    try:
        return SupportedModel(model_id)
    except ValueError:
        raise ValueError(
            f"Unsupported model: {model_id}. "
            f"Supported models are: {', '.join(m.value for m in SupportedModel)}"
        )


def get_all_models() -> list[SupportedModel]:
    """
    Get a list of all supported models.
    
    Returns:
        List of all SupportedModel enum values
    """
    return list(SupportedModel)


# Model capabilities mapping - accurate per model
MODEL_CAPABILITIES = {
    SupportedModel.GEMINI_FLASH: ["chat", "streaming", "function_calling", "thinking"],
    SupportedModel.GEMINI_PRO: ["chat", "streaming", "function_calling", "thinking", "extended_output"],
    SupportedModel.KIMI_K2: ["chat", "coding", "long_context"]  # No streaming/function_calling confirmed
}


def get_model_metadata(model: SupportedModel) -> dict:
    """
    Get comprehensive metadata for a model suitable for API responses.
    
    Args:
        model: The model to get metadata for
        
    Returns:
        Dictionary containing comprehensive model metadata
    """
    base_info = MODEL_METADATA.get(model, MODEL_METADATA[DEFAULT_MODEL])
    return {
        "name": base_info["display_name"],
        "provider": base_info["provider"],
        "description": base_info["description"],
        "capabilities": MODEL_CAPABILITIES.get(model, ["chat"]),
        "max_tokens": base_info["max_output_tokens"],  # Dynamic lookup
        "context_window": base_info["context_window"],
        "required_env_var": base_info["required_env_var"],  # From metadata
        "pricing": base_info["pricing"]  # From metadata
    }