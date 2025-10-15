from __future__ import annotations

import hmac
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.settings import settings
from app.db.supabase.client import get_supabase_client
from .endpoints import _get_feature_state_snapshot, _upsert_month_usage

router = APIRouter(prefix="/integrations/zendesk/admin", tags=["Zendesk Admin"])

logger = logging.getLogger(__name__)


def _require_internal(request: Request) -> None:
    expected = getattr(settings, "internal_api_token", None)
    provided = request.headers.get("X-Internal-Token")
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")


@router.get("/health")
async def admin_health(request: Request) -> Dict[str, Any]:
    _require_internal(request)
    supa = get_supabase_client()

    # Feature flags snapshot and scheduler metrics
    feature_state = await _get_feature_state_snapshot()
    try:
        sched = await supa._exec(
            lambda: supa.client.table("feature_flags").select("value").eq("key", "zendesk_scheduler").maybe_single().execute()
        )
        sched_val = getattr(sched, "data", None) or {}
        sched_val = sched_val.get("value") if isinstance(sched_val, dict) else {}
    except Exception:
        sched_val = {}

    # Monthly/daily usage
    try:
        usage = await _upsert_month_usage(0)
    except Exception:
        usage = {"month_key": None, "calls_used": None, "budget": settings.zendesk_monthly_api_budget}
    try:
        from datetime import date
        today = date.today().isoformat()
        du = await supa._exec(lambda: supa.client.table("zendesk_daily_usage").select("gemini_calls_used,gemini_daily_limit").eq("usage_date", today).maybe_single().execute())
        daily = getattr(du, "data", None) or {}
    except Exception:
        daily = {}

    # Queue counts by status
    q_counts: Dict[str, Optional[int]] = {}
    for st in ("pending", "retry", "processing", "failed"):
        try:
            resp = await supa._exec(lambda st=st: supa.client.table("zendesk_pending_tickets").select("id", count="exact", head=True).eq("status", st).execute())
            q_counts[st] = getattr(resp, "count", None)
        except Exception:
            q_counts[st] = None

    # Last failed error snippet
    try:
        last_fail = await supa._exec(
            lambda: supa.client.table("zendesk_pending_tickets")
            .select("id,last_error,last_attempt_at")
            .eq("status", "failed")
            .order("last_attempt_at", desc=True)
            .limit(1)
            .execute()
        )
        last_error = (getattr(last_fail, "data", []) or [{}])[0].get("last_error")
    except Exception:
        last_error = None

    return {
        "enabled": feature_state.get("enabled", False),
        "dry_run": feature_state.get("dry_run", True),
        "scheduler": sched_val,
        "usage": usage,
        "daily": daily,
        "queue": q_counts,
        "last_error": last_error,
    }


@router.get("/queue")
async def list_queue(request: Request, response: Response, status_filter: Optional[str] = None, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    _require_internal(request)
    supa = get_supabase_client()
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    allowed = {"pending", "retry", "processing", "failed", "processed"}
    try:
        query = supa.client.table("zendesk_pending_tickets").select(
            "id,ticket_id,status,retry_count,created_at,last_attempt_at,last_error"
        ).order("created_at", desc=True).order("id", desc=True)
        if status_filter:
            if status_filter not in allowed:
                raise HTTPException(status_code=400, detail="invalid status")
            query = query.eq("status", status_filter)
        # range is inclusive; emulate offset/limit
        res = await supa._exec(lambda: query.range(offset, offset + limit - 1).execute())
        # Get total count for the same filter
        count_q = supa.client.table("zendesk_pending_tickets").select("id", count="exact", head=True)
        if status_filter:
            count_q = count_q.eq("status", status_filter)
        count_res = await supa._exec(lambda: count_q.execute())
        total = getattr(count_res, "count", 0) or 0
        response.headers["X-Total-Count"] = str(total)
        return {"items": getattr(res, "data", []) or [], "total": total, "limit": limit, "offset": offset}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("queue list failed: %s", e)
        raise HTTPException(status_code=500, detail="queue_list_failed")


@router.post("/queue/{item_id}/retry")
async def retry_item(request: Request, item_id: int) -> Dict[str, Any]:
    _require_internal(request)
    if item_id <= 0:
        raise HTTPException(status_code=400, detail="invalid id")
    supa = get_supabase_client()
    try:
        now = datetime.now(timezone.utc).isoformat()
        # Perform update without select (compat with supabase-py builder)
        await supa._exec(
            lambda: supa.client.table("zendesk_pending_tickets")
            .update({"status": "retry", "next_attempt_at": now, "last_error": None})
            .eq("id", item_id)
            .execute()
        )
        # Verify update
        verify = await supa._exec(
            lambda: supa.client.table("zendesk_pending_tickets")
            .select("id,status,next_attempt_at")
            .eq("id", item_id)
            .maybe_single()
            .execute()
        )
        data = getattr(verify, "data", None) or {}
        return {"updated": bool(data), "status": data.get("status"), "next_attempt_at": data.get("next_attempt_at")}
    except Exception as e:
        logger.error("queue retry failed: %s", e)
        raise HTTPException(status_code=500, detail="queue_retry_failed")


@router.post("/queue/retry-batch")
async def retry_batch(request: Request) -> Dict[str, Any]:
    _require_internal(request)
    supa = get_supabase_client()
    try:
        body = await request.json()
        raw_ids = body.get("ids") if isinstance(body, dict) else None
        if not isinstance(raw_ids, list) or not raw_ids:
            raise HTTPException(status_code=400, detail="ids required")
        try:
            ids = [int(i) for i in raw_ids]
        except Exception:
            raise HTTPException(status_code=400, detail="ids must be integers")
        ids = [i for i in ids if i > 0]
        if not ids:
            raise HTTPException(status_code=400, detail="ids must be positive integers")
        # dedupe and cap to 200
        ids = list(dict.fromkeys(ids))[:200]
        now = datetime.now(timezone.utc).isoformat()
        # Update without select
        await supa._exec(
            lambda: supa.client.table("zendesk_pending_tickets")
            .update({"status": "retry", "next_attempt_at": now, "last_error": None})
            .in_("id", ids)
            .execute()
        )
        # Verify by counting rows now in retry
        verify = await supa._exec(
            lambda: supa.client.table("zendesk_pending_tickets")
            .select("id")
            .in_("id", ids)
            .eq("status", "retry")
            .execute()
        )
        count = len(getattr(verify, "data", []) or [])
        return {"updated": count, "requested": len(ids)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("queue retry batch failed: %s", e)
        raise HTTPException(status_code=500, detail="queue_retry_batch_failed")
