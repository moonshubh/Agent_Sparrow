"""Unified Agent Sparrow implementation built on LangGraph v1.

Refactored to use modular streaming, event emission, and message preparation.
"""

from __future__ import annotations

import asyncio
import json
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.config import RunnableConfig, get_stream_writer
from loguru import logger

# Import middleware classes from correct sources
try:
    from langchain.agents.middleware import TodoListMiddleware
    from langchain.agents.middleware.summarization import SummarizationMiddleware
    from deepagents.middleware.subagents import SubAgentMiddleware, TASK_SYSTEM_PROMPT
    from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
    from app.agents.harness.middleware import ToolResultEvictionMiddleware

    # Import new context management middleware
    from app.agents.unified.context_middleware import (
        FractionBasedSummarizationMiddleware,
        ContextEditingMiddleware,
        ModelRetryMiddleware,
        get_model_context_window,
    )

    MIDDLEWARE_AVAILABLE = True
    CONTEXT_MIDDLEWARE_AVAILABLE = True

    class SubAgentTodoListMiddleware(TodoListMiddleware):
        """Distinct marker to avoid duplicate detection."""
        pass

    class SubAgentSummarizationMiddleware(SummarizationMiddleware):
        """Subagent-specific summarization variant (legacy fallback)."""
        pass

except ImportError as e:
    logger.warning("Middleware not available ({}) - agent will run without middleware", e)
    MIDDLEWARE_AVAILABLE = False
    CONTEXT_MIDDLEWARE_AVAILABLE = False

from app.agents.orchestration.orchestration.state import GraphState
from app.agents.harness.observability import AgentLoopState
from app.agents.harness.middleware import get_state_tracking_middleware
from app.core.config import get_registry
from app.core.settings import settings
from app.memory import memory_service
from app.core.rate_limiting.agent_wrapper import get_rate_limiter
from app.core.rate_limiting.exceptions import (
    CircuitBreakerOpenException,
    GeminiQuotaExhaustedException,
    GeminiServiceUnavailableException,
    RateLimitExceededException,
)
from app.agents.unified.cache import configure_llm_cache
from app.agents.helpers.gemma_helper import GemmaHelper

# Import new streaming modules
from app.agents.streaming import StreamEventEmitter, StreamEventHandler
from app.agents.streaming.handler import ThinkingBlockTracker
from app.agents.unified.message_preparation import MessagePreparer
from app.agents.unified.session_cache import get_session_data

from .model_router import ModelSelectionResult, model_router
from .tools import get_registered_support_tools, get_registered_tools
from .attachment_processor import get_attachment_processor
from .subagents import get_subagent_specs, get_subagent_by_name
from .prompts import get_coordinator_prompt, TODO_PROMPT
from app.agents.skills import get_skills_registry

try:
    from google.api_core.exceptions import ResourceExhausted
except Exception:  # pragma: no cover - optional dependency
    ResourceExhausted = None

# Constants
MEMORY_AGENT_ID = "sparrow"
MEMORY_SYSTEM_NAME = "server_memory_context"
BASE_AGENT_PROMPT = (
    "In order to complete the objective that the user asks of you, you have access to a number "
    "of standard tools."
)
DEFAULT_RECURSION_LIMIT = 400
HELPER_TIMEOUT_SECONDS = 8.0

# Best-effort LLM cache to reduce repeat costs; safe to ignore failures.
configure_llm_cache()

# Provider-specific token limits for summarization middleware
# Set conservatively to prevent quota/context overflow
PROVIDER_TOKEN_LIMITS: Dict[str, int] = {
    "google": 50000,      # Gemini 3 Pro has 1M/min quota - keep very low
    "xai": 80000,         # Grok ~400K context → 80K summarization threshold
    "openrouter": 50000,  # OpenRouter 262K context → 50K summarization threshold
}
DEFAULT_TOKEN_LIMIT = 50000  # Conservative default for unknown providers


@dataclass(frozen=True)
class LogAnalysisNote:
    file_name: str = ""
    customer_ready: str = ""
    internal_notes: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


def _extract_log_analysis_notes(messages: list[BaseMessage]) -> dict[str, LogAnalysisNote]:
    """Extract log analysis notes emitted by the log-diagnoser Task subagent.

    Returns a mapping from tool_call_id -> LogAnalysisNote.
    """

    log_task_ids: set[str] = set()
    for msg in messages or []:
        if not isinstance(msg, AIMessage):
            continue
        tool_calls = getattr(msg, "tool_calls", None)
        if not isinstance(tool_calls, list):
            continue
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            if str(call.get("name") or "") != "task":
                continue
            args = call.get("args")
            if not isinstance(args, dict):
                continue
            if str(args.get("subagent_type") or "") != "log-diagnoser":
                continue
            call_id = str(call.get("id") or "").strip()
            if call_id:
                log_task_ids.add(call_id)

    if not log_task_ids:
        return {}

    notes: dict[str, LogAnalysisNote] = {}
    for msg in messages or []:
        if not isinstance(msg, ToolMessage):
            continue
        tool_call_id = str(getattr(msg, "tool_call_id", "") or "").strip()
        if not tool_call_id or tool_call_id not in log_task_ids:
            continue
        content = str(getattr(msg, "content", "") or "")
        try:
            payload = json.loads(content) if content else {}
        except Exception:
            payload = {}
        payload = payload if isinstance(payload, dict) else {}

        evidence = payload.get("evidence")
        recommended_actions = payload.get("recommended_actions")
        open_questions = payload.get("open_questions")

        notes[tool_call_id] = LogAnalysisNote(
            file_name=str(payload.get("file_name") or ""),
            customer_ready=str(payload.get("customer_ready") or ""),
            internal_notes=str(payload.get("internal_notes") or ""),
            confidence=float(payload.get("confidence") or 0.0),
            evidence=[str(x) for x in evidence] if isinstance(evidence, list) else [],
            recommended_actions=[str(x) for x in recommended_actions]
            if isinstance(recommended_actions, list)
            else [],
            open_questions=[str(x) for x in open_questions] if isinstance(open_questions, list) else [],
        )

    return notes


def _is_quota_exhausted(exc: Exception) -> bool:
    """Best-effort detection for Gemini quota exhaustion errors."""
    if ResourceExhausted is not None and isinstance(exc, ResourceExhausted):
        return True
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "resourceexhausted",
            "quota",
            "rate limit",
            "429",
        )
    )

