"""Unified Agent Sparrow implementation built on LangGraph v1."""

from __future__ import annotations

import itertools
import asyncio
import time
import hashlib
import json
import re
import textwrap
import urllib.parse
import base64
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.config import RunnableConfig, get_stream_writer
from loguru import logger

# Import middleware classes from correct sources
try:
    # LangChain provides TodoList and Summarization middleware
    from langchain.agents.middleware import TodoListMiddleware
    from langchain.agents.middleware.summarization import SummarizationMiddleware

    # DeepAgents provides SubAgent and PatchToolCalls middleware
    from deepagents.middleware.subagents import SubAgentMiddleware
    from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware

    MIDDLEWARE_AVAILABLE = True
    class SubAgentTodoListMiddleware(TodoListMiddleware):
        """Distinct marker to avoid duplicate detection."""

        pass

    class SubAgentSummarizationMiddleware(SummarizationMiddleware):
        """Subagent-specific summarization variant."""

        pass
except ImportError as e:
    logger.warning(f"Middleware not available ({e}) - agent will run without middleware")
    MIDDLEWARE_AVAILABLE = False

from app.agents.orchestration.orchestration.state import GraphState
from app.core.settings import settings
from app.memory import memory_service
from app.core.rate_limiting.agent_wrapper import get_rate_limiter
from app.core.rate_limiting.exceptions import (
    CircuitBreakerOpenException,
    RateLimitExceededException,
    GeminiServiceUnavailableException,
)
from app.agents.helpers.gemma_helper import GemmaHelper

from .model_router import ModelSelectionResult, model_router
from .tools import get_registered_tools
from .subagents import get_subagent_specs
from .prompts import COORDINATOR_PROMPT, TODO_PROMPT

MEMORY_AGENT_ID = "sparrow"
MEMORY_SYSTEM_NAME = "server_memory_context"
BASE_AGENT_PROMPT = (
    "In order to complete the objective that the user asks of you, you have access to a number "
    "of standard tools."
)
DEFAULT_RECURSION_LIMIT = 120
MAX_ATTACHMENTS = 5
HELPER_TIMEOUT_SECONDS = 8.0
MAX_BASE64_CHARS = 480000  # Prevent unbounded base64 payloads from consuming memory.


tracer = trace.get_tracer(__name__)

# Simple per-session helper/grounding caches with short TTL to reduce repeat calls.
SESSION_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}
SESSION_CACHE_TTL = 600  # seconds
BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


@dataclass
class AgentRuntimeConfig:
    """Resolved runtime configuration for a single run."""

    provider: str
    model: str
    task_type: str


def _resolve_runtime_config(state: GraphState) -> AgentRuntimeConfig:
    provider = (state.provider or settings.primary_agent_provider or "google").lower()
    task_type = _determine_task_type(state)

    user_override = state.model
    selected_model = model_router.select_model(task_type, user_override=user_override)
    state.model = selected_model

    return AgentRuntimeConfig(provider=provider, model=selected_model, task_type=task_type)


async def _with_timeout(coro: Any, timeout_seconds: float, label: str):
    """Apply a timeout to helper calls to avoid hanging the agent loop."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning("%s_timeout", label, timeout=timeout_seconds)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("%s_failed", label, error=str(exc))
    return None


def _determine_task_type(state: GraphState) -> str:
    forwarded_props = getattr(state, "forwarded_props", {}) or {}
    coordinator_mode = forwarded_props.get("coordinator_mode") or getattr(state, "coordinator_mode", None)
    heavy_mode = isinstance(coordinator_mode, str) and coordinator_mode.lower() in {"heavy", "pro", "coordinator_heavy"}
    return "coordinator_heavy" if heavy_mode else "coordinator"


def _get_session_cache(session_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
    if not session_id:
        return {}
    now = time.time()
    cache = SESSION_CACHE.setdefault(session_id, {})
    # prune expired entries
    expired = [k for k, v in cache.items() if v.get("ts", 0) + SESSION_CACHE_TTL < now]
    for k in expired:
        cache.pop(k, None)
    return cache


def _stringify_message_content(content: Any) -> str:
    """Best-effort conversion of LangChain message chunks into plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (int, float, bool)):
        return str(content)
    if isinstance(content, BaseMessage):  # type: ignore[arg-type]
        return _stringify_message_content(content.content)
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
        return json.dumps(content, default=str)
    if isinstance(content, list):
        return " ".join(_stringify_message_content(part) for part in content)
    return str(content)


def _extract_tool_name(raw_name: Any, tool_call_id: str) -> str:
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name
    if tool_call_id and tool_call_id != "unknown":
        return tool_call_id
    return "tool"


async def _ensure_model_selection(state: GraphState) -> ModelSelectionResult:
    task_type = _determine_task_type(state)
    selection = await model_router.select_model_with_health(task_type, user_override=state.model)
    state.model = selection.model

    system_bucket = state.scratchpad.setdefault("_system", {}) if isinstance(state.scratchpad, dict) else {}
    if isinstance(state.scratchpad, dict):
        system_bucket["model_selection"] = {
            "task_type": selection.task_type,
            "selected_model": selection.model,
            "attempts": selection.trace_dict(),
        }
        state.scratchpad["_system"] = system_bucket

    final_health = selection.health_trace[-1] if selection.health_trace else None
    if final_health and not final_health.available:
        logger.warning(
            "Selected %s for task=%s despite limited availability (reason=%s)",
            selection.model,
            selection.task_type,
            final_health.reason,
        )

    return selection


def _build_chat_model(runtime: AgentRuntimeConfig):
    if runtime.provider != "google":
        logger.warning(
            "Unsupported provider '%s' requested; falling back to Google Gemini",
            runtime.provider,
        )
    from langchain_google_genai import ChatGoogleGenerativeAI
    from app.core.settings import settings
    return ChatGoogleGenerativeAI(
        model=runtime.model,
        temperature=0.3,
        google_api_key=settings.gemini_api_key,
    )


def _build_deep_agent(state: GraphState, runtime: AgentRuntimeConfig):
    chat_model = _build_chat_model(runtime)
    tools = get_registered_tools()
    subagents = get_subagent_specs()

    todo_prompt = TODO_PROMPT if "TODO_PROMPT" in globals() else ""
    system_prompt_parts = [COORDINATOR_PROMPT, todo_prompt, BASE_AGENT_PROMPT]
    system_prompt = "\n\n".join(part for part in system_prompt_parts if part)

    middleware_stack = []
    if MIDDLEWARE_AVAILABLE:
        coordinator_middleware = SubAgentMiddleware(
            default_model=chat_model,
            default_tools=tools,
            subagents=subagents,
            default_middleware=[
                SubAgentTodoListMiddleware(),
                SubAgentSummarizationMiddleware(
                    model=chat_model,
                    max_tokens_before_summary=170000,
                    messages_to_keep=6,
                ),
                PatchToolCallsMiddleware(),
            ],
            general_purpose_agent=True,
        )
        middleware_stack.append(coordinator_middleware)
        logger.debug(
            "Coordinator middleware stack initialized: {}",
            [mw.name for mw in middleware_stack],
        )
    else:
        logger.warning("Running unified agent without middleware - functionality may be limited")

    agent = create_agent(
        chat_model,
        system_prompt=system_prompt,
        tools=tools,
        middleware=middleware_stack,
    )

    return agent.with_config({"recursion_limit": 1000})


