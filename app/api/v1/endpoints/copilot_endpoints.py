from __future__ import annotations

"""
CopilotKit Remote Endpoint (AG-UI LangGraph)

Exposes `/api/v1/copilot/stream` as an auth-protected POST streaming endpoint
compatible with CopilotKit's runtime client. Uses the official `ag_ui_langgraph`
adapter to wrap our compiled LangGraph graph.

Phase 4 Implementation (AG-UI Protocol):
- Uses LangGraphAgent wrapper from ag_ui_langgraph for proper AG-UI protocol support
- Integrates EventEncoder from ag_ui.encoder for proper SSE formatting
- Preserves all Phase 1 enhancements:
  - Context merge: Extracts properties (session_id, trace_id, provider, model, agent_type)
    and merges them into both state dict and config.configurable for LangGraph execution
  - Attachment validation: Validates attachments using Attachment model with size/MIME checks
  - Comprehensive logging: Logs normalized properties, attachment processing, trace propagation
"""

import json
import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

# AG-UI Protocol imports
from ag_ui_langgraph import LangGraphAgent
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder

router = APIRouter()

# Authentication dependency
try:  # pragma: no cover - import-time guard
    from app.api.v1.endpoints.auth import get_current_user_id  # type: ignore
except Exception:  # pragma: no cover
    async def get_current_user_id() -> str:  # type: ignore
        from app.core.settings import settings
        return getattr(settings, 'development_user_id', 'dev-user-12345')


from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.orchestration.orchestration.graph import app as compiled_graph

# Import for context merge and attachment validation
from app.agents.orchestration.orchestration.state import GraphState, Attachment
from app.core.settings import get_settings

# OpenTelemetry tracer for this module
tracer = trace.get_tracer(__name__)

# Initialize AG-UI LangGraph agent wrapper
# This wraps our compiled graph with AG-UI protocol support
_langgraph_agent: Optional[LangGraphAgent] = None

def get_langgraph_agent() -> LangGraphAgent:
    """Get or create the AG-UI LangGraph agent wrapper."""
    global _langgraph_agent
    if _langgraph_agent is None:
        if compiled_graph is None:
            raise RuntimeError("Compiled graph not available")
        _langgraph_agent = LangGraphAgent(
            name="sparrow",
            graph=compiled_graph,
            description="Agent Sparrow - Multi-agent AI system with research, log analysis, and conversational capabilities",
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


def _coerce_message(raw: Any) -> Optional[BaseMessage]:
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
        if tool_calls and not isinstance(tool_calls, list):
            tool_calls = [tool_calls]
        return AIMessage(
            content=_coerce_text(data.get("content")),
            name=name,
            additional_kwargs=additional_kwargs,
            response_metadata=response_metadata,
            tool_calls=tool_calls,
        )

    if role == "system":
        return SystemMessage(content=_coerce_text(data.get("content")), name=name, additional_kwargs=additional_kwargs)

    if role == "tool":
        tool_call_id = data.get("tool_call_id") or data.get("toolCallId")
        if not tool_call_id:
            return None
        return ToolMessage(
            tool_call_id=str(tool_call_id),
            content=_coerce_text(data.get("content")),
            additional_kwargs=additional_kwargs,
        )

    return None


def _normalize_messages(raw_messages: Any) -> List[BaseMessage]:
    normalized: List[BaseMessage] = []
    if not isinstance(raw_messages, list):
        return normalized
    for item in raw_messages:
        msg = _coerce_message(item)
        if msg is not None:
            normalized.append(msg)
    return normalized


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
        except Exception as e:
            # Required: fail loudly on validation errors
            error_detail = f"Attachment validation failed at index {idx}: {str(e)}"
            logging.error(error_detail)
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "attachment_validation_failed",
                    "message": error_detail,
                    "attachment_index": idx,
                }
            )

    return attachments