# -----------------------------------------------------------------------------
# Fast Task Classification (keyword-based, <5ms vs ~200ms for attachment scan)
# -----------------------------------------------------------------------------
# Patterns are checked in order; first match wins
TASK_TYPE_PATTERNS: Dict[str, List[str]] = {
    "log_analysis": [
        # File extensions and explicit log mentions
        r"\.log\b", r"\.txt\b.*log", r"log\s*file",
        # Error/debug indicators
        r"\berror\b", r"\bexception\b", r"traceback", r"stack\s*trace",
        r"\bcrash", r"\bfail(?:ed|ure)?\b", r"\bdebug\b",
        # Email client specific (Mailbird context)
        r"\bimap\b", r"\bsmtp\b", r"\bpop3?\b", r"oauth.*fail",
        r"connection.*(?:timeout|refused|lost)", r"ssl.*(?:error|fail)",
        r"sync.*(?:error|fail)", r"authentication.*fail",
        # Log-like patterns
        r"\d{4}-\d{2}-\d{2}.*(?:error|warn|info)", r"\[error\]", r"\[warn",
    ],
    "coordinator_heavy": [
        # Explicit complexity requests
        r"detailed\s*analysis", r"step[\s-]*by[\s-]*step", r"comprehensive",
        r"thorough(?:ly)?", r"in[\s-]*depth", r"deep\s*dive",
        # Multi-part tasks
        r"compare.*and.*contrast", r"pros?\s*(?:and|&)\s*cons?",
        r"analyze.*multiple", r"evaluate.*options",
    ],
}

# Pre-compile patterns for performance
_COMPILED_TASK_PATTERNS: Dict[str, List[re.Pattern]] = {
    task: [re.compile(p, re.IGNORECASE) for p in patterns]
    for task, patterns in TASK_TYPE_PATTERNS.items()
}


def _fast_classify_task(message: str) -> Optional[str]:
    """Fast O(n) keyword classification - no LLM/attachment scan needed.

    Runs in <5ms for typical messages. Returns None if no pattern matches,
    allowing fallback to attachment-based detection.
    """
    if not message:
        return None

    for task_type, patterns in _COMPILED_TASK_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(message):
                logger.debug("fast_task_classification", task_type=task_type, pattern=pattern.pattern[:30])
                return task_type

    return None


