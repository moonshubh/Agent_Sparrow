from __future__ import annotations

import asyncio
from dataclasses import dataclass
import html
import json
import logging
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.config import get_models_config, resolve_coordinator_config
from app.core.settings import settings
from app.db.supabase.client import get_supabase_client
from .client import ZendeskClient, ZendeskRateLimitError
from .exclusions import compute_ticket_exclusion
from .spam_guard import evaluate_spam_guard
from app.core.user_context import UserContext, user_context_scope
from app.agents.unified.agent_sparrow import run_unified_agent
from app.agents.orchestration.orchestration.state import GraphState
from app.agents.unified.tools import (
    kb_search_tool,
    db_unified_search_tool,
    db_context_search_tool,
    firecrawl_search_tool,
    firecrawl_fetch_tool,
    firecrawl_map_tool,
    firecrawl_extract_tool,
    web_search_tool,
)
import re
from app.integrations.zendesk.attachments import (
    fetch_ticket_attachments,
    summarize_attachments,
    convert_to_unified_attachments,
)
from app.security.pii_redactor import redact_pii

logger = logging.getLogger(__name__)

# Recursion limit for Zendesk ticket processing
# Keep low to prevent runaway agent loops (default is 400, which can take hours with Gemini Pro)
# 30 is enough for: KB search + FeedMe + web research + subagent calls + final response
ZENDESK_RECURSION_LIMIT = 30


_ZENDESK_PATTERN_CATEGORIES: tuple[str, ...] = (
    "account_setup",
    "sync_auth",
    "licensing",
    "sending",
    "performance",
    "features",
)


@dataclass(frozen=True, slots=True)
class ZendeskReplyResult:
    reply: str
    session_id: str
    ticket_id: str
    category: str | None
    redacted_ticket_text: str
    kb_articles_used: list[str]
    macros_used: list[str]
    learning_messages: list[Any]

@dataclass(frozen=True, slots=True)
class ZendeskQueryAgentProductContext:
    os: str | None
    provider: str | None
    version: str | None


@dataclass(frozen=True, slots=True)
class ZendeskQueryAgentIntent:
    primary_intent: str
    product_context: ZendeskQueryAgentProductContext
    signals: tuple[str, ...]
    sub_issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ZendeskInternalRetrievalPreflight:
    query: str
    retrieved_results: list[dict[str, Any]] | None
    internal_context: str | None
    macro_ok: bool
    kb_ok: bool
    feedme_ok: bool
    macro_choice: dict[str, Any] | None
    kb_articles_used: list[str]
    macros_used: list[str]
    confidence: float | None
    best_score: float | None
    macro_hits: int
    kb_hits: int
    feedme_hits: int


_ZENDESK_NOTE_SECTION_HEADINGS: set[str] = {
    "suggested reply",
    "issue summary",
    "root cause analysis",
    "relevant resources",
    "follow-up considerations",
    # Legacy headings (older prompt variants)
    "solution overview",
    "try now — immediate actions",
    "try now - immediate actions",
    "full fix — step-by-step instructions",
    "full fix - step-by-step instructions",
    "additional context",
    "pro tips",
    "empathetic opening",
    "supportive closing",
}

_ZENDESK_NOTE_NON_REPLY_HEADINGS: set[str] = _ZENDESK_NOTE_SECTION_HEADINGS - {
    "suggested reply"
}

_ZENDESK_META_LINE_PREFIXES: tuple[str, ...] = (
    "assistant",
    "system",
    "developer",
    "tool",
    "analysis",
    "reasoning",
    "thought process",
    "scratchpad",
    "plan",
    "approach",
    "notes",
)

_ZENDESK_META_INLINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bzendesk\s+(ticket\s+scenario|internal\s+note)\b"),
    re.compile(r"(?i)\b(i\s+(must|should|need\s+to))\b.*\b(output|reply|respond)\b"),
    re.compile(r"(?i)\b(do\s+not|don't)\b.*\b(mention|include|output|show)\b"),
    re.compile(
        r"(?i)\b(tool\s+results|synthesi[sz]ed\s+knowledge|synthesis|final\s+output)\b"
    ),
    re.compile(
        r"(?i)\b(db[-\s]?retrieval|kb[_\s-]?search|feedme[_\s-]?search|macro\s+id|kb\s+id)\b"
    ),
)


def _infer_ticket_category(
    ticket_text: str,
    similar_resolutions: List[Any],
) -> str | None:
    """Best-effort ticket category inference.

    Preference order:
    1) High-confidence majority from similar resolution hits
    2) Keyword heuristics on current ticket text
    """
    # 1) Similar-resolution vote (prefer top hit when confident)
    try:
        if similar_resolutions:
            top = similar_resolutions[0]
            top_cat = getattr(top, "category", None)
            top_sim = getattr(top, "similarity", None)
            if (
                top_cat in _ZENDESK_PATTERN_CATEGORIES
                and isinstance(top_sim, (int, float))
                and top_sim >= 0.78
            ):
                return str(top_cat)

            weights: Dict[str, float] = {}
            total = 0.0
            for r in similar_resolutions[:5]:
                cat = getattr(r, "category", None)
                sim = getattr(r, "similarity", None)
                if cat not in _ZENDESK_PATTERN_CATEGORIES or not isinstance(
                    sim, (int, float)
                ):
                    continue
                total += float(sim)
                weights[str(cat)] = weights.get(str(cat), 0.0) + float(sim)
            if total > 0 and weights:
                best_cat, best_score = max(weights.items(), key=lambda kv: kv[1])
                if best_score / total >= 0.55:
                    return best_cat
    except Exception:
        pass

    # 2) Keyword fallback
    return _infer_ticket_category_from_text(ticket_text)


def _infer_ticket_category_from_text(ticket_text: str) -> str | None:
    """Infer ticket category using keyword heuristics only (no retrieval)."""
    text = (ticket_text or "").lower()
    if not text:
        return None

    def _has_any(*needles: str) -> bool:
        return any(n in text for n in needles)

    # Licensing / billing
    if _has_any(
        "license",
        "subscription",
        "billing",
        "payment",
        "refund",
        "invoice",
        "renew",
        "cancel",
        "trial",
        "upgrade",
        "activation",
    ):
        return "licensing"

    # Performance / stability
    if _has_any(
        "slow",
        "lag",
        "freez",
        "not responding",
        "crash",
        "high cpu",
        "high memory",
        "spinning",
        "stuck loading",
    ):
        return "performance"

    # Sending problems (prefer explicit send failures / SMTP errors)
    if _has_any(
        "can't send",
        "cannot send",
        "unable to send",
        "sending error",
        "smtp error",
        "outgoing server",
        "message could not be sent",
        "550",
        "554",
        "relay",
    ):
        return "sending"

    # Sync/authentication (OAuth/IMAP/SMTP auth flows)
    if _has_any(
        "oauth",
        "authorization",
        "authenticate",
        "authentication",
        "app password",
        "two-factor",
        "2fa",
        "imap",
        "smtp",
        "gmail",
        "google",
        "outlook",
        "office 365",
        "microsoft",
        "yahoo",
    ):
        return "sync_auth"

    # Feature/how-to requests
    if _has_any(
        "feature request",
        "can you add",
        "does mailbird",
        "how do i",
        "how to",
        "is it possible",
        "unified inbox",
        "template",
        "signature",
        "calendar",
        "integration",
    ):
        return "features"

    # Account setup / login / adding accounts
    if _has_any(
        "add account",
        "set up",
        "setup",
        "sign in",
        "log in",
        "login",
        "password",
        "credentials",
        "cannot add account",
    ):
        return "account_setup"

    return None


_ZENDESK_RETRIEVAL_STOPWORDS: set[str] = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "but",
    "by",
    "can",
    "cant",
    "contacting",
    "could",
    "customer",
    "did",
    "do",
    "does",
    "else",
    "email",
    "for",
    "from",
    "had",
    "has",
    "have",
    "happiness",
    "he",
    "hello",
    "help",
    "her",
    "hi",
    "him",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "mail",
    "mailbird",
    "many",
    "me",
    "my",
    "no",
    "not",
    "of",
    "on",
    "or",
    "our",
    "please",
    "problem",
    "she",
    "should",
    "so",
    "team",
    "thank",
    "thanks",
    "that",
    "the",
    "their",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "too",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "without",
    "would",
    "you",
    "your",
}


def _zendesk_extract_keywords(text: str) -> set[str]:
    raw = str(text or "").lower()
    tokens = re.findall(r"[^\W_]+", raw, flags=re.UNICODE)
    return {t for t in tokens if len(t) >= 3 and t not in _ZENDESK_RETRIEVAL_STOPWORDS}


def _zendesk_min_overlap(query_keywords: set[str]) -> int:
    if len(query_keywords) >= 12:
        return 3
    if len(query_keywords) >= 6:
        return 2
    return 1


def _zendesk_lexically_relevant(
    query_keywords: set[str],
    candidate_text: str,
    *,
    min_overlap: int,
    min_item_coverage: float,
) -> bool:
    candidate_keywords = _zendesk_extract_keywords(candidate_text)
    if not query_keywords or not candidate_keywords:
        return True
    overlap = len(query_keywords & candidate_keywords)
    if overlap < min_overlap:
        return False
    return (overlap / max(1, len(candidate_keywords))) >= float(min_item_coverage)


def _zendesk_strip_attachment_block(ticket_text: str) -> tuple[str, str]:
    """Split `ticket_text` into (base_text, attachment_block).

    The attachment block begins at a line starting with "Attachments summary for agent:".
    """
    raw = str(ticket_text or "")
    if not raw.strip():
        return "", ""

    lines = raw.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    start: int | None = None
    for idx, line in enumerate(lines):
        if line.strip().lower().startswith("attachments summary for agent"):
            start = idx
            break

    if start is None:
        return raw.strip(), ""

    base = "\n".join(lines[:start]).strip()
    block = "\n".join(lines[start:]).strip()
    return base, block


def _zendesk_extract_attachment_signals(attachment_block: str) -> tuple[str, ...]:
    """Extract concrete technical signals (domains, error codes) from the attachment text."""
    block = str(attachment_block or "")
    if not block.strip():
        return ()

    candidates: list[str] = []

    # Domain / hostname-like tokens (e.g., smtp.gmail.com)
    candidates.extend(
        re.findall(r"\b[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}\b", block)
    )

    # 3-digit SMTP-like error codes (e.g., 550)
    candidates.extend(re.findall(r"\b\d{3}\b", block))

    # Common auth tokens
    candidates.extend(re.findall(r"\binvalid_grant\b", block, flags=re.IGNORECASE))

    seen: set[str] = set()
    ordered: list[str] = []
    for value in candidates:
        token = str(value or "").strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(token)

    return tuple(ordered)


def _zendesk_infer_provider(text: str) -> str | None:
    low = str(text or "").lower()
    if "gmail" in low or "google" in low:
        return "gmail"
    if "outlook" in low or "office 365" in low or "microsoft" in low:
        return "outlook"
    if "icloud" in low:
        return "icloud"
    if "yahoo" in low:
        return "yahoo"
    return None


def _zendesk_infer_primary_intent(text: str) -> str:
    low = str(text or "").lower()

    if _REFUND_INTENT_RE.search(low):
        return "refund"

    if re.search(r"\b(password|authenticate|authentication|oauth|sign[- ]in|login)\b", low):
        return "sync_auth"

    if re.search(r"\b(smtp|cannot send|can't send|sending error|relay denied|550|554)\b", low):
        return "sending"

    if re.search(r"\b(crash|freez|not responding|slow|lag)\b", low):
        return "performance"

    return "general"


def _zendesk_build_query_agent_intent_and_query(
    *, ticket_text: str, subject: str
) -> tuple[ZendeskQueryAgentIntent, str, str]:
    """Derive a retrieval intent and a safe, source-free internal retrieval query."""
    base_text, attachment_block = _zendesk_strip_attachment_block(ticket_text)
    signals = _zendesk_extract_attachment_signals(attachment_block)

    segments = _zendesk_extract_issue_segments(base_text, max_segments=2)
    primary_segment = segments[0] if segments else base_text

    combined_primary = "\n".join(
        [str(subject or ""), str(primary_segment or ""), attachment_block]
    ).strip()
    provider = _zendesk_infer_provider(combined_primary)
    primary_intent = _zendesk_infer_primary_intent(combined_primary)
    product_context = ZendeskQueryAgentProductContext(
        os=None,
        provider=provider,
        version=None,
    )

    sub_issues = _zendesk_extract_sub_issues(base_text)
    intent = ZendeskQueryAgentIntent(
        primary_intent=primary_intent,
        product_context=product_context,
        signals=signals,
        sub_issues=sub_issues,
    )

    parts = [f"Mailbird {str(subject or '').strip()}".strip(), base_text.strip()]
    extra_signals: list[str] = []
    for sig in signals:
        if len(extra_signals) >= 3:
            break
        if sig.lower().endswith(".log"):
            continue
        extra_signals.append(sig)
    if extra_signals:
        parts.append(" ".join(extra_signals))

    retrieval_query = " ".join(p for p in parts if p).strip()
    retrieval_query = re.sub(r"\s+", " ", retrieval_query).strip()
    return intent, base_text, retrieval_query


def _zendesk_reformulate_retrieval_query(
    *,
    previous_query: str,
    subject: str,
    base_text: str,
    intent: ZendeskQueryAgentIntent,
    attempt_index: int,
    expansion_count: int,
) -> str:
    """Lightweight, controlled query reformulation (no AI) to improve retrieval."""
    _ = subject, base_text
    previous = re.sub(r"\s+", " ", str(previous_query or "")).strip()

    expansions: list[str] = []
    if intent.primary_intent == "sync_auth":
        expansions = ["oauth", "authentication", "imap", "invalid_grant"]
    elif intent.primary_intent == "sending":
        expansions = ["smtp", "authentication", "relay", "outgoing"]
    elif intent.primary_intent == "refund":
        expansions = ["refund policy", "subscription", "billing"]

    provider = intent.product_context.provider
    if provider and provider.lower() not in previous.lower():
        expansions.insert(0, provider)

    wanted = max(1, int(expansion_count or 1))
    additions: list[str] = []
    for term in expansions:
        if len(additions) >= wanted:
            break
        if term.lower() in previous.lower():
            continue
        additions.append(term)

    if not additions:
        additions = [f"attempt{attempt_index + 1}"]

    return f"{previous} {' '.join(additions)}".strip()


def _zendesk_extract_issue_segments(ticket_text: str, *, max_segments: int = 4) -> list[str]:
    """Split an incoming ticket into explicit issue segments (primary + secondary)."""
    text = str(ticket_text or "").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []
    if len(paragraphs) == 1:
        return paragraphs

    segments: list[str] = [paragraphs[0]]
    for para in paragraphs[1:]:
        low = para.lower().strip()
        if re.match(r"^(also|additionally|another|secondly)\b", low):
            segments.append(para)
            continue
        if re.search(r"\b(refund|billing|payment|cannot|can't|unable|error|crash|password|authenticate|smtp|oauth)\b", low):
            segments.append(para)

    return segments[: max(1, int(max_segments or 1))]


_ZENDESK_TROUBLESHOOTING_RE = re.compile(
    r"(?i)\b(i tried|i have tried|tried|reinstall|reinstalling|restart|restarting|reboot|updated|reset)\b"
)


def _zendesk_extract_sub_issues(ticket_text: str) -> tuple[str, ...]:
    """Extract secondary issues, skipping 'I tried X' troubleshooting paragraphs."""
    segments = _zendesk_extract_issue_segments(ticket_text, max_segments=6)
    if len(segments) <= 1:
        return ()

    subs: list[str] = []
    for seg in segments[1:]:
        low = seg.lower()
        if _ZENDESK_TROUBLESHOOTING_RE.search(low):
            continue
        subs.append(seg.strip())

    return tuple(s for s in subs if s)


def _zendesk_pack_multi_issue_internal_context(
    *, issues: list[str], issue_contexts: list[str]
) -> str | None:
    if not issues or not issue_contexts:
        return None

    pairs = list(zip(issues, issue_contexts, strict=False))
    if not any(str(ctx or "").strip() for _, ctx in pairs):
        return None

    lines: list[str] = [
        "Internal knowledge (do NOT mention sources in the customer reply):",
        "",
    ]
    for idx, (issue, ctx) in enumerate(pairs, start=1):
        header = "Issue 1 (primary):" if idx == 1 else f"Issue {idx}:"
        lines.append(header)
        lines.append(str(issue or "").strip())
        ctx_clean = str(ctx or "").strip()
        if ctx_clean:
            lines.append("")
            lines.append(ctx_clean)
        lines.append("")

    packed = "\n".join(lines).strip()
    packed = re.sub(r"\n{3,}", "\n\n", packed).strip()
    return packed or None


def _zendesk_select_feedme_slice_indices(
    scores: dict[int, float],
    *,
    window_before: int,
    window_after: int,
    max_chunks: int,
) -> list[int]:
    if not scores:
        return []

    before = max(0, int(window_before))
    after = max(0, int(window_after))
    budget = max(1, int(max_chunks))

    windows: list[tuple[int, int, float]] = []
    for idx, score in scores.items():
        start = int(idx) - before
        end = int(idx) + after
        windows.append((start, end, float(score)))

    windows.sort(key=lambda w: w[0])

    clusters: list[dict[str, float | int]] = []
    for start, end, score in windows:
        if not clusters or start > int(clusters[-1]["end"]) + 1:
            clusters.append({"start": start, "end": end, "max_score": score})
            continue
        clusters[-1]["end"] = max(int(clusters[-1]["end"]), end)
        clusters[-1]["max_score"] = max(float(clusters[-1]["max_score"]), score)

    all_indices: list[int] = []
    for cluster in clusters:
        all_indices.extend(range(int(cluster["start"]), int(cluster["end"]) + 1))
    all_indices = sorted({i for i in all_indices if i >= 0})
    if len(all_indices) <= budget:
        return all_indices

    # Too wide: keep the strongest cluster only.
    best = max(
        clusters,
        key=lambda c: (float(c["max_score"]), -(int(c["end"]) - int(c["start"]))),
    )
    best_indices = [i for i in range(int(best["start"]), int(best["end"]) + 1) if i >= 0]
    if len(best_indices) <= budget:
        return best_indices

    # Still too many (very large window): center around the best-scoring chunk.
    best_chunk = max(
        (idx for idx in scores.keys() if int(best["start"]) <= idx <= int(best["end"])),
        key=lambda i: float(scores.get(i) or 0.0),
    )
    half = budget // 2
    start = max(int(best["start"]), best_chunk - half)
    end = start + budget - 1
    end = min(int(best["end"]), end)
    start = max(int(best["start"]), end - budget + 1)
    return [i for i in range(start, end + 1) if i >= 0]


def _zendesk_build_feedme_slice_content(
    chunks: list[dict[str, Any]],
) -> tuple[str, list[int]]:
    if not chunks:
        return "", []

    ordered = sorted(
        [c for c in chunks if isinstance(c, dict)],
        key=lambda c: int(c.get("chunk_index") or 0),
    )

    parts: list[str] = []
    indices: list[int] = []
    prev_index: int | None = None
    for chunk in ordered:
        try:
            idx = int(chunk.get("chunk_index"))
        except Exception:
            continue
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        if prev_index is not None and idx != prev_index + 1:
            parts.append("[...]")
        parts.append(content)
        indices.append(idx)
        prev_index = idx

    return "\n\n".join(parts).strip(), indices


def _zendesk_slice_kb_guidance(
    kb_text: str,
    *,
    tier: str,
    query_keywords: set[str],
    max_chars: int,
) -> str:
    _ = tier
    text = str(kb_text or "").strip()
    if not text:
        return ""

    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        if current_title is None:
            return
        body = "\n".join(current_lines).strip()
        sections.append((current_title, body))
        current_title = None
        current_lines = []

    for line in text.splitlines():
        if re.match(r"^\s*#{1,6}\s+", line):
            flush()
            current_title = line.strip()
            continue
        current_lines.append(line)

    flush()

    if not sections:
        return _trim_block(text, int(max_chars))

    if not query_keywords:
        title, body = sections[0]
        return _trim_block(f"{title}\n{body}".strip(), int(max_chars))

    best = max(
        sections,
        key=lambda s: len(query_keywords & _zendesk_extract_keywords(f"{s[0]}\n{s[1]}")),
    )
    selected = f"{best[0]}\n{best[1]}".strip()
    return _trim_block(selected, int(max_chars))


