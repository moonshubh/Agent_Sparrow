"""Unified Agent Sparrow implementation built on LangGraph v1."""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
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

from .model_router import ModelSelectionResult, model_router
from .tools import get_registered_tools
from .subagents import get_subagent_specs
from .prompts import COORDINATOR_PROMPT

MEMORY_AGENT_ID = "sparrow"
MEMORY_SYSTEM_NAME = "server_memory_context"
BASE_AGENT_PROMPT = (
    "In order to complete the objective that the user asks of you, you have access to a number "
    "of standard tools."
)


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


def _determine_task_type(state: GraphState) -> str:
    forwarded_props = getattr(state, "forwarded_props", {}) or {}
    coordinator_mode = forwarded_props.get("coordinator_mode") or getattr(state, "coordinator_mode", None)
    heavy_mode = isinstance(coordinator_mode, str) and coordinator_mode.lower() in {"heavy", "pro", "coordinator_heavy"}
    return "coordinator_heavy" if heavy_mode else "coordinator"


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

    system_prompt = f"{COORDINATOR_PROMPT}\n\n{BASE_AGENT_PROMPT}" if COORDINATOR_PROMPT else BASE_AGENT_PROMPT

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
            general_purpose_agent=False,
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
    try:
        retrieved = await memory_service.retrieve(
            agent_id=MEMORY_AGENT_ID,
            query=query,
            top_k=settings.memory_top_k,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("memory_retrieve_failed", error=str(exc))
        return state.messages

    if not retrieved:
        return state.messages

    memory_message = _build_memory_system_message(retrieved)
    if not memory_message:
        return state.messages

    return [memory_message, *state.messages]


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
    if not facts:
        return

    meta: Dict[str, Any] = {"source": "unified_agent"}
    if state.user_id:
        meta["user_id"] = state.user_id
    if state.session_id:
        meta["session_id"] = state.session_id
    meta["fact_strategy"] = "sentence_extract"

    try:
        await memory_service.add_facts(
            agent_id=MEMORY_AGENT_ID,
            facts=facts,
            meta=meta,
        )
    except Exception as exc:  # pragma: no cover - best effort persistence
        logger.warning("memory_add_failed", error=str(exc))


async def run_unified_agent(state: GraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Run the unified agent with comprehensive error handling."""
    try:
        await _ensure_model_selection(state)
        runtime = _resolve_runtime_config(state)
        agent = _build_deep_agent(state, runtime)
        run_config = _build_runnable_config(state, config, runtime)
        writer = get_stream_writer()
        memory_enabled = _memory_is_enabled(state)
        messages_with_memory = await _prepend_memory_context(state, memory_enabled)

        final_output: Optional[Dict[str, Any]] = None

        def _agent_inputs() -> Dict[str, Any]:
            return {
                "messages": list(messages_with_memory),
                "attachments": state.attachments,
                "scratchpad": state.scratchpad,
            }

        if writer is not None:
            try:
                async for event in agent.astream_events(
                    _agent_inputs(),
                    config=run_config,
                ):
                    event_type = event.get("event")
                    data = event.get("data", {})
                    if event_type == "on_chat_model_stream":
                        chunk = data.get("chunk")
                        if chunk is None:
                            continue
                        content = getattr(chunk, "content", None)
                        if not content and hasattr(chunk, "message"):
                            message_obj = getattr(chunk, "message")
                            content = getattr(message_obj, "content", None)
                        if isinstance(content, list):
                            content = "".join(str(part) for part in content if part)
                        if content:
                            writer({"type": "assistant-delta", "delta": content})
                    elif event_type in {"on_chain_end", "on_graph_end"}:
                        output = data.get("output")
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

        updated_messages = _strip_memory_messages(final_output.get("messages") or [])
        # DeepAgents returns BaseMessage objects; ensure we maintain list semantics.
        if not updated_messages or not isinstance(updated_messages[-1], BaseMessage):
            logger.error("Unified agent response missing AI message; returning original state")
            return {"messages": state.messages}

        scratchpad = final_output.get("scratchpad") or state.scratchpad
        forwarded_props = final_output.get("forwarded_props") or state.forwarded_props

        last_ai_message = updated_messages[-1]
        if isinstance(last_ai_message, AIMessage):
            await _record_memory(state, last_ai_message)

        return {
            "messages": updated_messages,
            "scratchpad": scratchpad,
            "forwarded_props": forwarded_props,
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


def should_continue(state: GraphState) -> str:
    if not state.messages:
        return "end"
    last_message = state.messages[-1]
    if isinstance(last_message, AIMessage):
        tool_calls = getattr(last_message, "tool_calls", None)
        if tool_calls:
            return "continue"
    return "end"
