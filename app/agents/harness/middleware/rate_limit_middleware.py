"""Rate limit middleware for Gemini quota management.

This middleware handles model quota checking and automatic fallback
to alternative models when rate limits are hit.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from loguru import logger

# Import shared stats from canonical location
from app.agents.harness._stats import RateLimitStats

if TYPE_CHECKING:
    from langgraph.config import RunnableConfig

try:
    from langchain.agents.middleware import AgentMiddleware
    from langchain.agents.middleware.types import ModelRequest, ModelResponse
    AGENT_MIDDLEWARE_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    AgentMiddleware = object  # type: ignore[assignment]
    ModelRequest = Any  # type: ignore[misc,assignment]
    ModelResponse = Any  # type: ignore[misc,assignment]
    AGENT_MIDDLEWARE_AVAILABLE = False

try:
    from google.api_core.exceptions import ResourceExhausted
except Exception:  # pragma: no cover - optional dependency
    ResourceExhausted = None


# Fallback chain for model degradation
FALLBACK_CHAIN: Dict[str, Optional[str]] = {
    "gemini-3-pro-preview": "gemini-2.5-pro",
    "gemini-3-pro": "gemini-2.5-pro",
    "gemini-3-flash": "gemini-2.5-flash",
    "gemini-3-flash-lite": "gemini-2.5-flash-lite",
    "gemini-2.5-pro": "gemini-2.5-flash",
    "gemini-2.5-flash": "gemini-2.5-flash-lite",
    "gemini-2.5-flash-lite": None,  # Terminal - no more fallbacks
}


class SparrowRateLimitMiddleware(AgentMiddleware if AGENT_MIDDLEWARE_AVAILABLE else object):
    """Middleware for Gemini quota management and model fallback.

    This middleware integrates with the rate limiter to:
    1. Check quota availability before model calls
    2. Automatically fall back to lower-tier models when quota exhausted
    3. Track usage statistics for observability

    The middleware uses a fallback chain:
    gemini-2.5-pro -> gemini-2.5-flash -> gemini-2.5-flash-lite -> (fail)

    Usage:
        middleware = SparrowRateLimitMiddleware()
        # Middleware is then added to the agent's middleware stack

    Attributes:
        fallback_chain: Dict mapping models to their fallbacks.
    """

    name: str = "sparrow_rate_limit"

    def __init__(
        self,
        fallback_chain: Optional[Dict[str, Optional[str]]] = None,
    ):
        """Initialize the rate limit middleware.

        Args:
            fallback_chain: Optional custom fallback chain.
        """
        self.fallback_chain = fallback_chain or FALLBACK_CHAIN
        self._rate_limiter = None
        self._stats = RateLimitStats()
        self._reserved_slots: List[tuple[str, Optional[str]]] = []
        self._current_model: Optional[str] = None  # Tracks active model for fallback
        self._stats_lock = asyncio.Lock()

    @property
    def rate_limiter(self):
        """Lazy-load rate limiter to avoid circular imports."""
        if self._rate_limiter is None:
            try:
                from app.core.rate_limiting.agent_wrapper import get_rate_limiter

                self._rate_limiter = get_rate_limiter()
            except ImportError:
                logger.warning("Rate limiter not available")
        return self._rate_limiter

    async def check_model_availability(
        self,
        model: str,
        config: "RunnableConfig",
    ) -> tuple[str, bool]:
        """Check if model is available and return fallback if needed.

        Args:
            model: Requested model name.
            config: Runnable configuration.

        Returns:
            Tuple of (actual_model_to_use, was_fallback_used).

        Raises:
            RateLimitExceededException: If all models in fallback chain exhausted.
        """
        from app.core.rate_limiting.exceptions import (
            CircuitBreakerOpenException,
            GeminiServiceUnavailableException,
            RateLimitExceededException,
        )

        async with self._stats_lock:
            self._stats = RateLimitStats(primary_model=model)
        attempted: Set[str] = set()
        current_model = model

        while current_model and current_model not in attempted:
            attempted.add(current_model)
            attempt_info = {"model": current_model, "available": False, "reason": None}

            try:
                if self.rate_limiter:
                    result = await self.rate_limiter.check_and_consume(current_model)
                    if getattr(result, "allowed", False):
                        self._reserved_slots.append(
                            (current_model, getattr(result, "token_identifier", None))
                        )
                        attempt_info["available"] = True
                        async with self._stats_lock:
                            self._stats.attempts.append(attempt_info)
                            self._stats.slot_reserved = True
                            if current_model != model:
                                self._stats.fallback_used = True
                                self._stats.fallback_model = current_model

                        return current_model, current_model != model
                else:
                    # No rate limiter - assume available
                    attempt_info["available"] = True
                    self._stats.attempts.append(attempt_info)
                    return current_model, False

            except RateLimitExceededException:
                attempt_info["reason"] = "rate_limited"
                logger.warning("model_rate_limited", model=current_model)
            except CircuitBreakerOpenException:
                attempt_info["reason"] = "circuit_open"
                logger.warning("model_circuit_open", model=current_model)
            except GeminiServiceUnavailableException as exc:
                attempt_info["reason"] = f"unavailable: {exc}"
                logger.warning("model_unavailable", model=current_model, error=str(exc))
            except Exception as exc:
                attempt_info["reason"] = f"error: {exc}"
                logger.warning("model_check_failed", model=current_model, error=str(exc))

            self._stats.attempts.append(attempt_info)

            # Try fallback
            fallback = self.get_fallback(current_model, attempted)
            if fallback:
                self._stats.fallback_reason = attempt_info["reason"]
                current_model = fallback
            else:
                break

        # All models exhausted
        from app.core.rate_limiting.exceptions import RateLimitExceededException

        raise RateLimitExceededException(
            f"All models exhausted in fallback chain starting from {model}"
        )

    def get_fallback(self, model: str, attempted: Optional[Set[str]] = None) -> Optional[str]:
        """Get fallback model, preventing cycles.

        Args:
            model: Current model.
            attempted: Set of already attempted models.

        Returns:
            Fallback model name, or None if no valid fallback.
        """
        attempted = attempted or set()
        fallback = self.fallback_chain.get(model)

        if fallback is None or fallback in attempted:
            return None

        return fallback

    def _resolve_model_name(self, model_obj: Any) -> Optional[str]:
        """Best-effort extraction of model name from a chat model instance."""
        if isinstance(model_obj, str):
            return model_obj
        for attr in ("model", "model_name", "model_id"):
            value = getattr(model_obj, attr, None)
            if isinstance(value, str) and value:
                return value
        return None

    def _apply_fallback_model(self, model_obj: Any, fallback_model: str) -> bool:
        """Attempt to update the model object in-place for fallback."""
        for attr in ("model", "model_name"):
            value = getattr(model_obj, attr, None)
            if isinstance(value, str):
                try:
                    setattr(model_obj, attr, fallback_model)
                    return True
                except Exception:  # pragma: no cover - defensive
                    continue
        return False

    def _is_quota_exhausted(self, exc: Exception) -> bool:
        if ResourceExhausted is not None and isinstance(exc, ResourceExhausted):
            return True
        message = str(exc).lower()
        return any(token in message for token in ("resourceexhausted", "quota", "rate limit", "429"))

    async def release_slots(self) -> None:
        """Release all reserved rate limit slots.

        Should be called in finally block after agent completion.
        """
        if not self.rate_limiter:
            return

        for model_name, token_identifier in self._reserved_slots:
            try:
                await self.rate_limiter.release_slot(model_name, token_identifier)
            except Exception as exc:
                logger.warning(
                    "rate_limit_slot_release_failed",
                    model=model_name,
                    error=str(exc),
                )

        self._reserved_slots.clear()

    def wrap_model_call(self, request: ModelRequest, handler: Callable) -> ModelResponse:
        """Sync wrapper for model calls (no-op rate limiting if async required)."""
        return handler(request)

    async def awrap_model_call(self, request: ModelRequest, handler: Callable) -> ModelResponse:
        """Async wrapper for model calls with quota checks and fallback."""
        from app.core.rate_limiting.exceptions import RateLimitExceededException

        model_name = self._resolve_model_name(getattr(request, "model", None))
        if not model_name:
            return await handler(request)

        self._current_model = model_name

        try:
            if self.rate_limiter:
                result = await self.rate_limiter.check_and_consume(model_name)
                if not getattr(result, "allowed", False):
                    metadata = getattr(result, "metadata", None)
                    limits = metadata.dict() if hasattr(metadata, "dict") else (
                        metadata if isinstance(metadata, dict) else None
                    )
                    raise RateLimitExceededException(
                        f"Rate limit exceeded for {model_name}",
                        retry_after=getattr(result, "retry_after", None),
                        limits=limits,
                        model=model_name,
                    )
                self._reserved_slots.append(
                    (model_name, getattr(result, "token_identifier", None))
                )
        except RateLimitExceededException:
            fallback = self.get_fallback(model_name)
            if fallback and self._apply_fallback_model(request.model, fallback):
                logger.info("retrying_with_fallback", primary=model_name, fallback=fallback)
                self._current_model = fallback
                return await handler(request)
            raise

        try:
            return await handler(request)
        except Exception as exc:
            if self._is_quota_exhausted(exc):
                raise RateLimitExceededException(
                    f"Rate limit exceeded for {model_name}",
                    model=model_name,
                ) from exc
            raise

    def set_current_model(self, model: str) -> None:
        """Set the current model being used (for tracking fallback context).

        Should be called before making model calls wrapped with wrap_model_call.

        Args:
            model: The model name being used.
        """
        self._current_model = model

    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiting statistics.

        Returns:
            Dict of stats for observability.
        """
        return self._stats.to_dict()

    def reset_stats(self) -> None:
        """Reset statistics for a new run."""
        self._stats = RateLimitStats()
