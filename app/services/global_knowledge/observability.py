"""In-memory observability helpers for global knowledge pipelines."""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Deque, Dict, Iterable, Optional, Set

from pydantic import BaseModel, Field

from .models import sanitize_metadata


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


MAX_BUFFER_EVENTS = 500
MAX_STAGE_SAMPLES = 500


class TimelineEvent(BaseModel):
    """Serializable representation of a single observability event."""

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timeline_id: str
    kind: str
    stage: str
    status: str
    created_at: datetime = Field(default_factory=_utcnow)
    duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = None
    submission_id: Optional[int] = None
    fallback_used: Optional[bool] = None
    store_written: Optional[bool] = None


@dataclass
class TraceInfo:
    """Internal bookkeeping for timeline-level aggregation."""

    timeline_id: str
    kind: str
    user_id: Optional[str]
    created_at: datetime
    submission_id: Optional[int] = None
    last_event_at: datetime = field(default_factory=_utcnow)
    fallback_events: int = 0
    store_written: Optional[bool] = None
    completed: bool = False


_TRACE_REGISTRY: Dict[str, TraceInfo] = {}
_EVENT_BUFFER: Deque[TimelineEvent] = deque(maxlen=MAX_BUFFER_EVENTS)
_LISTENERS: Set[asyncio.Queue[TimelineEvent]] = set()
_STAGE_LATENCIES: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=MAX_STAGE_SAMPLES))
_LOCK = asyncio.Lock()


async def _broadcast(event: TimelineEvent) -> None:
    """Fan out the event to active listeners without blocking."""

    for queue in list(_LISTENERS):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop events for slow consumers to avoid back pressure.
            continue


def _store_event(event: TimelineEvent) -> None:
    _EVENT_BUFFER.append(event)
    if event.duration_ms is not None:
        _STAGE_LATENCIES[event.stage].append(event.duration_ms)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    loop.create_task(_broadcast(event))


async def subscribe_events(since: Optional[datetime] = None) -> AsyncGenerator[TimelineEvent, None]:
    """Yield timeline events via an async generator for SSE endpoints."""

    queue: asyncio.Queue[TimelineEvent] = asyncio.Queue(maxsize=200)
    async with _LOCK:
        snapshot = list(_EVENT_BUFFER)
        _LISTENERS.add(queue)

    try:
        for event in snapshot:
            if since is None or event.created_at >= since:
                await queue.put(event)

        while True:
            event = await queue.get()
            yield event
    finally:
        async with _LOCK:
            _LISTENERS.discard(queue)


