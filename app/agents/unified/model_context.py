"""Shared model context window metadata and helpers.

Centralizes provider/model context sizes to avoid drift across modules.
"""

from __future__ import annotations

from typing import Optional

# Model context window sizes (in tokens)
# Sourced from current provider docs/posts as of Dec 2025 where available.
# Unknown/future models use conservative estimates to avoid overfilling context.
MODEL_CONTEXT_WINDOWS = {
    # Google Gemini models (1M context per public docs for 1.5 Pro/Flash;
    # apply same cap to 2.x/3.x aliases used here).
    "gemini-3-pro-preview": 1_000_000,
    "gemini-3-pro-image-preview": 65_536,  # vision variant smaller window
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.5-flash-lite": 1_000_000,
    "gemini-2.5-pro": 1_000_000,
    "gemini-2.5-flash-preview-09-2025": 1_000_000,
    "gemini-2.5-flash-lite-preview-09-2025": 1_000_000,
    "gemini-2.0-flash": 1_000_000,
    "gemini-2.0-flash-lite": 1_000_000,
    "gemini-embedding-001": 3_584,
    "models/gemini-embedding-001": 3_584,

    # XAI Grok models (public Grok-1.5 docs cite 128K; use conservative 128K).
    "grok-4": 128_000,
    "grok-4-fast": 128_000,
    "grok-4-1-fast-reasoning": 128_000,
    "grok-3": 128_000,
    "grok-3-mini": 128_000,
    "grok-3-fast": 128_000,

    # OpenRouter aliases (mirror Grok/Gemini caps above).
    "x-ai/grok-4.1-fast": 128_000,
    "minimax/minimax-m2.1": 204_800,
    "google/gemini-2.5-flash": 1_000_000,
    "google/gemini-2.5-pro": 1_000_000,
    "google/gemini-3-pro-preview": 1_000_000,

    # OpenAI models (per OpenAI docs: GPT-4o/4o mini/4 Turbo 128K; GPT-4 8K; GPT-3.5 16K).
    "gpt-5.1": 128_000,  # placeholder until official doc; keep conservative
    "gpt-5": 128_000,
    "gpt-5-mini": 128_000,
    "gpt-5-nano": 128_000,
    "gpt-5-pro": 128_000,
    "gpt-4.1": 128_000,
    "gpt-4.1-mini": 128_000,
    "gpt-4.1-nano": 128_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,

    # Anthropic Claude models (Claude 3/3.5 family published at 200K).
    "claude-sonnet-4": 200_000,  # placeholder until official doc; keep conservative
    "claude-4-sonnet": 200_000,
    "claude-sonnet-4.5": 200_000,
    "claude-4.5-sonnet": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-sonnet": 200_000,
    "claude-3-haiku": 200_000,
    "claude-3.5-sonnet": 200_000,
}

# Provider-specific default context windows
PROVIDER_DEFAULT_CONTEXT = {
    "google": 1_000_000,
    "xai": 128_000,
    "openai": 128_000,
    "anthropic": 200_000,
}

DEFAULT_CONTEXT_WINDOW = 128_000


def get_model_context_window(model: str, provider: Optional[str] = None) -> int:
    """Get the context window size for a model.

    Order of resolution:
    1. Exact match (case-sensitive)
    2. Case-insensitive match
    3. Prefix match (versioned aliases)
    4. Provider inference from model name
    5. Provider default hint
    6. Global default
    """
    if not model:
        if provider and provider.lower() in PROVIDER_DEFAULT_CONTEXT:
            return PROVIDER_DEFAULT_CONTEXT[provider.lower()]
        return DEFAULT_CONTEXT_WINDOW

    model_lower = model.lower()

    if model in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model]

    for known_model, context in MODEL_CONTEXT_WINDOWS.items():
        if known_model.lower() == model_lower:
            return context

    for known_model, context in MODEL_CONTEXT_WINDOWS.items():
        if model_lower.startswith(known_model.lower()):
            return context
        if known_model.lower().startswith(model_lower):
            return context

    if "gemini" in model_lower:
        return PROVIDER_DEFAULT_CONTEXT.get("google", DEFAULT_CONTEXT_WINDOW)
    if "grok" in model_lower:
        return PROVIDER_DEFAULT_CONTEXT.get("xai", DEFAULT_CONTEXT_WINDOW)
    if "gpt" in model_lower:
        return PROVIDER_DEFAULT_CONTEXT.get("openai", DEFAULT_CONTEXT_WINDOW)
    if "claude" in model_lower:
        return PROVIDER_DEFAULT_CONTEXT.get("anthropic", DEFAULT_CONTEXT_WINDOW)

    if provider and provider.lower() in PROVIDER_DEFAULT_CONTEXT:
        return PROVIDER_DEFAULT_CONTEXT[provider.lower()]

    return DEFAULT_CONTEXT_WINDOW


__all__ = [
    "MODEL_CONTEXT_WINDOWS",
    "PROVIDER_DEFAULT_CONTEXT",
    "DEFAULT_CONTEXT_WINDOW",
    "get_model_context_window",
]
