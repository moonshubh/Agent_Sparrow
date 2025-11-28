"""Provider factory for multi-model support.

This module provides a factory function for creating chat models from different
providers (Google Gemini, XAI/Grok) with consistent configuration and fallback behavior.

Usage:
    from app.agents.unified.provider_factory import build_chat_model

    model = build_chat_model(
        provider="xai",
        model="grok-4-1-fast-reasoning",
        temperature=0.3,
    )
"""

from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from loguru import logger

from app.core.settings import settings


# Type alias for supported providers
Provider = str  # "google" | "xai"


def build_chat_model(
    provider: str,
    model: str,
    temperature: float = 0.3,
    reasoning_enabled: Optional[bool] = None,
) -> BaseChatModel:
    """Build a chat model for the specified provider.

    Args:
        provider: The model provider ("google" or "xai").
        model: The model identifier (e.g., "gemini-2.5-flash", "grok-4-1-fast-reasoning").
        temperature: Sampling temperature for the model (0.0-2.0).
        reasoning_enabled: For XAI models, whether to enable reasoning mode.
            If None, uses the value from settings.xai_reasoning_enabled.

    Returns:
        A configured BaseChatModel instance.

    Raises:
        No exceptions are raised; unknown providers fall back to Google Gemini.

    Example:
        >>> model = build_chat_model("xai", "grok-4-1-fast-reasoning")
        >>> response = model.invoke("Hello!")
    """
    provider = provider.lower().strip()

    if provider == "google":
        return _build_google_model(model, temperature)

    elif provider == "xai":
        return _build_xai_model(model, temperature, reasoning_enabled)

    else:
        logger.warning(
            "unknown_provider_fallback",
            provider=provider,
            fallback="google",
            model=settings.primary_agent_model,
        )
        return _build_google_model(settings.primary_agent_model, temperature)


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

    logger.debug(
        "building_google_model",
        model=model,
        temperature=temperature,
    )

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        google_api_key=settings.gemini_api_key,
    )


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
    if not settings.xai_api_key:
        logger.warning(
            "xai_api_key_not_configured",
            fallback="google",
            model=settings.primary_agent_model,
        )
        return _build_google_model(settings.primary_agent_model, temperature)

    try:
        from langchain_xai import ChatXAI
    except ImportError as e:
        logger.error(
            "langchain_xai_import_failed",
            error=str(e),
            fallback="google",
        )
        return _build_google_model(settings.primary_agent_model, temperature)

    # Determine reasoning mode
    use_reasoning = (
        reasoning_enabled
        if reasoning_enabled is not None
        else settings.xai_reasoning_enabled
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


def get_available_providers() -> dict[str, bool]:
    """Check which providers are configured and available.

    Returns:
        A dictionary mapping provider names to their availability status.

    Example:
        >>> get_available_providers()
        {'google': True, 'xai': False}
    """
    return {
        "google": bool(settings.gemini_api_key),
        "xai": bool(settings.xai_api_key),
    }


def get_default_model_for_provider(provider: str) -> str:
    """Get the default model for a provider.

    Args:
        provider: The provider name.

    Returns:
        The default model identifier for the provider.
    """
    defaults = {
        "google": settings.primary_agent_model,
        "xai": settings.xai_default_model,
    }
    return defaults.get(provider.lower(), settings.primary_agent_model)