def _zendesk_slice_macro_guidance(
    macro_text: str,
    *,
    tier: str,
    query_keywords: set[str],
    max_chars: int,
) -> str:
    _ = tier
    raw = _normalize_macro_body(str(macro_text or ""))
    if not raw:
        return ""

    bullet_lines = [
        ln.strip()
        for ln in raw.splitlines()
        if re.match(r"^(?:[-*]|\d+[.)])\s+", ln.strip())
    ]

    if not bullet_lines:
        return _trim_block(raw, int(max_chars))

    kept: list[str] = []
    for line in bullet_lines:
        if not query_keywords:
            kept.append(line)
            continue
        overlap = len(query_keywords & _zendesk_extract_keywords(line))
        if overlap >= 1:
            kept.append(line)

    if not kept:
        return _trim_block("\n".join(bullet_lines[:5]).strip(), int(max_chars))

    return _trim_block("\n".join(kept).strip(), int(max_chars))


async def _zendesk_run_internal_retrieval_preflight(
    *,
    query: str,
    intent: ZendeskQueryAgentIntent | None = None,
    min_relevance: float,
    max_per_source: int,
    include_header: bool = True,
) -> ZendeskInternalRetrievalPreflight:
    _ = intent
    retrieved = await db_unified_search_tool.ainvoke(
        {
            "query": query,
            "sources": ["macros", "kb", "feedme"],
            "max_results_per_source": int(max_per_source),
            "min_relevance": float(min_relevance),
        }
    )
    results = list((retrieved or {}).get("results") or [])

    # Late-slice FeedMe results to keep only the most relevant chunk windows.
    for item in results:
        if not isinstance(item, dict) or str(item.get("source") or "") != "feedme":
            continue
        meta = item.get("metadata")
        meta = meta if isinstance(meta, dict) else {}

        conv_id = meta.get("id") or meta.get("conversation_id")
        try:
            conv_int = int(conv_id)
        except Exception:
            continue

        matched = meta.get("matched_chunks") or []
        matched_indices = meta.get("matched_chunk_indices") or []
        scores: dict[int, float] = {}
        if isinstance(matched, list):
            for row in matched:
                if not isinstance(row, dict):
                    continue
                try:
                    idx = int(row.get("chunk_index"))
                except Exception:
                    continue
                sim = row.get("similarity")
                try:
                    score = float(sim) if sim is not None else 1.0
                except Exception:
                    score = 1.0
                scores[idx] = max(scores.get(idx, 0.0), score)
        if isinstance(matched_indices, list):
            for idx_raw in matched_indices:
                try:
                    idx = int(idx_raw)
                except Exception:
                    continue
                scores[idx] = max(scores.get(idx, 0.0), 1.0)

        if not scores:
            continue

        wanted_indices = _zendesk_select_feedme_slice_indices(
            scores,
            window_before=1,
            window_after=1,
            max_chunks=10,
        )
        if not wanted_indices:
            continue

        supa = get_supabase_client()
        resp = await supa._exec(
            lambda: supa.client.table("feedme_text_chunks")
            .select("conversation_id,chunk_index,content")
            .eq("conversation_id", conv_int)
            .in_("chunk_index", wanted_indices)
            .order("chunk_index")
            .execute()
        )
        chunks = getattr(resp, "data", None) or []
        if not isinstance(chunks, list) or not chunks:
            continue

        sliced_content, slice_indices = _zendesk_build_feedme_slice_content(chunks)
        if not sliced_content:
            continue

        item["content"] = sliced_content
        item_meta = item.get("metadata")
        item_meta = item_meta if isinstance(item_meta, dict) else {}
        item["metadata"] = {
            **item_meta,
            "hydration": "late_slice",
            "slice_indices": slice_indices,
        }

    kb_articles_used: list[str] = []
    macros_used: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").lower()
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if source == "kb":
            kb_id = meta.get("id") or meta.get("url")
            if kb_id:
                kb_articles_used.append(str(kb_id))
        if source in {"macro", "macros"}:
            macro_id = meta.get("zendesk_id")
            if macro_id:
                macros_used.append(str(macro_id))

    preflight = _format_internal_retrieval_context(results, query=query)
    internal_context = preflight.get("context")
    if internal_context and not include_header:
        internal_context = re.sub(
            r"^Internal knowledge \(do NOT mention sources in the customer reply\):\s*",
            "",
            internal_context,
            flags=re.IGNORECASE,
        ).strip() or None

    best_score: float | None = None
    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            score = float(item.get("relevance_score") or 0.0)
        except Exception:
            continue
        best_score = score if best_score is None else max(best_score, score)

    return ZendeskInternalRetrievalPreflight(
        query=query,
        retrieved_results=results,
        internal_context=internal_context,
        macro_ok=bool(preflight.get("macro_ok")),
        kb_ok=bool(preflight.get("kb_ok")),
        feedme_ok=bool(preflight.get("feedme_ok")),
        macro_choice=None,
        kb_articles_used=kb_articles_used,
        macros_used=macros_used,
        confidence=None,
        best_score=best_score,
        macro_hits=int(preflight.get("macro_hits") or 0),
        kb_hits=int(preflight.get("kb_hits") or 0),
        feedme_hits=int(preflight.get("feedme_hits") or 0),
    )


async def _zendesk_run_multi_issue_internal_retrieval_preflight(
    *,
    subject: str,
    base_text: str,
    intent: ZendeskQueryAgentIntent,
    issue_segments: list[str],
    min_relevance: float,
    max_per_source: int,
    max_subqueries: int,
    confidence_threshold: float,
    max_reformulations: int,
    expansion_count: int,
) -> ZendeskInternalRetrievalPreflight:
    segments = [s for s in issue_segments if str(s or "").strip()]
    if not segments:
        return await _zendesk_run_internal_retrieval_preflight(
            query=f"Mailbird {subject} {base_text}".strip(),
            intent=intent,
            min_relevance=min_relevance,
            max_per_source=max_per_source,
            include_header=True,
        )

    segments = segments[: max(1, int(max_subqueries or 1))]
    issue_count = len(segments)

    secondary_budget = max(0, issue_count - 1)
    primary_budget = max(1, int(max_per_source) - secondary_budget)
    primary_query = f"Mailbird {subject} {segments[0]}".strip()

    best_primary = await _zendesk_run_internal_retrieval_preflight(
        query=primary_query,
        intent=intent,
        min_relevance=min_relevance,
        max_per_source=primary_budget,
        include_header=False,
    )

    # Only reformulate the primary issue (avoid exploding calls for secondary issues).
    current_query = primary_query
    for attempt in range(max(0, int(max_reformulations or 0))):
        confidence = float(best_primary.confidence or 0.0)
        if confidence >= float(confidence_threshold):
            break
        next_query = _zendesk_reformulate_retrieval_query(
            previous_query=current_query,
            subject=subject,
            base_text=base_text,
            intent=intent,
            attempt_index=attempt,
            expansion_count=expansion_count,
        )
        if not next_query or next_query.strip().lower() == current_query.strip().lower():
            break
        current_query = next_query
        candidate = await _zendesk_run_internal_retrieval_preflight(
            query=next_query,
            intent=intent,
            min_relevance=min_relevance,
            max_per_source=primary_budget,
            include_header=False,
        )
        if float(candidate.confidence or 0.0) > float(best_primary.confidence or 0.0):
            best_primary = candidate

    issue_contexts: list[str] = [best_primary.internal_context or ""]
    macro_ok = best_primary.macro_ok
    kb_ok = best_primary.kb_ok
    feedme_ok = best_primary.feedme_ok
    kb_articles_used = list(best_primary.kb_articles_used)
    macros_used = list(best_primary.macros_used)
    best_score = best_primary.best_score
    confidence = best_primary.confidence

    # Secondary issues: single pass with minimal budget.
    for seg in segments[1:]:
        secondary_query = f"Mailbird {subject} {seg}".strip()
        secondary_preflight = await _zendesk_run_internal_retrieval_preflight(
            query=secondary_query,
            intent=intent,
            min_relevance=min_relevance,
            max_per_source=1,
            include_header=False,
        )
        issue_contexts.append(secondary_preflight.internal_context or "")
        macro_ok = macro_ok or secondary_preflight.macro_ok
        kb_ok = kb_ok or secondary_preflight.kb_ok
        feedme_ok = feedme_ok or secondary_preflight.feedme_ok
        kb_articles_used.extend(list(secondary_preflight.kb_articles_used))
        macros_used.extend(list(secondary_preflight.macros_used))
        if secondary_preflight.best_score is not None:
            best_score = (
                secondary_preflight.best_score
                if best_score is None
                else max(best_score, secondary_preflight.best_score)
            )
        if secondary_preflight.confidence is not None:
            confidence = (
                secondary_preflight.confidence
                if confidence is None
                else max(confidence, secondary_preflight.confidence)
            )

    internal_context = _zendesk_pack_multi_issue_internal_context(
        issues=segments,
        issue_contexts=issue_contexts,
    )

    return ZendeskInternalRetrievalPreflight(
        query=primary_query,
        retrieved_results=None,
        internal_context=internal_context,
        macro_ok=macro_ok,
        kb_ok=kb_ok,
        feedme_ok=feedme_ok,
        macro_choice=None,
        kb_articles_used=kb_articles_used,
        macros_used=macros_used,
        confidence=confidence,
        best_score=best_score,
        macro_hits=0,
        kb_hits=0,
        feedme_hits=0,
    )


def _filter_similar_resolutions_for_ticket(
    ticket_text: str,
    resolutions: list[Any],
) -> list[Any]:
    if not resolutions:
        return []
    query_keywords = _zendesk_extract_keywords(ticket_text)
    if not query_keywords:
        return list(resolutions)

    min_overlap = _zendesk_min_overlap(query_keywords)
    filtered: list[Any] = []
    for res in resolutions:
        sim = getattr(res, "similarity", None)
        try:
            if isinstance(sim, (int, float)) and float(sim) >= 0.86:
                filtered.append(res)
                continue
        except Exception:
            pass

        prob = str(getattr(res, "problem_summary", "") or "")
        sol = str(getattr(res, "solution_summary", "") or "")
        text = f"{prob}\n{sol}".strip()
        if _zendesk_lexically_relevant(
            query_keywords,
            text,
            min_overlap=min_overlap,
            min_item_coverage=0.08,
        ):
            filtered.append(res)

    return filtered


def _format_similar_scenarios_md(
    ticket_id: str,
    query: str,
    resolutions: List[Any],
) -> str:
    """Render similar scenario hits into a compact markdown context file."""
    lines: List[str] = []
    lines.append("# Similar Scenarios (auto-retrieved)")
    lines.append("")
    lines.append(
        "Use these as reference patterns. Do NOT mention internal ticket IDs, similarity scores, "
        "or this file in the customer reply."
    )
    lines.append("")
    q = (query or "").strip()
    if q:
        q_preview = q[:800].rstrip()
        if len(q) > 800:
            q_preview += "…"
        lines.append(f"Ticket: {ticket_id}")
        lines.append("")
        lines.append("## Current Ticket (redacted)")
        lines.append(q_preview)
        lines.append("")

    if not resolutions:
        lines.append("_No close matches found in IssueResolutionStore._")
        return "\n".join(lines).strip() + "\n"

    for idx, res in enumerate(resolutions, 1):
        cat = getattr(res, "category", "") or ""
        sim = getattr(res, "similarity", None)
        created_at = getattr(res, "created_at", None)
        created_str = ""
        try:
            if created_at is not None:
                created_str = created_at.isoformat()
        except Exception:
            created_str = ""
        sim_str = f"{float(sim):.3f}" if isinstance(sim, (int, float)) else "n/a"
        lines.append(
            f"## Scenario {idx} ({cat or 'uncategorized'}, similarity {sim_str})"
        )
        if created_str:
            lines.append(f"- Created: {created_str}")
        lines.append("")
        prob = str(getattr(res, "problem_summary", "") or "").strip()
        sol = str(getattr(res, "solution_summary", "") or "").strip()
        if prob:
            lines.append("**Problem**")
            lines.append(prob)
            lines.append("")
        if sol:
            lines.append("**Resolution**")
            lines.append(sol)
            lines.append("")

    return "\n".join(lines).strip() + "\n"


