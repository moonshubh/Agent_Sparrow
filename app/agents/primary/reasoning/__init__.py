"""Compatibility layer for primary reasoning components.

Canonical import path: app.agents.primary.reasoning
Temporarily re-exports from app.agents.primary.primary_agent.reasoning.*
"""

try:
    from app.agents.primary.primary_agent.reasoning.reasoning_engine import (
        ReasoningEngine,  # noqa: F401
        ReasoningConfig,  # noqa: F401
    )
    from app.agents.primary.primary_agent.reasoning.schemas import (
        ReasoningState,  # noqa: F401
        QueryAnalysis,  # noqa: F401
        EmotionalState,  # noqa: F401
        ToolDecisionType,  # noqa: F401
        ProblemCategory,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

__all__ = [
    "ReasoningEngine",
    "ReasoningConfig",
    "ReasoningState",
    "QueryAnalysis",
    "EmotionalState",
    "ToolDecisionType",
    "ProblemCategory",
]
