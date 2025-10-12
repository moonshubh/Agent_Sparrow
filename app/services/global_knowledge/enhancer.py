"""Enhancer that produces enriched payloads for global knowledge submissions."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, cast

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from .models import (
    BaseSubmission,
    CorrectionSubmission,
    EnhancedPayload,
    FeedbackSubmission,
)
from .observability import publish_stage

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_SUMMARY_MAX_CHARS = 120
_KEY_FACT_LIMIT = 5
_KEY_FACT_MAX_LEN = 180


class EnhancerState(BaseModel):
    """Graph state used by the enhancer subgraph."""

    submission: BaseSubmission
    payload: Optional[EnhancedPayload] = None
    errors: List[str] = Field(default_factory=list)
    classification: Optional[str] = None
    timeline_id: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _split_sentences(text: str) -> List[str]:
    sentences: List[str] = []
    for chunk in _SENTENCE_SPLIT_RE.split(text):
        candidate = chunk.strip()
        if candidate:
            sentences.append(candidate)
    if not sentences and text.strip():
        sentences.append(text.strip())
    return sentences


def _derive_summary(text: str) -> str:
    normalized = _normalize_whitespace(text)
    sentences = _split_sentences(normalized)
    if not sentences:
        return normalized[:_SUMMARY_MAX_CHARS]
    summary = sentences[0]
    if len(summary) > _SUMMARY_MAX_CHARS:
        summary = summary[: _SUMMARY_MAX_CHARS - 1].rstrip() + "…"
    return summary


def _extract_key_facts(text: str) -> List[str]:
    sentences = _split_sentences(_normalize_whitespace(text))
    key_facts: List[str] = []
    for sentence in sentences:
        truncated = sentence[:_KEY_FACT_MAX_LEN].rstrip()
        key_facts.append(truncated)
        if len(key_facts) >= _KEY_FACT_LIMIT:
            break
    return key_facts


async def _build_feedback_payload(submission: FeedbackSubmission) -> EnhancedPayload:
    feedback_text = _normalize_whitespace(submission.feedback_text)
    selected_text = (
        _normalize_whitespace(submission.selected_text)
        if submission.selected_text
        else None
    )

    raw_segments = [feedback_text]
    metadata: Dict[str, Any] = {"kind": submission.kind, "source": submission.kind}

    if selected_text:
        metadata["selected_text"] = selected_text
        raw_segments.append(f"Selected: {selected_text}")

    merge_metadata(metadata, submission.metadata)

    raw_text = "\n".join(segment for segment in raw_segments if segment)
    summary = _derive_summary(feedback_text)
    key_facts = _extract_key_facts(raw_text)

    tags = {submission.kind}
    if submission.attachments:
        tags.add("has_attachments")
    if selected_text:
        tags.add("has_selection")

    return EnhancedPayload(
        kind=submission.kind,
        summary=summary,
        key_facts=key_facts,
        normalized_pair=None,
        tags=sorted(tags),
        raw_text=raw_text,
        attachments=list(submission.attachments),
        metadata=metadata,
    )


async def _build_correction_payload(submission: CorrectionSubmission) -> EnhancedPayload:
    incorrect = _normalize_whitespace(submission.incorrect_text)
    corrected = _normalize_whitespace(submission.corrected_text)
    explanation = (
        _normalize_whitespace(submission.explanation)
        if submission.explanation
        else None
    )

    raw_segments = [f"Incorrect: {incorrect}", f"Corrected: {corrected}"]
    metadata: Dict[str, Any] = {"kind": submission.kind, "source": submission.kind}

    if explanation:
        metadata["explanation"] = explanation
        raw_segments.append(f"Explanation: {explanation}")

    merge_metadata(metadata, submission.metadata)

    raw_text = "\n".join(segment for segment in raw_segments if segment)
    summary = _derive_summary(corrected)
    key_facts = _extract_key_facts(raw_text)
    normalized_pair = {"incorrect": incorrect, "corrected": corrected}

    tags = {submission.kind}
    if submission.attachments:
        tags.add("has_attachments")
    if explanation:
        tags.add("has_explanation")

    return EnhancedPayload(
        kind=submission.kind,
        summary=summary,
        key_facts=key_facts,
        normalized_pair=normalized_pair,
        tags=sorted(tags),
        raw_text=raw_text,
        attachments=list(submission.attachments),
        metadata=metadata,
    )


def merge_metadata(target: Dict[str, Any], additional: Dict[str, Any]) -> None:
    """Merge additional metadata into the base dictionary without overwriting keys."""

    for key, value in (additional or {}).items():
        if key not in target:
            target[key] = value
        else:
            logger.debug("Metadata key '%s' already present; preserving base value", key)


async def _classify_submission(state: EnhancerState) -> Dict[str, Any]:
    submission = state.submission
    if isinstance(submission, FeedbackSubmission):
        if state.timeline_id:
            publish_stage(
                state.timeline_id,
                stage="classified",
                status="complete",
                kind=submission.kind,
                user_id=submission.user_id,
                metadata={"classification": "feedback"},
            )
        return {"classification": "feedback"}
    if isinstance(submission, CorrectionSubmission):
        if state.timeline_id:
            publish_stage(
                state.timeline_id,
                stage="classified",
                status="complete",
                kind=submission.kind,
                user_id=submission.user_id,
                metadata={"classification": "correction"},
            )
        return {"classification": "correction"}
    error = f"unsupported_submission:{submission.__class__.__name__}"
    if state.timeline_id:
        publish_stage(
            state.timeline_id,
            stage="classified",
            status="error",
            kind=submission.kind if hasattr(submission, "kind") else "unknown",
            user_id=submission.user_id if hasattr(submission, "user_id") else None,
            metadata={"error": error},
        )
    return {
        "classification": "unsupported",
        "errors": [*state.errors, error],
    }


def _route_after_classification(state: EnhancerState) -> str:
    classification = state.classification or "unsupported"
    if classification == "feedback":
        return "feedback"
    if classification == "correction":
        return "correction"
    return "unsupported"


async def _normalize_feedback_node(state: EnhancerState) -> Dict[str, Any]:
    submission = cast(FeedbackSubmission, state.submission)
    payload = await _build_feedback_payload(submission)
    if state.timeline_id:
        publish_stage(
            state.timeline_id,
            stage="normalized_feedback",
            status="complete",
            kind=submission.kind,
            user_id=submission.user_id,
            metadata={"tags": payload.tags},
        )
    return {"payload": payload}


async def _normalize_correction_node(state: EnhancerState) -> Dict[str, Any]:
    submission = cast(CorrectionSubmission, state.submission)
    payload = await _build_correction_payload(submission)
    if state.timeline_id:
        publish_stage(
            state.timeline_id,
            stage="normalized_correction",
            status="complete",
            kind=submission.kind,
            user_id=submission.user_id,
            metadata={"tags": payload.tags},
        )
    return {"payload": payload}


async def _moderate_payload(state: EnhancerState) -> Dict[str, Any]:
    if state.payload is None:
        return {}
    # Placeholder moderation hook; emits status for downstream metrics.
    metadata = dict(state.payload.metadata)
    metadata.setdefault("moderation", {"status": "skipped"})
    updated = state.payload.model_copy(update={"metadata": metadata})
    if state.timeline_id:
        publish_stage(
            state.timeline_id,
            stage="moderated",
            status="complete",
            kind=state.submission.kind,
            user_id=state.submission.user_id,
        )
    return {"payload": updated}


async def _handle_unsupported(state: EnhancerState) -> Dict[str, Any]:
    if state.timeline_id:
        publish_stage(
            state.timeline_id,
            stage="unsupported",
            status="error",
            kind=state.submission.kind if hasattr(state.submission, "kind") else "unknown",
            user_id=state.submission.user_id if hasattr(state.submission, "user_id") else None,
        )
    return {"errors": state.errors or ["unsupported_submission"]}


async def _finalize_payload(state: EnhancerState) -> Dict[str, Any]:
    if state.payload is None:
        if state.timeline_id:
            publish_stage(
                state.timeline_id,
                stage="finalized",
                status="error",
                kind=state.submission.kind if hasattr(state.submission, "kind") else "unknown",
                user_id=state.submission.user_id if hasattr(state.submission, "user_id") else None,
            )
        return {"errors": [*state.errors, "missing_payload"]}
    if state.timeline_id:
        publish_stage(
            state.timeline_id,
            stage="finalized",
            status="complete",
            kind=state.submission.kind,
            user_id=state.submission.user_id,
        )
    return {}


def build_enhancer_graph() -> Any:
    """Return a compiled LangGraph enhancer pipeline."""

    workflow = StateGraph(EnhancerState)
    workflow.add_node("classify", _classify_submission)
    workflow.add_node("normalize_feedback", _normalize_feedback_node)
    workflow.add_node("normalize_correction", _normalize_correction_node)
    workflow.add_node("moderate", _moderate_payload)
    workflow.add_node("unsupported", _handle_unsupported)
    workflow.add_node("finalize", _finalize_payload)

    workflow.set_entry_point("classify")
    workflow.add_conditional_edges(
        "classify",
        _route_after_classification,
        {
            "feedback": "normalize_feedback",
            "correction": "normalize_correction",
            "unsupported": "unsupported",
        },
    )

    workflow.add_edge("normalize_feedback", "moderate")
    workflow.add_edge("normalize_correction", "moderate")
    workflow.add_edge("moderate", "finalize")
    workflow.add_edge("unsupported", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile(checkpointer=MemorySaver())


_GRAPH_CACHE: Optional[Any] = None


def _get_enhancer_graph() -> Any:
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        _GRAPH_CACHE = build_enhancer_graph()
    return _GRAPH_CACHE


class FeedbackEnhancer:
    """Normalize slash command submissions into enriched payloads via LangGraph."""

    def __init__(self) -> None:
        self._graph = _get_enhancer_graph()

    async def enhance(self, submission: BaseSubmission, *, timeline_id: Optional[str] = None) -> EnhancedPayload:
        thread_id = f"enhancer-{uuid.uuid4()}"
        checkpointer = getattr(self._graph, "checkpointer", None)
        try:
            if timeline_id:
                publish_stage(
                    timeline_id,
                    stage="enhancer_started",
                    status="in_progress",
                    kind=submission.kind if hasattr(submission, "kind") else "unknown",
                    user_id=submission.user_id if hasattr(submission, "user_id") else None,
                )
            state = EnhancerState(submission=submission, timeline_id=timeline_id)
            result = await self._graph.ainvoke(
                state,
                config={"configurable": {"thread_id": thread_id}},
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Enhancer graph failed (%s); using fallback path", exc)
            if timeline_id:
                publish_stage(
                    timeline_id,
                    stage="enhancer_failed",
                    status="error",
                    kind=submission.kind if hasattr(submission, "kind") else "unknown",
                    user_id=submission.user_id if hasattr(submission, "user_id") else None,
                    metadata={"error": str(exc)},
                )
            return await self._fallback(submission, timeline_id=timeline_id)
        finally:
            if checkpointer and hasattr(checkpointer, "delete_thread"):
                try:
                    checkpointer.delete_thread(thread_id)
                except Exception:  # pragma: no cover - best-effort cleanup
                    logger.debug("Failed to delete enhancer checkpoint thread", exc_info=True)

        if isinstance(result, EnhancerState):
            classification = result.classification
            payload = result.payload
            errors = result.errors
        elif isinstance(result, dict):
            classification = result.get("classification")
            payload = result.get("payload")
            errors = result.get("errors") or []
        else:
            classification = None
            payload = None
            errors = []

        if payload is not None:
            if timeline_id:
                publish_stage(
                    timeline_id,
                    stage="enhancer_completed",
                    status="complete",
                    kind=submission.kind if hasattr(submission, "kind") else "unknown",
                    user_id=submission.user_id if hasattr(submission, "user_id") else None,
                    metadata={"tags": getattr(payload, "tags", [])},
                )
            return payload

        if classification == "unsupported" or isinstance(submission, BaseSubmission) and not isinstance(
            submission, (FeedbackSubmission, CorrectionSubmission)
        ):
            if timeline_id:
                publish_stage(
                    timeline_id,
                    stage="enhancer_completed",
                    status="error",
                    kind=submission.kind if hasattr(submission, "kind") else "unknown",
                    user_id=submission.user_id if hasattr(submission, "user_id") else None,
                    metadata={"errors": errors},
                )
            raise TypeError(f"Unsupported submission type: {type(submission)!r}")

        if timeline_id:
            publish_stage(
                timeline_id,
                stage="enhancer_completed",
                status="error",
                kind=submission.kind if hasattr(submission, "kind") else "unknown",
                user_id=submission.user_id if hasattr(submission, "user_id") else None,
                metadata={"errors": errors},
            )
        raise ValueError(
            "Enhancer graph did not produce payload",
            errors,
        )

    async def _fallback(self, submission: BaseSubmission, *, timeline_id: Optional[str] = None) -> EnhancedPayload:
        if timeline_id:
            publish_stage(
                timeline_id,
                stage="enhancer_fallback",
                status="in_progress",
                kind=submission.kind if hasattr(submission, "kind") else "unknown",
                user_id=submission.user_id if hasattr(submission, "user_id") else None,
            )
        if isinstance(submission, FeedbackSubmission):
            payload = await _build_feedback_payload(submission)
            if timeline_id:
                publish_stage(
                    timeline_id,
                    stage="enhancer_completed",
                    status="complete",
                    kind=submission.kind,
                    user_id=submission.user_id,
                    metadata={"tags": payload.tags, "path": "fallback"},
                )
            return payload
        if isinstance(submission, CorrectionSubmission):
            payload = await _build_correction_payload(submission)
            if timeline_id:
                publish_stage(
                    timeline_id,
                    stage="enhancer_completed",
                    status="complete",
                    kind=submission.kind,
                    user_id=submission.user_id,
                    metadata={"tags": payload.tags, "path": "fallback"},
                )
            return payload
        raise TypeError(f"Unsupported submission type: {type(submission)!r}")
