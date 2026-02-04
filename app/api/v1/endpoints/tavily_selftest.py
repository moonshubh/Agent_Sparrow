from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.settings import settings
from app.core.user_context import create_user_context_from_user_id, user_context_scope

logger = logging.getLogger(__name__)
router = APIRouter()


class TavilySelfTestResponse(BaseModel):
    ok: bool
    status: int | None = None
    error: str | None = None


try:
    from app.api.v1.endpoints.auth import get_current_user_id
except Exception:  # pragma: no cover

    async def get_current_user_id() -> str:  # type: ignore
        return settings.development_user_id


@router.get(
    "/tools/tavily/self-test",
    response_model=TavilySelfTestResponse,
    tags=["Search Tools"],
)
async def tavily_self_test(user_id: str = Depends(get_current_user_id)):
    """Dev-only endpoint to validate Tavily key and request shape.

    Returns ok when a minimal search completes; otherwise returns error code.
    """
    if settings.is_production_mode():
        raise HTTPException(status_code=404, detail="Not available in production")

    try:
        user_ctx = await create_user_context_from_user_id(user_id)
        key = await user_ctx.get_tavily_api_key()
        if not key:
            return TavilySelfTestResponse(ok=False, status=400, error="no_user_key")

        from app.tools.user_research_tools import tavily_web_search  # type: ignore[import-not-found]

        async with user_context_scope(user_ctx):
            res = await tavily_web_search("mailbird", max_results=1)
        if res.get("results"):
            return TavilySelfTestResponse(ok=True)
        # Bubble up structured error if present
        return TavilySelfTestResponse(
            ok=False, status=res.get("status"), error=res.get("error") or "no_results"
        )
    except Exception as e:
        logger.error("Tavily self-test failed: %s", e, exc_info=True)
        return TavilySelfTestResponse(ok=False, status=500, error="exception")