async def _run_pattern_preflight(
    *,
    ticket_id: str,
    session_id: str,
    ticket_text: str,
    workspace_store: Any,
    issue_store: Any,
    playbook_extractor: Any | None,
    max_hits: int,
    min_similarity: float,
) -> Dict[str, Any]:
    """Populate workspace files for pattern-first Zendesk runs.

    Writes:
    - `/context/similar_scenarios.md` (+ legacy `/context/similar_resolutions.md`)
    - `/context/ticket_category.json` (when inferred)
    - `/context/ticket_playbook.md` (when a playbook is compiled)
    - `/playbooks/{category}.md` (compiled, verified procedures)
    """
    max_hits = max(0, min(10, int(max_hits)))
    min_similarity = float(min_similarity)

    seed_category = _infer_ticket_category_from_text(ticket_text)
    similar: list[Any] = []
    if max_hits > 0:
        try:
            if seed_category:
                similar = await issue_store.find_similar_resolutions(
                    query=ticket_text,
                    category=seed_category,
                    limit=max_hits,
                    min_similarity=min_similarity,
                )
                if not similar:
                    cross_min = min(0.95, min_similarity + 0.08)
                    similar = await issue_store.find_similar_resolutions(
                        query=ticket_text,
                        limit=max_hits,
                        min_similarity=cross_min,
                    )
            else:
                similar = await issue_store.find_similar_resolutions(
                    query=ticket_text,
                    limit=max_hits,
                    min_similarity=min_similarity,
                )
        except Exception as exc:  # pragma: no cover - best effort
            logger.debug(
                "issue_pattern_search_failed ticket_id=%s error=%s",
                ticket_id,
                str(exc)[:180],
            )
            similar = []

    similar = _filter_similar_resolutions_for_ticket(ticket_text, similar)
    md = _format_similar_scenarios_md(ticket_id, ticket_text, similar)
    await workspace_store.write_file("/context/similar_scenarios.md", md)
    await workspace_store.write_file("/context/similar_resolutions.md", md)

    if similar:
        logger.info(
            "issue_resolution_hit ticket_id=%s count=%s top_similarity=%s",
            ticket_id,
            len(similar),
            getattr(similar[0], "similarity", None),
        )

    category = _infer_ticket_category(ticket_text, similar)
    if seed_category and category and category != seed_category and similar:
        top_sim = getattr(similar[0], "similarity", None)
        if not isinstance(top_sim, (int, float)) or float(top_sim) < 0.86:
            category = seed_category
    playbook_compiled = False
    playbook_path: str | None = None

    if not category:
        return {
            "category": None,
            "similar_count": len(similar),
            "top_similarity": getattr(similar[0], "similarity", None) if similar else None,
            "playbook_compiled": False,
            "playbook_path": None,
        }

    await workspace_store.write_file(
        "/context/ticket_category.json",
        json.dumps(
            {
                "ticket_id": str(ticket_id),
                "session_id": str(session_id),
                "category": category,
                "derived_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        ),
    )

    if category in _ZENDESK_PATTERN_CATEGORIES and playbook_extractor is not None:
        try:
            playbook = await playbook_extractor.build_playbook_with_learned(category)
            playbook_md = playbook.to_prompt_context(include_pending=False).strip()
            if playbook_md:
                compiled = (
                    "<!-- auto-generated by Zendesk scheduler; source: "
                    "/playbooks/source + approved playbook_learned_entries -->\n\n"
                    f"{playbook_md}\n"
                )
                playbook_path = f"/playbooks/{category}.md"
                existing = await workspace_store.read_file(playbook_path)
                if not existing or existing.strip() != compiled.strip():
                    await workspace_store.write_file(playbook_path, compiled)

                await workspace_store.write_file(
                    "/context/ticket_playbook.md",
                    (
                        f"Ticket category: {category}\n"
                        f"Use verified procedures from: {playbook_path}\n"
                    ),
                )
                logger.info(
                    "playbook_compiled ticket_id=%s category=%s has_content=%s",
                    ticket_id,
                    category,
                    True,
                )
                playbook_compiled = True
        except Exception as exc:  # pragma: no cover - best effort
            logger.debug(
                "playbook_compile_failed ticket_id=%s category=%s error=%s",
                ticket_id,
                category,
                str(exc)[:180],
            )

    return {
        "category": category,
        "similar_count": len(similar),
        "top_similarity": getattr(similar[0], "similarity", None) if similar else None,
        "playbook_compiled": playbook_compiled,
        "playbook_path": playbook_path,
    }


def _strip_html_tags(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", text)


def _compact_one_line(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _summarize_problem_for_pattern_store(ticket_text: str) -> str:
    """Derive a short, high-signal problem summary from the ticket text."""
    raw = str(ticket_text or "").strip()
    if not raw:
        return ""

    # Prefer the first 1-2 paragraphs (subject/last public/description ordering).
    parts = [p.strip() for p in raw.split("\n\n") if p.strip()]
    chosen = "\n\n".join(parts[:2]) if parts else raw
    return _compact_one_line(chosen, max_chars=360)


def _summarize_solution_for_pattern_store(reply_text: str) -> str:
    """Derive a short solution summary from the agent reply (strip HTML + greeting)."""
    text = _strip_html_tags(str(reply_text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    # Drop the standard greeting line if present.
    greeting_prefix = (
        "Hi there, Many thanks for contacting the Mailbird Customer Happiness Team."
    )
    if text.startswith(greeting_prefix):
        text = text[len(greeting_prefix) :].strip()

    # Capture first ~2 sentences worth of content (max chars cap).
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = " ".join([s for s in sentences[:2] if s]).strip()
    if not summary:
        summary = text
    return _compact_one_line(summary, max_chars=420)


def _filter_messages_for_playbook_learning(messages: list[Any]) -> list[Any]:
    """Prepare a compact, safe conversation payload for playbook extraction.

    We include customer/agent turns plus truncated TOOL outputs so the extractor
    has enough context for short Zendesk runs, while avoiding prompt bloat.
    """
    MAX_HUMAN_CHARS = 8000
    MAX_AI_CHARS = 8000
    MAX_TOOL_CHARS = 2000

    def _truncate(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…\n\n[...truncated]"

    filtered: list[Any] = []
    for msg in messages or []:
        # LangChain BaseMessage instances
        if isinstance(msg, HumanMessage):
            content = getattr(msg, "content", "")
            if isinstance(content, str) and content.strip():
                filtered.append(
                    HumanMessage(
                        content=_truncate(redact_pii(content), MAX_HUMAN_CHARS)
                    )
                )
            continue

        if isinstance(msg, AIMessage):
            content = getattr(msg, "content", "")
            if isinstance(content, str) and content.strip():
                filtered.append(
                    AIMessage(content=_truncate(redact_pii(content), MAX_AI_CHARS))
                )
            continue

        if isinstance(msg, ToolMessage):
            content = getattr(msg, "content", "")
            if isinstance(content, str) and content.strip():
                safe = _truncate(redact_pii(content), MAX_TOOL_CHARS)
                filtered.append({"role": "tool", "content": safe})
            continue

        if isinstance(msg, dict):
            role = msg.get("role") or msg.get("type")
            content = msg.get("content")
            if not isinstance(content, str) or not content.strip():
                continue

            if role in {"human", "user"}:
                filtered.append(
                    {
                        "role": "user",
                        "content": _truncate(redact_pii(content), MAX_HUMAN_CHARS),
                    }
                )
            elif role in {"ai", "assistant"}:
                filtered.append(
                    {
                        "role": "assistant",
                        "content": _truncate(redact_pii(content), MAX_AI_CHARS),
                    }
                )
            elif role == "tool":
                filtered.append(
                    {
                        "role": "tool",
                        "content": _truncate(redact_pii(content), MAX_TOOL_CHARS),
                    }
                )
    return filtered


def _fire_and_forget(coro: Any, *, log_label: str) -> None:
    """Schedule a coroutine and surface exceptions via logger."""
    try:
        task = asyncio.create_task(coro)
    except Exception:
        return

    def _done(t: asyncio.Task) -> None:  # pragma: no cover - best effort
        try:
            exc = t.exception()
        except Exception:
            exc = None
        if exc is not None:
            logger.debug("%s_failed error=%s", log_label, str(exc)[:180])

    try:
        task.add_done_callback(_done)
    except Exception:
        pass


def _queue_post_resolution_learning(
    run: ZendeskReplyResult,
    *,
    dry_run: bool,
) -> None:
    """Best-effort post-resolution learning (pattern memory + playbook enrichment)."""
    if dry_run:
        return

    category = run.category
    if category not in _ZENDESK_PATTERN_CATEGORIES:
        return

    if bool(getattr(settings, "zendesk_issue_pattern_learning_enabled", True)):
        try:
            from app.agents.harness.store import IssueResolutionStore

            store = IssueResolutionStore()
            problem_summary = _summarize_problem_for_pattern_store(
                run.redacted_ticket_text
            )
            solution_summary = _summarize_solution_for_pattern_store(run.reply)

            # Extra safety: redact any stray PII in summaries.
            problem_summary = redact_pii(problem_summary)
            solution_summary = redact_pii(solution_summary)

            _fire_and_forget(
                store.store_resolution(
                    ticket_id=str(run.ticket_id),
                    category=category,
                    problem_summary=problem_summary,
                    solution_summary=solution_summary,
                    was_escalated=False,
                    kb_articles_used=run.kb_articles_used,
                    macros_used=run.macros_used,
                ),
                log_label="issue_pattern_store",
            )
            logger.info(
                "issue_pattern_stored_queued ticket_id=%s category=%s",
                run.ticket_id,
                category,
            )
        except Exception as exc:  # pragma: no cover - best effort
            logger.debug(
                "issue_pattern_store_queue_failed ticket_id=%s error=%s",
                run.ticket_id,
                str(exc)[:180],
            )

    if bool(getattr(settings, "zendesk_playbook_learning_enabled", True)):
        messages = _filter_messages_for_playbook_learning(run.learning_messages)
        if messages:
            try:
                from app.agents.unified.playbooks import PlaybookEnricher

                enricher = PlaybookEnricher()
                _fire_and_forget(
                    enricher.extract_from_conversation(
                        conversation_id=run.session_id,
                        messages=messages,
                        category=category,
                    ),
                    log_label="playbook_extraction",
                )
                logger.info(
                    "playbook_extraction_queued conversation_id=%s category=%s",
                    run.session_id,
                    category,
                )
            except Exception as exc:  # pragma: no cover - best effort
                logger.debug(
                    "playbook_extraction_queue_failed conversation_id=%s error=%s",
                    run.session_id,
                    str(exc)[:180],
                )


def _normalize_zendesk_heading_candidate(line: str) -> str:
    text = (line or "").strip()
    if not text:
        return ""

    # Strip common markdown / list prefixes.
    text = re.sub(r"^\s*#{1,6}\s*", "", text)
    text = re.sub(r"^\s*\d+\s*[\.)]\s*", "", text)
    text = re.sub(r"^\s*[-*]\s*", "", text)

    # Strip whole-line emphasis markers.
    text = re.sub(r"^\s*(\*\*|__|\*|_)", "", text)
    text = re.sub(r"(\*\*|__|\*|_)\s*$", "", text)

    text = text.strip().rstrip(":").strip()
    return text.lower()


def _extract_suggested_reply_only(note_text: str) -> str:
    """Best-effort extraction of the Suggested Reply block from a structured note."""
    raw = str(note_text or "").strip()
    if not raw:
        return ""

    lines = raw.splitlines()
    suggested_idx: int | None = None
    first_non_reply_heading_idx: int | None = None

    for idx, line in enumerate(lines):
        normalized = _normalize_zendesk_heading_candidate(line)
        if normalized == "suggested reply":
            suggested_idx = idx
            break
        if (
            normalized in _ZENDESK_NOTE_NON_REPLY_HEADINGS
            and first_non_reply_heading_idx is None
        ):
            first_non_reply_heading_idx = idx

    if suggested_idx is not None:
        end_idx = len(lines)
        for j in range(suggested_idx + 1, len(lines)):
            normalized = _normalize_zendesk_heading_candidate(lines[j])
            if (
                normalized in _ZENDESK_NOTE_SECTION_HEADINGS
                and normalized != "suggested reply"
            ):
                end_idx = j
                break
        extracted = "\n".join(lines[suggested_idx:end_idx]).strip()
        return extracted or raw

    # If the model produced only non-reply sections, keep any preamble above them.
    if first_non_reply_heading_idx is not None:
        preamble = "\n".join(lines[:first_non_reply_heading_idx]).strip()
        if preamble:
            return preamble

        # Otherwise, strip headings but keep content as a best-effort reply.
        stripped: List[str] = []
        for line in lines:
            normalized = _normalize_zendesk_heading_candidate(line)
            if normalized in _ZENDESK_NOTE_NON_REPLY_HEADINGS:
                continue
            stripped.append(line)
        cleaned = "\n".join(stripped).strip()
        return cleaned or raw

    return raw


def _sanitize_suggested_reply_text(text: str) -> str:
    """Normalize the agent output into a customer-ready Suggested Reply only."""
    extracted = _extract_suggested_reply_only(text)
    if not extracted:
        return ""

    def _greeting_start_index(lines: List[str]) -> int | None:
        for idx, ln in enumerate(lines):
            if not re.match(r"(?i)^hi\s+there\b", (ln or "").strip()):
                continue
            if re.search(r"(?i)mailbird\s+customer\s+happiness\s+team", ln):
                return idx
            # Split greeting: "Hi there," then "Many thanks ... Mailbird Customer Happiness Team."
            for j in range(idx + 1, min(idx + 4, len(lines))):
                nxt = lines[j] or ""
                if re.search(r"(?i)mailbird\s+customer\s+happiness\s+team", nxt):
                    return idx
                # Stop early if we hit substantive content.
                if nxt.strip() and not re.match(r"(?i)^many\s+thanks\b", nxt.strip()):
                    break
        return None

    def _strip_meta_preamble(raw: str) -> str:
        lines = [ln.rstrip() for ln in (raw or "").splitlines()]
        if not lines:
            return raw

        # Prefer the greeting start as the start of the customer reply.
        start = _greeting_start_index(lines)
        if start is not None:
            return "\n".join(lines[start:]).strip()

        return raw

    def _strip_meta_lines(raw: str) -> str:
        out: List[str] = []
        skip_block = False
        for ln in (raw or "").splitlines():
            line = ln.rstrip()
            if not line.strip():
                skip_block = False
                out.append(line)
                continue

            normalized = _normalize_zendesk_heading_candidate(line)
            if normalized in _ZENDESK_META_LINE_PREFIXES:
                skip_block = True
                continue

            if re.match(r"(?i)^\s*(assistant|system|developer|tool|user)\s*:\s*", line):
                skip_block = True
                continue

            if any(p.search(line) for p in _ZENDESK_META_INLINE_PATTERNS):
                continue

            # Skip follow-on bullet lines when we just removed a meta heading/preamble.
            if skip_block and re.match(r"^\s*([-*]|\d+[.)])\s+", line):
                continue

            out.append(line)

        cleaned = "\n".join(out)
        cleaned = re.sub(
            r"(?is)<\s*(analysis|thinking|reasoning)\b[^>]*>.*?<\s*/\s*\1\s*>",
            "",
            cleaned,
        )
        return cleaned.strip()

    # Drop any placeholder lines if they slip through.
    cleaned_lines: List[str] = []
    extracted = _strip_meta_lines(_strip_meta_preamble(extracted))
    for raw_line in extracted.splitlines():
        line = raw_line.rstrip()
        if re.search(r"(?i)\bpending\b", line) and re.search(
            r"(?i)fill\s+in\s+key\s+points", line
        ):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()

    def _is_heading_line(line: str) -> bool:
        return (
            _normalize_zendesk_heading_candidate(line) in _ZENDESK_NOTE_SECTION_HEADINGS
        )

    greeting_pattern = re.compile(
        r"(?i)\bhi\s+there\b.*?\bmailbird\s+customer\s+happiness\s+team\b\.?",
        re.DOTALL,
    )

    def _strip_greeting(line: str) -> str:
        return greeting_pattern.sub("", line).strip()

    meaningful_lines: List[str] = []
    cleaned_split = cleaned.splitlines()
    for idx, ln in enumerate(cleaned_split):
        if not ln.strip():
            continue
        if _is_heading_line(ln):
            continue
        # Skip greeting lines (support both single-line and split greeting).
        if idx < 6:
            if re.match(r"(?i)^hi\s+there\b", ln.strip()):
                # If the greeting is on one line, keep any trailing content after the greeting.
                stripped = _strip_greeting(ln)
                if stripped and stripped != ln.strip():
                    meaningful_lines.append(stripped)
                continue
            if re.search(r"(?i)mailbird\s+customer\s+happiness\s+team", ln):
                continue
        meaningful_lines.append(ln)
    if not meaningful_lines:
        return ""

    # Enforce greeting (two-line format).
    greeting = (
        "Hi there,\nMany thanks for contacting the Mailbird Customer Happiness Team."
    )
    first_window = "\n".join(cleaned.splitlines()[:6])
    has_hi = bool(re.search(r"(?i)\bhi\s+there\b", first_window))
    has_team = bool(
        re.search(r"(?i)mailbird\s+customer\s+happiness\s+team", first_window)
    )
    if not (has_hi and has_team):
        cleaned = f"{greeting}\n\n{cleaned}".strip()

    # Normalize legacy single-line greeting to the new split format.
    cleaned = re.sub(
        r"(?im)^hi\s+there\s*,\s*many\s+thanks\s+for\s+contacting\s+the\s+mailbird\s+customer\s+happiness\s+team\b\.?$",
        greeting,
        cleaned,
    )

    # Ensure a blank line after the greeting block for readability.
    split_lines = cleaned.splitlines()
    non_empty = [(idx, ln) for idx, ln in enumerate(split_lines) if ln.strip()]
    if len(non_empty) >= 2:
        idx1, ln1 = non_empty[0]
        idx2, ln2 = non_empty[1]
        if re.match(r"(?i)^hi\s+there\b", ln1.strip()) and re.search(
            r"(?i)mailbird\s+customer\s+happiness\s+team", ln2
        ):
            insert_at = idx2 + 1
            if insert_at < len(split_lines) and split_lines[insert_at].strip() != "":
                split_lines.insert(insert_at, "")
                cleaned = "\n".join(split_lines).strip()

    # Remove exclamation marks (tone rule) and clean common punctuation artifacts.
    cleaned = cleaned.replace("!", ".")
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)

    # Final cleanup pass in case meta slipped after greeting insertion.
    cleaned = _strip_meta_lines(cleaned)

    return cleaned.strip()


def _quality_gate_issues(note_text: str, *, use_html: bool) -> List[str]:
    """Hard-stop checks before posting the Zendesk note."""
    raw = str(note_text or "")
    if not raw.strip():
        return ["empty_reply"]

    # Preserve basic line boundaries for heading detection.
    if use_html:
        normalized = re.sub(r"(?i)<br\s*/?>", "\n", raw)
        normalized = re.sub(r"(?i)</p\s*>", "\n", normalized)
        normalized = re.sub(r"(?i)</h[23]\s*>", "\n", normalized)
        text_for_lines = _strip_html(normalized)
    else:
        text_for_lines = raw

    text_for_lines = text_for_lines.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in text_for_lines.splitlines() if ln.strip()]
    flat = re.sub(r"\s+", " ", " ".join(lines)).strip()

    issues: List[str] = []
    if "!" in flat:
        issues.append("contains_exclamation")

    # Block any chain-of-thought / planning leakage.
    for ln in lines[:140]:
        normalized = _normalize_zendesk_heading_candidate(ln)
        meta_key = normalized.split(" ")[0] if normalized else ""
        if (
            normalized in _ZENDESK_META_LINE_PREFIXES
            or meta_key in _ZENDESK_META_LINE_PREFIXES
        ):
            issues.append("contains_thinking_leakage")
            break
        if re.match(r"(?i)^:::\s*(?:thinking|think|analysis|reasoning)\b", ln):
            issues.append("contains_thinking_leakage")
            break
        if re.match(r"(?i)^</?\s*(?:analysis|thinking|reasoning|think)\b", ln):
            issues.append("contains_thinking_leakage")
            break

    greeting_window = " ".join(lines[:6])[:500]
    if not (
        re.search(r"(?i)\bhi\s+there\b", greeting_window)
        and re.search(r"(?i)mailbird\s+customer\s+happiness\s+team", greeting_window)
    ):
        issues.append("missing_greeting")

    for ln in lines[:80]:
        normalized_heading = _normalize_zendesk_heading_candidate(ln)
        if normalized_heading in _ZENDESK_NOTE_NON_REPLY_HEADINGS:
            issues.append("contains_non_reply_sections")
            break

    def _is_greeting_component_line(line: str) -> bool:
        stripped = (line or "").strip()
        if not stripped:
            return False
        if re.match(r"(?i)^hi\s+there\b", stripped):
            return True
        if re.match(r"(?i)^many\s+thanks\b", stripped) and re.search(
            r"(?i)mailbird\s+customer\s+happiness\s+team",
            stripped,
        ):
            return True
        # Legacy single-line greeting.
        if re.search(r"(?i)\bhi\s+there\b", stripped) and re.search(
            r"(?i)mailbird\s+customer\s+happiness\s+team",
            stripped,
        ):
            return True
        return False

    greeting_pattern = re.compile(
        r"(?i)\bhi\s+there\b.*?\bmailbird\s+customer\s+happiness\s+team\b\.?",
        re.DOTALL,
    )

    def _strip_greeting(line: str) -> str:
        return greeting_pattern.sub("", line).strip()

    content_lines: List[str] = []
    for idx, ln in enumerate(lines):
        if _normalize_zendesk_heading_candidate(ln) in _ZENDESK_NOTE_SECTION_HEADINGS:
            continue
        if idx < 6 and _is_greeting_component_line(ln):
            stripped = _strip_greeting(ln)
            # Only keep trailing content when the greeting shares a line with content.
            if stripped and stripped != ln.strip():
                content_lines.append(stripped)
            continue
        content_lines.append(ln)

    content_words = re.sub(r"\s+", " ", " ".join(content_lines)).strip().split()
    if len(content_words) < 5:
        issues.append("reply_too_short")

    if re.search(r"(?i)\bpending\b", flat):
        issues.append("contains_placeholder")

    if re.search(r"(?i)\b(db[- ]?retrieval|supabase|firecrawl|tavily)\b", flat):
        issues.append("mentions_internal_system")

    # Block prompt leakage / transcript-like output (common with reasoning models).
    if any(
        re.match(r"(?i)^(assistant|system|developer|tool|user)\s*:", ln)
        for ln in lines[:120]
    ):
        issues.append("contains_role_transcript")

    if any(p.search(flat) for p in _ZENDESK_META_INLINE_PATTERNS):
        issues.append("contains_prompt_leakage")

    return issues


def _format_zendesk_internal_note_html(
    text: str,
    *,
    heading_level: str = "h3",
    format_style: str = "compact",
) -> str:
    """Format a customer-ready Suggested Reply as readable Zendesk HTML.

    Accepts plain text with light Markdown (bold + inline code + lists) and
    produces Zendesk-safe HTML with paragraphs and nested lists.
    """

    safe_heading_level = (heading_level or "h3").lower()
    if safe_heading_level not in {"h2", "h3"}:
        safe_heading_level = "h3"

    def render_inline_md(raw: str) -> str:
        escaped = html.escape(raw or "", quote=False)

        # Inline code first so emphasis doesn't touch code spans.
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)

        # Bold
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", escaped)

        # Italic (best-effort, avoids **bold** which is already handled)
        escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
        escaped = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<em>\1</em>", escaped)

        return escaped

    heading_names = {
        # Legacy headings
        "solution overview",
        "try now — immediate actions",
        "try now - immediate actions",
        "full fix — step-by-step instructions",
        "full fix - step-by-step instructions",
        "additional context",
        "pro tips",
        "supportive closing",
        # Current Zendesk structured headings
        "suggested reply",
        "issue summary",
        "root cause analysis",
        "relevant resources",
        "follow-up considerations",
        # Hidden (sometimes emitted by older prompts)
        "empathetic opening",
    }
    hidden_headings = {"empathetic opening", "supportive closing", "suggested reply"}

    def is_heading(line: str) -> str | None:
        t = re.sub(r"^\s*#+\s*", "", line).strip()
        low = t.lower().rstrip(":").strip()
        if low in heading_names:
            return t.rstrip(":").strip()
        return None

    def list_indent(line: str) -> int:
        indent = 0
        for ch in line:
            if ch == " ":
                indent += 1
            elif ch == "\t":
                indent += 4
            else:
                break
        return indent

    def ordered_item(line: str) -> tuple[int, int, str] | None:
        m = re.match(r"^(\s*)(\d+)[\.)]\s+(.*)$", line)
        if m:
            indent = list_indent(m.group(1))
            num = int(m.group(2))
            content = m.group(3).strip()
            return indent, num, content

        # Handle bolded ordinals emitted by some prompts: "**2. Title**" -> "2. **Title**"
        m2 = re.match(r"^(\s*)(\*\*|__)(\d+)[\.)]\s+(.*?)(\2)\s*(.*)$", line)
        if not m2:
            return None
        indent = list_indent(m2.group(1))
        num = int(m2.group(3))
        title = m2.group(4).strip()
        tail = m2.group(6).strip()
        marker = m2.group(2)
        content = f"{marker}{title}{marker}"
        if tail:
            content += f" {tail}"
        return indent, num, content

    def unordered_item(line: str) -> tuple[int, str] | None:
        # Support common LLM bullet styles (Markdown '-'/'*' plus unicode bullets).
        m = re.match(r"^(\s*)(?:[-*]|[•●◦‣▪∙·])\s+(.*)$", line)
        if m:
            indent = list_indent(m.group(1))
            return indent, m.group(2).strip()
        m2 = re.match(r"^(\s*)([A-Z][A-Za-z0-9 \-/()]+):\s+(.*)$", line)
        if m2:
            indent = list_indent(m2.group(1))
            title, rest = m2.group(2).strip(), m2.group(3).strip()
            return (
                indent,
                f"<strong>{render_inline_md(title)}:</strong> {render_inline_md(rest)}",
            )
        return None

    style = (format_style or "compact").lower()
    sep = "<br>" if style != "relaxed" else "<br><br>"

    def render_paragraph(lines: list[str]) -> str | None:
        clean_lines = [ln.strip() for ln in lines if ln.strip()]
        if not clean_lines:
            return None

        # Preserve the split greeting as two lines (Hi there, + Many thanks...).
        if (
            len(clean_lines) >= 2
            and re.match(r"(?i)^hi\s+there\b", clean_lines[0])
            and re.search(r"(?i)mailbird\s+customer\s+happiness\s+team", clean_lines[1])
        ):
            parts = [render_inline_md(clean_lines[0]), render_inline_md(clean_lines[1])]
            for extra in clean_lines[2:]:
                parts.append(render_inline_md(extra))
            greeting_html = f"{parts[0]}&nbsp;<br>{parts[1]}"
            for extra in parts[2:]:
                greeting_html += f"<br>{extra}"
            # Explicit blank line after greeting (Zendesk often collapses <p> margins).
            return f"<p>{greeting_html}</p><br>&nbsp;<br>"

        content = " ".join(clean_lines)
        return f"<p>{render_inline_md(content)}</p>"

    html_parts: list[str] = []
    paragraph_buf: list[str] = []

    # List rendering with nesting based on indentation.
    list_stack: list[
        dict[str, Any]
    ] = []  # {"type": "ul"|"ol", "indent": int, "li_open": bool}

    def close_li_if_open() -> None:
        if list_stack and list_stack[-1].get("li_open"):
            if style == "relaxed":
                if not html_parts or not re.search(
                    r"(?i)<br\s*/?>\s*(?:&nbsp;|\u00a0)?\s*$", html_parts[-1]
                ):
                    html_parts.append("<br/>&nbsp;")
            html_parts.append("</li>")
            list_stack[-1]["li_open"] = False

    def close_lists_to_indent(target_indent: int) -> None:
        while list_stack and list_stack[-1]["indent"] > target_indent:
            close_li_if_open()
            html_parts.append(f"</{list_stack[-1]['type']}>")
            list_stack.pop()

    def close_all_lists() -> None:
        close_lists_to_indent(-1)

    def open_list(list_type: str, indent: int, start: int | None = None) -> None:
        start_attr = f' start="{start}"' if start and list_type == "ol" else ""
        html_parts.append(f"<{list_type}{start_attr}>")
        list_stack.append({"type": list_type, "indent": indent, "li_open": False})

    def begin_list_item(
        list_type: str, indent: int, *, start: int | None = None, content_html: str
    ) -> None:
        if not list_stack:
            open_list(list_type, indent, start=start)
        else:
            cur = list_stack[-1]
            if indent > cur["indent"]:
                # Nested list inside the current <li>.
                if not cur.get("li_open"):
                    html_parts.append("<li>")
                    cur["li_open"] = True
                open_list(list_type, indent, start=start)
            else:
                close_lists_to_indent(indent)
                if not list_stack:
                    open_list(list_type, indent, start=start)
                else:
                    cur = list_stack[-1]
                    if (
                        list_stack
                        and cur["indent"] == indent
                        and cur["type"] != list_type
                    ):
                        close_li_if_open()
                        html_parts.append(f"</{cur['type']}>")
                        list_stack.pop()
                        open_list(list_type, indent, start=start)

        # Same level list item: close prior <li> first.
        close_li_if_open()
        html_parts.append(f"<li>{content_html}")
        list_stack[-1]["li_open"] = True

    def append_to_current_list_item(
        fragment_html: str, *, as_paragraph: bool = False
    ) -> None:
        if not list_stack or not list_stack[-1].get("li_open"):
            return
        if as_paragraph:
            html_parts.append(f"<p>{fragment_html}</p>")
        else:
            html_parts.append(fragment_html)

    heading_dedup: set[str] = set()

    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            # Paragraph boundary.
            para = render_paragraph(paragraph_buf)
            if para:
                close_all_lists()
                html_parts.append(para)
            paragraph_buf = []
            continue

        h = is_heading(line)
        if h is not None:
            h_norm = h.strip().lower()
            if h_norm in heading_dedup:
                continue
            heading_dedup.add(h_norm)
            para = render_paragraph(paragraph_buf)
            if para:
                close_all_lists()
                html_parts.append(para)
            paragraph_buf = []
            close_all_lists()
            if h_norm not in hidden_headings:
                html_parts.append(
                    f"<{safe_heading_level}>{render_inline_md(h)}</{safe_heading_level}>"
                )
            continue

        ordered = ordered_item(line)
        if ordered is not None:
            indent, num, item_text = ordered
            para = render_paragraph(paragraph_buf)
            if para:
                close_all_lists()
                html_parts.append(para)
            paragraph_buf = []

            start = None
            if (
                not list_stack
                or list_stack[-1]["type"] != "ol"
                or list_stack[-1]["indent"] != indent
            ):
                start = num
            begin_list_item(
                "ol", indent, start=start, content_html=render_inline_md(item_text)
            )
            continue

        unordered = unordered_item(line)
        if unordered is not None:
            indent, item_text = unordered
            para = render_paragraph(paragraph_buf)
            if para:
                close_all_lists()
                html_parts.append(para)
            paragraph_buf = []

            if list_stack:
                current = list_stack[-1]
                if (
                    current["type"] == "ul"
                    and current.get("li_open")
                    and indent < current["indent"]
                ):
                    indent = current["indent"]
                elif (
                    current["type"] == "ol"
                    and current.get("li_open")
                    and indent <= current["indent"]
                ):
                    indent = current["indent"] + 2

            content_html = (
                item_text
                if item_text.startswith("<strong>")
                else render_inline_md(item_text)
            )
            begin_list_item("ul", indent, content_html=content_html)
            continue

        m = re.match(
            r"^\s*(Action|Where|Expected Result|If different)\s*:\s*(.*)$", line
        )
        if m and list_stack:
            label = m.group(1)
            val = m.group(2).strip()
            append_to_current_list_item(
                f" — <strong>{render_inline_md(label)}:</strong> {render_inline_md(val)}"
            )
            continue

        if list_stack and list_indent(line) > list_stack[-1]["indent"]:
            if list_stack[-1]["type"] == "ol":
                append_to_current_list_item(
                    render_inline_md(line.strip()), as_paragraph=True
                )
            else:
                append_to_current_list_item(f"{sep}{render_inline_md(line.strip())}")
            continue

        if (
            list_stack
            and list_stack[-1]["type"] == "ol"
            and list_stack[-1].get("li_open")
        ):
            append_to_current_list_item(
                render_inline_md(line.strip()), as_paragraph=True
            )
            continue

        paragraph_buf.append(line)

    para = render_paragraph(paragraph_buf)
    if para:
        close_all_lists()
        html_parts.append(para)
    close_all_lists()

    # Ensure the greeting is present as an early paragraph (downstream quality gate expects it).
    greeting_window = "\n".join(html_parts[:3])
    has_hi = bool(re.search(r"(?i)\bhi\s+there\b", greeting_window))
    has_team = bool(
        re.search(r"(?i)mailbird\s+customer\s+happiness\s+team", greeting_window)
    )
    if not (has_hi and has_team):
        insert_at = (
            1
            if html_parts
            and html_parts[0].lower().startswith(f"<{safe_heading_level}>")
            else 0
        )
        html_parts.insert(
            insert_at,
            "<p>Hi there,&nbsp;<br>Many thanks for contacting the Mailbird Customer Happiness Team.</p><br>&nbsp;<br>",
        )

    merged: list[str] = []
    seen_pro = False
    for frag in html_parts:
        low = frag.strip().lower()
        if low in ("<h2>pro tips</h2>", "<h3>pro tips</h3>"):
            if seen_pro:
                continue
            seen_pro = True
        merged.append(frag)

    return "\n".join(merged).strip()


def _trim_block(text: str, max_chars: int | None) -> str:
    content = str(text or "").strip()
    if not content:
        return ""
    if max_chars is None:
        return content
    try:
        max_chars_int = int(max_chars)
    except Exception:
        return content
    if max_chars_int <= 0:
        return content
    if len(content) <= max_chars_int:
        return content
    return content[: max(1, max_chars_int - 1)].rstrip() + "…"


def _text_stats(text: str | None) -> tuple[int, int, int]:
    if not text:
        return 0, 0, 0
    s = str(text)
    chars = len(s)
    words = len(re.findall(r"\S+", s))
    tokens_est = chars // 4
    return chars, words, tokens_est


def _format_internal_retrieval_context(
    results: List[Dict[str, Any]],
    *,
    query: str,
) -> Dict[str, Any]:
    macro_min = float(getattr(settings, "zendesk_macro_min_relevance", 0.55))
    # Zendesk support prefers recall over aggressive KB filtering; keep thresholds
    # aligned with the retrieval preflight (zendesk_internal_retrieval_min_relevance).
    kb_min = float(
        getattr(settings, "zendesk_internal_retrieval_min_relevance", 0.35)
    )
    feedme_min = float(getattr(settings, "zendesk_feedme_min_relevance", 0.45))
    max_per_source = int(
        getattr(settings, "zendesk_internal_retrieval_max_per_source", 5)
    )

    query_keywords = _zendesk_extract_keywords(query)
    min_overlap = _zendesk_min_overlap(query_keywords)

    def keep_item(
        item: Dict[str, Any],
        *,
        min_score: float,
        bypass_score: float,
        min_item_coverage: float,
    ) -> bool:
        score = float(item.get("relevance_score") or 0.0)
        if score < float(min_score):
            return False
        if score >= float(bypass_score):
            return True
        if not query_keywords:
            return True

        title = str(item.get("title") or "")
        raw_content = item.get("content") or item.get("snippet") or ""
        if item.get("source") == "macro":
            content = _normalize_macro_body(str(raw_content))
        else:
            content = str(raw_content)
        candidate_text = f"{title}\n{content}"
        return _zendesk_lexically_relevant(
            query_keywords,
            candidate_text,
            min_overlap=min_overlap,
            min_item_coverage=min_item_coverage,
        )

    macro_bypass = max(0.85, macro_min + 0.25)
    kb_bypass = max(0.80, kb_min + 0.25)
    feedme_bypass = max(0.80, feedme_min + 0.25)

    macro_hits = [
        r
        for r in results
        if r.get("source") == "macro"
        and keep_item(
            r,
            min_score=macro_min,
            bypass_score=macro_bypass,
            min_item_coverage=0.12,
        )
    ]
    kb_hits = [
        r
        for r in results
        if r.get("source") == "kb"
        and keep_item(
            r,
            min_score=kb_min,
            bypass_score=kb_bypass,
            min_item_coverage=0.08,
        )
    ]
    feedme_hits = [
        r
        for r in results
        if r.get("source") == "feedme"
        and keep_item(
            r,
            min_score=feedme_min,
            bypass_score=feedme_bypass,
            min_item_coverage=0.08,
        )
    ]

    macro_hits = sorted(
        macro_hits,
        key=lambda r: float(r.get("relevance_score") or 0.0),
        reverse=True,
    )
    kb_hits = sorted(
        kb_hits,
        key=lambda r: float(r.get("relevance_score") or 0.0),
        reverse=True,
    )
    feedme_hits = sorted(
        feedme_hits,
        key=lambda r: float(r.get("relevance_score") or 0.0),
        reverse=True,
    )

    lines: List[str] = []
    if macro_hits or kb_hits or feedme_hits:
        lines.append(
            "Internal knowledge (do NOT mention sources in the customer reply):"
        )

    def add_section(title: str, items: List[Dict[str, Any]], max_items: int) -> None:
        if not items:
            return
        lines.append("")
        lines.append(f"{title}:")
        for item in items[:max_items]:
            item_title = str(item.get("title") or "Untitled").strip()
            score = float(item.get("relevance_score") or 0.0)
            raw_content = item.get("content") or item.get("snippet") or ""
            if item.get("source") == "macro":
                content = _normalize_macro_body(str(raw_content))
            else:
                content = str(raw_content).strip()
            if not content:
                continue

            meta = (
                item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            )
            url = str(meta.get("url") or "").strip() if isinstance(meta, dict) else ""

            header = f"- {item_title} (relevance ~{score:.2f})"
            if url:
                header += f" — {url}"
            lines.append(header)
            lines.append(content)
            lines.append("")

    # Macro-first: if a good macro exists, show it first.
    max_items = max(1, min(10, max_per_source))

    def _content_len(items: list[dict[str, Any]]) -> int:
        total = 0
        for item in items[:max_items]:
            raw_content = item.get("content") or item.get("snippet") or ""
            if item.get("source") == "macro":
                content = _normalize_macro_body(str(raw_content))
            else:
                content = str(raw_content).strip()
            total += len(content)
        return total

    macro_chars = _content_len(macro_hits)
    kb_chars = _content_len(kb_hits)
    feedme_chars = _content_len(feedme_hits)

    best_score: float | None = None
    for group in (macro_hits, kb_hits, feedme_hits):
        if not group:
            continue
        try:
            score = float(group[0].get("relevance_score") or 0.0)
        except Exception:
            continue
        best_score = score if best_score is None else max(best_score, score)

    add_section("Macro guidance", macro_hits, max_items=max_items)
    add_section("Knowledge base", kb_hits, max_items=max_items)
    add_section("Similar past examples", feedme_hits, max_items=max_items)

    context = "\n".join(lines).strip()
    context = re.sub(r"\n{3,}", "\n\n", context).strip()
    return {
        "context": context or None,
        "macro_ok": bool(macro_hits),
        "kb_ok": bool(kb_hits),
        "feedme_ok": bool(feedme_hits),
        "best_score": best_score,
        "macro_hits": len(macro_hits),
        "kb_hits": len(kb_hits),
        "feedme_hits": len(feedme_hits),
        "macro_context_chars": macro_chars,
        "kb_context_chars": kb_chars,
        "feedme_context_chars": feedme_chars,
        "macro_results": macro_hits,
    }


def _zendesk_resolve_context_clashes(
    items: list[dict[str, Any]], *, resolution: str
) -> list[dict[str, Any]]:
    """Resolve contradictory/duplicate context items (e.g., outdated KB vs newer KB)."""

    def canonical_title(title: str) -> str:
        cleaned = re.sub(r"\s*\(.*?\)\s*$", "", str(title or "")).strip().lower()
        cleaned = re.sub(r"(?i)\b(updated|new)\b", "", cleaned).strip()
        cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned).strip()
        return cleaned

    def parse_last_updated(meta: dict[str, Any]) -> datetime | None:
        raw = meta.get("last_updated")
        if not raw:
            return None
        try:
            value = str(raw)
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except Exception:
            return None

    resolved = str(resolution or "").strip().lower()
    if resolved != "prefer_newer":
        return list(items or [])

    by_key: dict[str, list[dict[str, Any]]] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        key = canonical_title(title) or title.strip().lower()
        by_key.setdefault(key, []).append(item)

    selected: list[dict[str, Any]] = []
    for group in by_key.values():
        if len(group) == 1:
            selected.append(group[0])
            continue

        def score(item: dict[str, Any]) -> tuple[int, float]:
            meta = item.get("metadata")
            meta = meta if isinstance(meta, dict) else {}
            dt = parse_last_updated(meta)
            dt_score = int(dt.timestamp()) if dt else 0
            confidence = float(item.get("confidence_score") or 0.0)
            return (dt_score, confidence)

        selected.append(max(group, key=score))

    return selected


def _format_internal_retrieval_context_quality_first(
    results: list[dict[str, Any]],
    *,
    query: str,
    include_header: bool,
    max_per_source: int,
    total_budget_tokens: int,
    confidence_high: float,
    confidence_low: float,
) -> dict[str, Any]:
    """Pack internal context by selecting the most relevant paragraphs first.

    This is designed to keep the prompt under budget while maximizing signal density.
    """
    _ = confidence_high, confidence_low

    query_keywords = _zendesk_extract_keywords(query)
    query_phrases = [
        s.lower()
        for s in re.findall(r"\b[a-zA-Z0-9]+_[a-zA-Z0-9]+\b", str(query or ""))
        if s
    ]
    max_items = max(1, min(10, int(max_per_source)))
    char_budget = max(120, int(total_budget_tokens) * 4)

    candidates: list[tuple[tuple[int, float], str]] = []
    best_score: float | None = None

    def paragraphs(text: str) -> list[str]:
        return [p.strip() for p in re.split(r"\n{2,}", str(text or "")) if p.strip()]

    def excerpt(text: str, max_len: int) -> str:
        raw = str(text or "").strip()
        if max_len <= 0 or not raw:
            return ""
        if len(raw) <= max_len:
            return raw

        lower = raw.lower()

        def find_anchor() -> tuple[int, int] | None:
            for phrase in query_phrases:
                idx = lower.find(phrase)
                if idx != -1:
                    return idx, idx + len(phrase)
            for kw in query_keywords:
                idx = lower.find(kw.lower())
                if idx != -1:
                    return idx, idx + len(kw)
            return None

        anchor = find_anchor()
        if not anchor:
            return raw[: max_len - 1].rstrip() + "…"

        anchor_start, anchor_end = anchor
        start = max(0, anchor_start - 28)
        end = start + max_len
        if end < anchor_end:
            start = max(0, anchor_end - max_len)
            end = start + max_len
        end = min(len(raw), end)
        start = max(0, min(start, max(0, end - max_len)))

        snippet = raw[start:end].strip()
        if start > 0:
            snippet = "…" + snippet.lstrip()
        if end < len(raw):
            snippet = snippet.rstrip() + "…"
        return snippet

    for item in (results or [])[: max_items * 3]:
        if not isinstance(item, dict):
            continue
        try:
            relevance = float(item.get("relevance_score") or 0.0)
        except Exception:
            relevance = 0.0
        best_score = relevance if best_score is None else max(best_score, relevance)

        raw_content = item.get("content") or item.get("snippet") or ""
        content = str(raw_content)
        for para in paragraphs(content):
            if not query_keywords:
                overlap = 1
            else:
                overlap = len(query_keywords & _zendesk_extract_keywords(para))
            if overlap <= 0:
                continue
            candidates.append(((overlap, relevance), para))

    candidates.sort(key=lambda c: c[0], reverse=True)

    lines: list[str] = []
    if include_header:
        lines.append("Internal knowledge (do NOT mention sources in the customer reply):")
        lines.append("")

    remaining = char_budget - sum(len(line) + 1 for line in lines)
    for _, para in candidates:
        if remaining <= 0:
            break
        snippet = excerpt(para, remaining)
        lines.append(snippet)
        lines.append("")
        remaining -= len(snippet) + 2

    context = "\n".join(lines).strip()
    context = re.sub(r"\n{3,}", "\n\n", context).strip()
    return {"context": context or None, "best_score": best_score}


def _topic_drift_issues(
    reply: str,
    *,
    ticket_text: str,
    intent: ZendeskQueryAgentIntent,
    strictness: str,
) -> list[str]:
    """Detect when a draft reply drifts into unrelated topics."""
    _ = ticket_text
    strict = str(strictness or "").strip().lower()
    if strict not in {"low", "medium", "high"}:
        strict = "medium"

    issues: list[str] = []
    low_reply = str(reply or "").lower()

    mentions_payment = bool(
        re.search(r"\b(payment method|payment|credit card|invoice)\b", low_reply)
    )
    if mentions_payment and intent.primary_intent not in {"refund", "licensing"}:
        issues.append("topic_drift_payment_methods")

    return issues


_REFUND_POLICY_WINDOW_RE = re.compile(r"(?i)\bwithin\s+(\d{1,3})\s+days\b")


def _risk_statement_issues(
    reply: str,
    *,
    ticket_text: str,
    evidence_text: str,
    intent: ZendeskQueryAgentIntent,
) -> list[str]:
    """Flag risky claims in the reply that are not supported by evidence."""
    _ = ticket_text
    issues: list[str] = []

    if intent.primary_intent != "refund":
        return issues

    reply_text = str(reply or "")
    evidence = str(evidence_text or "")

    match = _REFUND_POLICY_WINDOW_RE.search(reply_text)
    if not match:
        return issues

    days = match.group(1)
    if days and days not in evidence:
        issues.append("risk_unsupported_refund_policy")

    return issues


def _select_macro_candidate(
    results: List[Dict[str, Any]],
    *,
    min_relevance: float,
    max_candidates: int = 3,
) -> Dict[str, Any] | None:
    """Pick the strongest macro ahead of drafting to avoid the wrong template."""
    macros = [
        r
        for r in results or []
        if r.get("source") == "macro"
        and float(r.get("relevance_score") or 0.0) >= min_relevance
    ]
    if not macros:
        return None

    ordered = sorted(
        macros, key=lambda r: float(r.get("relevance_score") or 0.0), reverse=True
    )
    top = ordered[0]
    top_score = float(top.get("relevance_score") or 0.0)
    runner_up = ordered[1] if len(ordered) > 1 else None
    runner_score = float(runner_up.get("relevance_score") or 0.0) if runner_up else 0.0

    # Confidence: relative lead over runner-up, capped to sensible bounds.
    denom = max(top_score + runner_score, 1e-6)
    confidence = max(0.35, min(0.99, top_score / denom))

    alternates = []
    for alt in ordered[1:max_candidates]:
        alt_title = str(alt.get("title") or "").strip() or "Alternate macro"
        alt_score = float(alt.get("relevance_score") or 0.0)
        alternates.append(f"{alt_title} (~{alt_score:.2f})")

    title = str(top.get("title") or "Macro").strip()
    macro_id = (top.get("metadata") or {}).get("zendesk_id")
    reason = "Highest semantic match vs. other macros"
    if runner_score:
        reason += f" (+{top_score - runner_score:.2f} vs. next)"

    return {
        "macro_id": macro_id,
        "title": title,
        "confidence": confidence,
        "reason": reason,
        "alternates": alternates,
    }


def _format_macro_selector_context(choice: Dict[str, Any] | None) -> str | None:
    if not choice:
        return None
    lines = [
        "Macro selector (internal — do not cite macros/templates to the customer):"
    ]
    title = choice.get("title") or "Macro"
    conf = choice.get("confidence")
    macro_id = choice.get("macro_id")
    reason = choice.get("reason")
    if conf is not None:
        lines.append(f"- Recommended template: {title} (confidence ~{conf:.2f})")
    else:
        lines.append(f"- Recommended template: {title}")
    if macro_id:
        lines.append(f"- Internal ref: {macro_id}")
    if reason:
        lines.append(f"- Why: {reason}")
    alts = choice.get("alternates") or []
    if alts:
        lines.append(f"- Alternates: {', '.join(alts[:2])}")
    lines.append(
        "- Use it as guidance; write a customer-ready reply directly with no IDs."
    )
    return "\n".join(lines)


_POLICY_MACRO_TITLES: dict[str, str] = {
    "log_request": "TECH: Request log file - Using Mailbird Number 2",
    "screenshot_request": "REQUEST:: Ask for a screenshot",
    "refund_pay_once": "REFUND::[Refund Experiment][Premium Pay Once] 50% Refund",
    "refund_yearly": "REFUND::[Refund Experiment][Premium Yearly] 50% Refund",
}

_POLICY_MACRO_CACHE: dict[str, dict[str, Any]] = {}
_POLICY_MACRO_CACHE_TTL_SEC = 60 * 30


def _normalize_macro_body(raw: str) -> str:
    if not raw:
        return ""

    normalized = str(raw)
    # Preserve basic structure from HTML macros.
    normalized = re.sub(r"(?i)<br\s*/?>", "\n", normalized)
    normalized = re.sub(r"(?i)</p\s*>", "\n\n", normalized)
    normalized = re.sub(r"(?i)</li\s*>", "\n", normalized)
    normalized = re.sub(r"(?i)<li\b[^>]*>", "- ", normalized)
    normalized = re.sub(r"(?i)</ul\s*>", "\n", normalized)
    normalized = re.sub(r"(?i)</ol\s*>", "\n", normalized)

    normalized = _strip_html(normalized)
    normalized = html.unescape(normalized)

    lines: List[str] = []
    for ln in normalized.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        if not ln.strip():
            lines.append("")
            continue
        lines.append(re.sub(r"[ \t]+", " ", ln).strip())

    out = []
    blank = 0
    for ln in lines:
        if not ln.strip():
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        out.append(ln)
    return "\n".join(out).strip()


def _count_step_lines(text: str) -> int:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    step_lines = [ln for ln in lines if re.match(r"^(?:\d+[.)]|[-*])\s+", ln)]
    return len(step_lines)


async def _fetch_zendesk_macro_by_title(title: str) -> Dict[str, Any] | None:
    wanted = str(title or "").strip()
    if not wanted:
        return None

    cache_key = wanted.lower()
    cached = _POLICY_MACRO_CACHE.get(cache_key)
    if cached and (
        time.time() - float(cached.get("fetched_at") or 0.0)
        < _POLICY_MACRO_CACHE_TTL_SEC
    ):
        macro_obj = cached.get("macro")
        return macro_obj if isinstance(macro_obj, dict) else None

    supa = get_supabase_client()
    try:
        resp = await supa._exec(
            lambda: supa.client.table("zendesk_macros")
            .select("zendesk_id,title,comment_value,updated_at")
            .eq("title", wanted)
            .limit(1)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        if not rows:
            # Best-effort fallback for minor title drift.
            resp = await supa._exec(
                lambda: supa.client.table("zendesk_macros")
                .select("zendesk_id,title,comment_value,updated_at")
                .ilike("title", wanted)
                .limit(1)
                .execute()
            )
            rows = getattr(resp, "data", None) or []
        if not rows:
            return None

        row = rows[0] if isinstance(rows, list) else rows
        macro = {
            "title": row.get("title") or wanted,
            "content": _normalize_macro_body(row.get("comment_value") or ""),
            "updated_at": row.get("updated_at"),
            "zendesk_id": row.get("zendesk_id"),
        }
        _POLICY_MACRO_CACHE[cache_key] = {"macro": macro, "fetched_at": time.time()}
        return macro
    except Exception as exc:
        logger.debug(
            "zendesk_policy_macro_fetch_failed title=%s error=%s",
            wanted,
            str(exc)[:180],
        )
        return None


def _format_policy_macros_context(macros: List[Dict[str, Any]]) -> str | None:
    usable = [
        m
        for m in (macros or [])
        if isinstance(m, dict) and str(m.get("content") or "").strip()
    ]
    if not usable:
        return None

    lines: List[str] = [
        "Policy macros (internal reference — do NOT paste verbatim; paraphrase but keep all steps when used):"
    ]
    for m in usable:
        title = str(m.get("title") or "Macro").strip()
        body = str(m.get("content") or "").strip()
        lines.append(f"\n{title}:")
        lines.append(body)
    return "\n".join(lines).strip()


_REFUND_INTENT_RE = re.compile(r"(?i)\brefund\b|\bmoney\s+back\b|\bcancel(?:lation)?\b")


def _ticket_wants_refund(ticket_text: str) -> bool:
    return bool(_REFUND_INTENT_RE.search(str(ticket_text or "")))


def _ticket_seems_unclear(
    *,
    subject: str | None,
    description: str | None,
    last_public: str | None,
) -> bool:
    # If there's already meaningful back-and-forth, it's not unclear.
    if isinstance(last_public, str) and len(last_public.strip()) >= 120:
        return False

    subj = str(subject or "").strip()
    desc = str(description or "").strip()
    combined = " ".join([subj, desc]).strip()
    if not combined:
        return True

    # Obvious low-signal descriptions.
    if desc and re.fullmatch(
        r"(?i)\s*(hi|hello|hey|test|asdf|n/?a|none|help|pls|please)\b[\s!.]*",
        desc,
    ):
        return True

    # If there's a clear issue keyword, treat it as sufficiently informative.
    if re.search(
        r"(?i)\b(error|can\s*not|cannot|can't|won't|does\s+not|crash|freeze|stuck|sync|imap|smtp|password|login|activate|activation|license|refund|payment|billing)\b",
        combined,
    ):
        return False

    words = re.findall(r"[A-Za-z0-9]{2,}", combined)
    if len(words) < 10 and len(combined) < 90:
        return True
    return False


def _build_web_search_query(
    *, subject: str | None, description: str | None, fallback: str
) -> str:
    raw = "\n\n".join([p for p in [subject, description] if p]) or fallback
    redacted = redact_pii(raw) or raw
    # Remove any attachment summary blocks (often too noisy for search).
    redacted = re.split(r"(?im)^attachments\s+summary\s+for\s+agent\s*:\s*$", redacted)[
        0
    ].strip()
    query = re.sub(r"\s+", " ", redacted).strip()
    if query and "mailbird" not in query.lower():
        query = f"Mailbird {query}"
    return query[:400].strip()


def _strip_html(text: str) -> str:
    if not text:
        return ""
    try:
        cleaned = re.sub(r"(?is)<!--.*?-->", " ", str(text))
        # Strip common HTML tags while preserving angle-bracket placeholders
        # like "<your user name>" that appear in support instructions.
        cleaned = re.sub(
            r"(?is)<\s*/?\s*(?:p|br|div|span|strong|em|b|i|u|ul|ol|li|h1|h2|h3|h4|h5|h6|table|thead|tbody|tr|td|th|pre|code|blockquote|a|img|hr)\b[^>]*>",
            " ",
            cleaned,
        )
        return cleaned
    except Exception:
        return text


def _format_web_research_context(items: List[Dict[str, Any]]) -> str | None:
    lines: List[str] = []
    for item in items:
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "Web result").strip()
        content = str(item.get("content") or "").strip()
        if not url and not content:
            continue
        lines.append(f"- {title}" + (f" — {url}" if url else ""))
        if content:
            lines.append(content)
            lines.append("")
    if not lines:
        return None
    context = (
        "Web research (do NOT mention sources in the customer reply):\n"
        + "\n".join(lines)
    )
    context = re.sub(r"\n{3,}", "\n\n", context).strip()
    return context


async def _prefetch_web_research(
    *,
    search_query: str,
    max_pages: int,
) -> str | None:
    """Best-effort web context using Firecrawl first, Tavily as fallback."""
    query = (search_query or "").strip()
    if not query:
        return None

    scrape_options = {
        # Ask Firecrawl to return markdown for results when possible.
        "formats": ["markdown"],
        "onlyMainContent": True,
    }

    urls: List[str] = []
    try:
        res = await firecrawl_search_tool.ainvoke(
            {
                "query": query,
                "limit": max(1, min(10, int(max_pages) * 2)),
                "sources": ["web"],
                "scrape_options": scrape_options,
            }
        )
        if isinstance(res, dict) and res.get("error"):
            raise RuntimeError(str(res.get("error")))

        data = res.get("data") if isinstance(res, dict) else None
        web_list = []
        if isinstance(data, dict):
            web_list = data.get("web") or data.get("results") or []
        if isinstance(web_list, list):
            for row in web_list:
                if not isinstance(row, dict):
                    continue
                url = row.get("url") or row.get("link")
                if isinstance(url, str) and url.startswith("http"):
                    urls.append(url)
                if len(urls) >= max_pages:
                    break
    except Exception:
        urls = []

    # Fallback: Tavily for URLs when Firecrawl search is unavailable.
    if not urls:
        try:
            tavily = await web_search_tool.ainvoke(
                {
                    "query": query,
                    "max_results": max(3, min(10, int(max_pages) * 2)),
                    "include_images": False,
                }
            )
            if isinstance(tavily, dict):
                raw_urls = tavily.get("urls") or []
                if isinstance(raw_urls, list):
                    urls = [
                        u
                        for u in raw_urls
                        if isinstance(u, str) and u.startswith("http")
                    ][:max_pages]
        except Exception:
            urls = []

    if not urls:
        return None

    fetched: List[Dict[str, Any]] = []
    for url in urls[:max_pages]:
        try:
            page = await firecrawl_fetch_tool.ainvoke(
                {
                    "url": url,
                    "formats": ["markdown"],
                }
            )
            if not isinstance(page, dict) or page.get("error"):
                continue
            markdown = page.get("markdown")
            data = page.get("data")
            if markdown is None and isinstance(data, dict):
                markdown = data.get("markdown")
            content = _strip_html(str(markdown or "")) if markdown else ""
            content = content.strip()
            title = ""
            try:
                title = (
                    str(page.get("metadata", {}).get("title") or "")
                    if isinstance(page.get("metadata"), dict)
                    else ""
                )
            except Exception:
                title = ""
            fetched.append(
                {"url": url, "title": title or "Web result", "content": content}
            )
        except Exception:
            continue

    return _format_web_research_context(fetched)


async def _firecrawl_support_bundle(
    *,
    search_query: str,
    domains: List[str],
    max_pages: int,
    include_screenshots: bool,
) -> str | None:
    """Domain-scoped Firecrawl bundle for Mailbird help sources."""
    query = (search_query or "").strip()
    if not query or not domains:
        return None

    urls: List[str] = []
    seen: set[str] = set()
    for domain in domains:
        try:
            mapped = await firecrawl_map_tool.ainvoke(
                {
                    "url": domain,
                    "limit": max(1, min(20, max_pages * 4)),
                    "search": query[:120],
                    "include_subdomains": True,
                }
            )
            raw_urls = []
            if isinstance(mapped, dict):
                raw_urls = (
                    mapped.get("links")
                    or mapped.get("urls")
                    or mapped.get("data", {}).get("links")
                    or mapped.get("data", {}).get("urls")
                    or []
                )
            for u in raw_urls or []:
                if not isinstance(u, str):
                    continue
                if not u.startswith("http"):
                    continue
                if u in seen:
                    continue
                seen.add(u)
                urls.append(u)
                if len(urls) >= max_pages * 2:
                    break
        except Exception:
            continue
        if len(urls) >= max_pages * 2:
            break

    if not urls:
        return None

    fetch_formats = ["markdown"]
    if include_screenshots:
        fetch_formats.append("screenshot")

    page_summaries: List[str] = []
    for url in urls[:max_pages]:
        try:
            page = await firecrawl_fetch_tool.ainvoke(
                {
                    "url": url,
                    "formats": fetch_formats,
                    "only_main_content": True,
                }
            )
            if isinstance(page, dict) and "screenshot" in page:
                # Drop large binary blobs to keep context lightweight.
                page = dict(page)
                page.pop("screenshot", None)
            markdown = None
            if isinstance(page, dict):
                if page.get("markdown"):
                    markdown = page.get("markdown")
                elif isinstance(page.get("data"), dict):
                    markdown = page.get("data", {}).get("markdown")
            snippet = _strip_html(str(markdown or "")).strip() if markdown else ""
            title = ""
            try:
                title = (
                    str(page.get("metadata", {}).get("title") or "")
                    if isinstance(page, dict)
                    else ""
                )
            except Exception:
                title = ""
            if snippet:
                page_summaries.append(f"- {title or 'Page'} — {url}\n  {snippet}")
        except Exception:
            continue

    extract_lines: List[str] = []
    try:
        schema = {
            "type": "object",
            "properties": {
                "steps": {"type": "array", "items": {"type": "string"}},
                "requirements": {"type": "array", "items": {"type": "string"}},
                "caveats": {"type": "array", "items": {"type": "string"}},
            },
        }
        extraction = await firecrawl_extract_tool.ainvoke(
            {
                "urls": urls[: max(1, max_pages)],
                "schema": schema,
                "enable_web_search": False,
            }
        )
        data = extraction.get("data") if isinstance(extraction, dict) else None
        if isinstance(data, dict):
            for key in ("steps", "requirements", "caveats"):
                vals = data.get(key)
                if isinstance(vals, list):
                    trimmed = [
                        f"- {v}" for v in vals if isinstance(v, str) and v.strip()
                    ]
                    if trimmed:
                        extract_lines.append(f"{key.title()}:")
                        extract_lines.extend(trimmed[:5])
    except Exception:
        extract_lines = []

    if not page_summaries and not extract_lines:
        return None

    lines: List[str] = [
        "Firecrawl Mailbird help (internal only — do not cite URLs directly):"
    ]
    if extract_lines:
        lines.append("Structured guidance:")
        lines.extend(extract_lines)
    if page_summaries:
        lines.append("Page highlights:")
        lines.extend(page_summaries)

    context = "\n".join(lines).strip()
    context = re.sub(r"\n{3,}", "\n\n", context).strip()
    return context


async def _run_daily_maintenance(
    webhook_retention_days: int = 7, queue_retention_days: int | None = None
) -> None:
    """Perform daily cleanup tasks for webhook events and processed queue rows."""
    try:
        supa = get_supabase_client()
        resp = await supa._exec(
            lambda: supa.client.table("feature_flags")
            .select("value")
            .eq("key", "zendesk_cleanup")
            .maybe_single()
            .execute()
        )
        raw = getattr(resp, "data", None) or {}
        state = raw.get("value") if isinstance(raw, dict) else {}
        state = state if isinstance(state, dict) else {}
        today = datetime.now(timezone.utc).date().isoformat()
        updated = False

        last_cleanup = state.get("last_cleanup_date")
        if last_cleanup != today:
            cutoff = (
                datetime.now(timezone.utc)
                - timedelta(days=max(1, int(webhook_retention_days)))
            ).isoformat()
            try:
                await supa._exec(
                    lambda: supa.client.table("zendesk_webhook_events")
                    .delete()
                    .lt("seen_at", cutoff)
                    .execute()
                )
            except Exception as cleanup_exc:
                logger.debug("webhook cleanup failed: %s", cleanup_exc)
            else:
                state["last_cleanup_date"] = today
                updated = True

        if queue_retention_days is not None:
            last_retention = state.get("last_retention_date")
            if last_retention != today:
                cutoff_queue = (
                    datetime.now(timezone.utc)
                    - timedelta(days=max(1, int(queue_retention_days)))
                ).isoformat()
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
                lambda: supa.client.table("feature_flags")
                .upsert({"key": "zendesk_cleanup", "value": state})
                .execute()
            )
    except Exception as e:
        logger.debug("daily maintenance failed: %s", e)


async def _requeue_stale_processing(max_age_minutes: int = 30) -> int:
    """Move long-running `processing` rows back to `retry` so they can be picked up again.

    This protects against worker crashes/timeouts between the "claim" update and the
    final "processed"/"retry"/"failed" update.
    """
    try:
        max_age = max(1, int(max_age_minutes))
    except Exception:
        max_age = 30

    supa = get_supabase_client()
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=max_age)).isoformat()
    now_iso = now.isoformat()

    updated = 0
    payload = {
        "status": "retry",
        "next_attempt_at": now_iso,
        "last_error": "stale_processing_requeued",
        "last_attempt_at": now_iso,
    }

    # Stale rows that have a timestamp
    try:
        res = await supa._exec(
            lambda: supa.client.table("zendesk_pending_tickets")
            .update(payload)
            .eq("status", "processing")
            .lt("last_attempt_at", cutoff)
            .execute()
        )
        updated += len(getattr(res, "data", []) or [])
    except Exception:
        pass

    # Backward-compat: processing rows with NULL last_attempt_at (older deployments)
    try:
        res2 = await supa._exec(
            lambda: supa.client.table("zendesk_pending_tickets")
            .update(payload)
            .eq("status", "processing")
            .is_("last_attempt_at", "null")
            .lt("created_at", cutoff)
            .execute()
        )
        updated += len(getattr(res2, "data", []) or [])
    except Exception:
        pass

    if updated:
        logger.warning("Re-queued %d stale Zendesk processing tickets", updated)
    return updated


