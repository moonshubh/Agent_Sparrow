"""Provider-aware rate limit wrappers.

Thin re-exports of core rate limiting wrappers under a provider-centric path.
"""

from __future__ import annotations

from app.core.rate_limiting.agent_wrapper import (
    wrap_gemini_agent as wrap_gemini_agent,
)

__all__ = [
    "wrap_gemini_agent",
]