def _build_runnable_config(
    state: GraphState,
    config: Optional[RunnableConfig],
    runtime: AgentRuntimeConfig,
) -> Dict[str, Any]:
    base_config: Dict[str, Any] = dict(config or {})  # type: ignore[arg-type]
    recursion_limit = base_config.get("recursion_limit")
    if recursion_limit is None:
        # Default LangGraph recursion limit (25) is too low for multi-hop research flows.
        base_config["recursion_limit"] = DEFAULT_RECURSION_LIMIT
    else:
        try:
            base_config["recursion_limit"] = int(recursion_limit)
        except Exception:
            base_config["recursion_limit"] = DEFAULT_RECURSION_LIMIT
    configurable = dict(base_config.get("configurable") or {})
    configurable.setdefault("thread_id", state.session_id)
    configurable.setdefault("trace_id", state.trace_id)
    configurable.update({
        "provider": state.provider,
        "model": state.model,
        "use_server_memory": state.use_server_memory,
    })
    metadata = dict(configurable.get("metadata") or {})
    metadata.setdefault("session_id", state.session_id)
    metadata.setdefault("trace_id", state.trace_id)
    metadata.setdefault("resolved_task_type", runtime.task_type)
    metadata.setdefault("resolved_model", runtime.model)

    model_selection = None
    if isinstance(state.scratchpad, dict):
        model_selection = (state.scratchpad.get("_system") or {}).get("model_selection")
    if model_selection:
        metadata.setdefault("model_selection", model_selection)

    # Add predict_state metadata for GenUI
    metadata.setdefault("predict_state", [{
        "state_key": "steps",
        "tool": "generate_task_steps_generative_ui",
        "tool_argument": "steps",
    }])

    configurable["metadata"] = metadata

    tags = list(configurable.get("tags") or [])
    for tag in (
        "sparrow-unified",
        state.provider or None,
        state.model or None,
        f"resolved-model:{runtime.model}",
        f"resolved-task:{runtime.task_type}",
    ):
        if tag and tag not in tags:
            tags.append(tag)
    configurable["tags"] = tags

    if settings.langsmith_tracing_enabled:
        configurable.setdefault("name", "sparrow-unified-agent")
        if settings.langsmith_project:
            configurable.setdefault("project", settings.langsmith_project)
        if settings.langsmith_endpoint:
            configurable.setdefault("endpoint", settings.langsmith_endpoint)

    base_config["configurable"] = configurable
    return base_config


def _memory_is_enabled(state: GraphState) -> bool:
    """Return True when memory should run; emit diagnostics when misconfigured."""

    backend_ready = settings.should_enable_agent_memory()
    requested = bool(getattr(state, "use_server_memory", False))

    if requested and not backend_ready and isinstance(state.scratchpad, dict):
        system_bucket = state.scratchpad.setdefault("_system", {})
        system_bucket["memory"] = {
            "requested": True,
            "enabled": False,
            "reason": "backend_not_configured",
            "enable_agent_memory": settings.enable_agent_memory,
            "memory_backend": settings.memory_backend,
            "supabase_db_conn_configured": bool(settings.supabase_db_conn),
        }
        state.scratchpad["_system"] = system_bucket

    return requested and backend_ready


def _coerce_message_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for chunk in content:
            if isinstance(chunk, dict) and chunk.get("type") == "text":
                parts.append(str(chunk.get("text") or ""))
            else:
                parts.append(str(chunk))
        return "".join(parts)
    return str(content) if content is not None else ""


def _decode_data_url_text(data_url: str, max_chars: int = 120000) -> Optional[str]:
    """Decode a data URL (or raw base64/text) to text, trimming to max_chars."""
    header: Optional[str] = None
    encoded: str = data_url
    is_base64 = False

    # Accept both full data URLs and raw base64/text blobs
    if data_url.startswith("data:"):
        try:
            header, encoded = data_url.split(",", 1)
            is_base64 = ";base64" in header.lower()
        except ValueError:
            return None

    # Normalize encoding (strip whitespace/newlines and URL escapes)
    encoded_clean = urllib.parse.unquote(encoded or "")
    encoded_clean = re.sub(r"[\r\n\t ]+", "", encoded_clean)

    # Guard against unbounded payloads before decoding
    if len(encoded_clean) > MAX_BASE64_CHARS:
        logger.warning("attachment_base64_too_large", length=len(encoded_clean))
        return None

    # Heuristic: if no explicit header, guess base64 when the payload is base64-like
    if not is_base64:
        is_base64 = bool(BASE64_PATTERN.fullmatch(encoded_clean)) and len(encoded_clean) % 4 in (0, 2, 3)

    text: Optional[str]
    try:
        if is_base64:
            padding_needed = (-len(encoded_clean)) % 4
            padded = encoded_clean + ("=" * padding_needed)
            raw = base64.b64decode(padded, validate=True)
            text = raw.decode("utf-8", errors="replace")
        else:
            text = encoded_clean
    except Exception as exc:
        # Last resort: treat as URL-decoded plain text
        logger.warning(
            "attachment_base64_decode_failed",
            error=str(exc),
            sample=encoded_clean[:64],
        )
        text = encoded_clean

    if text is None:
        return None

    text = text.strip()
    if len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text


