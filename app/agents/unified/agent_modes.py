"""Shared agent-mode normalization utilities.

Centralizes the hard-switch mode contract so AG-UI ingestion, coordinator
prompting, routing, and tool gating all use the same semantics.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class AgentMode(str, Enum):
    """Supported frontend-selectable agent modes."""

    GENERAL = "general"
    MAILBIRD_EXPERT = "mailbird_expert"
    RESEARCH_EXPERT = "research_expert"
    CREATIVE_EXPERT = "creative_expert"


DEFAULT_AGENT_MODE = AgentMode.GENERAL.value

# Backward compatibility map for legacy clients that only send `agent_type`.
LEGACY_AGENT_TYPE_TO_MODE: dict[str, str] = {
    "primary": AgentMode.GENERAL.value,
    "research": AgentMode.RESEARCH_EXPERT.value,
    "log_analysis": AgentMode.MAILBIRD_EXPERT.value,
    "router": AgentMode.GENERAL.value,
}

# User/input aliases normalized to canonical mode keys.
_MODE_ALIASES: dict[str, str] = {
    AgentMode.GENERAL.value: AgentMode.GENERAL.value,
    "general_assistant": AgentMode.GENERAL.value,
    "assistant": AgentMode.GENERAL.value,
    AgentMode.MAILBIRD_EXPERT.value: AgentMode.MAILBIRD_EXPERT.value,
    "mailbird": AgentMode.MAILBIRD_EXPERT.value,
    "support": AgentMode.MAILBIRD_EXPERT.value,
    AgentMode.RESEARCH_EXPERT.value: AgentMode.RESEARCH_EXPERT.value,
    "research": AgentMode.RESEARCH_EXPERT.value,
    AgentMode.CREATIVE_EXPERT.value: AgentMode.CREATIVE_EXPERT.value,
    "creative": AgentMode.CREATIVE_EXPERT.value,
}


def normalize_agent_mode(value: Any, default: str = DEFAULT_AGENT_MODE) -> str:
    """Normalize an arbitrary mode-like value into a canonical mode key."""
    if isinstance(value, AgentMode):
        return value.value
    if not isinstance(value, str):
        return default
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return _MODE_ALIASES.get(normalized, default)


def map_legacy_agent_type_to_mode(agent_type: Any) -> str | None:
    """Map legacy `agent_type` values to the modern `agent_mode` contract."""
    if not isinstance(agent_type, str):
        return None
    legacy_key = agent_type.strip().lower()
    if not legacy_key:
        return None
    return LEGACY_AGENT_TYPE_TO_MODE.get(legacy_key)


def resolve_agent_mode(
    explicit_mode: Any,
    *,
    legacy_agent_type: Any = None,
    default: str = DEFAULT_AGENT_MODE,
) -> str:
    """Resolve effective mode with explicit mode taking precedence."""
    normalized_mode = normalize_agent_mode(explicit_mode, default="")
    if normalized_mode:
        return normalized_mode
    mapped = map_legacy_agent_type_to_mode(legacy_agent_type)
    if mapped:
        return mapped
    return default


def mode_allows_log_analysis(mode: Any) -> bool:
    """Return whether tactical log-analysis overrides are allowed in a mode."""
    resolved = normalize_agent_mode(mode)
    return resolved in {
        AgentMode.GENERAL.value,
        AgentMode.MAILBIRD_EXPERT.value,
        AgentMode.RESEARCH_EXPERT.value,
    }

