from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.settings import settings
from app.integrations.zendesk.client import ZendeskClient
from app.integrations.zendesk import scheduler
from app.security.pii_redactor import redact_sensitive


logger = logging.getLogger("zendesk_phase6")


def _require_zendesk_settings() -> tuple[str, str, str]:
    subdomain = getattr(settings, "zendesk_subdomain", None)
    email = getattr(settings, "zendesk_email", None)
    api_token = getattr(settings, "zendesk_api_token", None)
    missing = [
        name
        for name, value in (
            ("ZENDESK_SUBDOMAIN", subdomain),
            ("ZENDESK_EMAIL", email),
            ("ZENDESK_API_TOKEN", api_token),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")
    return str(subdomain), str(email), str(api_token)


def _parse_ticket_ids(values: list[str]) -> list[int]:
    out: list[int] = []
    for raw in values:
        candidate = (raw or "").strip()
        if not candidate:
            continue
        if candidate.startswith("http"):
            # https://mailbird.zendesk.com/agent/tickets/552465
            parts = [p for p in candidate.split("/") if p]
            try:
                idx = parts.index("tickets")
                candidate = parts[idx + 1]
            except Exception:
                candidate = parts[-1]
        try:
            out.append(int(candidate))
        except Exception:
            raise SystemExit(f"Invalid ticket id/url: {raw}")
    return sorted(set(out))


@dataclass(frozen=True)
class Phase6FeedmeAudit:
    conversation_id: int
    hydration: str | None
    matched_chunks: int
    hydrated_chunks: int
    hydrated_window: dict[str, Any] | None
    content_chars: int


@dataclass(frozen=True)
class Phase6TicketRun:
    ticket_id: int
    posted: bool
    posted_comment_id: int | None
    posted_comment_public: bool | None
    reply_validation_issues: list[str]
    reply_topic_drift_issues: list[str]
    reply_risk_issues: list[str]
    posted_validation_issues: list[str]
    posted_topic_drift_issues: list[str]
    posted_risk_issues: list[str]
    internal_context_chars: int
    internal_context_tokens_est: int
    retrieval_best_score: float
    retrieval_confidence: float
    macro_hits: int
    kb_hits: int
    feedme_hits: int
    feedme_audit: list[Phase6FeedmeAudit]
    model: str
    provider: str
    started_at: str
    finished_at: str


def _best_effort_reply_text_from_comment(comment: Dict[str, Any]) -> tuple[str, bool]:
    if not isinstance(comment, dict):
        return "", False
    html_body = comment.get("html_body")
    if isinstance(html_body, str) and html_body.strip():
        return html_body, True
    body = comment.get("body")
    if isinstance(body, str) and body.strip():
        return body, False
    return "", False


def _pick_recent_private_comment(
    comments: list[dict[str, Any]], *, posted_after: datetime
) -> dict[str, Any] | None:
    skew = timedelta(seconds=120)
    for comment in comments or []:
        if not isinstance(comment, dict):
            continue
        if comment.get("public") is True:
            continue
        created = comment.get("created_at")
        if isinstance(created, str):
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                created_dt = None
            if created_dt and created_dt < (posted_after - skew):
                continue
        return comment
    return None


async def _audit_internal_retrieval(
    *,
    ticket_id: int,
    subject: str | None,
    description: str | None,
) -> tuple[scheduler.ZendeskQueryAgentIntent | None, scheduler.ZendeskInternalRetrievalPreflight | None, str]:
    subject_s = str(subject or "").strip()
    description_s = str(description or "").strip()
    ticket_text = "\n\n".join([p for p in (subject_s, description_s) if p]).strip()

    if not ticket_text:
        return None, None, ""

    intent, base_text, retrieval_query = scheduler._zendesk_build_query_agent_intent_and_query(
        ticket_text=ticket_text,
        subject=subject_s if subject_s else None,
    )

    decomposition_enabled = bool(getattr(settings, "zendesk_query_decomposition_enabled", True))
    decomposition_max_subqueries = int(getattr(settings, "zendesk_query_decomposition_max_subqueries", 3))
    issue_segments: list[str] = []
    if decomposition_enabled and intent is not None:
        issue_segments = scheduler._zendesk_extract_issue_segments(
            base_text,
            max_segments=decomposition_max_subqueries,
        )

    min_rel = float(getattr(settings, "zendesk_internal_retrieval_min_relevance", 0.35))
    max_per_source = int(getattr(settings, "zendesk_internal_retrieval_max_per_source", 3))
    confidence_threshold = float(getattr(settings, "zendesk_query_confidence_threshold", 0.6))
    max_reformulations = int(getattr(settings, "zendesk_query_reformulation_max_attempts", 2))
    expansion_count = int(getattr(settings, "zendesk_query_expansion_count", 2))

    if intent is not None and len(issue_segments) > 1:
        preflight = await scheduler._zendesk_run_multi_issue_internal_retrieval_preflight(
            subject=subject_s if subject_s else None,
            base_text=base_text,
            intent=intent,
            issue_segments=issue_segments,
            min_relevance=min_rel,
            max_per_source=max_per_source,
            max_subqueries=decomposition_max_subqueries,
            confidence_threshold=confidence_threshold,
            max_reformulations=max_reformulations,
            expansion_count=expansion_count,
        )
    else:
        preflight = await scheduler._zendesk_run_internal_retrieval_preflight(
            query=retrieval_query,
            intent=intent,
            min_relevance=min_rel,
            max_per_source=max_per_source,
            include_header=True,
        )

    _ = ticket_id  # reserved for future per-ticket retrieval logging
    return intent, preflight, ticket_text


async def _build_policy_context(
    *,
    subject: str,
    description: str,
    ticket_text: str,
) -> str:
    policy_macros: list[dict[str, Any]] = []
    try:
        log_macro = await scheduler._fetch_zendesk_macro_by_title(
            scheduler._POLICY_MACRO_TITLES["log_request"]
        )
        if log_macro:
            policy_macros.append(log_macro)
    except Exception:
        pass

    try:
        if scheduler._ticket_wants_refund(ticket_text):
            hint_text = f"{subject}\n{description}".lower()
            wants_yearly = bool(re.search(r"\b(yearly|annual|subscription)\b", hint_text))
            wants_pay_once = bool(re.search(r"\b(pay\s*once|lifetime|one[- ]time)\b", hint_text))
            if wants_yearly and not wants_pay_once:
                macro = await scheduler._fetch_zendesk_macro_by_title(
                    scheduler._POLICY_MACRO_TITLES["refund_yearly"]
                )
                if macro:
                    policy_macros.append(macro)
            elif wants_pay_once and not wants_yearly:
                macro = await scheduler._fetch_zendesk_macro_by_title(
                    scheduler._POLICY_MACRO_TITLES["refund_pay_once"]
                )
                if macro:
                    policy_macros.append(macro)
            else:
                for key in ("refund_pay_once", "refund_yearly"):
                    macro = await scheduler._fetch_zendesk_macro_by_title(
                        scheduler._POLICY_MACRO_TITLES[key]
                    )
                    if macro:
                        policy_macros.append(macro)
    except Exception:
        pass

    try:
        return scheduler._format_policy_macros_context(policy_macros)
    except Exception:
        return ""


async def _process_one_ticket(
    *,
    zc: ZendeskClient,
    ticket_id: int,
    provider: str,
    model: str,
    post: bool,
    verify_posted: bool,
    skip_generate: bool,
    add_tag: str | None,
    sleep_sec: float,
) -> Phase6TicketRun:
    started_at_dt = datetime.now(timezone.utc)

    ticket = await asyncio.to_thread(zc.get_ticket, ticket_id)
    subject = ticket.get("subject") if isinstance(ticket, dict) else None
    description = ticket.get("description") if isinstance(ticket, dict) else None

    intent, preflight, ticket_text = await _audit_internal_retrieval(
        ticket_id=ticket_id,
        subject=str(subject) if subject is not None else None,
        description=str(description) if description is not None else None,
    )

    internal_context = preflight.internal_context if preflight is not None else None
    policy_context = await _build_policy_context(
        subject=str(subject or ""),
        description=str(description or ""),
        ticket_text=ticket_text,
    )
    internal_chars, _internal_words, internal_tokens_est = scheduler._text_stats(internal_context)

    feedme_audit: list[Phase6FeedmeAudit] = []
    if preflight is not None:
        for item in preflight.retrieved_results or []:
            if not isinstance(item, dict) or item.get("source") != "feedme":
                continue
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            conv_raw = meta.get("id") or meta.get("conversation_id")
            try:
                conv_id = int(conv_raw)
            except Exception:
                continue
            hydration = meta.get("hydration")
            matched_indices = meta.get("matched_chunk_indices") or []
            hydrated_indices = meta.get("hydrated_chunk_indices") or []
            feedme_audit.append(
                Phase6FeedmeAudit(
                    conversation_id=conv_id,
                    hydration=str(hydration) if hydration is not None else None,
                    matched_chunks=len(matched_indices) if isinstance(matched_indices, list) else 0,
                    hydrated_chunks=len(hydrated_indices) if isinstance(hydrated_indices, list) else 0,
                    hydrated_window=meta.get("hydrated_window") if isinstance(meta.get("hydrated_window"), dict) else None,
                    content_chars=len(str(item.get("content") or "")),
                )
            )

    reply = ""
    if not skip_generate:
        run = await scheduler._generate_reply(
            ticket_id,
            subject,
            description,
            provider=provider,
            model=model,
        )
        reply = run.reply

    use_html = bool(getattr(settings, "zendesk_use_html", True))
    strictness = str(getattr(settings, "zendesk_drift_guard_strictness", "medium"))
    evidence_text = "\n\n".join([p for p in [internal_context, policy_context] if p]).strip()
    reply_validation: list[str] = []
    reply_topic_drift: list[str] = []
    reply_risk: list[str] = []
    if reply.strip():
        reply_validation = scheduler._quality_gate_issues(reply, use_html=use_html)
        reply_topic_drift = scheduler._topic_drift_issues(
            reply,
            ticket_text=ticket_text,
            intent=intent,
            strictness=strictness,
        )
        reply_risk = scheduler._risk_statement_issues(
            reply,
            ticket_text=ticket_text,
            evidence_text=evidence_text,
            intent=intent,
        )

    posted_comment_id: int | None = None
    posted_comment_public: bool | None = None
    posted_validation: list[str] = []
    posted_topic_drift: list[str] = []
    posted_risk: list[str] = []

    posted_after = datetime.now(timezone.utc)
    if post:
        await asyncio.to_thread(
            zc.add_internal_note,
            ticket_id,
            reply,
            add_tag=add_tag,
            use_html=use_html,
        )

        comments = await asyncio.to_thread(zc.get_ticket_comments, ticket_id, 5)
        comment = _pick_recent_private_comment(comments, posted_after=posted_after)
        if comment:
            posted_comment_id = comment.get("id") if isinstance(comment.get("id"), int) else None
            posted_comment_public = bool(comment.get("public")) if "public" in comment else None
            posted_text, posted_is_html = _best_effort_reply_text_from_comment(comment)

            posted_validation = scheduler._quality_gate_issues(posted_text, use_html=posted_is_html)
            posted_topic_drift = scheduler._topic_drift_issues(
                posted_text,
                ticket_text=ticket_text,
                intent=intent,
                strictness=strictness,
            )
            posted_risk = scheduler._risk_statement_issues(
                posted_text,
                    ticket_text=ticket_text,
                    evidence_text=evidence_text,
                    intent=intent,
                )
    elif verify_posted:
        comments = await asyncio.to_thread(zc.get_ticket_comments, ticket_id, 10)
        comment = None
        for c in comments or []:
            if not isinstance(c, dict):
                continue
            if c.get("public") is True:
                continue
            comment = c
            break
        if comment:
            posted_comment_id = comment.get("id") if isinstance(comment.get("id"), int) else None
            posted_comment_public = bool(comment.get("public")) if "public" in comment else None
            posted_text, posted_is_html = _best_effort_reply_text_from_comment(comment)

            posted_validation = scheduler._quality_gate_issues(posted_text, use_html=posted_is_html)
            posted_topic_drift = scheduler._topic_drift_issues(
                posted_text,
                ticket_text=ticket_text,
                intent=intent,
                strictness=strictness,
            )
            posted_risk = scheduler._risk_statement_issues(
                posted_text,
                ticket_text=ticket_text,
                evidence_text=evidence_text,
                intent=intent,
            )

    finished_at_dt = datetime.now(timezone.utc)

    result = Phase6TicketRun(
        ticket_id=ticket_id,
        posted=post,
        posted_comment_id=posted_comment_id,
        posted_comment_public=posted_comment_public,
        reply_validation_issues=reply_validation,
        reply_topic_drift_issues=reply_topic_drift,
        reply_risk_issues=reply_risk,
        posted_validation_issues=posted_validation,
        posted_topic_drift_issues=posted_topic_drift,
        posted_risk_issues=posted_risk,
        internal_context_chars=internal_chars,
        internal_context_tokens_est=internal_tokens_est,
        retrieval_best_score=float(preflight.best_score) if preflight is not None else 0.0,
        retrieval_confidence=float(preflight.confidence) if preflight is not None else 0.0,
        macro_hits=int(preflight.macro_hits) if preflight is not None else 0,
        kb_hits=int(preflight.kb_hits) if preflight is not None else 0,
        feedme_hits=int(preflight.feedme_hits) if preflight is not None else 0,
        feedme_audit=feedme_audit,
        model=model,
        provider=provider,
        started_at=started_at_dt.isoformat(),
        finished_at=finished_at_dt.isoformat(),
    )

    # Log a safe one-line summary (no ticket content).
    logger.info(
        "phase6_ticket_result ticket_id=%s posted=%s comment_id=%s validation=%s/%s drift=%s/%s risk=%s/%s feedme=%s",
        ticket_id,
        post,
        posted_comment_id,
        len(reply_validation),
        len(posted_validation),
        len(reply_topic_drift),
        len(posted_topic_drift),
        len(reply_risk),
        len(posted_risk),
        [
            {
                "conversation_id": a.conversation_id,
                "hydration": a.hydration,
                "matched": a.matched_chunks,
                "hydrated": a.hydrated_chunks,
            }
            for a in feedme_audit[:3]
        ],
    )

    if sleep_sec > 0:
        await asyncio.sleep(float(sleep_sec))

    return result


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 6 batch test: post internal notes + verify output validators + Phase 6 retrieval signals."
    )
    parser.add_argument(
        "--ticket-id",
        action="append",
        default=[],
        help="Zendesk ticket id or agent URL (repeatable).",
    )
    parser.add_argument("--provider", default="google", help='Agent provider (default: "google")')
    parser.add_argument("--model", default="gemini-2.5-pro", help='Agent model (default: "gemini-2.5-pro")')
    parser.add_argument("--post", action="store_true", help="Actually post internal notes (otherwise dry-run).")
    parser.add_argument(
        "--verify-posted",
        action="store_true",
        help="Validate the latest private comment on the ticket (even when not posting).",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="Skip generating a new reply (use with --verify-posted to only validate what’s already posted).",
    )
    parser.add_argument("--tag", default="", help="Optional Zendesk tag to add when posting.")
    parser.add_argument("--sleep-sec", type=float, default=0.7, help="Sleep between tickets (seconds).")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    if bool(args.post) and bool(args.skip_generate):
        raise SystemExit("--post requires generating a reply; remove --skip-generate.")

    ticket_ids = _parse_ticket_ids(list(args.ticket_id or []))
    if not ticket_ids:
        raise SystemExit("Provide at least one --ticket-id (id or URL).")

    _require_zendesk_settings()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = REPO_ROOT / "system_logs" / "backend"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"zendesk_phase6_test_{timestamp}.log"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        logging.FileHandler(log_path, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )
    # Reduce noisy dependency/module logs (and avoid accidentally logging ticket content).
    for noisy in (
        "httpx",
        "httpcore",
        "supabase",
        "postgrest",
        "langchain",
        "langgraph",
        "app.agents",
    ):
        try:
            logging.getLogger(noisy).setLevel(logging.WARNING)
        except Exception:
            continue

    provider = str(args.provider)
    model = str(args.model)
    post = bool(args.post)
    verify_posted = bool(args.verify_posted)
    skip_generate = bool(args.skip_generate)
    add_tag = str(args.tag).strip() or None
    sleep_sec = float(args.sleep_sec)

    zc = ZendeskClient(
        subdomain=str(settings.zendesk_subdomain),
        email=str(settings.zendesk_email),
        api_token=str(settings.zendesk_api_token),
        dry_run=not post,
    )

    results: list[Phase6TicketRun] = []
    failures: list[int] = []

    logger.info(
        "phase6_batch_start tickets=%s post=%s model=%s provider=%s log=%s",
        ",".join(str(t) for t in ticket_ids),
        post,
        model,
        provider,
        log_path,
    )

    for ticket_id in ticket_ids:
        try:
            logger.info("phase6_ticket_start ticket_id=%s", ticket_id)
            result = await _process_one_ticket(
                zc=zc,
                ticket_id=ticket_id,
                provider=provider,
                model=model,
                post=post,
                verify_posted=verify_posted,
                skip_generate=skip_generate,
                add_tag=add_tag,
                sleep_sec=sleep_sec,
            )
            results.append(result)
        except Exception as exc:
            failures.append(ticket_id)
            msg = redact_sensitive(str(exc))
            logger.exception(
                "phase6_ticket_failed ticket_id=%s error=%s",
                ticket_id,
                msg[:240],
            )

    json_path = log_dir / f"zendesk_phase6_test_{timestamp}.json"
    payload = {
        "run": {
            "timestamp": timestamp,
            "post": post,
            "model": model,
            "provider": provider,
            "ticket_ids": ticket_ids,
            "failures": failures,
            "log_path": str(log_path),
        },
        "results": [
            {
                **{
                    k: v
                    for k, v in asdict(r).items()
                    if k not in {"feedme_audit", "reply_validation_issues", "reply_topic_drift_issues", "reply_risk_issues", "posted_validation_issues", "posted_topic_drift_issues", "posted_risk_issues"}
                },
                "feedme_audit": [asdict(a) for a in r.feedme_audit],
                "reply_validation_issues": [redact_sensitive(i) for i in r.reply_validation_issues],
                "reply_topic_drift_issues": [redact_sensitive(i) for i in r.reply_topic_drift_issues],
                "reply_risk_issues": [redact_sensitive(i) for i in r.reply_risk_issues],
                "posted_validation_issues": [redact_sensitive(i) for i in r.posted_validation_issues],
                "posted_topic_drift_issues": [redact_sensitive(i) for i in r.posted_topic_drift_issues],
                "posted_risk_issues": [redact_sensitive(i) for i in r.posted_risk_issues],
            }
            for r in results
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    logger.info("phase6_batch_done successes=%s failures=%s json=%s", len(results), len(failures), json_path)


if __name__ == "__main__":
    asyncio.run(main())
