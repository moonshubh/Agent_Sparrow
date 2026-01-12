from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


def infer_provider_from_model_id(model_id: str) -> str:
    mid = (model_id or "").strip()
    lower = mid.lower()

    if lower.startswith("gemini"):
        return "google"
    if lower.startswith("models/"):
        return "google"
    if lower.startswith("grok") or lower.startswith("xai/"):
        return "xai"
    if "/" in mid:
        return "openrouter"
    return "google"


class RateLimitingSettings(BaseModel):
    safety_margin: float = Field(default=0.0, ge=0.0)

    model_config = ConfigDict(extra="ignore")


class ModelRateLimits(BaseModel):
    rpm: int | None = Field(default=None, ge=0)
    rpd: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="ignore")


class ModelConfig(BaseModel):
    model_id: str
    provider: str | None = None
    temperature: float | None = None
    context_window: int | None = Field(default=None, ge=1)
    embedding_dims: int | None = Field(default=None, ge=1)
    rate_limits: ModelRateLimits | None = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _infer_provider(self) -> "ModelConfig":
        if not self.provider:
            self.provider = infer_provider_from_model_id(self.model_id)
        return self


class SubagentConfig(BaseModel):
    model_id: str | None = None
    provider: str | None = None
    temperature: float | None = None
    context_window: int | None = Field(default=None, ge=1)
    rate_limits: ModelRateLimits | None = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _infer_provider(self) -> "SubagentConfig":
        if not self.provider and self.model_id:
            self.provider = infer_provider_from_model_id(self.model_id)
        return self

    def resolve(self, default: "SubagentConfig") -> "SubagentConfig":
        model_id = self.model_id or default.model_id
        if not model_id:
            raise ValueError("subagent model_id missing")

        provider = self.provider or default.provider or infer_provider_from_model_id(model_id)
        return SubagentConfig(
            model_id=model_id,
            provider=provider,
            temperature=self.temperature if self.temperature is not None else default.temperature,
            context_window=self.context_window if self.context_window is not None else default.context_window,
            rate_limits=self.rate_limits if self.rate_limits is not None else default.rate_limits,
        )


class ModelsConfig(BaseModel):
    rate_limiting: RateLimitingSettings = Field(default_factory=RateLimitingSettings)
    coordinators: dict[str, ModelConfig] = Field(default_factory=dict)
    internal: dict[str, ModelConfig] = Field(default_factory=dict)
    subagents: dict[str, SubagentConfig] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


_MODELS_CONFIG_CACHE: ModelsConfig | None = None
_MODELS_CONFIG_CACHE_PATH: str | None = None


def _default_models_config_dict() -> dict[str, Any]:
    # Minimal defaults used when MODELS_CONFIG_PATH isn't set and models.yaml
    # isn't present (e.g., lightweight test runs).
    return {
        "rate_limiting": {"safety_margin": 0.1},
        "subagents": {
            "_default": {
                "model_id": "minimax/minimax-m2.1",
                "context_window": 2048,
                "rate_limits": {"rpm": 2, "rpd": 20},
            }
        },
    }


def clear_models_config_cache() -> None:
    global _MODELS_CONFIG_CACHE, _MODELS_CONFIG_CACHE_PATH
    _MODELS_CONFIG_CACHE = None
    _MODELS_CONFIG_CACHE_PATH = None


def _resolve_models_config_path() -> Path:
    env_path = os.getenv("MODELS_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    # Default to repo root models.yaml when running from project root.
    return Path("models.yaml")


def get_models_config() -> ModelsConfig:
    global _MODELS_CONFIG_CACHE, _MODELS_CONFIG_CACHE_PATH

    path = _resolve_models_config_path()
    cache_key = str(path)
    if _MODELS_CONFIG_CACHE is not None and _MODELS_CONFIG_CACHE_PATH == cache_key:
        return _MODELS_CONFIG_CACHE

    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        raw = raw if isinstance(raw, dict) else {}
    else:
        raw = _default_models_config_dict()

    # YAML allows bare keys (e.g., `research-agent:`) which parse as None.
    # Treat these as empty dicts so they can inherit from defaults.
    subagents = raw.get("subagents")
    if isinstance(subagents, dict):
        for key, value in list(subagents.items()):
            if value is None:
                subagents[key] = {}
    config = ModelsConfig.model_validate(raw)

    default_subagent = config.subagents.get("_default")
    if not default_subagent or not default_subagent.model_id:
        raise ValueError("subagents._default is required")
    if not default_subagent.provider:
        default_subagent.provider = infer_provider_from_model_id(default_subagent.model_id)

    _MODELS_CONFIG_CACHE = config
    _MODELS_CONFIG_CACHE_PATH = cache_key
    return config


def resolve_subagent_config(config: ModelsConfig, name: str) -> SubagentConfig:
    default = config.subagents.get("_default")
    if not default or not default.model_id:
        raise ValueError("subagents._default is required")

    specific = config.subagents.get(name) or SubagentConfig()
    return specific.resolve(default)
