"""Persistence helpers for global knowledge submissions."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from app.core.settings import settings
from app.db.embedding_config import assert_dim
from app.db import embedding_utils
from app.db.supabase_client import SupabaseClient

from .enhancer import FeedbackEnhancer
from .models import (
    BaseSubmission,
    FeedbackSubmission,
    CorrectionSubmission,
    EnhancedPayload,
    PersistenceResult,
    sanitize_metadata,
)
from .store import upsert_enhanced_entry
from .observability import attach_submission_id, publish_stage, start_trace

logger = logging.getLogger(__name__)


async def persist_feedback(
    submission: FeedbackSubmission,
    *,
    supabase_client: Optional[SupabaseClient] = None,
    enhancer: Optional[FeedbackEnhancer] = None,
    embed_model: Optional[Any] = None,
    store: Any = None,
) -> PersistenceResult:
    """Persist a feedback submission to Supabase and optionally the LangGraph store."""

    timeline_id = start_trace(kind=submission.kind, user_id=submission.user_id)

    try:
        return await _persist_submission(
            submission,
            insert_callable=_insert_feedback,
            supabase_client=supabase_client,
            enhancer=enhancer,
            embed_model=embed_model,
            store=store,
            timeline_id=timeline_id,
        )
    except Exception as exc:
        publish_stage(
            timeline_id,
            stage="completed",
            status="error",
            kind=submission.kind,
            user_id=submission.user_id,
            metadata={"error": str(exc)},
        )
        raise


async def persist_correction(
    submission: CorrectionSubmission,
    *,
    supabase_client: Optional[SupabaseClient] = None,
    enhancer: Optional[FeedbackEnhancer] = None,
    embed_model: Optional[Any] = None,
    store: Any = None,
) -> PersistenceResult:
    """Persist a correction submission to Supabase and optionally the LangGraph store."""

    timeline_id = start_trace(kind=submission.kind, user_id=submission.user_id)

    try:
        return await _persist_submission(
            submission,
            insert_callable=_insert_correction,
            supabase_client=supabase_client,
            enhancer=enhancer,
            embed_model=embed_model,
            store=store,
            timeline_id=timeline_id,
        )
    except Exception as exc:
        publish_stage(
            timeline_id,
            stage="completed",
            status="error",
            kind=submission.kind,
            user_id=submission.user_id,
            metadata={"error": str(exc)},
        )
        raise


async def _persist_submission(
    submission: BaseSubmission,
    *,
    insert_callable: Callable[[SupabaseClient, EnhancedPayload, BaseSubmission, Optional[List[float]]], Optional[Dict[str, Any]]],
    supabase_client: Optional[SupabaseClient],
    enhancer: Optional[FeedbackEnhancer],
    embed_model: Optional[Any],
    store: Any,
    timeline_id: Optional[str],
) -> PersistenceResult:
    supabase_client = supabase_client or SupabaseClient()
    enhancer = enhancer or FeedbackEnhancer()

    timeline_id = timeline_id or start_trace(kind=submission.kind, user_id=getattr(submission, "user_id", None))

    publish_stage(
        timeline_id,
        stage="persistence_started",
        status="in_progress",
        kind=submission.kind,
        user_id=submission.user_id,
    )

    enhanced = await enhancer.enhance(submission, timeline_id=timeline_id)
    publish_stage(
        timeline_id,
        stage="enhanced_payload",
        status="complete",
        kind=submission.kind,
        user_id=submission.user_id,
        metadata={"tags": enhanced.tags},
    )
    embedding_vector: Optional[List[float]] = None
    should_try_store = settings.should_enable_store_writes() and settings.has_global_store_configuration()

    if should_try_store:
        embed_model = embed_model or embedding_utils.get_embedding_model()
        try:
            embedding_vector = embed_model.embed_query(enhanced.raw_text)
            assert_dim(embedding_vector, "global_knowledge_enhanced")
            publish_stage(
                timeline_id,
                stage="embedding_generated",
                status="complete",
                kind=submission.kind,
                user_id=submission.user_id,
            )
        except ValueError as err:
            logger.warning("Embedding dimension mismatch: %s", err)
            embedding_vector = None
            should_try_store = False
            publish_stage(
                timeline_id,
                stage="embedding_failed",
                status="error",
                kind=submission.kind,
                user_id=submission.user_id,
                metadata={"error": str(err)},
            )
        except Exception as exc:
            logger.warning("Failed to compute embedding for global knowledge submission: %s", exc)
            embedding_vector = None
            should_try_store = False
            publish_stage(
                timeline_id,
                stage="embedding_failed",
                status="error",
                kind=submission.kind,
                user_id=submission.user_id,
                metadata={"error": str(exc)},
            )

    supabase_error_stage_emitted = False
    try:
        supabase_row = await insert_callable(supabase_client, enhanced, submission, embedding_vector)
    except Exception as exc:
        logger.warning(
            "Failed to insert global knowledge submission (kind=%s user=%s): %s",
            submission.kind,
            submission.user_id,
            exc,
        )
        publish_stage(
            timeline_id,
            stage="supabase_persisted",
            status="error",
            kind=submission.kind,
            user_id=submission.user_id,
            metadata={"error": str(exc)},
        )
        supabase_row = None
        supabase_error_stage_emitted = True

    if isinstance(supabase_row, dict) and "id" in supabase_row:
        try:
            updated_metadata = {**enhanced.metadata, "source_id": int(supabase_row["id"])}
            enhanced = enhanced.model_copy(update={"metadata": updated_metadata})
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug("Failed to attach source id to enhanced payload metadata: %s", exc)
        attach_submission_id(timeline_id, int(supabase_row["id"]))
        publish_stage(
            timeline_id,
            stage="supabase_persisted",
            status="complete",
            kind=submission.kind,
            user_id=submission.user_id,
            submission_id=int(supabase_row["id"]),
        )
    else:
        if not supabase_error_stage_emitted:
            publish_stage(
                timeline_id,
                stage="supabase_persisted",
                status="error",
                kind=submission.kind,
                user_id=submission.user_id,
            )

    store_written = False
    if should_try_store and supabase_row and embedding_vector is not None:
        store_written = await upsert_enhanced_entry(enhanced, embedding_vector, store=store)
        publish_stage(
            timeline_id,
            stage="store_upserted",
            status="complete" if store_written else "error",
            kind=submission.kind,
            user_id=submission.user_id,
            store_written=store_written,
            fallback_used=not store_written,
        )
    else:
        publish_stage(
            timeline_id,
            stage="store_upserted",
            status="skipped",
            kind=submission.kind,
            user_id=submission.user_id,
            store_written=store_written,
            fallback_used=False,
        )

    publish_stage(
        timeline_id,
        stage="completed",
        status="complete" if supabase_row else "error",
        kind=submission.kind,
        user_id=submission.user_id,
        metadata={"store_written": store_written},
        store_written=store_written,
    )

    return PersistenceResult(
        supabase_row=supabase_row,
        enhanced=enhanced,
        store_written=store_written,
    )


async def _insert_feedback(
    client: SupabaseClient,
    enhanced: EnhancedPayload,
    submission: FeedbackSubmission,
    embedding_vector: Optional[List[float]],
) -> Optional[Dict[str, Any]]:
    metadata = _compose_metadata(submission.metadata, enhanced)

    row = await client.insert_sparrow_feedback(
        user_id=submission.user_id,
        feedback_text=submission.feedback_text,
        selected_text=submission.selected_text,
        attachments=submission.attachments_payload(),
        metadata=metadata,
        embedding=embedding_vector,
    )

    if row:
        logger.info("Persisted feedback submission (id=%s)", row.get("id"))
    else:
        logger.warning("Failed to persist feedback submission for user_id=%s", submission.user_id)
    return row


async def _insert_correction(
    client: SupabaseClient,
    enhanced: EnhancedPayload,
    submission: CorrectionSubmission,
    embedding_vector: Optional[List[float]],
) -> Optional[Dict[str, Any]]:
    metadata = _compose_metadata(submission.metadata, enhanced)

    row = await client.insert_sparrow_correction(
        user_id=submission.user_id,
        incorrect_text=submission.incorrect_text,
        corrected_text=submission.corrected_text,
        explanation=submission.explanation,
        attachments=submission.attachments_payload(),
        metadata=metadata,
        embedding=embedding_vector,
    )

    if row:
        logger.info("Persisted correction submission (id=%s)", row.get("id"))
    else:
        logger.warning("Failed to persist correction submission for user_id=%s", submission.user_id)
    return row


def _compose_metadata(base_metadata: Dict[str, Any], enhanced: EnhancedPayload) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {**(base_metadata or {})}
    metadata.setdefault("source", enhanced.kind)
    metadata["enhanced"] = enhanced.model_dump()
    metadata.setdefault("tags", enhanced.tags)
    return sanitize_metadata(metadata)
