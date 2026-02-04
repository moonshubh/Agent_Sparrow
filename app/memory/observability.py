"""
Lightweight observability helpers for the memory layer.

Tracks basic counters/histograms in-process so tests can validate behaviour
while still emitting structured debugging logs that downstream telemetry
pipelines can scrape.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List

from app.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalStats:
    """Aggregated retrieval statistics for a given operation."""

    calls: int = 0
    hits: int = 0
    errors: int = 0
    total_results: int = 0
    latency_ms: List[float] = field(default_factory=list)


@dataclass
class WriteStats:
    """Aggregated write statistics for a given operation."""

    calls: int = 0
    success: int = 0
    errors: int = 0
    latency_ms: List[float] = field(default_factory=list)


@dataclass
class MemorySnapshot:
    """Snapshot of current in-memory metrics."""

    retrieval: Dict[str, RetrievalStats]
    writes: Dict[str, WriteStats]


class MemoryMetrics:
    """Thread-safe metrics collector for memory operations."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._retrieval: Dict[str, RetrievalStats] = defaultdict(RetrievalStats)
        self._writes: Dict[str, WriteStats] = defaultdict(WriteStats)

    def reset(self) -> None:
        """Clear all accumulated stats."""
        with self._lock:
            self._retrieval = defaultdict(RetrievalStats)
            self._writes = defaultdict(WriteStats)

    def snapshot(self) -> MemorySnapshot:
        """Return a deep copy of the current metrics."""
        with self._lock:
            retrieval = deepcopy(dict(self._retrieval))
            writes = deepcopy(dict(self._writes))
        return MemorySnapshot(retrieval=retrieval, writes=writes)

    def record_retrieval(
        self,
        operation: str,
        *,
        hit: bool,
        duration_ms: float,
        result_count: int = 0,
        error: bool = False,
    ) -> None:
        """Record a retrieval attempt for the supplied operation name."""
        with self._lock:
            stats = self._retrieval[operation]
            stats.calls += 1
            if hit:
                stats.hits += 1
            if error:
                stats.errors += 1
            stats.total_results += max(0, result_count)
            stats.latency_ms.append(duration_ms)

        logger.debug(
            "memory_metrics_retrieval",
            operation=operation,
            hit=hit,
            error=error,
            duration_ms=duration_ms,
            result_count=result_count,
        )

    def record_write(
        self,
        operation: str,
        *,
        success: bool,
        duration_ms: float,
        error: bool = False,
    ) -> None:
        """Record a write attempt for the supplied operation name."""
        with self._lock:
            stats = self._writes[operation]
            stats.calls += 1
            if success:
                stats.success += 1
            if error:
                stats.errors += 1
            stats.latency_ms.append(duration_ms)

        logger.debug(
            "memory_metrics_write",
            operation=operation,
            success=success,
            error=error,
            duration_ms=duration_ms,
        )


memory_metrics = MemoryMetrics()

__all__ = [
    "MemoryMetrics",
    "MemorySnapshot",
    "RetrievalStats",
    "WriteStats",
    "memory_metrics",
]
