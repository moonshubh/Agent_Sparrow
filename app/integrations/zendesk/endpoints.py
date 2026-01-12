from __future__ import annotations

import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import re

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import get_models_config, resolve_coordinator_config
from app.core.settings import settings
from app.db.supabase.client import get_supabase_client
from .exclusions import compute_ticket_exclusion
from .security import verify_webhook_signature

router = APIRouter(prefix="/integrations/zendesk", tags=["Zendesk"])

logger = logging.getLogger(__name__)

# Default model for Zendesk - centralized to ensure consistency

# Basic PII redactors for emails and phone numbers
_EMAIL_RE = re.compile(r'([A-Za-z0-9._%+-]{1,})@([A-Za-z0-9.-]{1,})')
_PHONE_RE = re.compile(r'(?<!\d)(\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?){2}\d{4}(?!\d)')

def _redact_pii(text: str | None) -> str | None:
    if not text or not isinstance(text, str):
        return text
    t = _EMAIL_RE.sub(lambda m: f"{m.group(1)[:2]}***@{m.group(2)}", text)
    t = _PHONE_RE.sub("[redacted-phone]", t)
    return t


def _get_nested(d: Dict[str, Any] | None, *keys: str) -> Any:
    cur: Any = d or {}
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur.get(k)
    return cur


def _find_ticket_id_recursive(d: Any, parents: Tuple[str, ...] = ()) -> Optional[str]:
    if isinstance(d, dict):
        # Direct key matches first
        for k, v in d.items():
            lk = str(k).lower()
            if v is None:
                continue
            if lk in ("ticket_id", "ticketid"):
                return str(v).strip()
            if lk == "id":
                # Accept when within a likely ticket context
                if any(p in ("ticket", "ticket_event") for p in parents) or (
                    "detail" in parents and ("brand_id" in d or "form_id" in d or "custom_status" in d)
                ):
                    return str(v).strip()
        # Recurse
        for k, v in d.items():
            res = _find_ticket_id_recursive(v, parents + (str(k),))
            if res:
                return res
    elif isinstance(d, list):
        for i, v in enumerate(d):
            res = _find_ticket_id_recursive(v, parents + (f"[{i}]",))
            if res:
                return res
    return None


def _find_brand_id_recursive(d: Any) -> Optional[str]:
    if isinstance(d, dict):
        for k, v in d.items():
            if str(k).lower() == "brand_id" and v is not None:
                return str(v).strip()
        for v in d.values():
            res = _find_brand_id_recursive(v)
            if res:
                return res
    elif isinstance(d, list):
        for v in d:
            res = _find_brand_id_recursive(v)
            if res:
                return res
    return None


