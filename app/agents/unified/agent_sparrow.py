"""Unified Agent Sparrow implementation built on LangGraph v1.

Refactored to use modular streaming, event emission, and message preparation.
"""

from __future__ import annotations

import asyncio
import re
import textwrap
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.config import RunnableConfig, get_stream_writer
from loguru import logger

if TYPE_CHECKING:
    from app.agents.orchestration.orchestration.state import LogAnalysisNote

# Import middleware classes from correct sources
try:
    from langchain.agents.middleware import TodoListMiddleware
    from langchain.agents.middleware.summarization import SummarizationMiddleware
    from deepagents.middleware.subagents import SubAgentMiddleware, TASK_SYSTEM_PROMPT
    from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
    from app.agents.harness.middleware import (
        ToolResultEvictionMiddleware,
        WorkspaceWriteSandboxMiddleware,
    )

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
from app.core.config import (
    coordinator_bucket_name,
    find_bucket_for_model,
    find_model_config,
    get_models_config,
    resolve_coordinator_config,
)
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
from .log_autoroute_middleware import LogAutorouteMiddleware
from .name_sanitization_middleware import MessageNameSanitizationMiddleware
from .subagents import get_subagent_specs
from .prompts import get_coordinator_prompt, get_current_utc_date, TODO_PROMPT
from .thread_state import (
    compute_tool_burst_signature,
    extract_thread_state_at_tool_burst,
    maybe_ingest_legacy_handoff,
)
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
PROVIDER_TOKEN_LIMITS: dict[str, int] = {
    "google": 50000,      # Gemini 3 Pro has 1M/min quota - keep very low
    "xai": 80000,         # Grok ~400K context → 80K summarization threshold
    "openrouter": 50000,  # OpenRouter 262K context → 50K summarization threshold
}
DEFAULT_TOKEN_LIMIT = 50000  # Conservative default for unknown providers


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
TASK_TYPE_PATTERNS: dict[str, list[str]] = {
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
_COMPILED_TASK_PATTERNS: dict[str, list[re.Pattern]] = {
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

def _normalize_runtime_overrides(state: GraphState) -> str:
    """Normalize provider/model overrides using models.yaml."""
    config = get_models_config()
    allowed_providers = {"google", "xai", "openrouter"}

    provider = (state.provider or "").strip().lower()

    if state.model:
        match = find_model_config(config, state.model)
        if match is None:
            logger.warning("unknown_model_override", model=state.model)
            state.model = None
        else:
            provider = match.provider or provider

    if provider not in allowed_providers:
        provider = "google"

    state.provider = provider
    return provider


def _resolve_runtime_config(state: GraphState) -> AgentRuntimeConfig:
    """Resolve runtime configuration from state.

    IMPORTANT: This function should be called AFTER _ensure_model_selection()
    which performs the async health check and sets state.model. This function
    now uses the already-selected model rather than re-running model selection
    to avoid inconsistency between async health check and sync router.
    """
    provider = _normalize_runtime_overrides(state)
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
        config = get_models_config()
        if provider in {"xai", "openrouter"}:
            resolved_model = resolve_coordinator_config(config, provider).model_id
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

    # If attachments are present, prefer attachment-based routing for log analysis.
    # Attached logs are handled via deterministic tool calls, so we don't need to
    # escalate to the heavy coordinator model just because the user used log-ish keywords.
    attachments = getattr(state, "attachments", []) or []

    if fast_task == "log_analysis" and not attachments:
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
    if attachments:
        detection = _attachments_indicate_logs(state)
        if detection.get("has_log"):
            logger.info("task_type_slow_path", task_type="log_analysis", trigger="attachment_scan")
            forwarded_props["agent_type"] = "log_analysis"
            forwarded_props["log_detection"] = detection
            forwarded_props["task_detection_method"] = "attachment"
            state.forwarded_props = forwarded_props
            state.agent_type = "log_analysis"
            # Use the standard coordinator model; per-file log analysis runs via tools.
            return "coordinator"

    # 4. Default: light coordinator
    return "coordinator"


def _attachments_indicate_logs(state: GraphState) -> dict[str, Any]:
    """Centralized log attachment detection."""
    try:
        processor = get_attachment_processor()
        return processor.detect_log_attachments(getattr(state, "attachments", []) or [])
    except Exception as exc:
        logger.warning("log_attachment_detection_failed", error=str(exc))
        return {"has_log": False, "candidates": [], "non_text_skipped": []}


def _get_session_cache(session_id: Optional[str]) -> dict[str, dict[str, Any]]:
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
    provider = _normalize_runtime_overrides(state)

    # For non-Google providers, preserve the user's model selection
    if provider != "google":
        config = get_models_config()
        is_zendesk = (state.forwarded_props or {}).get("is_zendesk_ticket") is True
        if not state.model:
            coordinator_cfg = resolve_coordinator_config(
                config,
                provider,
                with_subagents=bool(MIDDLEWARE_AVAILABLE),
                zendesk=is_zendesk,
            )
            state.model = coordinator_cfg.model_id

        provider_key = (provider or "google").strip().lower()
        api_key_available = True
        if provider_key == "xai":
            api_key_available = bool(settings.xai_api_key)
        elif provider_key == "openrouter":
            api_key_available = bool(getattr(settings, "openrouter_api_key", None))

        if not api_key_available or not model_router.is_available(state.model):
            fallback_provider = config.fallback.coordinator_provider
            fallback_cfg = resolve_coordinator_config(
                config,
                fallback_provider,
                with_subagents=bool(MIDDLEWARE_AVAILABLE),
                zendesk=is_zendesk,
            )
            logger.warning(
                "non_google_model_unavailable",
                provider=provider,
                model=state.model,
                fallback_provider=fallback_provider,
                fallback_model=fallback_cfg.model_id,
            )
            provider = fallback_provider
            state.provider = fallback_provider
            state.model = fallback_cfg.model_id

        bucket_name = coordinator_bucket_name(
            provider,
            with_subagents=bool(MIDDLEWARE_AVAILABLE),
            zendesk=is_zendesk,
        )
        logger.info(
            "preserving_non_google_model_selection",
            provider=provider,
            model=state.model,
            task_type=task_type,
        )
        # Create a minimal selection result for non-Gemini models
        from .model_health import ModelHealth
        health = ModelHealth(
            bucket=bucket_name,
            model=state.model,
            provider=provider,
            available=True,
            rpm_used=0,
            rpm_limit=0,
            rpd_used=0,
            rpd_limit=0,
            tpm_used=0,
            tpm_limit=None,
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

    is_zendesk = (state.forwarded_props or {}).get("is_zendesk_ticket") is True
    selection = await model_router.select_model_with_health(
        task_type,
        user_override=state.model,
        provider=provider,
        zendesk=is_zendesk,
        with_subagents=bool(MIDDLEWARE_AVAILABLE),
    )
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

    Temperatures are resolved from models.yaml via provider_factory.

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

    current_date = get_current_utc_date()
    forwarded_props = getattr(state, "forwarded_props", {}) or {}
    if forwarded_props.get("agent_type") == "log_analysis":
        rule = (
            "Auto-routing rule: The user provided log file attachments.\n"
            "- Spawn ONE `log_diagnoser` tool call per file.\n"
            "- IMPORTANT: parallelize by emitting all tool calls in a SINGLE tool batch (one assistant turn).\n"
            "- Each call must include ONLY that file's name + log content (copy the matching Attachment block), plus the user's question/objective.\n"
            "- Do NOT combine multiple files into one tool call.\n"
            "- The `log_diagnoser` tool returns JSON with customer_ready + internal_notes; synthesize the customer-ready sections for the final response."
        )
        return f"{base}\n\nCurrent date: {current_date}\n\n{rule}"

    return f"{base}\n\nCurrent date: {current_date}"


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
    summarizer_model = chat_model
    try:
        from .provider_factory import build_summarization_model

        summarizer_model = build_summarization_model()
    except Exception as exc:  # pragma: no cover - best effort fallback
        logger.warning(
            "summarization_model_unavailable",
            error=str(exc),
            fallback_provider=runtime.provider,
            fallback_model=runtime.model,
        )
    # Zendesk tickets use a curated toolset (safer, support-focused) to reduce leakage risk
    # and keep replies aligned with internal support playbooks/macros.
    is_zendesk = (state.forwarded_props or {}).get("is_zendesk_ticket") is True
    tools = list(
        get_registered_support_tools() if is_zendesk else get_registered_tools()
    )

    # Inject workspace tools so agents can read persisted context (e.g. playbooks,
    # similar scenarios, evicted tool results) without keeping large blobs in memory.
    workspace_tools: list[Any] = []
    workspace_store: Any | None = None
    subagent_workspace_bridge: Any | None = None
    try:
        from app.agents.harness.store import SparrowWorkspaceStore
        from app.agents.unified.workspace_tools import (
            create_append_workspace_file,
            create_list_workspace_files,
            create_read_workspace_file,
            create_search_workspace,
            create_write_workspace_file,
        )

        session_id = getattr(state, "session_id", None) or getattr(state, "trace_id", None)
        user_id = getattr(state, "user_id", None)
        forwarded = state.forwarded_props or {}
        customer_id = None
        if isinstance(forwarded, dict):
            customer_id = forwarded.get("customer_id") or forwarded.get("customerId")

        if session_id is None:
            raise ValueError("workspace_session_id_missing")

        store = SparrowWorkspaceStore(
            session_id=str(session_id),
            user_id=str(user_id) if user_id is not None else None,
            customer_id=customer_id,
        )
        workspace_store = store
        workspace_tools = [
            create_read_workspace_file(store),
            create_list_workspace_files(store),
            create_search_workspace(store),
        ]
        if not is_zendesk:
            workspace_tools.extend(
                [create_write_workspace_file(store), create_append_workspace_file(store)]
            )
        tools.extend(workspace_tools)
        logger.debug(
            "workspace_tools_injected",
            is_zendesk=is_zendesk,
            count=len(workspace_tools),
        )
    except Exception as exc:
        logger.debug("workspace_tools_not_injected", error=str(exc)[:180])

    # Phase 1: Claude Code–style subagent report persistence + deterministic ingestion.
    if (
        settings.subagent_workspace_bridge_enabled
        and workspace_store is not None
        and workspace_tools
    ):
        try:
            from app.agents.unified.subagent_report_tools import (
                create_mark_subagent_reports_read_tool,
            )
            from app.agents.unified.subagent_workspace_bridge_middleware import (
                SubagentWorkspaceBridgeMiddleware,
            )

            tools.append(create_mark_subagent_reports_read_tool())
            subagent_workspace_bridge = SubagentWorkspaceBridgeMiddleware(
                workspace_store=workspace_store,
                report_read_limit_chars=settings.subagent_report_read_limit_chars,
                capsule_max_chars=settings.subagent_context_capsule_max_chars,
            )
        except Exception as exc:  # pragma: no cover - best effort only
            logger.debug("subagent_workspace_bridge_unavailable", error=str(exc)[:180])
    logger.debug("tool_registry_selected", mode="support" if is_zendesk else "standard")
    subagents = get_subagent_specs(
        provider=runtime.provider,
        zendesk=is_zendesk,
        workspace_tools=workspace_tools,
    )

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
                    model=summarizer_model,
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
                    model=summarizer_model,
                    trigger=("tokens", token_limit),
                    keep=("messages", 6),
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

        # Restrict subagent writes to their run directory (Claude-style isolation).
        default_middleware.append(WorkspaceWriteSandboxMiddleware())

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

        # Phase 3: deterministically autoroute log attachments into per-file `task` calls.
        middleware_stack.append(LogAutorouteMiddleware())
        if subagent_workspace_bridge is not None:
            middleware_stack.append(subagent_workspace_bridge)

        coordinator_middleware = SubAgentMiddleware(
            default_model=chat_model,
            default_tools=tools,
            subagents=subagents,
            default_middleware=default_middleware,
            system_prompt=_build_task_system_prompt(state),
            # Phase 2: keep subagent behavior/tooling strictly scoped to the
            # explicitly-declared subagents (no implicit general-purpose subagent).
            general_purpose_agent=False,
        )
        middleware_stack.append(coordinator_middleware)
        # Some providers (notably xAI) reject `name` on non-user messages. We
        # rely on message names internally for routing and context bookkeeping,
        # so sanitize names only immediately before model calls.
        middleware_stack.append(MessageNameSanitizationMiddleware())
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
) -> dict[str, Any]:
    """Build the runnable config for agent invocation."""
    base_config: dict[str, Any] = dict(config or {})
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
    """Inject an auto-routing instruction when log attachments are present.

    Phase 3 requirement: one subagent run per file (parallel) via DeepAgents `task`.
    We do NOT pre-run log analysis here; instead we instruct the coordinator to
    spawn per-file tasks in a single tool batch.
    """
    detection = _attachments_indicate_logs(state)
    forwarded_props = getattr(state, "forwarded_props", {}) or {}
    if detection.get("has_log"):
        forwarded_props["agent_type"] = "log_analysis"
        forwarded_props["log_detection"] = detection
        state.forwarded_props = forwarded_props
        state.agent_type = "log_analysis"
    else:
        return None

    candidates = detection.get("candidates") or []
    candidate_names = {
        str(item.get("name") or "").strip().lower()
        for item in candidates
        if isinstance(item, dict)
    }
    attachments = getattr(state, "attachments", []) or []
    file_names: list[str] = []
    for att in attachments:
        name = getattr(att, "name", None) if att is not None else None
        if isinstance(name, str) and name.strip() and name.strip().lower() in candidate_names:
            file_names.append(name.strip())

    # Fallback if we couldn't map candidates back to the original filenames
    if not file_names and candidate_names:
        file_names = sorted(name for name in candidate_names if name)

    files_block = "\n".join(f"- {name}" for name in file_names) if file_names else "- (unnamed attachments)"

    forwarded_props["autorouted"] = True
    state.forwarded_props = forwarded_props

    return SystemMessage(
        content=(
            "Log attachments detected. Do the following before writing the final answer:\n"
            f"{files_block}\n\n"
            "1) Spawn ONE `log_diagnoser` tool call per file.\n"
            "2) IMPORTANT: parallelize by emitting all tool calls in a SINGLE tool batch.\n"
            "3) Each call must include ONLY that file's name + log content, plus the user's question/objective.\n"
            "4) Do NOT combine multiple files into one call.\n"
            "5) After tools return, produce (per file): customer-ready response + internal diagnostic notes.\n"
            "6) Only use `web_search` if confidence is low and internal sources are insufficient.\n"
        ),
        name="log_autoroute_instruction",
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


def _extract_last_user_query(messages: list[BaseMessage]) -> str:
    """Extract the last human message text."""
    for message in reversed(messages or []):
        if getattr(message, "type", None) == "human":
            text = _coerce_message_text(message).strip()
            if text:
                return text
    return ""


def _build_memory_system_message(memories: list[dict[str, Any]]) -> Optional[SystemMessage]:
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
        "retrieved_memory_ids": [],  # Track IDs for feedback attribution
        "memory_ui_retrieval_enabled": memory_ui_enabled,
        "mem0_retrieval_enabled": mem0_enabled,
    }

    retrieved: list[dict[str, Any]] = []
    memory_ui_retrieved_ids: list[str] = []

    if mem0_enabled:
        try:
            retrieved = await memory_service.retrieve(
                agent_id=MEMORY_AGENT_ID,
                query=query,
                top_k=settings.memory_top_k,
            )
        except Exception as exc:
            logger.warning("memory_retrieve_failed", error=str(exc))
            memory_stats["retrieval_error"] = str(exc)

    if memory_ui_enabled:
        try:
            from app.memory.memory_ui_service import get_memory_ui_service

            service = get_memory_ui_service()
            ui_results = await service.search_memories(
                query=query,
                agent_id=getattr(settings, "memory_ui_agent_id", MEMORY_AGENT_ID) or MEMORY_AGENT_ID,
                tenant_id=getattr(settings, "memory_ui_tenant_id", "mailbot") or "mailbot",
                limit=settings.memory_top_k,
                similarity_threshold=0.5,
            )
            for item in ui_results or []:
                if not isinstance(item, dict):
                    continue
                memory_id = item.get("id")
                if isinstance(memory_id, str) and memory_id:
                    memory_ui_retrieved_ids.append(memory_id)
                retrieved.append(
                    {
                        "id": memory_id,
                        "memory": item.get("content"),
                        "score": item.get("similarity"),
                        "metadata": item.get("metadata") or {},
                        "source": "memory_ui",
                    }
                )
        except Exception as exc:
            logger.warning("memory_ui_retrieve_failed", error=str(exc))

    if not retrieved:
        _update_memory_stats(state, memory_stats)
        return None

    # Extract stats from retrieved memories including IDs for feedback attribution
    memory_stats["facts_retrieved"] = len(retrieved)
    memory_stats["relevance_scores"] = [
        mem.get("score", 0.0) if isinstance(mem, dict) else getattr(mem, "score", 0.0)
        for mem in retrieved
    ]
    # Extract memory IDs for feedback attribution
    memory_stats["retrieved_memory_ids"] = [
        mem.get("id") if isinstance(mem, dict) else getattr(mem, "id", None)
        for mem in retrieved
        if (mem.get("id") if isinstance(mem, dict) else getattr(mem, "id", None))
    ]

    memory_message = _build_memory_system_message(retrieved)
    if not memory_message:
        _update_memory_stats(state, memory_stats)
        return None

    # Store memory stats in scratchpad for LangSmith
    _update_memory_stats(state, memory_stats)

    # Best-effort: increment retrieval_count for Memory UI memories actually retrieved by the agent.
    if memory_ui_retrieved_ids:
        try:
            from app.memory.memory_ui_service import get_memory_ui_service

            service = get_memory_ui_service()
            unique_ids = list(dict.fromkeys(memory_ui_retrieved_ids))

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


def _update_memory_stats(state: GraphState, stats: dict[str, Any]) -> None:
    """Update memory stats in scratchpad for LangSmith observability."""
    if isinstance(state.scratchpad, dict):
        system_bucket = state.scratchpad.setdefault("_system", {})
        memory_section = system_bucket.setdefault("memory_stats", {})
        memory_section.update(stats)
        state.scratchpad["_system"] = system_bucket


def _strip_memory_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
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


def _summarize_response_to_facts(text: str, max_facts: int = 3, max_chars: int = 280) -> list[str]:
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

    seen: set[str] = set()
    distilled: list[str] = []
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


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    parts = _SENTENCE_BOUNDARY.split(text)
    sentences: list[str] = []
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

    meta: dict[str, Any] = {"source": "unified_agent"}
    if state.user_id:
        meta["user_id"] = state.user_id
    if state.session_id:
        meta["session_id"] = state.session_id
    if state.trace_id:
        meta["trace_id"] = state.trace_id
    if state.agent_type:
        meta["agent_type"] = state.agent_type
    meta["fact_strategy"] = "sentence_extract"

    if mem0_enabled:
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

    data: Optional[dict[str, Any]] = None
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

    # Phase 3 log diagnoser contract (per-file): customer-ready + internal notes
    customer_ready = data.get("customer_ready") or data.get("customerReady")
    internal_notes = data.get("internal_notes") or data.get("internalNotes")
    file_name = data.get("file_name") or data.get("fileName")

    lines: list[str] = []
    if file_name:
        lines.append(f"File: {file_name}")
    if customer_ready:
        lines.append("Customer-ready response:")
        lines.append(str(customer_ready).strip())
    if internal_notes:
        lines.append("Internal diagnostic notes:")
        lines.append(str(internal_notes).strip())
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

    def _solution_lines(solution: Any) -> Optional[list[str]]:
        if not isinstance(solution, dict):
            return None
        title = solution.get("title") or "Recommended action"
        steps = solution.get("steps") or []
        step_lines = [f"{idx+1}. {step}" for idx, step in enumerate(steps) if step]
        if not step_lines:
            return None
        return [f"{title}:"] + [f"   {s}" for s in step_lines]

    rendered_solutions: list[str] = []
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


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _extract_log_analysis_notes(
    messages: list[BaseMessage],
) -> dict[str, LogAnalysisNote]:
    """Extract per-file log notes from log-analysis tool results."""
    import json

    from app.agents.orchestration.orchestration.state import LogAnalysisNote

    tool_calls_by_id: dict[str, dict[str, Any]] = {}
    for msg in messages or []:
        if not isinstance(msg, AIMessage):
            continue
        tool_calls = getattr(msg, "tool_calls", None) or (
            (getattr(msg, "additional_kwargs", {}) or {}).get("tool_calls")
        ) or []
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            call_id = call.get("id") or call.get("tool_call_id") or call.get("toolCallId")
            if isinstance(call_id, str) and call_id:
                tool_calls_by_id[call_id] = call

    def _strip_code_fences(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*```\s*$", "", stripped)
        return stripped.strip()

    def _extract_json_object(text: str) -> Optional[str]:
        if not text:
            return None
        # Fast path: already looks like JSON object
        candidate = _strip_code_fences(text)
        if candidate.startswith("{") and candidate.endswith("}"):
            return candidate
        start = candidate.find("{")
        if start < 0:
            return None
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(candidate)):
            ch = candidate[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\\\":
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
                    return candidate[start : idx + 1]
        return None

    extracted: dict[str, LogAnalysisNote] = {}
    for msg in messages or []:
        if not isinstance(msg, ToolMessage):
            continue
        tool_call_id = getattr(msg, "tool_call_id", None)
        if not isinstance(tool_call_id, str) or not tool_call_id:
            continue
        call = tool_calls_by_id.get(tool_call_id)
        if not call:
            continue
        tool_name = str(call.get("name") or "").strip()
        if tool_name not in {"task", "log_diagnoser"}:
            continue

        args = call.get("args") or call.get("arguments") or {}
        if isinstance(args, str):
            try:
                parsed_args = json.loads(args)
                args = parsed_args if isinstance(parsed_args, dict) else {}
            except Exception:
                args = {}
        if not isinstance(args, dict):
            args = {}

        if tool_name == "task":
            subagent_type = args.get("subagent_type") or args.get("subagentType")
            if subagent_type != "log-diagnoser":
                continue

        content = _coerce_message_text(msg).strip()
        blob = _extract_json_object(content)
        if not blob:
            continue
        try:
            payload = json.loads(blob)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue

        file_name = str(payload.get("file_name") or payload.get("fileName") or "").strip()
        if not file_name and tool_name == "log_diagnoser":
            file_name = str(args.get("file_name") or args.get("fileName") or "").strip()
        customer_ready = str(payload.get("customer_ready") or payload.get("customerReady") or "").strip()
        internal_notes = str(payload.get("internal_notes") or payload.get("internalNotes") or "").strip()

        if tool_name == "log_diagnoser" and not customer_ready and payload.get("error"):
            customer_ready = (
                "Log analysis failed due to a processing error. "
                "Please try again or upload a smaller excerpt around the failure."
            )
            internal_notes = str(payload.get("message") or payload.get("suggestion") or "").strip()

        confidence_raw = payload.get("confidence", 0.0)
        try:
            confidence = float(confidence_raw) if confidence_raw is not None else 0.0
        except Exception:
            confidence = 0.0

        evidence = payload.get("evidence") or []
        if not isinstance(evidence, list):
            evidence = []
        recommended_actions = payload.get("recommended_actions") or payload.get("recommendedActions") or []
        if not isinstance(recommended_actions, list):
            recommended_actions = []
        open_questions = payload.get("open_questions") or payload.get("openQuestions") or []
        if not isinstance(open_questions, list):
            open_questions = []

        extracted[tool_call_id] = LogAnalysisNote(
            file_name=file_name,
            customer_ready=customer_ready,
            internal_notes=internal_notes,
            confidence=confidence,
            evidence=[str(item) for item in evidence if item is not None],
            recommended_actions=[str(item) for item in recommended_actions if item is not None],
            open_questions=[str(item) for item in open_questions if item is not None],
            created_at=_utc_now_iso(),
        )

    return extracted


# -----------------------------------------------------------------------------
# Main Agent Runner
# -----------------------------------------------------------------------------

async def run_unified_agent(state: GraphState, config: Optional[RunnableConfig] = None) -> dict[str, Any]:
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

        # 3. Rate limit preflight check with fallback (bucket-based)
        is_zendesk = (state.forwarded_props or {}).get("is_zendesk_ticket") is True
        with_subagents = bool(MIDDLEWARE_AVAILABLE)

        async def _reserve_bucket_slot(bucket_name: str) -> bool:
            """Reserve a rate limit slot for the supplied bucket."""
            try:
                result = await limiter.check_and_consume(bucket_name)
                return bool(getattr(result, "allowed", False))
            except RateLimitExceededException:
                logger.warning("bucket_precheck_rate_limited", bucket=bucket_name)
                return False
            except CircuitBreakerOpenException:
                logger.warning("bucket_precheck_circuit_open", bucket=bucket_name)
                return False
            except GeminiServiceUnavailableException as exc:
                logger.warning("bucket_precheck_unavailable", bucket=bucket_name, error=str(exc))
                return False

        if runtime.provider == "google" and runtime.task_type in {"coordinator_heavy", "log_analysis"}:
            primary_bucket = (
                "zendesk.coordinators.heavy" if is_zendesk else "coordinators.heavy"
            )
        else:
            primary_bucket = coordinator_bucket_name(
                runtime.provider,
                with_subagents=with_subagents,
                zendesk=is_zendesk,
            )

        slot_ok = await _reserve_bucket_slot(primary_bucket)
        if not slot_ok:
            config = get_models_config()
            bucket_prefix = "zendesk.coordinators." if is_zendesk else "coordinators."
            fallback_model = model_router.fallback_chain.get(runtime.model)
            fallback_bucket = None
            if fallback_model:
                fallback_bucket = (
                    find_bucket_for_model(config, fallback_model, prefix=bucket_prefix)
                    or find_bucket_for_model(config, fallback_model)
                )
            if fallback_model and fallback_bucket and await _reserve_bucket_slot(fallback_bucket):
                logger.info(
                    "retrying_with_fallback_model",
                    primary=runtime.model,
                    fallback=fallback_model,
                    bucket=fallback_bucket,
                )
                runtime = AgentRuntimeConfig(
                    provider=runtime.provider,
                    model=fallback_model,
                    task_type=runtime.task_type,
                )
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

        # Hydrate any persisted internal notes for the UI (Phase 3).
        try:  # pragma: no cover - best effort only
            existing_notes = getattr(state, "log_analysis_notes", None) or {}
            if existing_notes:
                emitter.emit_genui_state(
                    {
                        "logAnalysisNotes": {
                            key: note.model_dump()
                            for key, note in existing_notes.items()
                            if hasattr(note, "model_dump")
                        }
                    }
                )
        except Exception as exc:
            logger.debug("log_analysis_notes_emit_failed", error=str(exc))

        # ------------------------------------------------------------------
        # Phase 1: Thread State ("compressed truth")
        # ------------------------------------------------------------------
        # 5a. One-time migration: legacy workspace /handoff/summary.json -> thread_state
        try:
            session_key = getattr(state, "session_id", None) or getattr(state, "trace_id", None)
            if session_key:
                from app.agents.harness.store import SparrowWorkspaceStore

                user_id = getattr(state, "user_id", None)
                forwarded = getattr(state, "forwarded_props", {}) or {}
                customer_id = None
                if isinstance(forwarded, dict):
                    customer_id = forwarded.get("customer_id") or forwarded.get("customerId")

                workspace_store = SparrowWorkspaceStore(
                    session_id=session_key,
                    user_id=str(user_id) if user_id is not None else None,
                    customer_id=customer_id,
                )
                migrated = await maybe_ingest_legacy_handoff(state=state, workspace_store=workspace_store)
                if migrated:
                    emitter.add_trace_step(
                        step_type="thought",
                        content="Migrated legacy handoff into thread_state",
                        metadata={"kind": "compaction"},
                    )
        except Exception as exc:  # pragma: no cover - best effort only
            logger.debug("handoff_migration_skipped", error=str(exc))

        # 5b. Tool-burst boundary: extract/update thread_state after parallel tool batch completes
        burst_sig = compute_tool_burst_signature(getattr(state, "messages", []) or [])
        if burst_sig:
            compaction_alias = f"thread_state_compaction_{uuid.uuid4().hex[:8]}"
            emitter.add_trace_step(
                step_type="thought",
                content="Compacting thread_state from tool results...",
                metadata={"kind": "compaction"},
                alias=compaction_alias,
            )
            try:
                from .provider_factory import build_summarization_model

                summarizer = build_summarization_model()
                next_thread_state = await extract_thread_state_at_tool_burst(
                    summarizer_model=summarizer,
                    state=state,
                    current_date=get_current_utc_date(),
                )
                if next_thread_state is not None:
                    state.thread_state = next_thread_state
                emitter.update_trace_step(
                    compaction_alias,
                    replace_content="thread_state updated",
                    metadata={"status": "success"},
                    finalize=True,
                )
            except Exception as exc:
                emitter.update_trace_step(
                    compaction_alias,
                    replace_content="thread_state compaction failed",
                    metadata={"status": "error", "error": str(exc)},
                    finalize=True,
                )
                logger.warning("thread_state_compaction_failed", error=str(exc))

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
                        models_config = get_models_config()
                        bucket_prefix = "zendesk.coordinators." if is_zendesk else "coordinators."
                        fallback_bucket = (
                            find_bucket_for_model(models_config, fallback_model, prefix=bucket_prefix)
                            or find_bucket_for_model(models_config, fallback_model)
                        )
                        if fallback_bucket and await _reserve_bucket_slot(fallback_bucket):
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
            return {"messages": state.messages, "thread_state": state.thread_state}

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

        # ------------------------------------------------------------------
        # Phase 3: Persist internal log notes from per-file subagent runs
        # ------------------------------------------------------------------
        try:
            extracted_notes = _extract_log_analysis_notes(updated_messages)
            if extracted_notes:
                merged_notes = dict(getattr(state, "log_analysis_notes", {}) or {})
                merged_notes.update(extracted_notes)
                state.log_analysis_notes = merged_notes
                emitter.emit_genui_state(
                    {
                        "logAnalysisNotes": {
                            key: note.model_dump()
                            for key, note in merged_notes.items()
                            if hasattr(note, "model_dump")
                        }
                    }
                )
        except Exception as exc:  # pragma: no cover - best effort only
            logger.debug("log_analysis_notes_extract_failed", error=str(exc))

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
            "thread_state": state.thread_state,
            "log_analysis_notes": getattr(state, "log_analysis_notes", {}) or {},
        }

    except RateLimitExceededException as e:
        tracker.set_error(f"Rate limit exceeded: {str(e)[:100]}")
        logger.error(
            "provider_rate_limited",
            provider=getattr(runtime, "provider", "unknown"),
            model=getattr(runtime, "model", "unknown"),
            error=str(e),
        )
        rate_limit_msg = AIMessage(content=(
            "I'm temporarily paused because the LLM rate limit was hit. "
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
            "thread_state": getattr(state, "thread_state", None),
            "log_analysis_notes": getattr(state, "log_analysis_notes", {}) or {},
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
            "thread_state": getattr(state, "thread_state", None),
            "log_analysis_notes": getattr(state, "log_analysis_notes", {}) or {},
            "error": str(e)
        }
def _extract_messages_from_output(state: GraphState, final_output: Any) -> Optional[list[BaseMessage]]:
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


def _format_log_analysis_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
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