def _extract_last_user_message(state: GraphState) -> str:
    """Extract the last user message text for classification."""
    messages = getattr(state, "messages", []) or []
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            content = getattr(msg, "content", "") or ""
            if isinstance(content, list):
                # Handle multimodal messages
                return " ".join(
                    part.get("text", "") for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            return content
    return ""


@dataclass
class AgentRuntimeConfig:
    """Resolved runtime configuration for a single run."""
    provider: str
    model: str
    task_type: str


# -----------------------------------------------------------------------------
# Configuration and Model Building
# -----------------------------------------------------------------------------

def _resolve_runtime_config(state: GraphState) -> AgentRuntimeConfig:
    """Resolve runtime configuration from state.

    IMPORTANT: This function should be called AFTER _ensure_model_selection()
    which performs the async health check and sets state.model. This function
    now uses the already-selected model rather than re-running model selection
    to avoid inconsistency between async health check and sync router.
    """
    provider = (state.provider or settings.primary_agent_provider or "google").lower()
    task_type = _determine_task_type(state)

    # Use the model already selected by _ensure_model_selection()
    # Only fall back to router selection if state.model is not set (defensive)
    if state.model:
        resolved_model = state.model
        logger.debug(
            "using_preselected_model",
            provider=provider,
            model=resolved_model,
            task_type=task_type,
        )
    else:
        # Fallback: model selection wasn't done yet (shouldn't happen in normal flow)
        logger.warning(
            "model_selection_fallback_needed",
            provider=provider,
            task_type=task_type,
        )
        if provider in {"xai", "openrouter"}:
            registry = get_registry()
            resolved_model = registry.get_model_for_role("coordinator", provider).id
        else:
            resolved_model = model_router.select_model(task_type, check_availability=False)
        state.model = resolved_model

    return AgentRuntimeConfig(provider=provider, model=resolved_model, task_type=task_type)


def _determine_task_type(state: GraphState) -> str:
    """Determine task type from state using fast keyword classification.

    Routing priority:
    1. Explicit coordinator_mode from forwarded_props (heavy/pro → coordinator_heavy)
    2. Fast keyword classification from message content (<5ms)
    3. Attachment-based log detection (only if keywords didn't match, ~200ms)
    4. Default to "coordinator" (light mode)
    """
    forwarded_props = getattr(state, "forwarded_props", {}) or {}
    coordinator_mode = forwarded_props.get("coordinator_mode") or getattr(state, "coordinator_mode", None)
    heavy_mode = isinstance(coordinator_mode, str) and coordinator_mode.lower() in {"heavy", "pro", "coordinator_heavy"}

    # 1. Priority #1: Explicit coordinator_mode takes precedence
    if heavy_mode:
        logger.info("task_type_explicit_mode", task_type="coordinator_heavy", trigger="coordinator_mode")
        forwarded_props["task_detection_method"] = "explicit_mode"
        state.forwarded_props = forwarded_props
        return "coordinator_heavy"

    # 2. Fast path: keyword classification from user message (~5ms)
    user_message = _extract_last_user_message(state)
    fast_task = _fast_classify_task(user_message)

    if fast_task == "log_analysis":
        logger.info("task_type_fast_path", task_type="log_analysis", trigger="keyword_match")
        forwarded_props["agent_type"] = "log_analysis"
        forwarded_props["task_detection_method"] = "keyword"
        state.forwarded_props = forwarded_props
        state.agent_type = "log_analysis"
        return "log_analysis"

    if fast_task == "coordinator_heavy":
        logger.info("task_type_fast_path", task_type="coordinator_heavy", trigger="keyword_match")
        return "coordinator_heavy"

    # 3. Slow path: attachment-based detection (only if no keyword match, ~200ms)
    # Skip if no attachments to avoid unnecessary processing
    attachments = getattr(state, "attachments", []) or []
    if attachments:
        detection = _attachments_indicate_logs(state)
        if detection.get("has_log"):
            logger.info("task_type_slow_path", task_type="log_analysis", trigger="attachment_scan")
            forwarded_props["agent_type"] = "log_analysis"
            forwarded_props["log_detection"] = detection
            forwarded_props["task_detection_method"] = "attachment"
            state.forwarded_props = forwarded_props
            state.agent_type = "log_analysis"
            return "log_analysis"

    # 4. Default: light coordinator
    return "coordinator"


def _attachments_indicate_logs(state: GraphState) -> Dict[str, Any]:
    """Centralized log attachment detection."""
    try:
        processor = get_attachment_processor()
        return processor.detect_log_attachments(getattr(state, "attachments", []) or [])
    except Exception as exc:
        logger.warning("log_attachment_detection_failed", error=str(exc))
        return {"has_log": False, "candidates": [], "non_text_skipped": []}


def _get_session_cache(session_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Get session cache data using thread-safe cache.

    This function provides backwards compatibility with the old global dict
    pattern while using the new thread-safe SessionCache underneath.
    """
    return get_session_data(session_id)


async def _ensure_model_selection(state: GraphState) -> ModelSelectionResult:
    """Ensure model is selected with health check.

    For non-Google providers (e.g., XAI/Grok), the user's model selection is
    preserved without going through the Gemini-specific model router.
    """
    task_type = _determine_task_type(state)
    provider = (state.provider or settings.primary_agent_provider or "google").lower()

    # For non-Google providers, preserve the user's model selection
    if provider != "google":
        if not state.model:
            registry = get_registry()
            state.model = registry.get_model_for_role("coordinator", provider).id
        logger.info(
            "preserving_non_google_model_selection",
            provider=provider,
            model=state.model,
            task_type=task_type,
        )
        # Create a minimal selection result for non-Gemini models
        from .model_health import ModelHealth
        health = ModelHealth(
            model=state.model,
            available=True,
            rpm_used=0,
            rpm_limit=0,
            rpd_used=0,
            rpd_limit=0,
            circuit_state="ok",
            reason=None,
        )
        return ModelSelectionResult(
            task_type=task_type,
            model=state.model,
            health_trace=[health],
            fallback_occurred=False,
            fallback_chain=[state.model],
        )

    selection = await model_router.select_model_with_health(task_type, user_override=state.model)
    state.model = selection.model

    # Store selection metadata for LangSmith
    if isinstance(state.scratchpad, dict):
        system_bucket = state.scratchpad.setdefault("_system", {})
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
    """Build the chat model for the agent using the provider factory.

    Uses role-based temperature selection from provider_factory.TEMPERATURE_CONFIG:
    - coordinator: 0.2 (deterministic reasoning)
    - coordinator_heavy: 0.2 (complex reasoning)
    - log_analysis: 0.1 (high precision for error diagnosis)

    Supports multiple providers (Google Gemini, XAI/Grok) with automatic
    fallback to Gemini if the requested provider is unavailable.
    """
    from .provider_factory import build_chat_model

    return build_chat_model(
        provider=runtime.provider,
        model=runtime.model,
        role=runtime.task_type,  # Role-based temperature selection
    )


def _build_task_system_prompt(state: GraphState) -> Optional[str]:
    """Augment the SubAgent task system prompt when logs are detected."""
    base = TASK_SYSTEM_PROMPT if "TASK_SYSTEM_PROMPT" in globals() else None
    if not base:
        return None

    forwarded_props = getattr(state, "forwarded_props", {}) or {}
    if forwarded_props.get("agent_type") == "log_analysis":
        rule = (
            "Auto-routing rule: The user provided log file attachments. "
            "Immediately use the `task` tool with subagent_type=\"log-diagnoser\". "
            "Pass a clear objective plus the inlined Attachments context, then synthesize a concise user-facing summary when the subagent returns."
        )
        return f"{base}\n\n{rule}"

    return base


def _build_skills_context(state: GraphState, runtime: AgentRuntimeConfig) -> str:
    """Build skills context with auto-detection from message content.

    This function:
    1. Always injects writing/empathy skills for user-facing responses
    2. Auto-detects additional skills based on message keywords (e.g., "pdf", "excel")
    3. Limits total skills to prevent prompt bloat

    Skills auto-detection triggers on keywords like:
    - Document types: pdf, docx, xlsx, pptx, csv
    - Actions: brainstorm, root cause, enhance image, create poster
    - Tasks: research company, write article, analyze data

    Maximum 3 additional skills are injected beyond writing/empathy.
    """
    try:
        skills_registry = get_skills_registry()

        # Build context for auto-detection
        forwarded_props = getattr(state, "forwarded_props", {}) or {}
        scratchpad = getattr(state, "scratchpad", {}) or {}
        system_bucket = scratchpad.get("_system", {}) if isinstance(scratchpad, dict) else {}

        # Extract last user message for skill detection
        user_message = ""
        messages = getattr(state, "messages", []) or []
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                user_message = getattr(msg, "content", "") or ""
                if isinstance(user_message, list):
                    # Handle multimodal messages
                    user_message = " ".join(
                        part.get("text", "") for part in user_message
                        if isinstance(part, dict) and part.get("type") == "text"
                    )
                break

        skill_context = {
            "message": user_message,  # For auto-detection
            "is_final_response": True,  # Default to user-facing for coordinator
            "task_type": system_bucket.get("task_type") or forwarded_props.get("task_type"),
            "is_internal_call": forwarded_props.get("is_internal_call", False),
        }

        # Use enhanced auto-detection
        skills_content = skills_registry.get_context_skills_content(skill_context)

        if skills_content:
            logger.debug(
                "skills_context_activated",
                message_preview=user_message[:100] if user_message else "",
            )

        return skills_content

    except Exception as e:
        logger.warning("skills_context_build_failed", error=str(e))

    return ""


def _build_deep_agent(state: GraphState, runtime: AgentRuntimeConfig):
    """Build the deep agent with middleware stack."""
    chat_model = _build_chat_model(runtime)
    # Zendesk tickets use a curated toolset (safer, support-focused) to reduce leakage risk
    # and keep replies aligned with internal support playbooks/macros.
    is_zendesk = (state.forwarded_props or {}).get("is_zendesk_ticket") is True
    tools = get_registered_support_tools() if is_zendesk else get_registered_tools()
    logger.debug("tool_registry_selected", mode="support" if is_zendesk else "standard")
    subagents = get_subagent_specs(provider=runtime.provider)

    todo_prompt = TODO_PROMPT if "TODO_PROMPT" in globals() else ""
    # Build coordinator prompt with dynamic model identification
    coordinator_prompt = get_coordinator_prompt(
        model=runtime.model,
        provider=state.provider,
    )

    # Build skills context for auto-detected writing/empathy skills
    skills_context = _build_skills_context(state, runtime)

    system_prompt_parts = [coordinator_prompt, skills_context, todo_prompt, BASE_AGENT_PROMPT]
    system_prompt = "\n\n".join(part for part in system_prompt_parts if part)

    middleware_stack = []
    if MIDDLEWARE_AVAILABLE:
        # Get model context window for fraction-based summarization
        # Pass provider for better fallback on unknown models (xAI, OpenRouter, etc.)
        model_context_window = (
            get_model_context_window(runtime.model, runtime.provider)
            if CONTEXT_MIDDLEWARE_AVAILABLE
            else 128000
        )

        # Build default middleware for subagents.
        # NOTE: Do NOT include TodoListMiddleware here — DeepAgents subagent graphs
        # can emit multiple `todos` updates in a single step, which triggers
        # langgraph.errors.InvalidUpdateError (LastValue channel).
        # Order matters: retry → summarization → context editing → eviction → patch
        default_middleware: list[Any] = []

        # Add model retry middleware for context overflow resilience
        if CONTEXT_MIDDLEWARE_AVAILABLE:
            default_middleware.append(
                ModelRetryMiddleware(
                    max_retries=2,
                    on_failure="continue",  # Return graceful error, don't crash
                    base_delay=1.0,
                )
            )

        # Add fraction-based summarization (triggers at 70% of context window)
        if CONTEXT_MIDDLEWARE_AVAILABLE:
            default_middleware.append(
                FractionBasedSummarizationMiddleware(
                    model=chat_model,
                    trigger_fraction=0.7,  # 70% of context window
                    messages_to_keep=6,
                    model_name=runtime.model,
                )
            )
        else:
            # Fallback to legacy fixed-threshold summarization
            provider_lower = (runtime.provider or "google").lower()
            token_limit = PROVIDER_TOKEN_LIMITS.get(provider_lower, DEFAULT_TOKEN_LIMIT)
            default_middleware.append(
                SubAgentSummarizationMiddleware(
                    model=chat_model,
                    max_tokens_before_summary=token_limit,
                    messages_to_keep=6,
                )
            )

        # Add context editing middleware to clear old tool results
        if CONTEXT_MIDDLEWARE_AVAILABLE:
            # Calculate trigger threshold: 60% of context window (before summarization kicks in)
            context_edit_threshold = int(model_context_window * 0.6)
            default_middleware.append(
                ContextEditingMiddleware(
                    trigger_tokens=context_edit_threshold,
                    keep_recent=3,  # Keep 3 most recent tool results
                    exclude_tools=["search_knowledge_base", "search_feedme_documents"],
                    placeholder="[Result cleared to save context - use tool again if needed]",
                )
            )

        # Evict large tool results (images, search results) before they go into
        # LangGraph state. This prevents context overflow - image base64 is 1-3MB.
        # The handler's _compact_image_output only modifies local variables,
        # not the actual state, so this middleware is REQUIRED.
        default_middleware.append(ToolResultEvictionMiddleware(char_threshold=50000))

        # Tool call normalization (must be last)
        default_middleware.append(PatchToolCallsMiddleware())

        logger.info(
            "context_middleware_configured",
            model=runtime.model,
            context_window=model_context_window,
            summarization_trigger=f"{0.7 * 100:.0f}% ({int(model_context_window * 0.7):,} tokens)",
            context_edit_trigger=f"{0.6 * 100:.0f}% ({int(model_context_window * 0.6):,} tokens)" if CONTEXT_MIDDLEWARE_AVAILABLE else "disabled",
            middleware_count=len(default_middleware),
        )

        coordinator_middleware = SubAgentMiddleware(
            default_model=chat_model,
            default_tools=tools,
            subagents=subagents,
            default_middleware=default_middleware,
            system_prompt=_build_task_system_prompt(state),
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
    """Build the runnable config for agent invocation."""
    base_config: Dict[str, Any] = dict(config or {})
    recursion_limit = base_config.get("recursion_limit")
    try:
        resolved_limit = int(recursion_limit) if recursion_limit is not None else DEFAULT_RECURSION_LIMIT
    except (ValueError, TypeError):
        resolved_limit = DEFAULT_RECURSION_LIMIT
    # Prevent upstream configs (e.g., adapters) from lowering recursion_limit too far.
    if resolved_limit < DEFAULT_RECURSION_LIMIT:
        resolved_limit = DEFAULT_RECURSION_LIMIT
    base_config["recursion_limit"] = resolved_limit

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


async def _maybe_autoroute_log_analysis(state: GraphState, helper: GemmaHelper) -> Optional[SystemMessage]:
    """Proactively run the log-diagnoser subagent when log attachments are present."""
    detection = _attachments_indicate_logs(state)
    forwarded_props = getattr(state, "forwarded_props", {}) or {}
    if detection.get("has_log"):
        forwarded_props["agent_type"] = "log_analysis"
        forwarded_props["log_detection"] = detection
        state.forwarded_props = forwarded_props
        state.agent_type = "log_analysis"
    else:
        return None

    provider = (state.provider or settings.primary_agent_provider or "google").lower()
    spec = get_subagent_by_name("log-diagnoser", provider=provider)
    if not spec:
        return None

    processor = get_attachment_processor()
    inline = None
    try:
        inline = await processor.inline_attachments(
            getattr(state, "attachments", []) or [],
            summarizer=helper.summarize if helper else None,
        )
    except Exception as exc:
        logger.warning("log_autoroute_inline_failed", error=str(exc))

    if not inline:
        return None

    subagent = create_agent(
        spec.get("model"),
        system_prompt=spec.get("system_prompt"),
        tools=spec.get("tools"),
        middleware=spec.get("middleware"),
    )

    task = (
        "Analyze the attached logs, identify root causes, timeline, and user impact. "
        "Return JSON with keys: overall_summary, health_status, priority_concerns, "
        "identified_issues[{title, severity, details}], proposed_solutions[{title, steps[]}], confidence_level.\n\n"
        f"{inline}"
    )

    try:
        sub_result = await subagent.ainvoke({"messages": [HumanMessage(content=task)]})
    except Exception as exc:
        logger.warning("log_autoroute_failed", error=str(exc))
        return None

    text: Optional[str] = None
    if isinstance(sub_result, dict):
        output_field = sub_result.get("output")
        messages_field = sub_result.get("messages")
        if isinstance(output_field, BaseMessage):
            text = _coerce_message_text(output_field)
        elif isinstance(output_field, str):
            text = output_field
        elif isinstance(messages_field, list) and messages_field:
            last_msg = messages_field[-1]
            if isinstance(last_msg, BaseMessage):
                text = _coerce_message_text(last_msg)
            else:
                text = str(last_msg)
    elif isinstance(sub_result, BaseMessage):
        text = _coerce_message_text(sub_result)

    if not text:
        return None

    forwarded_props["autorouted"] = True
    forwarded_props["agent_type"] = "log_analysis"
    forwarded_props["log_detection"] = detection
    state.forwarded_props = forwarded_props
    state.agent_type = "log_analysis"

    return SystemMessage(
        content=(
            "Log-diagnoser subagent report (use this for the final reply; do not re-analyze raw logs):\n"
            f"{text}"
        )
    )


# -----------------------------------------------------------------------------
# Memory Functions
# -----------------------------------------------------------------------------

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
    """Convert message content to plain text."""
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


def _coerce_visible_assistant_text(content: Any) -> str:
    """Extract user-visible assistant text from LangChain content blocks.

    Gemini 3 (and some OpenAI-compatible providers) may return structured content
    blocks containing thinking/reasoning/signatures. These must never leak into
    user-facing outputs (including Zendesk replies).
    """
    if content is None:
        return ""

    if isinstance(content, str):
        return ThinkingBlockTracker.sanitize_final_content(content).strip()

    if isinstance(content, dict):
        raw_type = content.get("type", "")
        block_type = raw_type.lower() if isinstance(raw_type, str) else ""
        if block_type in ("thinking", "reasoning", "thought", "signature", "thought_signature"):
            return ""
        if block_type in ("tool", "tool_use", "tool_call", "tool_calls", "function_call", "function"):
            return ""
        text = content.get("text")
        if isinstance(text, str) and text.strip():
            return ThinkingBlockTracker.sanitize_final_content(text).strip()
        raw_content = content.get("content")
        if isinstance(raw_content, str) and raw_content.strip():
            return ThinkingBlockTracker.sanitize_final_content(raw_content).strip()
        return ""

    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if part is None:
                continue
            if isinstance(part, str):
                parts.append(part)
                continue
            if isinstance(part, dict):
                raw_type = part.get("type", "")
                block_type = raw_type.lower() if isinstance(raw_type, str) else ""
                if block_type in ("thinking", "reasoning", "thought", "signature", "thought_signature"):
                    continue
                if block_type in ("tool", "tool_use", "tool_call", "tool_calls", "function_call", "function"):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
                    continue
                raw_part_content = part.get("content")
                if isinstance(raw_part_content, str) and raw_part_content.strip():
                    parts.append(raw_part_content)
                    continue
        joined = "".join(parts)
        return ThinkingBlockTracker.sanitize_final_content(joined).strip()

    return ThinkingBlockTracker.sanitize_final_content(str(content)).strip()


def _sanitize_user_facing_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Ensure assistant messages are safe, plain-text, and free of thinking."""
    sanitized: list[BaseMessage] = []
    for message in messages:
        if isinstance(message, AIMessage):
            sanitized.append(
                message.model_copy(
                    update={"content": _coerce_visible_assistant_text(message.content)}
                )
            )
        else:
            sanitized.append(message)
    return sanitized


def _extract_last_user_query(messages: List[BaseMessage]) -> str:
    """Extract the last human message text."""
    for message in reversed(messages or []):
        if getattr(message, "type", None) == "human":
            text = _coerce_message_text(message).strip()
            if text:
                return text
    return ""


def _build_memory_system_message(memories: List[Dict[str, Any]]) -> Optional[SystemMessage]:
    """Build a system message from retrieved memories."""
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


async def _retrieve_memory_context(state: GraphState) -> Optional[str]:
    """Retrieve memory context for the conversation.

    Also tracks memory IDs for feedback attribution - when users provide
    feedback on a response, it can be propagated to the memories used.
    """
    mem0_enabled = _memory_is_enabled(state)
    memory_ui_enabled = bool(getattr(settings, "enable_memory_ui_retrieval", False)) and bool(
        getattr(state, "use_server_memory", False)
    )
    if not mem0_enabled and not memory_ui_enabled:
        return None

    query = _extract_last_user_query(state.messages)
    if not query:
        return None

    # Initialize memory stats for LangSmith observability
    memory_stats = {
        "retrieval_attempted": True,
        "query_length": len(query),
        "facts_retrieved": 0,
        "relevance_scores": [],
        "retrieval_error": None,
        # Track Memory UI IDs for feedback attribution.
        # (Never include mem0 IDs here; feedback RPCs expect Memory UI UUIDs.)
        "retrieved_memory_ids": [],
        "retrieved_memory_ui_ids": [],
        "retrieved_mem0_ids": [],
        "memory_ui_retrieval_enabled": memory_ui_enabled,
        "mem0_retrieval_enabled": mem0_enabled,
    }

    def _as_float(value: Any, default: float = 0.0) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value))
        except Exception:
            return default

    # Collect results separately so we can normalize, dedupe, and rank consistently.
    # Policy: Memory UI is the primary source of truth; mem0 is only used as a backup
    # when Memory UI yields no hits (or is disabled/unavailable).

    ui_raw: list[dict[str, Any]] = []
    if memory_ui_enabled:
        try:
            from app.memory.memory_ui_service import get_memory_ui_service

            service = get_memory_ui_service()
            ui_raw = await service.search_memories(
                query=query,
                agent_id=getattr(settings, "memory_ui_agent_id", MEMORY_AGENT_ID)
                or MEMORY_AGENT_ID,
                tenant_id=getattr(settings, "memory_ui_tenant_id", "mailbot")
                or "mailbot",
                limit=settings.memory_top_k,
                similarity_threshold=0.5,
            )
        except Exception as exc:
            logger.warning("memory_ui_retrieve_failed", error=str(exc))

    mem0_raw: List[Dict[str, Any]] = []
    mem0_should_query = mem0_enabled and (not memory_ui_enabled or not ui_raw)
    if mem0_should_query:
        try:
            mem0_raw = await memory_service.retrieve(
                agent_id=MEMORY_AGENT_ID,
                query=query,
                top_k=settings.memory_top_k,
            )
        except Exception as exc:
            logger.warning("memory_retrieve_failed", error=str(exc))
            memory_stats["retrieval_error"] = str(exc)

    normalized: list[dict[str, Any]] = []
    # Prefer Memory UI memories when conflicts occur (source of truth).
    for item in ui_raw or []:
        if not isinstance(item, dict):
            continue
        memory_id = item.get("id")
        if not isinstance(memory_id, str) or not memory_id:
            continue
        text = str(item.get("content") or "").strip()
        if not text:
            continue
        normalized.append(
            {
                "canonical_id": f"memory_ui:{memory_id}",
                "id": memory_id,
                "memory": text,
                "score": _as_float(item.get("similarity"), 0.0),
                "confidence_score": _as_float(item.get("confidence_score"), 0.5),
                "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                "source": "memory_ui",
            }
        )

    for item in mem0_raw or []:
        if not isinstance(item, dict):
            continue
        mem0_id = item.get("id")
        text = str(item.get("memory") or "").strip()
        if not text:
            continue
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        memory_ui_id = meta.get("memory_ui_id")
        canonical_id: str
        if isinstance(memory_ui_id, str) and memory_ui_id:
            canonical_id = f"memory_ui:{memory_ui_id}"
        elif isinstance(mem0_id, str) and mem0_id:
            canonical_id = f"mem0:{mem0_id}"
        else:
            import hashlib

            canonical_id = f"mem0:sha1:{hashlib.sha1(text.encode('utf-8')).hexdigest()}"

        normalized.append(
            {
                "canonical_id": canonical_id,
                "id": str(mem0_id) if mem0_id is not None else None,
                "memory": text,
                "score": _as_float(item.get("score"), 0.0),
                "confidence_score": _as_float(meta.get("confidence_score"), 0.5),
                "metadata": meta,
                "source": "mem0",
            }
        )

    if not normalized:
        _update_memory_stats(state, memory_stats)
        return None

    # Dedupe + prefer Memory UI.
    by_canonical: dict[str, dict[str, Any]] = {}
    for hit in normalized:
        canonical = str(hit.get("canonical_id") or "").strip()
        if not canonical:
            continue
        existing = by_canonical.get(canonical)
        if not existing:
            by_canonical[canonical] = hit
            continue
        existing_source = str(existing.get("source") or "")
        hit_source = str(hit.get("source") or "")
        if existing_source != "memory_ui" and hit_source == "memory_ui":
            by_canonical[canonical] = hit
            continue
        if hit_source == existing_source and _as_float(hit.get("score"), 0.0) > _as_float(
            existing.get("score"), 0.0
        ):
            by_canonical[canonical] = hit

    def _rank(hit: dict[str, Any]) -> float:
        # Confidence dominates similarity (user preference), with a small bias for Memory UI.
        conf = _as_float(hit.get("confidence_score"), 0.5)
        sim = _as_float(hit.get("score"), 0.0)
        source_boost = 0.1 if str(hit.get("source")) == "memory_ui" else 0.0
        return (conf * 10.0) + sim + source_boost

    ranked = sorted(by_canonical.values(), key=_rank, reverse=True)

    # Enforce a deterministic token/char budget for memory injection.
    budget = int(getattr(settings, "memory_char_budget", 2000) or 2000)
    header = "Server memory retrieved for this session/user. Use only if relevant:\n"
    used_chars = len(header)
    selected: list[dict[str, Any]] = []
    for hit in ranked:
        raw_text = str(hit.get("memory") or "").strip()
        if not raw_text:
            continue
        compact = re.sub(r"\s+", " ", raw_text).strip()
        preview = textwrap.shorten(compact, width=320, placeholder="…")
        conf = _as_float(hit.get("confidence_score"), 0.5)
        sim = _as_float(hit.get("score"), 0.0)
        src = str(hit.get("source") or "")
        prefix = f"[{src} conf={conf:.2f} sim={sim:.2f}] "
        line = f"- {prefix}{preview}"
        projected = used_chars + len(line) + 1
        if projected > budget:
            continue
        selected.append(hit)
        used_chars = projected
        if len(selected) >= int(getattr(settings, "memory_top_k", 5) or 5):
            break

    if not selected:
        _update_memory_stats(state, memory_stats)
        return None

    # Track Memory UI IDs used (for feedback attribution and retrieval_count updates).
    memory_ui_ids_used: list[str] = []
    mem0_ids_used: list[str] = []
    for hit in selected:
        src = str(hit.get("source") or "")
        if src == "memory_ui":
            mid = hit.get("id")
            if isinstance(mid, str) and mid:
                memory_ui_ids_used.append(mid)
        else:
            mid = hit.get("id")
            if isinstance(mid, str) and mid:
                mem0_ids_used.append(mid)
            meta = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
            ui_id = meta.get("memory_ui_id")
            if isinstance(ui_id, str) and ui_id:
                memory_ui_ids_used.append(ui_id)

    unique_memory_ui_ids = list(dict.fromkeys(memory_ui_ids_used))
    unique_mem0_ids = list(dict.fromkeys(mem0_ids_used))

    memory_stats["facts_retrieved"] = len(selected)
    memory_stats["relevance_scores"] = [_as_float(h.get("score"), 0.0) for h in selected]
    memory_stats["retrieved_memory_ui_ids"] = unique_memory_ui_ids
    memory_stats["retrieved_mem0_ids"] = unique_mem0_ids
    # Back-compat: keep this field Memory-UI-only to avoid invalid UUIDs downstream.
    memory_stats["retrieved_memory_ids"] = unique_memory_ui_ids

    lines: list[str] = []
    for hit in selected:
        raw_text = str(hit.get("memory") or "").strip()
        if not raw_text:
            continue
        compact = re.sub(r"\s+", " ", raw_text).strip()
        preview = textwrap.shorten(compact, width=320, placeholder="…")
        conf = _as_float(hit.get("confidence_score"), 0.5)
        sim = _as_float(hit.get("score"), 0.0)
        src = str(hit.get("source") or "")
        lines.append(f"- [{src} conf={conf:.2f} sim={sim:.2f}] {preview}")

    if not lines:
        _update_memory_stats(state, memory_stats)
        return None

    memory_message = SystemMessage(
        content=header + "\n".join(lines),
        name=MEMORY_SYSTEM_NAME,
    )

    # Store memory stats in scratchpad for LangSmith
    _update_memory_stats(state, memory_stats)

    # Best-effort: increment retrieval_count for Memory UI memories actually retrieved by the agent.
    if unique_memory_ui_ids:
        try:
            from app.memory.memory_ui_service import get_memory_ui_service

            service = get_memory_ui_service()
            unique_ids = unique_memory_ui_ids

            async def _record_retrievals(ids: list[str]) -> None:
                supabase = service._get_supabase()
                for mid in ids:
                    try:
                        await supabase._exec(
                            lambda: supabase.client.rpc(
                                "record_memory_retrieval",
                                {"p_memory_id": mid},
                            ).execute()
                        )
                    except Exception as exc:
                        logger.debug("memory_ui_record_retrieval_failed", memory_id=mid, error=str(exc))

            asyncio.create_task(_record_retrievals(unique_ids))
        except Exception as exc:
            logger.debug("memory_ui_record_retrieval_schedule_failed", error=str(exc))

    return memory_message.content


