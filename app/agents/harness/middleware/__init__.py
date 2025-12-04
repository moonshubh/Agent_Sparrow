"""Custom middleware for Agent Sparrow.

Middleware components following DeepAgents patterns:
- SparrowMemoryMiddleware: mem0-based memory integration
- SparrowRateLimitMiddleware: Gemini quota management and model fallback
- ToolResultEvictionMiddleware: Large result eviction to prevent context overflow
- SessionInitMiddleware: Session handoff and goal context injection (NEW)
"""

from __future__ import annotations

from .memory_middleware import SparrowMemoryMiddleware
from .rate_limit_middleware import SparrowRateLimitMiddleware
from .eviction_middleware import ToolResultEvictionMiddleware
from .agent_mw_adapters import (
    SafeMiddleware,
    ToolRetryMiddleware,
    ToolCircuitBreakerMiddleware,
)
from .trace_seed import TraceSeedMiddleware
from .session_init_middleware import (
    SessionInitMiddleware,
    strip_session_context_messages,
    HANDOFF_SYSTEM_NAME,
    GOALS_SYSTEM_NAME,
    PROGRESS_SYSTEM_NAME,
)
from .handoff_capture_middleware import HandoffCaptureMiddleware

__all__ = [
    "SparrowMemoryMiddleware",
    "SparrowRateLimitMiddleware",
    "ToolResultEvictionMiddleware",
    "SafeMiddleware",
    "ToolRetryMiddleware",
    "ToolCircuitBreakerMiddleware",
    "TraceSeedMiddleware",
    # Session context engineering (Deep Agent pattern)
    "SessionInitMiddleware",
    "strip_session_context_messages",
    "HandoffCaptureMiddleware",
    "HANDOFF_SYSTEM_NAME",
    "GOALS_SYSTEM_NAME",
    "PROGRESS_SYSTEM_NAME",
]
