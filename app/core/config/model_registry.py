"""Centralized Model Registry - Single source of truth for all model configurations.

This module provides a unified registry for all AI models used in Agent Sparrow.
To update models across the entire system, simply modify the model specs and role
assignments in this file.

Usage:
    from app.core.config import get_registry, MODEL_REGISTRY

    # Get the registry (with env var overrides)
    registry = get_registry()

    # Get model for a role
    model_id = registry.coordinator.id

    # Get display names for all models
    display_names = registry.get_display_names()

    # Get fallback chain
    fallbacks = registry.get_fallback_chain()
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field, replace
from enum import Enum


class ModelTier(Enum):
    """Model capability tiers for routing and fallback decisions."""

    PRO = "pro"  # Highest capability - complex reasoning, analysis
    STANDARD = "standard"  # Balanced - general purpose
    LITE = "lite"  # Cost-efficient - simple tasks
    EMBEDDING = "embedding"  # Vector embeddings (separate API)

    def __str__(self) -> str:
        return self.value


class Provider(Enum):
    """Supported LLM providers."""

    GOOGLE = "google"
    XAI = "xai"
    OPENROUTER = "openrouter"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Immutable specification for a model.

    Attributes:
        id: API model identifier (e.g., "gemini-3-pro-preview")
        display_name: Human-readable name for UI/prompts
        provider: The provider (Google, xAI)
        tier: Capability tier for routing decisions
        rpm_limit: Requests per minute (free tier default)
        rpd_limit: Requests per day (free tier default)
        supports_reasoning: Whether model supports extended reasoning
        supports_vision: Whether model supports image inputs
        always_enable_reasoning: Whether to always request reasoning tokens (provider-specific)
        embedding_dims: Dimension count for embedding models (None for others)
        expose_in_ui: Whether to expose this model via public model-selection APIs
    """

    id: str
    display_name: str
    provider: Provider
    tier: ModelTier
    rpm_limit: int = 10
    rpd_limit: int = 250
    supports_reasoning: bool = False
    supports_vision: bool = False
    always_enable_reasoning: bool = False
    embedding_dims: int | None = None
    expose_in_ui: bool = True


# =============================================================================
# MODEL DEFINITIONS - Update these to change models across the entire system
# =============================================================================

# Google Gemini 3.0 Series (Latest - Dec 2025)
GEMINI_3_PRO = ModelSpec(
    id="gemini-3-pro-preview",
    display_name="Gemini 3.0 Pro",
    provider=Provider.GOOGLE,
    tier=ModelTier.PRO,
    rpm_limit=5,
    rpd_limit=200,
    supports_reasoning=True,
    supports_vision=True,
)

GEMINI_3_FLASH = ModelSpec(
    id="gemini-3-flash-preview",
    display_name="Gemini 3.0 Flash",
    provider=Provider.GOOGLE,
    tier=ModelTier.STANDARD,
    rpm_limit=1000,   # Tier 1: 1K RPM
    rpd_limit=10000,  # Tier 1: 10K RPD
    supports_reasoning=True,
    supports_vision=True,
)

# Google Gemini 2.5 Series (Stable)
GEMINI_PRO = ModelSpec(
    id="gemini-2.5-pro",
    display_name="Gemini 2.5 Pro",
    provider=Provider.GOOGLE,
    tier=ModelTier.PRO,
    rpm_limit=2,
    rpd_limit=100,
    supports_reasoning=True,
    supports_vision=True,
)

GEMINI_FLASH = ModelSpec(
    id="gemini-2.5-flash",
    display_name="Gemini 2.5 Flash",
    provider=Provider.GOOGLE,
    tier=ModelTier.STANDARD,
    rpm_limit=10,
    rpd_limit=250,
    supports_reasoning=True,
    supports_vision=True,
    expose_in_ui=False,
)

GEMINI_FLASH_LITE = ModelSpec(
    id="gemini-2.5-flash-lite",
    display_name="Gemini 2.5 Flash Lite",
    provider=Provider.GOOGLE,
    tier=ModelTier.LITE,
    rpm_limit=15,
    rpd_limit=500,
    supports_vision=True,
    expose_in_ui=False,
)

# Preview variants (for when stable isn't available yet)
GEMINI_FLASH_PREVIEW = ModelSpec(
    id="gemini-2.5-flash-preview-09-2025",
    display_name="Gemini 2.5 Flash (preview)",
    provider=Provider.GOOGLE,
    tier=ModelTier.STANDARD,
    rpm_limit=10,
    rpd_limit=250,
    supports_reasoning=True,
    supports_vision=True,
    expose_in_ui=False,
)