def _merge_copilot_context(
    properties: Dict[str, Any],
    state: Dict[str, Any],
    config: Dict[str, Any],
) -> None:
    """
    Inject per-request CopilotKit context (provider, session, attachments) into state and config.

    Phase 1 Enhancement: Ports context merge logic from SparrowLangGraphAgent._merge_context
    to ensure feature parity between GraphQL and stream endpoints.

    This function:
    1. Extracts properties: session_id, trace_id, provider, model, agent_type, etc.
    2. Validates and sanitizes attachments
    3. Merges into state dict (for GraphState)
    4. Merges into config.configurable (for LangGraph execution)
    5. Applies defaults from settings if provider/model not specified

    Required: Fails loudly if critical properties are malformed (per requirement 3b).

    Args:
        properties: Forwarded properties from CopilotKit client
        state: State dict to be passed to LangGraph (modified in-place)
        config: Config dict with configurable field (modified in-place)
    """
    settings = get_settings()

    def _get_first(*keys: str) -> Optional[Any]:
        """Helper to extract first non-empty value from properties."""
        for key in keys:
            if key in properties and properties[key] not in (None, ""):
                return properties[key]
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
        provider = provider or getattr(settings, "primary_agent_provider", "google")
        model = model or getattr(settings, "primary_agent_model", "gemini-2.5-flash")

    # Validate and sanitize attachments (fails loudly on error)
    attachments = _sanitize_attachments(properties.get("attachments") or [])

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

    metadata = dict(configurable.get("metadata") or {})
    if session_id and "session_id" not in metadata:
        metadata["session_id"] = str(session_id)
    if trace_id and "trace_id" not in metadata:
        metadata["trace_id"] = str(trace_id)
    configurable["metadata"] = metadata

    tags = list(configurable.get("tags") or [])
    for tag in ("copilot-stream", agent_type, provider):
        if tag and tag not in tags:
            tags.append(tag)
    configurable["tags"] = tags

    if settings.langsmith_tracing_enabled:
        configurable.setdefault("name", "copilot-stream-run")
        if settings.langsmith_project:
            configurable.setdefault("project", settings.langsmith_project)
        if settings.langsmith_endpoint:
            configurable.setdefault("endpoint", settings.langsmith_endpoint)

    # Merge into state (GraphState fields)
    if session_id:
        state.setdefault("session_id", str(session_id))
    if trace_id:
        state.setdefault("trace_id", str(trace_id))
    if provider:
        state.setdefault("provider", str(provider))
    if model:
        state.setdefault("model", str(model))
    if agent_type:
        state.setdefault("agent_type", str(agent_type))
    if force_websearch is not None:
        state.setdefault("force_websearch", force_websearch)
    if websearch_max_results is not None:
        state.setdefault("websearch_max_results", websearch_max_results)
    if websearch_profile:
        state.setdefault("websearch_profile", str(websearch_profile))
    if formatting_mode:
        state.setdefault("formatting", str(formatting_mode).lower())
    if use_server_memory is not None:
        state.setdefault("use_server_memory", use_server_memory)
    if attachments:
        state.setdefault("attachments", attachments)

    # Comprehensive logging (Phase 1 requirement)
    logging.info(
        "copilot_context_merge_complete",
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


@router.post("/copilot/stream")
async def copilot_stream(
    input_data: RunAgentInput,
    request: Request,
    user_id: str = Depends(get_current_user_id)
):
    """Auth-protected CopilotKit streaming endpoint with AG-UI protocol.

    Phase 4 Implementation:
    - Accepts AG-UI RunAgentInput for proper protocol compliance
    - Applies custom context merge and attachment validation (Phase 1)
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
    with tracer.start_as_current_span("copilot.stream") as span:
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
            "copilot_stream_request_received",
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
            span.set_attribute("copilot.thread_id", thread_id)
            span.set_attribute("copilot.run_id", run_id)
            span.set_attribute("copilot.message_count", len(input_data.messages) if input_data.messages else 0)
            if isinstance(forwarded, dict):
                span.set_attribute("copilot.session_id", str(forwarded.get("session_id") or ""))
                span.set_attribute("copilot.trace_id", str(forwarded.get("trace_id") or ""))
                span.set_attribute("copilot.provider", str(forwarded.get("provider") or ""))
                span.set_attribute("copilot.model", str(forwarded.get("model") or ""))
                span.set_attribute("copilot.agent_type", str(forwarded.get("agent_type") or ""))
                att_count = len(forwarded.get("attachments", []) if isinstance(forwarded.get("attachments"), list) else [])
                span.set_attribute("copilot.attachments_count", att_count)
        except Exception:
            # Defensive: never break request flow due to telemetry
            pass

        # Phase 1: Merge CopilotKit context into state and config
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
            _merge_copilot_context(forwarded, state_dict, config_dict)
            logging.info(
                "copilot_context_merge_applied",
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
                    "message": f"Failed to merge CopilotKit context: {str(e)}",
                }
            )

        configurable = config_dict.setdefault("configurable", {})
        configurable.setdefault("thread_id", thread_id)
        configurable.setdefault("run_id", run_id)

        # Convert AG-UI messages to LangChain messages
        # AG-UI RunAgentInput already has properly typed messages, convert them to LangChain format
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

        # Create enriched graph state with merged context
        graph_state = {
            **state_dict,
            "messages": normalized_messages,
            "forwarded_props": forwarded_without_attachments,
            "scratchpad": state_dict.get("scratchpad") or {},
        }

        graph_state.setdefault("session_id", str(configurable.get("session_id") or thread_id))
        graph_state.setdefault("trace_id", str(configurable.get("trace_id") or run_id))
        graph_state.setdefault("attachments", state_dict.get("attachments") or [])
        graph_state.setdefault("use_server_memory", configurable.get("use_server_memory", False))

        logging.info(
            "copilot_stream_normalized",
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
            with tracer.start_as_current_span("copilot.stream.run") as run_span:
                cfg = config_dict.get("configurable", {})
                run_span.set_attribute("copilot.session_id", str(cfg.get("session_id") or ""))
                run_span.set_attribute("copilot.trace_id", str(cfg.get("trace_id") or ""))
                run_span.set_attribute("copilot.provider", str(cfg.get("provider") or ""))
                run_span.set_attribute("copilot.model", str(cfg.get("model") or ""))

                try:
                    # Stream events from AG-UI LangGraphAgent
                    # The agent.run() method returns properly formatted AG-UI protocol events
                    async for event in agent.run(enriched_input):
                        # Encode event using AG-UI EventEncoder for proper SSE formatting
                        yield encoder.encode(event)

                    run_span.set_status(Status(StatusCode.OK))
                except Exception as exc:  # pragma: no cover
                    run_span.record_exception(exc)
                    run_span.set_status(Status(StatusCode.ERROR, "agent_run_failed"))
                    logging.error(f"Agent run failed: {str(exc)}", exc_info=True)
                    raise

        span.set_status(Status(StatusCode.OK))
        return StreamingResponse(
            event_generator(),
            status_code=200,
            media_type=encoder.get_content_type()
        )


@router.get("/copilot/stream/health")
async def copilot_stream_health():
    """Return availability and configuration snapshot for the Copilot stream path.

    Phase 4: Updated to reflect AG-UI protocol integration.
    """
    graph_ok = compiled_graph is not None
    agent_ok = False
    try:
        agent = get_langgraph_agent()
        agent_ok = agent is not None
    except Exception:
        pass

    from app.core.settings import settings as _settings
    if not graph_ok or not agent_ok:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "ag_ui_available": True,
                "graph_compiled": graph_ok,
                "agent_initialized": agent_ok,
            },
        )
    return {
        "status": "ok",
        "protocol": "ag-ui",
        "ag_ui_available": True,
        "graph_compiled": True,
        "agent_initialized": True,
        "agent": "sparrow",
        "agents": [{"name": "sparrow", "status": "ready"}],
        "models": {
            "router": getattr(_settings, "router_model", None),
            "primary": getattr(_settings, "primary_agent_model", None),
            "log_analysis": getattr(_settings, "enhanced_log_model", None),
        },
    }
