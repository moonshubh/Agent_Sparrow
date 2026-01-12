from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def infer_provider(model_id: str) -> str:
    """Infer provider from model_id pattern."""
    model_lower = (model_id or "").strip().lower()
    if model_lower.startswith("models/"):
        return "google"
    if "/" in model_lower:
        return "openrouter"
    if model_lower.startswith("gemini") or "gemini" in model_lower:
        return "google"
    if model_lower.startswith("grok") or "grok" in model_lower:
        return "xai"
    return "google"


class RateLimits(BaseModel):
    rpm: int = Field(..., description="Requests per minute")
    rpd: int = Field(..., description="Requests per day")
    tpm: int | None = Field(default=None, description="Tokens per minute (optional)")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_limits(self) -> "RateLimits":
        if self.rpm <= 0:
            raise ValueError("rate_limits.rpm must be positive")
        if self.rpd <= 0:
            raise ValueError("rate_limits.rpd must be positive")
        if self.tpm is not None and self.tpm <= 0:
            raise ValueError("rate_limits.tpm must be positive when set")
        return self


class RateLimitingConfig(BaseModel):
    safety_margin: float = Field(default=0.06, description="Safety margin for quotas")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_margin(self) -> "RateLimitingConfig":
        if self.safety_margin < 0 or self.safety_margin >= 0.5:
            raise ValueError("rate_limiting.safety_margin must be between 0 and 0.5")
        return self


