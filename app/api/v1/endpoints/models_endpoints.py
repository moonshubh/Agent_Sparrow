"""
Model Discovery API Endpoints

This module provides endpoints for discovering available AI models
and their metadata for the MB-Sparrow system.
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.agents_v2.primary_agent.llm_registry import (
    SupportedModel, 
    get_all_models, 
    get_model_info,
    get_model_metadata,
    DEFAULT_MODEL
)
# Conditional import for authentication  
try:
    from app.api.v1.endpoints.auth import get_current_user_id as get_current_user
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    # Fallback function when auth is not available
    async def get_current_user() -> dict:
        return {"id": "dev-user-12345", "email": "dev@example.com"}

from app.core.settings import settings

router = APIRouter(prefix="/models", tags=["models"])


class ModelInfo(BaseModel):
    """Information about an available model."""
    id: str
    name: str
    provider: str
    description: str
    capabilities: List[str]
    max_tokens: int
    context_window: int
    is_default: bool
    is_available: bool
    required_env_var: Optional[str] = None
    pricing: Optional[Dict[str, float]] = None


class ModelsResponse(BaseModel):
    """Response containing available models."""
    models: List[ModelInfo]
    default_model: str
    total_count: int


@router.get("", response_model=ModelsResponse)
async def get_available_models(
    current_user: dict = Depends(get_current_user)
) -> ModelsResponse:
    """
    Get all available AI models and their metadata.
    
    Returns a list of models that can be used with the system,
    including their capabilities, limits, and availability status.
    """
    try:
        all_models = get_all_models()
        model_list = []
        
        for model in all_models:
            info = get_model_metadata(model)
            
            # Check if model is available based on API keys
            is_available = _check_model_availability(model, current_user)
            
            model_info = ModelInfo(
                id=model.value,
                name=info["name"],
                provider=info["provider"],
                description=info["description"],
                capabilities=info["capabilities"],
                max_tokens=info["max_tokens"],
                context_window=info["context_window"],
                is_default=(model == DEFAULT_MODEL),
                is_available=is_available,
                required_env_var=info.get("required_env_var"),
                pricing=info.get("pricing")
            )
            model_list.append(model_info)
        
        return ModelsResponse(
            models=model_list,
            default_model=DEFAULT_MODEL.value,
            total_count=len(model_list)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve models: {str(e)}"
        )


@router.get("/{model_id}", response_model=ModelInfo)
async def get_model_details(
    model_id: str,
    current_user: dict = Depends(get_current_user)
) -> ModelInfo:
    """
    Get detailed information about a specific model.
    
    Args:
        model_id: The model identifier (e.g., "google/gemini-2.5-flash")
        
    Returns:
        Detailed model information including availability status
    """
    try:
        # Validate model ID
        model = None
        for supported_model in SupportedModel:
            if supported_model.value == model_id:
                model = supported_model
                break
        
        if not model:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model_id}' not found"
            )
        
        info = get_model_metadata(model)
        is_available = _check_model_availability(model, current_user)
        
        return ModelInfo(
            id=model.value,
            name=info["name"],
            provider=info["provider"],
            description=info["description"],
            capabilities=info["capabilities"],
            max_tokens=info["max_tokens"],
            context_window=info["context_window"],
            is_default=(model == DEFAULT_MODEL),
            is_available=is_available,
            required_env_var=info.get("required_env_var"),
            pricing=info.get("pricing")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve model details: {str(e)}"
        )


@router.get("/validate/{model_id}")
async def validate_model_access(
    model_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Validate if the current user has access to use a specific model.
    
    Args:
        model_id: The model identifier to validate
        
    Returns:
        Validation result with access status and any missing requirements
    """
    try:
        # Validate model ID
        model = None
        for supported_model in SupportedModel:
            if supported_model.value == model_id:
                model = supported_model
                break
        
        if not model:
            return {
                "valid": False,
                "reason": "Model not found",
                "model_id": model_id
            }
        
        # Check availability
        is_available = _check_model_availability(model, current_user)
        info = get_model_metadata(model)
        
        if is_available:
            return {
                "valid": True,
                "model_id": model_id,
                "message": f"Access to {info['name']} is validated"
            }
        else:
            return {
                "valid": False,
                "reason": "Missing API key",
                "model_id": model_id,
                "required_env_var": info.get("required_env_var"),
                "message": f"API key required for {info['provider']} models"
            }
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to validate model access: {str(e)}"
        )


def _check_model_availability(model: SupportedModel, user: dict) -> bool:
    """
    Check if a model is available for the current user.
    
    Args:
        model: The model to check
        user: Current user information
        
    Returns:
        True if the model is available, False otherwise
    """
    # For Gemini models, check if user has Gemini API key
    if model in (SupportedModel.GEMINI_FLASH, SupportedModel.GEMINI_PRO):
        # In a real implementation, this would check user's stored API keys
        # For now, we'll assume it's available if the user is authenticated
        return True
    
    # For Kimi K2, check if OpenRouter API key is configured
    elif model == SupportedModel.KIMI_K2:
        # This would check if the user has configured OpenRouter access
        # For now, return True if settings have OpenRouter key
        import os
        return bool(os.getenv("OPENROUTER_API_KEY"))
    
    return False