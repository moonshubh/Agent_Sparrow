"""Centralized Model Registry backed by YAML configuration."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from enum import Enum

from app.core.config.config_loader import (
    ModelsConfig,
    find_model_config,
    get_models_config,
    iter_model_configs,
    resolve_coordinator_config,
)


class ModelTier(Enum):
    """Model capability tiers for routing and fallback decisions."""

    PRO = "pro"
    STANDARD = "standard"
    LITE = "lite"
    EMBEDDING = "embedding"

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
    """Immutable specification for a model."""

    id: str
    display_name: str
    provider: Provider
    tier: ModelTier
    supports_reasoning: bool = True
    supports_vision: bool = True
    always_enable_reasoning: bool = False
    embedding_dims: int | None = None
    expose_in_ui: bool = True


def _sanitize_display_name(model_id: str) -> str:
    """Sanitize model ID into a safe display name."""
    safe_id = re.sub(r"[<>&\"']", "", model_id)
    display = safe_id.replace("-", " ").replace("_", " ").replace("/", " ")
    return display.title()[:64]


def _infer_tier(model_id: str, *, embedding: bool, explicit: str | None) -> ModelTier:
    if explicit:
        normalized = explicit.strip().lower()
        if normalized == "pro":
            return ModelTier.PRO
        if normalized == "lite":
            return ModelTier.LITE
        if normalized == "embedding":
            return ModelTier.EMBEDDING
        return ModelTier.STANDARD
    if embedding:
        return ModelTier.EMBEDDING

    model_lower = model_id.lower()
    if "pro" in model_lower:
        return ModelTier.PRO
    if "lite" in model_lower:
        return ModelTier.LITE
    return ModelTier.STANDARD


def _provider_enum(provider: str) -> Provider:
    normalized = provider.strip().lower()
    if normalized == "xai":
        return Provider.XAI
    if normalized == "openrouter":
        return Provider.OPENROUTER
    return Provider.GOOGLE


def _spec_from_config(
    model_id: str,
    provider: str,
    *,
    tier_hint: str | None,
    display_name: str | None,
    supports_reasoning: bool | None,
    supports_vision: bool | None,
    always_enable_reasoning: bool | None,
    embedding_dims: int | None,
    expose_in_ui: bool | None,
    category: str,
) -> ModelSpec:
    provider_enum = _provider_enum(provider)
    embedding = category == "internal" and model_id.lower().startswith("models/")
    tier = _infer_tier(model_id, embedding=embedding, explicit=tier_hint)

    display = display_name or _sanitize_display_name(model_id)

    if supports_reasoning is None:
        supports_reasoning = tier != ModelTier.EMBEDDING
    if supports_vision is None:
        supports_vision = tier != ModelTier.EMBEDDING

    if always_enable_reasoning is None:
        always_enable_reasoning = False

    if expose_in_ui is None:
        if category.startswith("internal") or tier == ModelTier.EMBEDDING:
            expose_in_ui = False
        elif category.startswith("zendesk"):
            expose_in_ui = False
        else:
            expose_in_ui = True

    return ModelSpec(
        id=model_id,
        display_name=display,
        provider=provider_enum,
        tier=tier,
        supports_reasoning=supports_reasoning,
        supports_vision=supports_vision,
        always_enable_reasoning=always_enable_reasoning,
        embedding_dims=embedding_dims,
        expose_in_ui=bool(expose_in_ui),
    )


class ModelRegistry:
    """Registry that maps logical roles to YAML-defined models."""

    def __init__(self, config: ModelsConfig):
        self._config = config
        self._specs_by_id = self._build_model_specs(config)

    @property
    def coordinator_google(self) -> ModelSpec:
        return self._spec_for_config(self._config.coordinators["google"])

    @property
    def coordinator_google_with_subagents(self) -> ModelSpec:
        return self._spec_for_config(self._config.coordinators["google_with_subagents"])

    @property
    def coordinator_xai(self) -> ModelSpec:
        return self._spec_for_config(self._config.coordinators["xai"])

    @property
    def coordinator_xai_with_subagents(self) -> ModelSpec:
        return self._spec_for_config(self._config.coordinators["xai_with_subagents"])

    @property
    def coordinator_openrouter(self) -> ModelSpec:
        return self._spec_for_config(self._config.coordinators["openrouter"])

    @property
    def coordinator_openrouter_with_subagents(self) -> ModelSpec:
        return self._spec_for_config(
            self._config.coordinators["openrouter_with_subagents"]
        )

    @property
    def summarizer(self) -> ModelSpec:
        return self._spec_for_config(self._config.internal["summarizer"])

    @property
    def helper(self) -> ModelSpec:
        return self._spec_for_config(self._config.internal["helper"])

    @property
    def feedme(self) -> ModelSpec:
        return self._spec_for_config(self._config.internal["feedme"])

    @property
    def grounding(self) -> ModelSpec:
        return self._spec_for_config(self._config.internal["grounding"])

    @property
    def embedding(self) -> ModelSpec:
        return self._spec_for_config(self._config.internal["embedding"])

    @property
    def log_analysis(self) -> ModelSpec:
        return self.coordinator_google

    @property
    def db_retrieval(self) -> ModelSpec:
        # Prefer helper if present; otherwise fall back to coordinator.
        helper = self._config.internal.get("helper")
        if helper is not None:
            return self._spec_for_config(helper)
        return self.coordinator_google

    def _spec_for_config(self, model_cfg) -> ModelSpec:
        return self._specs_by_id[model_cfg.model_id]

    def get_model_for_role(self, role: str, provider: str = "google") -> ModelSpec:
        role_normalized = (role or "").strip().lower()
        provider_normalized = (provider or "google").strip().lower()

        if role_normalized == "coordinator":
            try:
                config = resolve_coordinator_config(self._config, provider_normalized)
            except ValueError:
                config = resolve_coordinator_config(self._config, "google")
            return self._spec_for_config(config)

        if role_normalized == "log_analysis":
            return self.coordinator_google

        aliases = {"lightweight": "db_retrieval", "embeddings": "embedding"}
        role_key = aliases.get(role_normalized, role_normalized)

        if role_key in self._config.internal:
            return self._spec_for_config(self._config.internal[role_key])

        if role_key == "db_retrieval":
            return self.db_retrieval

        return self.coordinator_google

    def get_display_names(self) -> dict[str, str]:
        return {
            model_id: spec.display_name for model_id, spec in self._specs_by_id.items()
        }

    def get_provider_display_names(self) -> dict[str, str]:
        return {
            "google": "Google Gemini",
            "xai": "xAI Grok",
            "openrouter": "OpenRouter",
        }

    def get_fallback_chain(self, provider: str = "google") -> dict[str, str | None]:
        provider_lower = (provider or "google").strip().lower()
        chain: dict[str, str | None] = {}

        if provider_lower == "google":
            google_id = self.coordinator_google.id
            # Prefer same-provider degradations before cross-provider failover.
            # This keeps coordinator behavior predictable under transient Gemini 3
            # overload events while still providing a robust fallback path.
            candidates: list[str] = []

            summarizer_cfg = self._config.internal.get("summarizer")
            grounding_cfg = self._config.internal.get("grounding")
            helper_cfg = self._config.internal.get("helper")
            if summarizer_cfg and summarizer_cfg.model_id:
                candidates.append(summarizer_cfg.model_id)
            if grounding_cfg and grounding_cfg.model_id:
                candidates.append(grounding_cfg.model_id)
            if helper_cfg and helper_cfg.model_id:
                candidates.append(helper_cfg.model_id)

            filtered: list[str] = []
            seen: set[str] = {google_id}
            for candidate in candidates:
                if (
                    candidate
                    and candidate not in seen
                    and candidate in self._specs_by_id
                ):
                    filtered.append(candidate)
                    seen.add(candidate)

            if filtered:
                cursor = google_id
                for next_model in filtered:
                    chain[cursor] = next_model
                    cursor = next_model
                chain.setdefault(cursor, None)
            else:
                chain.setdefault(google_id, None)
        elif provider_lower == "openrouter":
            openrouter_id = self.coordinator_openrouter.id
            default_subagent = self._config.subagents.get("_default")
            if (
                default_subagent is not None
                and default_subagent.model_id != openrouter_id
            ):
                chain[openrouter_id] = default_subagent.model_id
                chain.setdefault(default_subagent.model_id, None)
            else:
                chain[openrouter_id] = None
        else:
            chain[self.coordinator_xai.id] = None

        return chain

    def get_rate_limits(self, model_id: str) -> tuple[int, int]:
        config = find_model_config(self._config, model_id)
        if config is None:
            return (0, 0)
        return (config.rate_limits.rpm, config.rate_limits.rpd)

    def get_models_by_provider(self, provider: str) -> list[ModelSpec]:
        provider_lower = (provider or "google").strip().lower()
        return [
            spec
            for spec in self._specs_by_id.values()
            if str(spec.provider) == provider_lower
        ]

    def get_models_by_tier(self, tier: ModelTier) -> list[ModelSpec]:
        return [spec for spec in self._specs_by_id.values() if spec.tier == tier]

    def get_available_models_for_api(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {"google": [], "xai": [], "openrouter": []}
        for spec in self._specs_by_id.values():
            if spec.tier == ModelTier.EMBEDDING:
                continue
            if not spec.expose_in_ui:
                continue
            provider_key = str(spec.provider)
            if provider_key in result:
                result[provider_key].append(spec.id)
        return result

    def get_allowed_model_ids(self) -> set[str]:
        return set(self._specs_by_id.keys())

    @staticmethod
    def _build_model_specs(config: ModelsConfig) -> dict[str, ModelSpec]:
        specs: dict[str, ModelSpec] = {}
        for category, _, model in iter_model_configs(config):
            model_id = model.model_id
            if model_id in specs:
                existing = specs[model_id]
                if existing.embedding_dims is None and model.embedding_dims is not None:
                    specs[model_id] = ModelSpec(
                        id=existing.id,
                        display_name=existing.display_name,
                        provider=existing.provider,
                        tier=existing.tier,
                        supports_reasoning=existing.supports_reasoning,
                        supports_vision=existing.supports_vision,
                        always_enable_reasoning=existing.always_enable_reasoning,
                        embedding_dims=model.embedding_dims,
                        expose_in_ui=existing.expose_in_ui,
                    )
                continue

            specs[model_id] = _spec_from_config(
                model_id=model.model_id,
                provider=model.provider or "google",
                tier_hint=model.tier,
                display_name=model.display_name,
                supports_reasoning=model.supports_reasoning,
                supports_vision=model.supports_vision,
                always_enable_reasoning=model.always_enable_reasoning,
                embedding_dims=model.embedding_dims,
                expose_in_ui=model.expose_in_ui,
                category=category,
            )

        return specs


MODEL_REGISTRY = ModelRegistry(get_models_config())

_registry_lock = threading.Lock()
_registry_instance: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    """Get the model registry using cached YAML configuration."""
    global _registry_instance

    if _registry_instance is not None:
        return _registry_instance

    with _registry_lock:
        if _registry_instance is None:
            _registry_instance = ModelRegistry(get_models_config())
        return _registry_instance


def clear_registry_cache() -> None:
    """Clear the cached registry (useful for testing)."""
    global _registry_instance
    with _registry_lock:
        _registry_instance = None


def get_model_by_id(model_id: str) -> ModelSpec | None:
    """Look up a model spec by its ID."""
    registry = get_registry()
    return registry._specs_by_id.get(model_id)
