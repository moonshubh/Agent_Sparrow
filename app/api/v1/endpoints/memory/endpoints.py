"""
Memory UI API Endpoints

CRUD and action endpoints for the Memory UI.
Provides authenticated access to memory management operations.

Endpoints:
- POST /add - Add new memory (authenticated)
- PUT /{memory_id} - Update memory (admin only)
- DELETE /{memory_id} - Delete memory (admin only)
- POST /merge - Merge duplicate memories (admin only)
- POST /{memory_id}/feedback - Submit feedback (authenticated)
- POST /export - Export memories (admin only)
- POST /duplicate/{candidate_id}/dismiss - Dismiss duplicate (admin only)
- GET /stats - Get memory statistics (authenticated)
"""

import logging
import os
import mimetypes
import asyncio
import json
import re
from datetime import datetime, timezone
from datetime import timedelta
from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple
from uuid import UUID, NAMESPACE_URL, uuid5

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi import Query
from fastapi.responses import RedirectResponse, Response

from app.core.security import get_current_user, TokenPayload
from app.core.settings import settings
from app.db.supabase.client import get_supabase_client, SupabaseClient
from app.memory.title import derive_memory_title
from app.memory.memory_ui_service import (
    MemoryUIService,
    get_memory_ui_service as _get_service,
)

from .schemas import (
    AddMemoryRequest,
    AddMemoryResponse,
    MemoryMeResponse,
    UpdateMemoryRequest,
    UpdateMemoryResponse,
    DeleteMemoryResponse,
    DeleteRelationshipResponse,
    RelationshipType,
    UpdateRelationshipRequest,
    MergeMemoriesRequest,
    MergeMemoriesResponse,
    MergeMemoriesArbitraryRequest,
    MergeMemoriesArbitraryResponse,
    SubmitFeedbackRequest,
    SubmitFeedbackResponse,
    ExportMemoriesRequest,
    ExportMemoriesResponse,
    DismissDuplicateRequest,
    DismissDuplicateResponse,
    MemoryStatsResponse,
    MemoryRecord,
    MemoryListResponse,
    MemoryEntityRecord,
    MemoryRelationshipRecord,
    DuplicateCandidateRecord,
    ImportMemorySourcesRequest,
    ImportMemorySourcesResponse,
    ImportZendeskTaggedRequest,
    ImportZendeskTaggedResponse,
    MergeRelationshipsRequest,
    MergeRelationshipsResponse,
    SplitRelationshipCommitRequest,
    SplitRelationshipCommitResponse,
    SplitRelationshipPreviewRequest,
    SplitRelationshipPreviewResponse,
    SplitRelationshipClusterSample,
    SplitRelationshipClusterSuggestion,
    RelationshipAnalysisRequest,
    RelationshipAnalysisResponse,
    RelationshipChecklistItem,
    RelationshipSuggestedAction,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Memory"])

EXPORTS_BUCKET = "memory-exports"
MEMORY_ASSET_SIGNED_TTL_SEC = int(os.getenv("MEMORY_ASSET_SIGNED_TTL_SEC", "900"))

# ============================================================================
# Auth Dependencies
# ============================================================================


async def require_admin(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
) -> TokenPayload:
    """
    Dependency that requires the user to have admin role.

    Checks if 'admin' is in the user's roles list.
    Raises 403 Forbidden if not an admin.
    """
    if not current_user.roles or "admin" not in current_user.roles:
        logger.warning(
            f"Access denied: User {current_user.sub} attempted admin operation without admin role"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for this operation",
        )
    return current_user


# ============================================================================
# Service Dependency
# ============================================================================


def get_memory_ui_service() -> MemoryUIService:
    """Get the MemoryUIService singleton instance."""
    return _get_service()


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/me",
    response_model=MemoryMeResponse,
    summary="Get current user (Memory UI)",
    description="Return the authenticated user's ID and roles for UI gating.",
    responses={
        200: {"description": "User info returned successfully"},
        401: {"description": "Authentication required"},
    },
)
async def get_memory_me(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
) -> MemoryMeResponse:
    roles = [r for r in (current_user.roles or []) if isinstance(r, str)]
    return MemoryMeResponse(
        sub=current_user.sub,
        roles=roles,
        is_admin="admin" in roles,
    )


@router.get(
    "/assets/{bucket}/{object_path:path}",
    summary="Fetch a stored memory asset (Authenticated)",
    description="Streams a stored memory asset from Supabase Storage (authenticated users only).",
    responses={
        200: {"description": "Asset retrieved successfully"},
        401: {"description": "Authentication required"},
        404: {"description": "Asset not found"},
    },
)
async def get_memory_asset(
    bucket: str,
    object_path: str,
    _current_user: Annotated[TokenPayload, Depends(get_current_user)],
    supabase: SupabaseClient = Depends(get_supabase_client),
) -> Response:
    if not bucket or not object_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        )
    if not settings.supabase_service_key:
        logger.warning(
            "memory_asset_service_key_missing bucket=%s path=%s",
            bucket,
            object_path,
        )

    try:
        data = await supabase._exec(
            lambda: supabase.client.storage.from_(bucket).download(object_path)
        )
    except Exception as exc:
        logger.debug(
            "memory_asset_download_failed bucket=%s path=%s error=%s",
            bucket,
            object_path,
            str(exc)[:180],
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        ) from exc

    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        )

    mime_type, _ = mimetypes.guess_type(object_path)
    return Response(content=data, media_type=mime_type or "application/octet-stream")


@router.get(
    "/assets/{bucket}/{object_path:path}/signed",
    summary="Get a signed URL for a memory asset (Authenticated)",
    description="Returns a short-lived signed URL for a stored memory asset.",
    responses={
        200: {"description": "Signed URL generated"},
        401: {"description": "Authentication required"},
        404: {"description": "Asset not found"},
    },
)
async def get_memory_asset_signed(
    bucket: str,
    object_path: str,
    _current_user: Annotated[TokenPayload, Depends(get_current_user)],
    supabase: SupabaseClient = Depends(get_supabase_client),
) -> dict[str, Any]:
    if not bucket or not object_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        )

    try:
        signed = await supabase._exec(
            lambda: supabase.client.storage.from_(bucket).create_signed_url(
                object_path, MEMORY_ASSET_SIGNED_TTL_SEC
            )
        )
        signed_url = None
        if isinstance(signed, dict):
            signed_url = signed.get("signedURL") or signed.get("signedUrl")

        if not signed_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
            )

        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=MEMORY_ASSET_SIGNED_TTL_SEC)
        ).isoformat()
        return {
            "signed_url": signed_url,
            "expires_at": expires_at,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error generating asset signed URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate signed URL",
        ) from exc


