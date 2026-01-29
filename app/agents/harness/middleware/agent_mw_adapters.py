"""Adapters and resilience middleware for the Sparrow harness."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Type

from langchain_core.messages import ToolMessage
from loguru import logger

try:  # pragma: no cover - optional dependency
    from langchain.agents.middleware.types import (
        AgentMiddleware,
        ModelRequest,
        ModelResponse,
        ToolCallRequest,
    )

    MIDDLEWARE_AVAILABLE = True
except Exception:  # pragma: no cover
    AgentMiddleware = object  # type: ignore[assignment]
    ModelRequest = object  # type: ignore[assignment]
    ModelResponse = object  # type: ignore[assignment]
    ToolCallRequest = object  # type: ignore[assignment]
    MIDDLEWARE_AVAILABLE = False


class SafeMiddleware(AgentMiddleware):
    """Guard an inner middleware so failures don't break the chain."""

    def __init__(self, inner: AgentMiddleware, name: Optional[str] = None) -> None:
        super().__init__()
        self.inner = inner
        self.name = name or getattr(inner, "name", type(inner).__name__)

    async def abefore_agent(self, state: Dict[str, Any], runtime: Any) -> Optional[Dict[str, Any]]:
        try:
            if hasattr(self.inner, "abefore_agent"):
                return await self.inner.abefore_agent(state, runtime)
            if hasattr(self.inner, "before_agent"):
                return self.inner.before_agent(state, runtime)  # type: ignore
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("middleware_before_agent_failed", mw=self.name, error=str(exc))
        return None

    async def aafter_agent(self, state: Dict[str, Any], runtime: Any) -> Optional[Dict[str, Any]]:
        try:
            if hasattr(self.inner, "aafter_agent"):
                return await self.inner.aafter_agent(state, runtime)
            if hasattr(self.inner, "after_agent"):
                return self.inner.after_agent(state, runtime)  # type: ignore
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("middleware_after_agent_failed", mw=self.name, error=str(exc))
        return None

    def wrap_model_call(self, request: ModelRequest, handler) -> ModelResponse:
        try:
            if hasattr(self.inner, "wrap_model_call"):
                return self.inner.wrap_model_call(request, handler)  # type: ignore
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("middleware_wrap_model_call_failed", mw=self.name, error=str(exc))
        return handler(request)

    async def awrap_model_call(self, request: ModelRequest, handler) -> ModelResponse:
        try:
            if hasattr(self.inner, "awrap_model_call"):
                return await self.inner.awrap_model_call(request, handler)  # type: ignore
            if hasattr(self.inner, "wrap_model_call"):
                return self.inner.wrap_model_call(request, handler)  # type: ignore
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("middleware_awrap_model_call_failed", mw=self.name, error=str(exc))
        return await handler(request)

    async def awrap_tool_call(self, request: ToolCallRequest, handler) -> ToolMessage:
        try:
            if hasattr(self.inner, "awrap_tool_call"):
                return await self.inner.awrap_tool_call(request, handler)  # type: ignore
            if hasattr(self.inner, "wrap_tool_call"):
                return self.inner.wrap_tool_call(request, handler)  # type: ignore
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("middleware_awrap_tool_call_failed", mw=self.name, error=str(exc))
        return await handler(request)


@dataclass
class RetryConfig:
    max_attempts: int = 2
    base_delay_s: float = 0.4
    max_delay_s: float = 4.0
    jitter_s: float = 0.2
    retry_exceptions: Tuple[Type[BaseException], ...] = (TimeoutError, ConnectionError)


class ToolRetryMiddleware(AgentMiddleware):
    """Retry transient tool failures with backoff."""

    name = "tool_retry"

    def __init__(self, config: Optional[RetryConfig] = None) -> None:
        super().__init__()
        self.cfg = config or RetryConfig()

    async def awrap_tool_call(self, request: ToolCallRequest, handler) -> ToolMessage:
        attempts = 0
        last_exc: Optional[BaseException] = None
        while attempts < self.cfg.max_attempts:
            attempts += 1
            try:
                return await handler(request)
            except self.cfg.retry_exceptions as exc:
                last_exc = exc
                delay = min(self.cfg.max_delay_s, self.cfg.base_delay_s * (2 ** (attempts - 1)))
                await asyncio.sleep(delay + random.uniform(0, self.cfg.jitter_s))
            except Exception as exc:
                return self._error_tool_message(request, exc, attempts, retryable=False)

        return self._error_tool_message(request, last_exc or Exception("tool_failed"), attempts, retryable=True)

    def _error_tool_message(
        self,
        request: ToolCallRequest,
        exc: BaseException,
        attempts: int,
        retryable: bool,
    ) -> ToolMessage:
        tool_call_id = getattr(request, "tool_call_id", None) or getattr(request, "id", "unknown")
        tool_name = getattr(request, "name", None) or "tool"
        logger.warning(
            "tool_retry_exhausted",
            tool=tool_name,
            attempts=attempts,
            retryable=retryable,
            error=str(exc),
        )
        return ToolMessage(
            content=(
                f"Tool `{tool_name}` failed after {attempts} attempt(s). "
                f"{'May retry later.' if retryable else 'Not retryable.'} "
                f"Error: {exc}"
            ),
            tool_call_id=tool_call_id,
            name=tool_name,
            additional_kwargs={"error": True, "retryable": retryable},
        )


class ToolCircuitBreakerMiddleware(AgentMiddleware):
    """Simple circuit breaker per tool name."""

    name = "tool_circuit_breaker"

    def __init__(
        self,
        failure_threshold: int = 5,
        window_s: float = 60.0,
        cooloff_s: float = 60.0,
    ) -> None:
        super().__init__()
        self.failure_threshold = failure_threshold
        self.window_s = window_s
        self.cooloff_s = cooloff_s
        self._state: Dict[str, Dict[str, Any]] = {}

    def _state_for(self, tool_name: str) -> Dict[str, Any]:
        now = time.time()
        state = self._state.setdefault(tool_name, {"failures": [], "opened_until": 0.0})
        # Drop old failures
        state["failures"] = [ts for ts in state["failures"] if now - ts <= self.window_s]
        return state

    async def awrap_tool_call(self, request: ToolCallRequest, handler) -> ToolMessage:
        tool_name = getattr(request, "name", None) or "tool"
        tool_call_id = getattr(request, "tool_call_id", None) or getattr(request, "id", "unknown")
        now = time.time()
        state = self._state_for(tool_name)

        if state["opened_until"] > now:
            logger.warning("tool_circuit_open_short_circuit", tool=tool_name)
            return ToolMessage(
                content=f"Circuit breaker open for `{tool_name}`. Try later or pick another tool.",
                tool_call_id=tool_call_id,
                name=tool_name,
                additional_kwargs={"error": True, "circuit": "open"},
            )

        try:
            result = await handler(request)
            state["failures"].clear()
            return result
        except Exception:
            state["failures"].append(now)
            if len(state["failures"]) >= self.failure_threshold:
                state["opened_until"] = now + self.cooloff_s
                logger.warning("tool_circuit_opened", tool=tool_name, cooloff=self.cooloff_s)
            raise