def _update_memory_stats(state: GraphState, stats: Dict[str, Any]) -> None:
    """Update memory stats in scratchpad for LangSmith observability."""
    if isinstance(state.scratchpad, dict):
        system_bucket = state.scratchpad.setdefault("_system", {})
        memory_section = system_bucket.setdefault("memory_stats", {})
        memory_section.update(stats)
        state.scratchpad["_system"] = system_bucket


def _strip_memory_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """Remove memory system messages from message list."""
    if not messages:
        return messages
    return [
        message
        for message in messages
        if not (isinstance(message, SystemMessage) and message.name == MEMORY_SYSTEM_NAME)
    ]


_BULLET_PREFIX = re.compile(r"^[-*•]\s+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _summarize_response_to_facts(text: str, max_facts: int = 3, max_chars: int = 280) -> List[str]:
    """Extract key facts from a response for memory storage."""
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
    """Split text into sentences."""
    parts = _SENTENCE_BOUNDARY.split(text)
    sentences: List[str] = []
    for part in parts:
        stripped = part.strip()
        if len(stripped) < 20:
            continue
        sentences.append(stripped)
    return sentences


async def _record_memory(state: GraphState, ai_message: BaseMessage) -> None:
    """Record memory from AI response."""
    mem0_enabled = _memory_is_enabled(state)
    memory_ui_enabled = bool(getattr(settings, "enable_memory_ui_capture", False)) and bool(
        getattr(state, "use_server_memory", False)
    )
    if not mem0_enabled and not memory_ui_enabled:
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
    if state.trace_id:
        meta["trace_id"] = state.trace_id
    if state.agent_type:
        meta["agent_type"] = state.agent_type
    meta["fact_strategy"] = "sentence_extract"
    meta["review_status"] = "pending_review"

    # Policy: only approved memories are ever written to mem0.
    review_status = str(meta.get("review_status") or "").strip().lower()
    mem0_write_enabled = mem0_enabled and review_status == "approved"

    if mem0_write_enabled:
        try:
            result = await memory_service.add_facts(
                agent_id=MEMORY_AGENT_ID,
                facts=facts,
                meta=meta,
            )
            write_stats["write_successful"] = bool(result)
            write_stats["facts_written"] = len(facts)
        except Exception as exc:
            logger.warning("memory_add_failed", error=str(exc))
            write_stats["write_error"] = str(exc)
            write_stats["write_successful"] = False

    # Best-effort capture into the Memory UI schema (separate from mem0).
    if memory_ui_enabled:
        try:
            from app.memory.memory_ui_service import get_memory_ui_service

            service = get_memory_ui_service()
            agent_id = getattr(settings, "memory_ui_agent_id", MEMORY_AGENT_ID) or MEMORY_AGENT_ID
            tenant_id = getattr(settings, "memory_ui_tenant_id", "mailbot") or "mailbot"

            async def _capture_one(fact: str) -> None:
                try:
                    await service.add_memory(
                        content=fact,
                        metadata=meta,
                        source_type="auto_extracted",
                        agent_id=agent_id,
                        tenant_id=tenant_id,
                        review_status="pending_review",
                    )
                except Exception as exc:
                    logger.debug("memory_ui_capture_failed", error=str(exc)[:180])

            for fact in facts:
                asyncio.create_task(_capture_one(fact))
        except Exception as exc:
            logger.debug("memory_ui_capture_unavailable", error=str(exc)[:180])

    _update_memory_stats(state, write_stats)


# -----------------------------------------------------------------------------
# Output Formatting
# -----------------------------------------------------------------------------

def _format_log_analysis_result(raw: Any) -> Optional[str]:
    """Render log analysis output into a readable summary."""
    import json

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


# -----------------------------------------------------------------------------
# Main Agent Runner
# -----------------------------------------------------------------------------

async def run_unified_agent(state: GraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Run the unified agent with comprehensive error handling.

    This function orchestrates:
    1. Model selection and rate limit handling
    2. Memory retrieval
    3. Message preparation (rewriting, summarization, attachments)
    4. Agent streaming with AG-UI event emission
    5. Memory recording from response

    State transitions are tracked via LoopStateTracker for observability.

    Returns:
        Updated state dict with messages, scratchpad, and forwarded_props.
    """
    reserved_slots: List[tuple[str, Optional[str]]] = []
    limiter = None

    # Initialize state tracker for observability via middleware
    session_id = getattr(state, "session_id", None) or getattr(state, "trace_id", None) or "unknown"
    state_middleware = get_state_tracking_middleware()
    tracker = state_middleware.get_tracker(session_id)
    tracker.transition_to(AgentLoopState.PROCESSING_INPUT, metadata={"session_id": session_id})

    try:
        # 1. Model selection with health check
        await _ensure_model_selection(state)
        runtime = _resolve_runtime_config(state)
        limiter = get_rate_limiter()

        # 2. Initialize helpers
        helper = GemmaHelper(max_calls=10)
        session_id = getattr(state, "session_id", None) or getattr(state, "trace_id", None)
        session_cache = _get_session_cache(session_id)

        # 3. Rate limit preflight check with fallback (Gemini only)
        # Non-Gemini providers (XAI/Grok) bypass the Gemini rate limiter via explicit check below
        async def _reserve_model_slot(model_name: str) -> bool:
            """Reserve a rate limit slot for Gemini models.

            Note: This function should only be called for Google provider models.
            Non-Google providers are handled by the explicit provider check below.
            """
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
            # Note: ValueError is not caught here to avoid swallowing unrelated errors.
            # Non-Gemini providers are handled by the explicit provider check below.

        # Skip rate limiting for non-Gemini providers
        if runtime.provider != "google":
            logger.info(
                "skipping_gemini_rate_limit_for_provider",
                provider=runtime.provider,
                model=runtime.model,
            )
            slot_ok = True
        else:
            slot_ok = await _reserve_model_slot(runtime.model)
            if not slot_ok:
                fallback_model = model_router.fallback_chain.get(runtime.model) or "gemini-2.5-flash-lite"
                if fallback_model != runtime.model and await _reserve_model_slot(fallback_model):
                    logger.info("retrying_with_fallback_model", primary=runtime.model, fallback=fallback_model)
                    runtime = AgentRuntimeConfig(provider=runtime.provider, model=fallback_model, task_type=runtime.task_type)
                    state.model = fallback_model
                else:
                    raise GeminiQuotaExhaustedException(runtime.model)

        # 4. Build agent and config
        agent = _build_deep_agent(state, runtime)
        run_config = _build_runnable_config(state, config, runtime)
        # In non-graph contexts (e.g., Zendesk batch jobs), LangGraph may not set a stream writer.
        # Fallback to no-op writer to avoid "get_config outside of a runnable context" errors.
        try:
            writer = get_stream_writer()
        except Exception:
            writer = None

        # 5. Initialize stream event emitter early so the client receives
        # immediate feedback even if preprocessing (attachments, memory) is slow.
        root_id = str(state.trace_id or state.session_id or "run")
        emitter = StreamEventEmitter(writer, root_id=root_id)
        emitter.start_root_operation(
            name="Unified Agent",
            provider=runtime.provider,
            model=runtime.model,
            task_type=runtime.task_type,
        )

        # 6. Retrieve memory context
        memory_context = await _retrieve_memory_context(state)

        # 7. Prepare messages using MessagePreparer
        preparer = MessagePreparer(
            helper=helper,
            session_cache=session_cache,
        )
        messages, prep_stats = await preparer.prepare_messages(state, memory_context)

        # Store prep stats in scratchpad
        if isinstance(state.scratchpad, dict):
            state.scratchpad.setdefault("_system", {})["message_preparation"] = prep_stats

        # Auto-delegate to the log diagnoser when attachments indicate logs
        autoroute_msg = await _maybe_autoroute_log_analysis(state, helper)
        if autoroute_msg:
            messages.append(autoroute_msg)

        # Attachments may include large base64 payloads (images/PDFs). By this point
        # they've been inlined into `messages` (multimodal or summarized), so we can
        # drop the raw payload to reduce memory pressure and checkpoint bloat.
        try:
            state.attachments = []
        except Exception:
            pass

        # 8. Extract user query for reranking
        last_user_query = None
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                last_user_query = _coerce_message_text(message)
                break

        # 9. Transition to awaiting model and stream with handler
        tracker.transition_to(
            AgentLoopState.AWAITING_MODEL,
            metadata={"model": runtime.model, "provider": runtime.provider},
        )

        handler = StreamEventHandler(
            agent=agent,
            emitter=emitter,
            config=run_config,
            state=state,
            messages=messages,
            helper=helper,
            session_cache=session_cache,
            last_user_query=last_user_query,
        )

        final_output = await handler.stream_and_process()

        # Transition to streaming response
        tracker.transition_to(AgentLoopState.STREAMING_RESPONSE)

        # 10. Fallback if streaming returned nothing
        if final_output is None:
            try:
                final_output = await agent.ainvoke(
                    {"messages": list(messages), "attachments": state.attachments, "scratchpad": state.scratchpad},
                    config=run_config,
                )
            except Exception as exc:
                if runtime.provider == "google" and _is_quota_exhausted(exc):
                    fallback_model = model_router.fallback_chain.get(runtime.model)
                    if fallback_model and fallback_model != runtime.model:
                        logger.warning(
                            "gemini_quota_fallback",
                            primary=runtime.model,
                            fallback=fallback_model,
                            error=str(exc),
                        )
                        if limiter and reserved_slots:
                            for model_name, token_identifier in reserved_slots:
                                try:
                                    await limiter.release_slot(model_name, token_identifier)
                                except Exception as release_exc:
                                    logger.warning(
                                        "rate_limit_slot_release_failed",
                                        model=model_name,
                                        error=str(release_exc),
                                    )
                            reserved_slots.clear()
                        if await _reserve_model_slot(fallback_model):
                            runtime = AgentRuntimeConfig(
                                provider=runtime.provider,
                                model=fallback_model,
                                task_type=runtime.task_type,
                            )
                            state.model = fallback_model
                            agent = _build_deep_agent(state, runtime)
                            run_config = _build_runnable_config(state, config, runtime)
                            final_output = await agent.ainvoke(
                                {
                                    "messages": list(messages),
                                    "attachments": state.attachments,
                                    "scratchpad": state.scratchpad,
                                },
                                config=run_config,
                            )
                        else:
                            raise GeminiQuotaExhaustedException(runtime.model) from exc
                    else:
                        raise GeminiQuotaExhaustedException(runtime.model) from exc
                else:
                    raise

        # 11. Normalize outputs
        messages_payload = _extract_messages_from_output(state, final_output)

        if messages_payload is None:
            logger.error("Unified agent response missing messages; returning original state")
            return {"messages": state.messages}

        updated_messages = _strip_memory_messages(messages_payload)
        logger.info(
            "unified_agent_final_messages",
            count=len(updated_messages),
            last_role=getattr(updated_messages[-1], "role", None),
            last_preview=str(_coerce_message_text(updated_messages[-1]))[:200],
        )

        # Use output values if available, otherwise fall back to state, ensuring never None
        scratchpad = (
            (final_output.get("scratchpad") if isinstance(final_output, dict) else None)
            or state.scratchpad
            or {}
        )
        forwarded_props = (
            (final_output.get("forwarded_props") if isinstance(final_output, dict) else None)
            or state.forwarded_props
            or {}
        )

        # 12. Format log analysis results if applicable
        log_agent = (state.agent_type or state.forwarded_props.get("agent_type")) == "log_analysis"
        if log_agent:
            updated_messages = _format_log_analysis_messages(updated_messages)

        # Ensure assistant messages never leak thinking/tool-call artifacts to the user,
        # including non-AGUI contexts like the Zendesk scheduler.
        updated_messages = _sanitize_user_facing_messages(updated_messages)

        # 13. Record memory from response
        last_ai_message = next((m for m in reversed(updated_messages) if isinstance(m, AIMessage)), None)
        if last_ai_message is not None:
            await _record_memory(state, last_ai_message)

        # Mark completion and store tracker summary for LangSmith
        tracker.complete()

        # Add loop state summary to scratchpad for observability
        loop_summary = tracker.get_summary()
        if isinstance(scratchpad, dict):
            system_bucket = scratchpad.setdefault("_system", {})
            system_bucket["loop_state"] = loop_summary
            scratchpad["_system"] = system_bucket

        return {
            "messages": updated_messages,
            "scratchpad": scratchpad,
            "forwarded_props": forwarded_props,
            "attachments": [],
        }

    except RateLimitExceededException as e:
        tracker.set_error(f"Rate limit exceeded: {str(e)[:100]}")
        logger.error("gemini_rate_limited", model=getattr(runtime, "model", "unknown"), error=str(e))
        rate_limit_msg = AIMessage(content=(
            "I'm temporarily paused because the Gemini API rate limit was hit. "
            "Please wait a few seconds and try again; I'll reuse cached prep and keep the same model when capacity is free."
        ))

        # Add error state to scratchpad
        scratchpad = dict(state.scratchpad or {})
        system_bucket = scratchpad.setdefault("_system", {})
        system_bucket["loop_state"] = tracker.get_summary()
        scratchpad["_system"] = system_bucket

        return {
            "messages": [*state.messages, rate_limit_msg],
            "scratchpad": scratchpad,
            "forwarded_props": state.forwarded_props or {},
            "attachments": getattr(state, "attachments", []),
        }
    except Exception as e:
        tracker.set_error(f"Critical error: {str(e)[:100]}")
        logger.opt(exception=True).error("Critical error in unified agent execution: {}", e)

        # Add error state to scratchpad
        scratchpad = dict(state.scratchpad or {})
        system_bucket = scratchpad.setdefault("_system", {})
        system_bucket["loop_state"] = tracker.get_summary()
        scratchpad["_system"] = system_bucket

        return {
            "messages": state.messages,
            "scratchpad": scratchpad,
            "forwarded_props": state.forwarded_props or {},
            "error": str(e)
        }
    finally:
        if limiter:
            for model_name, token_identifier in reserved_slots:
                try:
                    await limiter.release_slot(model_name, token_identifier)
                except Exception as exc:
                    logger.warning(
                        "rate_limit_slot_release_failed",
                        model=model_name,
                        error=str(exc),
                    )


def _extract_messages_from_output(state: GraphState, final_output: Any) -> Optional[List[BaseMessage]]:
    """Extract messages list from agent output."""
    if isinstance(final_output, BaseMessage):
        return list(state.messages) + [final_output]

    if isinstance(final_output, dict):
        output_field = final_output.get("output")
        messages_field = final_output.get("messages")

        if isinstance(messages_field, list) and messages_field:
            return messages_field
        elif isinstance(output_field, BaseMessage):
            return list(state.messages) + [output_field]
        elif isinstance(output_field, str) and output_field.strip():
            return list(state.messages) + [AIMessage(content=output_field.strip())]

    return None


def _format_log_analysis_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """Format log analysis results in messages."""
    def _format_msg(msg: BaseMessage) -> Optional[str]:
        return _format_log_analysis_result(_coerce_message_text(msg))

    # Prefer the latest assistant message
    formatted: Optional[str] = None
    for idx in range(len(messages) - 1, -1, -1):
        candidate = messages[idx]
        if getattr(candidate, "role", None) == "assistant":
            formatted = _format_msg(candidate)
            if formatted:
                messages[idx] = AIMessage(content=formatted, additional_kwargs=getattr(candidate, "additional_kwargs", {}))
            break

    # Fallback to latest tool result if no assistant message was found
    if formatted is None:
        for idx in range(len(messages) - 1, -1, -1):
            candidate = messages[idx]
            if getattr(candidate, "role", None) == "tool":
                formatted = _format_msg(candidate)
                if formatted:
                    messages.append(AIMessage(content=formatted))
                break

    return messages


def should_continue(state: GraphState) -> str:
    """Determine if agent should continue or end."""
    if not state.messages:
        return "end"
    last_message = state.messages[-1]
    if isinstance(last_message, AIMessage):
        tool_calls = getattr(last_message, "tool_calls", None) or (
            (getattr(last_message, "additional_kwargs", {}) or {}).get("tool_calls")
        )
        if tool_calls:
            return "continue"
    return "end"