async def _get_feature_state() -> Dict[str, Any]:
    """Read feature flag state from Supabase, fallback to env flags."""
    enabled = bool(getattr(settings, "zendesk_enabled", False))
    dry_run = bool(getattr(settings, "zendesk_dry_run", True))
    config = get_models_config()
    if config.zendesk is not None:
        coordinator_cfg = resolve_coordinator_config(config, "google", zendesk=True)
    else:
        coordinator_cfg = resolve_coordinator_config(config, "google")
    provider = coordinator_cfg.provider or "google"
    model = coordinator_cfg.model_id
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
            val = data["value"]
            enabled = bool(val.get("enabled", enabled))
            if "dry_run" in val:
                dry_run = bool(val.get("dry_run", dry_run))
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
    return {
        "enabled": enabled,
        "dry_run": dry_run,
        "provider": provider,
        "model": model,
        "last_run_at": last_run_at,
    }


async def _set_last_run(ts: datetime) -> None:
    try:
        supa = get_supabase_client()
        await supa._exec(
            lambda: supa.client.table("feature_flags")
            .upsert(
                {
                    "key": "zendesk_scheduler",
                    "value": {"last_run_at": ts.replace(microsecond=0).isoformat()},
                }
            )
            .execute()
        )
    except Exception as e:
        logger.debug("failed to persist scheduler ts: %s", e)