GEMINI_PRO_PREVIEW = ModelSpec(
    id="gemini-2.5-pro-preview-09-2025",
    display_name="Gemini 2.5 Pro (preview)",
    provider=Provider.GOOGLE,
    tier=ModelTier.PRO,
    rpm_limit=2,
    rpd_limit=100,
    supports_reasoning=True,
    supports_vision=True,
    expose_in_ui=False,
)

GEMINI_FLASH_LITE_PREVIEW = ModelSpec(
    id="gemini-2.5-flash-lite-preview-09-2025",
    display_name="Gemini 2.5 Flash Lite (preview)",
    provider=Provider.GOOGLE,
    tier=ModelTier.LITE,
    rpm_limit=15,
    rpd_limit=500,
    supports_vision=True,
    expose_in_ui=False,
)

# Embedding model
GEMINI_EMBEDDING = ModelSpec(
    id="models/gemini-embedding-001",
    display_name="Gemini Embeddings 001",
    provider=Provider.GOOGLE,
    tier=ModelTier.EMBEDDING,
    rpm_limit=100,
    rpd_limit=1000,
    embedding_dims=3072,
)

# xAI Grok Models
GROK_4_1_FAST = ModelSpec(
    id="grok-4-1-fast-reasoning",
    display_name="Grok 4.1 Fast",
    provider=Provider.XAI,
    tier=ModelTier.STANDARD,
    rpm_limit=60,
    rpd_limit=1000,
    supports_reasoning=True,
)

GROK_4 = ModelSpec(
    id="grok-4",
    display_name="Grok 4",
    provider=Provider.XAI,
    tier=ModelTier.PRO,
    rpm_limit=20,
    rpd_limit=500,
    supports_reasoning=True,
)

# OpenRouter (Grok via OpenRouter)
GROK_4_1_FAST_OPENROUTER = ModelSpec(
    id="x-ai/grok-4.1-fast",
    display_name="Grok 4.1 Fast",
    provider=Provider.OPENROUTER,
    tier=ModelTier.STANDARD,
    rpm_limit=60,
    rpd_limit=1000,
    supports_reasoning=True,
    always_enable_reasoning=True,
)

MINIMAX_M2_OPENROUTER = ModelSpec(
    id="minimax/minimax-m2.1",
    display_name="MiniMax M2.1 (OpenRouter)",
    provider=Provider.OPENROUTER,
    tier=ModelTier.STANDARD,
    rpm_limit=60,
    rpd_limit=1000,
    supports_reasoning=True,
    always_enable_reasoning=True,
)

# =============================================================================
# ALL MODELS COLLECTION - For iteration and lookup
# =============================================================================

ALL_MODELS: tuple[ModelSpec, ...] = (
    GEMINI_3_PRO,
    GEMINI_3_FLASH,
    GEMINI_PRO,
    GEMINI_FLASH,
    GEMINI_FLASH_LITE,
    GEMINI_FLASH_PREVIEW,
    GEMINI_PRO_PREVIEW,
    GEMINI_FLASH_LITE_PREVIEW,
    GEMINI_EMBEDDING,
    GROK_4_1_FAST,
    GROK_4,
    MINIMAX_M2_OPENROUTER,
    GROK_4_1_FAST_OPENROUTER,
)

# Lookup by ID
_MODELS_BY_ID: dict[str, ModelSpec] = {m.id: m for m in ALL_MODELS}

LEGACY_MODEL_ID_ALIASES: dict[str, str] = {
    # OpenRouter previously exposed a free tier suffix for this model.
    "x-ai/grok-4.1-fast:free": "x-ai/grok-4.1-fast",
    # OpenRouter model rename.
    "minimax/minimax-m2": "minimax/minimax-m2.1",
}


def normalize_model_id(model_id: str) -> str:
    """Normalize known legacy model IDs to current registry IDs."""
    normalized = (model_id or "").strip()
    return LEGACY_MODEL_ID_ALIASES.get(normalized, normalized)


def get_model_by_id(model_id: str) -> ModelSpec | None:
    """Look up a model spec by its ID."""
    return _MODELS_BY_ID.get(normalize_model_id(model_id))


# =============================================================================
# MODEL FAMILIES - Define fallback chains
# =============================================================================


