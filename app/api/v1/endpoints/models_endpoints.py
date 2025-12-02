from __future__ import annotations

from typing import Any, Dict, Literal
from fastapi import APIRouter, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.settings import settings
from app.core.config import get_registry, Provider as RegistryProvider

# Initialize rate limiter for model endpoints
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()

# Type aliases for documentation (not used in function signatures due to Pydantic issues)
Provider = Literal["google", "xai"]
AgentType = Literal["primary", "log_analysis"]


def _get_provider_models() -> dict[str, list[str]]:
    """Get available models per provider from registry."""
    registry = get_registry()
    return registry.get_available_models_for_api()


def get_available_providers() -> dict[str, bool]:
    """Check which providers are configured with API keys."""
    return {
        "google": bool(settings.gemini_api_key),
        "xai": bool(settings.xai_api_key),
        "openrouter": bool(getattr(settings, "openrouter_api_key", None)),
    }


@router.get("/models")
@limiter.limit("60/minute")
async def list_models(
    request: Request,
    agent_type: str = Query("primary", description="Agent type: primary or log_analysis"),
):
    """
    Returns available models by provider for the requested agent type.
    Only returns providers that have API keys configured.
    """
    # TODO: Implement agent-type-specific model filtering when requirements are defined
    _ = agent_type  # Silence unused parameter warning until filtering is implemented
    available = get_available_providers()

    # Get models from registry
    provider_models = _get_provider_models()

    # Filter to only include configured providers
    providers = {
        provider: list(models)
        for provider, models in provider_models.items()
        if available.get(provider, False)
    }

    # Ensure configured defaults are present even if not in the static list
    google_default = getattr(settings, "primary_agent_model", None)
    if providers.get("google") is not None and google_default and google_default not in providers["google"]:
        providers["google"].append(google_default)

    xai_default = getattr(settings, "xai_default_model", None)
    if providers.get("xai") is not None and xai_default and xai_default not in providers["xai"]:
        providers["xai"].append(xai_default)

    openrouter_default = getattr(settings, "openrouter_default_model", None)
    if providers.get("openrouter") is not None and openrouter_default and openrouter_default not in providers["openrouter"]:
        providers["openrouter"].append(openrouter_default)

    # Always include Google as fallback if nothing else is configured
    if not providers and settings.gemini_api_key:
        google_models = list(provider_models.get("google", []))
        google_default = getattr(settings, "primary_agent_model", None)
        if google_default and google_default not in google_models:
            google_models.append(google_default)
        providers = {"google": google_models}

    return {"providers": providers}


@router.get("/providers")
@limiter.limit("60/minute")
async def list_providers(request: Request):
    """
    Returns which providers are configured and available.
    """
    return {"providers": get_available_providers()}


@router.get("/models/config")
@limiter.limit("60/minute")
async def get_model_config(request: Request):
    """
    Returns comprehensive model configuration from the registry.

    This endpoint exposes the centralized model registry to the frontend,
    enabling single-source-of-truth model management.

    Returns:
        - models: All available models with display names, providers, and tiers
        - defaults: Default models for each provider
        - fallback_chains: Fallback model chains for graceful degradation
        - available_providers: Which providers have API keys configured
    """
    registry = get_registry()
    available = get_available_providers()

    # Build model info
    models: Dict[str, Dict[str, Any]] = {}
    for provider in ["google", "xai", "openrouter"]:
        for model in registry.get_models_by_provider(provider):
            # Skip embedding models from public API
            if model.tier.value == "embedding":
                continue
            models[model.id] = {
                "display_name": model.display_name,
                "provider": model.provider.value,
                "tier": model.tier.value,
                "supports_reasoning": model.supports_reasoning,
                "supports_vision": model.supports_vision,
            }

    # Defaults
    defaults = {
        "google": registry.coordinator_google.id,
        "xai": registry.coordinator_xai.id,
        "openrouter": registry.coordinator_openrouter.id,
    }

    # Fallback chains
    fallback_chains = {
        "google": registry.get_fallback_chain("google"),
        "xai": registry.get_fallback_chain("xai"),
        "openrouter": registry.get_fallback_chain("openrouter"),
    }

    return {
        "models": models,
        "defaults": defaults,
        "fallback_chains": fallback_chains,
        "available_providers": available,
    }
