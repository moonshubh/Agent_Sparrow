"""
AG-UI Streaming Endpoint (LangGraph)

Exposes `/api/v1/agui/stream` as an auth-protected POST streaming endpoint for
the native AG-UI client. Uses the official `ag_ui_langgraph` adapter to wrap
our compiled LangGraph graph.

Highlights:
- Native AG-UI protocol support via LangGraphAgent and EventEncoder
- Preserves Phase 1 safeguards:
  - Context merge: Extracts properties (session_id, trace_id, provider, model, agent_type)
    and merges them into both state dict and config.configurable for LangGraph execution
  - Attachment validation: Validates attachments using Attachment model with size/MIME checks
  - Comprehensive logging: Logs normalized properties, attachment processing, trace propagation
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import ValidationError

# AG-UI Protocol imports
from ag_ui_langgraph import LangGraphAgent
from ag_ui.core.types import RunAgentInput
from ag_ui.core import (
    CustomEvent,
    EventType,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
)
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph.types import LangGraphEventTypes
from ag_ui_langgraph.utils import make_json_safe
from ag_ui_langgraph.utils import agui_messages_to_langchain, get_stream_payload_input
from langgraph.types import Command

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.agents.orchestration.orchestration.graph import app as compiled_graph

# Import for context merge and attachment validation
from app.agents.orchestration.orchestration.state import Attachment
from app.core.settings import get_settings

router = APIRouter()

# Authentication dependency
try:  # pragma: no cover - import-time guard
    from app.api.v1.endpoints.auth import get_current_user_id  # type: ignore
except Exception:  # pragma: no cover
    async def get_current_user_id() -> str:  # type: ignore
        from app.core.settings import settings
        return getattr(settings, 'development_user_id', 'dev-user-12345')

# OpenTelemetry tracer for this module
tracer = trace.get_tracer(__name__)

# Initialize AG-UI LangGraph agent wrapper
# This wraps our compiled graph with AG-UI protocol support
_langgraph_agent: Optional[LangGraphAgent] = None
DEFAULT_LANGGRAPH_RECURSION_LIMIT = 120

class SparrowLangGraphAgent(LangGraphAgent):
    """LangGraphAgent variant that preserves full message history."""

    def langgraph_default_merge_state(self, state, messages, input):  # type: ignore[override]
        # DeepAgents inserts a synthetic system message at the beginning; drop it
        pruned_messages = list(messages or [])
        if pruned_messages and isinstance(pruned_messages[0], SystemMessage):
            pruned_messages = pruned_messages[1:]

        existing_messages = list(state.get("messages", []) or [])
        seen_ids = {
            str(getattr(msg, "id"))
            for msg in existing_messages
            if getattr(msg, "id", None) is not None
        }

        merged_messages = list(existing_messages)
        for message in pruned_messages:
            message_id = getattr(message, "id", None)
            if message_id is not None:
                key = str(message_id)
                if key in seen_ids:
                    continue
                seen_ids.add(key)
            merged_messages.append(message)

        tools = input.tools or []
        tools_as_dicts = []
        for tool in tools:
            if hasattr(tool, "model_dump"):
                tools_as_dicts.append(tool.model_dump())
            elif hasattr(tool, "dict"):
                tools_as_dicts.append(tool.dict())
            else:
                tools_as_dicts.append(tool)

        all_tools = [*state.get("tools", []), *tools_as_dicts]
        seen_tool_names = set()
        unique_tools = []
        for tool in all_tools:
            tool_name = None
            if isinstance(tool, dict):
                tool_name = tool.get("name")
            else:
                tool_name = getattr(tool, "name", None)

            if tool_name and tool_name in seen_tool_names:
                continue
            if tool_name:
                seen_tool_names.add(tool_name)
            unique_tools.append(tool)

        return {
            **state,
            "messages": merged_messages,
            "tools": unique_tools,
            "ag-ui": {
                "tools": unique_tools,
                "context": input.context or [],
            },
        }

    async def prepare_stream(self, input: RunAgentInput, agent_state: Any, config: Dict[str, Any]):
        state_input = input.state or {}
        messages = input.messages or []
        forwarded_props = input.forwarded_props or {}
        thread_id = input.thread_id

        state_input["messages"] = agent_state.values.get("messages", [])
        self.active_run["current_graph_state"] = agent_state.values.copy()
        langchain_messages = agui_messages_to_langchain(messages)
        state = self.langgraph_default_merge_state(state_input, langchain_messages, input)
        self.active_run["current_graph_state"].update(state)
        config["configurable"]["thread_id"] = thread_id
        interrupts = agent_state.tasks[0].interrupts if agent_state.tasks and len(agent_state.tasks) > 0 else []
        has_active_interrupts = len(interrupts) > 0
        resume_input = forwarded_props.get("command", {}).get("resume", None)

        self.active_run["schema_keys"] = self.get_schema_keys(config)

        events_to_dispatch = []
        if has_active_interrupts and not resume_input:
            events_to_dispatch.append(
                RunStartedEvent(type=EventType.RUN_STARTED, thread_id=thread_id, run_id=self.active_run["id"])
            )

            for interrupt in interrupts:
                events_to_dispatch.append(
                    CustomEvent(
                        type=EventType.CUSTOM,
                        name=LangGraphEventTypes.OnInterrupt.value,
                        value=make_json_safe(interrupt.value),
                        raw_event=interrupt,
                    )
                )

            events_to_dispatch.append(
                RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=thread_id, run_id=self.active_run["id"])
            )
            return {
                "stream": None,
                "state": None,
                "config": None,
                "events_to_dispatch": events_to_dispatch,
            }

        if self.active_run["mode"] == "continue":
            await self.graph.aupdate_state(config, state, as_node=self.active_run.get("node_name"))

        if resume_input:
            stream_input = Command(resume=resume_input)
        else:
            payload_input = get_stream_payload_input(
                mode=self.active_run["mode"],
                state=state,
                schema_keys=self.active_run["schema_keys"],
            )
            stream_input = {**forwarded_props, **payload_input} if payload_input else None

        subgraphs_stream_enabled = input.forwarded_props.get("stream_subgraphs") if input.forwarded_props else False

        kwargs = self.get_stream_kwargs(
            input=stream_input,
            config=config,
            subgraphs=bool(subgraphs_stream_enabled),
            version="v2",
        )

        stream = self.graph.astream_events(**kwargs)

        return {
            "stream": stream,
            "state": state,
            "config": config,
        }


def get_langgraph_agent() -> LangGraphAgent:
    """Get or create the AG-UI LangGraph agent wrapper."""
    global _langgraph_agent
    if _langgraph_agent is None:
        if compiled_graph is None:
            raise RuntimeError("Compiled graph not available")
        settings = get_settings()
        recur_limit = getattr(settings, "langgraph_recursion_limit", None) or getattr(settings, "agui_recursion_limit", None)
        try:
            recur_limit = int(recur_limit) if recur_limit is not None else DEFAULT_LANGGRAPH_RECURSION_LIMIT
        except Exception:
            recur_limit = DEFAULT_LANGGRAPH_RECURSION_LIMIT
        _langgraph_agent = SparrowLangGraphAgent(
            name="sparrow",
            graph=compiled_graph,
            description="Agent Sparrow - Multi-agent AI system with research, log analysis, and conversational capabilities",
            # LangGraph's default recursion_limit (25) is too low for multi-hop research flows.
            config={"recursion_limit": recur_limit},
        )
    return _langgraph_agent


def _coerce_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                pieces.append(str(part.get("text") or ""))
            else:
                pieces.append(str(part))
        return "".join(pieces)
    return str(content)


def _strip_reasoning_details(value: Any) -> Any:
    """Remove OpenRouter/OpenAI-style reasoning_details from JSON-like payloads.

    MiniMax M2.1 can emit large `reasoning_details` blocks (especially in streaming
    chunks). These should not be sent to the browser as part of RAW debug events.
    """

    if isinstance(value, dict):
        return {
            k: _strip_reasoning_details(v)
            for k, v in value.items()
            if k != "reasoning_details"
        }
    if isinstance(value, list):
        return [_strip_reasoning_details(v) for v in value]
    return value


def _normalize_tool_call_dict(raw: Any) -> Any:
    """Normalize various tool_call dict shapes into LangChain's {name, args, id} form.

    DeepAgents / Gemini may emit OpenAI-style tool_calls where arguments are nested
    under a `function` key. LangChain's ToolCall expects only name/args/id, so we
    strip the wrapper and coerce arguments into a dict when possible.
    """

    if not isinstance(raw, dict):
        return raw

    # OpenAI-style: {"id": "...", "type": "tool_call", "function": {"name": str, "arguments": str}}
    fn = raw.get("function")
    if isinstance(fn, dict):
        name = raw.get("name") or fn.get("name")
        args = raw.get("args") or fn.get("arguments") or fn.get("args")
        parsed_args: Any = args
        if isinstance(args, str):
            try:
                parsed_args = json.loads(args)
            except Exception:
                # Fall back to passing the raw string; LangChain will still accept
                parsed_args = {"input": args}
        if not isinstance(parsed_args, dict):
            parsed_args = {"input": parsed_args}

        return {
            "id": raw.get("id"),
            "name": name or "tool",
            "args": parsed_args,
        }

    # Already close to expected shape; just drop unknown keys that create_tool_call doesn't support
    cleaned: Dict[str, Any] = {}
    for key in ("id", "name", "args"):
        if key in raw:
            cleaned[key] = raw[key]
    return cleaned or raw


def _coerce_message(raw: Any) -> Optional[BaseMessage]:
    if isinstance(raw, BaseMessage):
        return raw

    data = raw.model_dump() if hasattr(raw, "model_dump") else raw
    if not isinstance(data, dict):
        return None

    role = str(data.get("role") or data.get("type") or "").lower()
    name = data.get("name")
    additional_kwargs = data.get("additional_kwargs") or {}
    response_metadata = data.get("response_metadata") or {}

    if role == "user":
        return HumanMessage(content=_coerce_text(data.get("content")), name=name, additional_kwargs=additional_kwargs)

    if role == "assistant":
        tool_calls = data.get("tool_calls") or data.get("toolCalls")
        invalid_tool_calls = data.get("invalid_tool_calls") or data.get("invalidToolCalls")

        if tool_calls and not isinstance(tool_calls, list):
            tool_calls = [tool_calls]
        if invalid_tool_calls and not isinstance(invalid_tool_calls, list):
            invalid_tool_calls = [invalid_tool_calls]

        normalized_tool_calls = [
            _normalize_tool_call_dict(tc) for tc in (tool_calls or [])
        ]
        resolved_tool_calls = normalized_tool_calls if normalized_tool_calls else []

        return AIMessage(
            content=_coerce_text(data.get("content")),
            name=name,
            additional_kwargs=additional_kwargs,
            response_metadata=response_metadata,
            tool_calls=resolved_tool_calls,
            invalid_tool_calls=invalid_tool_calls or [],
        )

    if role == "system":
        return SystemMessage(content=_coerce_text(data.get("content")), name=name, additional_kwargs=additional_kwargs)

    if role == "tool":
        tool_call_id = data.get("tool_call_id") or data.get("toolCallId")
        if not tool_call_id:
            return None

        tool_name = (
            data.get("name")
            or data.get("tool_call_name")
            or additional_kwargs.get("tool_name")
            or additional_kwargs.get("name")
            or "tool"
        )
        return ToolMessage(
            tool_call_id=str(tool_call_id),
            content=_coerce_text(data.get("content")),
            name=str(tool_name),
            additional_kwargs=additional_kwargs,
        )

    return None


def _normalize_messages(raw_messages: Any) -> List[BaseMessage]:
    normalized: List[BaseMessage] = []
    if raw_messages is None:
        return normalized
    if isinstance(raw_messages, BaseMessage):
        return [raw_messages]
    if not isinstance(raw_messages, list):
        raw_messages = [raw_messages]
    for item in raw_messages:
        msg = _coerce_message(item)
        if msg is not None:
            normalized.append(msg)
    return normalized


def _merge_message_history(
    existing: Optional[List[BaseMessage]],
    new: Optional[List[BaseMessage]],
) -> List[BaseMessage]:
    merged: List[BaseMessage] = list(existing or [])
    seen_ids: Set[str] = {
        str(getattr(message, "id"))
        for message in merged
        if getattr(message, "id", None) is not None
    }

    for message in new or []:
        message_id = getattr(message, "id", None)
        if message_id is not None:
            key = str(message_id)
            if key in seen_ids:
                continue
            seen_ids.add(key)
        merged.append(message)

    return merged


def _extract_chunk_text(chunk: Any) -> str:
    if chunk is None:
        return ""
    if hasattr(chunk, "message"):
        message = getattr(chunk, "message")
        content = getattr(message, "content", None)
    else:
        content = getattr(chunk, "content", None)
    if content is None and isinstance(chunk, dict):
        content = chunk.get("content")
    return _coerce_text(content)


def _message_to_text(message: BaseMessage) -> str:
    if isinstance(message, (AIMessage, HumanMessage, SystemMessage, ToolMessage)):
        return _coerce_text(message.content)
    return _coerce_text(getattr(message, "content", ""))


def _encode_sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sanitize_attachments(payload: Any) -> List[Dict[str, Any]]:
    """
    Validate and normalize attachment payloads into a predictable list of dicts.

    Phase 1 Enhancement: Validates attachments using the Attachment pydantic model
    to ensure size limits (10MB), allowed MIME types, and proper data URL format.

    Choice: Extract, validate, and pass attachments in state (not in forwardedProps)
    Why:
    - Ensures validation before agent execution
    - Provides parity with GraphQL endpoint (SparrowLangGraphAgent)
    - Clean separation: validated attachments in state, other properties in forwardedProps
    - Agents can trust state["attachments"] is validated

    Args:
        payload: Raw attachments list from client properties

    Returns:
        List of validated attachment dicts ready for GraphState

    Raises:
        HTTPException: If attachment validation fails (size, MIME type, format)
    """
    attachments: List[Dict[str, Any]] = []
    if not isinstance(payload, list):
        return attachments

    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            logging.warning(f"Skipping non-dict attachment at index {idx}")
            continue

        try:
            # Backward-compatibility mapping: accept legacy GraphQL keys
            # - filename -> name
            # - media_type -> mime_type
            normalized = dict(item)
            if "mime_type" not in normalized and "media_type" in normalized:
                normalized["mime_type"] = normalized.get("media_type")
            if "name" not in normalized and "filename" in normalized:
                normalized["name"] = normalized.get("filename")

            # Validate using Attachment model (enforces size, MIME type, data URL format)
            validated = Attachment.model_validate(normalized)
            attachments.append({
                "name": validated.name,
                "mime_type": validated.mime_type,
                "data_url": validated.data_url,
                "size": validated.size,
            })
            logging.debug(
                f"Validated attachment: name={validated.name}, mime_type={validated.mime_type}, "
                f"size={validated.size}"
            )
        except ValidationError as e:
            # Required: fail loudly on validation errors
            errors = e.errors()
            is_payload_too_large = any(
                (err.get("loc") or [])[-1:] == ["size"]
                and (
                    "less_than_equal" in str(err.get("type") or "")
                    or "maximum allowed" in str(err.get("msg") or "").lower()
                    or "exceeds" in str(err.get("msg") or "").lower()
                )
                for err in errors
            )
            status_code = 413 if is_payload_too_large else 400

            error_detail = f"Attachment validation failed at index {idx}"
            logging.error("%s: %s", error_detail, errors)
            raise HTTPException(
                status_code=status_code,
                detail={
                    "error": "attachment_validation_failed",
                    "message": error_detail,
                    "attachment_index": idx,
                    "validation_errors": [
                        {
                            "loc": err.get("loc"),
                            "msg": err.get("msg"),
                            "type": err.get("type"),
                        }
                        for err in errors
                    ],
                }
            )
        except Exception as e:
            # Required: fail loudly on validation errors
            error_detail = f"Attachment validation failed at index {idx}"
            logging.error("%s: %s", error_detail, str(e))
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "attachment_validation_failed",
                    "message": error_detail,
                    "attachment_index": idx,
                }
            )

    return attachments


def _merge_agui_context(
    properties: Dict[str, Any],
    state: Dict[str, Any],
    config: Dict[str, Any],
) -> None:
    """
    Inject per-request AG-UI context (provider, session, attachments) into state and config.

    This function:
    1. Extracts properties: session_id, trace_id, provider, model, agent_type, etc.
    2. Validates and sanitizes attachments
    3. Merges into state dict (for GraphState)
    4. Merges into config.configurable (for LangGraph execution)
    5. Applies defaults from settings if provider/model not specified

    Required: Fails loudly if critical properties are malformed (per requirement 3b).

    Args:
        properties: Forwarded properties from the AG-UI client
        state: State dict to be passed to LangGraph (modified in-place)
        config: Config dict with configurable field (modified in-place)
    """
    settings = get_settings()

    def _get_first(*keys: str) -> Optional[Any]:
        """Helper to extract first non-empty value from properties or state."""
        for key in keys:
            if key in properties and properties[key] not in (None, ""):
                return properties[key]
            if key in state and state[key] not in (None, ""):
                return state[key]
        return None

    # Extract core properties
    session_id = _get_first("session_id")
    trace_id = _get_first("trace_id")
    provider = _get_first("provider")
    model = _get_first("model")
    agent_type = _get_first("agent_type")
    force_websearch = _get_first("force_websearch")
    websearch_max_results = _get_first("websearch_max_results")
    websearch_profile = _get_first("websearch_profile")
    formatting_mode = _get_first("formatting", "formatting_mode")
    use_server_memory = _get_first("use_server_memory")

    # Apply defaults if provider/model not specified
    if not provider or not model:
        provider = (provider or getattr(settings, "primary_agent_provider", "google")).lower()
        if not model:
            if provider == "xai":
                model = getattr(settings, "xai_default_model", None) or "grok-4-1-fast-reasoning"
            elif provider == "openrouter":
                model = getattr(settings, "openrouter_default_model", None) or "x-ai/grok-4.1-fast"
            else:
                model = getattr(settings, "primary_agent_model", "gemini-2.5-flash")

    # Backend default for memory toggle when client is silent
    if use_server_memory is None:
        if settings.should_enable_agent_memory():
            use_server_memory = bool(getattr(settings, "agent_memory_default_enabled", False))
        else:
            use_server_memory = False

    # Validate and sanitize attachments (fails loudly on error)
    attachments = _sanitize_attachments(properties.get("attachments") or state.get("attachments") or [])

    # Merge into config.configurable (LangGraph execution context)
    configurable = config.setdefault("configurable", {})
    if session_id:
        configurable["session_id"] = str(session_id)
    if trace_id:
        configurable["trace_id"] = str(trace_id)
    if provider:
        configurable["provider"] = str(provider)
    if model:
        configurable["model"] = str(model)
    if agent_type:
        configurable["agent_type"] = str(agent_type)
    if force_websearch is not None:
        configurable["force_websearch"] = force_websearch
    if websearch_max_results is not None:
        configurable["websearch_max_results"] = websearch_max_results
    if websearch_profile:
        configurable["websearch_profile"] = str(websearch_profile)
    if formatting_mode:
        configurable["formatting"] = str(formatting_mode).lower()
    if use_server_memory is not None:
        configurable["use_server_memory"] = use_server_memory
    if attachments:
        configurable["attachments"] = attachments

    # Enhanced LangSmith metadata for comprehensive observability (Phase 5)
    metadata = dict(configurable.get("metadata") or {})

    # Core identifiers
    if session_id and "session_id" not in metadata:
        metadata["session_id"] = str(session_id)
    if trace_id and "trace_id" not in metadata:
        metadata["trace_id"] = str(trace_id)

    # Agent configuration for analysis
    metadata["agent_config"] = {
        "provider": provider or "unknown",
        "model": model or "unknown",
        "agent_type": agent_type or "primary",
        "coordinator_mode": "heavy" if model and "pro" in model.lower() else "light",
    }

    # Feature flags for tracking usage patterns
    metadata["feature_flags"] = {
        "memory_enabled": bool(use_server_memory),
        "grounding_enabled": bool(settings.enable_grounding_search),
        "attachments_present": len(attachments) > 0,
        "attachments_count": len(attachments),
        "force_websearch": bool(force_websearch),
    }

    # Search configuration if applicable
    if websearch_max_results is not None or websearch_profile is not None:
        metadata["search_config"] = {
            "max_results": websearch_max_results,
            "profile": websearch_profile,
        }

    configurable["metadata"] = metadata

    # Enhanced tags for filtering and analysis in LangSmith
    tags = list(configurable.get("tags") or [])
    tag_candidates = ["agui-stream", agent_type, provider]

    # Memory and attachment tags
    if use_server_memory:
        tag_candidates.append("memory_enabled")
    if attachments:
        tag_candidates.append("attachments:true")

    # Model and coordinator mode tags
    if model:
        tag_candidates.append(f"model:{model}")
        coordinator_mode = "heavy" if "pro" in model.lower() else "light"
        tag_candidates.append(f"coordinator_mode:{coordinator_mode}")

    # Agent type and task tags
    if agent_type:
        tag_candidates.append(f"task_type:{agent_type}")

    for tag in tag_candidates:
        if tag and tag not in tags:
            tags.append(tag)
    configurable["tags"] = tags

    if settings.langsmith_tracing_enabled:
        configurable.setdefault("name", "agui-stream-run")
        if settings.langsmith_project:
            configurable.setdefault("project", settings.langsmith_project)
        if settings.langsmith_endpoint:
            configurable.setdefault("endpoint", settings.langsmith_endpoint)

    # Merge into state (GraphState fields)
    if session_id:
        state["session_id"] = str(session_id)
    if trace_id:
        state["trace_id"] = str(trace_id)
    if provider:
        state["provider"] = str(provider)
    if model:
        state["model"] = str(model)
    if agent_type:
        state["agent_type"] = str(agent_type)
    if force_websearch is not None:
        state["force_websearch"] = force_websearch
    if websearch_max_results is not None:
        state["websearch_max_results"] = websearch_max_results
    if websearch_profile:
        state["websearch_profile"] = str(websearch_profile)
    if formatting_mode:
        state["formatting"] = str(formatting_mode).lower()
    if use_server_memory is not None:
        state["use_server_memory"] = use_server_memory
    if attachments:
        state["attachments"] = attachments

    # Comprehensive logging (Phase 1 requirement)
    logging.info(
        "agui_context_merge_complete",
        extra={
            "session_id": session_id,
            "trace_id": trace_id,
            "provider": provider,
            "model": model,
            "agent_type": agent_type,
            "attachments_count": len(attachments),
            "use_server_memory": use_server_memory,
            "force_websearch": force_websearch,
        },
    )


@router.post("/agui/stream")
async def agui_stream(
    input_data: RunAgentInput,
    request: Request,
    user_id: str = Depends(get_current_user_id)
):
    """Auth-protected AG-UI streaming endpoint.

    Phase 4 Implementation:
    - Accepts AG-UI RunAgentInput for proper protocol compliance
    - Applies custom context merge and attachment validation (Phase 1 guardrails)
    - Uses LangGraphAgent.run() for AG-UI protocol streaming
    - Uses EventEncoder for proper SSE event formatting
    - Preserves authentication and telemetry

    Args:
        input_data: AG-UI protocol RunAgentInput with messages, state, tools, etc.
        request: FastAPI request for headers and telemetry
        user_id: Authenticated user ID from dependency

    Returns:
        StreamingResponse with AG-UI protocol formatted SSE events
    """
    with tracer.start_as_current_span("agui.stream") as span:
        try:
            agent = get_langgraph_agent()
        except RuntimeError as e:
            span.set_status(Status(StatusCode.ERROR, "graph_unavailable"))
            return JSONResponse(
                status_code=501,
                content={
                    "error": "graph_unavailable",
                    "detail": str(e),
                },
            )

        # Extract forwardedProps from AG-UI RunAgentInput
        # These contain custom properties like session_id, trace_id, provider, model, attachments
        forwarded: Dict[str, Any] = input_data.forwarded_props if input_data.forwarded_props else {}

        # Extract thread and run IDs from AG-UI input
        thread_id = input_data.thread_id
        run_id = input_data.run_id

        # Comprehensive logging: Log incoming properties (Phase 1 requirement)
        logging.info(
            "agui_stream_request_received",
            extra={
                "thread_id": thread_id,
                "run_id": run_id,
                "message_count": len(input_data.messages) if input_data.messages else 0,
                "has_forwarded_props": bool(forwarded),
                "forwarded_keys": list(forwarded.keys()) if isinstance(forwarded, dict) else [],
                "session_id_present": "session_id" in forwarded,
                "trace_id_present": "trace_id" in forwarded,
                "attachments_present": "attachments" in forwarded,
                "attachments_count": len(forwarded.get("attachments", [])) if isinstance(forwarded.get("attachments"), list) else 0,
            },
        )

        # Populate span attributes with non-PII diagnostics
        try:
            span.set_attribute("agui.thread_id", thread_id)
            span.set_attribute("agui.run_id", run_id)
            span.set_attribute("agui.message_count", len(input_data.messages) if input_data.messages else 0)
            if isinstance(forwarded, dict):
                span.set_attribute("agui.session_id", str(forwarded.get("session_id") or ""))
                span.set_attribute("agui.trace_id", str(forwarded.get("trace_id") or ""))
                span.set_attribute("agui.provider", str(forwarded.get("provider") or ""))
                span.set_attribute("agui.model", str(forwarded.get("model") or ""))
                span.set_attribute("agui.agent_type", str(forwarded.get("agent_type") or ""))
                att_count = len(forwarded.get("attachments", []) if isinstance(forwarded.get("attachments"), list) else [])
                span.set_attribute("agui.attachments_count", att_count)
        except Exception:
            # Defensive: never break request flow due to telemetry
            pass

        # Phase 1: Merge AG-UI context into state and config
        # This ensures feature parity with GraphQL endpoint (SparrowLangGraphAgent)
        # Start with state from input_data (may be dict or None)
        state_dict: Dict[str, Any] = {}
        if input_data.state:
            if isinstance(input_data.state, dict):
                state_dict = dict(input_data.state)
            elif hasattr(input_data.state, 'model_dump'):
                state_dict = input_data.state.model_dump()
            elif hasattr(input_data.state, 'dict'):
                state_dict = input_data.state.dict()

        config_dict: Dict[str, Any] = {"configurable": {}}

        # Extract attachments from forwarded props and remove to avoid duplication
        # (attachments will be in state after merge, not in forwardedProps)
        forwarded_without_attachments = {k: v for k, v in forwarded.items() if k != "attachments"}

        try:
            _merge_agui_context(forwarded, state_dict, config_dict)
            logging.info(
                "agui_context_merge_applied",
                extra={
                    "state_keys": list(state_dict.keys()),
                    "config_keys": list(config_dict.get("configurable", {}).keys()),
                },
            )
        except HTTPException:
            # Attachment validation errors are already HTTPException, re-raise
            raise
        except Exception as e:
            # Required: Fail loudly on context merge errors (requirement 3b)
            logging.error(f"Context merge failed: {str(e)}", exc_info=True)
            span.set_status(Status(StatusCode.ERROR, "context_merge_failed"))
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "context_merge_failed",
                    "message": f"Failed to merge AG-UI context: {str(e)}",
                }
            )

        configurable = config_dict.setdefault("configurable", {})
        configurable.setdefault("thread_id", thread_id)
        configurable.setdefault("run_id", run_id)

        metadata = dict(configurable.get("metadata") or {})
        if user_id:
            metadata["user_id"] = str(user_id)
        configurable["metadata"] = metadata

        state_dict["user_id"] = str(user_id)

        # Convert AG-UI messages to LangChain messages
        # AG-UI RunAgentInput already has properly typed messages, convert them to LangChain format
        persisted_messages = _normalize_messages(state_dict.pop("messages", None))

        messages_payload = []
        if input_data.messages:
            for msg in input_data.messages:
                # Convert AG-UI message model to dict for _normalize_messages
                if hasattr(msg, 'model_dump'):
                    messages_payload.append(msg.model_dump())
                elif hasattr(msg, 'dict'):
                    messages_payload.append(msg.dict())
                elif isinstance(msg, dict):
                    messages_payload.append(msg)

        normalized_messages = _normalize_messages(messages_payload)
        merged_messages = _merge_message_history(persisted_messages, normalized_messages)

        # Create enriched graph state with merged context
        graph_state = {
            **state_dict,
            "messages": merged_messages,
            "forwarded_props": forwarded_without_attachments,
            "scratchpad": state_dict.get("scratchpad") or {},
        }

        graph_state.setdefault("session_id", str(configurable.get("session_id") or thread_id))
        graph_state.setdefault("trace_id", str(configurable.get("trace_id") or run_id))
        graph_state.setdefault("attachments", state_dict.get("attachments") or [])
        graph_state.setdefault("use_server_memory", configurable.get("use_server_memory", False))
        # user_id already set in state_dict at line 514, no need for setdefault

        logging.info(
            "agui_stream_normalized",
            extra={
                "message_count": len(normalized_messages),
                "thread_id": graph_state.get("session_id"),
                "trace_id": graph_state.get("trace_id"),
            },
        )

        # Create enriched RunAgentInput with merged context
        # This preserves all AG-UI protocol fields while adding our custom state
        enriched_input = RunAgentInput(
            thread_id=thread_id,
            run_id=run_id,
            state=graph_state,  # Enriched state with context merge
            messages=input_data.messages,
            tools=input_data.tools if input_data.tools else [],
            context=input_data.context if input_data.context else [],
            forwarded_props=forwarded_without_attachments,  # Pass forwardedProps without attachments
        )

        # Get Accept header for proper event encoding
        accept_header = request.headers.get("accept")
        encoder = EventEncoder(accept=accept_header)

        async def event_generator():
            """Stream AG-UI protocol events from LangGraphAgent."""
            with tracer.start_as_current_span("agui.stream.run") as run_span:
                cfg = config_dict.get("configurable", {})
                run_span.set_attribute("agui.session_id", str(cfg.get("session_id") or ""))
                run_span.set_attribute("agui.trace_id", str(cfg.get("trace_id") or ""))
                run_span.set_attribute("agui.provider", str(cfg.get("provider") or ""))
                run_span.set_attribute("agui.model", str(cfg.get("model") or ""))

                try:
                    # Stream events from AG-UI LangGraphAgent
                    # The agent.run() method returns properly formatted AG-UI protocol events
                    async for event in agent.run(enriched_input):
                        update: dict[str, Any] = {}

                        # Avoid sending large `reasoning_details` blocks to the browser.
                        try:
                            if hasattr(event, "raw_event") and getattr(event, "raw_event") is not None:
                                update["raw_event"] = _strip_reasoning_details(
                                    getattr(event, "raw_event")
                                )
                            if getattr(event, "type", None) == EventType.RAW and hasattr(event, "event"):
                                update["event"] = _strip_reasoning_details(getattr(event, "event"))
                            if update:
                                event = event.model_copy(update=update)
                        except Exception:
                            # Never fail streaming due to debug payload sanitization.
                            pass
                        # Encode event using AG-UI EventEncoder for proper SSE formatting
                        yield encoder.encode(event)

                    run_span.set_status(Status(StatusCode.OK))
                except Exception as exc:  # pragma: no cover
                    run_span.record_exception(exc)
                    run_span.set_status(Status(StatusCode.ERROR, "agent_run_failed"))
                    logging.error(f"Agent run failed: {str(exc)}", exc_info=True)
                    try:
                        yield encoder.encode(
                            RunErrorEvent(
                                type=EventType.RUN_ERROR,
                                message=f"Agent run failed: {type(exc).__name__}",
                                code="agent_run_failed",
                            )
                        )
                    except Exception:
                        pass
                    return

        span.set_status(Status(StatusCode.OK))
        return StreamingResponse(
            event_generator(),
            status_code=200,
            media_type=encoder.get_content_type()
        )


@router.get("/agui/stream/health")
async def agui_stream_health():
    """Return availability and configuration snapshot for the AG-UI stream path.

    Phase 4: Updated to reflect AG-UI protocol integration.
    """
    graph_ok = compiled_graph is not None
    agent_ok = False
    try:
        _ = get_langgraph_agent()
        agent_ok = True
    except Exception:
        agent_ok = False
    return {
        "status": "ok" if graph_ok else "error",
        "graph_available": graph_ok,
        "agent_available": agent_ok,
        "protocol": "ag-ui-langgraph",
    }


# --- Subgraphs Support ---

try:
    from app.agents.unified.agent_travel import graph as travel_graph
except ImportError:
    travel_graph = None  # type: ignore[assignment]

_travel_agent: Optional[LangGraphAgent] = None

def get_travel_agent() -> LangGraphAgent:
    """Get or create the Travel Agent wrapper."""
    global _travel_agent
    if _travel_agent is None:
        if travel_graph is None:
            raise RuntimeError("Travel graph not available")
        _travel_agent = LangGraphAgent(
            name="travel_agent",
            graph=travel_graph,
            description="Travel Agent Supervisor",
            config={"recursion_limit": DEFAULT_LANGGRAPH_RECURSION_LIMIT},
        )
    return _travel_agent

@router.post("/agui/subgraphs/stream")
async def agui_subgraphs_stream(
    input_data: RunAgentInput,
    request: Request,
    user_id: str = Depends(get_current_user_id)
):
    """Endpoint for Subgraphs demo (Travel Agent)."""
    with tracer.start_as_current_span("agui.subgraphs.stream"):
        try:
            agent = get_travel_agent()
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

        # Basic encoder setup
        accept_header = request.headers.get("accept")
        encoder = EventEncoder(accept=accept_header)

        async def event_generator():
            async for event in agent.run(input_data):
                yield encoder.encode(event)

        return StreamingResponse(
            event_generator(),
            status_code=200,
            media_type=encoder.get_content_type()
        )
