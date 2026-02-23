"""
FeedMe Search Endpoints.

Implements frontend-facing search contracts for FeedMe workspace discovery.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import TokenPayload, get_current_user
from app.core.settings import settings

from .helpers import get_feedme_supabase_client

router = APIRouter(tags=["FeedMe"])


class SearchExamplesFilters(BaseModel):
    date_from: str | None = None
    date_to: str | None = None
    folder_ids: list[int] | None = None
    tags: list[str] | None = None
    min_confidence: float | None = None
    max_confidence: float | None = None
    platforms: list[str] | None = None
    status: list[str] | None = None
    min_quality_score: float | None = None
    max_quality_score: float | None = None
    issue_types: list[str] | None = None
    resolution_types: list[str] | None = None


class SearchExamplesRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    filters: SearchExamplesFilters | None = None
    include_snippets: bool = True
    highlight_matches: bool = True
    sort_by: str = "relevance"


class SearchExampleResult(BaseModel):
    id: int
    type: Literal["conversation", "example"] = "conversation"
    title: str
    snippet: str | None = None
    score: float
    conversation_id: int
    example_id: int | None = None
    folder_id: int | None = None
    folder_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    quality_score: float = 0.0
    issue_type: str | None = None
    resolution_type: str | None = None
    created_at: str
    updated_at: str


class SearchExamplesResponse(BaseModel):
    results: list[SearchExampleResult]
    total_count: int
    page: int
    page_size: int
    has_more: bool
    facets: dict[str, Any] | None = None


def _snippet(content: str, query_text: str, include_snippets: bool) -> str | None:
    if not include_snippets:
        return None
    if not content:
        return None

    lower_content = content.lower()
    lower_query = query_text.lower()
    idx = lower_content.find(lower_query)

    if idx < 0:
        return content[:220]

    start = max(0, idx - 80)
    end = min(len(content), idx + len(query_text) + 140)
    return content[start:end]


def _score(title: str, extracted_text: str, query_text: str, quality_score: float) -> float:
    score = 0.0
    lower_query = query_text.lower()
    if lower_query in (title or "").lower():
        score += 1.0
    if lower_query in (extracted_text or "").lower():
        score += 0.6
    if quality_score > 0:
        score += min(quality_score, 1.0) * 0.2
    return round(score, 4)


def _matches_metadata_filters(
    metadata: dict[str, Any],
    filters: SearchExamplesFilters | None,
    confidence_score: float,
) -> bool:
    if filters is None:
        return True

    tags = metadata.get("tags")
    normalized_tags = tags if isinstance(tags, list) else []
    issue_type = metadata.get("issue_type")
    resolution_type = metadata.get("resolution_type")

    if filters.tags:
        wanted = {tag.strip().lower() for tag in filters.tags if tag}
        actual = {str(tag).strip().lower() for tag in normalized_tags if tag}
        if not actual.intersection(wanted):
            return False

    if filters.min_confidence is not None and confidence_score < filters.min_confidence:
        return False
    if filters.max_confidence is not None and confidence_score > filters.max_confidence:
        return False

    if filters.issue_types:
        wanted_issue_types = {item.strip().lower() for item in filters.issue_types if item}
        if str(issue_type or "").strip().lower() not in wanted_issue_types:
            return False

    if filters.resolution_types:
        wanted_resolution_types = {
            item.strip().lower() for item in filters.resolution_types if item
        }
        if str(resolution_type or "").strip().lower() not in wanted_resolution_types:
            return False

    return True


@router.post("/search/examples", response_model=SearchExamplesResponse)
async def search_examples(
    request: SearchExamplesRequest,
    current_user: TokenPayload = Depends(get_current_user),
) -> SearchExamplesResponse:
    """Search FeedMe conversations for frontend discovery and search UI flows."""
    _ = current_user

    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503,
            detail="FeedMe service is currently disabled",
        )

    client = get_feedme_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="FeedMe service is temporarily unavailable.",
        )

    query_text = request.query.strip()
    if not query_text:
        return SearchExamplesResponse(
            results=[],
            total_count=0,
            page=request.page,
            page_size=request.page_size,
            has_more=False,
        )

    page = max(1, request.page)
    page_size = max(1, min(request.page_size, 100))
    offset = (page - 1) * page_size
    filters = request.filters

    try:
        ilike_pattern = f"%{query_text}%"
        query_builder = client.client.table("feedme_conversations").select(
            "id,title,extracted_text,metadata,folder_id,quality_score,created_at,updated_at,os_category,approval_status",
            count="exact",
        )
        query_builder = query_builder.or_(
            f"title.ilike.{ilike_pattern},extracted_text.ilike.{ilike_pattern}"
        )

        if filters:
            if filters.date_from:
                query_builder = query_builder.gte("created_at", filters.date_from)
            if filters.date_to:
                query_builder = query_builder.lte("created_at", filters.date_to)
            if filters.folder_ids:
                query_builder = query_builder.in_("folder_id", filters.folder_ids)
            if filters.platforms:
                query_builder = query_builder.in_("os_category", filters.platforms)
            if filters.status:
                query_builder = query_builder.in_("approval_status", filters.status)
            if filters.min_quality_score is not None:
                query_builder = query_builder.gte(
                    "quality_score",
                    filters.min_quality_score,
                )
            if filters.max_quality_score is not None:
                query_builder = query_builder.lte(
                    "quality_score",
                    filters.max_quality_score,
                )

        query_builder = query_builder.order("updated_at", desc=True)
        response = await client._exec(
            lambda: query_builder.range(offset, offset + page_size - 1).execute()
        )

        rows = response.data or []
        total_count = int(getattr(response, "count", 0) or 0)

        results: list[SearchExampleResult] = []
        for row in rows:
            conversation_id = int(row.get("id"))
            title = str(row.get("title") or f"Conversation {conversation_id}")
            extracted_text = str(row.get("extracted_text") or "")
            metadata_raw = row.get("metadata")
            metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
            quality_score = float(row.get("quality_score") or 0.0)
            confidence_score = float(metadata.get("confidence_score") or 0.0)

            if not _matches_metadata_filters(metadata, filters, confidence_score):
                continue

            tags_raw = metadata.get("tags")
            tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
            issue_type = (
                str(metadata.get("issue_type"))
                if metadata.get("issue_type") is not None
                else None
            )
            resolution_type = (
                str(metadata.get("resolution_type"))
                if metadata.get("resolution_type") is not None
                else None
            )

            result = SearchExampleResult(
                id=conversation_id,
                type="conversation",
                title=title,
                snippet=_snippet(extracted_text, query_text, request.include_snippets),
                score=_score(title, extracted_text, query_text, quality_score),
                conversation_id=conversation_id,
                example_id=None,
                folder_id=row.get("folder_id"),
                folder_name=(
                    str(metadata.get("folder_name"))
                    if metadata.get("folder_name") is not None
                    else None
                ),
                tags=tags,
                confidence_score=confidence_score,
                quality_score=quality_score,
                issue_type=issue_type,
                resolution_type=resolution_type,
                created_at=str(row.get("created_at") or ""),
                updated_at=str(row.get("updated_at") or ""),
            )
            results.append(result)

        if request.sort_by.strip().lower() == "relevance":
            results.sort(key=lambda item: item.score, reverse=True)

        has_more = (offset + len(results)) < total_count
        return SearchExamplesResponse(
            results=results,
            total_count=total_count,
            page=page,
            page_size=page_size,
            has_more=has_more,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search FeedMe examples: {exc}",
        ) from exc
