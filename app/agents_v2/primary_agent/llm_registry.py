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
    - GEMINI_FLASH: Default model, fastest (10 RPM, 250/day), cost-effective
    - GEMINI_PRO: Advanced reasoning (5 RPM, 100/day), higher quality
    - KIMI_K2: Open-source 1T parameter MoE model via OpenRouter, 20 RPM free tier
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
        "description": "Fast and efficient (default)",
        "rpm_limit": 10,  # Actual Google API free tier limit
        "rpd_limit": 250,  # Requests per day limit
        "context_window": 1048576,
        "provider": "google"
    },
    SupportedModel.GEMINI_PRO: {
        "display_name": "Gemini 2.5 Pro",
        "description": "Advanced reasoning capabilities", 
        "rpm_limit": 5,  # Actual Google API free tier limit
        "rpd_limit": 100,  # Requests per day limit
        "context_window": 2097152,
        "provider": "google"
    },
    SupportedModel.KIMI_K2: {
        "display_name": "Kimi K2 (open-source)",
        "description": "1T parameter MoE model",
        "rpm_limit": 20,  # Free tier limit
        "context_window": 128000,
        "provider": "openrouter"
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
        "capabilities": ["chat", "streaming", "function_calling"],
        "max_tokens": 8192,  # Output tokens limit
        "context_window": base_info["context_window"],
        "required_env_var": "GEMINI_API_KEY" if base_info["provider"] == "google" else "OPENROUTER_API_KEY",
        "pricing": {
            "input_tokens_per_1k": 0.0001 if base_info["provider"] == "google" else 0.0002,
            "output_tokens_per_1k": 0.0003 if base_info["provider"] == "google" else 0.0004
        }
    }