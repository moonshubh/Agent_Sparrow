"""
Model Discovery API Endpoints

This module provides endpoints for discovering available AI models
and their metadata for the MB-Sparrow system.
"""

import os
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
    from app.api.v1.endpoints.auth import get_current_user_id
    # Create a wrapper to match expected signature
    async def get_current_user() -> dict:
        user_id = await get_current_user_id()
        return {"id": user_id}
except ImportError:
    # In production, this should fail rather than use hardcoded data
    async def get_current_user() -> dict:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is not available"
        )

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


class ValidationResponse(BaseModel):
    """Response for model access validation."""
    valid: bool
    model_id: str
    reason: Optional[str] = None
    message: Optional[str] = None
    required_env_var: Optional[str] = None


def _get_model_by_id(model_id: str) -> SupportedModel:
    """
    Get a SupportedModel by its ID string.
    
    Args:
        model_id: The model identifier string
        
    Returns:
        The SupportedModel enum
        
    Raises:
        HTTPException: If model not found
    """
    try:
        return SupportedModel(model_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found"
        )


def _create_model_info(model: SupportedModel, current_user: dict) -> ModelInfo:
    """
    Create a ModelInfo object for a given model.
    
    Args:
        model: The SupportedModel enum
        current_user: Current user information
        
    Returns:
        ModelInfo object with all metadata
    """
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
            model_info = _create_model_info(model, current_user)
            model_list.append(model_info)
        
        return ModelsResponse(
            models=model_list,
            default_model=DEFAULT_MODEL.value,
            total_count=len(model_list)
        )
        
    except ValueError as e:
        # Handle model enumeration or metadata errors
        raise HTTPException(
            status_code=500,
            detail=f"Model configuration error: {str(e)}"
        )
    except KeyError as e:
        # Handle missing metadata fields
        raise HTTPException(
            status_code=500,
            detail=f"Missing model metadata: {str(e)}"
        )
    except Exception as e:
        # Catch any other unexpected errors
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
        # Validate model ID using helper
        model = _get_model_by_id(model_id)
        
        # Create and return model info using helper
        return _create_model_info(model, current_user)
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except KeyError as e:
        # Handle missing metadata fields
        raise HTTPException(
            status_code=500,
            detail=f"Missing model metadata: {str(e)}"
        )
    except Exception as e:
        # Catch any other unexpected errors
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve model details: {str(e)}"
        )


@router.get("/validate/{model_id}", response_model=ValidationResponse)
async def validate_model_access(
    model_id: str,
    current_user: dict = Depends(get_current_user)
) -> ValidationResponse:
    """
    Validate if the current user has access to use a specific model.
    
    Args:
        model_id: The model identifier to validate
        
    Returns:
        Validation result with access status and any missing requirements
    """
    try:
        # Validate model ID using helper
        try:
            model = _get_model_by_id(model_id)
        except HTTPException:
            return ValidationResponse(
                valid=False,
                model_id=model_id,
                reason="Model not found"
            )
        
        # Check availability
        is_available = _check_model_availability(model, current_user)
        info = get_model_metadata(model)
        
        if is_available:
            return ValidationResponse(
                valid=True,
                model_id=model_id,
                message=f"Access to {info['name']} is validated"
            )
        else:
            return ValidationResponse(
                valid=False,
                model_id=model_id,
                reason="Missing API key",
                required_env_var=info.get("required_env_var"),
                message=f"API key required for {info['provider']} models"
            )
            
    except KeyError as e:
        # Handle missing metadata fields
        raise HTTPException(
            status_code=500,
            detail=f"Missing model metadata: {str(e)}"
        )
    except Exception as e:
        # Catch any other unexpected errors
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
        # Check for Gemini API key in environment or settings
        # Priority: environment variable > settings > user config
        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not gemini_key and hasattr(settings, 'gemini_api_key'):
            gemini_key = settings.gemini_api_key
        return bool(gemini_key)
    
    # For Kimi K2, check if OpenRouter API key is configured
    elif model == SupportedModel.KIMI_K2:
        # Check for OpenRouter API key
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if not openrouter_key and hasattr(settings, 'openrouter_api_key'):
            openrouter_key = settings.openrouter_api_key
        return bool(openrouter_key)
    
    return False