class ModelConfig(BaseModel):
    model_id: str
    provider: str | None = None
    temperature: float = 0.3
    context_window: int = 128000
    rate_limits: RateLimits
    embedding_dims: int | None = None

    # Optional metadata fields (for UI/behavioral hints)
    display_name: str | None = None
    tier: str | None = None
    supports_reasoning: bool | None = None
    supports_vision: bool | None = None
    always_enable_reasoning: bool | None = None
    expose_in_ui: bool | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("model_id must be set")
        return normalized

    @field_validator("context_window")
    @classmethod
    def validate_context_window(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("context_window must be positive")
        return value

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if value < 0.0 or value > 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return value

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in {"google", "xai", "openrouter"}:
            raise ValueError(f"Unsupported provider: {value}")
        return normalized

    @model_validator(mode="after")
    def apply_provider_inference(self) -> "ModelConfig":
        if not self.provider:
            self.provider = infer_provider(self.model_id)
        return self


class FallbackConfig(BaseModel):
    strategy: str = Field(default="coordinator")
    coordinator_provider: str = Field(default="google")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_strategy(self) -> "FallbackConfig":
        strategy = (self.strategy or "").strip().lower()
        if strategy not in {"coordinator", "none"}:
            raise ValueError("fallback.strategy must be 'coordinator' or 'none'")
        self.strategy = strategy

        provider = (self.coordinator_provider or "").strip().lower()
        if provider not in {"google", "xai", "openrouter"}:
            raise ValueError("fallback.coordinator_provider must be google/xai/openrouter")
        self.coordinator_provider = provider
        return self


class ZendeskModelsConfig(BaseModel):
    coordinators: dict[str, ModelConfig]
    subagents: dict[str, ModelConfig | None]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_defaults(self) -> "ZendeskModelsConfig":
        default = self.subagents.get("_default")
        if default is None:
            raise ValueError("zendesk.subagents._default must be configured")
        return self


class ModelsConfig(BaseModel):
    rate_limiting: RateLimitingConfig = Field(default_factory=RateLimitingConfig)
    coordinators: dict[str, ModelConfig]
    internal: dict[str, ModelConfig]
    subagents: dict[str, ModelConfig | None]
    zendesk: ZendeskModelsConfig | None = None
    fallback: FallbackConfig = Field(default_factory=FallbackConfig)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_required_fields(self) -> "ModelsConfig":
        default = self.subagents.get("_default")
        if default is None:
            raise ValueError("subagents._default must be configured")
        return self


_config_cache: ModelsConfig | None = None
_config_mtime: float | None = None
_config_hash: str | None = None
_config_lock = threading.Lock()


def get_models_config_path() -> Path:
    override = os.getenv("MODELS_CONFIG_PATH")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parent / "models.yaml"


def _read_models_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(
            f"Models configuration not found at {path}. "
            "Set MODELS_CONFIG_PATH or create app/core/config/models.yaml."
        )
    return path.read_text(encoding="utf-8")


def load_models_config() -> ModelsConfig:
    """Load models.yaml and validate schema."""
    path = get_models_config_path()
    raw = _read_models_file(path)
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse models YAML: {exc}") from exc

    try:
        return ModelsConfig.model_validate(data)
    except Exception as exc:
        raise ValueError(f"Invalid models.yaml schema: {exc}") from exc


def get_models_config() -> ModelsConfig:
    """Get cached models config, loading from YAML if needed."""
    global _config_cache, _config_mtime, _config_hash
    path = get_models_config_path()
    reload_on_change = _parse_bool(os.getenv("MODELS_CONFIG_RELOAD"))

    with _config_lock:
        if _config_cache is not None and not reload_on_change:
            return _config_cache

        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            mtime = None

        if _config_cache is not None and reload_on_change:
            if _config_mtime is not None and mtime == _config_mtime:
                return _config_cache

        config = load_models_config()
        _config_cache = config
        _config_mtime = mtime
        _config_hash = hashlib.sha256(
            _read_models_file(path).encode("utf-8")
        ).hexdigest()
        return config


def get_models_config_hash() -> str:
    """Return a stable hash of the active models.yaml file."""
    if _config_hash is None:
        _ = get_models_config()
    return _config_hash or ""


def clear_models_config_cache() -> None:
    """Clear cached models config (useful for testing)."""
    global _config_cache, _config_mtime, _config_hash
    with _config_lock:
        _config_cache = None
        _config_mtime = None
        _config_hash = None


def iter_model_configs(config: ModelsConfig) -> Iterable[tuple[str, str, ModelConfig]]:
    """Iterate over all configured model entries with their category/key."""
    for key, model in config.coordinators.items():
        yield "coordinators", key, model
    for key, model in config.internal.items():
        yield "internal", key, model
    for key, model in config.subagents.items():
        if model is not None:
            yield "subagents", key, model
    if config.zendesk is not None:
        for key, model in config.zendesk.coordinators.items():
            yield "zendesk.coordinators", key, model
        for key, model in config.zendesk.subagents.items():
            if model is not None:
                yield "zendesk.subagents", key, model


def iter_rate_limit_buckets(config: ModelsConfig) -> Iterable[tuple[str, ModelConfig]]:
    """Iterate over rate-limit buckets with resolved ModelConfig."""
    for key, model in config.coordinators.items():
        yield f"coordinators.{key}", model
    for key, model in config.internal.items():
        yield f"internal.{key}", model
    for key in config.subagents.keys():
        resolved = config.subagents.get(key) or config.subagents.get("_default")
        if resolved is None:
            continue
        yield f"subagents.{key}", resolved
    if config.zendesk is not None:
        for key, model in config.zendesk.coordinators.items():
            yield f"zendesk.coordinators.{key}", model
        for key in config.zendesk.subagents.keys():
            resolved = config.zendesk.subagents.get(key) or config.zendesk.subagents.get("_default")
            if resolved is None:
                continue
            yield f"zendesk.subagents.{key}", resolved


def find_bucket_for_model(
    config: ModelsConfig,
    model_id: str,
    *,
    prefix: str | None = None,
) -> str | None:
    """Find the first bucket name that matches a given model_id."""
    target = (model_id or "").strip()
    if not target:
        return None
    for bucket, model_cfg in iter_rate_limit_buckets(config):
        if prefix and not bucket.startswith(prefix):
            continue
        if model_cfg.model_id == target:
            return bucket
    return None


def find_model_config(
    config: ModelsConfig,
    model_id: str,
) -> ModelConfig | None:
    """Find the first matching ModelConfig for a given model_id."""
    target = (model_id or "").strip()
    if not target:
        return None
    for _, _, model in iter_model_configs(config):
        if model.model_id == target:
            return model
    return None


def resolve_subagent_config(
    config: ModelsConfig,
    name: str,
    *,
    zendesk: bool = False,
) -> ModelConfig:
    """Resolve subagent config with fallback to _default."""
    subagents = config.subagents
    if zendesk and config.zendesk is not None:
        subagents = config.zendesk.subagents

    entry = subagents.get(name)
    if entry is None:
        entry = subagents.get("_default")
    if entry is None:
        raise ValueError(f"Subagent '{name}' missing _default configuration")
    return entry


def resolve_coordinator_config(
    config: ModelsConfig,
    provider: str,
    *,
    with_subagents: bool = False,
    zendesk: bool = False,
) -> ModelConfig:
    """Resolve coordinator config for provider and usage bucket."""
    provider_key = (provider or "google").strip().lower()
    key = f"{provider_key}_with_subagents" if with_subagents else provider_key

    coordinators = config.coordinators
    if zendesk and config.zendesk is not None:
        coordinators = config.zendesk.coordinators

    if key in coordinators:
        return coordinators[key]
    if provider_key in coordinators:
        return coordinators[provider_key]

    raise ValueError(f"Coordinator config not found for provider '{provider_key}'")


def coordinator_bucket_name(
    provider: str,
    *,
    with_subagents: bool = False,
    zendesk: bool = False,
) -> str:
    """Return the rate-limit bucket name for a coordinator."""
    provider_key = (provider or "google").strip().lower()
    key = f"{provider_key}_with_subagents" if with_subagents else provider_key
    prefix = "zendesk.coordinators" if zendesk else "coordinators"
    return f"{prefix}.{key}"


def resolve_bucket_config(config: ModelsConfig, bucket: str) -> ModelConfig:
    """Resolve a rate-limit bucket name to its ModelConfig."""
    normalized = (bucket or "").strip()
    if not normalized:
        raise ValueError("Bucket name is required")

    parts = normalized.split(".")
    if parts[0] == "coordinators" and len(parts) >= 2:
        return config.coordinators[parts[1]]
    if parts[0] == "internal" and len(parts) >= 2:
        return config.internal[parts[1]]
    if parts[0] == "subagents" and len(parts) >= 2:
        return resolve_subagent_config(config, parts[1])
    if parts[0] == "zendesk" and len(parts) >= 3 and config.zendesk is not None:
        if parts[1] == "coordinators":
            return config.zendesk.coordinators[parts[2]]
        if parts[1] == "subagents":
            return resolve_subagent_config(config, parts[2], zendesk=True)

    raise ValueError(f"Unknown rate-limit bucket '{bucket}'")