def _format_log_analysis_result(raw: Any) -> Optional[str]:
    """Render log analysis output into a readable summary."""
    data: Optional[Dict[str, Any]] = None
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception:
            return None
    if not data:
        return None

    summary = data.get("overall_summary") or data.get("summary")
    health = data.get("health_status")
    concerns = data.get("priority_concerns") or []
    issues = data.get("identified_issues") or data.get("issues") or []
    solutions = data.get("proposed_solutions") or data.get("solutions") or []
    confidence = data.get("confidence_level")

    lines: List[str] = []
    if summary:
        lines.append(f"Summary: {summary}")
    if health:
        lines.append(f"Health: {health}")
    if concerns:
        bullet = "; ".join(str(c) for c in concerns if c)
        if bullet:
            lines.append(f"Top concerns: {bullet}")

    def _issue_line(issue: Any) -> Optional[str]:
        if not isinstance(issue, dict):
            return None
        title = issue.get("title") or ""
        sev = issue.get("severity")
        details = issue.get("details") or issue.get("description") or ""
        prefix = f"[{sev}] " if sev else ""
        body = f"{prefix}{title}".strip() if title else (prefix.strip() if prefix else "")
        if details:
            body = f"{body}: {details}" if body else details
        return body.strip() or None

    rendered_issues = [ln for ln in (_issue_line(item) for item in issues) if ln]
    if rendered_issues:
        lines.append("Issues:")
        lines.extend(f"- {ln}" for ln in rendered_issues)

    def _solution_lines(solution: Any) -> Optional[List[str]]:
        if not isinstance(solution, dict):
            return None
        title = solution.get("title") or "Recommended action"
        steps = solution.get("steps") or []
        step_lines = [f"{idx+1}. {step}" for idx, step in enumerate(steps) if step]
        if not step_lines:
            return None
        return [f"{title}:"] + [f"   {s}" for s in step_lines]

    rendered_solutions: List[str] = []
    for sol in solutions:
        rendered = _solution_lines(sol)
        if rendered:
            rendered_solutions.extend(f"- {line}" if i == 0 else line for i, line in enumerate(rendered))
    if rendered_solutions:
        lines.append("Recommended actions:")
        lines.extend(rendered_solutions)

    if confidence is not None:
        try:
            conf_pct = round(float(confidence) * 100)
            lines.append(f"Confidence: ~{conf_pct}%")
        except Exception:
            pass

    return "\n".join(lines) if lines else None


def _extract_last_user_query(messages: List[BaseMessage]) -> str:
    for message in reversed(messages or []):
        if getattr(message, "type", None) == "human":
            text = _coerce_message_text(message).strip()
            if text:
                return text
    return ""