def start_trace(*, kind: str, user_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
    """Initialise a new timeline and emit an initial `received` event."""

    timeline_id = uuid.uuid4().hex
    now = _utcnow()
    _TRACE_REGISTRY[timeline_id] = TraceInfo(
        timeline_id=timeline_id,
        kind=kind,
        user_id=user_id,
        created_at=now,
        last_event_at=now,
    )

    event = TimelineEvent(
        timeline_id=timeline_id,
        kind=kind,
        stage="received",
        status="in_progress",
        created_at=now,
        duration_ms=0.0,
        metadata=sanitize_metadata(metadata or {}),
        user_id=user_id,
    )
    _store_event(event)
    return timeline_id


def publish_stage(
    timeline_id: str,
    *,
    stage: str,
    status: str,
    kind: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    submission_id: Optional[int] = None,
    fallback_used: Optional[bool] = None,
    store_written: Optional[bool] = None,
    duration_override_ms: Optional[float] = None,
) -> TimelineEvent:
    """Record a stage transition and notify listeners."""

    now = _utcnow()
    trace = _TRACE_REGISTRY.get(timeline_id)
    if trace is None:
        trace = TraceInfo(
            timeline_id=timeline_id,
            kind=kind or "unknown",
            user_id=user_id,
            created_at=now,
            last_event_at=now,
        )
        _TRACE_REGISTRY[timeline_id] = trace

    if kind and trace.kind == "unknown":
        trace.kind = kind
    if user_id and not trace.user_id:
        trace.user_id = user_id

    if submission_id is not None:
        trace.submission_id = submission_id
    if store_written is not None:
        trace.store_written = store_written
    if fallback_used:
        trace.fallback_events += 1

    duration_ms = duration_override_ms
    if duration_ms is None and trace.last_event_at:
        duration_ms = (now - trace.last_event_at).total_seconds() * 1000.0

    trace.last_event_at = now

    if stage == "completed" and status == "complete":
        trace.completed = True

    event = TimelineEvent(
        timeline_id=timeline_id,
        kind=trace.kind,
        stage=stage,
        status=status,
        created_at=now,
        duration_ms=duration_ms,
        metadata=sanitize_metadata(metadata or {}),
        user_id=trace.user_id,
        submission_id=trace.submission_id,
        fallback_used=fallback_used,
        store_written=store_written,
    )

    _store_event(event)
    return event


def attach_submission_id(timeline_id: str, submission_id: int) -> None:
    trace = _TRACE_REGISTRY.get(timeline_id)
    if trace:
        trace.submission_id = submission_id
        publish_stage(
            timeline_id,
            stage="submission_linked",
            status="complete",
            submission_id=submission_id,
        )


def recent_events(limit: int = 200) -> Iterable[TimelineEvent]:
    buffer = list(_EVENT_BUFFER)
    return buffer[-limit:]


def _percentile(values: Iterable[float], percentile: float) -> Optional[float]:
    data = [value for value in values if value is not None]
    if not data:
        return None
    if len(data) == 1:
        return data[0]
    sorted_data = sorted(data)
    rank = (len(sorted_data) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(sorted_data) - 1)
    fraction = rank - lower
    return sorted_data[lower] + (sorted_data[upper] - sorted_data[lower]) * fraction


def compute_summary(window: timedelta) -> Dict[str, Any]:
    cutoff = _utcnow() - window
    events = [event for event in _EVENT_BUFFER if event.created_at >= cutoff]

    received = [event for event in events if event.stage == "received"]
    completed = [event for event in events if event.stage == "completed" and event.status == "complete"]
    failed = [event for event in events if event.stage == "completed" and event.status == "error"]
    store_events = [event for event in events if event.stage == "store_upserted"]
    fallback_events = [event for event in events if event.fallback_used]

    by_kind: Dict[str, int] = defaultdict(int)
    for event in received:
        by_kind[event.kind] += 1

    total_submissions = len(received)
    total_outcomes = len(completed) + len(failed)
    enhancer_success_rate = (
        len(completed) / total_outcomes if total_outcomes else None
    )

    store_success_candidates = [event for event in store_events if event.store_written is not None]
    store_success_rate = (
        sum(1 for event in store_success_candidates if event.store_written)
        / len(store_success_candidates)
        if store_success_candidates
        else None
    )

    fallback_rate = (
        len(fallback_events) / len(store_events)
        if store_events
        else (len(fallback_events) / total_submissions if total_submissions else None)
    )

    stage_p95: Dict[str, Optional[float]] = {}
    for stage, durations in _STAGE_LATENCIES.items():
        stage_p95[stage] = _percentile(durations, 0.95)

    return {
        "window_seconds": int(window.total_seconds()),
        "total_submissions": total_submissions,
        "by_kind": by_kind,
        "enhancer_success_rate": enhancer_success_rate,
        "store_write_success_rate": store_success_rate,
        "fallback_rate": fallback_rate,
        "stage_p95_ms": stage_p95,
    }


def reset_observability_state() -> None:
    """Testing helper to clear global state."""

    _TRACE_REGISTRY.clear()
    _EVENT_BUFFER.clear()
    _STAGE_LATENCIES.clear()
    for queue in list(_LISTENERS):
        try:
            queue.put_nowait(
                TimelineEvent(
                    timeline_id="reset",
                    kind="system",
                    stage="shutdown",
                    status="complete",
                )
            )
        except asyncio.QueueFull:
            continue
    _LISTENERS.clear()
