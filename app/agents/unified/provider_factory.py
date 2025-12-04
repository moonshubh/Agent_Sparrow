"""Provider factory for multi-model support.

This module provides a factory function for creating chat models from different
providers (Google Gemini, XAI/Grok) with consistent configuration and fallback behavior.

Supports:
- Role-based temperature configuration
- Always-enabled Grok reasoning mode
- Tiered model selection (Pro/Standard/Lite)

Usage:
    from app.agents.unified.provider_factory import build_chat_model

    model = build_chat_model(
        provider="xai",
        model="grok-4-1-fast-reasoning",
        temperature=0.3,
        role="coordinator",  # Optional: uses role-based temperature
    )
"""

from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from loguru import logger

from app.core.settings import settings
from app.core.config import get_registry


# Type alias for supported providers
Provider = str  # "google" | "xai" | "openrouter"

# =============================================================================
# TEMPERATURE CONFIGURATION BY ROLE
# Based on prompt tier and task requirements
# =============================================================================

TEMPERATURE_CONFIG: dict[str, float] = {
    # Heavy tier - deterministic reasoning
    "coordinator": 0.2,
    "coordinator_heavy": 0.2,
    "log_analysis": 0.1,  # High precision for error diagnosis
    # Standard tier - balanced
    "research": 0.5,  # Creative synthesis of sources
    "grounding": 0.3,
    # Lite tier - exact matching
    "db_retrieval": 0.1,
    "feedme": 0.3,
    # Default fallback
    "default": 0.3,
}

# =============================================================================
# GROK CONFIGURATION - Always enabled reasoning for maximum quality
# =============================================================================

GROK_CONFIG = {
    "reasoning_enabled": True,  # Always enabled per user choice
    "thinking_budget": "medium",  # Balanced latency/quality (low/medium/high)
}

# =============================================================================
# TIMEOUT CONFIGURATION - Prevent 504 Deadline Exceeded errors
# =============================================================================

# Request timeout in seconds for LLM API calls
# Google API can hang indefinitely without a timeout, causing 504 errors
# Default: 300 seconds (5 minutes) - balanced between complex reasoning and responsiveness
REQUEST_TIMEOUT_SECONDS = 300

# Transport timeout for opening connections (httpx/aiohttp)
CONNECT_TIMEOUT_SECONDS = 30


def get_temperature_for_role(role: str) -> float:
    """Get the configured temperature for a specific agent role.

    Args:
        role: The agent role (coordinator, log_analysis, research, etc.)

    Returns:
        Temperature value for the role, or default if not found.
    """
    return TEMPERATURE_CONFIG.get(role.lower().strip(), TEMPERATURE_CONFIG["default"])


def build_chat_model(
    provider: str,
    model: str,
    temperature: Optional[float] = None,
    reasoning_enabled: Optional[bool] = None,
    role: Optional[str] = None,
) -> BaseChatModel:
    """Build a chat model for the specified provider.

    Args:
        provider: The model provider ("google" or "xai").
        model: The model identifier (e.g., "gemini-2.5-flash", "grok-4-1-fast-reasoning").
        temperature: Sampling temperature for the model (0.0-2.0).
            If None and role is provided, uses role-based temperature.
            If None and no role, uses default (0.3).
        reasoning_enabled: For XAI models, whether to enable reasoning mode.
            If None, uses GROK_CONFIG["reasoning_enabled"] (always True).
        role: Optional agent role for role-based temperature selection.
            One of: coordinator, coordinator_heavy, log_analysis, research,
            db_retrieval, grounding, feedme.

    Returns:
        A configured BaseChatModel instance.

    Raises:
        No exceptions are raised; unknown providers fall back to Google Gemini.

    Example:
        >>> model = build_chat_model("xai", "grok-4-1-fast-reasoning", role="coordinator")
        >>> response = model.invoke("Hello!")
    """
    provider = provider.lower().strip()

    # Determine temperature: explicit > role-based > default
    if temperature is None:
        if role:
            temperature = get_temperature_for_role(role)
        else:
            temperature = TEMPERATURE_CONFIG["default"]

    if provider == "google":
        return _build_google_model(model, temperature)

    elif provider == "xai":
        return _build_xai_model(model, temperature, reasoning_enabled)

    elif provider == "openrouter":
        return _build_openrouter_model(model, temperature)

    else:
        registry = get_registry()
        fallback_model = registry.coordinator_google.id
        logger.warning(
            "unknown_provider_fallback",
            provider=provider,
            fallback="google",
            model=fallback_model,
        )
        return _build_google_model(fallback_model, temperature)