@dataclass(slots=True)
class ModelFamily:
    """A family of models with defined fallback chain.

    The fallback chain is used when a model is unavailable (quota exhausted,
    circuit breaker open, etc.) to gracefully degrade to a lower-tier model.
    """

    primary: ModelSpec
    fallbacks: list[ModelSpec] = field(default_factory=list)

    def get_fallback_chain(self) -> dict[str, str | None]:
        """Generate fallback mapping compatible with model_router."""
        chain: dict[str, str | None] = {}
        models = [self.primary] + self.fallbacks
        for i, model in enumerate(models):
            if i + 1 < len(models):
                chain[model.id] = models[i + 1].id
            else:
                chain[model.id] = None  # Terminal - no more fallbacks
        return chain

    def get_all_model_ids(self) -> list[str]:
        """Get all model IDs in the family (primary + fallbacks)."""
        return [self.primary.id] + [m.id for m in self.fallbacks]


# Google model families
GOOGLE_STANDARD_FAMILY = ModelFamily(
    primary=GEMINI_3_FLASH,
    fallbacks=[GEMINI_FLASH, GEMINI_FLASH_LITE],
)

GOOGLE_HEAVY_FAMILY = ModelFamily(
    primary=GEMINI_3_PRO,  # NEW: Gemini 3.0 Pro for heavy tasks!
    fallbacks=[GEMINI_PRO, GEMINI_FLASH, GEMINI_FLASH_LITE],
)

# XAI model family
XAI_FAMILY = ModelFamily(
    primary=GROK_4_1_FAST,
    fallbacks=[],  # No fallback for XAI yet
)


# =============================================================================
# MODEL REGISTRY - Central role-to-model mapping
# =============================================================================


