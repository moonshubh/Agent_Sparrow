"""Shared statistics dataclasses for middleware observability.

All middleware stats follow this pattern:
- Dataclass with sensible defaults
- to_dict() method for scratchpad/LangSmith storage
- Field names consistent across all stats classes

These dataclasses are extracted from individual middleware files to:
1. Eliminate duplication (~80 lines)
2. Provide consistent to_dict() implementation
3. Enable type checking across middleware boundaries
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class MemoryStats:
    """Statistics from memory operations.

    Tracks both retrieval (before agent) and write (after agent) operations.
    Used by SparrowMemoryMiddleware for observability.
    """

    retrieval_attempted: bool = False
    retrieval_success: bool = False
    facts_retrieved: int = 0
    relevance_scores: List[float] = field(default_factory=list)
    retrieval_error: Optional[str] = None

    write_attempted: bool = False
    write_success: bool = False
    facts_written: int = 0
    write_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for scratchpad storage and LangSmith metadata."""
        return asdict(self)


@dataclass
class RateLimitStats:
    """Statistics from rate limiting operations.

    Tracks model availability checks, fallback usage, and slot reservations.
    Used by SparrowRateLimitMiddleware for quota monitoring.
    """

    primary_model: str = ""
    fallback_used: bool = False
    fallback_model: Optional[str] = None
    fallback_reason: Optional[str] = None
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    slot_reserved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for observability."""
        return asdict(self)


@dataclass
class EvictionStats:
    """Statistics from eviction operations.

    Tracks tool result eviction to prevent context overflow.
    Used by ToolResultEvictionMiddleware for monitoring large outputs.
    """

    total_tool_results: int = 0
    results_evicted: int = 0
    total_chars_evicted: int = 0
    evicted_paths: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for observability."""
        return asdict(self)


@dataclass
class StateTrackingStats:
    """Statistics for state tracking middleware.

    Tracks agent loop state transitions for observability.
    Used by StateTrackingMiddleware for execution monitoring.
    """

    transitions_tracked: int = 0
    model_calls_tracked: int = 0
    tool_calls_tracked: int = 0
    completions: int = 0
    errors: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return asdict(self)
