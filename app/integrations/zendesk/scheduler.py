from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List
import time

from langchain_core.messages import AIMessage, HumanMessage

from app.core.settings import settings
from app.db.supabase.client import get_supabase_client
from .client import ZendeskClient
from app.core.user_context import UserContext, user_context_scope
from app.agents.unified.agent_sparrow import run_unified_agent
from app.agents.orchestration.orchestration.state import GraphState
from app.agents.unified.tools import kb_search_tool
import re
from app.integrations.zendesk.attachments import fetch_ticket_attachments, summarize_attachments

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
    """Run Primary Agent with the same pipeline as chat to produce a high-quality reply.

    Uses raw subject/description (no meta-prompt), optional latest public comment context,
    user context scope for API keys, grounding preflight to decide web search, a light
    quality check on the final response, and an attachment fetch (logs/images) for
    additional context.
    """
    # Basic PII redaction (align with webhook redaction)
    _EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]{1,})@([A-Za-z0-9.-]{1,})")
    _PHONE_RE = re.compile(r"(?<!\d)(\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?){2}\d{4}(?!\d)")

    def _redact_pii(text: str | None) -> str | None:
        if not text or not isinstance(text, str):
            return text
        t = _EMAIL_RE.sub(lambda m: f"{m.group(1)[:2]}***@{m.group(2)}", text)
        t = _PHONE_RE.sub("[redacted-phone]", t)
        return t

    def _normalize_result_to_text(result_payload: Dict[str, Any] | None, state_obj: GraphState | None) -> str:
        result_messages = list((result_payload or {}).get("messages") or [])
        final_msg = None
        for candidate in reversed(result_messages):
            if not isinstance(candidate, AIMessage):
                continue
            content_str = str(getattr(candidate, "content", "") or "")
            # Skip planning/analysis artifacts
            if re.search(r"(?i):::thinking", content_str) or re.search(r"(?i)\bthinking\b", content_str):
                continue
            final_msg = candidate
            break
        # If everything was filtered, fall back to the last AI message
        if final_msg is None:
            for candidate in reversed(result_messages):
                if isinstance(candidate, AIMessage):
                    final_msg = candidate
                    break
        if final_msg is None:
            trace_id = getattr(state_obj, "trace_id", None)
            preview_payload = []
            for msg in result_messages[-3:]:
                content = getattr(msg, "content", "")
                if isinstance(content, str):
                    preview_payload.append(content[:120])
                else:
                    preview_payload.append(str(type(content)))
            logger.warning(
                "zendesk_unified_agent_no_ai_message session_id=%s trace_id=%s message_types=%s previews=%s",
                getattr(state_obj, "session_id", None),
                trace_id,
                [type(msg).__name__ for msg in result_messages],
                preview_payload,
            )
        text_out = ""
        if final_msg and getattr(final_msg, "content", None):
            text_out = str(final_msg.content).strip()
        # Strip any accidental planning/thinking markers from model output
        text_out = re.sub(r"(?im)^:::thinking\s*\n?", "", text_out)
        text_out = re.sub(r"(?im)^thinking\s*\n?", "", text_out)
        text_out = re.sub(r"(?im)^\*?\s*thoughts?:.*$", "", text_out)
        # Strip any accidental offers for channels we don't support (e.g., screen sharing)
        text_out = re.sub(r"(?im)^.*screen\\s*share.*$", "", text_out)
        text_out = re.sub(r"(?im)^.*screenshare.*$", "", text_out)
        # Collapse blank lines created by removals
        text_out = "\n".join([ln for ln in text_out.splitlines() if ln.strip() != ""])

        # Plain‑text normalization for Zendesk display (consistent headings and spacing)
        def _to_plaintext_for_zendesk(s: str) -> str:
            lines = []
            for raw in (s or "").splitlines():
                line = raw.rstrip()
                # Strip markdown heading markers (##, ###, etc.)
                m = re.match(r"^\s*#{1,6}\s*(.*)$", line)
                if m:
                    heading = m.group(1).strip()
                    # Normalize Pro Tips heading label
                    if re.match(r"(?im)^pro\s*tips(\s*💡)?$", heading):
                        heading = "Pro Tips"
                    lines.append(heading)
                    continue
                # Leave other lines as is
                lines.append(line)

            # Ensure single blank line after headings and between major sections
            out = []
            prev_was_heading = False
            for _, l in enumerate(lines):
                is_heading = bool(
                    re.match(
                        r"^(Empathetic Opening|Solution Overview|Try Now — Immediate Actions|Full Fix — Step-by-Step Instructions|Additional Context|Pro Tips|Supportive Closing)\s*$",
                        l,
                    )
                )
                if is_heading:
                    if out and out[-1].strip() != "":
                        out.append("")
                    out.append(l)
                    prev_was_heading = True
                    continue
                if prev_was_heading and l.strip() != "":
                    out.append("")
                    prev_was_heading = False
                out.append(l)

            merged = []
            seen_pro_tips = False
            i = 0
            while i < len(out):
                if re.match(r"^Pro Tips\s*$", out[i]):
                    if seen_pro_tips:
                        i += 1
                        continue
                    seen_pro_tips = True
                merged.append(out[i])
                i += 1

            final = []
            blank = 0
            for l in merged:
                if l.strip() == "":
                    blank += 1
                    if blank <= 1:
                        final.append("")
                else:
                    blank = 0
                    final.append(l)
            return "\n".join(final).strip()

        # HTML formatter for Zendesk internal notes (no inline CSS)
        def _format_html_for_zendesk(s: str) -> str:
            raw_lines = (s or "").splitlines()

            def strip_emphasis(text: str) -> str:
                t = text
                t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
                t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
                t = re.sub(r"\*([^*]+)\*", r"\1", t)
                t = re.sub(r"__([^_]+)__", r"\1", t)
                t = re.sub(r"_([^_]+)_", r"\1", t)
                return t

            lines = [strip_emphasis(l) for l in raw_lines]
            html_parts: List[str] = []
            buf: List[str] = []

            p_style = 'style="margin:0 0 14px; line-height:1.5;"'
            ul_style = 'style="margin:0 0 14px 20px; padding-left:18px; line-height:1.5;"'
            ol_style = 'style="margin:0 0 14px 20px; padding-left:18px; line-height:1.5;"'
            li_style = 'style="margin:4px 0; line-height:1.5;"'

            def flush_paragraph():
                nonlocal buf
                content = " ".join(x.strip() for x in buf if x.strip())
                if content:
                    html_parts.append(f"<p {p_style}>{content}</p>")
                buf = []

            def open_list(list_type: str):
                style = ul_style if list_type == "ul" else ol_style
                html_parts.append(f"<{list_type} {style}>")

            def close_list(list_type: str):
                html_parts.append(f"</{list_type}>")

            in_ol = False
            in_ul = False
            last_li_index: int | None = None

            def ensure_lists_closed():
                nonlocal in_ol, in_ul, last_li_index
                if in_ol:
                    close_list("ol")
                if in_ul:
                    close_list("ul")
                in_ol = False
                in_ul = False
                last_li_index = None

            heading_names = {
                "solution overview",
                "try now — immediate actions",
                "try now - immediate actions",
                "full fix — step-by-step instructions",
                "full fix - step-by-step instructions",
                "additional context",
                "pro tips",
                "supportive closing",
            }
            hidden_headings = {"empathetic opening", "supportive closing"}

            def is_heading(line: str) -> str | None:
                t = re.sub(r"^\s*#+\s*", "", line).strip()
                low = t.lower()
                if low in hidden_headings:
                    return "empathetic opening" if low == "empathetic opening" else "supportive closing"
                return t if low in heading_names else None

            def is_ordered_item(line: str) -> str | None:
                m = re.match(r"^\s*(\d+)[\.)]\s+(.*)$", line)
                return m.group(2).strip() if m else None

            def is_unordered_item(line: str) -> str | None:
                m = re.match(r"^\s*[-*]\s+(.*)$", line)
                if m:
                    return m.group(1).strip()
                m2 = re.match(r"^\s*([A-Z][A-Za-z0-9 \-/()]+):\s+(.*)$", line)
                if m2:
                    title, rest = m2.group(1).strip(), m2.group(2).strip()
                    return f"<strong>{title}:</strong> {rest}"
                return None

            style = str(getattr(settings, "zendesk_format_style", "compact")).lower()
            br_sep = "<br>" if style != "relaxed" else "<br><br>"

            def sentence_breaks(text: str) -> str:
                def repl(m: re.Match[str]) -> str:
                    return m.group(1) + br_sep + " "
                return re.sub(r"([.!?])\s+(?=[A-Z0-9\(])", repl, text)

            for raw in lines:
                line = raw.rstrip()
                h = is_heading(line)
                if h is not None:
                    ensure_lists_closed()
                    flush_paragraph()
                    if h.lower() not in hidden_headings:
                        heading_tag = getattr(settings, "zendesk_heading_level", "h3").lower()
                        if heading_tag not in {"h2", "h3"}:
                            heading_tag = "h3"
                        html_parts.append(f"<{heading_tag}>{h}</{heading_tag}>")
                    continue

                oi = is_ordered_item(line)
                if oi is not None:
                    flush_paragraph()
                    if not in_ol:
                        ensure_lists_closed()
                        open_list("ol")
                        in_ol = True
                    html_parts.append(f"<li {li_style}>{oi}</li>")
                    last_li_index = len(html_parts) - 1
                    continue

                ui = is_unordered_item(line)
                if ui is not None:
                    flush_paragraph()
                    if not in_ul:
                        ensure_lists_closed()
                        open_list("ul")
                        in_ul = True
                    html_parts.append(f"<li {li_style}>{ui}</li>")
                    last_li_index = len(html_parts) - 1
                    continue

                m = re.match(r"^\s*(Action|Where|Expected Result|If different)\s*:\s*(.*)$", line)
                if m:
                    label = m.group(1)
                    val = m.group(2).strip()
                    if last_li_index is not None and 0 <= last_li_index < len(html_parts):
                        prev = html_parts[last_li_index]
                        prev = prev.rstrip("</li>") + f" — <strong>{label}:</strong> {val}</li>"
                        html_parts[last_li_index] = prev
                    else:
                        if buf:
                            buf[-1] = (buf[-1] + f" — {label}: {val}").strip()
                        else:
                            buf.append(f"{label}: {val}")
                    continue

                buf.append(line)

            ensure_lists_closed()
            flush_paragraph()

            merged: List[str] = []
            seen_pro = False
            i = 0
            while i < len(html_parts):
                frag = html_parts[i]
                if frag.strip().lower() in ("<h2>pro tips</h2>", "<h3>pro tips</h3>"):
                    if seen_pro:
                        i += 1
                        continue
                    seen_pro = True
                merged.append(frag)
                i += 1

            def transform_paragraphs(html: str) -> str:
                # Force paragraph-style output (avoid sentence-per-line) and add relaxed line spacing.
                sentence_blocks = False

                def rewriter(m: re.Match[str]) -> str:
                    inner = m.group(1).strip()
                    if not inner:
                        return ""
                    if sentence_blocks:
                        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\(])", inner)
                        parts = [p.strip() for p in parts if p.strip()]
                        return "".join(f"<p>{p}</p>" for p in parts)
                    return f"<p>{sentence_breaks(inner)}</p>"

                content = "\n".join(merged)
                transformed = re.sub(r"<p>(.*?)</p>", rewriter, content, flags=re.DOTALL)
                return f'<div style="line-height:1.5;">{transformed}</div>'

            return transform_paragraphs("\n".join(merged))

        if getattr(settings, "zendesk_use_html", True):
            return _format_html_for_zendesk(text_out)
        return _to_plaintext_for_zendesk(text_out)

    # Compose the user query similar to main chat input
    parts_in: List[str] = []
    if subject:
        parts_in.append(str(subject))

    last_public = None
    try:
        if settings.zendesk_subdomain and settings.zendesk_email and settings.zendesk_api_token:
            zc = ZendeskClient(
                subdomain=str(settings.zendesk_subdomain),
                email=str(settings.zendesk_email),
                api_token=str(settings.zendesk_api_token),
                dry_run=True,
            )
            last_public = await asyncio.to_thread(zc.get_last_public_comment_snippet, ticket_id)
    except Exception:
        last_public = None
    if last_public:
        parts_in.append(last_public)

    if description:
        parts_in.append(str(description))

    attachments: List[Dict[str, Any]] = []
    try:
        attachments = fetch_ticket_attachments(ticket_id)
        att_summary = summarize_attachments(attachments)
        if att_summary:
            parts_in.append(f"Attachments summary for agent:\n{att_summary}")
    except Exception as e:
        logger.debug(f"attachment_fetch_failed ticket={ticket_id}: {e}")

    user_query_raw = "\n\n".join([p for p in parts_in if p]) or "(no description)"
    user_query = _redact_pii(user_query_raw) or user_query_raw

    session_id = f"zendesk-{ticket_id}"
    state: GraphState | None = None
    result: Dict[str, Any] | None = None

    try:
        async with user_context_scope(UserContext(user_id="zendesk-bot")):
            kb_ok = True
            try:
                kb_payload: Dict[str, Any] = {
                    "query": user_query,
                    "max_results": settings.primary_agent_min_kb_results,
                }
                min_conf = getattr(settings, "primary_agent_min_kb_relevance", None)
                if min_conf is not None:
                    kb_payload["min_confidence"] = min_conf

                kb_result = await kb_search_tool.ainvoke(kb_payload)
                kb_ok = isinstance(kb_result, str) and len(kb_result.strip()) > 50
            except Exception as e:
                logger.debug(f"KB preflight check failed: {e}, defaulting to web search")
                kb_ok = False

            provider = getattr(settings, "zendesk_agent_provider", None) or getattr(settings, "primary_agent_provider", "google")
            model = getattr(settings, "zendesk_agent_model", None) or getattr(settings, "primary_agent_model", "gemini-2.5-flash")

            state = GraphState(
                messages=[HumanMessage(content=user_query)],
                session_id=session_id,
                provider=provider,
                model=model,
                forwarded_props={
                    "force_websearch": not kb_ok,
                    "websearch_max_results": None,
                },
            )

            result = await run_unified_agent(state)
    finally:
        try:
            if attachments:
                from app.integrations.zendesk.attachments import cleanup_attachments
                cleanup_attachments(attachments)
        except Exception:
            pass

    return _normalize_result_to_text(result, state) or "Thank you for reaching out. We’re reviewing your request and will follow up shortly."


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
            # Try HTML if enabled; fallback signature without use_html for test stubs
            try:
                await asyncio.to_thread(zc.add_internal_note, tid, reply, add_tag="mb_auto_triaged", use_html=getattr(settings, "zendesk_use_html", True))
            except TypeError:
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
