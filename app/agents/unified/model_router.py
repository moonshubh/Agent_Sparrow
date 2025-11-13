"""Centralized model routing helpers for the unified agent.

This module encapsulates the logic for selecting coordinator and subagent
models with lightweight availability/fallback handling. It keeps model
decisions in one place so coordinator/subagent modules can focus on behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from loguru import logger

from app.core.settings import settings
from .model_health import ModelHealth, quota_tracker


CoordinatorTask = str


def _default_model_map() -> Dict[CoordinatorTask, str]:
    """Build the default task→model mapping from settings."""

    return {
        "coordinator": settings.primary_agent_model or "gemini-2.5-flash",
        "coordinator_heavy": "gemini-2.5-pro",
        "log_analysis": settings.enhanced_log_model or "gemini-2.5-pro",
        "lightweight": settings.router_model or "gemini-2.5-flash-lite",
        "embeddings": "models/gemini-embedding-001",
    }


def _default_fallbacks() -> Dict[str, str]:
    return {
        "gemini-2.5-pro": "gemini-2.5-flash",
        "gemini-2.5-flash-lite": "gemini-2.5-flash",
    }


@dataclass
class ModelRouter:
    """Simple task-based router with soft availability checks."""

    default_models: Dict[CoordinatorTask, str] = field(default_factory=_default_model_map)
    fallback_chain: Dict[str, str] = field(default_factory=_default_fallbacks)
    allowed_models: Optional[Set[str]] = None

    def is_available(self, model: str) -> bool:
        """Return True when the requested model is permitted for execution."""

        if not model:
            return False
        if self.allowed_models is None:
            return True
        return model in self.allowed_models

    def select_model(
        self,
        task_type: CoordinatorTask,
        *,
        user_override: Optional[str] = None,
        check_availability: bool = True,
    ) -> str:
        """Resolve the model for the supplied task.

        Args:
            task_type: Logical task identifier (e.g., "coordinator", "log_analysis").
            user_override: Explicit model requested by the caller, if any.
            check_availability: When True, walk the fallback chain if a model is
                unavailable.
        """

        # Handle user override with optional availability check
        if user_override:
            if not check_availability:
                return user_override
            # Check if user override is available
            if self.is_available(user_override):
                return user_override
            # User override unavailable - log and continue to fallback logic
            logger.warning(
                "User override model '%s' is unavailable; using fallback selection",
                user_override
            )

        normalized_task = (task_type or "coordinator").strip().lower()
        model = self.default_models.get(normalized_task) or self.default_models.get("coordinator")
        if not model:
            logger.warning("Model router missing default for task '%s'; falling back to coordinator", normalized_task)
            model = "gemini-2.5-flash"

        if not check_availability:
            return model

        visited: Set[str] = set()
        current = model
        while current and not self.is_available(current):
            visited.add(current)
            fallback = self.fallback_chain.get(current)
            if not fallback or fallback in visited:
                logger.warning(
                    "Model '%s' unavailable and no fallback configured; returning it anyway.",
                    current,
                )
                break
            logger.info("Falling back from %s to %s", current, fallback)
            current = fallback

        # Ensure we return an available model or the last attempted one
        if current and self.is_available(current):
            return current
        # If still unavailable, return the original model as last resort
        return current or model

    async def select_model_with_health(
        self,
        task_type: CoordinatorTask,
        *,
        user_override: Optional[str] = None,
    ) -> "ModelSelectionResult":
        """Resolve a model while collecting quota/circuit health telemetry."""

        normalized_task = (task_type or "coordinator").strip().lower()
        health_trace: List[ModelHealth] = []

        if user_override:
            health = await quota_tracker.get_health(user_override)
            health_trace.append(health)
            # Only return override if it's available
            if health.available:
                return ModelSelectionResult(normalized_task, user_override, health_trace)
            # Override unavailable - log and continue to fallback logic
            logger.warning(
                "User override model '%s' is unavailable (health check failed); using fallback selection",
                user_override
            )

        candidate = self.select_model(normalized_task, check_availability=False)
        visited: Set[str] = set()
        while candidate:
            health = await quota_tracker.get_health(candidate)
            health_trace.append(health)
            if health.available:
                return ModelSelectionResult(normalized_task, candidate, health_trace)
            fallback = self.fallback_chain.get(candidate)
            if not fallback or fallback in visited:
                logger.warning(
                    "Quota exhausted for %s and no viable fallback; using %s despite limited availability",
                    candidate,
                    candidate,
                )
                break
            visited.add(candidate)
            candidate = fallback

        # Either no candidate or last one is exhausted – return the last attempt for transparency.
        final_model = candidate or self.default_models.get("coordinator") or "gemini-2.5-flash"
        return ModelSelectionResult(normalized_task, final_model, health_trace)


# Shared router instance for coordinator + subagents
model_router = ModelRouter()


@dataclass
class ModelSelectionResult:
    task_type: str
    model: str
    health_trace: List[ModelHealth]

    def trace_dict(self) -> List[Dict[str, Optional[str]]]:
        return [health.as_dict() for health in self.health_trace]