@dataclass
class ModelRegistry:
    """Central registry mapping agent roles to models.

    This is the single source of truth for which models are used throughout
    Agent Sparrow. To change a model for a specific role, update the
    corresponding field here.

    Role Definitions:
        coordinator: Primary agent for general queries (standard tier)
        coordinator_heavy: Complex reasoning requiring pro tier
        log_analysis: Log/trace analysis (uses heavy reasoning)
        research: Web research and synthesis
        db_retrieval: Cost-efficient database lookups
        grounding: Gemini search grounding
        feedme: Document processing
        embedding: Vector embeddings
    """

    # Primary agent models by provider
    coordinator_google: ModelSpec = field(default=GEMINI_3_FLASH)
    coordinator_xai: ModelSpec = field(default=GROK_4_1_FAST)
    coordinator_openrouter: ModelSpec = field(default=GROK_4_1_FAST_OPENROUTER)

    # Heavy reasoning - uses Gemini 3.0 Pro!
    coordinator_heavy: ModelSpec = field(default=GEMINI_3_PRO)

    # Subagent models
    # Log/trace analysis tends to be reasoning-heavy; override via ENHANCED_LOG_MODEL when needed.
    log_analysis: ModelSpec = field(default=GEMINI_3_PRO)
    research: ModelSpec = field(default=GEMINI_3_FLASH)
    db_retrieval: ModelSpec = field(default=GEMINI_FLASH_LITE)  # LITE tier for cost-efficient lookups

    # Specialized models
    grounding: ModelSpec = field(default=GEMINI_3_FLASH)
    feedme: ModelSpec = field(default=GEMINI_FLASH_LITE)
    embedding: ModelSpec = field(default=GEMINI_EMBEDDING)

    # Model families for fallback chains
    google_standard_family: ModelFamily = field(
        default_factory=lambda: GOOGLE_STANDARD_FAMILY
    )
    google_heavy_family: ModelFamily = field(
        default_factory=lambda: GOOGLE_HEAVY_FAMILY
    )
    xai_family: ModelFamily = field(default_factory=lambda: XAI_FAMILY)
    openrouter_family: ModelFamily = field(
        default_factory=lambda: ModelFamily(
            primary=GROK_4_1_FAST_OPENROUTER,
            fallbacks=[MINIMAX_M2_OPENROUTER],
        )
    )

    def get_model_for_role(
        self, role: str, provider: str = "google"
    ) -> ModelSpec:
        """Get the model spec for a specific role.

        Args:
            role: Role identifier (coordinator, log_analysis, etc.)
            provider: Provider preference (google, xai)

        Returns:
            ModelSpec for the role
        """
        role_normalized = role.strip().lower()
        provider_normalized = provider.strip().lower()

        # Handle coordinator specially based on provider
        if role_normalized == "coordinator":
            if provider_normalized == "xai":
                return self.coordinator_xai
            if provider_normalized == "openrouter":
                return self.coordinator_openrouter
            return self.coordinator_google

        # Handle aliases
        aliases = {"lightweight": "db_retrieval", "embeddings": "embedding"}
        attr_name = aliases.get(role_normalized, role_normalized)

        return getattr(self, attr_name, self.coordinator_google)

    def get_display_names(self) -> dict[str, str]:
        """Generate MODEL_DISPLAY_NAMES compatible dictionary.

        Returns:
            Dict mapping model IDs to display names
        """
        return {m.id: m.display_name for m in ALL_MODELS}

    def get_provider_display_names(self) -> dict[str, str]:
        """Get provider display names.

        Returns:
            Dict mapping provider IDs to display names
        """
        return {
            "google": "Google Gemini",
            "xai": "xAI Grok",
            "openrouter": "OpenRouter",
        }

    def get_fallback_chain(self, provider: str = "google") -> dict[str, str | None]:
        """Get the fallback chain for a provider.

        Args:
            provider: Provider identifier (google, xai, openrouter)

        Returns:
            Dict mapping model IDs to their fallback model IDs
        """
        if provider.lower() == "xai":
            return self.xai_family.get_fallback_chain()
        if provider.lower() == "openrouter":
            return self.openrouter_family.get_fallback_chain()
        # Combine both Google families
        chain = self.google_heavy_family.get_fallback_chain()
        chain.update(self.google_standard_family.get_fallback_chain())
        return chain

    def get_rate_limits(self, model_id: str) -> tuple[int, int]:
        """Get (rpm_limit, rpd_limit) for a model.

        Args:
            model_id: The model identifier

        Returns:
            Tuple of (rpm_limit, rpd_limit)
        """
        if model := get_model_by_id(model_id):
            return (model.rpm_limit, model.rpd_limit)
        # Fallback to Flash limits for unknown models
        return (GEMINI_FLASH.rpm_limit, GEMINI_FLASH.rpd_limit)

    def get_models_by_provider(self, provider: str) -> list[ModelSpec]:
        """Get all models for a specific provider.

        Args:
            provider: Provider identifier (google, xai, openrouter)

        Returns:
            List of ModelSpec for the provider
        """
        provider_lower = provider.lower()
        if provider_lower == "google":
            provider_enum = Provider.GOOGLE
        elif provider_lower == "xai":
            provider_enum = Provider.XAI
        else:
            provider_enum = Provider.OPENROUTER
        return [m for m in ALL_MODELS if m.provider == provider_enum]

    def get_models_by_tier(self, tier: ModelTier) -> list[ModelSpec]:
        """Get all models for a specific tier.

        Args:
            tier: ModelTier enum value

        Returns:
            List of ModelSpec for the tier
        """
        return [m for m in ALL_MODELS if m.tier == tier]

    def get_google_model_ids(self) -> set[str]:
        """Get all Google model IDs (for rate limiter initialization).

        Returns:
            Set of Google model IDs (excluding embeddings)
        """
        return {
            m.id
            for m in ALL_MODELS
            if m.provider == Provider.GOOGLE and m.tier != ModelTier.EMBEDDING
        }

    def get_available_models_for_api(self) -> dict[str, list[str]]:
        """Get models grouped by provider for API response.

        Returns:
            Dict mapping provider names to lists of model IDs
        """
        result: dict[str, list[str]] = {"google": [], "xai": [], "openrouter": []}
        for model in ALL_MODELS:
            if model.tier == ModelTier.EMBEDDING:
                continue  # Don't expose embedding models in selection
            if not model.expose_in_ui:
                continue
            provider_key = str(model.provider)
            if provider_key in result:
                result[provider_key].append(model.id)
        return result


# =============================================================================
# SINGLETON & ENV VAR OVERRIDE SUPPORT
# =============================================================================

# Default registry instance
MODEL_REGISTRY = ModelRegistry()

# Thread-safe singleton support
_registry_lock = threading.Lock()
_registry_instance: ModelRegistry | None = None

# Model ID validation pattern - alphanumeric with .-_ separators
MODEL_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,127}$")


def _validate_model_id(model_id: str) -> bool:
    """Validate a model ID against the expected pattern.

    Args:
        model_id: The model identifier to validate

    Returns:
        True if valid, False otherwise
    """
    return bool(MODEL_ID_PATTERN.match(model_id))


