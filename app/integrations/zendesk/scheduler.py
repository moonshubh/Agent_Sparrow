from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List
import time

from langchain_core.messages import HumanMessage

from app.core.settings import settings
from app.db.supabase.client import get_supabase_client
from app.agents.primary import run_primary_agent, PrimaryAgentState
from .client import ZendeskClient

logger = logging.getLogger(__name__)


class RPMLimiter:
    """Simple token bucket RPM limiter (in-memory)."""
    def __init__(self, rpm: int) -> None:
        self.capacity = max(1, int(rpm))
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - self.last_refill)
        # tokens per second = capacity / 60
        rate_per_sec = self.capacity / 60.0
        self.tokens = min(self.capacity, self.tokens + elapsed * rate_per_sec)
        self.last_refill = now

    def try_acquire(self, n: int = 1) -> bool:
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


# Global RPM limiter instance
_rpm = RPMLimiter(getattr(settings, "zendesk_rpm_limit", 300))


async def _run_daily_maintenance(webhook_retention_days: int = 7, queue_retention_days: int | None = None) -> None:
    """Perform daily cleanup tasks for webhook events and processed queue rows."""
    try:
        supa = get_supabase_client()
        resp = await supa._exec(
            lambda: supa.client.table("feature_flags").select("value").eq("key", "zendesk_cleanup").maybe_single().execute()
        )
        raw = getattr(resp, "data", None) or {}
        state = raw.get("value") if isinstance(raw, dict) else {}
        state = state if isinstance(state, dict) else {}
        today = datetime.now(timezone.utc).date().isoformat()
        updated = False

        last_cleanup = state.get("last_cleanup_date")
        if last_cleanup != today:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, int(webhook_retention_days)))).isoformat()
            try:
                await supa._exec(
                    lambda: supa.client.table("zendesk_webhook_events").delete().lt("seen_at", cutoff).execute()
                )
            except Exception as cleanup_exc:
                logger.debug("webhook cleanup failed: %s", cleanup_exc)
            else:
                state["last_cleanup_date"] = today
                updated = True

        if queue_retention_days is not None:
            last_retention = state.get("last_retention_date")
            if last_retention != today:
                cutoff_queue = (datetime.now(timezone.utc) - timedelta(days=max(1, int(queue_retention_days)))).isoformat()
                try:
                    await supa._exec(
                        lambda: supa.client.table("zendesk_pending_tickets")
                        .delete()
                        .in_("status", ["processed", "failed"])
                        .lt("created_at", cutoff_queue)
                        .execute()
                    )
                except Exception as retention_exc:
                    logger.debug("queue retention cleanup failed: %s", retention_exc)
                else:
                    state["last_retention_date"] = today
                    updated = True

        if updated:
            await supa._exec(
                lambda: supa.client.table("feature_flags").upsert({"key": "zendesk_cleanup", "value": state}).execute()
            )
    except Exception as e:
        logger.debug("daily maintenance failed: %s", e)


async def _get_feature_state() -> Dict[str, Any]:
    """Read feature flag state from Supabase, fallback to env flags."""
    enabled = bool(getattr(settings, "zendesk_enabled", False))
    dry_run = bool(getattr(settings, "zendesk_dry_run", True))
    last_run_at = None
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
            enabled = bool(data["value"].get("enabled", enabled))
            if "dry_run" in data["value"]:
                dry_run = bool(data["value"].get("dry_run", dry_run))
        # Also track scheduler state under key 'zendesk_scheduler'
        resp2 = await supa._exec(
            lambda: supa.client.table("feature_flags")
            .select("value")
            .eq("key", "zendesk_scheduler")
            .maybe_single()
            .execute()
        )
        data2 = getattr(resp2, "data", None)
        if data2 and isinstance(data2.get("value"), dict):
            last_run_at = data2["value"].get("last_run_at")
    except Exception as e:
        logger.debug("feature flag read failed: %s", e)
    return {"enabled": enabled, "dry_run": dry_run, "last_run_at": last_run_at}


