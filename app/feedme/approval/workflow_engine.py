"""
FeedMe v3.0 Approval Workflow Engine - Supabase Only

Core workflow orchestration engine that manages the approval process for AI-extracted
content, including state transitions, reviewer assignment, and business logic.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Dict, Optional, Union

from .schemas import (
    TempExampleCreate,
    ApprovalDecision,
    BulkApprovalRequest,
    BulkApprovalResponse,
    WorkflowMetrics,
    ReviewerWorkloadSummary,
    ReviewerWorkload,
    WorkflowConfig,
    ApprovalState,
    ApprovalAction,
)
from .state_machine import ApprovalStateMachine, StateTransitionError
from ..embeddings.embedding_pipeline import FeedMeEmbeddingPipeline
from app.db.supabase.client import get_supabase_client

logger = logging.getLogger(__name__)


_TEMP_EXAMPLES_TABLE = "feedme_temp_examples"
_REVIEW_HISTORY_TABLE = "feedme_review_history"


class WorkflowTransition:
    """Represents a workflow state transition with metadata"""

    def __init__(
        self,
        from_state: ApprovalState,
        to_state: ApprovalState,
        action: ApprovalAction,
        timestamp: datetime,
        reviewer_id: str,
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.action = action
        self.timestamp = timestamp
        self.reviewer_id = reviewer_id


class ApprovalWorkflowEngine:
    """
    Core workflow engine for managing approval processes.

    This engine orchestrates the entire approval workflow including:
    - Creating and processing temp examples
    - Managing state transitions
    - Assigning reviewers
    - Processing approval decisions
    - Bulk operations
    - Analytics and metrics
    """

    def __init__(
        self, embedding_service: FeedMeEmbeddingPipeline, config: WorkflowConfig
    ):
        """Initialize the workflow engine."""
        self._supabase_client = None
        self.embedding_service = embedding_service
        self.config = config
        self.state_machine = ApprovalStateMachine()

        # Performance tracking
        self._metrics_cache: Dict[str, Any] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)

    @property
    def supabase_client(self):
        """Lazy load Supabase client"""
        if self._supabase_client is None:
            self._supabase_client = get_supabase_client()
        return self._supabase_client

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _normalize_temp_example(self, row: Dict[str, Any]) -> Dict[str, Any]:
        if not row:
            return {}

        normalized = dict(row)
        if not normalized.get("extraction_timestamp"):
            normalized["extraction_timestamp"] = (
                normalized.get("created_at") or self._now().isoformat()
            )

        if normalized.get("extraction_confidence") is None:
            normalized["extraction_confidence"] = (
                normalized.get("confidence_score") or 0.0
            )

        if not normalized.get("ai_model_used"):
            normalized["ai_model_used"] = "unknown"

        if not normalized.get("extraction_method"):
            normalized["extraction_method"] = "ai"

        if normalized.get("approval_status") is None:
            normalized["approval_status"] = ApprovalState.PENDING.value

        if normalized.get("priority") is None:
            normalized["priority"] = "normal"

        if normalized.get("auto_approved") is None:
            normalized["auto_approved"] = False

        if "tags" not in normalized or normalized.get("tags") is None:
            normalized["tags"] = []

        if "metadata" not in normalized or normalized.get("metadata") is None:
            normalized["metadata"] = {}

        if not normalized.get("created_at"):
            normalized["created_at"] = self._now().isoformat()

        if not normalized.get("updated_at"):
            normalized["updated_at"] = normalized.get("created_at")

        return normalized

    async def _exec(self, fn):
        return await self.supabase_client._exec(fn)

    async def create_temp_example(
        self, temp_example: TempExampleCreate
    ) -> Dict[str, Any]:
        """Create a new temp example with automatic approval logic."""
        try:
            # Generate embeddings for the Q&A content
            embeddings = await self._generate_embeddings(temp_example)

            auto_approved = bool(
                temp_example.extraction_confidence
                and temp_example.extraction_confidence
                >= self.config.auto_approval_threshold
            )
            approval_status = (
                ApprovalState.APPROVED.value
                if auto_approved
                else ApprovalState.PENDING.value
            )

            example_data: Dict[str, Any] = {
                "conversation_id": temp_example.conversation_id,
                "question_text": temp_example.question_text,
                "answer_text": temp_example.answer_text,
                "context_before": temp_example.context_before,
                "context_after": temp_example.context_after,
                "question_embedding": embeddings.get("question_embedding"),
                "answer_embedding": embeddings.get("answer_embedding"),
                "combined_embedding": embeddings.get("combined_embedding"),
                "extraction_method": temp_example.extraction_method,
                "extraction_confidence": temp_example.extraction_confidence,
                "ai_model_used": temp_example.ai_model_used,
                "extraction_timestamp": self._now().isoformat(),
                "approval_status": approval_status,
                "auto_approved": auto_approved,
                "auto_approval_reason": (
                    "confidence_threshold" if auto_approved else None
                ),
            }

            response = await self._exec(
                lambda: self.supabase_client.table(_TEMP_EXAMPLES_TABLE)
                .insert(example_data)
                .execute()
            )

            if not response.data:
                raise RuntimeError("Supabase insert returned no data")

            return self._normalize_temp_example(response.data[0])

        except Exception as e:
            logger.error(f"Failed to create temp example: {e}")
            raise

    async def _generate_embeddings(
        self, temp_example: Union[TempExampleCreate, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate embeddings for Q&A content."""
        if isinstance(temp_example, dict):
            payload = {
                "question_text": temp_example.get("question_text", ""),
                "answer_text": temp_example.get("answer_text", ""),
                "context_before": temp_example.get("context_before"),
                "context_after": temp_example.get("context_after"),
            }
        else:
            payload = {
                "question_text": temp_example.question_text,
                "answer_text": temp_example.answer_text,
                "context_before": temp_example.context_before,
                "context_after": temp_example.context_after,
            }

        embedded = await self.embedding_service.generate_embeddings([payload])
        if embedded:
            return embedded[0]
        return {}

    async def get_temp_example(self, temp_example_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a temp example by ID."""
        response = await self._exec(
            lambda: self.supabase_client.table(_TEMP_EXAMPLES_TABLE)
            .select("*")
            .eq("id", temp_example_id)
            .execute()
        )

        if not response.data:
            return None

        return self._normalize_temp_example(response.data[0])

    async def list_temp_examples(
        self,
        *,
        filters: Dict[str, Any],
        page: int,
        page_size: int,
    ) -> Dict[str, Any]:
        """List temp examples with filtering and pagination."""
        query = self.supabase_client.table(_TEMP_EXAMPLES_TABLE).select(
            "*", count="exact"
        )

        approval_status = filters.get("approval_status")
        if approval_status:
            query = query.eq("approval_status", approval_status)

        assigned_reviewer = filters.get("assigned_reviewer")
        if assigned_reviewer:
            query = query.eq("assigned_reviewer", assigned_reviewer)

        priority = filters.get("priority")
        if priority:
            query = query.eq("priority", priority)

        min_confidence = filters.get("min_confidence")
        if min_confidence is not None:
            query = query.gte("extraction_confidence", min_confidence)

        offset = max(0, (page - 1) * page_size)
        query = query.order("created_at", desc=True).range(
            offset, offset + page_size - 1
        )

        response = await self._exec(lambda: query.execute())
        items = [self._normalize_temp_example(row) for row in (response.data or [])]

        total = response.count if response.count is not None else len(items)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def update_temp_example(
        self, temp_example_id: int, update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a temp example by ID."""
        payload = dict(update_data)
        if "approval_status" in payload and isinstance(
            payload["approval_status"], ApprovalState
        ):
            payload["approval_status"] = payload["approval_status"].value
        if "priority" in payload and hasattr(payload["priority"], "value"):
            payload["priority"] = payload["priority"].value
        payload["updated_at"] = self._now().isoformat()

        response = await self._exec(
            lambda: self.supabase_client.table(_TEMP_EXAMPLES_TABLE)
            .update(payload)
            .eq("id", temp_example_id)
            .execute()
        )

        if not response.data:
            raise ValueError("Temp example not found")

        return self._normalize_temp_example(response.data[0])

    async def assign_reviewer(self, temp_example_id: int, reviewer_id: str) -> str:
        """Assign a reviewer to a temp example."""
        payload = {
            "assigned_reviewer": reviewer_id,
            "updated_at": self._now().isoformat(),
        }
        response = await self._exec(
            lambda: self.supabase_client.table(_TEMP_EXAMPLES_TABLE)
            .update(payload)
            .eq("id", temp_example_id)
            .execute()
        )
        if not response.data:
            raise ValueError("Temp example not found")
        return reviewer_id

    async def process_approval_decision(
        self, temp_example_id: int, decision: ApprovalDecision
    ) -> Dict[str, Any]:
        """Process approval decision for a temp example."""
        current = await self.get_temp_example(temp_example_id)
        if not current:
            raise ValueError("Temp example not found")

        current_state = ApprovalState(
            current.get("approval_status", ApprovalState.PENDING.value)
        )

        if not self.state_machine.can_transition(current_state, decision.action):
            raise StateTransitionError(
                f"Cannot transition from {current_state} with action {decision.action}"
            )

        new_state = self.state_machine.transition(current_state, decision.action)
        approval_status = new_state.value

        update_payload: Dict[str, Any] = {
            "approval_status": approval_status,
            "reviewer_id": decision.reviewer_id,
            "assigned_reviewer": decision.reviewer_id,
            "reviewed_at": self._now().isoformat(),
            "review_notes": decision.review_notes,
            "rejection_reason": decision.rejection_reason,
            "revision_instructions": decision.revision_instructions,
            "reviewer_confidence_score": decision.reviewer_confidence_score,
            "reviewer_usefulness_score": decision.reviewer_usefulness_score,
            "auto_approved": False,
            "auto_approval_reason": None,
            "updated_at": self._now().isoformat(),
        }

        response = await self._exec(
            lambda: self.supabase_client.table(_TEMP_EXAMPLES_TABLE)
            .update(update_payload)
            .eq("id", temp_example_id)
            .execute()
        )

        if response.data:
            updated_row = response.data[0]
        else:
            raise RuntimeError("Failed to update temp example")

        # Record review history (best-effort)
        try:
            action_map = {
                ApprovalAction.APPROVE: "approved",
                ApprovalAction.REJECT: "rejected",
                ApprovalAction.REQUEST_REVISION: "revision_requested",
            }
            history_payload = {
                "temp_example_id": temp_example_id,
                "reviewer_id": decision.reviewer_id,
                "action": action_map.get(decision.action, decision.action.value),
                "review_notes": decision.review_notes,
                "confidence_assessment": decision.confidence_assessment,
                "time_spent_minutes": decision.time_spent_minutes,
                "previous_status": current_state.value,
                "new_status": approval_status,
                "changes_made": {
                    "approval_status": approval_status,
                    "review_notes": decision.review_notes,
                },
            }
            await self._exec(
                lambda: self.supabase_client.table(_REVIEW_HISTORY_TABLE)
                .insert(history_payload)
                .execute()
            )
        except Exception as exc:
            logger.warning("Failed to record review history: %s", exc)

        return self._normalize_temp_example(updated_row)

    async def bulk_approve_examples(
        self, request: BulkApprovalRequest
    ) -> BulkApprovalResponse:
        """Process bulk approval of multiple examples."""
        start_time = time.perf_counter()
        failures: list[dict[str, Any]] = []
        successful = 0

        for temp_example_id in request.temp_example_ids:
            try:
                decision = ApprovalDecision(
                    temp_example_id=temp_example_id,
                    action=request.action,
                    reviewer_id=request.reviewer_id,
                    review_notes=request.review_notes,
                    confidence_assessment=None,
                    time_spent_minutes=None,
                    rejection_reason=request.rejection_reason,
                    revision_instructions=request.revision_instructions,
                    reviewer_confidence_score=None,
                    reviewer_usefulness_score=None,
                )
                await self.process_approval_decision(temp_example_id, decision)
                successful += 1
            except Exception as exc:
                failures.append({"temp_example_id": temp_example_id, "error": str(exc)})

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return BulkApprovalResponse(
            processed_count=len(request.temp_example_ids),
            successful_count=successful,
            failed_count=len(failures),
            failures=failures,
            processing_time_ms=elapsed_ms,
        )

    async def process_bulk_approval(
        self, request: BulkApprovalRequest
    ) -> BulkApprovalResponse:
        """Compatibility wrapper for bulk approval."""
        return await self.bulk_approve_examples(request)

    async def get_workflow_metrics(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> WorkflowMetrics:
        """Get workflow performance metrics."""
        now = self._now()
        period_start = start_date or (now - timedelta(days=30))
        period_end = end_date or now

        query = (
            self.supabase_client.table(_TEMP_EXAMPLES_TABLE)
            .select(
                "approval_status, auto_approved, extraction_confidence, reviewed_at, created_at, reviewer_id, assigned_reviewer",
                count="exact",
            )
            .gte("created_at", period_start.isoformat())
            .lte("created_at", period_end.isoformat())
        )

        response = await self._exec(lambda: query.execute())
        rows = response.data or []

        total_pending = sum(
            1
            for row in rows
            if row.get("approval_status") == ApprovalState.PENDING.value
        )
        total_approved = sum(
            1
            for row in rows
            if row.get("approval_status") == ApprovalState.APPROVED.value
        )
        total_rejected = sum(
            1
            for row in rows
            if row.get("approval_status") == ApprovalState.REJECTED.value
        )
        total_revision_requested = sum(
            1
            for row in rows
            if row.get("approval_status") == ApprovalState.REVISION_REQUESTED.value
        )
        total_auto_approved = sum(1 for row in rows if row.get("auto_approved") is True)

        total = len(rows) if rows else 0
        approval_rate = (total_approved / total) if total else 0.0
        rejection_rate = (total_rejected / total) if total else 0.0
        auto_approval_rate = (total_auto_approved / total) if total else 0.0

        durations: list[float] = []
        extraction_confidences: list[float] = []
        reviewer_efficiency: Dict[str, int] = {}

        for row in rows:
            extraction_conf = row.get("extraction_confidence")
            if extraction_conf is not None:
                try:
                    extraction_confidences.append(float(extraction_conf))
                except (TypeError, ValueError):
                    pass

            reviewed_at = row.get("reviewed_at")
            created_at = row.get("created_at")
            if reviewed_at and created_at:
                try:
                    reviewed_dt = datetime.fromisoformat(str(reviewed_at))
                    created_dt = datetime.fromisoformat(str(created_at))
                    durations.append(
                        (reviewed_dt - created_dt).total_seconds() / 3600.0
                    )
                except ValueError:
                    pass

            reviewer_id = row.get("reviewer_id") or row.get("assigned_reviewer")
            if reviewer_id and row.get("approval_status") in {
                ApprovalState.APPROVED.value,
                ApprovalState.REJECTED.value,
                ApprovalState.REVISION_REQUESTED.value,
            }:
                reviewer_efficiency[reviewer_id] = (
                    reviewer_efficiency.get(reviewer_id, 0) + 1
                )

        avg_review_time = (sum(durations) / len(durations)) if durations else None
        median_review_time = median(durations) if durations else None
        avg_extraction_confidence = (
            sum(extraction_confidences) / len(extraction_confidences)
            if extraction_confidences
            else None
        )

        return WorkflowMetrics(
            total_pending=total_pending,
            total_approved=total_approved,
            total_rejected=total_rejected,
            total_revision_requested=total_revision_requested,
            total_auto_approved=total_auto_approved,
            approval_rate=approval_rate,
            rejection_rate=rejection_rate,
            auto_approval_rate=auto_approval_rate,
            avg_review_time_hours=avg_review_time,
            median_review_time_hours=median_review_time,
            avg_extraction_confidence=avg_extraction_confidence,
            avg_reviewer_confidence=None,
            reviewer_efficiency=reviewer_efficiency,
            period_start=period_start,
            period_end=period_end,
        )

    async def get_reviewer_workload(self) -> ReviewerWorkloadSummary:
        """Get workload summary for reviewers."""
        query = self.supabase_client.table(_TEMP_EXAMPLES_TABLE).select(
            "assigned_reviewer, reviewer_id, approval_status, reviewed_at, created_at"
        )
        response = await self._exec(lambda: query.execute())
        rows = response.data or []

        reviewers: Dict[str, Dict[str, Any]] = {}
        now = self._now()
        today = now.date()
        week_start = (now - timedelta(days=7)).date()

        for row in rows:
            reviewer_id = row.get("assigned_reviewer") or row.get("reviewer_id")
            if not reviewer_id:
                continue
            stats = reviewers.setdefault(
                reviewer_id,
                {
                    "pending_count": 0,
                    "total_reviewed": 0,
                    "durations": [],
                    "reviews_today": 0,
                    "reviews_this_week": 0,
                },
            )

            status = row.get("approval_status")
            if status == ApprovalState.PENDING.value:
                stats["pending_count"] += 1

            reviewed_at = row.get("reviewed_at")
            created_at = row.get("created_at")
            if reviewed_at:
                stats["total_reviewed"] += 1
                try:
                    reviewed_dt = datetime.fromisoformat(str(reviewed_at))
                    if created_at:
                        created_dt = datetime.fromisoformat(str(created_at))
                        stats["durations"].append(
                            (reviewed_dt - created_dt).total_seconds() / 3600.0
                        )
                    if reviewed_dt.date() == today:
                        stats["reviews_today"] += 1
                    if reviewed_dt.date() >= week_start:
                        stats["reviews_this_week"] += 1
                except ValueError:
                    pass

        workload_items: list[ReviewerWorkload] = []
        pending_counts: list[int] = []

        for reviewer_id, stats in reviewers.items():
            pending_count = stats["pending_count"]
            pending_counts.append(pending_count)
            durations = stats["durations"]
            avg_review_time = sum(durations) / len(durations) if durations else None
            efficiency_score = None
            if self.config.max_pending_per_reviewer:
                efficiency_score = max(
                    0.0,
                    1.0 - (pending_count / float(self.config.max_pending_per_reviewer)),
                )

            workload_items.append(
                ReviewerWorkload(
                    reviewer_id=reviewer_id,
                    pending_count=pending_count,
                    total_reviewed=stats["total_reviewed"],
                    avg_review_time_hours=avg_review_time,
                    efficiency_score=efficiency_score,
                    reviews_today=stats["reviews_today"],
                    reviews_this_week=stats["reviews_this_week"],
                )
            )

        total_pending = sum(pending_counts) if pending_counts else 0
        avg_workload = (total_pending / len(pending_counts)) if pending_counts else 0.0
        max_workload = max(pending_counts) if pending_counts else 0
        min_workload = min(pending_counts) if pending_counts else 0

        recommendations: list[str] = []
        if max_workload > self.config.max_pending_per_reviewer:
            recommendations.append(
                "High reviewer load detected. Consider adding reviewers or redistributing assignments."
            )

        return ReviewerWorkloadSummary(
            reviewers=workload_items,
            total_pending=total_pending,
            avg_workload=avg_workload,
            max_workload=max_workload,
            min_workload=min_workload,
            recommendations=recommendations,
        )

    async def cleanup_old_rejected_items(self, cutoff_date: datetime) -> int:
        """Clean up old rejected temp examples."""
        response = await self._exec(
            lambda: self.supabase_client.table(_TEMP_EXAMPLES_TABLE)
            .delete()
            .eq("approval_status", ApprovalState.REJECTED.value)
            .lt("created_at", cutoff_date.isoformat())
            .execute()
        )

        return len(response.data or [])

    async def get_approval_metrics(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> WorkflowMetrics:
        """Compatibility wrapper for health checks."""
        return await self.get_workflow_metrics(start_date, end_date)