def _escape_like_pattern(value: str) -> str:
    """
    Escape LIKE metacharacters (% _ \\) to avoid surprising matches.
    Supabase parameterizes queries, but the LIKE pattern itself is user-controlled.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get(
    "/list",
    response_model=MemoryListResponse,
    summary="List memories",
    description="List memory records (read-only) for the Memory UI. Requires authentication.",
    responses={
        200: {"description": "Memories retrieved successfully"},
        401: {"description": "Authentication required"},
        500: {"description": "Internal server error"},
    },
)
async def list_memories(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=10000),
    agent_id: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
) -> MemoryListResponse:
    try:
        memories, total = await service.list_memories_with_total(
            agent_id=agent_id,
            tenant_id=tenant_id,
            source_type=source_type,
            limit=int(limit),
            offset=int(offset),
            sort_order=sort_order,
        )
        items = [MemoryRecord.model_validate(item) for item in memories]
        return MemoryListResponse(
            items=items,
            total=total,
            limit=int(limit),
            offset=int(offset),
        )
    except Exception as exc:
        logger.exception("Error listing memories: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list memories",
        )


@router.get(
    "/search",
    response_model=List[MemoryRecord],
    summary="Search memories (text)",
    description="Text search memories by content (case-insensitive). Requires authentication.",
    responses={
        200: {"description": "Search completed successfully"},
        401: {"description": "Authentication required"},
        500: {"description": "Internal server error"},
    },
)
async def search_memories_text(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
    query: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(default=20, ge=1, le=200),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    agent_id: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
) -> List[MemoryRecord]:
    supabase = service._get_supabase()
    trimmed = (query or "").strip()
    if not trimmed:
        return []

    escaped = _escape_like_pattern(trimmed)
    pattern = f"%{escaped}%"

    try:
        q = (
            supabase.client.table("memories")
            .select(service.MEMORY_SELECT_COLUMNS)
            .ilike("content", pattern)
            .gte("confidence_score", float(min_confidence))
            .order("confidence_score", desc=True)
            .limit(int(limit))
        )
        if agent_id:
            q = q.eq("agent_id", agent_id)
        if tenant_id:
            q = q.eq("tenant_id", tenant_id)

        resp = await supabase._exec(lambda: q.execute())
        rows = list(resp.data or [])
        return rows  # type: ignore[return-value]
    except Exception as exc:
        logger.exception("Error searching memories: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search memories",
        )


@router.get(
    "/entities",
    response_model=List[MemoryEntityRecord],
    summary="List memory entities",
    description="List extracted entities for the Memory UI graph. Requires authentication.",
)
async def list_entities(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
    limit: int = Query(default=500, ge=1, le=2000),
    entity_types: List[str] | None = Query(default=None),
) -> List[MemoryEntityRecord]:
    supabase = service._get_supabase()
    try:
        q = (
            supabase.client.table("memory_entities")
            .select("*")
            .order("occurrence_count", desc=True)
            .limit(int(limit))
        )
        if entity_types:
            q = q.in_("entity_type", entity_types)

        resp = await supabase._exec(lambda: q.execute())
        rows = list(resp.data or [])
        return rows  # type: ignore[return-value]
    except Exception as exc:
        logger.exception("Error listing memory entities: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list memory entities",
        )


@router.get(
    "/relationships",
    response_model=List[MemoryRelationshipRecord],
    summary="List memory relationships",
    description="List extracted relationships for the Memory UI graph. Requires authentication.",
)
async def list_relationships(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
    limit: int = Query(default=1000, ge=1, le=5000),
) -> List[MemoryRelationshipRecord]:
    supabase = service._get_supabase()
    try:
        q = (
            supabase.client.table("memory_relationships")
            .select("*")
            .order("occurrence_count", desc=True)
            .limit(int(limit))
        )
        resp = await supabase._exec(lambda: q.execute())
        rows = list(resp.data or [])
        return rows  # type: ignore[return-value]
    except Exception as exc:
        logger.exception("Error listing memory relationships: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list memory relationships",
        )


@router.put(
    "/relationships/{relationship_id:uuid}",
    response_model=MemoryRelationshipRecord,
    summary="Update relationship metadata (Admin only)",
    description="Update relationship endpoints, type, and weight. Requires admin privileges.",
    responses={
        200: {"description": "Relationship updated successfully"},
        400: {"description": "Invalid request"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        404: {"description": "Relationship not found"},
        409: {
            "description": "Relationship update conflicts with existing relationship"
        },
        500: {"description": "Internal server error"},
    },
)
async def update_relationship(
    relationship_id: UUID,
    request: UpdateRelationshipRequest,
    admin_user: Annotated[TokenPayload, Depends(require_admin)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> MemoryRelationshipRecord:
    if request.source_entity_id == request.target_entity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_entity_id and target_entity_id must be different",
        )

    supabase = service._get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()

    payload: Dict[str, Any] = {
        "source_entity_id": str(request.source_entity_id),
        "target_entity_id": str(request.target_entity_id),
        "relationship_type": request.relationship_type.value,
        "weight": float(request.weight),
        # Any edit requires re-review.
        "acknowledged_at": None,
        "last_modified_at": now_iso,
    }

    try:
        resp = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .update(payload)
            .eq("id", str(relationship_id))
            .execute()
        )
        rows = list(resp.data or [])
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Relationship {relationship_id} not found",
            )
        return rows[0]  # type: ignore[return-value]
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error updating relationship %s: %s", relationship_id, exc)
        message = str(exc).lower()
        if "duplicate key" in message or "unique constraint" in message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Relationship update conflicts with an existing relationship",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update relationship",
        )


@router.delete(
    "/relationships/{relationship_id:uuid}",
    response_model=DeleteRelationshipResponse,
    summary="Delete relationship (Admin only)",
    description="Delete a relationship row. Requires admin privileges.",
    responses={
        200: {"description": "Relationship deleted successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        404: {"description": "Relationship not found"},
        500: {"description": "Internal server error"},
    },
)
async def delete_relationship(
    relationship_id: UUID,
    admin_user: Annotated[TokenPayload, Depends(require_admin)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> DeleteRelationshipResponse:
    supabase = service._get_supabase()

    try:
        resp = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .delete()
            .eq("id", str(relationship_id))
            .execute()
        )
        rows = list(resp.data or [])
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Relationship {relationship_id} not found",
            )
        return DeleteRelationshipResponse(deleted=True, relationship_id=relationship_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error deleting relationship %s: %s", relationship_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete relationship",
        )


def _parse_iso_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _truncate(text: str, limit: int) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: max(0, limit - 1)]}…"


def _infer_relationship_type(text: str) -> str:
    """Heuristic fallback relationship type inference from memory text."""

    haystack = (text or "").lower()
    patterns: list[tuple[str, tuple[str, ...]]] = [
        (
            "RESOLVED_BY",
            ("resolved by", "fix", "fixed", "workaround", "solution", "resolve"),
        ),
        ("REQUIRES", ("requires", "requirement", "needs", "must have", "depends on")),
        (
            "SUPERSEDES",
            ("supersedes", "replaces", "replaced by", "deprecated", "newer version"),
        ),
        ("CAUSED_BY", ("caused by", "due to", "root cause", "because of")),
        ("REPORTED_BY", ("reported by", "customer", "user reported", "reported this")),
        ("WORKS_ON", ("works on", "compatible with", "supported on")),
        ("AFFECTS", ("affects", "impact", "impacts", "breaks", "fails on")),
    ]

    for relationship_type, keywords in patterns:
        if any(keyword in haystack for keyword in keywords):
            return relationship_type

    return "RELATED_TO"


def _pick_direction(
    source_id: str,
    target_id: str,
    source_entity_type: str | None,
    target_entity_type: str | None,
    relationship_type: str,
) -> tuple[str, str]:
    """
    Choose relationship direction based on entity types when possible.

    Falls back to (source_id, target_id) if unable to infer.
    """
    left = (source_entity_type or "").lower().strip()
    right = (target_entity_type or "").lower().strip()

    type_rules: dict[str, tuple[str, str]] = {
        "RESOLVED_BY": ("issue", "solution"),
        "AFFECTS": ("issue", "feature"),
        "REQUIRES": ("solution", "platform"),
        "REPORTED_BY": ("issue", "customer"),
        "WORKS_ON": ("solution", "platform"),
        "SUPERSEDES": ("solution", "solution"),
    }

    expected = type_rules.get(relationship_type)
    if not expected:
        return (source_id, target_id)

    expected_source, expected_target = expected
    if left == expected_source and right == expected_target:
        return (source_id, target_id)
    if left == expected_target and right == expected_source:
        return (target_id, source_id)
    return (source_id, target_id)


def _sanitize_llm_json(raw: str) -> str:
    """Strip code fences and leading text to get to JSON payload."""
    if not raw:
        return ""
    trimmed = raw.strip()
    if trimmed.startswith("```"):
        trimmed = trimmed.strip("`")
        # If language tag exists, drop first line.
        if "\n" in trimmed:
            trimmed = trimmed.split("\n", 1)[1].strip()
        if trimmed.endswith("```"):
            trimmed = trimmed[:-3].strip()
    # Best-effort: find first "{" and last "}".
    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start != -1 and end != -1 and end > start:
        return trimmed[start : end + 1]
    return trimmed


_JSON_UNQUOTED_KEY_RE = re.compile(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:")
_JSON_SINGLE_QUOTED_VALUE_RE = re.compile(r":\s*'([^']*)'")
_JSON_TRAILING_COMMA_RE = re.compile(r",(\s*[}\\]])")


def _repair_json_like(raw: str) -> str:
    """Best-effort repair for common LLM JSON mistakes (unquoted keys, single quotes)."""

    repaired = raw.strip()

    # Quote unquoted keys: {clusters: ...} -> {"clusters": ...}
    repaired = _JSON_UNQUOTED_KEY_RE.sub(r'\1"\2":', repaired)

    # Convert single-quoted string values to JSON strings.
    repaired = _JSON_SINGLE_QUOTED_VALUE_RE.sub(
        lambda m: f": {json.dumps(m.group(1))}",
        repaired,
    )

    # Remove trailing commas before } or ]
    repaired = _JSON_TRAILING_COMMA_RE.sub(r"\1", repaired)

    return repaired


def _load_llm_json(raw: str) -> dict[str, Any] | None:
    """Parse an LLM response into JSON with repair fallback."""

    candidate = _sanitize_llm_json(raw)
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    repaired = _repair_json_like(candidate)
    try:
        data = json.loads(repaired)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _llm_content_to_text(content: Any) -> str:
    """Coerce an LLM message content payload into plain text.

    Some providers (notably Gemini via LangChain) return structured content
    like: [{"type": "text", "text": "...", ...}] instead of a raw string.
    """

    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                if part.strip():
                    parts.append(part)
                continue
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content).strip()


@router.post(
    "/relationships/merge",
    response_model=MergeRelationshipsResponse,
    summary="Merge relationships (Admin only)",
    description=(
        "Destructively merge multiple relationships into a single relationship. "
        "Deleted relationships are removed permanently."
    ),
    responses={
        200: {"description": "Relationships merged successfully"},
        400: {"description": "Invalid request"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        404: {"description": "One or more relationships not found"},
        409: {"description": "Merge conflicts with an existing relationship"},
        500: {"description": "Internal server error"},
    },
)
async def merge_relationships(
    request: MergeRelationshipsRequest,
    admin_user: Annotated[TokenPayload, Depends(require_admin)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> MergeRelationshipsResponse:
    relationship_ids = list(dict.fromkeys(request.relationship_ids))
    if len(relationship_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="relationship_ids must contain at least 2 unique IDs",
        )

    if request.source_entity_id == request.target_entity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_entity_id and target_entity_id must be different",
        )

    supabase = service._get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        resp = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .select("*")
            .in_("id", [str(rid) for rid in relationship_ids])
            .execute()
        )
        rows = list(resp.data or [])
    except Exception as exc:
        logger.exception("Error fetching relationships for merge: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch relationships for merge",
        )

    found_ids = {UUID(str(r.get("id"))) for r in rows if r.get("id")}
    missing = [str(rid) for rid in relationship_ids if rid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relationships not found: {', '.join(missing)}",
        )

    target_source = str(request.source_entity_id)
    target_target = str(request.target_entity_id)
    target_type = request.relationship_type.value

    # Prevent creating a relationship that conflicts with an existing one outside the merge set.
    try:
        conflict = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .select("id")
            .eq("source_entity_id", target_source)
            .eq("target_entity_id", target_target)
            .eq("relationship_type", target_type)
            .execute()
        )
        conflict_ids = {
            UUID(str(r.get("id"))) for r in list(conflict.data or []) if r.get("id")
        }
        if conflict_ids and not conflict_ids.intersection(set(relationship_ids)):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Merge conflicts with an existing relationship",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error checking merge conflicts: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate merge request",
        )

    def _matches_target(row: dict[str, Any]) -> bool:
        return (
            str(row.get("source_entity_id")) == target_source
            and str(row.get("target_entity_id")) == target_target
            and str(row.get("relationship_type")) == target_type
        )

    keep_row = next((r for r in rows if _matches_target(r)), None)
    keep_id = str(keep_row.get("id")) if keep_row else None

    total_occurrence = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    source_memory_choice: Optional[Tuple[datetime, str]] = None

    for row in rows:
        occurrence = row.get("occurrence_count")
        if isinstance(occurrence, int):
            total_occurrence += occurrence
        elif isinstance(occurrence, str) and occurrence.isdigit():
            total_occurrence += int(occurrence)

        seen_first = _parse_iso_timestamp(row.get("first_seen_at"))
        seen_last = _parse_iso_timestamp(row.get("last_seen_at"))
        if seen_first and (first_seen is None or seen_first < first_seen):
            first_seen = seen_first
        if seen_last and (last_seen is None or seen_last > last_seen):
            last_seen = seen_last

        mid = row.get("source_memory_id")
        if isinstance(mid, str) and mid:
            ts = seen_last or seen_first or datetime.min.replace(tzinfo=timezone.utc)
            if source_memory_choice is None or ts > source_memory_choice[0]:
                source_memory_choice = (ts, mid)

    total_occurrence = max(1, total_occurrence)

    payload: Dict[str, Any] = {
        "source_entity_id": target_source,
        "target_entity_id": target_target,
        "relationship_type": target_type,
        "weight": float(request.weight),
        "occurrence_count": total_occurrence,
        "source_memory_id": source_memory_choice[1] if source_memory_choice else None,
        "first_seen_at": (first_seen or datetime.now(timezone.utc)).isoformat(),
        "last_seen_at": (last_seen or datetime.now(timezone.utc)).isoformat(),
        # Any merge requires re-review.
        "acknowledged_at": None,
        "last_modified_at": now_iso,
    }

    deleted_ids: list[str] = []

    try:
        if keep_id:
            update_resp = await supabase._exec(
                lambda: supabase.client.table("memory_relationships")
                .update(payload)
                .eq("id", keep_id)
                .execute()
            )
            updated_rows = list(update_resp.data or [])
            if not updated_rows:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Relationship {keep_id} not found",
                )

            deleted_ids = [str(rid) for rid in relationship_ids if str(rid) != keep_id]
            if deleted_ids:
                await supabase._exec(
                    lambda: supabase.client.table("memory_relationships")
                    .delete()
                    .in_("id", deleted_ids)
                    .execute()
                )

            return MergeRelationshipsResponse(
                merged_relationship=updated_rows[0],  # type: ignore[arg-type]
                deleted_relationship_ids=[UUID(v) for v in deleted_ids],
            )

        insert_resp = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .insert(payload)
            .execute()
        )
        inserted_rows = list(insert_resp.data or [])
        if not inserted_rows:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create merged relationship",
            )

        deleted_ids = [str(rid) for rid in relationship_ids]
        await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .delete()
            .in_("id", deleted_ids)
            .execute()
        )

        return MergeRelationshipsResponse(
            merged_relationship=inserted_rows[0],  # type: ignore[arg-type]
            deleted_relationship_ids=[UUID(v) for v in deleted_ids],
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error merging relationships: %s", exc)
        message = str(exc).lower()
        if "duplicate key" in message or "unique constraint" in message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Merge conflicts with an existing relationship",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to merge relationships",
        )


@router.post(
    "/relationships/{relationship_id:uuid}/split/preview",
    response_model=SplitRelationshipPreviewResponse,
    summary="Preview relationship split",
    description=(
        "Generate an AI-assisted preview for splitting an entity-pair edge into "
        "multiple relationship types. Uses embeddings clustering when available."
    ),
    responses={
        200: {"description": "Split preview generated successfully"},
        401: {"description": "Authentication required"},
        404: {"description": "Relationship not found"},
        500: {"description": "Internal server error"},
    },
)
async def split_relationship_preview(
    relationship_id: UUID,
    request: SplitRelationshipPreviewRequest,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> SplitRelationshipPreviewResponse:
    supabase = service._get_supabase()

    try:
        rel_resp = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .select("id,source_entity_id,target_entity_id")
            .eq("id", str(relationship_id))
            .execute()
        )
        rel_rows = list(rel_resp.data or [])
        if not rel_rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Relationship {relationship_id} not found",
            )
        rel_row = rel_rows[0]
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error fetching relationship for split preview: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch relationship for split preview",
        )

    source_id = str(rel_row.get("source_entity_id"))
    target_id = str(rel_row.get("target_entity_id"))

    try:
        edge_resp = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .select(
                "id,source_entity_id,target_entity_id,relationship_type,weight,occurrence_count,source_memory_id,last_seen_at"
            )
            .or_(
                f"and(source_entity_id.eq.{source_id},target_entity_id.eq.{target_id}),"
                f"and(source_entity_id.eq.{target_id},target_entity_id.eq.{source_id})"
            )
            .order("last_seen_at", desc=True)
            .limit(5000)
            .execute()
        )
        edge_rows = list(edge_resp.data or [])
    except Exception as exc:
        logger.exception("Error fetching edge relationships for split preview: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch edge relationships for split preview",
        )

    existing_relationship_ids = [
        UUID(str(r.get("id"))) for r in edge_rows if r.get("id") is not None
    ]

    # Gather up to max_memories distinct memory IDs from relationship provenance.
    memory_ids: list[str] = []
    seen_mid: set[str] = set()
    for row in edge_rows:
        mid = row.get("source_memory_id")
        if not isinstance(mid, str) or not mid:
            continue
        if mid in seen_mid:
            continue
        seen_mid.add(mid)
        memory_ids.append(mid)
        if len(memory_ids) >= int(request.max_memories):
            break

    # Fetch entity metadata for direction heuristics / UI labels.
    entity_meta: dict[str, dict[str, Any]] = {}
    try:
        ent_resp = await supabase._exec(
            lambda: supabase.client.table("memory_entities")
            .select("id,entity_type,display_label,entity_name")
            .in_("id", [source_id, target_id])
            .execute()
        )
        for row in list(ent_resp.data or []):
            eid = str(row.get("id"))
            if eid:
                entity_meta[eid] = row
    except Exception:
        # Metadata is optional; proceed without it.
        entity_meta = {}

    # Summarize edge types to provide sensible defaults.
    dominant_type = "RELATED_TO"
    dominant_weight = 1.0
    if edge_rows:
        type_weight: dict[str, int] = {}
        for row in edge_rows:
            rtype = row.get("relationship_type")
            if not isinstance(rtype, str) or not rtype:
                continue
            count = row.get("occurrence_count")
            weight = int(count) if isinstance(count, int) else 1
            type_weight[rtype] = type_weight.get(rtype, 0) + weight
            w = row.get("weight")
            if isinstance(w, (int, float)):
                dominant_weight = max(dominant_weight, float(w))
        if type_weight:
            dominant_type = sorted(
                type_weight.items(), key=lambda item: item[1], reverse=True
            )[0][0]

    source_type = str(entity_meta.get(source_id, {}).get("entity_type") or "")
    target_type = str(entity_meta.get(target_id, {}).get("entity_type") or "")

    mem_rows: list[dict[str, Any]] = []
    provenance_note: str | None = None

    if memory_ids:
        try:
            mem_resp = await supabase._exec(
                lambda: supabase.client.table("memories")
                .select("id,content,metadata,embedding,confidence_score,created_at")
                .in_("id", memory_ids)
                .execute()
            )
            mem_rows = list(mem_resp.data or [])
        except Exception as exc:
            logger.exception("Error fetching memories for split preview: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch memories for split preview",
            )
    else:
        provenance_note = (
            "No relationship provenance found (source_memory_id missing). "
            "Using a text-search fallback over memories."
        )

        def _pick_entity_term(entity_id: str) -> str | None:
            meta = entity_meta.get(entity_id) or {}
            for key in ("display_label", "entity_name"):
                value = meta.get(key)
                if isinstance(value, str):
                    term = value.strip()
                    if len(term) >= 3:
                        return term
            return None

        source_term = _pick_entity_term(source_id)
        target_term = _pick_entity_term(target_id)

        if source_term and target_term:
            try:
                escaped_source = _escape_like_pattern(source_term)
                escaped_target = _escape_like_pattern(target_term)
                mem_resp = await supabase._exec(
                    lambda: supabase.client.table("memories")
                    .select("id,content,metadata,embedding,confidence_score,created_at")
                    .ilike("content", f"%{escaped_source}%")
                    .ilike("content", f"%{escaped_target}%")
                    .order("created_at", desc=True)
                    .limit(int(request.max_memories))
                    .execute()
                )
                mem_rows = list(mem_resp.data or [])
            except Exception as exc:
                logger.exception(
                    "Error fetching fallback memories for split preview: %s", exc
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to fetch fallback memories for split preview",
                )

        if not mem_rows:
            return SplitRelationshipPreviewResponse(
                relationship_id=relationship_id,
                source_entity_id=UUID(source_id),
                target_entity_id=UUID(target_id),
                existing_relationship_ids=existing_relationship_ids,
                clusters=[],
                used_ai=False,
                ai_error=provenance_note,
            )

    allowed_relationship_types = {rt.value for rt in RelationshipType}

    def build_text_cluster_suggestions(
        rows: list[dict[str, Any]],
    ) -> list[SplitRelationshipClusterSuggestion]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            inferred = _infer_relationship_type(str(row.get("content") or ""))
            if inferred not in allowed_relationship_types:
                inferred = dominant_type
            groups.setdefault(inferred, []).append(row)

        if not groups:
            return []

        sorted_groups = sorted(
            groups.items(), key=lambda item: len(item[1]), reverse=True
        )
        suggestions: list[SplitRelationshipClusterSuggestion] = []

        for cluster_index, (rtype, rows_in_group) in enumerate(
            sorted_groups[: int(request.max_clusters)]
        ):
            direction_source, direction_target = _pick_direction(
                source_id, target_id, source_type, target_type, rtype
            )

            sample_title = ""
            first_row = rows_in_group[0] if rows_in_group else {}
            first_meta = first_row.get("metadata")
            first_content = str(first_row.get("content") or "")
            if isinstance(first_meta, dict):
                title = first_meta.get("title")
                if isinstance(title, str) and title.strip():
                    sample_title = title.strip()
            if not sample_title:
                sample_title = derive_memory_title(first_content, max_length=72)

            relationship_label = rtype.replace("_", " ").title()
            name = sample_title
            if not name or name == "Untitled memory":
                name = (
                    relationship_label if rtype != "RELATED_TO" else "Related context"
                )

            memory_ids_cluster: list[UUID] = []
            for row in rows_in_group:
                mid = row.get("id")
                if not mid:
                    continue
                try:
                    memory_ids_cluster.append(UUID(str(mid)))
                except Exception:
                    continue

            samples: list[SplitRelationshipClusterSample] = []
            sample_limit = int(request.samples_per_cluster)
            if sample_limit > 0:
                for row in rows_in_group[:sample_limit]:
                    mid = row.get("id")
                    if not mid:
                        continue
                    score = row.get("confidence_score")
                    try:
                        samples.append(
                            SplitRelationshipClusterSample(
                                id=UUID(str(mid)),
                                content_preview=_truncate(
                                    str(row.get("content") or ""), 280
                                ),
                                confidence_score=(
                                    float(score)
                                    if isinstance(score, (int, float))
                                    else None
                                ),
                                created_at=_parse_iso_timestamp(row.get("created_at")),
                            )
                        )
                    except Exception:
                        continue

            suggestions.append(
                SplitRelationshipClusterSuggestion(
                    cluster_id=cluster_index,
                    name=name,
                    source_entity_id=UUID(direction_source),
                    target_entity_id=UUID(direction_target),
                    relationship_type=RelationshipType(rtype),
                    weight=float(dominant_weight),
                    occurrence_count=max(1, len(memory_ids_cluster)),
                    memory_ids=memory_ids_cluster,
                    samples=samples,
                )
            )

        return suggestions

    # Filter memories with usable embeddings.
    embeddings: list[list[float]] = []
    mem_by_idx: list[dict[str, Any]] = []
    mem_no_embedding: list[dict[str, Any]] = []
    for row in mem_rows:
        emb = row.get("embedding")
        if not isinstance(emb, list) or not emb:
            mem_no_embedding.append(row)
            continue
        if not all(isinstance(v, (int, float)) for v in emb):
            mem_no_embedding.append(row)
            continue
        embeddings.append([float(v) for v in emb])
        mem_by_idx.append(row)

    total_samples = len(mem_by_idx)
    if total_samples < 2:
        suggestions = build_text_cluster_suggestions(mem_rows)
        used_ai = False
        model_id: str | None = None
        ai_error: str | None = None

        if not suggestions:
            return SplitRelationshipPreviewResponse(
                relationship_id=relationship_id,
                source_entity_id=UUID(source_id),
                target_entity_id=UUID(target_id),
                existing_relationship_ids=existing_relationship_ids,
                clusters=[],
                used_ai=False,
            )

        if request.use_ai and not settings.gemini_api_key:
            ai_error = (
                "AI enrichment unavailable: missing GEMINI_API_KEY / GOOGLE_API_KEY."
            )

        if request.use_ai and settings.gemini_api_key:
            if len(suggestions) <= 1:
                ai_error = "AI enrichment skipped (not enough clusters to meaningfully refine)."
            else:
                try:
                    from app.agents.unified.provider_factory import build_chat_model
                    from app.core.config import get_registry

                    registry = get_registry()
                    model_id = getattr(
                        registry, "memory_clustering", registry.coordinator_google
                    ).id

                    response_schema = {
                        "type": "object",
                        "properties": {
                            "clusters": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "cluster_id": {"type": "integer"},
                                        "name": {"type": "string"},
                                        "relationship_type": {
                                            "type": "string",
                                            "enum": [
                                                rt.value for rt in RelationshipType
                                            ],
                                        },
                                        "direction": {
                                            "type": "string",
                                            "enum": ["A_TO_B", "B_TO_A"],
                                        },
                                        "weight": {"type": "number"},
                                    },
                                    "required": [
                                        "cluster_id",
                                        "name",
                                        "relationship_type",
                                        "direction",
                                        "weight",
                                    ],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["clusters"],
                        "additionalProperties": False,
                    }

                    llm_base = build_chat_model(
                        provider="google",
                        model=model_id,
                        role="memory_clustering",
                    )
                    try:
                        llm_base = llm_base.model_copy(  # type: ignore[attr-defined]
                            update={"max_retries": 1, "timeout": 20.0}
                        )
                    except Exception:
                        for attr, value in (("max_retries", 1), ("timeout", 20.0)):
                            if hasattr(llm_base, attr):
                                try:
                                    setattr(llm_base, attr, value)
                                except Exception:
                                    pass

                    llm = llm_base.bind(
                        response_mime_type="application/json",
                        response_schema=response_schema,
                    )

                    entity_a_label = str(
                        entity_meta.get(source_id, {}).get("display_label")
                        or entity_meta.get(source_id, {}).get("entity_name")
                        or source_id
                    )
                    entity_b_label = str(
                        entity_meta.get(target_id, {}).get("display_label")
                        or entity_meta.get(target_id, {}).get("entity_name")
                        or target_id
                    )

                    prompt_lines: list[str] = [
                        "You are helping split a knowledge-graph edge into clearer relationship types.",
                        "Return STRICT JSON only. No markdown. No commentary.",
                        "",
                        f"Entity A: id={source_id}, type={source_type or 'unknown'}, label={entity_a_label!r}",
                        f"Entity B: id={target_id}, type={target_type or 'unknown'}, label={entity_b_label!r}",
                        "",
                        "Allowed relationship_type values: "
                        "RESOLVED_BY, AFFECTS, REQUIRES, CAUSED_BY, REPORTED_BY, WORKS_ON, RELATED_TO, SUPERSEDES",
                        "Direction values: A_TO_B or B_TO_A (relative to Entity A and Entity B above).",
                        "",
                        "For each cluster, produce:",
                        "- cluster_id (number)",
                        "- name (short label)",
                        "- relationship_type (one of allowed)",
                        '- direction (either "A_TO_B" or "B_TO_A")',
                        "- weight (number 0-10)",
                        "",
                        "Naming guidance:",
                        "- Prefer human-readable names derived from the memory titles/summaries below.",
                        '- Avoid IDs, UUIDs, ticket numbers, and generic labels like "Cluster 1".',
                        "",
                        "Clusters:",
                    ]

                    for suggestion in suggestions:
                        prompt_lines.append(f"- cluster_id={suggestion.cluster_id}")
                        prompt_lines.append(f"  * heuristic_name={suggestion.name!r}")
                        prompt_lines.append(
                            f"  * heuristic_relationship_type={suggestion.relationship_type.value!r}"
                        )
                        prompt_lines.append(
                            "  * heuristic_direction="
                            f"{'A_TO_B' if suggestion.source_entity_id == UUID(source_id) else 'B_TO_A'}"
                        )
                        for sample in suggestion.samples[:2]:
                            sample_title = derive_memory_title(
                                sample.content_preview, max_length=72
                            )
                            sample_preview = _truncate(
                                str(sample.content_preview or ""), 260
                            )
                            prompt_lines.append(f"  * sample_title: {sample_title!r}")
                            prompt_lines.append(f"    sample_text: {sample_preview!r}")

                    prompt_lines.append("")
                    prompt_lines.append('Output JSON as: {"clusters":[...]}')

                    response = await asyncio.wait_for(
                        llm.ainvoke("\n".join(prompt_lines)),
                        timeout=24.0,
                    )
                    raw_text = _llm_content_to_text(getattr(response, "content", ""))
                    data = _load_llm_json(raw_text)
                    if not data:
                        raise ValueError("LLM returned invalid JSON for split preview")

                    clusters_data: Any = None
                    if isinstance(data, dict):
                        clusters_data = data.get("clusters")
                    elif isinstance(data, list):
                        clusters_data = data

                    if isinstance(clusters_data, list):
                        by_id = {s.cluster_id: s for s in suggestions}
                        for item in clusters_data:
                            if not isinstance(item, dict):
                                continue
                            cid = item.get("cluster_id")
                            if not isinstance(cid, int) or cid not in by_id:
                                continue
                            s = by_id[cid]

                            name = item.get("name")
                            if isinstance(name, str) and name.strip():
                                s.name = _truncate(name.strip(), 120)

                            rtype = item.get("relationship_type")
                            if isinstance(rtype, str) and rtype.strip():
                                try:
                                    s.relationship_type = RelationshipType(
                                        rtype.strip()
                                    )
                                except ValueError:
                                    continue

                            direction = item.get("direction")
                            if direction == "B_TO_A":
                                s.source_entity_id = UUID(target_id)
                                s.target_entity_id = UUID(source_id)
                            elif direction == "A_TO_B":
                                s.source_entity_id = UUID(source_id)
                                s.target_entity_id = UUID(target_id)

                            item_weight = item.get("weight")
                            if isinstance(item_weight, (int, float)):
                                s.weight = float(max(0.0, min(10.0, item_weight)))

                        used_ai = True
                except Exception as exc:
                    logger.exception(
                        "Split preview AI enrichment failed",
                        extra={"model_id": model_id},
                    )
                    if isinstance(exc, asyncio.TimeoutError):
                        ai_error = "AI enrichment timed out. Using heuristic labels."
                    else:
                        message = str(exc).lower()
                        if (
                            "quota" in message
                            or "rate" in message
                            or "resourceexhausted" in message
                        ):
                            ai_error = (
                                "AI enrichment unavailable (quota/rate-limited). "
                                "Using heuristic labels."
                            )
                        else:
                            ai_error = "AI enrichment failed. Using heuristic labels."
                    used_ai = False

        return SplitRelationshipPreviewResponse(
            relationship_id=relationship_id,
            source_entity_id=UUID(source_id),
            target_entity_id=UUID(target_id),
            existing_relationship_ids=existing_relationship_ids,
            clusters=suggestions,
            used_ai=used_ai,
            ai_model_id=model_id if used_ai else None,
            ai_error=ai_error,
        )

    # Choose k and cluster (CPU-bound). Import sklearn lazily.
    labels: list[int] = []
    if total_samples < 2:
        labels = [0]
    else:
        from sklearn.cluster import KMeans  # type: ignore
        from sklearn.metrics import silhouette_score  # type: ignore
        import numpy as np  # type: ignore

        X = np.asarray(embeddings, dtype=float)
        if request.cluster_count is not None:
            k = int(request.cluster_count)
            if k > total_samples:
                k = total_samples
            if k < 2:
                k = 2
        else:
            max_k = min(int(request.max_clusters), max(2, total_samples))
            max_k = min(max_k, total_samples - 1) if total_samples > 2 else max_k
            candidate_ks = list(range(2, max_k + 1))
            best_k = 2
            best_score = -1.0
            for candidate_k in candidate_ks:
                if candidate_k >= total_samples:
                    continue
                try:
                    model = KMeans(
                        n_clusters=candidate_k,
                        n_init=10,
                        random_state=42,
                    )
                    candidate_labels = model.fit_predict(X)
                    score = float(silhouette_score(X, candidate_labels))
                except Exception:
                    continue
                if score > best_score:
                    best_score = score
                    best_k = candidate_k
            k = best_k

        model = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = [int(v) for v in model.fit_predict(X)]

    # Build initial cluster suggestions (heuristic names/types).
    clusters_by_label: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        clusters_by_label.setdefault(label, []).append(idx)

    cluster_suggestions: list[SplitRelationshipClusterSuggestion] = []
    sorted_labels = sorted(
        clusters_by_label.items(), key=lambda item: len(item[1]), reverse=True
    )

    for cluster_index, (_, indices) in enumerate(sorted_labels):
        cluster_text = "\n".join(
            str(mem_by_idx[i].get("content") or "") for i in indices[:5]
        )
        inferred_type = _infer_relationship_type(cluster_text)
        if inferred_type not in allowed_relationship_types:
            inferred_type = dominant_type

        direction_source, direction_target = _pick_direction(
            source_id, target_id, source_type, target_type, inferred_type
        )

        sample_title = ""
        if indices:
            first_row = mem_by_idx[indices[0]]
            first_meta = first_row.get("metadata")
            first_content = str(first_row.get("content") or "")
            if isinstance(first_meta, dict):
                title = first_meta.get("title")
                if isinstance(title, str) and title.strip():
                    sample_title = title.strip()
            if not sample_title:
                sample_title = derive_memory_title(first_content, max_length=72)

        relationship_label = inferred_type.replace("_", " ").title()
        name = sample_title
        if not name or name == "Untitled memory":
            name = (
                relationship_label
                if inferred_type != "RELATED_TO"
                else "Related context"
            )

        memory_ids_cluster = [
            UUID(str(mem_by_idx[i].get("id")))
            for i in indices
            if mem_by_idx[i].get("id")
        ]

        samples: list[SplitRelationshipClusterSample] = []
        sample_limit = int(request.samples_per_cluster)
        if sample_limit > 0:
            for i in indices[:sample_limit]:
                row = mem_by_idx[i]
                mid = row.get("id")
                if not mid:
                    continue
                confidence_value = row.get("confidence_score")
                samples.append(
                    SplitRelationshipClusterSample(
                        id=UUID(str(mid)),
                        content_preview=_truncate(str(row.get("content") or ""), 280),
                        confidence_score=(
                            float(confidence_value)
                            if isinstance(confidence_value, (int, float))
                            else None
                        ),
                        created_at=_parse_iso_timestamp(row.get("created_at")),
                    )
                )

        cluster_suggestions.append(
            SplitRelationshipClusterSuggestion(
                cluster_id=cluster_index,
                name=name,
                source_entity_id=UUID(direction_source),
                target_entity_id=UUID(direction_target),
                relationship_type=RelationshipType(inferred_type),
                weight=float(dominant_weight),
                occurrence_count=max(1, len(memory_ids_cluster)),
                memory_ids=memory_ids_cluster,
                samples=samples,
            )
        )

    # Assign memories without embeddings to the closest inferred relationship_type cluster.
    if mem_no_embedding and cluster_suggestions:
        by_type: dict[str, SplitRelationshipClusterSuggestion] = {}
        for s in cluster_suggestions:
            by_type[s.relationship_type.value] = s

        default_cluster = cluster_suggestions[0]
        sample_limit = int(request.samples_per_cluster)

        for row in mem_no_embedding:
            inferred = _infer_relationship_type(str(row.get("content") or ""))
            if inferred not in allowed_relationship_types:
                inferred = dominant_type

            target_cluster = by_type.get(inferred, default_cluster)
            mid = row.get("id")
            if not mid:
                continue
            try:
                memory_uuid = UUID(str(mid))
            except Exception:
                continue
            if memory_uuid not in target_cluster.memory_ids:
                target_cluster.memory_ids.append(memory_uuid)
                target_cluster.occurrence_count = max(1, len(target_cluster.memory_ids))

            if sample_limit > 0 and len(target_cluster.samples) < sample_limit:
                try:
                    confidence_value = row.get("confidence_score")
                    target_cluster.samples.append(
                        SplitRelationshipClusterSample(
                            id=memory_uuid,
                            content_preview=_truncate(
                                str(row.get("content") or ""), 280
                            ),
                            confidence_score=(
                                float(confidence_value)
                                if isinstance(confidence_value, (int, float))
                                else None
                            ),
                            created_at=_parse_iso_timestamp(row.get("created_at")),
                        )
                    )
                except Exception:
                    continue

    used_ai = False
    cluster_model_id: str | None = None
    cluster_ai_error: str | None = None

    if request.use_ai and not settings.gemini_api_key:
        cluster_ai_error = (
            "AI enrichment unavailable: missing GEMINI_API_KEY / GOOGLE_API_KEY."
        )

    if request.use_ai and settings.gemini_api_key and len(cluster_suggestions) > 1:
        try:
            from app.agents.unified.provider_factory import build_chat_model
            from app.core.config import get_registry

            registry = get_registry()
            cluster_model_id = getattr(
                registry, "memory_clustering", registry.coordinator_google
            ).id

            response_schema = {
                "type": "object",
                "properties": {
                    "clusters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "cluster_id": {"type": "integer"},
                                "name": {"type": "string"},
                                "relationship_type": {
                                    "type": "string",
                                    "enum": [rt.value for rt in RelationshipType],
                                },
                                "direction": {
                                    "type": "string",
                                    "enum": ["A_TO_B", "B_TO_A"],
                                },
                                "weight": {"type": "number"},
                            },
                            "required": [
                                "cluster_id",
                                "name",
                                "relationship_type",
                                "direction",
                                "weight",
                            ],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["clusters"],
                "additionalProperties": False,
            }

            llm_base = build_chat_model(
                provider="google",
                model=cluster_model_id,
                role="memory_clustering",
            )
            try:
                llm_base = llm_base.model_copy(  # type: ignore[attr-defined]
                    update={"max_retries": 1, "timeout": 20.0}
                )
            except Exception:
                for attr, value in (("max_retries", 1), ("timeout", 20.0)):
                    if hasattr(llm_base, attr):
                        try:
                            setattr(llm_base, attr, value)
                        except Exception:
                            pass

            llm = llm_base.bind(
                response_mime_type="application/json",
                response_schema=response_schema,
            )

            entity_a_label = str(
                entity_meta.get(source_id, {}).get("display_label")
                or entity_meta.get(source_id, {}).get("entity_name")
                or source_id
            )
            entity_b_label = str(
                entity_meta.get(target_id, {}).get("display_label")
                or entity_meta.get(target_id, {}).get("entity_name")
                or target_id
            )

            cluster_prompt_lines: list[str] = [
                "You are helping split a knowledge-graph edge into clearer relationship types.",
                "Return STRICT JSON only. No markdown. No commentary.",
                "",
                f"Entity A: id={source_id}, type={source_type or 'unknown'}, label={entity_a_label!r}",
                f"Entity B: id={target_id}, type={target_type or 'unknown'}, label={entity_b_label!r}",
                "",
                "Allowed relationship_type values: "
                "RESOLVED_BY, AFFECTS, REQUIRES, CAUSED_BY, REPORTED_BY, WORKS_ON, RELATED_TO, SUPERSEDES",
                "Direction values: A_TO_B or B_TO_A (relative to Entity A and Entity B above).",
                "",
                "For each cluster, produce:",
                "- cluster_id (number)",
                "- name (short label)",
                "- relationship_type (one of allowed)",
                '- direction (either "A_TO_B" or "B_TO_A")',
                "- weight (number 0-10)",
                "",
                "Naming guidance:",
                "- Prefer human-readable names derived from the memory titles/summaries below.",
                '- Avoid IDs, UUIDs, ticket numbers, and generic labels like "Cluster 1".',
                "",
                "Clusters:",
            ]

            for s in cluster_suggestions:
                cluster_prompt_lines.append(f"- cluster_id={s.cluster_id}")
                cluster_prompt_lines.append(f"  * heuristic_name={s.name!r}")
                cluster_prompt_lines.append(
                    f"  * heuristic_relationship_type={s.relationship_type.value!r}"
                )
                cluster_prompt_lines.append(
                    f"  * heuristic_direction={'A_TO_B' if s.source_entity_id == UUID(source_id) else 'B_TO_A'}"
                )
                for sample in s.samples[:2]:
                    sample_title = derive_memory_title(
                        sample.content_preview, max_length=72
                    )
                    sample_preview = _truncate(str(sample.content_preview or ""), 260)
                    cluster_prompt_lines.append(f"  * sample_title: {sample_title!r}")
                    cluster_prompt_lines.append(f"    sample_text: {sample_preview!r}")

            cluster_prompt_lines.append("")
            cluster_prompt_lines.append('Output JSON as: {"clusters":[...]}')

            response = await asyncio.wait_for(
                llm.ainvoke("\n".join(cluster_prompt_lines)),
                timeout=24.0,
            )
            raw_text = _llm_content_to_text(getattr(response, "content", ""))
            data = _load_llm_json(raw_text)
            if not data:
                raise ValueError("LLM returned invalid JSON for split preview")

            cluster_clusters_data: Any = None
            if isinstance(data, dict):
                cluster_clusters_data = data.get("clusters")
            elif isinstance(data, list):
                cluster_clusters_data = data
            if isinstance(cluster_clusters_data, list):
                by_id = {s.cluster_id: s for s in cluster_suggestions}
                for item in cluster_clusters_data:
                    if not isinstance(item, dict):
                        continue
                    cid = item.get("cluster_id")
                    if not isinstance(cid, int) or cid not in by_id:
                        continue
                    s = by_id[cid]

                    name = item.get("name")
                    if isinstance(name, str) and name.strip():
                        s.name = _truncate(name.strip(), 120)

                    rtype = item.get("relationship_type")
                    if isinstance(rtype, str) and rtype.strip():
                        try:
                            s.relationship_type = RelationshipType(rtype.strip())
                        except ValueError:
                            continue

                    direction = item.get("direction")
                    if direction == "B_TO_A":
                        s.source_entity_id = UUID(target_id)
                        s.target_entity_id = UUID(source_id)
                    elif direction == "A_TO_B":
                        s.source_entity_id = UUID(source_id)
                        s.target_entity_id = UUID(target_id)

                    item_weight = item.get("weight")
                    if isinstance(item_weight, (int, float)):
                        s.weight = float(max(0.0, min(10.0, item_weight)))

                used_ai = True
        except Exception as exc:
            logger.exception(
                "Split preview AI enrichment failed",
                extra={"model_id": cluster_model_id},
            )
            if isinstance(exc, asyncio.TimeoutError):
                cluster_ai_error = "AI enrichment timed out. Using heuristic labels."
            else:
                message = str(exc).lower()
                if (
                    "quota" in message
                    or "rate" in message
                    or "resourceexhausted" in message
                ):
                    cluster_ai_error = "AI enrichment unavailable (quota/rate-limited). Using heuristic labels."
                else:
                    cluster_ai_error = "AI enrichment failed. Using heuristic labels."
            used_ai = False

    return SplitRelationshipPreviewResponse(
        relationship_id=relationship_id,
        source_entity_id=UUID(source_id),
        target_entity_id=UUID(target_id),
        existing_relationship_ids=existing_relationship_ids,
        clusters=cluster_suggestions,
        used_ai=used_ai,
        ai_model_id=cluster_model_id if used_ai else None,
        ai_error=cluster_ai_error,
    )


@router.post(
    "/relationships/{relationship_id:uuid}/analysis",
    response_model=RelationshipAnalysisResponse,
    summary="Analyze a relationship edge",
    description=(
        "Generate an artifact-style analysis for an entity-pair relationship using "
        "direct provenance memories plus a limited set of top neighbor edges."
    ),
    responses={
        200: {"description": "Analysis generated successfully"},
        401: {"description": "Authentication required"},
        404: {"description": "Relationship not found"},
        500: {"description": "Internal server error"},
    },
)
async def analyze_relationship(
    relationship_id: UUID,
    request: RelationshipAnalysisRequest,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> RelationshipAnalysisResponse:
    try:
        supabase = service._get_supabase()
    except Exception as exc:
        logger.exception("Supabase unavailable for relationship analysis: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory backend unavailable (Supabase not configured)",
        )

    try:
        rel_resp = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .select("id,source_entity_id,target_entity_id")
            .eq("id", str(relationship_id))
            .execute()
        )
        rel_rows = list(rel_resp.data or [])
        if not rel_rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Relationship {relationship_id} not found",
            )
        rel_row = rel_rows[0]
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error fetching relationship for analysis: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch relationship for analysis",
        )

    source_id = str(rel_row.get("source_entity_id"))
    target_id = str(rel_row.get("target_entity_id"))

    try:
        edge_resp = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .select(
                "id,source_entity_id,target_entity_id,relationship_type,weight,occurrence_count,source_memory_id,last_seen_at,acknowledged_at,last_modified_at"
            )
            .or_(
                f"and(source_entity_id.eq.{source_id},target_entity_id.eq.{target_id}),"
                f"and(source_entity_id.eq.{target_id},target_entity_id.eq.{source_id})"
            )
            .order("last_seen_at", desc=True)
            .limit(5000)
            .execute()
        )
        edge_rows = list(edge_resp.data or [])
    except Exception as exc:
        logger.exception("Error fetching relationships for analysis: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch relationships for analysis",
        )

    # Direct provenance memories from the selected entity pair.
    direct_memory_ids: list[str] = []
    seen_direct: set[str] = set()
    for row in edge_rows:
        mid = row.get("source_memory_id")
        if not isinstance(mid, str) or not mid:
            continue
        if mid in seen_direct:
            continue
        seen_direct.add(mid)
        direct_memory_ids.append(mid)
        if len(direct_memory_ids) >= int(request.max_direct_memories):
            break

    async def _get_neighbor_rows(entity_id: str, other_id: str) -> list[dict[str, Any]]:
        try:
            resp = await supabase._exec(
                lambda: supabase.client.table("memory_relationships")
                .select(
                    "id,source_entity_id,target_entity_id,relationship_type,weight,occurrence_count,source_memory_id,last_seen_at,acknowledged_at,last_modified_at"
                )
                .or_(f"source_entity_id.eq.{entity_id},target_entity_id.eq.{entity_id}")
                .order("weight", desc=True)
                .order("occurrence_count", desc=True)
                .order("last_seen_at", desc=True)
                .limit(400)
                .execute()
            )
            rows = list(resp.data or [])
        except Exception:
            return []

        best_by_neighbor: dict[str, dict[str, Any]] = {}
        for row in rows:
            s = str(row.get("source_entity_id") or "")
            t = str(row.get("target_entity_id") or "")
            if not s or not t:
                continue
            neighbor = t if s == entity_id else s if t == entity_id else ""
            if not neighbor or neighbor == entity_id or neighbor == other_id:
                continue
            w = row.get("weight")
            oc = row.get("occurrence_count")
            score = (float(w) if isinstance(w, (int, float)) else 0.0) * 1.25 + (
                float(oc) if isinstance(oc, int) else 0.0
            ) * 0.2
            existing = best_by_neighbor.get(neighbor)
            if not existing or score > float(existing.get("__score") or 0):
                row["__score"] = score
                best_by_neighbor[neighbor] = row

        candidates = list(best_by_neighbor.values())
        candidates.sort(key=lambda r: float(r.get("__score") or 0), reverse=True)
        return candidates[: int(request.max_neighbor_edges)]

    # Fetch top neighbor edges for both endpoints.
    neighbor_rows_a = (
        await _get_neighbor_rows(source_id, target_id)
        if request.max_neighbor_edges
        else []
    )
    neighbor_rows_b = (
        await _get_neighbor_rows(target_id, source_id)
        if request.max_neighbor_edges
        else []
    )
    neighbor_rows = neighbor_rows_a + neighbor_rows_b

    neighbor_memory_ids: list[str] = []
    seen_neighbor_mem: set[str] = set()
    for row in neighbor_rows:
        mid = row.get("source_memory_id")
        if not isinstance(mid, str) or not mid:
            continue
        if mid in seen_neighbor_mem:
            continue
        seen_neighbor_mem.add(mid)
        neighbor_memory_ids.append(mid)
        if len(neighbor_memory_ids) >= int(request.max_neighbor_memories):
            break

    # Fetch entity labels for prompt readability.
    entity_ids: set[str] = {source_id, target_id}
    for row in neighbor_rows:
        s = str(row.get("source_entity_id") or "")
        t = str(row.get("target_entity_id") or "")
        if s:
            entity_ids.add(s)
        if t:
            entity_ids.add(t)

    entity_meta: dict[str, dict[str, Any]] = {}
    try:
        ent_resp = await supabase._exec(
            lambda: supabase.client.table("memory_entities")
            .select("id,entity_type,display_label,entity_name")
            .in_("id", list(entity_ids))
            .execute()
        )
        for row in list(ent_resp.data or []):
            eid = str(row.get("id"))
            if eid:
                entity_meta[eid] = row
    except Exception:
        entity_meta = {}

    all_memory_ids = list(dict.fromkeys([*direct_memory_ids, *neighbor_memory_ids]))
    mem_by_id: dict[str, dict[str, Any]] = {}
    if all_memory_ids:
        try:
            mem_resp = await supabase._exec(
                lambda: supabase.client.table("memories")
                .select("id,content,metadata,confidence_score,created_at")
                .in_("id", all_memory_ids)
                .execute()
            )
            for row in list(mem_resp.data or []):
                mid = str(row.get("id"))
                if mid:
                    mem_by_id[mid] = row
        except Exception:
            mem_by_id = {}

    def label_for_entity(eid: str) -> str:
        meta = entity_meta.get(eid) or {}
        return str(meta.get("display_label") or meta.get("entity_name") or eid)

    def type_for_entity(eid: str) -> str:
        meta = entity_meta.get(eid) or {}
        return str(meta.get("entity_type") or "")

    # Heuristic summary fallback.
    def build_heuristic_markdown() -> str:
        pair_types: dict[str, int] = {}
        for row in edge_rows:
            rtype = row.get("relationship_type")
            if not isinstance(rtype, str) or not rtype:
                continue
            occ = row.get("occurrence_count")
            pair_types[rtype] = pair_types.get(rtype, 0) + (
                int(occ) if isinstance(occ, int) else 1
            )

        lines: list[str] = []
        lines.append("# Relationship analysis (heuristic)")
        lines.append("")
        lines.append(
            f"**Entity A:** {label_for_entity(source_id)} ({type_for_entity(source_id) or 'unknown'})"
        )
        lines.append(
            f"**Entity B:** {label_for_entity(target_id)} ({type_for_entity(target_id) or 'unknown'})"
        )
        lines.append("")
        if pair_types:
            lines.append("## Observed relationship types (from existing rows)")
            for k, v in sorted(pair_types.items(), key=lambda it: it[1], reverse=True):
                lines.append(f"- `{k}` · {v} memories")
        else:
            lines.append("## Observed relationship types")
            lines.append("- No relationship_type values found for this pair yet.")

        if direct_memory_ids:
            lines.append("")
            lines.append("## Direct evidence (memory excerpts)")
            for mid in direct_memory_ids[: min(10, len(direct_memory_ids))]:
                content = str((mem_by_id.get(mid) or {}).get("content") or "")
                lines.append(f"- `{mid}`: {_truncate(content, 240)}")

        if neighbor_rows:
            lines.append("")
            lines.append("## Neighbor edges (strongest connections)")
            for row in neighbor_rows[: min(12, len(neighbor_rows))]:
                s = str(row.get("source_entity_id") or "")
                t = str(row.get("target_entity_id") or "")
                rtype = str(row.get("relationship_type") or "")
                w = row.get("weight")
                oc = row.get("occurrence_count")
                lines.append(
                    f"- `{label_for_entity(s)}` → `{label_for_entity(t)}` · `{rtype}` · w={w} · occ={oc}"
                )

        lines.append("")
        lines.append("## Recommended next steps")
        lines.append(
            "- Use **Split (Preview)** to explore whether this edge should be split into multiple relationship types."
        )
        lines.append("- Use **Show Evidence** to review shared memories for this pair.")
        lines.append(
            "- Use **Merge relationships** if multiple rows represent the same semantic relationship."
        )
        return "\n".join(lines)

    def build_heuristic_checklist() -> list[RelationshipChecklistItem]:
        evidence_ids: list[UUID] = []
        for mid in direct_memory_ids[:8]:
            try:
                evidence_ids.append(UUID(str(mid)))
            except Exception:
                continue

        entity_ids: list[UUID] = []
        try:
            entity_ids = [UUID(source_id), UUID(target_id)]
        except Exception:
            entity_ids = []

        return [
            RelationshipChecklistItem(
                id="review-evidence",
                title="I reviewed the direct evidence memories for this pair",
                category="evidence",
                why="Confirms this relationship is grounded in actual memories.",
                memory_ids=evidence_ids,
                entity_ids=entity_ids,
            ),
            RelationshipChecklistItem(
                id="confirm-type",
                title="The relationship type matches the evidence",
                category="type",
                why="Prevents mislabeling (e.g., RELATED_TO vs REQUIRES).",
                entity_ids=entity_ids,
            ),
            RelationshipChecklistItem(
                id="confirm-direction",
                title="The direction (A→B vs B→A) is correct",
                category="direction",
                why="Keeps causality/ownership relationships consistent.",
                entity_ids=entity_ids,
            ),
            RelationshipChecklistItem(
                id="resolve-hygiene",
                title="I resolved obvious duplicates/outdated memories affecting this relationship",
                category="hygiene",
                why="Improves signal quality and reduces noisy edges.",
            ),
            RelationshipChecklistItem(
                id="decide-split-merge",
                title="I decided whether this should be kept, merged, or split into multiple relationships",
                category="scope",
                why="Splitting broad edges can improve retrieval precision.",
                entity_ids=entity_ids,
            ),
        ]

    used_ai = False
    ai_model_id: str | None = None
    ai_error: str | None = None

    if request.use_ai and not settings.gemini_api_key:
        ai_error = "AI analysis unavailable: missing GEMINI_API_KEY / GOOGLE_API_KEY."

    analysis_markdown = build_heuristic_markdown()
    checklist: list[RelationshipChecklistItem] = build_heuristic_checklist()
    actions: list[RelationshipSuggestedAction] = []

    if request.use_ai and settings.gemini_api_key:
        try:
            from app.agents.unified.provider_factory import build_chat_model
            from app.core.config import get_registry

            registry = get_registry()
            ai_model_id = getattr(
                registry, "memory_relationship_analysis", registry.coordinator_google
            ).id

            response_schema = {
                "type": "object",
                "properties": {
                    "analysis_markdown": {"type": "string"},
                    "checklist": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "category": {
                                    "type": "string",
                                    "enum": [
                                        "evidence",
                                        "type",
                                        "direction",
                                        "entities",
                                        "hygiene",
                                        "scope",
                                        "merge",
                                        "split",
                                        "other",
                                    ],
                                },
                                "why": {"type": "string"},
                                "memory_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "entity_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["id", "title", "category"],
                            "additionalProperties": False,
                        },
                    },
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "kind": {
                                    "type": "string",
                                    "enum": [
                                        "update_relationship",
                                        "merge_relationships",
                                        "split_relationship_commit",
                                        "update_memory",
                                        "delete_memory",
                                        "merge_memories_arbitrary",
                                        "delete_relationship",
                                    ],
                                },
                                "confidence": {"type": "number"},
                                "destructive": {"type": "boolean"},
                                "payload": {"type": "object"},
                                "memory_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "entity_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "relationship_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["id", "title", "kind", "payload"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["analysis_markdown", "checklist"],
                "additionalProperties": False,
            }

            llm_base = build_chat_model(
                provider="google",
                model=ai_model_id,
                role="memory_relationship_analysis",
            )
            # Keep UI interactions responsive: avoid long exponential retries that can
            # trigger upstream timeouts (Next.js proxy / Railway / etc.).
            # We still fall back to heuristic analysis when AI is unavailable.
            try:
                # langchain_google_genai uses `max_retries` + `timeout`.
                # Use model_copy when available so we don't mutate shared instances.
                llm_base = llm_base.model_copy(  # type: ignore[attr-defined]
                    update={"max_retries": 1, "timeout": 24.0}
                )
            except Exception:
                # Best-effort: not all BaseChatModel implementations are pydantic models.
                for attr, value in (("max_retries", 1), ("timeout", 24.0)):
                    if hasattr(llm_base, attr):
                        try:
                            setattr(llm_base, attr, value)
                        except Exception:
                            pass

            llm = llm_base.bind(
                response_mime_type="application/json",
                response_schema=response_schema,
            )

            a_label = label_for_entity(source_id)
            b_label = label_for_entity(target_id)
            a_type = type_for_entity(source_id) or "unknown"
            b_type = type_for_entity(target_id) or "unknown"

            prompt_lines: list[str] = []
            prompt_lines.append(
                "You are an expert knowledge-graph relationship analyst."
            )
            prompt_lines.append(
                "Return STRICT JSON only. No markdown outside JSON. No commentary."
            )
            prompt_lines.append("The JSON MUST match the provided schema.")
            prompt_lines.append("Do NOT claim actions were executed. Only recommend.")
            prompt_lines.append(
                "Only reference entity IDs and memory IDs explicitly provided below; never invent IDs."
            )
            prompt_lines.append("")
            prompt_lines.append("## Task")
            prompt_lines.append(
                "Analyze the relationship between Entity A and Entity B. Recommend whether to keep as-is, edit, merge, or split."
            )
            prompt_lines.append(
                "Also suggest any memory hygiene actions (e.g., possible duplicate memories to merge) based on the evidence."
            )
            prompt_lines.append("")
            prompt_lines.append(
                f"Entity A: id={source_id}, type={a_type}, label={a_label!r}"
            )
            prompt_lines.append(
                f"Entity B: id={target_id}, type={b_type}, label={b_label!r}"
            )
            prompt_lines.append("")
            prompt_lines.append(
                "### Existing relationship rows for the pair (may include multiple types/directions)"
            )
            if edge_rows:
                for row in edge_rows[:50]:
                    rid = row.get("id")
                    rtype = row.get("relationship_type")
                    w = row.get("weight")
                    oc = row.get("occurrence_count")
                    s = row.get("source_entity_id")
                    t = row.get("target_entity_id")
                    ack = row.get("acknowledged_at")
                    mod = row.get("last_modified_at")
                    prompt_lines.append(
                        f"- relationship_id={rid} source={s} target={t} type={rtype} weight={w} occ={oc} acknowledged_at={ack} last_modified_at={mod}"
                    )
            else:
                prompt_lines.append("- (none)")

            prompt_lines.append("")
            prompt_lines.append("### Direct provenance memories (A↔B evidence)")
            direct_for_ai = direct_memory_ids[:12]
            for mid in direct_for_ai:
                row = mem_by_id.get(mid) or {}
                content = _truncate(str(row.get("content") or ""), 280)
                conf = row.get("confidence_score")
                created_at = row.get("created_at")
                prompt_lines.append(
                    f"- memory_id={mid} confidence={conf} created_at={created_at}\n  content: {content!r}"
                )
            if len(direct_memory_ids) > len(direct_for_ai):
                prompt_lines.append(
                    f"- (omitted {len(direct_memory_ids) - len(direct_for_ai)} additional direct memories)"
                )

            prompt_lines.append("")
            prompt_lines.append(
                "### Top neighbor edges (context only; do not expand beyond this list)"
            )
            if neighbor_rows:
                for row in neighbor_rows[:50]:
                    rid = row.get("id")
                    s = str(row.get("source_entity_id") or "")
                    t = str(row.get("target_entity_id") or "")
                    rtype = str(row.get("relationship_type") or "")
                    w = row.get("weight")
                    oc = row.get("occurrence_count")
                    prompt_lines.append(
                        f"- relationship_id={rid} {label_for_entity(s)!r} ({type_for_entity(s) or 'unknown'}) → {label_for_entity(t)!r} ({type_for_entity(t) or 'unknown'})"
                        f" type={rtype} weight={w} occ={oc}"
                    )
            else:
                prompt_lines.append("- (none)")

            prompt_lines.append("")
            prompt_lines.append("### Neighbor-edge memories (context excerpts)")
            neighbor_for_ai = neighbor_memory_ids[:10]
            for mid in neighbor_for_ai:
                row = mem_by_id.get(mid) or {}
                content = _truncate(str(row.get("content") or ""), 320)
                conf = row.get("confidence_score")
                prompt_lines.append(
                    f"- memory_id={mid} confidence={conf}\n  content: {content!r}"
                )
            if len(neighbor_memory_ids) > len(neighbor_for_ai):
                prompt_lines.append(
                    f"- (omitted {len(neighbor_memory_ids) - len(neighbor_for_ai)} additional neighbor memories)"
                )

            prompt_lines.append("")
            prompt_lines.append("## Output JSON")
            prompt_lines.append("Return JSON with:")
            prompt_lines.append(
                "- analysis_markdown: a Markdown artifact with sections:"
            )
            prompt_lines.append("  1) TL;DR (3 bullets max)")
            prompt_lines.append("  2) What the evidence suggests")
            prompt_lines.append(
                "  3) Recommended actions (table with Action | Target | Why | Confidence)"
            )
            prompt_lines.append("  4) Split plan (only if you recommend split)")
            prompt_lines.append(
                "  5) Memory hygiene suggestions (possible merges/edits; reference memory_id)"
            )
            prompt_lines.append("  6) Human review checklist")
            prompt_lines.append(
                "- checklist: 5-9 checkbox items that a human can mark as they complete review."
            )
            prompt_lines.append(
                "- actions: 3-10 suggested executable actions (or [] if none)."
            )
            prompt_lines.append("Action schema:")
            prompt_lines.append("- id: kebab-case stable label (no random numbers)")
            prompt_lines.append(
                "- title: human-friendly checkbox label (start with a verb)"
            )
            prompt_lines.append("- kind: one of:")
            prompt_lines.append(
                "  update_relationship | merge_relationships | split_relationship_commit | "
                "update_memory | delete_memory | merge_memories_arbitrary | delete_relationship"
            )
            prompt_lines.append("- confidence: number 0-1")
            prompt_lines.append("- destructive: true for delete/merge/split commits")
            prompt_lines.append("- payload depends on kind:")
            prompt_lines.append("  * update_relationship payload:")
            prompt_lines.append(
                '    {"relationship_id":"...","source_entity_id":"...","target_entity_id":"...",'
                '"relationship_type":"RELATED_TO","weight":4.2}'
            )
            prompt_lines.append("  * merge_relationships payload:")
            prompt_lines.append(
                '    {"relationship_ids":["...","..."],"source_entity_id":"...","target_entity_id":"...",'
                '"relationship_type":"RELATED_TO","weight":4.2}'
            )
            prompt_lines.append("  * split_relationship_commit payload:")
            prompt_lines.append(
                '    {"relationship_id":"...","clusters":[{"name":"...","source_entity_id":"...","target_entity_id":"...",'
                '"relationship_type":"RELATED_TO","weight":4.2,"memory_ids":["..."]}]}'
            )
            prompt_lines.append("  * update_memory payload:")
            prompt_lines.append('    {"memory_id":"...","content":"...","metadata":{}}')
            prompt_lines.append("  * delete_memory payload:")
            prompt_lines.append('    {"memory_id":"..."}')
            prompt_lines.append("  * merge_memories_arbitrary payload:")
            prompt_lines.append(
                '    {"keep_memory_id":"...","merge_memory_ids":["...","..."],"merge_content":"..."}'
            )
            prompt_lines.append("  * delete_relationship payload:")
            prompt_lines.append('    {"relationship_id":"..."}')
            prompt_lines.append("Checklist guidelines:")
            prompt_lines.append(
                "- Use short, human-friendly titles that start with a verb (e.g., “Reviewed…”, “Confirmed…”)"
            )
            prompt_lines.append(
                "- category must be one of: evidence, type, direction, entities, hygiene, scope, merge, split, other"
            )
            prompt_lines.append(
                "- id should be kebab-case and stable (no random numbers)"
            )
            prompt_lines.append(
                "- If a checklist item references specific evidence, include memory_ids (0-6) from the provided memory_id list"
            )
            prompt_lines.append(
                "- If a checklist item requires inspecting nodes, include entity_ids (0-4) from the provided entity IDs"
            )
            prompt_lines.append(
                "- Use empty arrays or omit memory_ids/entity_ids when not applicable"
            )
            prompt_lines.append("")
            prompt_lines.append(
                'Output JSON only: {"analysis_markdown":"...","checklist":[...],"actions":[...]}'
            )

            prompt_text = "\n".join(prompt_lines)
            response = await asyncio.wait_for(llm.ainvoke(prompt_text), timeout=28.0)
            raw_text = _llm_content_to_text(getattr(response, "content", ""))
            data = _load_llm_json(raw_text)
            if not isinstance(data, dict):
                raise ValueError("LLM returned invalid JSON for relationship analysis")

            next_markdown = data.get("analysis_markdown")
            if not isinstance(next_markdown, str) or not next_markdown.strip():
                raise ValueError("LLM returned empty analysis_markdown")

            next_checklist_raw = data.get("checklist")
            next_checklist: list[RelationshipChecklistItem] = []
            if isinstance(next_checklist_raw, list):
                for item in next_checklist_raw:
                    if not isinstance(item, dict):
                        continue
                    cid = item.get("id")
                    title = item.get("title")
                    category = item.get("category")
                    if not isinstance(cid, str) or not cid.strip():
                        continue
                    if not isinstance(title, str) or not title.strip():
                        continue
                    if not isinstance(category, str) or not category.strip():
                        continue

                    why = item.get("why")
                    why_str = (
                        why.strip() if isinstance(why, str) and why.strip() else None
                    )

                    memory_ids: list[UUID] = []
                    raw_memory_ids = item.get("memory_ids")
                    if isinstance(raw_memory_ids, list):
                        for mid in raw_memory_ids:
                            if not isinstance(mid, str) or not mid.strip():
                                continue
                            try:
                                memory_ids.append(UUID(mid.strip()))
                            except Exception:
                                continue
                            if len(memory_ids) >= 6:
                                break

                    checklist_entity_ids: list[UUID] = []
                    raw_entity_ids = item.get("entity_ids")
                    if isinstance(raw_entity_ids, list):
                        for eid in raw_entity_ids:
                            if not isinstance(eid, str) or not eid.strip():
                                continue
                            try:
                                checklist_entity_ids.append(UUID(eid.strip()))
                            except Exception:
                                continue
                            if len(checklist_entity_ids) >= 4:
                                break

                    next_checklist.append(
                        RelationshipChecklistItem(
                            id=_truncate(cid.strip(), 64),
                            title=_truncate(title.strip(), 140),
                            category=_truncate(category.strip(), 32),
                            why=_truncate(why_str, 420) if why_str else None,
                            memory_ids=memory_ids,
                            entity_ids=checklist_entity_ids,
                        )
                    )

            analysis_markdown = next_markdown.strip()
            checklist = next_checklist[:9] if next_checklist else checklist

            allowed_kinds = {
                "update_relationship",
                "merge_relationships",
                "split_relationship_commit",
                "update_memory",
                "delete_memory",
                "merge_memories_arbitrary",
                "delete_relationship",
            }

            allowed_relationship_ids: set[str] = set()
            for row in edge_rows:
                rid = row.get("id")
                if rid is None:
                    continue
                rid_str = str(rid).strip()
                if rid_str:
                    allowed_relationship_ids.add(rid_str)

            allowed_memory_ids = {
                mid for mid in all_memory_ids if isinstance(mid, str) and mid
            }
            allowed_entity_ids = {
                eid for eid in entity_ids if isinstance(eid, str) and eid
            }
            allowed_pair = {source_id, target_id}

            def _to_uuid(value: Any) -> UUID | None:
                if not isinstance(value, str) or not value.strip():
                    return None
                try:
                    return UUID(value.strip())
                except Exception:
                    return None

            def _uuid_list(raw: Any, limit: int) -> list[UUID]:
                out: list[UUID] = []
                if not isinstance(raw, list):
                    return out
                for item in raw:
                    u = _to_uuid(item)
                    if not u:
                        continue
                    out.append(u)
                    if len(out) >= limit:
                        break
                return out

            def _sanitize_action_payload(
                kind: str, payload: dict[str, Any]
            ) -> dict[str, Any] | None:
                if kind == "update_relationship":
                    rid = _to_uuid(payload.get("relationship_id"))
                    if not rid or str(rid) not in allowed_relationship_ids:
                        return None
                    sid = _to_uuid(payload.get("source_entity_id"))
                    tid = _to_uuid(payload.get("target_entity_id"))
                    if not sid or not tid or {str(sid), str(tid)} != allowed_pair:
                        return None
                    rtype = payload.get("relationship_type")
                    if not isinstance(rtype, str) or rtype.strip() not in {
                        rt.value for rt in RelationshipType
                    }:
                        return None
                    weight = payload.get("weight")
                    if not isinstance(weight, (int, float)):
                        return None
                    return {
                        "relationship_id": str(rid),
                        "source_entity_id": str(sid),
                        "target_entity_id": str(tid),
                        "relationship_type": rtype.strip(),
                        "weight": float(max(0.0, min(10.0, weight))),
                    }

                if kind == "merge_relationships":
                    rel_ids = _uuid_list(payload.get("relationship_ids"), 12)
                    rel_ids = list(dict.fromkeys(rel_ids))
                    if len(rel_ids) < 2:
                        return None
                    if any(str(rid) not in allowed_relationship_ids for rid in rel_ids):
                        return None
                    sid = _to_uuid(payload.get("source_entity_id"))
                    tid = _to_uuid(payload.get("target_entity_id"))
                    if not sid or not tid or {str(sid), str(tid)} != allowed_pair:
                        return None
                    rtype = payload.get("relationship_type")
                    if not isinstance(rtype, str) or rtype.strip() not in {
                        rt.value for rt in RelationshipType
                    }:
                        return None
                    weight = payload.get("weight")
                    if not isinstance(weight, (int, float)):
                        return None
                    return {
                        "relationship_ids": [str(rid) for rid in rel_ids],
                        "source_entity_id": str(sid),
                        "target_entity_id": str(tid),
                        "relationship_type": rtype.strip(),
                        "weight": float(max(0.0, min(10.0, weight))),
                    }

                if kind == "delete_relationship":
                    rid = _to_uuid(payload.get("relationship_id"))
                    if not rid or str(rid) not in allowed_relationship_ids:
                        return None
                    return {"relationship_id": str(rid)}

                if kind == "update_memory":
                    mid = _to_uuid(payload.get("memory_id"))
                    if not mid or str(mid) not in allowed_memory_ids:
                        return None
                    content = payload.get("content")
                    metadata = payload.get("metadata")
                    next_payload: dict[str, Any] = {"memory_id": str(mid)}
                    if isinstance(content, str) and content.strip():
                        next_payload["content"] = content.strip()
                    if isinstance(metadata, dict):
                        next_payload["metadata"] = metadata
                    if "content" not in next_payload and "metadata" not in next_payload:
                        return None
                    return next_payload

                if kind == "delete_memory":
                    mid = _to_uuid(payload.get("memory_id"))
                    if not mid or str(mid) not in allowed_memory_ids:
                        return None
                    return {"memory_id": str(mid)}

                if kind == "merge_memories_arbitrary":
                    keep_mid = _to_uuid(payload.get("keep_memory_id"))
                    if not keep_mid or str(keep_mid) not in allowed_memory_ids:
                        return None
                    merge_mids = _uuid_list(payload.get("merge_memory_ids"), 12)
                    merge_mids = [
                        mid for mid in dict.fromkeys(merge_mids) if mid != keep_mid
                    ]
                    if not merge_mids:
                        return None
                    if any(str(mid) not in allowed_memory_ids for mid in merge_mids):
                        return None
                    content = payload.get("merge_content")
                    merge_payload: dict[str, Any] = {
                        "keep_memory_id": str(keep_mid),
                        "merge_memory_ids": [str(mid) for mid in merge_mids],
                    }
                    if isinstance(content, str) and content.strip():
                        merge_payload["merge_content"] = content.strip()
                    return merge_payload

                if kind == "split_relationship_commit":
                    rid = _to_uuid(payload.get("relationship_id"))
                    if not rid or str(rid) not in allowed_relationship_ids:
                        return None
                    clusters = payload.get("clusters")
                    if not isinstance(clusters, list) or not clusters:
                        return None
                    out_clusters: list[dict[str, Any]] = []
                    for item in clusters[
                        : (
                            int(request.max_direct_memories)
                            if request.max_direct_memories
                            else 8
                        )
                    ]:
                        if not isinstance(item, dict):
                            continue
                        sid = _to_uuid(item.get("source_entity_id"))
                        tid = _to_uuid(item.get("target_entity_id"))
                        if not sid or not tid or {str(sid), str(tid)} != allowed_pair:
                            continue
                        rtype = item.get("relationship_type")
                        if not isinstance(rtype, str) or rtype.strip() not in {
                            rt.value for rt in RelationshipType
                        }:
                            continue
                        weight = item.get("weight")
                        if not isinstance(weight, (int, float)):
                            continue
                        mem_ids = _uuid_list(item.get("memory_ids"), 60)
                        mem_ids = [
                            mid
                            for mid in dict.fromkeys(mem_ids)
                            if str(mid) in allowed_memory_ids
                        ]
                        if not mem_ids:
                            continue
                        name = item.get("name")
                        out_clusters.append(
                            {
                                "name": (
                                    name.strip()
                                    if isinstance(name, str) and name.strip()
                                    else None
                                ),
                                "source_entity_id": str(sid),
                                "target_entity_id": str(tid),
                                "relationship_type": rtype.strip(),
                                "weight": float(max(0.0, min(10.0, weight))),
                                "memory_ids": [str(mid) for mid in mem_ids],
                            }
                        )
                    if not out_clusters:
                        return None
                    return {"relationship_id": str(rid), "clusters": out_clusters}

                return None

            next_actions_raw = data.get("actions")
            next_actions: list[RelationshipSuggestedAction] = []
            if isinstance(next_actions_raw, list):
                for item in next_actions_raw[:12]:
                    if not isinstance(item, dict):
                        continue
                    action_id = item.get("id")
                    title = item.get("title")
                    kind = item.get("kind")
                    payload = item.get("payload")
                    if not isinstance(action_id, str) or not action_id.strip():
                        continue
                    if not isinstance(title, str) or not title.strip():
                        continue
                    if not isinstance(kind, str) or kind.strip() not in allowed_kinds:
                        continue
                    if not isinstance(payload, dict):
                        continue

                    sanitized = _sanitize_action_payload(kind.strip(), payload)
                    if sanitized is None:
                        continue

                    confidence = item.get("confidence")
                    confidence_value = (
                        float(confidence)
                        if isinstance(confidence, (int, float))
                        else 0.6
                    )
                    confidence_value = float(max(0.0, min(1.0, confidence_value)))

                    destructive = item.get("destructive")
                    if isinstance(destructive, bool):
                        destructive_value = destructive
                    else:
                        destructive_value = kind.strip() in {
                            "delete_memory",
                            "merge_relationships",
                            "split_relationship_commit",
                            "merge_memories_arbitrary",
                            "delete_relationship",
                        }

                    memory_ids = _uuid_list(item.get("memory_ids"), 10)
                    memory_ids = [
                        mid for mid in memory_ids if str(mid) in allowed_memory_ids
                    ]
                    action_entity_ids = _uuid_list(item.get("entity_ids"), 10)
                    action_entity_ids = [
                        eid
                        for eid in action_entity_ids
                        if str(eid) in allowed_entity_ids
                    ]
                    relationship_ids = _uuid_list(item.get("relationship_ids"), 12)
                    relationship_ids = [
                        rid
                        for rid in relationship_ids
                        if str(rid) in allowed_relationship_ids
                    ]

                    next_actions.append(
                        RelationshipSuggestedAction(
                            id=_truncate(action_id.strip(), 64),
                            title=_truncate(title.strip(), 180),
                            kind=kind.strip(),  # type: ignore[arg-type]
                            confidence=confidence_value,
                            destructive=destructive_value,
                            payload=sanitized,
                            memory_ids=memory_ids,
                            entity_ids=action_entity_ids,
                            relationship_ids=relationship_ids,
                        )
                    )

            actions = next_actions[:10] if next_actions else actions
            used_ai = True
        except Exception as exc:
            logger.exception(
                "Relationship analysis failed",
                extra={"model_id": ai_model_id},
            )
            if isinstance(exc, asyncio.TimeoutError):
                ai_error = "AI analysis timed out. Falling back to heuristic analysis."
            else:
                message = str(exc).lower()
                if (
                    "quota" in message
                    or "rate" in message
                    or "resourceexhausted" in message
                ):
                    ai_error = "AI analysis unavailable (quota/rate-limited). Falling back to heuristic analysis."
                else:
                    ai_error = "AI analysis failed. Falling back to heuristic analysis."
            used_ai = False

    return RelationshipAnalysisResponse(
        relationship_id=relationship_id,
        source_entity_id=UUID(source_id),
        target_entity_id=UUID(target_id),
        checklist=checklist,
        analysis_markdown=analysis_markdown,
        used_ai=used_ai,
        ai_model_id=ai_model_id if used_ai else None,
        ai_error=ai_error,
        direct_memory_count=len(direct_memory_ids),
        neighbor_edge_count=len(neighbor_rows),
        neighbor_memory_count=len(neighbor_memory_ids),
        actions=actions,
    )


@router.post(
    "/relationships/{relationship_id:uuid}/split/commit",
    response_model=SplitRelationshipCommitResponse,
    summary="Commit relationship split (Admin only)",
    description=(
        "Commit a split preview by replacing the existing relationships between the "
        "two entities with the provided cluster relationships."
    ),
    responses={
        200: {"description": "Split committed successfully"},
        400: {"description": "Invalid request"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        404: {"description": "Relationship not found"},
        409: {"description": "Commit conflicts with existing data"},
        500: {"description": "Internal server error"},
    },
)
async def split_relationship_commit(
    relationship_id: UUID,
    request: SplitRelationshipCommitRequest,
    admin_user: Annotated[TokenPayload, Depends(require_admin)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> SplitRelationshipCommitResponse:
    supabase = service._get_supabase()

    rel_resp = await supabase._exec(
        lambda: supabase.client.table("memory_relationships")
        .select("id,source_entity_id,target_entity_id")
        .eq("id", str(relationship_id))
        .execute()
    )
    rel_rows = list(rel_resp.data or [])
    if not rel_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relationship {relationship_id} not found",
        )
    rel_row = rel_rows[0]

    source_id = str(rel_row.get("source_entity_id"))
    target_id = str(rel_row.get("target_entity_id"))
    allowed_pair = {source_id, target_id}

    # Deduplicate clusters by (source,target,type) and aggregate counts.
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    all_memory_ids: set[str] = set()
    for cluster in request.clusters:
        cid = str(cluster.source_entity_id)
        tid = str(cluster.target_entity_id)
        if {cid, tid} != allowed_pair:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Clusters must use the same entity pair as the relationship being split",
            )
        if cid == tid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cluster source_entity_id and target_entity_id must be different",
            )

        rtype = cluster.relationship_type.value
        key = (cid, tid, rtype)
        memory_ids = [str(mid) for mid in cluster.memory_ids]
        for mid in memory_ids:
            all_memory_ids.add(mid)

        if key not in deduped:
            deduped[key] = {
                "source_entity_id": cid,
                "target_entity_id": tid,
                "relationship_type": rtype,
                "weight": float(cluster.weight),
                "memory_ids": set(memory_ids),
                "name": cluster.name,
            }
            continue

        existing = deduped[key]
        existing["weight"] = max(float(existing["weight"]), float(cluster.weight))
        existing["memory_ids"].update(memory_ids)

    if not deduped:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="clusters must be non-empty",
        )

    # Validate memory IDs exist to avoid FK failures when setting source_memory_id.
    existing_memory_ids: set[str] = set()
    if all_memory_ids:
        try:
            mid_resp = await supabase._exec(
                lambda: supabase.client.table("memories")
                .select("id")
                .in_("id", list(all_memory_ids))
                .execute()
            )
            existing_memory_ids = {
                str(row.get("id")) for row in list(mid_resp.data or []) if row.get("id")
            }
        except Exception:
            existing_memory_ids = set()

    # Fetch and delete existing relationships between the entity pair.
    try:
        existing_rel_resp = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .select("id")
            .or_(
                f"and(source_entity_id.eq.{source_id},target_entity_id.eq.{target_id}),"
                f"and(source_entity_id.eq.{target_id},target_entity_id.eq.{source_id})"
            )
            .limit(5000)
            .execute()
        )
        to_delete = [
            str(row.get("id"))
            for row in list(existing_rel_resp.data or [])
            if row.get("id")
        ]
        if to_delete:
            await supabase._exec(
                lambda: supabase.client.table("memory_relationships")
                .delete()
                .in_("id", to_delete)
                .execute()
            )
    except Exception as exc:
        logger.exception("Error deleting relationships for split commit: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete existing relationships for split commit",
        )

    now_iso = datetime.now(timezone.utc).isoformat()

    payloads: list[dict[str, Any]] = []
    for key, entry in deduped.items():
        mids: set[str] = entry["memory_ids"]
        representative_mid = next(
            (mid for mid in mids if mid in existing_memory_ids), None
        )
        occurrence_count = max(1, len(mids))
        payloads.append(
            {
                "source_entity_id": entry["source_entity_id"],
                "target_entity_id": entry["target_entity_id"],
                "relationship_type": entry["relationship_type"],
                "weight": float(entry["weight"]),
                "occurrence_count": occurrence_count,
                "source_memory_id": representative_mid,
                # Any commit requires re-review.
                "acknowledged_at": None,
                "last_modified_at": now_iso,
            }
        )

    try:
        insert_resp = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .insert(payloads)
            .execute()
        )
        inserted_rows = list(insert_resp.data or [])
    except Exception as exc:
        logger.exception("Error inserting relationships for split commit: %s", exc)
        message = str(exc).lower()
        if "duplicate key" in message or "unique constraint" in message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Split commit conflicts with an existing relationship",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to commit relationship split",
        )

    return SplitRelationshipCommitResponse(
        source_entity_id=UUID(source_id),
        target_entity_id=UUID(target_id),
        deleted_relationship_ids=(
            [UUID(v) for v in to_delete] if "to_delete" in locals() else []
        ),
        created_relationships=inserted_rows,  # type: ignore[arg-type]
    )


@router.post(
    "/entities/{entity_id:uuid}/acknowledge",
    response_model=MemoryEntityRecord,
    summary="Acknowledge entity",
    description="Mark an entity as reviewed (sets acknowledged_at). Requires authentication.",
    responses={
        200: {"description": "Entity acknowledged successfully"},
        401: {"description": "Authentication required"},
        404: {"description": "Entity not found"},
        500: {"description": "Internal server error"},
    },
)
async def acknowledge_entity(
    entity_id: UUID,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> MemoryEntityRecord:
    supabase = service._get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    payload: Dict[str, Any] = {"acknowledged_at": now_iso, "last_modified_at": now_iso}

    try:
        resp = await supabase._exec(
            lambda: supabase.client.table("memory_entities")
            .update(payload)
            .eq("id", str(entity_id))
            .execute()
        )
        rows = list(resp.data or [])
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Entity {entity_id} not found",
            )
        return rows[0]  # type: ignore[return-value]
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error acknowledging entity %s: %s", entity_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to acknowledge entity",
        )


@router.post(
    "/relationships/{relationship_id:uuid}/acknowledge",
    response_model=MemoryRelationshipRecord,
    summary="Acknowledge relationship",
    description="Mark a relationship as reviewed (sets acknowledged_at). Requires authentication.",
    responses={
        200: {"description": "Relationship acknowledged successfully"},
        401: {"description": "Authentication required"},
        404: {"description": "Relationship not found"},
        500: {"description": "Internal server error"},
    },
)
async def acknowledge_relationship(
    relationship_id: UUID,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> MemoryRelationshipRecord:
    supabase = service._get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    payload: Dict[str, Any] = {"acknowledged_at": now_iso, "last_modified_at": now_iso}

    try:
        resp = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .update(payload)
            .eq("id", str(relationship_id))
            .execute()
        )
        rows = list(resp.data or [])
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Relationship {relationship_id} not found",
            )
        return rows[0]  # type: ignore[return-value]
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Error acknowledging relationship %s: %s", relationship_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to acknowledge relationship",
        )


@router.get(
    "/entities/{entity_id}/memories",
    response_model=List[MemoryRecord],
    summary="List memories related to an entity",
    description=(
        "Find memories associated with an extracted entity, using relationship provenance "
        "(memory_relationships.source_memory_id). Requires authentication."
    ),
)
async def list_memories_for_entity(
    entity_id: UUID,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
    limit: int = Query(default=20, ge=1, le=200),
) -> List[MemoryRecord]:
    supabase = service._get_supabase()

    try:
        # Pull a larger slice of relationships so we can dedupe memory IDs while preserving recency.
        rel_resp = await supabase._exec(
            lambda: supabase.client.table("memory_relationships")
            .select("source_memory_id,last_seen_at")
            .or_(f"source_entity_id.eq.{entity_id},target_entity_id.eq.{entity_id}")
            .not_.is_("source_memory_id", "null")
            .order("last_seen_at", desc=True)
            .limit(1000)
            .execute()
        )

        memory_ids: list[str] = []
        seen: set[str] = set()
        for row in list(rel_resp.data or []):
            mid = row.get("source_memory_id")
            if not isinstance(mid, str) or not mid:
                continue
            if mid in seen:
                continue
            seen.add(mid)
            memory_ids.append(mid)
            if len(memory_ids) >= int(limit):
                break

        if not memory_ids:
            return []

        mem_resp = await supabase._exec(
            lambda: supabase.client.table("memories")
            .select(service.MEMORY_SELECT_COLUMNS)
            .in_("id", memory_ids)
            .execute()
        )
        mem_rows = list(mem_resp.data or [])
        mem_map: dict[str, dict[str, Any]] = {
            str(m.get("id")): m for m in mem_rows if m.get("id")
        }

        # Preserve the relationship-derived order.
        ordered = [mem_map[mid] for mid in memory_ids if mid in mem_map]
        return ordered  # type: ignore[return-value]

    except Exception as exc:
        logger.exception(
            "Error listing related memories for entity %s: %s", entity_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list related memories for entity",
        )


@router.get(
    "/duplicates",
    response_model=List[DuplicateCandidateRecord],
    summary="List duplicate candidates",
    description="List duplicate candidates for review (optionally expanded with memory records). Requires authentication.",
)
async def list_duplicate_candidates(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
    status_filter: str = Query(default="pending", alias="status"),
    limit: int = Query(default=20, ge=1, le=200),
) -> List[DuplicateCandidateRecord]:
    supabase = service._get_supabase()

    try:
        q = (
            supabase.client.table("memory_duplicate_candidates")
            .select("*")
            .order("similarity_score", desc=True)
            .limit(int(limit))
        )

        if status_filter == "pending":
            q = q.eq("status", "pending")

        resp = await supabase._exec(lambda: q.execute())
        candidates: list[dict[str, Any]] = list(resp.data or [])

        memory_ids: set[str] = set()
        for cand in candidates:
            m1 = cand.get("memory_id_1")
            m2 = cand.get("memory_id_2")
            if isinstance(m1, str) and m1:
                memory_ids.add(m1)
            if isinstance(m2, str) and m2:
                memory_ids.add(m2)

        if memory_ids:
            mem_resp = await supabase._exec(
                lambda: supabase.client.table("memories")
                .select(service.MEMORY_SELECT_COLUMNS)
                .in_("id", list(memory_ids))
                .execute()
            )
            mem_rows = list(mem_resp.data or [])
            mem_map: dict[str, dict[str, Any]] = {
                str(m.get("id")): m for m in mem_rows if m.get("id")
            }

            for cand in candidates:
                m1 = cand.get("memory_id_1")
                m2 = cand.get("memory_id_2")
                if isinstance(m1, str):
                    cand["memory1"] = mem_map.get(m1)
                if isinstance(m2, str):
                    cand["memory2"] = mem_map.get(m2)

        return candidates  # type: ignore[return-value]
    except Exception as exc:
        logger.exception("Error listing duplicate candidates: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list duplicate candidates",
        )


@router.post(
    "/add",
    response_model=AddMemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add new memory",
    description="Add a new memory entry to the system. Requires authentication.",
    responses={
        201: {"description": "Memory created successfully"},
        400: {"description": "Invalid request data"},
        401: {"description": "Authentication required"},
        500: {"description": "Internal server error"},
    },
)
async def add_memory(
    request: AddMemoryRequest,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> AddMemoryResponse:
    """
    Add a new memory entry with automatic embedding generation.

    The memory content will be embedded using Gemini embeddings (3072-dim)
    for semantic search. Entities and relationships may be automatically
    extracted from the content.
    """
    try:
        result = await service.add_memory(
            content=request.content,
            metadata=request.metadata or {},
            source_type=request.source_type,
            agent_id=request.agent_id,
            tenant_id=request.tenant_id,
        )

        # Extract the memory ID from result
        memory_id = result.get("id")
        memory_uuid: UUID | None = None
        if isinstance(memory_id, UUID):
            memory_uuid = memory_id
        elif isinstance(memory_id, str):
            try:
                memory_uuid = UUID(memory_id)
            except ValueError:
                memory_uuid = None
        if memory_uuid is None:
            logger.error("Add memory returned invalid id: %s", memory_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create memory",
            )
        created_at = result.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        elif created_at is None:
            created_at = datetime.now(timezone.utc)

        # Best-effort duplicate detection (async, non-blocking)
        try:

            async def _run_duplicate_detection() -> None:
                try:
                    await service.detect_duplicates(memory_uuid)
                except Exception as exc:
                    logger.warning(
                        "Duplicate detection failed for memory %s: %s", memory_uuid, exc
                    )

            asyncio.create_task(_run_duplicate_detection())
        except Exception as exc:
            logger.warning("Failed to schedule duplicate detection: %s", exc)

        return AddMemoryResponse(
            id=memory_uuid,
            content=result.get("content", request.content),
            confidence_score=result.get("confidence_score", 0.5),
            source_type=result.get("source_type", request.source_type),
            entities_extracted=result.get("entities_extracted", 0),
            relationships_created=result.get("relationships_created", 0),
            created_at=created_at,
        )

    except ValueError as e:
        logger.warning(f"Invalid add memory request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error adding memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add memory",
        )


@router.get(
    "/{memory_id:uuid}",
    response_model=MemoryRecord,
    summary="Get memory by ID",
    description="Get a single memory record by ID. Requires authentication.",
    responses={
        200: {"description": "Memory retrieved successfully"},
        401: {"description": "Authentication required"},
        404: {"description": "Memory not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_memory_by_id(
    memory_id: UUID,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> MemoryRecord:
    try:
        existing = await service.get_memory_by_id(memory_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory {memory_id} not found",
            )
        return existing  # type: ignore[return-value]
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error retrieving memory %s: %s", memory_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve memory",
        )


@router.put(
    "/{memory_id:uuid}",
    response_model=UpdateMemoryResponse,
    summary="Update memory (Admin only)",
    description="Update an existing memory entry. Requires admin privileges.",
    responses={
        200: {"description": "Memory updated successfully"},
        400: {"description": "Invalid request data"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        404: {"description": "Memory not found"},
        500: {"description": "Internal server error"},
    },
)
async def update_memory(
    memory_id: UUID,
    request: UpdateMemoryRequest,
    admin_user: Annotated[TokenPayload, Depends(require_admin)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> UpdateMemoryResponse:
    """
    Update an existing memory entry.

    Admin only endpoint for modifying memory content or metadata.
    If content is changed, the embedding will be regenerated.
    """
    if request.content is None and request.metadata is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of 'content' or 'metadata' must be provided",
        )

    try:
        # Get the current memory to check if it exists
        existing = await service.get_memory_by_id(memory_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory {memory_id} not found",
            )

        # Use existing values if not provided
        content = (
            request.content
            if request.content is not None
            else existing.get("content", "")
        )
        metadata = (
            request.metadata
            if request.metadata is not None
            else existing.get("metadata", {})
        )

        result = await service.update_memory(
            memory_id=memory_id,
            content=content,
            metadata=metadata,
            reviewer_id=UUID(admin_user.sub) if admin_user.sub else None,
        )

        updated_at = result.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        elif updated_at is None:
            updated_at = datetime.now(timezone.utc)

        return UpdateMemoryResponse(
            id=memory_id,
            content=result.get("content", content),
            updated_at=updated_at,
        )

    except ValueError as e:
        logger.warning(f"Invalid update memory request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating memory {memory_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update memory",
        )


@router.delete(
    "/{memory_id:uuid}",
    response_model=DeleteMemoryResponse,
    summary="Delete memory (Admin only)",
    description="Delete a memory entry and its associated entities/relationships. Requires admin privileges.",
    responses={
        200: {"description": "Memory deleted successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        404: {"description": "Memory not found"},
        500: {"description": "Internal server error"},
    },
)
async def delete_memory(
    memory_id: UUID,
    admin_user: Annotated[TokenPayload, Depends(require_admin)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> DeleteMemoryResponse:
    """
    Delete a memory entry.

    Admin only endpoint for removing memories from the system.
    Also cleans up orphaned entities and relationships.
    """
    try:
        # Check if memory exists
        existing = await service.get_memory_by_id(memory_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory {memory_id} not found",
            )

        result = await service.delete_memory(memory_id=memory_id)

        return DeleteMemoryResponse(
            deleted=True,
            entities_orphaned=result.get("orphaned_entities_count", 0),
            relationships_removed=result.get("removed_relationships_count", 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting memory {memory_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete memory",
        )


@router.post(
    "/merge",
    response_model=MergeMemoriesResponse,
    summary="Merge duplicate memories (Admin only)",
    description="Merge duplicate memories into a single entry. Requires admin privileges.",
    responses={
        200: {"description": "Memories merged successfully"},
        400: {"description": "Invalid request data"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        404: {"description": "Memory or duplicate candidate not found"},
        500: {"description": "Internal server error"},
    },
)
async def merge_memories(
    request: MergeMemoriesRequest,
    admin_user: Annotated[TokenPayload, Depends(require_admin)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> MergeMemoriesResponse:
    """
    Merge duplicate memories into a primary memory.

    Admin only endpoint for deduplication. The kept memory absorbs
    the other memory's entities and the duplicate is deleted.
    If merged_content is provided, the embedding will be regenerated.
    """
    try:
        # Get the kept memory to get its ID for the duplicate
        kept_memory = await service.get_memory_by_id(request.keep_memory_id)
        if not kept_memory:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory {request.keep_memory_id} not found",
            )

        # Determine content to use
        content = (
            request.merge_content
            if request.merge_content
            else kept_memory.get("content", "")
        )

        result = await service.merge_memories(
            candidate_id=request.duplicate_candidate_id,
            keep_memory_id=request.keep_memory_id,
            reviewer_id=(
                UUID(admin_user.sub)
                if admin_user.sub
                else UUID("00000000-0000-0000-0000-000000000000")
            ),
            merged_content=content,
        )

        if isinstance(result, dict) and result.get("error"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(result["error"]),
            )

        # The result should contain the deleted memory ID from the candidate
        deleted_id = result.get("deleted_memory_id")
        if deleted_id is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Merge did not return deleted_memory_id",
            )

        return MergeMemoriesResponse(
            merged_memory_id=request.keep_memory_id,
            deleted_memory_id=(
                UUID(deleted_id) if isinstance(deleted_id, str) else deleted_id
            ),
            confidence_score=result.get("new_confidence", 0.6),
            entities_transferred=result.get("entities_transferred", 0),
        )

    except ValueError as e:
        logger.warning(f"Invalid merge request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error merging memories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to merge memories",
        )


@router.post(
    "/merge/arbitrary",
    response_model=MergeMemoriesArbitraryResponse,
    summary="Merge explicit memories (Admin only)",
    description=(
        "Merge an explicit list of memory IDs into a single kept memory. "
        "This creates temporary duplicate-candidate rows and reuses the existing merge RPC. "
        "Requires admin privileges."
    ),
    responses={
        200: {"description": "Memories merged successfully"},
        400: {"description": "Invalid request data"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        404: {"description": "Memory not found"},
        409: {"description": "Merge conflict"},
        500: {"description": "Internal server error"},
    },
)
async def merge_memories_arbitrary(
    request: MergeMemoriesArbitraryRequest,
    admin_user: Annotated[TokenPayload, Depends(require_admin)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> MergeMemoriesArbitraryResponse:
    supabase = service._get_supabase()

    kept_memory = await service.get_memory_by_id(request.keep_memory_id)
    if not kept_memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory {request.keep_memory_id} not found",
        )

    merge_ids = [
        mid for mid in request.merge_memory_ids if mid != request.keep_memory_id
    ]
    merge_ids = list(dict.fromkeys(merge_ids))
    if not merge_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="merge_memory_ids must contain at least one ID different from keep_memory_id",
        )

    content = (
        request.merge_content
        if request.merge_content
        else str(kept_memory.get("content") or "")
    )
    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="merge_content is empty and kept memory has no content",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    reviewer_id = (
        UUID(admin_user.sub)
        if admin_user.sub
        else UUID("00000000-0000-0000-0000-000000000000")
    )

    deleted_memory_ids: list[UUID] = []
    duplicate_candidate_ids: list[UUID] = []
    total_entities_transferred = 0
    confidence_score = 0.6

    for merge_id in merge_ids[:10]:
        candidate_id = uuid5(
            NAMESPACE_URL, f"manual-merge:{request.keep_memory_id}:{merge_id}"
        )
        candidate_id_to_use = candidate_id

        candidate_payload: dict[str, Any] = {
            "id": str(candidate_id),
            "memory_id_1": str(request.keep_memory_id),
            "memory_id_2": str(merge_id),
            "similarity_score": 1.0,
            "status": "pending",
            "reviewed_by": None,
            "reviewed_at": None,
            "merge_target_id": None,
            "detected_at": now_iso,
            "detection_method": "manual_merge",
            "notes": "Manual merge requested via Memory UI",
            "created_at": now_iso,
        }

        try:
            await supabase._exec(
                lambda: supabase.client.table("memory_duplicate_candidates")
                .upsert(candidate_payload, on_conflict="id")
                .execute()
            )
        except Exception as exc:
            message = str(exc).lower()
            if "duplicate key" in message or "unique constraint" in message:
                try:
                    existing_resp = await supabase._exec(
                        lambda: supabase.client.table("memory_duplicate_candidates")
                        .select("id")
                        .or_(
                            "and(memory_id_1.eq.{keep},memory_id_2.eq.{merge}),"
                            "and(memory_id_1.eq.{merge},memory_id_2.eq.{keep})".format(
                                keep=str(request.keep_memory_id),
                                merge=str(merge_id),
                            )
                        )
                        .order("detected_at", desc=True)
                        .limit(1)
                        .execute()
                    )
                    existing_rows = list(existing_resp.data or [])
                    if existing_rows and existing_rows[0].get("id"):
                        candidate_id_to_use = UUID(str(existing_rows[0]["id"]))
                        await supabase._exec(
                            lambda: supabase.client.table("memory_duplicate_candidates")
                            .update(
                                {
                                    "status": "pending",
                                    "reviewed_by": None,
                                    "reviewed_at": None,
                                    "merge_target_id": None,
                                    "similarity_score": 1.0,
                                    "detected_at": now_iso,
                                    "detection_method": "manual_merge",
                                    "notes": "Manual merge requested via Memory UI",
                                }
                            )
                            .eq("id", str(candidate_id_to_use))
                            .execute()
                        )
                    else:
                        raise ValueError("No existing merge candidate found")
                except Exception:
                    logger.exception("Error creating merge candidate: %s", exc)
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to create merge candidate",
                    )
            else:
                logger.exception("Error creating merge candidate: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create merge candidate",
                )

        duplicate_candidate_ids.append(candidate_id_to_use)

        result = await service.merge_memories(
            candidate_id=candidate_id_to_use,
            keep_memory_id=request.keep_memory_id,
            reviewer_id=reviewer_id,
            merged_content=content,
        )

        if isinstance(result, dict) and result.get("error"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(result["error"]),
            )

        deleted_id = result.get("deleted_memory_id")
        if deleted_id:
            try:
                deleted_memory_ids.append(UUID(str(deleted_id)))
            except Exception:
                pass

        transferred = result.get("entities_transferred")
        if isinstance(transferred, int):
            total_entities_transferred += transferred

        new_confidence = result.get("new_confidence")
        if isinstance(new_confidence, (int, float)):
            confidence_score = float(new_confidence)

    return MergeMemoriesArbitraryResponse(
        merged_memory_id=request.keep_memory_id,
        deleted_memory_ids=deleted_memory_ids,
        duplicate_candidate_ids=duplicate_candidate_ids,
        confidence_score=confidence_score,
        entities_transferred=total_entities_transferred,
    )


@router.post(
    "/{memory_id:uuid}/feedback",
    response_model=SubmitFeedbackResponse,
    summary="Submit feedback",
    description="Submit feedback on a memory entry. Requires authentication.",
    responses={
        200: {"description": "Feedback submitted successfully"},
        400: {"description": "Invalid feedback type"},
        401: {"description": "Authentication required"},
        404: {"description": "Memory not found"},
        500: {"description": "Internal server error"},
    },
)
async def submit_feedback(
    memory_id: UUID,
    request: SubmitFeedbackRequest,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> SubmitFeedbackResponse:
    """
    Submit feedback on a memory entry.

    Feedback affects the memory's confidence score:
    - **thumbs_up/resolution_success**: Increases confidence
    - **thumbs_down/resolution_failure**: Decreases confidence
    """
    try:
        # Verify memory exists
        existing = await service.get_memory_by_id(memory_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory {memory_id} not found",
            )

        result = await service.submit_feedback(
            memory_id=memory_id,
            user_id=(
                UUID(current_user.sub)
                if current_user.sub
                else UUID("00000000-0000-0000-0000-000000000000")
            ),
            feedback_type=request.feedback_type,
            session_id=request.session_id,
            ticket_id=request.ticket_id,
            notes=request.notes,
        )

        # Extract feedback ID from result
        feedback_id = result.get("feedback_id")
        if feedback_id and isinstance(feedback_id, str):
            feedback_id = UUID(feedback_id)

        return SubmitFeedbackResponse(
            feedback_id=feedback_id or UUID("00000000-0000-0000-0000-000000000000"),
            new_confidence_score=result.get(
                "new_confidence_score", result.get("new_confidence", 0.5)
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error submitting feedback for memory {memory_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit feedback",
        )


@router.post(
    "/export",
    response_model=ExportMemoriesResponse,
    summary="Export memories (Admin only)",
    description="Export memories to a downloadable JSON file. Requires admin privileges.",
    responses={
        200: {"description": "Export initiated successfully"},
        400: {"description": "Invalid export parameters"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        500: {"description": "Internal server error"},
    },
)
async def export_memories(
    request: ExportMemoriesRequest,
    admin_user: Annotated[TokenPayload, Depends(require_admin)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> ExportMemoriesResponse:
    """
    Export memories to a JSON file.

    Admin only endpoint for bulk memory export with optional filtering.
    Returns a download URL for the generated file.
    """
    try:
        import uuid as uuid_module
        from datetime import datetime, timezone

        # Build filter parameters from request
        source_type = None
        min_confidence = None
        created_after = None

        if request.filters:
            min_confidence = request.filters.min_confidence
            created_after = request.filters.created_after

        # Fetch memories with filters
        memories = await service.list_memories(
            source_type=source_type,
            limit=10000,  # Max export limit
            offset=0,
        )

        # Apply additional filters
        if min_confidence is not None:
            memories = [
                m for m in memories if m.get("confidence_score", 0) >= min_confidence
            ]
        if created_after is not None:
            memories = [
                m
                for m in memories
                if m.get("created_at")
                and datetime.fromisoformat(m["created_at"].replace("Z", "+00:00"))
                >= created_after
            ]

        # Generate export data
        export_id_str = str(uuid_module.uuid4())
        export_data = {
            "export_id": export_id_str,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "exported_by": admin_user.sub,
            "total_memories": len(memories),
            "memories": memories,
        }

        export_id = UUID(export_id_str)
        download_url = f"/api/v1/memory/exports/{export_id}/download"

        # Upload to Supabase Storage (admin-only bucket)
        supabase = service._get_supabase()

        try:
            await supabase._exec(
                lambda: supabase.client.storage.get_bucket(EXPORTS_BUCKET)
            )
        except Exception:
            await supabase._exec(
                lambda: supabase.client.storage.create_bucket(
                    EXPORTS_BUCKET,
                    options={"public": False},
                )
            )

        object_path = f"{export_id}.json"
        payload_bytes = json.dumps(export_data, ensure_ascii=False).encode("utf-8")

        await supabase._exec(
            lambda: supabase.client.storage.from_(EXPORTS_BUCKET).upload(
                object_path,
                payload_bytes,
                {
                    "content-type": "application/json",
                },
            )
        )

        # Use stats RPC for counts (filters are applied only to memory list for now)
        stats = await service.get_stats()
        if isinstance(stats, list) and stats:
            stats = stats[0]

        return ExportMemoriesResponse(
            export_id=export_id,
            download_url=download_url,
            memory_count=len(memories),
            entity_count=(
                stats.get("total_entities", 0) if isinstance(stats, dict) else 0
            ),
            relationship_count=(
                stats.get("total_relationships", 0) if isinstance(stats, dict) else 0
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error exporting memories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export memories",
        )


@router.post(
    "/duplicate/{candidate_id}/dismiss",
    response_model=DismissDuplicateResponse,
    summary="Dismiss duplicate candidate (Admin only)",
    description="Dismiss a duplicate memory candidate as not actually a duplicate. Requires admin privileges.",
    responses={
        200: {"description": "Duplicate candidate dismissed successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        404: {"description": "Duplicate candidate not found"},
        500: {"description": "Internal server error"},
    },
)
async def dismiss_duplicate(
    candidate_id: UUID,
    request: DismissDuplicateRequest,
    admin_user: Annotated[TokenPayload, Depends(require_admin)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> DismissDuplicateResponse:
    """
    Dismiss a duplicate candidate.

    Admin only endpoint for marking a duplicate candidate as dismissed
    (not actually a duplicate). This prevents it from appearing in
    future duplicate detection results.
    """
    try:
        result = await service.dismiss_duplicate(
            candidate_id=candidate_id,
            reviewer_id=(
                UUID(admin_user.sub)
                if admin_user.sub
                else UUID("00000000-0000-0000-0000-000000000000")
            ),
            notes=request.notes,
        )

        if isinstance(result, dict) and result.get("error"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(result["error"]),
            )

        return DismissDuplicateResponse(
            candidate_id=candidate_id,
            status=result.get("status", "dismissed"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error dismissing duplicate {candidate_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dismiss duplicate",
        )


@router.get(
    "/stats",
    response_model=MemoryStatsResponse,
    summary="Get memory statistics",
    description="Get aggregate statistics about the memory system. Requires authentication.",
    responses={
        200: {"description": "Statistics retrieved successfully"},
        401: {"description": "Authentication required"},
        500: {"description": "Internal server error"},
    },
)
async def get_memory_stats(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> MemoryStatsResponse:
    """
    Get memory system statistics.

    Returns aggregate statistics including:
    - Total counts (memories, entities, relationships)
    - Confidence distribution (high, medium, low)
    - Breakdowns by entity type and relationship type
    - Pending duplicate candidates count
    """
    try:
        result = await service.get_stats()

        # The service returns a dict; map to response schema
        # Handle both dict and RPC function return formats
        if isinstance(result, list) and result:
            result = result[0]

        return MemoryStatsResponse(
            total_memories=result.get("total_memories", 0),
            total_entities=result.get("total_entities", 0),
            total_relationships=result.get("total_relationships", 0),
            pending_duplicates=result.get("pending_duplicates", 0),
            high_confidence=result.get("high_confidence", 0),
            medium_confidence=result.get("medium_confidence", 0),
            low_confidence=result.get("low_confidence", 0),
            entity_types=result.get("entity_types", {}),
            relationship_types=result.get("relationship_types", {}),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting memory stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get memory statistics",
        )


@router.post(
    "/import",
    response_model=ImportMemorySourcesResponse,
    summary="Import existing knowledge sources (Admin only)",
    description=(
        "Backfill the Memory UI `memories` table from existing data sources "
        "(issue_resolutions + playbook_learned_entries) so admins can review/edit them."
    ),
    responses={
        200: {"description": "Import completed"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        500: {"description": "Internal server error"},
    },
)
async def import_memory_sources(
    request: ImportMemorySourcesRequest,
    admin_user: Annotated[TokenPayload, Depends(require_admin)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> ImportMemorySourcesResponse:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Memory import disabled. Use /api/v1/memory/import/zendesk-tagged instead.",
    )


@router.post(
    "/import/zendesk-tagged",
    response_model=ImportZendeskTaggedResponse,
    summary="Queue Zendesk tagged ticket import (Admin only)",
    description=(
        "Queue a background job to ingest solved/closed Zendesk tickets tagged for md_playbook "
        "learning into the Memory UI."
    ),
    responses={
        200: {"description": "Import queued"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        500: {"description": "Internal server error"},
    },
)
async def import_zendesk_tagged(
    request: ImportZendeskTaggedRequest,
    _admin_user: Annotated[TokenPayload, Depends(require_admin)],
) -> ImportZendeskTaggedResponse:
    try:
        supabase = get_supabase_client()
        if not getattr(supabase.config, "service_key", None):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Supabase service key required for Zendesk memory import.",
            )
        from app.feedme.tasks import import_zendesk_tagged as import_task

        task = import_task.delay(tag=request.tag, limit=request.limit)
        return ImportZendeskTaggedResponse(
            queued=True,
            task_id=getattr(task, "id", None),
            message="Zendesk import queued",
        )
    except Exception as exc:
        logger.exception("Failed to queue Zendesk import")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue Zendesk import",
        ) from exc


@router.get(
    "/exports/{export_id}/download",
    summary="Download memory export (Admin only)",
    description="Returns a short-lived signed URL to download a previously generated export.",
    responses={
        302: {"description": "Redirect to signed download URL"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin access required"},
        404: {"description": "Export not found"},
        500: {"description": "Internal server error"},
    },
)
async def download_export(
    export_id: UUID,
    admin_user: Annotated[TokenPayload, Depends(require_admin)],
    service: MemoryUIService = Depends(get_memory_ui_service),
) -> RedirectResponse:
    supabase = service._get_supabase()
    object_path = f"{export_id}.json"

    try:
        signed = await supabase._exec(
            lambda: supabase.client.storage.from_(EXPORTS_BUCKET).create_signed_url(
                object_path, 300
            )
        )
        signed_url = None
        if isinstance(signed, dict):
            signed_url = signed.get("signedURL") or signed.get("signedUrl")

        if not signed_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Export not found",
            )

        return RedirectResponse(url=signed_url, status_code=status.HTTP_302_FOUND)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error generating export download URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate export download URL",
        )