async def _set_last_run(ts: datetime) -> None:
    try:
        supa = get_supabase_client()
        await supa._exec(
            lambda: supa.client.table("feature_flags")
            .upsert({
                "key": "zendesk_scheduler",
                "value": {"last_run_at": ts.replace(microsecond=0).isoformat()},
            })
            .execute()
        )
    except Exception as e:
        logger.debug("failed to persist scheduler ts: %s", e)


async def _get_month_usage() -> Dict[str, Any]:
    supa = get_supabase_client()
    mk = datetime.now(timezone.utc).strftime("%Y-%m")
    resp = await supa._exec(
        lambda: supa.client.table("zendesk_usage")
        .select("month_key,calls_used,budget")
        .eq("month_key", mk)
        .maybe_single()
        .execute()
    )
    data = getattr(resp, "data", None)
    if not data:
        await supa._exec(
            lambda: supa.client.table("zendesk_usage")
            .insert({
                "month_key": mk,
                "calls_used": 0,
                "budget": settings.zendesk_monthly_api_budget,
            })
            .execute()
        )
        data = {"month_key": mk, "calls_used": 0, "budget": settings.zendesk_monthly_api_budget}
    return data


async def _inc_usage(n: int) -> None:
    if n <= 0:
        return
    supa = get_supabase_client()
    mk = datetime.now(timezone.utc).strftime("%Y-%m")
    resp = await supa._exec(
        lambda: supa.client.table("zendesk_usage")
        .select("calls_used")
        .eq("month_key", mk)
        .maybe_single()
        .execute()
    )
    cur = (getattr(resp, "data", None) or {}).get("calls_used", 0)
    await supa._exec(
        lambda: supa.client.table("zendesk_usage")
        .update({
            "calls_used": int(cur) + int(n),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("month_key", mk)
        .execute()
    )


async def _get_daily_usage() -> Dict[str, Any]:
    supa = get_supabase_client()
    today = date.today().isoformat()
    resp = await supa._exec(
        lambda: supa.client.table("zendesk_daily_usage")
        .select("usage_date, gemini_calls_used, gemini_daily_limit")
        .eq("usage_date", today)
        .maybe_single()
        .execute()
    )
    row = getattr(resp, "data", None)
    if not row:
        row = {
            "usage_date": today,
            "gemini_calls_used": 0,
            "gemini_daily_limit": getattr(settings, "zendesk_gemini_daily_limit", 1000),
        }
        await supa._exec(
            lambda: supa.client.table("zendesk_daily_usage").insert(row).execute()
        )
    return row


async def _inc_daily_usage(n: int) -> None:
    if n <= 0:
        return
    supa = get_supabase_client()
    today = date.today().isoformat()
    resp = await supa._exec(
        lambda: supa.client.table("zendesk_daily_usage")
        .select("gemini_calls_used")
        .eq("usage_date", today)
        .maybe_single()
        .execute()
    )
    used = (getattr(resp, "data", None) or {}).get("gemini_calls_used", 0)
    await supa._exec(
        lambda: supa.client.table("zendesk_daily_usage")
        .update({
            "gemini_calls_used": int(used) + int(n),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("usage_date", today)
        .execute()
    )


async def _generate_reply(ticket_id: int | str, subject: str | None, description: str | None) -> str:
    """Run Primary Agent non-streaming to produce suggested public reply text."""
    subj = subject or "(no subject)"
    desc = description or "(no description)"
    prompt = (
        "You are preparing a suggested public reply for a new Zendesk ticket.\n"
        f"Subject: {subj}\n"
        f"Description: {desc}\n\n"
        "Provide a helpful, accurate answer using available knowledge. Do not include private internal notes; write as a reply to the customer."
    )
    session_id = f"zendesk-{ticket_id}"
    state = PrimaryAgentState(messages=[HumanMessage(content=prompt)], session_id=session_id)
    parts: List[str] = []
    async for chunk in run_primary_agent(state):
        if getattr(chunk, "content", None):
            parts.append(str(chunk.content))
    text = ("".join(parts)).strip()
    return text or "Thank you for reaching out. We’re reviewing your request and will follow up shortly."


async def _process_window(window_start: datetime, window_end: datetime, dry_run: bool) -> Dict[str, Any]:
    supa = get_supabase_client()
    # Pull due tickets (pending or retry where next_attempt_at <= now)
    resp = await supa._exec(
        lambda: supa.client.table("zendesk_pending_tickets")
        .select("id,ticket_id,subject,description,created_at,retry_count,next_attempt_at")
        .in_("status", ["pending", "retry"]) 
        .lt("created_at", window_end.isoformat())
        .order("created_at")
        .order("id")
        .limit(500)
        .execute()
    )
    rows = resp.data or []
    # Filter to due rows only
    due_rows: List[Dict[str, Any]] = []
    now_utc = datetime.now(timezone.utc)
    for r in rows:
        na = r.get("next_attempt_at")
        if not na:
            due_rows.append(r)
            continue
        try:
            if isinstance(na, str):
                na_str = na.replace("Z", "+00:00")
                na_dt = datetime.fromisoformat(na_str)
            elif isinstance(na, datetime):
                na_dt = na
            else:
                # unknown type → skip as not due
                continue
            if na_dt.tzinfo is None:
                na_dt = na_dt.replace(tzinfo=timezone.utc)
        except Exception:
            # unparsable → skip as not due
            continue
        if na_dt <= now_utc:
            due_rows.append(r)
    rows = due_rows
    if not rows:
        return {"processed": 0, "skipped_budget": False}

    # Enforce monthly budget before doing any work (server-side check)
    try:
        mu = await _get_month_usage()
        if not dry_run and int(mu.get("calls_used", 0)) >= int(mu.get("budget", settings.zendesk_monthly_api_budget)):
            logger.warning("Monthly Zendesk budget exhausted; stopping processing")
            return {"processed": 0, "failed": 0, "skipped_budget": True}
    except Exception as e:
        logger.debug("failed to read monthly usage: %s", e)

    # Prepare Zendesk client (validate creds)
    if not (settings.zendesk_subdomain and settings.zendesk_email and settings.zendesk_api_token):
        logger.warning("Zendesk credentials missing; skipping processing window")
        return {"processed": 0, "failed": 0, "skipped_credentials": True}

    zc = ZendeskClient(
        subdomain=str(settings.zendesk_subdomain),
        email=str(settings.zendesk_email),
        api_token=str(settings.zendesk_api_token),
        dry_run=dry_run,
    )

    processed = 0
    failures = 0
    rpm_exhausted = False
    # Check Gemini daily remaining
    daily = await _get_daily_usage()
    gemini_remaining = max(0, int(daily.get("gemini_daily_limit", settings.zendesk_gemini_daily_limit)) - int(daily.get("gemini_calls_used", 0)))
    for row in rows:
        try:
            tid = int(row["ticket_id"])
        except (TypeError, ValueError):
            logger.warning("Skipping ticket with non-numeric id: %s", row.get("ticket_id"))
            continue
        # Rate limit checks
        if not _rpm.try_acquire(1):
            rpm_exhausted = True
            break
        if gemini_remaining <= 0 and not dry_run:
            logger.warning("Gemini daily limit exhausted; stopping processing")
            break
        try:
            # Claim row BEFORE doing any heavy work to avoid duplicate compute across workers
            now_iso = datetime.now(timezone.utc).isoformat()
            # Update without select (supabase-py may not support select() on update builders)
            await supa._exec(
                lambda: supa.client.table("zendesk_pending_tickets")
                .update({"status": "processing", "status_details": {"processing_started_at": now_iso}})
                .eq("id", row["id"])
                .in_("status", ["pending", "retry"])  # only claim if still eligible
                .execute()
            )
            # Verify claim by re-reading the row
            verify = await supa._exec(
                lambda: supa.client.table("zendesk_pending_tickets")
                .select("id,status")
                .eq("id", row["id"])  # the same row
                .maybe_single()
                .execute()
            )
            v = getattr(verify, "data", None) or {}
            if (v.get("status") != "processing"):
                # Already claimed/processed elsewhere; skip
                continue

            # Generate suggested reply after successful claim
            reply = await _generate_reply(tid, row.get("subject"), row.get("description"))
            await asyncio.to_thread(zc.add_internal_note, tid, reply, add_tag="mb_auto_triaged")
            await supa._exec(
                lambda: supa.client.table("zendesk_pending_tickets")
                .update({
                    "status": "processed",
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                })
                .eq("id", row["id"])
                .execute()
            )
            processed += 1
            gemini_remaining = gemini_remaining if dry_run else max(0, gemini_remaining - 1)
        except Exception as e:
            logger.warning("posting failed for ticket %s: %s", tid, e)
            err = str(e)
            # If credentials invalid (401/403), revert claim and stop this cycle
            if "Zendesk update failed: 401" in err or "Zendesk update failed: 403" in err:
                await supa._exec(
                    lambda: supa.client.table("zendesk_pending_tickets")
                    .update({
                        "status": "pending",
                        "last_error": "zendesk_auth_failed",
                        "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                    })
                    .eq("id", row["id"])
                    .execute()
                )
                failures += 1
                break
            rc = (row.get("retry_count") or 0) + 1
            if rc >= getattr(settings, "zendesk_max_retries", 5):
                new_status = "failed"
                next_at = None
            else:
                new_status = "retry"
                # backoff: 1,2,4,8,16,32 minutes; capped at 60
                delay_min = min(60, 2 ** min(6, rc - 1))
                next_at = (datetime.now(timezone.utc) + timedelta(minutes=delay_min)).isoformat()
            await supa._exec(
                lambda: supa.client.table("zendesk_pending_tickets")
                .update({
                    "status": new_status,
                    "retry_count": rc,
                    "last_error": str(e)[:500],
                    "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                    "next_attempt_at": next_at,
                })
                .eq("id", row["id"])
                .execute()
            )
            failures += 1

    # Mark any remaining tickets in the window as dropped (no backfill policy)
    overflow_pending = False
    if rpm_exhausted:
        overflow_pending = True
        logger.warning("RPM exhausted; deferring remaining tickets to next cycle")

    # Increment usage only for actual API calls when not dry-run
    if not dry_run and processed > 0:
        await _inc_usage(processed)
        await _inc_daily_usage(processed)

    return {"processed": processed, "failed": failures, "pending_overflow": overflow_pending, "rpm_exhausted": rpm_exhausted}


async def start_background_scheduler() -> None:
    """Background loop that runs every N seconds and drains the pending queue respecting RPM & daily limits."""
    interval_sec = max(1, int(getattr(settings, "zendesk_poll_interval_sec", 60)))
    logger.info("Zendesk scheduler starting (interval=%d sec)", interval_sec)

    while True:
        try:
            state = await _get_feature_state()
            if not state.get("enabled", False):
                continue

            now = datetime.now(timezone.utc).replace(microsecond=0)
            window_start = now - timedelta(seconds=interval_sec)
            result = await _process_window(window_start, now, bool(state.get("dry_run", True)))
            logger.info("Zendesk window processed: %s", result)
            await _set_last_run(now)
            # Mark last success timestamp
            try:
                supa = get_supabase_client()
                await supa._exec(
                    lambda: supa.client.table("feature_flags")
                    .upsert({
                        "key": "zendesk_scheduler",
                        "value": {"last_run_at": now.isoformat(), "last_success_at": now.isoformat()},
                    })
                    .execute()
                )
            except Exception:
                pass
            # Daily maintenance: webhook cleanup + queue retention
            await _run_daily_maintenance(
                webhook_retention_days=7,
                queue_retention_days=getattr(settings, "zendesk_queue_retention_days", 30),
            )
        except Exception as e:
            logger.error("Zendesk scheduler iteration failed: %s", e)
            # Persist last_error for admin health visibility
            try:
                supa = get_supabase_client()
                # Merge with existing scheduler value to preserve other fields
                cur = await supa._exec(
                    lambda: supa.client.table("feature_flags")
                    .select("value")
                    .eq("key", "zendesk_scheduler")
                    .maybe_single()
                    .execute()
                )
                cur_val = (getattr(cur, "data", None) or {}).get("value") or {}
                cur_val["last_error"] = str(e)[:400]
                await supa._exec(
                    lambda: supa.client.table("feature_flags")
                    .upsert({
                        "key": "zendesk_scheduler",
                        "value": cur_val,
                    })
                    .execute()
                )
            except Exception:
                pass
        finally:
            await asyncio.sleep(interval_sec)
