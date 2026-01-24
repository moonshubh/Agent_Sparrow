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

from typing import Optional, cast

from langchain_core.language_models import BaseChatModel
from loguru import logger

from app.core.settings import settings
from app.core.config import find_model_config, get_models_config
from app.core.config.model_registry import get_model_by_id
from app.core.rate_limiting.agent_wrapper import RateLimitedAgent, wrap_gemini_agent


# Type alias for supported providers
Provider = str  # "google" | "xai" | "openrouter"

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


def _is_gemini_3_model(model: str) -> bool:
    """Check if a model is a Gemini 3 model.

    Args:
        model: The model identifier.

    Returns:
        True if the model is a Gemini 3 model.
    """
    model_lower = model.lower()
    return "gemini-3" in model_lower or "gemini3" in model_lower


def get_temperature_for_role(role: str, model: str | None = None) -> float:
    """Resolve temperature from models.yaml (model-first, role fallback)."""
    config = get_models_config()

    if model:
        match = find_model_config(config, model)
        if match is not None:
            return match.temperature

    role_key = (role or "").strip().lower()
    if role_key in {"summarization", "state_extraction"} and "summarizer" in config.internal:
        return config.internal["summarizer"].temperature
    if role_key == "feedme" and "feedme" in config.internal:
        return config.internal["feedme"].temperature
    if role_key in {"db_retrieval", "lightweight"} and "helper" in config.internal:
        return config.internal["helper"].temperature

    return 0.3


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
        model: The model identifier (e.g., "gemini-3-flash-preview", "grok-4-1-fast-reasoning").
        temperature: Sampling temperature for the model (0.0-2.0).
            If None, temperature is determined automatically:
            - Pulled from models.yaml for the selected model/role
            Explicit temperature values will override these defaults.
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

    # Determine temperature: explicit > model-aware role-based > default
    if temperature is None:
        temperature = get_temperature_for_role(role or "default", model)

    if provider == "google":
        return _build_google_model(model, temperature)

    elif provider == "xai":
        return _build_xai_model(model, temperature, reasoning_enabled)

    elif provider == "openrouter":
        return _build_openrouter_model(model, temperature, role=role)

    else:
        config = get_models_config()
        fallback_model = config.coordinators["google"].model_id
        logger.warning(
            "provider_unavailable",
            provider=provider,
            reason="unknown_provider",
            fallback_provider="google",
            fallback_model=fallback_model,
        )
        return _build_google_model(fallback_model, temperature)