def _extract_ticket_and_brand(payload: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    # Try common shapes first; do NOT fall back to top-level id (that can be event id)
    candidates = [
        _get_nested(payload, "ticket", "id"),
        _get_nested(payload, "ticket_event", "ticket", "id"),
        payload.get("ticket_id"),
        _get_nested(payload, "detail", "ticket_id"),
        _get_nested(payload, "detail", "ticket", "id"),
    ]
    ticket_raw: Optional[str] = next((str(c).strip() for c in candidates if c is not None), None)
    if not ticket_raw:
        ticket_raw = _find_ticket_id_recursive(payload)  # broader fallback for Zendesk variants
    brand_candidates = [
        _get_nested(payload, "ticket", "brand_id"),
        _get_nested(payload, "ticket_event", "ticket", "brand_id"),
        payload.get("brand_id"),
        _get_nested(payload, "detail", "brand_id"),
    ]
    brand_raw: Optional[str] = next((str(c).strip() for c in brand_candidates if c is not None), None)
    if not brand_raw:
        brand_raw = _find_brand_id_recursive(payload)
    return ticket_raw, brand_raw


async def _upsert_month_usage(delta_calls: int = 0) -> Dict[str, Any]:
    """Ensure a usage row exists for current month and optionally increment calls_used."""
    supa = get_supabase_client()
    mk = datetime.now(timezone.utc).strftime("%Y-%m")
    desired_budget = int(getattr(settings, "zendesk_monthly_api_budget", 0) or 0)
    resp = await supa._exec(
        lambda: supa.client.table("zendesk_usage")
        .select("month_key, calls_used, budget")
        .eq("month_key", mk)
        .maybe_single()
        .execute()
    )
    row = getattr(resp, "data", None)
    if not row:
        await supa._exec(
            lambda: supa.client.table("zendesk_usage")
            .insert({
                "month_key": mk,
                "calls_used": 0,
                "budget": desired_budget,
            })
            .execute()
        )
        row = {"month_key": mk, "calls_used": 0, "budget": desired_budget}
    else:
        # Keep DB row budget in sync with config (so changes via env are applied immediately).
        try:
            current_budget = int(row.get("budget", desired_budget) or desired_budget)
        except Exception:
            current_budget = desired_budget
        if desired_budget > 0 and current_budget != desired_budget:
            try:
                await supa._exec(
                    lambda: supa.client.table("zendesk_usage")
                    .update(
                        {
                            "budget": desired_budget,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    .eq("month_key", mk)
                    .execute()
                )
                row["budget"] = desired_budget
            except Exception:
                row["budget"] = desired_budget
    if delta_calls:
        new_val = max(0, int(row.get("calls_used", 0)) + int(delta_calls))
        await supa._exec(
            lambda: supa.client.table("zendesk_usage")
            .update({
                "calls_used": new_val,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("month_key", mk)
            .execute()
        )
        row["calls_used"] = new_val
    return row


async def _get_feature_enabled() -> bool:
    # Prefer Supabase flag when present
    try:
        supa = get_supabase_client()
        resp = await supa._exec(
            lambda: supa.client.table("feature_flags")
            .select("value")
            .eq("key", "zendesk_enabled")
            .maybe_single()
            .execute()
        )
        data = getattr(resp, "data", None)
        if data and isinstance(data.get("value"), dict):
            return bool(data["value"].get("enabled", False))
    except Exception as e:
        logger.debug("feature flag fetch failed: %s", e)
    # Fallback to env flag
    return bool(getattr(settings, "zendesk_enabled", False))


async def _get_feature_state_snapshot() -> Dict[str, Any]:
    """Return current feature flag state (enabled/dry_run/provider/model)."""
    enabled = await _get_feature_enabled()
    dry_run = bool(getattr(settings, "zendesk_dry_run", True))
    config = get_models_config()
    if config.zendesk is not None:
        coordinator_cfg = resolve_coordinator_config(config, "google", zendesk=True)
    else:
        coordinator_cfg = resolve_coordinator_config(config, "google")
    provider = coordinator_cfg.provider or "google"
    model = coordinator_cfg.model_id
    try:
        supa = get_supabase_client()
        resp = await supa._exec(
            lambda: supa.client.table("feature_flags")
            .select("value")
            .eq("key", "zendesk_enabled")
            .maybe_single()
            .execute()
        )
        data = getattr(resp, "data", None)
        if data and isinstance(data.get("value"), dict):
            val = data["value"]
            if "dry_run" in val:
                dry_run = bool(val.get("dry_run", dry_run))
    except Exception:
        pass
    return {"enabled": enabled, "dry_run": dry_run, "provider": provider, "model": model}


@router.get("/health")
async def health(request: Request) -> Dict[str, Any]:
    expected = getattr(settings, "internal_api_token", None)
    provided = request.headers.get("X-Internal-Token")
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    """Return enabled status and usage snapshot, plus queue stats."""
    try:
        usage = await _upsert_month_usage(0)
    except Exception:
        usage = {"month_key": None, "calls_used": None, "budget": settings.zendesk_monthly_api_budget}
    feature_state = await _get_feature_state_snapshot()

    # Queue counts and daily Gemini usage
    supa = get_supabase_client()
    try:
        pending = await supa._exec(lambda: supa.client.table("zendesk_pending_tickets").select("id", count="exact", head=True).eq("status", "pending").execute())
        retry = await supa._exec(lambda: supa.client.table("zendesk_pending_tickets").select("id", count="exact", head=True).eq("status", "retry").execute())
        q_counts = {
            "pending": getattr(pending, "count", None),
            "retry": getattr(retry, "count", None),
        }
    except Exception:
        q_counts = {"pending": None, "retry": None}

    try:
        from datetime import date
        today = date.today().isoformat()
        du = await supa._exec(lambda: supa.client.table("zendesk_daily_usage").select("gemini_calls_used,gemini_daily_limit").eq("usage_date", today).maybe_single().execute())
        daily_usage = getattr(du, "data", None) or {}
    except Exception:
        daily_usage = {}

    return {
        "enabled": feature_state["enabled"],
        "dry_run": feature_state["dry_run"],
        "provider": feature_state["provider"],
        "model": feature_state["model"],
        "brand_id": getattr(settings, "zendesk_brand_id", None),
        "usage": usage,
        "queue": q_counts,
        "daily": daily_usage,
    }


class FeatureToggleRequest(BaseModel):
    enabled: bool
    dry_run: bool | None = None


# Available models for Zendesk - all support vision/multimodal (images, PDFs, logs)
ZENDESK_MODEL_OPTIONS = {
    "google": [
        # All Gemini models support vision natively
        {"id": "gemini-3-flash-preview", "name": "Gemini 3.0 Flash (Vision)"},
        {"id": "gemini-3-pro-preview", "name": "Gemini 3.0 Pro (Vision)"},
        {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash (Vision)"},
        {"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash Lite"},
    ],
    "xai": [
        # Grok models support vision via xAI API
        {"id": "grok-4-1-fast-reasoning", "name": "Grok 4.1 Fast (Vision)"},
        {"id": "grok-4", "name": "Grok 4 (Vision)"},
        {"id": "grok-2-vision-1212", "name": "Grok 2 Vision"},
    ],
    "openrouter": [
        # Vision-capable models via OpenRouter
        {"id": "x-ai/grok-4.1-fast", "name": "Grok 4.1 Fast"},
        {"id": "google/gemini-2.5-flash-preview", "name": "Gemini 2.5 Flash (Vision)"},
        {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet (Vision)"},
        {"id": "openai/gpt-4o", "name": "GPT-4o (Vision)"},
    ],
}


@router.get("/models")
async def get_available_models(request: Request) -> Dict[str, Any]:
    """Return available model options for Zendesk."""
    expected = getattr(settings, "internal_api_token", None)
    provided = request.headers.get("X-Internal-Token")
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    # Check which providers have API keys configured
    available_providers = []
    if getattr(settings, "gemini_api_key", None):
        available_providers.append("google")
    if getattr(settings, "xai_api_key", None):
        available_providers.append("xai")
    if getattr(settings, "openrouter_api_key", None):
        available_providers.append("openrouter")

    config = get_models_config()
    if config.zendesk is not None:
        coordinator_cfg = resolve_coordinator_config(config, "google", zendesk=True)
    else:
        coordinator_cfg = resolve_coordinator_config(config, "google")

    return {
        "models": ZENDESK_MODEL_OPTIONS,
        "available_providers": available_providers,
        "default_provider": coordinator_cfg.provider or "google",
        "default_model": coordinator_cfg.model_id,
    }


@router.post("/feature")
async def set_feature(request: Request, payload: FeatureToggleRequest) -> Dict[str, Any]:
    """Set feature flag in Supabase. Requires INTERNAL_API_TOKEN header."""
    expected = getattr(settings, "internal_api_token", None)
    if not expected:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal token not configured")

    provided = request.headers.get("X-Internal-Token")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid internal token")

    # Read existing value to preserve fields not being updated
    try:
        supa = get_supabase_client()
        resp = await supa._exec(
            lambda: supa.client.table("feature_flags")
            .select("value")
            .eq("key", "zendesk_enabled")
            .maybe_single()
            .execute()
        )
        existing = (getattr(resp, "data", None) or {}).get("value") or {}
    except Exception:
        existing = {}

    value: Dict[str, Any] = {**existing, "enabled": bool(payload.enabled)}
    if payload.dry_run is not None:
        value["dry_run"] = bool(payload.dry_run)

    try:
        supa = get_supabase_client()
        await supa._exec(
            lambda: supa.client.table("feature_flags")
            .upsert({"key": "zendesk_enabled", "value": value})
            .execute()
        )
    except Exception as e:
        logger.error("feature flag upsert failed: %s", e)
        raise HTTPException(status_code=500, detail="feature flag write failed")

    return {"ok": True, "value": value}


@router.post("/webhook")
async def webhook(request: Request) -> Dict[str, Any]:
    """Zendesk Trigger webhook: capture new tickets. No outbound Zendesk calls here.

    Expects headers: X-Zendesk-Webhook-Signature, X-Zendesk-Webhook-Signature-Timestamp
    Body should include ticket identifiers (ticket.id, brand_id, subject, description).
    """
    if not await _get_feature_enabled():
        # Fast no-op when disabled
        return {"ok": True, "disabled": True}

    body_bytes = await request.body()
    sig = request.headers.get("X-Zendesk-Webhook-Signature")
    ts = request.headers.get("X-Zendesk-Webhook-Signature-Timestamp")
    # Optional debug logging (redacted) to diagnose signature mismatches in dev
    if getattr(settings, "zendesk_debug_verify", False):
        try:
            # parse ts to epoch for window diagnostics
            ts_epoch = None
            try:
                ts_epoch = int(str(ts)) if ts is not None else None
            except Exception:
                try:
                    ts_str = str(ts).replace("Z", "+00:00") if ts is not None else None
                    if ts_str:
                        dt = datetime.fromisoformat(ts_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        ts_epoch = int(dt.timestamp())
                except Exception:
                    ts_epoch = None
            logger.warning(
                "Zendesk verify debug: body_len=%s ts_raw='%s' ts_epoch=%s",
                len(body_bytes), str(ts)[:32] if ts is not None else None, ts_epoch,
            )
        except Exception:
            # Do not fail webhook on debugging
            pass
    if not verify_webhook_signature(signature_b64=sig, timestamp=ts, raw_body=body_bytes, signing_secret=settings.zendesk_signing_secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid_signature")

    # Replay protection: idempotency guard keyed by (timestamp, signature-tail)
    try:
        if ts and sig:
            # Use only a short tail of the signature to avoid storing full secrets
            sig_tail = str(sig)[-12:]
            sig_key = f"{ts}:{sig_tail}"
            supa = get_supabase_client()
            # Parse timestamp for storage (epoch seconds)
            ts_epoch = None
            try:
                ts_epoch = int(ts)
            except Exception:
                try:
                    ts_str = str(ts).replace("Z", "+00:00")
                    dt = datetime.fromisoformat(ts_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    ts_epoch = int(dt.timestamp())
                except Exception:
                    ts_epoch = None
            await supa._exec(
                lambda: supa.client.table("zendesk_webhook_events")
                .insert({"sig_key": sig_key, "ts": ts_epoch})
                .execute()
            )
    except Exception as e:
        msg = str(e)
        if "duplicate key" in msg or "already exists" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="replay_detected")
        logger.error("replay state insert failed: %s", e)
        raise HTTPException(status_code=500, detail="replay_state_insert_failed")

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        payload = {}

    # Extract fields robustly from trigger payloads
    ticket_raw, brand_raw = _extract_ticket_and_brand(payload)
    if not ticket_raw:
        if getattr(settings, "zendesk_debug_verify", False):
            try:
                top_keys = sorted(list(payload.keys())) if isinstance(payload, dict) else []
                detail_keys = sorted(list((payload.get("detail") or {}).keys())) if isinstance(payload, dict) else []
                logger.warning("Zendesk payload debug: ticket id missing; top_keys=%s detail_keys=%s", top_keys[:20], detail_keys[:20])
            except Exception:
                pass
        raise HTTPException(status_code=400, detail="ticket id missing")
    try:
        ticket_id_int = int(str(ticket_raw).strip())
    except Exception:
        if getattr(settings, "zendesk_debug_verify", False):
            logger.warning("Zendesk payload debug: non-numeric ticket id raw='%s'", str(ticket_raw)[:32])
        raise HTTPException(status_code=400, detail="ticket id must be numeric")

    brand_id = brand_raw
    # Choose a best-effort ticket object for optional fields
    t = (
        (payload.get("ticket") or {}) if isinstance(payload, dict) else {}
    ) or (
        (_get_nested(payload, "ticket_event", "ticket") or {}) if isinstance(payload, dict) else {}
    ) or (
        (_get_nested(payload, "detail", "ticket") or {}) if isinstance(payload, dict) else {}
    )
    subject = (t.get("subject") if isinstance(t, dict) else None) or (payload.get("subject") if isinstance(payload, dict) else None)
    description = (t.get("description") if isinstance(t, dict) else None) or (payload.get("description") if isinstance(payload, dict) else None)
    # Optional requester hashing (only when signing secret is configured)
    requester_email = None
    try:
        req = (t.get("requester") if isinstance(t, dict) else None) or {}
        if isinstance(req, dict):
            requester_email = req.get("email")
    except Exception:
        requester_email = None
    requester_hashed = None
    try:
        if requester_email and settings.zendesk_signing_secret:
            # HMAC(email) with signing secret; avoid storing raw email
            key = str(settings.zendesk_signing_secret).encode("utf-8")
            requester_hashed = hmac.new(key, str(requester_email).encode("utf-8"), digestmod="sha256").hexdigest()
    except Exception:
        requester_hashed = None

    # Filter by configured brand if provided
    configured_brand = getattr(settings, "zendesk_brand_id", None)
    if configured_brand and str(brand_id) != str(configured_brand):
        return {"ok": True, "filtered": True}

    # Exclusions (status/tags/brand) to avoid generating internal notes on tickets like
    # proactive feature-delivery macros that are created already solved.
    ticket_for_exclusion: Dict[str, Any] = t if isinstance(t, dict) else {}
    if isinstance(payload, dict):
        if "status" not in ticket_for_exclusion and payload.get("status") is not None:
            ticket_for_exclusion = {**ticket_for_exclusion, "status": payload.get("status")}
        if "tags" not in ticket_for_exclusion and payload.get("tags") is not None:
            ticket_for_exclusion = {**ticket_for_exclusion, "tags": payload.get("tags")}

    exclusion = compute_ticket_exclusion(
        ticket_for_exclusion,
        brand_id=str(brand_id) if brand_id is not None else None,
        excluded_statuses=getattr(settings, "zendesk_excluded_statuses", []),
        excluded_tags=getattr(settings, "zendesk_excluded_tags", []),
        excluded_brand_ids=getattr(settings, "zendesk_excluded_brand_ids", []),
    )
    if exclusion.excluded:
        return {"ok": True, "filtered": True, "reason": exclusion.reason}

    # Minimal retention: truncate long text fields and do NOT persist raw payload
    if subject:
        subject = _redact_pii(subject)[:200]
    if description:
        description = _redact_pii(description)[:2000]

    # Insert into supabase queue; ignore duplicates by unique constraint
    try:
        supa = get_supabase_client()
        await supa._exec(
            lambda: supa.client.table("zendesk_pending_tickets")
            .insert({
                "ticket_id": ticket_id_int,
                "brand_id": str(brand_id) if brand_id is not None else None,
                "subject": subject,
                "description": description,
                "payload": {},
                "status": "pending",
                "requester_hashed": requester_hashed,
            })
            .execute()
        )
        queued = True
    except Exception as e:
        msg = str(e)
        if "duplicate key" in msg or "already exists" in msg:
            queued = False
        else:
            logger.error("Failed to queue ticket %s: %s", ticket_id_int, e)
            raise HTTPException(status_code=500, detail="queue_insert_failed")

    return {"ok": True, "queued": queued}