def _build_google_model(model: str, temperature: float) -> BaseChatModel:
    """Build a Google Gemini chat model.

    Args:
        model: The Gemini model identifier.
        temperature: Sampling temperature.

    Returns:
        A configured ChatGoogleGenerativeAI instance.

    Raises:
        ValueError: If GEMINI_API_KEY is not configured.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    # Validate API key before SDK instantiation for fail-fast behavior
    if not settings.gemini_api_key:
        logger.error(
            "gemini_api_key_not_configured",
            model=model,
            hint="Set GEMINI_API_KEY environment variable",
        )
        raise ValueError(
            "GEMINI_API_KEY is not configured. "
            "Please set the GEMINI_API_KEY environment variable."
        )

    # Check if this is a Gemini 3 thinking model
    is_gemini_3 = "gemini-3" in model.lower()
    is_thinking_model = is_gemini_3 or "gemini-2.5" in model.lower()

    logger.debug(
        "building_google_model",
        model=model,
        temperature=temperature,
        is_thinking_model=is_thinking_model,
        is_gemini_3=is_gemini_3,
    )

    # Configure Gemini model with thinking settings
    # IMPORTANT: include_thoughts=False doesn't work with chains (LangGraph)
    # due to known bug: https://github.com/langchain-ai/langchain/issues/31767
    # Thinking content WILL still appear in streaming - handler.py filters it
    #
    # NOTE: thinking_level and thinking_budget are not supported by langchain-google-genai 3.2.0
    # We rely entirely on handler.py's _extract_thinking_and_text() to filter thinking content
    kwargs = {
        "model": model,
        "temperature": temperature,
        "google_api_key": settings.gemini_api_key,
        "include_thoughts": False,  # Attempt to prevent thinking (may not work with chains)
        "timeout": REQUEST_TIMEOUT_SECONDS,  # Prevent 504 Deadline Exceeded errors
    }

    return ChatGoogleGenerativeAI(**kwargs)


def _build_xai_model(
    model: str,
    temperature: float,
    reasoning_enabled: Optional[bool],
) -> BaseChatModel:
    """Build an XAI/Grok chat model.

    Args:
        model: The Grok model identifier (e.g., "grok-4-1-fast-reasoning").
        temperature: Sampling temperature.
        reasoning_enabled: Whether to enable reasoning mode.

    Returns:
        A configured ChatXAI instance, or falls back to Google if XAI key not configured.
    """
    # Check if XAI API key is configured
    registry = get_registry()
    fallback_model = registry.coordinator_google.id

    if not settings.xai_api_key:
        logger.warning(
            "xai_api_key_not_configured",
            fallback="google",
            model=fallback_model,
        )
        return _build_google_model(fallback_model, temperature)

    try:
        from langchain_xai import ChatXAI
    except ImportError as e:
        logger.error(
            "langchain_xai_import_failed",
            error=str(e),
            fallback="google",
        )
        return _build_google_model(fallback_model, temperature)

    # Determine reasoning mode - defaults to GROK_CONFIG (always enabled)
    use_reasoning = (
        reasoning_enabled
        if reasoning_enabled is not None
        else GROK_CONFIG["reasoning_enabled"]
    )

    logger.debug(
        "building_xai_model",
        model=model,
        temperature=temperature,
        reasoning_enabled=use_reasoning,
        provider="xai",
    )

    # Build extra_body for reasoning mode if enabled
    extra_body = {"reasoning_enabled": use_reasoning} if use_reasoning else None

    return ChatXAI(
        model=model,
        temperature=temperature,
        xai_api_key=settings.xai_api_key,
        extra_body=extra_body,
    )


def _build_openrouter_model(model: str, temperature: float) -> BaseChatModel:
    """Build an OpenRouter chat model."""
    from langchain_openai import ChatOpenAI

    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        registry = get_registry()
        fallback_model = registry.coordinator_google.id
        logger.warning(
            "openrouter_api_key_not_configured",
            fallback="google",
            model=fallback_model,
        )
        return _build_google_model(fallback_model, temperature)

    base_url = getattr(settings, "openrouter_base_url", None) or "https://openrouter.ai/api/v1"
    headers = {
        "HTTP-Referer": getattr(settings, "openrouter_referer", None) or "https://agentsparrow.local",
        "X-Title": getattr(settings, "openrouter_app_name", None) or "Agent Sparrow",
    }

    logger.debug(
        "building_openrouter_model",
        model=model,
        temperature=temperature,
        base_url=base_url,
    )

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
        default_headers=headers,
    )


def get_available_providers() -> dict[str, bool]:
    """Check which providers are configured and available.

    Returns:
        A dictionary mapping provider names to their availability status.

    Example:
        >>> get_available_providers()
        {'google': True, 'xai': False, 'openrouter': False}
    """
    return {
        "google": bool(settings.gemini_api_key),
        "xai": bool(settings.xai_api_key),
        "openrouter": bool(getattr(settings, "openrouter_api_key", None)),
    }


def get_default_model_for_provider(provider: str) -> str:
    """Get the default model for a provider from registry.

    Args:
        provider: The provider name.

    Returns:
        The default model identifier for the provider.
    """
    registry = get_registry()
    defaults = {
        "google": registry.coordinator_google.id,
        "xai": registry.coordinator_xai.id,
        "openrouter": registry.coordinator_openrouter.id,
    }
    return defaults.get(provider.lower(), registry.coordinator_google.id)