def build_summarization_model() -> BaseChatModel:
    """Build the fixed summarization/state-extraction model.

    Spec requirement:
    - Always uses Google direct Gemini 2.5 Flash Preview (Sep 2025).
    - Must not depend on the coordinator provider/model selection.
    """
    config = get_models_config()
    summarizer = config.internal["summarizer"]
    model_id = summarizer.model_id
    model = build_chat_model(
        provider="google",
        model=model_id,
        temperature=summarizer.temperature,
        role="summarization",
    )
    if model.__class__.__name__ == "ChatGoogleGenerativeAI":
        return cast(BaseChatModel, wrap_gemini_agent(model, "internal.summarizer", model_id))
    return cast(BaseChatModel, RateLimitedAgent(model, "internal.summarizer"))


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

    # Check if this is a Gemini 3 thinking model (use helper for consistency)
    is_gemini_3 = _is_gemini_3_model(model)
    is_thinking_model = is_gemini_3 or "gemini-2.5" in model.lower()

    logger.debug(
        "building_google_model",
        model=model,
        temperature=temperature,
        is_thinking_model=is_thinking_model,
        is_gemini_3=is_gemini_3,
    )

    trace_mode = getattr(settings, "trace_mode", "narrated")
    include_thoughts = trace_mode in {"hybrid", "provider_reasoning"}

    # Configure Gemini model thinking settings.
    # `langchain-google-genai==3.2.0` supports `thinking_config` via:
    # - include_thoughts
    # - thinking_budget (Gemini 2.5+)
    # - thinking_level (Gemini 3+, API-dependent)
    kwargs = {
        "model": model,
        "temperature": temperature,
        "google_api_key": settings.gemini_api_key,
        "include_thoughts": include_thoughts,
        "timeout": REQUEST_TIMEOUT_SECONDS,  # Prevent 504 Deadline Exceeded errors
    }

    if include_thoughts:
        if is_gemini_3:
            # Gemini 3: request high thinking depth when supported.
            kwargs["thinking_level"] = "high"
        else:
            # Gemini 2.5: optional thinking budget (tokens).
            if settings.primary_agent_thinking_budget is not None:
                kwargs["thinking_budget"] = settings.primary_agent_thinking_budget

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
    config = get_models_config()
    fallback_model = config.coordinators["google"].model_id

    if not settings.xai_api_key:
        logger.warning(
            "provider_unavailable",
            provider="xai",
            reason="api_key_missing",
            fallback_provider="google",
            fallback_model=fallback_model,
        )
        return _build_google_model(fallback_model, temperature)

    try:
        from langchain_xai import ChatXAI
    except ImportError as e:
        logger.error(
            "provider_unavailable",
            provider="xai",
            reason="langchain_xai_import_failed",
            error=str(e),
            fallback_provider="google",
            fallback_model=fallback_model,
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

    # Grok reasoning exposure varies by model family.
    # Grok 3: supports `reasoning_content` with `reasoning_effort` in extra_body.
    # Grok 4: may ignore/reject these flags; keep request minimal.
    model_lower = model.lower()
    extra_body = None
    if use_reasoning and "grok-3" in model_lower:
        extra_body = {"reasoning_effort": "high"}

    return ChatXAI(
        model=model,
        temperature=temperature,
        xai_api_key=settings.xai_api_key,
        extra_body=extra_body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def _is_minimax_model(model: str) -> bool:
    """Check if a model is a Minimax model.

    Args:
        model: The model identifier.

    Returns:
        True if the model is a Minimax model (e.g., minimax/MiniMax-M2.1).
    """
    model_lower = model.lower()
    return "minimax" in model_lower


def _build_openrouter_model(
    model: str, temperature: float, *, role: str | None = None
) -> BaseChatModel:
    """Build an OpenRouter chat model.

    Also handles Minimax models by routing them to the Minimax API directly
    when MINIMAX_API_KEY is configured. This allows using the same OpenRouter
    code path with Minimax's native API.
    """
    from .openrouter_chat_openai import OpenRouterChatOpenAI

    # Check if this is a Minimax model and we have a direct API key
    is_minimax = _is_minimax_model(model)
    minimax_api_key = getattr(settings, "minimax_api_key", None)

    if is_minimax and minimax_api_key:
        # Route Minimax models to Minimax API directly
        base_url = getattr(settings, "minimax_base_url", None) or "https://api.minimax.io/v1"
        api_key = minimax_api_key

        # Extract the actual model name (e.g., "minimax/MiniMax-M2.1" -> "MiniMax-M2.1")
        actual_model = model.split("/")[-1] if "/" in model else model

        logger.info(
            "routing_to_minimax_api",
            original_model=model,
            actual_model=actual_model,
            base_url=base_url,
        )

        # Minimax M2.1 Interleaved Thinking requirements:
        # - reasoning_split=True: Separates thinking into `reasoning_details` field
        # - Our OpenRouterChatOpenAI wrapper preserves reasoning_details across turns
        # - This enables M2.1's chain-of-thought to remain uninterrupted
        # See: https://platform.minimax.io/docs/guides/text-m2-function-call
        extra_body = {"reasoning_split": True}

        # Minimax recommended parameters: temperature=1.0, top_p=0.95
        # But we respect the role-based temperature from our config
        return OpenRouterChatOpenAI(
            model=actual_model,
            temperature=temperature,
            api_key=api_key,
            base_url=base_url,
            extra_body=extra_body,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    # Standard OpenRouter path
    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        config = get_models_config()
        fallback_model = config.coordinators["google"].model_id
        logger.warning(
            "provider_unavailable",
            provider="openrouter",
            reason="api_key_missing",
            fallback_provider="google",
            fallback_model=fallback_model,
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

    trace_mode = getattr(settings, "trace_mode", "narrated")
    spec = get_model_by_id(model)
    supports_reasoning = spec.supports_reasoning if spec is not None else True
    include_reasoning = trace_mode in {"hybrid", "provider_reasoning"}

    # OpenRouter reasoning tokens: enable to receive `reasoning_details` and allow
    # reasoning continuity by echoing `reasoning_details` back in subsequent turns.
    extra_body = None
    if supports_reasoning:
        always_enable = spec.always_enable_reasoning if spec is not None else False
        if always_enable or include_reasoning:
            # OpenRouter expects `reasoning` as an object (not a string). See:
            # https://openrouter.ai/docs/use-cases/reasoning-tokens
            extra_body = {"reasoning": {"effort": "high"}}

    return OpenRouterChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
        default_headers=headers,
        extra_body=extra_body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def get_available_providers() -> dict[str, bool]:
    """Check which providers are configured and available.

    Returns:
        A dictionary mapping provider names to their availability status.

    Example:
        >>> get_available_providers()
        {'google': True, 'xai': False, 'openrouter': False, 'minimax': True}
    """
    return {
        "google": bool(settings.gemini_api_key),
        "xai": bool(settings.xai_api_key),
        "openrouter": bool(getattr(settings, "openrouter_api_key", None)),
        "minimax": bool(getattr(settings, "minimax_api_key", None)),
    }


def get_default_model_for_provider(provider: str) -> str:
    """Get the default model for a provider from registry.

    Args:
        provider: The provider name.

    Returns:
        The default model identifier for the provider.
    """
    config = get_models_config()
    defaults = {
        "google": config.coordinators["google"].model_id,
        "xai": config.coordinators["xai"].model_id,
        "openrouter": config.coordinators["openrouter"].model_id,
    }
    return defaults.get(provider.lower(), config.coordinators["google"].model_id)
