"""Thread-state ("compressed truth") extraction and migration helpers.

Phase 1 responsibilities:
- One-time ingest of legacy workspace handoff context (/handoff/summary.json) into GraphState.thread_state
- Structured thread-state extraction at tool-burst boundaries using the fixed summarization model

The thread_state is persisted via the LangGraph checkpointer as part of GraphState.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Optional, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from loguru import logger

from app.agents.orchestration.orchestration.state import (
    GraphState,
    ThreadState,
    ThreadStateDecision,
)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


THREAD_STATE_EXTRACTION_SYSTEM_PROMPT = """
You extract and maintain a compact, structured "thread_state" for a long-running agent run.

Return ONLY a single JSON object that matches this schema exactly:
{
  "one_line_status": "string",
  "user_intent": "string",
  "constraints": ["string"],
  "decisions": [{"decision": "string", "rationale": "string"}],
  "active_todos": ["string"],
  "progress_so_far": "string",
  "open_questions": ["string"],
  "artifacts": ["string"],
  "risks": ["string"],
  "assumptions": ["string"]
}

Rules:
- "one_line_status" MUST be a single line (no newlines).
- Prefer overwrite semantics: output the full new truth, not a patch/diff.
- Do NOT invent tools, artifacts, or results; use only provided evidence.
- Keep lists short, deduplicated, and high-signal.
- If unknown, use empty strings/lists (never null).
""".strip()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_message_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
            elif isinstance(part, dict) and part.get("type") == "image_url":
                url = part.get("image_url") or {}
                parts.append(f"[image_url:{url.get('url', '')}]")
            else:
                parts.append(str(part))
        return "\n".join(p for p in parts if p)
    return str(content)


def _strip_code_fences(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text or "").strip()


def _extract_json_object(text: str) -> Optional[str]:
    """Extract the first top-level JSON object from a string."""
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n\n[...truncated {len(text) - max_chars} chars...]"


def _trailing_tool_messages(messages: Sequence[BaseMessage]) -> list[ToolMessage]:
    trailing: list[ToolMessage] = []
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            trailing.append(msg)
        else:
            break
    trailing.reverse()
    return trailing


def compute_tool_burst_signature(messages: Sequence[BaseMessage]) -> Optional[str]:
    """Compute a stable signature for the last tool burst (if any)."""
    trailing = _trailing_tool_messages(messages)
    if not trailing:
        return None
    parts = []
    for msg in trailing:
        tool_call_id = getattr(msg, "tool_call_id", None) or ""
        name = getattr(msg, "name", None) or ""
        content = _coerce_message_text(msg)
        parts.append(f"{tool_call_id}:{name}:{content[:400]}")
    digest = sha256("|".join(parts).encode("utf-8", errors="ignore")).hexdigest()
    return digest[:24]


def map_workspace_handoff_to_thread_state(handoff: dict[str, Any]) -> ThreadState:
    summary = str(handoff.get("summary") or "").strip()
    next_steps = handoff.get("next_steps") or []
    if not isinstance(next_steps, list):
        next_steps = []

    active_todos_raw = handoff.get("active_todos") or []
    active_todos: list[str] = []
    if isinstance(active_todos_raw, list):
        for item in active_todos_raw:
            if isinstance(item, dict):
                content = str(item.get("content") or item.get("title") or "").strip()
                status = str(item.get("status") or "").strip()
                if content and status:
                    active_todos.append(f"[{status}] {content}")
                elif content:
                    active_todos.append(content)
            elif item is not None:
                active_todos.append(str(item))

    decisions_raw = handoff.get("key_decisions") or []
    decisions: list[ThreadStateDecision] = []
    if isinstance(decisions_raw, list):
        for item in decisions_raw:
            if isinstance(item, dict):
                decision = str(
                    item.get("decision") or item.get("content") or ""
                ).strip()
                rationale = str(item.get("rationale") or "").strip()
                if decision:
                    decisions.append(
                        ThreadStateDecision(decision=decision, rationale=rationale)
                    )
            elif isinstance(item, str) and item.strip():
                decisions.append(
                    ThreadStateDecision(decision=item.strip(), rationale="")
                )

    user_intent = ""
    match = re.search(r"^User Request:\s*(.+)$", summary, re.IGNORECASE | re.MULTILINE)
    if match:
        user_intent = match.group(1).strip()

    one_line_status = ""
    if next_steps and isinstance(next_steps[0], str) and next_steps[0].strip():
        one_line_status = f"Resuming: {next_steps[0].strip()}"
    elif user_intent:
        one_line_status = f"Resuming: {user_intent}"
    else:
        one_line_status = "Resuming previous session"

    progress_so_far_parts = []
    if summary:
        progress_so_far_parts.append(summary)
    if next_steps:
        rendered = "\n".join(
            f"- {str(step)}" for step in next_steps if step is not None
        )
        if rendered.strip():
            progress_so_far_parts.append(f"Suggested next steps:\n{rendered}")

    return ThreadState(
        one_line_status=one_line_status,
        user_intent=user_intent,
        constraints=[],
        decisions=decisions,
        active_todos=active_todos,
        progress_so_far="\n\n".join(progress_so_far_parts).strip(),
        open_questions=[],
        artifacts=[],
        risks=[],
        assumptions=[],
        last_updated_at=_utc_now_iso(),
    )


def _build_thread_state_extraction_input(
    *,
    state: GraphState,
    current_date: str,
    tool_burst_signature: str,
) -> str:
    previous = (
        state.thread_state.model_dump() if state.thread_state is not None else None
    )
    previous_json = (
        json.dumps(previous, ensure_ascii=False, indent=2) if previous else "{}"
    )

    todos = state.todos or []
    todos_json = json.dumps(todos, ensure_ascii=False, indent=2) if todos else "[]"

    messages = state.messages or []
    trailing_tools = _trailing_tool_messages(messages)

    # Include the tool-requesting AI message right before the trailing tool messages (if present).
    tool_request: Optional[AIMessage] = None
    if trailing_tools:
        idx = len(messages) - len(trailing_tools) - 1
        if idx >= 0:
            tool_candidate = messages[idx]
            if isinstance(tool_candidate, AIMessage):
                tool_request = tool_candidate

    parts: list[str] = [
        f"Current date: {current_date}",
        f"Tool burst signature: {tool_burst_signature}",
        "",
        "Previous thread_state (JSON):",
        previous_json,
        "",
        "Graph todos (raw, JSON):",
        todos_json,
        "",
        "Recent tool burst:",
    ]

    if tool_request is not None:
        tool_calls = (
            getattr(tool_request, "tool_calls", None)
            or (
                (getattr(tool_request, "additional_kwargs", {}) or {}).get("tool_calls")
            )
            or []
        )
        tool_names = [tc.get("name") for tc in tool_calls if isinstance(tc, dict)]
        parts.append(f"AI tool request: tools={tool_names}")

    for msg in trailing_tools:
        tool_name = getattr(msg, "name", None) or "tool"
        tool_call_id = getattr(msg, "tool_call_id", None) or ""
        content = _truncate(_coerce_message_text(msg), 8000)
        parts.append(
            f"\n[ToolResult] name={tool_name} tool_call_id={tool_call_id}\n{content}"
        )

    # Also include the most recent user message (helps stabilize user_intent).
    for recent_msg in reversed(messages):
        if isinstance(recent_msg, HumanMessage):
            parts.append(
                "\nMost recent user message:\n"
                + _truncate(_coerce_message_text(recent_msg), 4000)
            )
            break

    return "\n".join(parts).strip()


async def extract_thread_state_at_tool_burst(
    *,
    summarizer_model: BaseChatModel,
    state: GraphState,
    current_date: str,
) -> Optional[ThreadState]:
    """Extract and return a new thread_state after a tool burst.

    Returns None if no tool burst is present or if extraction fails.
    """
    signature = compute_tool_burst_signature(state.messages or [])
    if signature is None:
        return None

    system_bucket: dict[str, Any] = {}
    if isinstance(state.scratchpad, dict):
        system_bucket = dict((state.scratchpad.get("_system") or {}))

    last_seen = system_bucket.get("thread_state_last_tool_burst")
    if isinstance(last_seen, str) and last_seen == signature:
        return None

    human_input = _build_thread_state_extraction_input(
        state=state,
        current_date=current_date,
        tool_burst_signature=signature,
    )

    try:
        response = await summarizer_model.ainvoke(
            [
                SystemMessage(content=THREAD_STATE_EXTRACTION_SYSTEM_PROMPT),
                HumanMessage(content=human_input),
            ]
        )
    except Exception as exc:
        logger.warning("thread_state_extraction_model_failed", error=str(exc))
        return None

    raw = (
        _coerce_message_text(response)
        if isinstance(response, BaseMessage)
        else str(response)
    )
    cleaned = _strip_code_fences(raw)
    json_text = _extract_json_object(cleaned) or _extract_json_object(raw)
    if not json_text:
        logger.warning("thread_state_extraction_parse_failed", reason="no_json_object")
        return None

    try:
        payload = json.loads(json_text)
    except Exception as exc:
        logger.warning("thread_state_extraction_parse_failed", error=str(exc))
        return None

    if not isinstance(payload, dict):
        logger.warning("thread_state_extraction_parse_failed", reason="not_object")
        return None

    payload.setdefault("last_updated_at", _utc_now_iso())
    if isinstance(payload.get("one_line_status"), str):
        payload["one_line_status"] = " ".join(
            payload["one_line_status"].splitlines()
        ).strip()

    try:
        next_state = ThreadState.model_validate(payload)
    except Exception as exc:
        logger.warning("thread_state_extraction_validation_failed", error=str(exc))
        return None

    # Persist burst signature for idempotency (GraphState scratchpad is checkpointed).
    if isinstance(state.scratchpad, dict):
        system_bucket["thread_state_last_tool_burst"] = signature
        state.scratchpad["_system"] = system_bucket

    return next_state


async def maybe_ingest_legacy_handoff(
    *,
    state: GraphState,
    workspace_store: Any,
) -> bool:
    """One-time migration of /handoff/summary.json into state.thread_state.

    Returns True if a migration occurred.
    """
    if state.thread_state is not None:
        return False

    system_bucket: dict[str, Any] = {}
    if isinstance(state.scratchpad, dict):
        system_bucket = dict((state.scratchpad.get("_system") or {}))

    if system_bucket.get("handoff_migration_checked") is True:
        return False

    handoff: Optional[dict[str, Any]] = None
    try:
        handoff = await workspace_store.get_handoff_context()
    except Exception as exc:
        logger.debug("handoff_migration_read_failed", error=str(exc))
    finally:
        if isinstance(state.scratchpad, dict):
            system_bucket["handoff_migration_checked"] = True
            state.scratchpad["_system"] = system_bucket

    if not handoff:
        return False

    try:
        state.thread_state = map_workspace_handoff_to_thread_state(handoff)
        if isinstance(state.scratchpad, dict):
            system_bucket["handoff_migrated_at"] = _utc_now_iso()
            system_bucket["handoff_migrated"] = True
            state.scratchpad["_system"] = system_bucket
        return True
    except Exception as exc:
        logger.warning("handoff_migration_failed", error=str(exc))
        return False