def _sanitize_display_name(model_id: str) -> str:
    """Sanitize model ID into a safe display name.

    Prevents XSS by only allowing safe characters and limiting length.

    Args:
        model_id: The model identifier

    Returns:
        Safe display name string
    """
    # Remove any HTML-like characters
    safe_id = re.sub(r"[<>&\"']", "", model_id)
    # Convert separators to spaces and title case
    display = safe_id.replace("-", " ").replace("_", " ").replace("/", " ")
    # Limit length
    return display.title()[:64]


def _find_or_create_spec(
    model_id: str, provider: Provider = Provider.GOOGLE
) -> ModelSpec:
    """Find existing spec or create one for unknown models.

    This allows env var overrides to specify model IDs not in the registry.
    For unknown models, the tier is inferred from the model name:
    - Contains "pro" -> PRO tier
    - Contains "lite" -> LITE tier
    - Otherwise -> STANDARD tier

    Note:
        Created specs assume supports_reasoning=True and supports_vision=True.
        This may not be accurate for all models.

    Args:
        model_id: The model identifier
        provider: Provider for new specs

    Returns:
        Existing or new ModelSpec

    Raises:
        ValueError: If model_id format is invalid
    """
    model_id = normalize_model_id(model_id)

    # Infer provider from model_id when possible (e.g., OpenRouter prefixes)
    model_id_lower = model_id.lower()
    if provider == Provider.GOOGLE and "openrouter" in model_id_lower:
        provider = Provider.OPENROUTER

    # Check existing models first
    if existing := get_model_by_id(model_id):
        return existing

    # Validate model ID format for new models
    if not _validate_model_id(model_id):
        raise ValueError(
            f"Invalid model ID format: {model_id!r}. "
            "Model IDs must be alphanumeric with .-/_ separators."
        )

    # Create spec for unknown model with defaults
    # Determine tier from model name heuristics
    tier = ModelTier.STANDARD
    if "pro" in model_id_lower:
        tier = ModelTier.PRO
    elif "lite" in model_id_lower:
        tier = ModelTier.LITE

    return ModelSpec(
        id=model_id,
        display_name=_sanitize_display_name(model_id),
        provider=provider,
        tier=tier,
        supports_reasoning=True,
        supports_vision=True,
    )


def _create_registry_with_overrides() -> ModelRegistry:
    """Create a new registry with environment variable overrides applied.

    This is an internal function that creates a registry using immutable
    patterns via dataclasses.replace().

    Returns:
        ModelRegistry with applied overrides
    """
    # Import here to avoid circular imports
    from app.core.settings import settings

    overrides: dict[str, ModelSpec] = {}

    # Build overrides dict (only for set env vars)
    try:
        if settings.primary_agent_model:
            overrides["coordinator_google"] = _find_or_create_spec(
                settings.primary_agent_model
            )

        if settings.enhanced_log_model:
            spec = _find_or_create_spec(settings.enhanced_log_model)
            overrides["log_analysis"] = spec
            overrides["coordinator_heavy"] = spec

        if settings.router_model:
            overrides["db_retrieval"] = _find_or_create_spec(settings.router_model)

        if settings.grounding_model:
            overrides["grounding"] = _find_or_create_spec(settings.grounding_model)

        if settings.feedme_model_name:
            overrides["feedme"] = _find_or_create_spec(settings.feedme_model_name)

        if settings.xai_default_model:
            overrides["coordinator_xai"] = _find_or_create_spec(
                settings.xai_default_model, provider=Provider.XAI
            )
        if getattr(settings, "openrouter_default_model", None):
            overrides["coordinator_openrouter"] = _find_or_create_spec(
                settings.openrouter_default_model, provider=Provider.OPENROUTER
            )
    except ValueError as e:
        # Log but don't fail - use defaults for invalid model IDs
        import logging

        logging.getLogger(__name__).warning(f"Invalid model ID in env var: {e}")

    # Use immutable replace pattern
    if overrides:
        return replace(MODEL_REGISTRY, **overrides)
    return MODEL_REGISTRY


def get_registry() -> ModelRegistry:
    """Get the model registry with environment variable overrides.

    This function returns a thread-safe singleton registry instance with
    any env var overrides applied. The result is cached for efficiency.

    Returns:
        ModelRegistry with applied overrides
    """
    global _registry_instance

    # Fast path: already initialized
    if _registry_instance is not None:
        return _registry_instance

    # Slow path: initialize with lock (double-checked locking)
    with _registry_lock:
        if _registry_instance is None:
            _registry_instance = _create_registry_with_overrides()
        return _registry_instance


def clear_registry_cache() -> None:
    """Clear the cached registry (useful for testing)."""
    global _registry_instance
    with _registry_lock:
        _registry_instance = None