async def _get_month_usage() -> Dict[str, Any]:
    supa = get_supabase_client()
    mk = datetime.now(timezone.utc).strftime("%Y-%m")
    desired_budget = 0
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
            .insert(
                {
                    "month_key": mk,
                    "calls_used": 0,
                    "budget": desired_budget,
                }
            )
            .execute()
        )
        return {"month_key": mk, "calls_used": 0, "budget": desired_budget}

    # Normalize types and keep the stored budget in sync with config.
    try:
        calls_used = max(0, int(data.get("calls_used", 0) or 0))
    except Exception:
        calls_used = 0
    try:
        budget = int(data.get("budget", desired_budget) or desired_budget)
    except Exception:
        budget = desired_budget
    budget = 0

    if int(data.get("budget", 0) or 0) != 0:
        try:
            await supa._exec(
                lambda: supa.client.table("zendesk_usage")
                .update(
                    {
                        "budget": 0,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .eq("month_key", mk)
                .execute()
            )
        except Exception:
            pass

    return {"month_key": mk, "calls_used": calls_used, "budget": budget}


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
        .update(
            {
                "calls_used": int(cur) + int(n),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
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
        .update(
            {
                "gemini_calls_used": int(used) + int(n),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("usage_date", today)
        .execute()
    )


async def _generate_reply(
    ticket_id: int | str,
    subject: str | None,
    description: str | None,
    provider: str | None = None,
    model: str | None = None,
) -> ZendeskReplyResult:
    """Run Primary Agent with the same pipeline as chat to produce a high-quality reply.

    Uses raw subject/description (no meta-prompt), optional latest public comment context,
    user context scope for API keys, grounding preflight to decide web search, a light
    quality check on the final response, and an attachment fetch (logs/images) for
    additional context.
    """
    # Basic PII redaction (align with webhook redaction)
    _EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]{1,})@([A-Za-z0-9.-]{1,})")
    _PHONE_RE = re.compile(
        r"(?<!\d)(\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?){2}\d{4}(?!\d)"
    )

    def _redact_pii(text: str | None) -> str | None:
        if not text or not isinstance(text, str):
            return text
        t = _EMAIL_RE.sub(lambda m: f"{m.group(1)[:2]}***@{m.group(2)}", text)
        t = _PHONE_RE.sub("[redacted-phone]", t)
        return t

    def _normalize_result_to_text(
        result_payload: Dict[str, Any] | None, state_obj: GraphState | None
    ) -> str:
        result_messages = list((result_payload or {}).get("messages") or [])

        def _extract_text(content: Any) -> str:
            if isinstance(content, list):
                text_parts: List[str] = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text" and "text" in block:
                            text_parts.append(str(block["text"]))
                        elif "text" in block:
                            text_parts.append(str(block["text"]))
                    elif isinstance(block, str):
                        text_parts.append(block)
                return "\n".join(text_parts).strip()
            if content is None:
                return ""
            return str(content).strip()

        candidates: List[tuple[int, str]] = []
        for candidate in result_messages:
            if not isinstance(candidate, AIMessage):
                continue
            content_text = _extract_text(getattr(candidate, "content", None))
            if not content_text:
                continue
            # Skip planning/analysis artifacts
            if re.search(r"(?i):::thinking", content_text) or re.search(
                r"(?i)\bthinking\b", content_text
            ):
                continue
            score = len(content_text)
            if re.search(r"(?i)\bsuggested reply\b", content_text):
                score += 5000
            if re.search(r"(?i)\bhi\s+there\b", content_text) and re.search(
                r"(?i)mailbird\s+customer\s+happiness\s+team",
                content_text,
            ):
                score += 10000
            candidates.append((score, content_text))

        text_out = ""
        if candidates:
            _, text_out = max(candidates, key=lambda item: item[0])
        else:
            final_msg = None
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
            if final_msg and getattr(final_msg, "content", None):
                text_out = _extract_text(final_msg.content)
        # Strip any accidental planning/thinking markers from model output
        text_out = re.sub(r"(?im)^:::thinking\s*\n?", "", text_out)
        text_out = re.sub(r"(?im)^thinking\s*\n?", "", text_out)
        text_out = re.sub(r"(?im)^\*?\s*thoughts?:.*$", "", text_out)
        # Strip any accidental offers for channels we don't support (e.g., screen sharing)
        text_out = re.sub(r"(?im)^.*screen\s*share.*$", "", text_out)
        text_out = re.sub(r"(?im)^.*screenshare.*$", "", text_out)
        text_out = text_out.replace("\r\n", "\n").replace("\r", "\n")

        # Collapse *excessive* blank lines created by removals but preserve paragraph breaks.
        cleaned_lines: List[str] = []
        blank = 0
        for ln in text_out.splitlines():
            line = ln.rstrip()
            if not line.strip():
                blank += 1
                if blank <= 1:
                    cleaned_lines.append("")
                continue
            blank = 0
            cleaned_lines.append(line)
        text_out = "\n".join(cleaned_lines).strip("\n")

        # De-duplicate repeated greetings/first lines that often occur in model output,
        # while preserving indentation and paragraph boundaries.
        raw_lines = [ln.rstrip("\n") for ln in text_out.splitlines()]
        non_empty_indices = [i for i, ln in enumerate(raw_lines) if ln.strip()]
        skip_idx: set[int] = set()
        if len(non_empty_indices) >= 2:
            i0, i1 = non_empty_indices[0], non_empty_indices[1]
            cur = raw_lines[i0].strip()
            nxt = raw_lines[i1].strip()
            if nxt.lower().startswith(cur.lower()):
                skip_idx.add(i0)

        deduped: List[str] = []
        blank = 0
        last_nonblank_lower: str | None = None
        for i, ln in enumerate(raw_lines):
            if i in skip_idx:
                continue
            line = ln.rstrip()
            if not line.strip():
                blank += 1
                if blank <= 1:
                    deduped.append("")
                last_nonblank_lower = None
                continue
            blank = 0
            key = line.strip().lower()
            if last_nonblank_lower == key:
                continue
            deduped.append(line)
            last_nonblank_lower = key

        text_out = "\n".join(deduped).strip("\n")
        text_out = _sanitize_suggested_reply_text(text_out)

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
            for line in lines:
                is_heading = bool(
                    re.match(
                        r"^(Suggested Reply|Empathetic Opening|Solution Overview|Try Now — Immediate Actions|Full Fix — Step-by-Step Instructions|Additional Context|Pro Tips|Supportive Closing)\s*$",
                        line,
                    )
                )
                if is_heading:
                    if out and out[-1].strip() != "":
                        out.append("")
                    out.append(line)
                    prev_was_heading = True
                    continue
                if prev_was_heading and line.strip() != "":
                    out.append("")
                    prev_was_heading = False
                out.append(line)

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
            for line in merged:
                if line.strip() == "":
                    blank += 1
                    if blank <= 1:
                        final.append("")
                else:
                    blank = 0
                    final.append(line)
            return "\n".join(final).strip()

        # HTML formatter for Zendesk internal notes (no inline CSS)
        def _format_html_for_zendesk(s: str) -> str:
            heading_tag = getattr(settings, "zendesk_heading_level", "h3")
            style = getattr(settings, "zendesk_format_style", "compact")
            engine = getattr(settings, "zendesk_format_engine", "legacy")
            if str(engine).strip().lower() == "markdown_v2":
                from app.integrations.zendesk.formatters.markdown_v2 import (
                    format_zendesk_internal_note_markdown_v2,
                )

                return format_zendesk_internal_note_markdown_v2(
                    s,
                    heading_level=str(heading_tag),
                    format_style=str(style),
                )
            return _format_zendesk_internal_note_html(
                s,
                heading_level=str(heading_tag),
                format_style=str(style),
            )

        if getattr(settings, "zendesk_use_html", True):
            return _format_html_for_zendesk(text_out)
        return _to_plaintext_for_zendesk(text_out)

    # Compose the user query similar to main chat input
    parts_in: List[str] = []
    if subject:
        parts_in.append(str(subject))

    # If subject/description are missing, fetch from Zendesk to avoid empty prompts
    if (
        (not subject or not description)
        and settings.zendesk_subdomain
        and settings.zendesk_email
        and settings.zendesk_api_token
    ):
        try:
            zc_fetch = ZendeskClient(
                subdomain=str(settings.zendesk_subdomain),
                email=str(settings.zendesk_email),
                api_token=str(settings.zendesk_api_token),
                dry_run=True,
            )
            ticket_payload = await asyncio.to_thread(zc_fetch.get_ticket, ticket_id)
            fetched_subject = ticket_payload.get("subject")
            fetched_description = ticket_payload.get("description")
            if not subject and fetched_subject:
                subject = fetched_subject
                parts_in.append(str(fetched_subject))
            if not description and fetched_description:
                description = fetched_description
        except Exception as exc:  # pragma: no cover - network fallback
            logger.warning(
                "zendesk_fetch_ticket_failed", ticket_id=ticket_id, error=str(exc)
            )

    last_public = None
    try:
        if (
            settings.zendesk_subdomain
            and settings.zendesk_email
            and settings.zendesk_api_token
        ):
            zc = ZendeskClient(
                subdomain=str(settings.zendesk_subdomain),
                email=str(settings.zendesk_email),
                api_token=str(settings.zendesk_api_token),
                dry_run=True,
            )
            last_public = await asyncio.to_thread(
                zc.get_last_public_comment_snippet, ticket_id
            )
    except Exception:
        last_public = None
    if last_public:
        parts_in.append(last_public)

    if description:
        parts_in.append(str(description))

    # Deterministic guardrail for PGP/OpenPGP questions to avoid hallucinating support
    try:
        text_probe = " ".join(parts_in).lower()
    except Exception:
        text_probe = ""
    if any(k in text_probe for k in ["pgp", "openpgp", "gpg"]):
        parts_in.append(
            "Internal KB note: Mailbird does NOT support PGP/OpenPGP encryption today. "
            "There is no in-app toggle or workaround. "
            "Advise the customer to upvote the feature request: "
            "https://mailbird.featureupvote.com/suggestions/74494/pgp-encryption-support."
        )

    attachments: List[Dict[str, Any]] = []
    unified_attachments = []  # For multimodal processing (images, PDFs)
    try:
        attachments = fetch_ticket_attachments(ticket_id)
        att_summary = summarize_attachments(attachments)
        if att_summary:
            parts_in.append(f"Attachments summary for agent:\n{att_summary}")
        # Convert to unified agent format for multimodal processing
        unified_attachments = convert_to_unified_attachments(attachments)
        if unified_attachments:
            logger.info(
                f"ticket_{ticket_id}_multimodal_attachments count={len(unified_attachments)}"
            )
    except Exception as e:
        logger.debug(f"attachment_fetch_failed ticket={ticket_id}: {e}")

    user_query_raw = "\n\n".join([p for p in parts_in if p]) or "(no description)"
    user_query = _redact_pii(user_query_raw) or user_query_raw

    ticket_is_unclear = _ticket_seems_unclear(
        subject=str(subject) if subject is not None else None,
        description=str(description) if description is not None else None,
        last_public=str(last_public) if last_public is not None else None,
    )
    ticket_wants_refund = _ticket_wants_refund(user_query)

    # Observability: log which context sources are available for this run
    def _context_caps() -> Dict[str, bool]:
        caps = {
            "workspace_tools": False,
            "issue_pattern_memory": False,
            "playbooks": False,
        }
        try:
            from app.agents.unified.workspace_tools import get_workspace_tools  # type: ignore  # noqa: F401

            caps["workspace_tools"] = True
        except Exception:
            caps["workspace_tools"] = False
        try:
            from app.agents.harness.store.issue_resolution_store import (  # type: ignore
                IssueResolutionStore,
            )

            caps["issue_pattern_memory"] = IssueResolutionStore is not None
        except Exception:
            caps["issue_pattern_memory"] = False
        try:
            from app.agents.unified.playbooks import extractor  # type: ignore  # noqa: F401

            caps["playbooks"] = True
        except Exception:
            caps["playbooks"] = False
        return caps

    logger.info(
        "zendesk_context_caps ticket_id=%s caps=%s",
        ticket_id,
        _context_caps(),
    )

    session_id = f"zendesk-{ticket_id}"
    state: GraphState | None = None
    result: Dict[str, Any] | None = None
    learning_messages: list[Any] = []
    inferred_category: str | None = None
    kb_articles_used: list[str] = []
    macros_used: list[str] = []

    try:
        async with user_context_scope(UserContext(user_id="zendesk-bot")):
            kb_ok = False
            macro_ok = False
            feedme_ok = False
            pattern_ok = False
            internal_context: str | None = None
            web_context: str | None = None
            web_ok = False
            macro_choice: Dict[str, Any] | None = None
            playbook_path: str | None = None

            # Fetch policy macros from Supabase so the agent can follow the correct, full procedures.
            policy_macros: List[Dict[str, Any]] = []
            log_macro = await _fetch_zendesk_macro_by_title(
                _POLICY_MACRO_TITLES["log_request"]
            )
            if log_macro:
                policy_macros.append(log_macro)

            screenshot_macro: Dict[str, Any] | None = None
            if ticket_is_unclear:
                screenshot_macro = await _fetch_zendesk_macro_by_title(
                    _POLICY_MACRO_TITLES["screenshot_request"]
                )
                if screenshot_macro:
                    policy_macros.append(screenshot_macro)

            refund_macros: List[Dict[str, Any]] = []
            if ticket_wants_refund:
                hint_text = f"{subject or ''}\n{description or ''}".lower()
                wants_yearly = bool(
                    re.search(r"\b(yearly|annual|subscription)\b", hint_text)
                )
                wants_pay_once = bool(
                    re.search(r"\b(pay\s*once|lifetime|one[- ]time)\b", hint_text)
                )
                if wants_yearly and not wants_pay_once:
                    macro = await _fetch_zendesk_macro_by_title(
                        _POLICY_MACRO_TITLES["refund_yearly"]
                    )
                    if macro:
                        refund_macros.append(macro)
                elif wants_pay_once and not wants_yearly:
                    macro = await _fetch_zendesk_macro_by_title(
                        _POLICY_MACRO_TITLES["refund_pay_once"]
                    )
                    if macro:
                        refund_macros.append(macro)
                else:
                    for key in ("refund_pay_once", "refund_yearly"):
                        macro = await _fetch_zendesk_macro_by_title(
                            _POLICY_MACRO_TITLES[key]
                        )
                        if macro:
                            refund_macros.append(macro)
                policy_macros.extend(refund_macros)

            policy_context = _format_policy_macros_context(policy_macros)
            policy_chars, policy_words, policy_tokens = _text_stats(policy_context)
            logger.info(
                "zendesk_policy_context_stats ticket_id=%s macros=%s chars=%s words=%s tokens_est=%s",
                ticket_id,
                len(policy_macros),
                policy_chars,
                policy_words,
                policy_tokens,
            )
            log_macro_step_lines = _count_step_lines(
                str((log_macro or {}).get("content") or "")
            )

            # Macro-first retrieval preflight (KB + macros + FeedMe) to guide the agent.
            try:
                min_rel = float(
                    getattr(settings, "zendesk_internal_retrieval_min_relevance", 0.35)
                )
                max_per_source = int(
                    getattr(settings, "zendesk_internal_retrieval_max_per_source", 5)
                )
                retrieved = await db_unified_search_tool.ainvoke(
                    {
                        "query": user_query,
                        "sources": ["macros", "kb", "feedme"],
                        "max_results_per_source": max_per_source,
                        "min_relevance": min_rel,
                    }
                )
                retrieved_results = list((retrieved or {}).get("results") or [])

                # NOTE: Do NOT auto-hydrate full FeedMe transcripts here.
                # db_unified_search returns excerpts by default; the agent can
                # call db_context_search for full transcripts when truly needed.
                # Capture which KB/macros contributed (for post-resolution pattern memory)
                for item in retrieved_results:
                    if not isinstance(item, dict):
                        continue
                    source = str(item.get("source") or "").lower()
                    meta = item.get("metadata") or {}
                    if not isinstance(meta, dict):
                        meta = {}
                    if source == "kb":
                        kb_id = meta.get("id") or meta.get("url")
                        if kb_id:
                            kb_articles_used.append(str(kb_id))
                    if source in {"macro", "macros"}:
                        macro_id = meta.get("zendesk_id")
                        if macro_id:
                            macros_used.append(str(macro_id))
                preflight = _format_internal_retrieval_context(
                    retrieved_results, query=user_query
                )
                internal_context = preflight.get("context")
                macro_ok = bool(preflight.get("macro_ok"))
                feedme_ok = bool(preflight.get("feedme_ok"))
                macro_min = float(
                    getattr(settings, "zendesk_macro_min_relevance", 0.55)
                )
                macro_choice = _select_macro_candidate(
                    retrieved_results, min_relevance=macro_min
                )
                # This is a vector-only KB check; we still run hybrid KB search below for better recall.
                kb_ok = bool(preflight.get("kb_ok"))
                logger.info(
                    "zendesk_retrieval_preflight ticket_id=%s macro_hits=%s kb_hits=%s feedme_hits=%s macro_chars=%s kb_chars=%s feedme_chars=%s",
                    ticket_id,
                    preflight.get("macro_hits"),
                    preflight.get("kb_hits"),
                    preflight.get("feedme_hits"),
                    preflight.get("macro_context_chars"),
                    preflight.get("kb_context_chars"),
                    preflight.get("feedme_context_chars"),
                )
                internal_chars, internal_words, internal_tokens = _text_stats(
                    internal_context
                )
                logger.info(
                    "zendesk_internal_context_stats ticket_id=%s chars=%s words=%s tokens_est=%s",
                    ticket_id,
                    internal_chars,
                    internal_words,
                    internal_tokens,
                )
            except Exception as e:
                logger.debug("retrieval preflight failed: %s", e)

            # Pattern-based semantic grounding (IssueResolutionStore + verified playbooks)
            try:
                from app.agents.harness.store import (
                    IssueResolutionStore,
                    SparrowWorkspaceStore,
                )

                workspace_store = SparrowWorkspaceStore(session_id=session_id)
                issue_store = IssueResolutionStore()

                playbook_extractor = None
                try:
                    from app.agents.unified.playbooks import PlaybookExtractor

                    playbook_extractor = PlaybookExtractor()
                except Exception:
                    playbook_extractor = None

                pattern_preflight = await _run_pattern_preflight(
                    ticket_id=str(ticket_id),
                    session_id=session_id,
                    ticket_text=user_query,
                    workspace_store=workspace_store,
                    issue_store=issue_store,
                    playbook_extractor=playbook_extractor,
                    max_hits=int(
                        getattr(settings, "zendesk_issue_pattern_max_hits", 5)
                    ),
                    min_similarity=float(
                        getattr(settings, "zendesk_issue_pattern_min_similarity", 0.62)
                    ),
                )

                if isinstance(pattern_preflight, dict):
                    raw_category = pattern_preflight.get("category")
                    inferred_category = (
                        str(raw_category) if isinstance(raw_category, str) and raw_category.strip() else None
                    )
                    raw_playbook_path = pattern_preflight.get("playbook_path")
                    playbook_path = (
                        str(raw_playbook_path)
                        if isinstance(raw_playbook_path, str) and raw_playbook_path.strip()
                        else None
                    )

                    similar_count = 0
                    try:
                        similar_count = int(pattern_preflight.get("similar_count") or 0)
                    except Exception:
                        similar_count = 0
                    pattern_ok = bool(pattern_preflight.get("playbook_compiled")) or similar_count > 0

                # Inline a bounded amount of pattern/playbook context so the agent
                # can stay internal-first without immediately reaching for web search.
                try:
                    pattern_parts: list[str] = []
                    if pattern_ok:
                        similar_md = await workspace_store.read_file("/context/similar_scenarios.md")
                        if isinstance(similar_md, str) and similar_md.strip():
                            pattern_parts.append(
                                "Similar internal scenarios (do NOT mention sources in the customer reply):\n\n"
                                + _trim_block(similar_md, 5000)
                            )
                        if playbook_path:
                            playbook_md = await workspace_store.read_file(playbook_path)
                            if isinstance(playbook_md, str) and playbook_md.strip():
                                pattern_parts.append(
                                    "Verified internal playbook (do NOT mention sources in the customer reply):\n\n"
                                    + _trim_block(playbook_md, 7000)
                                )
                    pattern_context = "\n\n".join([p for p in pattern_parts if p]).strip()
                    if pattern_context:
                        internal_context = "\n\n".join(
                            [p for p in [internal_context, pattern_context] if p]
                        ).strip()
                except Exception:
                    pass
            except Exception as exc:  # pragma: no cover - best effort
                logger.debug(
                    "zendesk_pattern_preflight_failed ticket_id=%s error=%s",
                    ticket_id,
                    str(exc)[:180],
                )

            # Hybrid KB preflight (vector + full-text) for better recall.
            kb_ok_hybrid = False
            try:
                kb_payload: Dict[str, Any] = {
                    "query": user_query,
                    "max_results": settings.primary_agent_min_kb_results,
                }
                min_conf = getattr(
                    settings, "zendesk_internal_retrieval_min_relevance", None
                )
                if min_conf is None:
                    min_conf = getattr(settings, "primary_agent_min_kb_relevance", None)
                if min_conf is not None:
                    kb_payload["min_confidence"] = min_conf

                kb_result = await kb_search_tool.ainvoke(kb_payload)
                if isinstance(kb_result, str) and kb_result.strip():
                    try:
                        parsed = json.loads(kb_result)
                        kb_ok_hybrid = bool(int(parsed.get("result_count") or 0) > 0)
                    except Exception:
                        kb_ok_hybrid = len(kb_result.strip()) > 50
            except Exception as e:
                logger.debug(
                    f"KB preflight check failed: {e}, defaulting to web search"
                )

            kb_ok = bool(kb_ok or kb_ok_hybrid)

            internal_ok = bool(kb_ok or macro_ok or feedme_ok or pattern_ok)
            macro_selector_context = _format_macro_selector_context(macro_choice)
            if macro_selector_context:
                internal_context = "\n\n".join(
                    [p for p in [internal_context, macro_selector_context] if p]
                ).strip()
            if policy_context:
                internal_context = "\n\n".join(
                    [p for p in [internal_context, policy_context] if p]
                ).strip()

            internal_chars, internal_words, internal_tokens = _text_stats(
                internal_context
            )
            logger.info(
                "zendesk_internal_context_final_stats ticket_id=%s chars=%s words=%s tokens_est=%s",
                ticket_id,
                internal_chars,
                internal_words,
                internal_tokens,
            )

            search_query = _build_web_search_query(
                subject=subject, description=description, fallback=user_query
            )
            internal_relevance_low = not internal_ok
            if not internal_ok and bool(
                getattr(settings, "zendesk_web_prefetch_enabled", True)
            ):
                try:
                    max_pages = int(getattr(settings, "zendesk_web_prefetch_pages", 3))
                    web_context = await _prefetch_web_research(
                        search_query=search_query, max_pages=max_pages
                    )
                    web_ok = bool(web_context)
                    logger.info(
                        "zendesk_web_prefetch ticket_id=%s ok=%s query_len=%s",
                        ticket_id,
                        web_ok,
                        len(search_query),
                    )
                    web_chars, web_words, web_tokens = _text_stats(web_context)
                    logger.info(
                        "zendesk_web_context_stats ticket_id=%s chars=%s words=%s tokens_est=%s",
                        ticket_id,
                        web_chars,
                        web_words,
                        web_tokens,
                    )
                except Exception as e:
                    logger.debug(
                        "zendesk_web_prefetch_failed ticket_id=%s error=%s",
                        ticket_id,
                        str(e)[:180],
                    )

            if (
                internal_relevance_low
                and getattr(settings, "zendesk_firecrawl_enhanced_enabled", False)
                and search_query
            ):
                try:
                    domains = [
                        d
                        for d in getattr(
                            settings, "zendesk_firecrawl_support_domains", []
                        )
                        or []
                        if isinstance(d, str) and d.strip()
                    ]
                    max_pages = int(
                        getattr(settings, "zendesk_firecrawl_support_pages", 3)
                    )
                    include_shots = bool(
                        getattr(
                            settings, "zendesk_firecrawl_support_screenshots", False
                        )
                    )
                    support_pack = await _firecrawl_support_bundle(
                        search_query=search_query,
                        domains=domains,
                        max_pages=max_pages,
                        include_screenshots=include_shots,
                    )
                    if support_pack:
                        web_context = (
                            "\n\n".join(
                                [p for p in [web_context, support_pack] if p]
                            ).strip()
                            or web_context
                        )
                        web_ok = web_ok or bool(support_pack)
                        web_chars, web_words, web_tokens = _text_stats(web_context)
                        logger.info(
                            "zendesk_web_context_stats ticket_id=%s chars=%s words=%s tokens_est=%s",
                            ticket_id,
                            web_chars,
                            web_words,
                            web_tokens,
                        )
                    logger.info(
                        "zendesk_firecrawl_support ticket_id=%s ok=%s domains=%s",
                        ticket_id,
                        bool(support_pack),
                        len(domains),
                    )
                except Exception as e:
                    logger.debug(
                        "zendesk_firecrawl_support_failed ticket_id=%s error=%s",
                        ticket_id,
                        str(e)[:180],
                    )

            # Use configured provider/model from YAML (feature flag only controls enabled/dry_run).
            config = get_models_config()
            zendesk_configured = config.zendesk is not None
            default_provider_cfg = resolve_coordinator_config(
                config,
                "google",
                zendesk=zendesk_configured,
            )
            use_provider = provider or (default_provider_cfg.provider or "google")
            use_model = model
            if not use_model:
                try:
                    coordinator_cfg = resolve_coordinator_config(
                        config,
                        str(use_provider),
                        zendesk=zendesk_configured,
                    )
                except Exception:
                    coordinator_cfg = resolve_coordinator_config(config, "google")
                use_model = coordinator_cfg.model_id

            # Gemini 2.5 Pro currently trips quota/429 frequently when used with tool-enabled
            # LangGraph runs; run the unified agent on Flash and then do a Pro-only rewrite
            # as a final polishing pass (still via Google/GEMINI_API_KEY).
            agent_model = use_model
            rewrite_model: str | None = None
            if str(use_provider).lower() == "google" and str(
                use_model
            ).lower().startswith("gemini-2.5-pro"):
                # Prefer the configured primary agent model (often a preview Flash variant)
                # rather than hard-coding a stable ID that may not be enabled for the key.
                candidate = resolve_coordinator_config(config, "google").model_id
                candidate = str(candidate)
                if candidate.lower().startswith("gemini-2.5-pro"):
                    candidate = "gemini-2.5-flash-preview-09-2025"
                agent_model = candidate
                rewrite_model = str(use_model)

            # LangChain's Google GenAI image_url handling rejects PDF data URLs.
            # Until upstream supports PDF parts properly, drop PDFs from multimodal
            # attachments and rely on the text attachment summary already injected
            # into `user_query`.
            attachments_for_agent = unified_attachments
            provider_lower = str(use_provider).lower()
            if provider_lower in {"google", "xai"} and unified_attachments:
                # Gemini and Grok do not reliably support PDFs via image_url blocks today.
                pdfs = [
                    a
                    for a in unified_attachments
                    if getattr(a, "mime_type", None) == "application/pdf"
                ]
                if pdfs:
                    logger.info(
                        "zendesk_drop_pdf_attachments ticket_id=%s provider=%s count=%s",
                        ticket_id,
                        provider_lower,
                        len(pdfs),
                    )
                attachments_for_agent = [
                    a
                    for a in unified_attachments
                    if getattr(a, "mime_type", None) != "application/pdf"
                ]

            content_parts = [user_query]
            if internal_context:
                content_parts.append(internal_context)
            if web_context:
                content_parts.append(web_context)

            prompt_text = "\n\n".join(content_parts).strip()
            prompt_chars, prompt_words, prompt_tokens = _text_stats(prompt_text)
            logger.info(
                "zendesk_prompt_stats ticket_id=%s chars=%s words=%s tokens_est=%s",
                ticket_id,
                prompt_chars,
                prompt_words,
                prompt_tokens,
            )
            state = GraphState(
                messages=[HumanMessage(content=prompt_text)],
                session_id=session_id,
                provider=use_provider,
                model=agent_model,
                attachments=attachments_for_agent,  # Pass multimodal attachments for vision processing
                forwarded_props={
                    "force_websearch": not (
                        kb_ok or macro_ok or feedme_ok or pattern_ok or web_ok
                    ),
                    "websearch_max_results": None,
                    "is_final_response": True,  # Triggers writing/empathy skills
                    "task_type": "support",  # Support ticket context
                    "is_zendesk_ticket": True,  # Explicit Zendesk marker
                    "zendesk_ticket_id": ticket_id,
                    # Pattern-based context engineering
                    "ticket_category": inferred_category,
                    "similar_scenarios_path": "/context/similar_scenarios.md",
                    "playbook_path": playbook_path,
                },
            )

            # Pass config with lower recursion limit to prevent runaway agent loops
            result = await run_unified_agent(
                state,
                config={"recursion_limit": ZENDESK_RECURSION_LIMIT},
            )
            try:
                # Preserve original conversation for post-resolution learning (before rewrite passes)
                if isinstance(result, dict):
                    learning_messages = list(result.get("messages") or [])
            except Exception:
                learning_messages = []
            # Treat missing AI output or explicit agent errors as retryable failures.
            if isinstance(result, dict):
                if result.get("error"):
                    raise RuntimeError(f"unified_agent_error: {result.get('error')}")
                msgs = list(result.get("messages") or [])
                if not any(isinstance(m, AIMessage) for m in msgs):
                    raise RuntimeError("unified_agent_no_ai_message")

            def _extract_ai_text(payload: Dict[str, Any] | None) -> str:
                out_msgs = list((payload or {}).get("messages") or [])
                for candidate in reversed(out_msgs):
                    if isinstance(candidate, AIMessage):
                        content = getattr(candidate, "content", "")
                        if isinstance(content, list):
                            parts: List[str] = []
                            for block in content:
                                if isinstance(block, dict):
                                    if block.get("type") == "text" and "text" in block:
                                        parts.append(str(block["text"]))
                                    elif "text" in block:
                                        parts.append(str(block["text"]))
                                elif isinstance(block, str):
                                    parts.append(block)
                            return "\n".join(parts).strip()
                        return str(content).strip()
                return ""

            def _extract_llm_content(content: Any) -> str:
                if isinstance(content, list):
                    parts: List[str] = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text" and "text" in block:
                                parts.append(str(block["text"]))
                            elif "text" in block:
                                parts.append(str(block["text"]))
                        elif isinstance(block, str):
                            parts.append(block)
                    return "\n".join(parts).strip()
                if content is None:
                    return ""
                return str(content).strip()

            def _policy_rewrite_reasons(draft_text: str) -> List[str]:
                text = str(draft_text or "")
                lower = text.lower()
                reasons: List[str] = []

                if ticket_is_unclear:
                    if not re.search(r"(?i)\b(screen\s*shot|screenshot)\b", text):
                        reasons.append("unclear_ticket_missing_screenshot_request")
                    if not re.search(
                        r"(?i)\b(could\s+you|can\s+you|please\s+(share|send|provide)|what\s+happens|which\s+version|any\s+error)\b",
                        text,
                    ):
                        reasons.append("unclear_ticket_missing_details_request")

                asks_for_logs = bool(
                    re.search(r"(?i)\b(log\s*file|logs?)\b", text)
                    and re.search(r"(?i)\b(attach|upload|send|share|provide)\b", text)
                    and re.search(r"(?i)\b(please|could\s+you|can\s+you)\b", text)
                )
                if asks_for_logs:
                    draft_steps = _count_step_lines(text)
                    min_steps = 3
                    if log_macro_step_lines:
                        min_steps = max(
                            min_steps, max(1, int(log_macro_step_lines) - 1)
                        )
                    if draft_steps < min_steps:
                        reasons.append("log_request_too_short")

                suggests_reinstall = bool(
                    re.search(r"(?i)\bre-?install\b", text)
                    and re.search(r"(?i)\bmailbird\b", text)
                )
                suggests_remove_readd = bool(
                    re.search(r"(?i)\b(remove|delete)\b.*\baccount\b", text)
                    or re.search(r"(?i)\bre-?add\b.*\baccount\b", text)
                    or re.search(r"(?i)\bremove\b.*\badd\s+it\s+back\b", text)
                )
                if suggests_reinstall or suggests_remove_readd:
                    # Require backup-first guidance when destructive steps are suggested.
                    has_backup = bool(
                        re.search(r"(?i)\bbackup\b", text)
                        or re.search(r"(?i)\bcopy\b", text)
                    )
                    has_appdata = bool(
                        re.search(r"appdata\s*[\\/]+\s*local", lower)
                        or re.search(r"c:\\users\\", lower)
                    )
                    has_mailbird_folder = bool(
                        re.search(r"(?i)\bmailbird\b", text)
                        and re.search(r"(?i)\bfolder\b", text)
                    )
                    if not (has_backup and (has_appdata or has_mailbird_folder)):
                        reasons.append(
                            "missing_backup_before_remove_readd_or_reinstall"
                        )

                if ticket_wants_refund and re.search(r"(?i)\brefund\b", text):
                    if not re.search(r"(?i)\b50\s*%\b|\bhalf\b", text):
                        reasons.append("missing_50_percent_refund_option")

                return reasons

            def _draft_needs_customer_rewrite(draft_text: str) -> bool:
                if not str(draft_text or "").strip():
                    return True
                text = str(draft_text)
                if any(p.search(text) for p in _ZENDESK_META_INLINE_PATTERNS):
                    return True
                if re.search(
                    r"(?im)^\s*(assistant|system|developer|tool|user)\s*:", text
                ):
                    return True
                # If it looks like a KB/macro dump without customer steps, rewrite it.
                if re.search(
                    r"(?i)\b(kb\s+articles|zendesk\s+macros|feedme\s+history)\b", text
                ):
                    return True
                if _policy_rewrite_reasons(text):
                    return True
                return False

            # For Grok, a tool-enabled run can leak internal context. Perform a strict, tool-free rewrite.
            if str(use_provider).lower() == "xai":
                draft = _extract_ai_text(result)
                rewrite_reasons = _policy_rewrite_reasons(draft)
                if _draft_needs_customer_rewrite(draft):
                    ticket_context = user_query
                    if len(ticket_context) > 7000:
                        ticket_context = (
                            ticket_context[:7000].rstrip() + "\n[truncated]"
                        )
                    draft_context = draft
                    if len(draft_context) > 7000:
                        draft_context = draft_context[:7000].rstrip() + "\n[truncated]"

                    guidance_parts: List[str] = []
                    if internal_context:
                        guidance_parts.append(internal_context)
                    if web_context:
                        guidance_parts.append(web_context)
                    guidance = "\n\n".join([p for p in guidance_parts if p]).strip()

                    prompt = (
                        "Rewrite the content into a customer-ready Mailbird support reply.\n\n"
                        "Output rules (must follow exactly):\n"
                        "- Output ONLY the customer reply (no headings, no analysis, no tool results, no IDs).\n"
                        "- Do NOT include any text like 'Assistant:', 'Tool results', 'KB ID', 'Macro ID', or 'Final output:'.\n"
                        "- Do NOT mention internal tooling, retrieval, or web scraping.\n"
                        "- Do NOT use exclamation marks.\n"
                        "- Do NOT address the customer by name.\n"
                        "- Start with exactly two lines:\n"
                        "  Hi there,\n"
                        "  Many thanks for contacting the Mailbird Customer Happiness Team.\n"
                        "- After the greeting, add two sentences:\n"
                        "  - First, an empathetic bridge that acknowledges their emotion and impact, referencing a specific detail they shared.\n"
                        "  - Second, restate the main issue with their exact details (error text, provider, goal).\n"
                        "- The empathetic bridge must be the third line. Avoid defaulting to \"It sounds like\".\n"
                        "- If they provided logs, screenshots, or steps tried, thank them for the effort.\n"
                        "- Zendesk ticket policies (follow when applicable):\n"
                        "  - If requesting a log file, follow the macro titled: TECH: Request log file - Using Mailbird Number 2 (paraphrase, but keep ALL steps).\n"
                        "  - If the ticket is unclear, ask for the missing details and request a screenshot (macro: REQUEST:: Ask for a screenshot).\n"
                        '  - If suggesting remove/re-add or reinstall, include backup-first steps (close Mailbird; File Explorer → C:\\Users\\"your user name"\\AppData\\Local; copy the Mailbird folder).\n'
                        "  - If a refund is requested for Premium Pay Once or Premium Yearly, propose the 50% option first (refund experiment macro).\n"
                        "- Do NOT paste macros verbatim; paraphrase while preserving all required details.\n"
                        "- Keep it concise but actionable; include step-by-step instructions when helpful.\n"
                        "- Formatting: use short paragraphs separated by blank lines.\n"
                        "- Formatting: use '-' bullets (with 2-space indented sub-bullets) and '1.' numbered steps when needed.\n"
                        "- Formatting: use **bold** for UI labels / key actions and `inline code` for errors, server names, and ports.\n"
                        "- Do NOT use Markdown headings (##). Use **bold** labels if you need structure.\n"
                        "- Do NOT output HTML (Markdown only).\n\n"
                        + (
                            f"Rewrite focus (policy compliance): {', '.join(rewrite_reasons)}\n\n"
                            if rewrite_reasons
                            else ""
                        )
                        + f"Ticket context (redacted):\n{ticket_context}\n\n"
                        + (
                            f"Internal guidance (do NOT cite):\n{guidance}\n\n"
                            if guidance
                            else ""
                        )
                        + f"Draft (may include internal notes; do not copy those parts):\n{draft_context}\n"
                    )

                    try:
                        from langchain_core.messages import SystemMessage
                        from langchain_xai import ChatXAI

                        llm = ChatXAI(
                            model=str(use_model),
                            temperature=0.2,
                            xai_api_key=settings.xai_api_key,
                            timeout=300,
                        )
                        rewritten_text = ""
                        for attempt in range(1, 6):
                            try:
                                rewritten = await llm.ainvoke(
                                    [
                                        SystemMessage(
                                            content=(
                                                "You are a senior Mailbird support agent. "
                                                "Return only the final customer reply."
                                            )
                                        ),
                                        HumanMessage(content=prompt),
                                    ]
                                )
                                rewritten_text = _extract_llm_content(
                                    getattr(rewritten, "content", "")
                                )
                                if rewritten_text:
                                    break
                            except Exception as inner_exc:
                                msg = str(inner_exc)
                                is_429 = "429" in msg or "rate limit" in msg.lower()
                                if attempt < 5 and is_429:
                                    wait_sec = min(90, 10 * attempt)
                                    logger.warning(
                                        "zendesk_xai_rewrite_rate_limited ticket_id=%s attempt=%s wait_sec=%s",
                                        ticket_id,
                                        attempt,
                                        wait_sec,
                                    )
                                    await asyncio.sleep(wait_sec)
                                    continue
                                raise
                        if rewritten_text:
                            result = {"messages": [AIMessage(content=rewritten_text)]}
                    except Exception as exc:
                        logger.warning(
                            "zendesk_xai_rewrite_failed ticket_id=%s error=%s",
                            ticket_id,
                            str(exc)[:180],
                        )

            # For Gemini runs, do a lightweight rewrite when the draft looks like internal/tool output.
            if str(use_provider).lower() == "google" and not rewrite_model:
                draft = _extract_ai_text(result)
                rewrite_reasons = _policy_rewrite_reasons(draft)
                if _draft_needs_customer_rewrite(draft):
                    ticket_context = user_query
                    if len(ticket_context) > 7000:
                        ticket_context = (
                            ticket_context[:7000].rstrip() + "\n[truncated]"
                        )
                    draft_context = draft
                    if len(draft_context) > 7000:
                        draft_context = draft_context[:7000].rstrip() + "\n[truncated]"

                    guidance_parts: List[str] = []
                    if internal_context:
                        guidance_parts.append(internal_context)
                    if web_context:
                        guidance_parts.append(web_context)
                    guidance = "\n\n".join([p for p in guidance_parts if p]).strip()

                    prompt = (
                        "Rewrite the content into a customer-ready Mailbird support reply.\n\n"
                        "Output rules (must follow exactly):\n"
                        "- Output ONLY the customer reply (no headings, no analysis, no tool results, no IDs).\n"
                        "- Do NOT include any text like 'Assistant:', 'Tool results', 'KB ID', 'Macro ID', or 'Final output:'.\n"
                        "- Do NOT mention internal tooling, retrieval, or web scraping.\n"
                        "- Do NOT use exclamation marks.\n"
                        "- Do NOT address the customer by name.\n"
                        "- Start with exactly two lines:\n"
                        "  Hi there,\n"
                        "  Many thanks for contacting the Mailbird Customer Happiness Team.\n"
                        "- After the greeting, add two sentences:\n"
                        "  - First, an empathetic bridge that acknowledges their emotion and impact, referencing a specific detail they shared.\n"
                        "  - Second, restate the main issue with their exact details (error text, provider, goal).\n"
                        "- The empathetic bridge must be the third line. Avoid defaulting to \"It sounds like\".\n"
                        "- If they provided logs, screenshots, or steps tried, thank them for the effort.\n"
                        "- Zendesk ticket policies (follow when applicable):\n"
                        "  - If requesting a log file, follow the macro titled: TECH: Request log file - Using Mailbird Number 2 (paraphrase, but keep ALL steps).\n"
                        "  - If the ticket is unclear, ask for the missing details and request a screenshot (macro: REQUEST:: Ask for a screenshot).\n"
                        '  - If suggesting remove/re-add or reinstall, include backup-first steps (close Mailbird; File Explorer → C:\\Users\\"your user name"\\AppData\\Local; copy the Mailbird folder).\n'
                        "  - If a refund is requested for Premium Pay Once or Premium Yearly, propose the 50% option first (refund experiment macro).\n"
                        "- Do NOT paste macros verbatim; paraphrase while preserving all required details.\n"
                        "- Keep it concise but actionable; include step-by-step instructions when helpful.\n"
                        "- Formatting: use short paragraphs separated by blank lines.\n"
                        "- Formatting: use '-' bullets (with 2-space indented sub-bullets) and '1.' numbered steps when needed.\n"
                        "- Formatting: use **bold** for UI labels / key actions and `inline code` for errors, server names, and ports.\n"
                        "- Do NOT use Markdown headings (##). Use **bold** labels if you need structure.\n"
                        "- Do NOT output HTML (Markdown only).\n\n"
                        + (
                            f"Rewrite focus (policy compliance): {', '.join(rewrite_reasons)}\n\n"
                            if rewrite_reasons
                            else ""
                        )
                        + f"Ticket context (redacted):\n{ticket_context}\n\n"
                        + (
                            f"Internal guidance (do NOT cite):\n{guidance}\n\n"
                            if guidance
                            else ""
                        )
                        + f"Draft (may include internal notes; do not copy those parts):\n{draft_context}\n"
                    )

                    try:
                        from langchain_google_genai import ChatGoogleGenerativeAI

                        llm = ChatGoogleGenerativeAI(
                            model=str(agent_model),
                            temperature=0.2,
                            google_api_key=settings.gemini_api_key,
                            include_thoughts=False,
                            timeout=300,
                        )
                        rewritten_text = ""
                        for attempt in range(1, 6):
                            try:
                                rewritten = await llm.ainvoke(prompt)
                                rewritten_text = _extract_llm_content(
                                    getattr(rewritten, "content", "")
                                )
                                if rewritten_text:
                                    break
                            except Exception as inner_exc:
                                msg = str(inner_exc)
                                is_429 = "429" in msg or "ResourceExhausted" in msg
                                if attempt < 5 and is_429:
                                    wait_sec = min(90, 10 * attempt)
                                    logger.warning(
                                        "zendesk_google_rewrite_rate_limited ticket_id=%s attempt=%s wait_sec=%s",
                                        ticket_id,
                                        attempt,
                                        wait_sec,
                                    )
                                    await asyncio.sleep(wait_sec)
                                    continue
                                raise
                        if rewritten_text:
                            result = {"messages": [AIMessage(content=rewritten_text)]}
                    except Exception as exc:
                        logger.warning(
                            "zendesk_google_rewrite_failed ticket_id=%s error=%s",
                            ticket_id,
                            str(exc)[:180],
                        )

            # Optional Pro rewrite pass (keeps Pro usage to a single, tool-free call).
            if rewrite_model:
                draft = _extract_ai_text(result)
                rewrite_reasons = _policy_rewrite_reasons(draft)
                # Keep the Pro rewrite prompt bounded to reduce quota pressure.
                ticket_context = user_query
                if len(ticket_context) > 6000:
                    ticket_context = ticket_context[:6000].rstrip() + "\n[truncated]"
                draft_context = draft
                if len(draft_context) > 6000:
                    draft_context = draft_context[:6000].rstrip() + "\n[truncated]"

                guidance_parts: List[str] = []
                if internal_context:
                    guidance_parts.append(internal_context)
                if web_context:
                    guidance_parts.append(web_context)
                guidance = "\n\n".join([p for p in guidance_parts if p]).strip()

                prompt = (
                    "You are a senior Mailbird support agent writing an INTERNAL Zendesk note.\n\n"
                    "Rewrite the draft into a clean, customer-ready Suggested Reply only.\n\n"
                    "Rules:\n"
                    "- Do NOT include placeholders like 'Pending'.\n"
                    "- Do NOT include hidden chain-of-thought or planning.\n"
                    "- Output ONLY the Suggested Reply (no Issue Summary / Root Cause / Resources / Follow-up sections).\n"
                    "- Keep it customer-ready (public-facing tone), but do not mention internal tooling, macro IDs, or KB IDs.\n"
                    "- Do NOT use exclamation marks.\n"
                    "- Do NOT address the customer by name.\n"
                    "- Start with exactly two lines:\n"
                    "  Hi there,\n"
                    "  Many thanks for contacting the Mailbird Customer Happiness Team.\n"
                    "- Zendesk ticket policies (follow when applicable):\n"
                    "  - If requesting a log file, follow the macro titled: TECH: Request log file - Using Mailbird Number 2 (paraphrase, but keep ALL steps).\n"
                    "  - If the ticket is unclear, ask for the missing details and request a screenshot (macro: REQUEST:: Ask for a screenshot).\n"
                    '  - If suggesting remove/re-add or reinstall, include backup-first steps (close Mailbird; File Explorer → C:\\Users\\"your user name"\\AppData\\Local; copy the Mailbird folder).\n'
                    "  - If a refund is requested for Premium Pay Once or Premium Yearly, propose the 50% option first (refund experiment macro).\n"
                    "- Do NOT paste macros verbatim; paraphrase while preserving all required details.\n"
                    "- Be concise but actionable; include step-by-step instructions when helpful.\n"
                    "- Formatting: use short paragraphs separated by blank lines.\n"
                    "- Formatting: use '-' bullets (with 2-space indented sub-bullets) and '1.' numbered steps when needed.\n"
                    "- Formatting: use **bold** for UI labels / key actions and `inline code` for errors, server names, and ports.\n"
                    "- Do NOT output HTML (Markdown only).\n\n"
                    + (
                        f"Rewrite focus (policy compliance): {', '.join(rewrite_reasons)}\n\n"
                        if rewrite_reasons
                        else ""
                    )
                    + f"Ticket context (redacted):\n{ticket_context}\n\n"
                    + (
                        f"Internal guidance (do NOT cite):\n{guidance}\n\n"
                        if guidance
                        else ""
                    )
                    + f"Draft to rewrite:\n{draft_context}\n"
                )

                try:
                    from langchain_google_genai import ChatGoogleGenerativeAI

                    llm = ChatGoogleGenerativeAI(
                        model=rewrite_model,
                        temperature=0.2,
                        google_api_key=settings.gemini_api_key,
                        include_thoughts=False,
                        timeout=300,
                    )
                    rewritten_text = ""
                    for attempt in range(1, 7):
                        try:
                            rewritten = await llm.ainvoke(prompt)
                            rewritten_text = _extract_llm_content(
                                getattr(rewritten, "content", "")
                            )
                            if rewritten_text:
                                break
                        except Exception as inner_exc:
                            msg = str(inner_exc)
                            is_429 = "429" in msg or "ResourceExhausted" in msg
                            if attempt < 6 and is_429:
                                wait_sec = min(180, 15 * attempt)
                                logger.warning(
                                    "zendesk_pro_rewrite_rate_limited ticket_id=%s attempt=%s wait_sec=%s",
                                    ticket_id,
                                    attempt,
                                    wait_sec,
                                )
                                await asyncio.sleep(wait_sec)
                                continue
                            raise
                    if not rewritten_text:
                        raise RuntimeError("empty_pro_rewrite_output")
                except Exception as exc:
                    msg = str(exc)
                    if "429" in msg or "ResourceExhausted" in msg:
                        logger.warning(
                            "zendesk_pro_rewrite_skipped ticket_id=%s reason=%s",
                            ticket_id,
                            msg[:180],
                        )
                        rewritten_text = ""
                    else:
                        raise RuntimeError(
                            f"zendesk_pro_rewrite_failed: {exc}"
                        ) from exc

                # Replace agent result with the rewritten output for downstream formatting.
                if rewritten_text:
                    result = {"messages": [AIMessage(content=rewritten_text)]}
                    try:
                        state.model = rewrite_model
                    except Exception:
                        pass
    finally:
        try:
            if attachments:
                from app.integrations.zendesk.attachments import cleanup_attachments

                cleanup_attachments(attachments)
        except Exception:
            pass

    reply_text = _normalize_result_to_text(result, state) or (
        "Thank you for reaching out. We’re reviewing your request and will follow up shortly."
    )
    return ZendeskReplyResult(
        reply=reply_text,
        session_id=session_id,
        ticket_id=str(ticket_id),
        category=inferred_category,
        redacted_ticket_text=user_query,
        kb_articles_used=sorted(set(kb_articles_used)),
        macros_used=sorted(set(macros_used)),
        learning_messages=learning_messages,
    )


async def _process_window(
    window_start: datetime,
    window_end: datetime,
    dry_run: bool,
    provider: str | None = None,
    model: str | None = None,
) -> Dict[str, Any]:
    supa = get_supabase_client()
    # Re-queue tickets that were claimed but never finalized (e.g., crash/timeout).
    try:
        await _requeue_stale_processing(
            max_age_minutes=int(getattr(settings, "zendesk_processing_timeout_minutes", 30) or 30)
        )
    except Exception:
        pass
    # Pull due tickets (pending or retry where next_attempt_at <= now)
    resp = await supa._exec(
        lambda: supa.client.table("zendesk_pending_tickets")
        .select(
            "id,ticket_id,subject,description,created_at,retry_count,next_attempt_at"
        )
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

    # Monthly Zendesk budget enforcement has been removed (no monthly cap).

    # Prepare Zendesk client (validate creds)
    if not (
        settings.zendesk_subdomain
        and settings.zendesk_email
        and settings.zendesk_api_token
    ):
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
    gemini_remaining = max(
        0,
        int(daily.get("gemini_daily_limit", settings.zendesk_gemini_daily_limit))
        - int(daily.get("gemini_calls_used", 0)),
    )
    for row in rows:
        try:
            tid = int(row["ticket_id"])
        except (TypeError, ValueError):
            logger.warning(
                "Skipping ticket with non-numeric id: %s", row.get("ticket_id")
            )
            continue
        if gemini_remaining <= 0 and not dry_run:
            logger.warning("Gemini daily limit exhausted; stopping processing")
            break
        try:
            # Claim row BEFORE doing any heavy work to avoid duplicate compute across workers
            now_iso = datetime.now(timezone.utc).isoformat()
            # Update without select (supabase-py may not support select() on update builders)
            await supa._exec(
                lambda: supa.client.table("zendesk_pending_tickets")
                .update(
                    {
                        "status": "processing",
                        "status_details": {"processing_started_at": now_iso},
                        "last_attempt_at": now_iso,
                    }
                )
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
            if v.get("status") != "processing":
                # Already claimed/processed elsewhere; skip
                continue

            # Exclusions (e.g., solved tickets, or feature-delivery macro tags) should not
            # get an internal note / suggested reply.
            try:
                ticket = await asyncio.to_thread(zc.get_ticket, tid)
            except ZendeskRateLimitError:
                raise
            except Exception:
                ticket = {}
            exclusion = compute_ticket_exclusion(
                ticket if isinstance(ticket, dict) else None,
                brand_id=row.get("brand_id"),
                excluded_statuses=getattr(settings, "zendesk_excluded_statuses", []),
                excluded_tags=getattr(settings, "zendesk_excluded_tags", []),
                excluded_brand_ids=getattr(settings, "zendesk_excluded_brand_ids", []),
            )
            if exclusion.excluded:
                await supa._exec(
                    lambda: supa.client.table("zendesk_pending_tickets")
                    .update(
                        {
                            "status": "processed",
                            "processed_at": datetime.now(timezone.utc).isoformat(),
                            "status_details": {
                                "processing_started_at": now_iso,
                                "skipped": True,
                                "skip_reason": exclusion.reason,
                                **(exclusion.details or {}),
                            },
                        }
                    )
                    .eq("id", row["id"])
                    .execute()
                )
                continue

            # Spam guard: skip obvious spam bursts to avoid LLM processing costs.
            comments = None
            try:
                via = ticket.get("via") if isinstance(ticket, dict) else {}
                source = via.get("source") if isinstance(via, dict) else {}
                from_obj = source.get("from") if isinstance(source, dict) else {}
                recipients = from_obj.get("original_recipients")
                if not (isinstance(recipients, list) and recipients):
                    comments = await asyncio.to_thread(zc.get_ticket_comments, tid, 5)
            except Exception:
                comments = None
            spam_decision = await evaluate_spam_guard(
                ticket_id=tid,
                ticket=ticket,
                comments=comments,
            )
            if spam_decision and spam_decision.skip:
                try:
                    zc.add_internal_note(
                        tid,
                        spam_decision.note,
                        add_tag=spam_decision.tag,
                        use_html=False,
                    )
                except ZendeskRateLimitError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "zendesk_spam_guard_note_failed ticket_id=%s error=%s",
                        tid,
                        str(exc)[:180],
                    )
                await supa._exec(
                    lambda: supa.client.table("zendesk_pending_tickets")
                    .update(
                        {
                            "status": "processed",
                            "processed_at": datetime.now(timezone.utc).isoformat(),
                            "status_details": {
                                "processing_started_at": now_iso,
                                "skipped": True,
                                "skip_reason": spam_decision.reason,
                                **(spam_decision.details or {}),
                            },
                        }
                    )
                    .eq("id", row["id"])
                    .execute()
                )
                continue

            # Generate suggested reply after successful claim
            run = await _generate_reply(
                tid,
                row.get("subject"),
                row.get("description"),
                provider=provider,
                model=model,
            )
            reply = run.reply
            use_html = bool(getattr(settings, "zendesk_use_html", True))
            gate_issues = _quality_gate_issues(reply, use_html=use_html)
            if gate_issues:
                raise RuntimeError(f"quality_gate_failed: {','.join(gate_issues)}")
            # Try HTML if enabled; fallback signature without use_html for test stubs
            try:
                await asyncio.to_thread(
                    zc.add_internal_note,
                    tid,
                    reply,
                    add_tag="mb_auto_triaged",
                    use_html=use_html,
                )
            except TypeError:
                await asyncio.to_thread(
                    zc.add_internal_note, tid, reply, add_tag="mb_auto_triaged"
                )
            await supa._exec(
                lambda: supa.client.table("zendesk_pending_tickets")
                .update(
                    {
                        "status": "processed",
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .eq("id", row["id"])
                .execute()
            )
            _queue_post_resolution_learning(run, dry_run=dry_run)
            processed += 1
            gemini_remaining = (
                gemini_remaining if dry_run else max(0, gemini_remaining - 1)
            )
        except ZendeskRateLimitError as e:
            retry_after = e.retry_after_seconds
            if retry_after is None:
                retry_after = 60.0
            retry_after = max(5.0, float(retry_after) + 1.0)
            next_at = (
                datetime.now(timezone.utc) + timedelta(seconds=retry_after)
            ).isoformat()
            await supa._exec(
                lambda: supa.client.table("zendesk_pending_tickets")
                .update(
                    {
                        "status": "retry",
                        "last_error": str(e)[:500],
                        "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                        "next_attempt_at": next_at,
                    }
                )
                .eq("id", row["id"])
                .execute()
            )
            failures += 1
            rpm_exhausted = True
            logger.warning(
                "Zendesk rate limited; deferring remaining tickets (retry_after=%ss op=%s req_id=%s)",
                int(retry_after),
                e.operation,
                e.request_id,
            )
            break
        except Exception as e:
            logger.warning("posting failed for ticket %s: %s", tid, e)
            err = str(e)
            err_short = err[:500]
            # If credentials invalid (401/403), revert claim and stop this cycle
            if (
                "Zendesk update failed: 401" in err
                or "Zendesk update failed: 403" in err
            ):
                await supa._exec(
                    lambda: supa.client.table("zendesk_pending_tickets")
                    .update(
                        {
                            "status": "pending",
                            "last_error": "zendesk_auth_failed",
                            "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    .eq("id", row["id"])
                    .execute()
                )
                failures += 1
                break

            # 404s can happen when a ticket is deleted/merged; don't retry.
            if "Zendesk update failed: 404" in err:
                rc = (row.get("retry_count") or 0) + 1
                await supa._exec(
                    lambda: supa.client.table("zendesk_pending_tickets")
                    .update(
                        {
                            "status": "failed",
                            "retry_count": rc,
                            "last_error": "zendesk_ticket_not_found",
                            "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                            "next_attempt_at": None,
                        }
                    )
                    .eq("id", row["id"])
                    .execute()
                )
                failures += 1
                continue
            rc = (row.get("retry_count") or 0) + 1
            if rc >= getattr(settings, "zendesk_max_retries", 5):
                new_status = "failed"
                next_at = None
            else:
                new_status = "retry"
                # backoff: 1,2,4,8,16,32 minutes; capped at 60
                delay_min = min(60, 2 ** min(6, rc - 1))
                next_at = (
                    datetime.now(timezone.utc) + timedelta(minutes=delay_min)
                ).isoformat()
            await supa._exec(
                lambda: supa.client.table("zendesk_pending_tickets")
                .update(
                    {
                        "status": new_status,
                        "retry_count": rc,
                        "last_error": err_short,
                        "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                        "next_attempt_at": next_at,
                    }
                )
                .eq("id", row["id"])
                .execute()
            )
            failures += 1

    # Mark any remaining tickets in the window as dropped (no backfill policy)
    overflow_pending = False
    if rpm_exhausted:
        overflow_pending = True

    # Increment usage only for actual API calls when not dry-run
    if not dry_run and processed > 0:
        await _inc_usage(processed)
        await _inc_daily_usage(processed)

    return {
        "processed": processed,
        "failed": failures,
        "pending_overflow": overflow_pending,
        "rpm_exhausted": rpm_exhausted,
    }


async def start_background_scheduler() -> None:
    """Background loop that runs every N seconds and drains the pending queue respecting RPM & daily limits."""
    interval_sec = max(1, int(getattr(settings, "zendesk_poll_interval_sec", 60)))
    logger.info(
        "Zendesk scheduler starting (interval=%d sec, rpm=%d, monthly_budget=disabled)",
        interval_sec,
        int(getattr(settings, "zendesk_rpm_limit", 240) or 240),
    )

    while True:
        try:
            state = await _get_feature_state()
            if not state.get("enabled", False):
                continue

            now = datetime.now(timezone.utc).replace(microsecond=0)
            window_start = now - timedelta(seconds=interval_sec)
            result = await _process_window(
                window_start,
                now,
                bool(state.get("dry_run", True)),
                provider=state.get("provider"),
                model=state.get("model"),
            )
            logger.info("Zendesk window processed: %s", result)
            await _set_last_run(now)
            # Mark last success timestamp
            try:
                supa = get_supabase_client()
                await supa._exec(
                    lambda: supa.client.table("feature_flags")
                    .upsert(
                        {
                            "key": "zendesk_scheduler",
                            "value": {
                                "last_run_at": now.isoformat(),
                                "last_success_at": now.isoformat(),
                            },
                        }
                    )
                    .execute()
                )
            except Exception:
                pass
            # Daily maintenance: webhook cleanup + queue retention
            await _run_daily_maintenance(
                webhook_retention_days=7,
                queue_retention_days=getattr(
                    settings, "zendesk_queue_retention_days", 30
                ),
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
                    .upsert(
                        {
                            "key": "zendesk_scheduler",
                            "value": cur_val,
                        }
                    )
                    .execute()
                )
            except Exception:
                pass
        finally:
            await asyncio.sleep(interval_sec)
