from __future__ import annotations

from typing import Dict, List, Literal
from fastapi import APIRouter, Query

from app.core.settings import settings

router = APIRouter()

Provider = Literal["google", "xai"]
AgentType = Literal["primary", "log_analysis"]

# Available models per provider
PROVIDER_MODELS: Dict[Provider, List[str]] = {
    "google": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash-lite",
    ],
    "xai": [
        "grok-4-1-fast-reasoning",
    ],
}


def get_available_providers() -> Dict[str, bool]:
    """Check which providers are configured with API keys."""
    return {
        "google": bool(settings.gemini_api_key),
        "xai": bool(settings.xai_api_key),
    }


@router.get("/models")
async def list_models(agent_type: AgentType = Query("primary")):
    """
    Returns available models by provider for the requested agent type.
    Only returns providers that have API keys configured.
    """
    # TODO: Implement agent-type-specific model filtering when requirements are defined
    _ = agent_type  # Silence unused parameter warning until filtering is implemented
    available = get_available_providers()

    # Filter to only include configured providers
    providers = {
        provider: list(models)
        for provider, models in PROVIDER_MODELS.items()
        if available.get(provider, False)
    }

    # Ensure configured defaults are present even if not in the static list
    google_default = getattr(settings, "primary_agent_model", None)
    if providers.get("google") is not None and google_default and google_default not in providers["google"]:
        providers["google"].append(google_default)

    xai_default = getattr(settings, "xai_default_model", None)
    if providers.get("xai") is not None and xai_default and xai_default not in providers["xai"]:
        providers["xai"].append(xai_default)

    # Always include Google as fallback if nothing else is configured
    if not providers and settings.gemini_api_key:
        google_models = list(PROVIDER_MODELS["google"])  # Copy to avoid mutating global
        google_default = getattr(settings, "primary_agent_model", None)
        if google_default and google_default not in google_models:
            google_models.append(google_default)
        providers = {"google": google_models}

    return {"providers": providers}


@router.get("/providers")
async def list_providers():
    """
    Returns which providers are configured and available.
    """
    return {"providers": get_available_providers()}