_BULLET_PREFIX = re.compile(r"^[-*•]\s+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _summarize_response_to_facts(text: str, max_facts: int = 3, max_chars: int = 280) -> List[str]:
    normalized = (text or "").strip()
    if not normalized:
        return []

    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    bullet_candidates = [
        _BULLET_PREFIX.sub("", line).strip()
        for line in lines
        if _BULLET_PREFIX.match(line)
    ]

    if bullet_candidates:
        candidates = bullet_candidates
    else:
        candidates = _split_into_sentences(normalized)

    seen: Set[str] = set()
    distilled: List[str] = []
    for candidate in candidates:
        clean = re.sub(r"\s+", " ", candidate).strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        distilled.append(textwrap.shorten(clean, width=max_chars, placeholder="…"))
        if len(distilled) >= max_facts:
            break
    return distilled


def _split_into_sentences(text: str) -> List[str]:
    parts = _SENTENCE_BOUNDARY.split(text)
    sentences: List[str] = []
    for part in parts:
        stripped = part.strip()
        if len(stripped) < 20:
            continue
        sentences.append(stripped)
    return sentences


def _extract_structured_entries(data: Any) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []

    def _collect(items: Any) -> None:
        if isinstance(items, dict):
            entries.append(items)
        elif isinstance(items, list):
            for item in items:
                _collect(item)

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                entries.append(item)
            elif isinstance(item, list):
                entries.extend([sub for sub in item if isinstance(sub, dict)])
    elif isinstance(data, dict):
        for key in ("results", "items", "data", "entries", "documents"):
            value = data.get(key)
            if isinstance(value, list):
                entries.extend([item for item in value if isinstance(item, dict)])
        if not entries and any(isinstance(v, dict) for v in data.values()):
            _collect(list(data.values()))
        if not entries and all(isinstance(v, (str, int, float, bool, type(None))) for v in data.values()):
            # treat dictionary itself as an entry if it looks flat
            entries.append(data)
    return entries


def _summarize_structured_content(content: Any) -> Optional[str]:
    parsed: Any = None

    if isinstance(content, str):
        trimmed = content.strip()
        if not (trimmed.startswith(("{", "[")) and trimmed.endswith(("}", "]"))):
            return None
        try:
            parsed = json.loads(trimmed)
        except Exception:
            return None
    elif isinstance(content, (dict, list)):
        parsed = content
    else:
        return None

    entries = _extract_structured_entries(parsed)
    if not entries:
        return None

    summary_lines = ["Here are the most relevant matches:"]
    for idx, entry in enumerate(entries[:3], start=1):
        title = str(entry.get("title") or entry.get("name") or entry.get("id") or f"Result {idx}").strip()
        snippet = entry.get("snippet") or entry.get("summary") or entry.get("content") or ""
        snippet_text = textwrap.shorten(str(snippet).strip(), width=220, placeholder="…") if snippet else ""
        url = entry.get("url") or entry.get("link")
        line = f"{idx}. **{title}**"
        if snippet_text:
            line += f" – {snippet_text}"
        if isinstance(url, str) and url.strip():
            line += f" ({url.strip()})"
        summary_lines.append(line)

    return "\n".join(summary_lines)


def _safe_json_value(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        if isinstance(value, str):
            trimmed = value.strip()
            if (trimmed.startswith("{") and trimmed.endswith("}")) or (
                trimmed.startswith("[") and trimmed.endswith("]")
            ):
                try:
                    parsed = json.loads(trimmed)
                    json.dumps(parsed, ensure_ascii=False)
                    return parsed
                except Exception:
                    return value
            return value
        return str(value)


def _polish_ai_message(message: AIMessage) -> AIMessage:
    summary = _summarize_structured_content(message.content)
    if not summary:
        return message
    try:
        return message.model_copy(update={"content": summary})
    except Exception:
        return AIMessage(
            content=summary,
            additional_kwargs=getattr(message, "additional_kwargs", {}),
            example=getattr(message, "example", False),
            name=getattr(message, "name", None),
        )


def _build_memory_system_message(memories: List[Dict[str, Any]]) -> Optional[SystemMessage]:
    lines = []
    for item in memories:
        text = (item.get("memory") or "").strip()
        if not text:
            continue
        score = item.get("score")
        if isinstance(score, (int, float)):
            lines.append(f"- {text} (score={score:.2f})")
        else:
            lines.append(f"- {text}")
    if not lines:
        return None
    header = "Server memory retrieved for this session/user. Use only if relevant:\n"
    return SystemMessage(content=header + "\n".join(lines), name=MEMORY_SYSTEM_NAME)


async def _prepend_memory_context(state: GraphState, enabled: bool) -> List[BaseMessage]:
    if not enabled:
        return state.messages
    query = _extract_last_user_query(state.messages)
    if not query:
        return state.messages

    # Initialize memory stats for LangSmith observability
    memory_stats = {
        "retrieval_attempted": True,
        "query_length": len(query),
        "facts_retrieved": 0,
        "relevance_scores": [],
        "retrieval_error": None,
    }

    try:
        retrieved = await memory_service.retrieve(
            agent_id=MEMORY_AGENT_ID,
            query=query,
            top_k=settings.memory_top_k,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("memory_retrieve_failed", error=str(exc))
        memory_stats["retrieval_error"] = str(exc)
        _update_memory_stats(state, memory_stats)
        return state.messages

    if not retrieved:
        _update_memory_stats(state, memory_stats)
        return state.messages

    # Extract stats from retrieved memories
    memory_stats["facts_retrieved"] = len(retrieved)
    memory_stats["relevance_scores"] = [
        getattr(mem, "score", 0.0) for mem in retrieved
        if hasattr(mem, "score")
    ]

    memory_message = _build_memory_system_message(retrieved)
    if not memory_message:
        _update_memory_stats(state, memory_stats)
        return state.messages

    # Store memory stats in scratchpad for LangSmith
    _update_memory_stats(state, memory_stats)

    return [memory_message, *state.messages]


def _update_memory_stats(state: GraphState, stats: Dict[str, Any]) -> None:
    """Update memory stats in scratchpad for LangSmith observability."""
    if isinstance(state.scratchpad, dict):
        system_bucket = state.scratchpad.setdefault("_system", {})
        memory_section = system_bucket.setdefault("memory_stats", {})
        memory_section.update(stats)
        state.scratchpad["_system"] = system_bucket


def _strip_memory_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    if not messages:
        return messages
    return [
        message
        for message in messages
        if not (isinstance(message, SystemMessage) and message.name == MEMORY_SYSTEM_NAME)
    ]


async def _record_memory(state: GraphState, ai_message: BaseMessage) -> None:
    if not _memory_is_enabled(state):
        return
    if not isinstance(ai_message, BaseMessage):
        return
    fact_text = _coerce_message_text(ai_message).strip()
    facts = _summarize_response_to_facts(fact_text)

    # Initialize memory write stats for LangSmith
    write_stats = {
        "write_attempted": True,
        "facts_extracted": len(facts) if facts else 0,
        "response_length": len(fact_text),
        "write_error": None,
    }

    if not facts:
        _update_memory_stats(state, write_stats)
        return

    meta: Dict[str, Any] = {"source": "unified_agent"}
    if state.user_id:
        meta["user_id"] = state.user_id
    if state.session_id:
        meta["session_id"] = state.session_id
    meta["fact_strategy"] = "sentence_extract"

    try:
        result = await memory_service.add_facts(
            agent_id=MEMORY_AGENT_ID,
            facts=facts,
            meta=meta,
        )
        # Track successful write
        write_stats["write_successful"] = bool(result)
        write_stats["facts_written"] = len(facts)
    except Exception as exc:  # pragma: no cover - best effort persistence
        logger.warning("memory_add_failed", error=str(exc))
        write_stats["write_error"] = str(exc)
        write_stats["write_successful"] = False

    # Update memory stats in scratchpad
    _update_memory_stats(state, write_stats)


async def run_unified_agent(state: GraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Run the unified agent with comprehensive error handling."""
    reserved_slots: List[tuple[str, Optional[str]]] = []
    limiter = None
    completed_successfully = False
    try:
        await _ensure_model_selection(state)
        runtime = _resolve_runtime_config(state)
        limiter = get_rate_limiter()
        helper = GemmaHelper(max_calls=10)
        session_id = getattr(state, "session_id", None) or getattr(state, "trace_id", None)
        session_cache = _get_session_cache(session_id)

        async def _reserve_model_slot(model_name: str) -> bool:
            try:
                result = await limiter.check_and_consume(model_name)
                if getattr(result, "allowed", False):
                    reserved_slots.append((model_name, getattr(result, "token_identifier", None)))
                return True
            except RateLimitExceededException:
                logger.warning("gemini_precheck_rate_limited", model=model_name)
                return False
            except CircuitBreakerOpenException:
                logger.warning("gemini_precheck_circuit_open", model=model_name)
                return False
            except GeminiServiceUnavailableException as exc:
                logger.warning("gemini_precheck_unavailable", model=model_name, error=str(exc))
                return False

        # Preflight rate-limit check; fall back to lite if the primary slot is blocked
        slot_ok = await _reserve_model_slot(runtime.model)
        if not slot_ok:
            fallback_model = model_router.fallback_chain.get(runtime.model) or "gemini-2.5-flash-lite"
            if fallback_model != runtime.model and await _reserve_model_slot(fallback_model):
                logger.info("retrying_with_fallback_model", primary=runtime.model, fallback=fallback_model)
                runtime = AgentRuntimeConfig(provider=runtime.provider, model=fallback_model, task_type=runtime.task_type)
                state.model = fallback_model
            else:
                # No capacity on either the primary or fallback; surface a graceful error upstream
                raise RateLimitExceededException(f"Gemini rate limit reached for {runtime.model}; try again shortly")
        agent = _build_deep_agent(state, runtime)
        run_config = _build_runnable_config(state, config, runtime)
        writer = get_stream_writer()
        memory_enabled = _memory_is_enabled(state)
        messages_with_memory = await _prepend_memory_context(state, memory_enabled)

        # Track the latest user query for potential rewrites and reranks.
        last_user_query = None
        for message in reversed(messages_with_memory):
            if isinstance(message, HumanMessage):
                last_user_query = _coerce_message_text(message)
                break

        # Rewrite user query once to improve grounding recall/precision.
        if last_user_query:
            rewrite_key = f"rewrite:{last_user_query.lower().strip()}"
            cached_rewrite = session_cache.get(rewrite_key, {}).get("value") if session_cache else None
            rewritten = cached_rewrite or await _with_timeout(
                helper.rewrite_query(last_user_query),
                HELPER_TIMEOUT_SECONDS,
                "gemma_rewrite_query",
            )
            if rewritten:
                if session_cache is not None:
                    session_cache[rewrite_key] = {"value": rewritten, "ts": time.time()}
                messages_with_memory.append(
                    SystemMessage(content=f"Rewritten query for retrieval: {rewritten}")
                )
                state.scratchpad.setdefault("_system", {})["rewritten_query"] = rewritten

        # Summarize older history if it's long to cut TPM before the main model.
        if len(messages_with_memory) > 8:
            history_text = "\n\n".join(
                _coerce_message_text(msg) for msg in messages_with_memory[:-4]
            )
            summary = await _with_timeout(
                helper.summarize(history_text, budget_tokens=800),
                HELPER_TIMEOUT_SECONDS,
                "gemma_history_summarize",
            ) if history_text else None
            if summary:
                messages_with_memory = [
                    SystemMessage(content=f"Conversation so far (summarized):\n{summary}"),
                    *messages_with_memory[-4:],
                ]

        # Inline attachment text for text/plain/log files so model can read them directly.
        attachment_blocks: List[str] = []
        attachments_in_scope = list(state.attachments or [])
        if len(attachments_in_scope) > MAX_ATTACHMENTS:
            logger.warning(
                "attachment_limit_exceeded",
                count=len(attachments_in_scope),
                limit=MAX_ATTACHMENTS,
            )
            attachments_in_scope = attachments_in_scope[:MAX_ATTACHMENTS]
        if attachments_in_scope:
            logger.info(
                "attachments_received",
                count=len(attachments_in_scope),
                names=[getattr(att, "name", None) or (att.get("name") if isinstance(att, dict) else None) for att in attachments_in_scope],
            )
            for att in attachments_in_scope:
                mime = getattr(att, "mime_type", None) or (att.get("mime_type") if isinstance(att, dict) else None)
                name = getattr(att, "name", None) or (att.get("name") if isinstance(att, dict) else None)
                data_url = getattr(att, "data_url", None) or (att.get("data_url") if isinstance(att, dict) else None)
                if not data_url:
                    logger.info("attachment_skipped", name=name, reason="missing_data_url")
                    continue
                # Focus on textual/log attachments only
                if mime and not str(mime).startswith("text"):
                    logger.info("attachment_skipped", name=name, reason="non_text_mime", mime=mime)
                    continue
                text = _decode_data_url_text(str(data_url))
                if not text:
                    logger.info("attachment_skipped", name=name, reason="decode_failed", mime=mime)
                    continue
                header = f"Attachment: {name or 'log.txt'}"
                attachment_blocks.append(f"{header}\n{text}")
        if attachment_blocks:
            inline = "\n\n".join(attachment_blocks)
            if len(inline) > 4000:
                summary = await _with_timeout(
                    helper.summarize(inline, budget_tokens=900),
                    HELPER_TIMEOUT_SECONDS,
                    "gemma_attachment_summarize",
                )
                if summary:
                    inline = f"Summarized attachments (Gemma):\n{summary}"
            logger.info("inline_attachments_injected", count=len(attachment_blocks), chars=len(inline))
            messages_with_memory.append(SystemMessage(content=f"Attached logs/content:\n{inline}"))

        def _estimate_tokens(msgs: List[BaseMessage]) -> int:
            total_chars = 0
            for m in msgs:
                total_chars += len(_coerce_message_text(m))
            return int(total_chars / 4)  # rough heuristic

        # If prompt is very large, collapse older context further to avoid TPM spikes.
        if _estimate_tokens(messages_with_memory) > 9000:
            combined = "\n\n".join(
                f"{getattr(m, 'role', 'message')}: {_coerce_message_text(m)}" for m in messages_with_memory
            )
            summary = await _with_timeout(
                helper.summarize(combined, budget_tokens=1200),
                HELPER_TIMEOUT_SECONDS,
                "gemma_context_compact",
            )
            if summary:
                messages_with_memory = [
                    SystemMessage(content=f"Conversation summary (compacted):\n{summary}"),
                    *messages_with_memory[-3:],
                ]

        final_output: Optional[Dict[str, Any]] = None

        def _agent_inputs() -> Dict[str, Any]:
            return {
                "messages": list(messages_with_memory),
                "attachments": state.attachments,
                "scratchpad": state.scratchpad,
            }

        if writer is not None:
            operations: Dict[str, Dict[str, Any]] = {}
            root_operation_id = str(state.trace_id or state.session_id or "run")
            operations[root_operation_id] = {
                "id": root_operation_id,
                "type": "agent",
                "name": "Unified Agent",
                "status": "running",
                "startTime": datetime.now(timezone.utc).isoformat(),
                "children": [],
                "metadata": {
                    "provider": runtime.provider,
                    "model": runtime.model,
                    "task_type": runtime.task_type,
                },
            }

            thinking_trace: List[Dict[str, Any]] = []
            trace_step_aliases: Dict[str, Dict[str, Any]] = {}
            trace_step_counter = itertools.count(1)
            todo_items: List[Dict[str, Any]] = []
            todo_operation_ids: set[str] = set()

            def _emit_custom_event(name: str, value: Dict[str, Any]) -> None:
                if writer is None:
                    return
                writer(
                    {
                        "event": "on_custom_event",
                        "name": name,
                        "data": value,
                    }
                )

            def _serialize_trace_step(step: Dict[str, Any]) -> Dict[str, Any]:
                metadata = step.get("metadata") or {}
                safe_metadata: Dict[str, Any] = {}
                for key, value in metadata.items():
                    try:
                        json.dumps(value)
                        safe_metadata[key] = value
                    except TypeError:
                        safe_metadata[key] = str(value)
                return {
                    "id": step.get("id"),
                    "timestamp": step.get("timestamp"),
                    "type": step.get("type"),
                    "content": step.get("content"),
                    "metadata": safe_metadata,
                }

            def _emit_thinking_trace(step: Optional[Dict[str, Any]] = None, *, sync_all: bool = False) -> None:
                if writer is None:
                    return
                payload: Dict[str, Any] = {"totalSteps": len(thinking_trace)}
                if sync_all or not thinking_trace:
                    payload["thinkingTrace"] = [_serialize_trace_step(s) for s in thinking_trace]
                if step is not None:
                    payload["latestStep"] = _serialize_trace_step(step)
                    payload["activeStepId"] = step.get("id")
                elif thinking_trace:
                    payload["activeStepId"] = thinking_trace[-1].get("id")
                _emit_custom_event("agent_thinking_trace", payload)

            def _append_trace_step(
                step_type: str,
                content: str,
                *,
                metadata: Optional[Dict[str, Any]] = None,
                alias: Optional[str] = None,
            ) -> Dict[str, Any]:
                step = {
                    "id": f"{root_operation_id}-trace-{next(trace_step_counter)}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": step_type,
                    "content": content,
                    "metadata": metadata or {},
                }
                thinking_trace.append(step)
                if alias:
                    trace_step_aliases[alias] = step
                _emit_thinking_trace(step, sync_all=len(thinking_trace) == 1)
                return step

            def _update_trace_step(
                alias: str,
                *,
                append_content: Optional[str] = None,
                replace_content: Optional[str] = None,
                metadata: Optional[Dict[str, Any]] = None,
                step_type: Optional[str] = None,
                finalize: bool = False,
            ) -> Optional[Dict[str, Any]]:
                step = trace_step_aliases.get(alias)
                if step is None:
                    return None
                if append_content:
                    existing = step.get("content") or ""
                    step["content"] = f"{existing}{append_content}"
                if replace_content is not None:
                    step["content"] = replace_content
                if metadata:
                    meta = step.setdefault("metadata", {})
                    meta.update(metadata)
                if step_type:
                    step["type"] = step_type
                step["timestamp"] = datetime.now(timezone.utc).isoformat()
                _emit_thinking_trace(step)
                if finalize:
                    trace_step_aliases.pop(alias, None)
                return step

            def _emit_timeline_update(current_operation_id: Optional[str] = None) -> None:
                if writer is None:
                    return
                value: Dict[str, Any] = {
                    "operations": list(operations.values()),
                }
                if current_operation_id is not None:
                    value["currentOperationId"] = current_operation_id
                _emit_custom_event("agent_timeline_update", value)

            def _normalize_todos(raw: Any) -> List[Dict[str, Any]]:
                normalized: List[Dict[str, Any]] = []
                if not isinstance(raw, list):
                    return normalized
                for idx, item in enumerate(raw):
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title") or item.get("content") or item.get("description") or f"Step {idx + 1}")
                    status = str(item.get("status") or "pending").lower()
                    if status not in {"pending", "in_progress", "done"}:
                        status = "pending"
                    todo_id = str(item.get("id") or f"{root_operation_id}-todo-{idx + 1}")
                    normalized.append({
                        "id": todo_id,
                        "title": title,
                        "status": status,
                        "metadata": item.get("metadata") or {},
                    })
                return normalized

            def _sync_todo_operations() -> None:
                nonlocal todo_operation_ids
                old_ids = list(todo_operation_ids)
                for tid in old_ids:
                    operations.pop(tid, None)
                todo_operation_ids.clear()
                parent_op = operations.get(root_operation_id)
                if parent_op is not None:
                    children = parent_op.get("children") or []
                    parent_op["children"] = [c for c in children if c not in old_ids]

                for idx, todo in enumerate(todo_items):
                    op_id = f"{root_operation_id}-todo-{idx + 1}"
                    status = todo.get("status") or "pending"
                    op_status = "pending"
                    if status == "in_progress":
                        op_status = "running"
                    elif status == "done":
                        op_status = "success"
                    op = {
                        "id": op_id,
                        "type": "todo",
                        "name": todo.get("title") or f"Todo {idx + 1}",
                        "status": op_status,
                        "parent": root_operation_id,
                        "children": [],
                        "metadata": {"todo": todo},
                    }
                    operations[op_id] = op
                    todo_operation_ids.add(op_id)
                    if parent_op is not None:
                        children = parent_op.setdefault("children", [])
                        if op_id not in children:
                            children.append(op_id)
                _emit_timeline_update()
                _emit_custom_event("agent_todos_update", {"todos": todo_items})

            try:
                async def event_generator():
                    """Stream LangChain events and forward tool/custom events to AG-UI."""
                    span_cm = tracer.start_as_current_span("agui.stream.run") if "tracer" in globals() and tracer else nullcontext()
                    with span_cm as run_span:
                        cfg = (run_config or {}).get("configurable", {})
                        if run_span is not None:
                            run_span.set_attribute("agui.session_id", str(cfg.get("session_id") or ""))
                            run_span.set_attribute("agui.trace_id", str(cfg.get("trace_id") or ""))
                            run_span.set_attribute("agui.provider", str(cfg.get("provider") or ""))
                            run_span.set_attribute("agui.model", str(cfg.get("model") or ""))

                        try:
                            async for event in agent.astream_events(
                                _agent_inputs(),
                                config=run_config,
                                version="v2",
                            ):
                                logger.debug(f"Stream event: {event.get('event')} name={event.get('name')}")
                                yield event

                            if run_span is not None:
                                run_span.set_status(Status(StatusCode.OK))
                        except Exception as exc:  # pragma: no cover
                            if run_span is not None:
                                run_span.record_exception(exc)
                                run_span.set_status(Status(StatusCode.ERROR, "agent_run_failed"))
                            logger.error(f"Agent run failed: {str(exc)}", exc_info=True)
                            raise

                async for event in event_generator():
                    event_type = event.get("event")
                    data = event.get("data", {})
                    if event_type == "on_tool_start":
                        tool_data = event.get("data", {})
                        tool_call_id = str(tool_data.get("tool_call_id", "unknown"))
                        
                        # Defensive tool name extraction to prevent validation errors
                        tool_name = _extract_tool_name(event.get("name"), tool_call_id)
                        event["name"] = tool_name
                            
                        now_iso = datetime.now(timezone.utc).isoformat()
                        tool_op = operations.get(tool_call_id)
                        if tool_op is None:
                            tool_op = {
                                "id": tool_call_id,
                                "type": "tool",
                                "name": tool_name,
                                "status": "running",
                                "parent": root_operation_id,
                                "children": [],
                                "startTime": now_iso,
                                "metadata": {"toolName": tool_name},
                            }
                            operations[tool_call_id] = tool_op
                        parent_op = operations.get(root_operation_id)
                        if parent_op is not None:
                            children = parent_op.setdefault("children", [])
                            if tool_call_id not in children:
                                children.append(tool_call_id)
                        _emit_timeline_update(tool_call_id)
                        writer({
                            "type": "TOOL_CALL_START",
                            "toolCallId": tool_call_id,
                            "toolCallName": tool_name,
                        })
                        tool_trace_meta: Dict[str, Any] = {
                            "toolCallId": tool_call_id,
                            "toolName": tool_name,
                        }
                        tool_input = tool_data.get("input") or tool_data.get("tool_input")
                        if tool_input is not None:
                            tool_trace_meta["input"] = _safe_json_value(tool_input)
                        _append_trace_step(
                            "action",
                            f"Executing {tool_name}",
                            metadata=tool_trace_meta,
                        )
                    elif event_type == "on_tool_end":
                        tool_data = event.get("data", {})
                        output = tool_data.get("output")
                        tool_call_id = str(tool_data.get("tool_call_id", "unknown"))
                        
                        # Defensive tool name extraction
                        tool_name = _extract_tool_name(event.get("name"), tool_call_id)
                        event["name"] = tool_name
                            
                        now_iso = datetime.now(timezone.utc).isoformat()
                        tool_op = operations.get(tool_call_id)
                        if tool_op is None:
                            tool_op = {
                                "id": tool_call_id,
                                "type": "tool",
                                "name": tool_name,
                                "status": "running",
                                "parent": root_operation_id,
                                "children": [],
                                "startTime": now_iso,
                            }
                            operations[tool_call_id] = tool_op
                        tool_op["status"] = "success"
                        tool_op["endTime"] = now_iso
                        start_iso = tool_op.get("startTime")
                        if isinstance(start_iso, str):
                            try:
                                start_dt = datetime.fromisoformat(start_iso)
                                end_dt = datetime.fromisoformat(now_iso)
                                tool_op["duration"] = int((end_dt - start_dt).total_seconds() * 1000)
                            except Exception:
                                pass
                        safe_output: Optional[Any] = None
                        if output is not None:
                            safe_output = _safe_json_value(output)
                            metadata = tool_op.setdefault("metadata", {})
                            if "rawOutputPreview" not in metadata:
                                metadata["rawOutputPreview"] = str(safe_output)[:1000]
                            # Rerank grounding results via Gemma to reduce tool churn.
                            if isinstance(tool_name, str) and tool_name == "grounding_search":
                                try:
                                    results = None
                                    if isinstance(output, dict):
                                        results = output.get("results") or output.get("items")
                                    if isinstance(results, list) and last_user_query:
                                        snippet_texts = []
                                        for item in results:
                                            if isinstance(item, dict):
                                                snippet_texts.append(str(item.get("snippet") or item.get("content") or item))
                                            else:
                                                snippet_texts.append(str(item))
                                        rerank_key = None
                                        if session_cache is not None:
                                            hasher = hashlib.md5()
                                            for s in snippet_texts:
                                                hasher.update(s.encode("utf-8", errors="ignore"))
                                            rerank_key = f"rerank:{last_user_query.lower().strip()}:{hasher.hexdigest()}"
                                        cached_rerank = session_cache.get(rerank_key, {}).get("value") if rerank_key and session_cache else None
                                        reranked = cached_rerank or await _with_timeout(
                                            helper.rerank(snippet_texts, last_user_query, top_k=min(3, len(snippet_texts))),
                                            HELPER_TIMEOUT_SECONDS,
                                            "gemma_rerank_grounding",
                                        )
                                        if reranked:
                                            if rerank_key and session_cache is not None:
                                                session_cache[rerank_key] = {"value": reranked, "ts": time.time()}
                                            # Preserve original items order based on reranked texts
                                            ordered = []
                                            seen = set()
                                            for text in reranked:
                                                for item, raw in zip(results, snippet_texts):
                                                    if raw == text and id(item) not in seen:
                                                        ordered.append(item)
                                                        seen.add(id(item))
                                                        break
                                            # fallback to original if mapping failed
                                            if ordered:
                                                if isinstance(output, dict):
                                                    output["results"] = ordered
                                                    safe_output = _safe_json_value(output)
                                                metadata["reranked"] = True
                                except Exception as exc:
                                    logger.warning("gemma_rerank_grounding_failed", error=str(exc))
                            if isinstance(tool_name, str) and tool_name == "write_todos":
                                normalized_todos = _normalize_todos(
                                    output.get("todos") if isinstance(output, dict) else output
                                )
                                if normalized_todos:
                                    todo_items.clear()
                                    todo_items.extend(normalized_todos)
                                    state.scratchpad["_todos"] = list(normalized_todos)
                                    try:
                                        state.todos = list(normalized_todos)  # type: ignore[attr-defined]
                                    except Exception as exc:
                                        logger.warning("state_todos_set_failed", error=str(exc))
                                    _sync_todo_operations()
                            _emit_custom_event(
                                "tool_evidence_update",
                                {
                                    "toolCallId": tool_call_id,
                                    "toolName": tool_name,
                                    "output": safe_output,
                                    "summary": _summarize_structured_content(safe_output),
                                },
                            )
                        _emit_timeline_update(tool_call_id)
                        writer({
                            "type": "TOOL_CALL_END",
                            "toolCallId": tool_call_id,
                            "toolCallName": tool_name,
                            "result": str(output) if output else None
                        })
                        result_metadata: Dict[str, Any] = {
                            "toolCallId": tool_call_id,
                            "toolName": tool_name,
                        }
                        if safe_output is not None:
                            result_metadata["output"] = safe_output
                        if tool_op.get("duration") is not None:
                            result_metadata["durationMs"] = tool_op["duration"]
                        _append_trace_step(
                            "result",
                            f"{tool_name} completed",
                            metadata=result_metadata,
                        )
                    elif event_type == "on_tool_error":
                        tool_data = event.get("data", {}) or {}
                        tool_call_id = str(tool_data.get("tool_call_id", "unknown"))
                        raw_error = tool_data.get("error") or tool_data.get("error_message") or event.get("error")
                        tool_name = event.get("name") or tool_call_id or "tool"
                        logger.error("Tool error", tool_name=tool_name, tool_call_id=tool_call_id, error=raw_error)
                        _append_trace_step(
                            "result",
                            f"{tool_name} failed",
                            metadata={"toolCallId": tool_call_id, "error": str(raw_error)},
                        )
                        tool_op = operations.get(tool_call_id)
                        if tool_op:
                            tool_op["status"] = "error"
                            tool_op["error"] = str(raw_error)
                            _emit_timeline_update(tool_call_id)
                        _emit_custom_event(
                            "tool_error",
                            {
                                "toolCallId": tool_call_id,
                                "toolName": tool_name,
                                "error": str(raw_error),
                            },
                        )
                    elif event_type == "on_chat_model_start":
                        # Capture "Thinking" phase
                        data = event.get("data", {})
                        # We use run_id as the operation ID for thoughts
                        run_id = event.get("run_id")
                        if run_id:
                            now_iso = datetime.now(timezone.utc).isoformat()
                            thought_op = {
                                "id": run_id,
                                "type": "thought",
                                "name": "Thinking",
                                "status": "running",
                                "parent": root_operation_id,
                                "children": [],
                                "startTime": now_iso,
                                "metadata": {
                                    "model": data.get("model")
                                }
                            }
                            operations[run_id] = thought_op
                            
                            # Add to parent children
                            parent_op = operations.get(root_operation_id)
                            if parent_op is not None:
                                children = parent_op.setdefault("children", [])
                                if run_id not in children:
                                    children.append(run_id)
                            
                            _emit_timeline_update(run_id)
                            prompt_messages = data.get("messages") or data.get("inputs") or []
                            prompt_preview = ""
                            if isinstance(prompt_messages, list):
                                preview_chunks = []
                                for message in prompt_messages[-2:]:
                                    if isinstance(message, dict):
                                        preview_chunks.append(_stringify_message_content(message.get("content")))
                                    else:
                                        preview_chunks.append(_stringify_message_content(message))
                                prompt_preview = " ".join(part for part in preview_chunks if part).strip()
                            thinking_metadata = {"model": data.get("model")}
                            if prompt_preview:
                                thinking_metadata["promptPreview"] = prompt_preview[:600]
                            _append_trace_step(
                                "thought",
                                "Model reasoning",
                                metadata=thinking_metadata,
                                alias=str(run_id),
                            )

                    elif event_type == "on_chat_model_end":
                        # Complete "Thinking" phase
                        run_id = event.get("run_id")
                        if run_id and run_id in operations:
                            thought_op = operations[run_id]
                            now_iso = datetime.now(timezone.utc).isoformat()
                            thought_op["status"] = "success"
                            thought_op["endTime"] = now_iso
                            
                            start_iso = thought_op.get("startTime")
                            if isinstance(start_iso, str):
                                try:
                                    start_dt = datetime.fromisoformat(start_iso)
                                    end_dt = datetime.fromisoformat(now_iso)
                                    thought_op["duration"] = int((end_dt - start_dt).total_seconds() * 1000)
                                except Exception:
                                    pass
                            
                            # Capture output content if available
                            data = event.get("data", {})
                            output = data.get("output")
                            if output:
                                # output is typically an AIMessage
                                content = getattr(output, "content", "")
                                if content:
                                    thought_op.setdefault("metadata", {})["content"] = str(content)
                            
                            _emit_timeline_update(run_id)
                        final_output = data.get("output")
                        normalized_output = _stringify_message_content(getattr(final_output, "content", final_output)) if final_output else ""
                        updated = None
                        if run_id is not None:
                            updated = _update_trace_step(
                                str(run_id),
                                metadata={"finalOutput": normalized_output} if normalized_output else None,
                                finalize=True,
                            )
                        if updated is None and normalized_output:
                            _append_trace_step(
                                "result",
                                normalized_output,
                                metadata={"source": "model"},
                            )
                    elif event_type in {"on_chat_model_stream", "on_llm_stream"}:
                        run_id = event.get("run_id")
                        if not run_id:
                            continue
                        stream_data = event.get("data", {})
                        chunk = stream_data.get("chunk") or stream_data.get("output")
                        chunk_text = _stringify_message_content(
                            getattr(chunk, "content", chunk)
                        )
                        if not chunk_text:
                            continue
                        updated = _update_trace_step(str(run_id), append_content=chunk_text)
                        if updated is None:
                            _append_trace_step(
                                "thought",
                                chunk_text,
                                alias=str(run_id),
                            )
                    elif event_type == "manually_emit_state":
                        # Handle GenUI state updates using CUSTOM event type
                        data = event.get("data", {})
                        if data:
                            writer({
                                "type": "CUSTOM",
                                "name": "genui_state_update",
                                "value": data
                            })
                    elif event_type in {"on_chain_end", "on_graph_end"}:
                        root_op = operations.get(root_operation_id)
                        if root_op is not None:
                            if "endTime" not in root_op:
                                end_iso = datetime.now(timezone.utc).isoformat()
                                root_op["endTime"] = end_iso
                                start_iso = root_op.get("startTime")
                                if isinstance(start_iso, str):
                                    try:
                                        start_dt = datetime.fromisoformat(start_iso)
                                        end_dt = datetime.fromisoformat(end_iso)
                                        root_op["duration"] = int((end_dt - start_dt).total_seconds() * 1000)
                                    except Exception:
                                        pass
                                root_op["status"] = "success"
                            _emit_timeline_update(root_operation_id)
                        output = data.get("output")
                        if output:
                            summarized = _stringify_message_content(output)
                            if summarized:
                                _append_trace_step(
                                    "result",
                                    summarized,
                                    metadata={"source": event_type},
                                )
                        if isinstance(output, dict):
                            final_output = output
            except Exception as e:
                logger.error(f"Error during agent streaming: {e}")
                # Try to get final output if streaming failed
                final_output = await agent.ainvoke(
                    _agent_inputs(),
                    config=run_config,
                )
        if final_output is None:
            final_output = await agent.ainvoke(
                _agent_inputs(),
                config=run_config,
            )

        # Normalize outputs into a messages list
        messages_payload = None
        if isinstance(final_output, BaseMessage):
            messages_payload = list(state.messages) + [final_output]
        elif isinstance(final_output, dict):
            output_field = final_output.get("output")
            messages_field = final_output.get("messages")
            if isinstance(messages_field, list) and messages_field:
                messages_payload = messages_field
            elif isinstance(output_field, BaseMessage):
                messages_payload = list(state.messages) + [output_field]
            elif isinstance(output_field, str) and output_field.strip():
                messages_payload = list(state.messages) + [AIMessage(content=output_field.strip())]

        if messages_payload is None:
            logger.error("Unified agent response missing messages; returning original state")
            completed_successfully = True
            return {"messages": state.messages}

        updated_messages = _strip_memory_messages(messages_payload)
        logger.info(
            "unified_agent_final_messages",
            count=len(updated_messages),
            last_role=getattr(updated_messages[-1], "role", None),
            last_preview=str(_coerce_message_text(updated_messages[-1]))[:200],
        )

        scratchpad = final_output.get("scratchpad") or state.scratchpad
        forwarded_props = final_output.get("forwarded_props") or state.forwarded_props

        # Reformat/append a human-readable log analysis response so the UI surfaces it.
        log_agent = (state.agent_type or state.forwarded_props.get("agent_type")) == "log_analysis"
        if log_agent:
            def _format_msg(msg: BaseMessage) -> Optional[str]:
                return _format_log_analysis_result(_coerce_message_text(msg))

            # Prefer the latest assistant message
            formatted: Optional[str] = None
            for idx in range(len(updated_messages) - 1, -1, -1):
                candidate = updated_messages[idx]
                if getattr(candidate, "role", None) == "assistant":
                    formatted = _format_msg(candidate)
                    if formatted:
                        updated_messages[idx] = AIMessage(content=formatted, additional_kwargs=getattr(candidate, "additional_kwargs", {}))
                    break

            # If no assistant message was present or formatting failed, fall back to the latest tool result.
            if formatted is None:
                for idx in range(len(updated_messages) - 1, -1, -1):
                    candidate = updated_messages[idx]
                    if getattr(candidate, "role", None) == "tool":
                        formatted = _format_msg(candidate)
                        if formatted:
                            updated_messages.append(AIMessage(content=formatted))
                        break

        last_ai_message = next((m for m in reversed(updated_messages) if isinstance(m, AIMessage)), None)
        if last_ai_message is not None:
            await _record_memory(state, last_ai_message)

        completed_successfully = True
        return {
            "messages": updated_messages,
            "scratchpad": scratchpad,
            "forwarded_props": forwarded_props,
            "attachments": [],
        }

    except RateLimitExceededException as e:
        logger.error("gemini_rate_limited", model=getattr(runtime, "model", "unknown"), error=str(e))
        rate_limit_msg = AIMessage(content=(
            "I'm temporarily paused because the Gemini API rate limit was hit. "
            "Please wait a few seconds and try again; I'll reuse cached prep and keep the same model when capacity is free."
        ))
        return {
            "messages": [*state.messages, rate_limit_msg],
            "scratchpad": state.scratchpad,
            "forwarded_props": state.forwarded_props,
            "attachments": getattr(state, "attachments", []),
        }
    except Exception as e:
        logger.error(f"Critical error in unified agent execution: {e}")
        # Return original state as fallback for graceful degradation
        return {
            "messages": state.messages,
            "scratchpad": state.scratchpad,
            "forwarded_props": state.forwarded_props,
            "error": str(e)
        }
    finally:
        if limiter and not completed_successfully:
            for model_name, token_identifier in reserved_slots:
                try:
                    await limiter.release_slot(model_name, token_identifier)
                except Exception as exc:  # pragma: no cover - best effort cleanup
                    logger.warning(
                        "rate_limit_slot_release_failed",
                        model=model_name,
                        error=str(exc),
                    )


def should_continue(state: GraphState) -> str:
    if not state.messages:
        return "end"
    last_message = state.messages[-1]
    if isinstance(last_message, AIMessage):
        tool_calls = getattr(last_message, "tool_calls", None)
        if tool_calls:
            return "continue"
    return "end"
