from __future__ import annotations

"""
CopilotKit Remote Endpoint (AG-UI LangGraph)

Exposes `/api/v1/copilot/stream` as an auth-protected POST streaming endpoint
compatible with CopilotKit's runtime client. Uses the official `ag_ui_langgraph`
adapter to wrap our compiled LangGraph graph.

Phase 1 Enhancement:
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
async def copilot_stream(request: Request, user_id: str = Depends(get_current_user_id)):
    """Auth-protected CopilotKit streaming endpoint.

    Accepts raw JSON from CopilotKit runtime clients, normalizes it into the unified
    graph state, and streams LangGraph output as simple SSE events.
    """
    with tracer.start_as_current_span("copilot.stream") as span:
        if compiled_graph is None:
            span.set_status(Status(StatusCode.ERROR, "graph_unavailable"))
            return JSONResponse(
                status_code=501,
                content={
                    "error": "graph_unavailable",
                    "detail": "Unified LangGraph application is not compiled.",
                },
            )

        try:
            raw: Dict[str, Any] = await request.json()
        except Exception as e:  # pragma: no cover
            logging.exception("Failed to parse JSON body for /copilot/stream")
            span.set_status(Status(StatusCode.ERROR, "invalid_json"))
            return JSONResponse(status_code=400, content={"error": "invalid_json", "detail": str(e)})

        # Unwrap common wrappers
        # - GraphQL-style { query, variables: { input|data } }
        # - Runtime client style { data: { ...payload } }
        try:
            if isinstance(raw, dict):
                if "query" in raw and isinstance(raw.get("variables"), dict):
                    gql_vars = raw.get("variables") or {}
                    gql_input = gql_vars.get("input") or gql_vars.get("data") or {}
                    if isinstance(gql_input, dict) and gql_input:
                        raw = gql_input
                elif "data" in raw and isinstance(raw.get("data"), dict):
                    raw = raw.get("data")
        except Exception:
            pass

        # Normalize common field variants from different CopilotKit clients
        forwarded: Dict[str, Any] = (
            raw.get("forwardedProps")
            or raw.get("forwardedProperties")
            or raw.get("properties")
            or {}
        )

        # Comprehensive logging: Log incoming properties (Phase 1 requirement)
        logging.info(
            "copilot_stream_request_received",
            extra={
                "has_forwarded_props": bool(forwarded),
                "forwarded_keys": list(forwarded.keys()) if isinstance(forwarded, dict) else [],
                "session_id_present": "session_id" in forwarded,
                "trace_id_present": "trace_id" in forwarded,
                "attachments_present": "attachments" in forwarded,
                "attachments_count": len(forwarded.get("attachments", [])) if isinstance(forwarded.get("attachments"), list) else 0,
            },
        )

        thread_id: Optional[str] = raw.get("threadId") or forwarded.get("session_id")
        run_id: str = (
            raw.get("runId")
            or forwarded.get("trace_id")
            or str(uuid4())
        )

        # Populate span attributes with non-PII diagnostics
        try:
            span.set_attribute("copilot.thread_id_present", bool(thread_id))
            span.set_attribute("copilot.run_id_present", bool(run_id))
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

        messages_in = raw.get("messages") or []
        messages: List[Dict[str, Any]] = []
        try:
            for m in messages_in:
                if not isinstance(m, dict):
                    continue
                mid = str(m.get("id") or uuid4())
                # GraphQL-like input: { textMessage: { content, role, ... } }
                if "textMessage" in m and isinstance(m["textMessage"], dict):
                    tm = m["textMessage"]
                    role = str(tm.get("role", "user")).lower()
                    content = tm.get("content", "")
                    messages.append({"id": mid, "role": role, "content": content})
                    continue
                # AG-UI style already: { role, content }
                if "role" in m and "content" in m:
                    role = str(m.get("role", "user")).lower()
                    content = m.get("content", "")
                    messages.append({"id": mid, "role": role, "content": content})
                    continue
                # Image message (best-effort)
                if "imageMessage" in m and isinstance(m["imageMessage"], dict):
                    im = m["imageMessage"]
                    role = str(im.get("role", "user")).lower()
                    messages.append({
                        "id": mid,
                        "role": role,
                        "content": "",
                        "image": {
                            "format": im.get("format", "png"),
                            "bytes": im.get("bytes", ""),
                        }
                    })
                    continue
                # Fallback: ignore unknown shapes
        except Exception:
            # keep messages empty, agent may still handle state-only inputs
            pass

        # Build candidate payload variants to satisfy different SDK expectations
        # Choose best messages representation
        effective_messages = messages if messages else messages_in

        base: Dict[str, Any] = {
            **raw,
            "messages": effective_messages,
            "threadId": thread_id or str(uuid4()),
            "runId": run_id,
        }
        # Remove alternates to control variants explicitly
        base.pop("forwardedProps", None)
        base.pop("forwardedProperties", None)
        base.pop("properties", None)

        # Ensure optional fields exist
        base.setdefault("state", {})
        base.setdefault("tools", [])
        base.setdefault("context", [])

        # Phase 1: Merge CopilotKit context into state and config
        # This ensures feature parity with GraphQL endpoint (SparrowLangGraphAgent)
        state_dict: Dict[str, Any] = base["state"]
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
        configurable.setdefault("thread_id", base["threadId"])
        configurable.setdefault("run_id", run_id)

        messages_payload = base.get("messages") or state_dict.get("messages") or []
        normalized_messages = _normalize_messages(messages_payload)

        graph_state = {
            **state_dict,
            "messages": normalized_messages,
            "forwarded_props": forwarded_without_attachments,
            "scratchpad": state_dict.get("scratchpad") or {},
        }

        graph_state.setdefault("session_id", str(configurable.get("session_id") or base["threadId"]))
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

        if compiled_graph is None:
            span.set_status(Status(StatusCode.ERROR, "graph_not_available"))
            return JSONResponse(
                status_code=503,
                content={
                    "error": "graph_unavailable",
                    "detail": "Unified graph is not compiled",
                },
            )

        async def event_generator():
            final_state: Optional[Dict[str, Any]] = None
            with tracer.start_as_current_span("copilot.stream.run") as run_span:
                cfg = config_dict.get("configurable", {})
                run_span.set_attribute("copilot.session_id", str(cfg.get("session_id") or ""))
                run_span.set_attribute("copilot.trace_id", str(cfg.get("trace_id") or ""))
                run_span.set_attribute("copilot.provider", str(cfg.get("provider") or ""))
                run_span.set_attribute("copilot.model", str(cfg.get("model") or ""))

                try:
                    async for event in compiled_graph.astream_events(graph_state, config=config_dict):
                        event_name = event.get("event")
                        data = event.get("data", {})
                        if event_name == "on_chat_model_stream":
                            delta = _extract_chunk_text(data.get("chunk"))
                            if delta:
                                yield _encode_sse(
                                    {
                                        "type": "assistant-delta",
                                        "threadId": graph_state.get("session_id"),
                                        "runId": run_id,
                                        "delta": delta,
                                    }
                                )
                        elif event_name in {"on_chain_end", "on_graph_end"}:
                            output = data.get("output")
                            if isinstance(output, dict):
                                final_state = output
                    run_span.set_status(Status(StatusCode.OK))
                except Exception as exc:  # pragma: no cover
                    run_span.record_exception(exc)
                    run_span.set_status(Status(StatusCode.ERROR, "agent_run_failed"))
                    raise

            if final_state is None:
                final_state = await compiled_graph.ainvoke(graph_state, config=config_dict)

            messages_out = final_state.get("messages") or []
            if messages_out and not isinstance(messages_out[0], BaseMessage):
                messages_out = _normalize_messages(messages_out)

            if messages_out:
                assistant_msg = messages_out[-1]
                message_payload: Dict[str, Any] = {
                    "type": "assistant-message",
                    "threadId": graph_state.get("session_id"),
                    "runId": run_id,
                    "message": {
                        "role": "assistant",
                        "content": _message_to_text(assistant_msg),
                    },
                }

                metadata: Dict[str, Any] = {}
                additional = getattr(assistant_msg, "additional_kwargs", None)
                if additional:
                    metadata.update(additional)
                response_meta = getattr(assistant_msg, "response_metadata", None)
                if response_meta:
                    metadata["response_metadata"] = response_meta
                if metadata:
                    message_payload["message"]["messageMetadata"] = metadata

                yield _encode_sse(message_payload)

            yield _encode_sse(
                {
                    "type": "finish",
                    "threadId": graph_state.get("session_id"),
                    "runId": run_id,
                    "reason": "stop",
                }
            )

        span.set_status(Status(StatusCode.OK))
        return StreamingResponse(event_generator(), status_code=200, media_type="text/event-stream")


@router.get("/copilot/stream/health")
async def copilot_stream_health():
    """Return availability and configuration snapshot for the Copilot stream path."""
    graph_ok = compiled_graph is not None
    from app.core.settings import settings as _settings
    if not graph_ok:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "sdk_available": True,
                "graph_compiled": graph_ok,
            },
        )
    return {
        "status": "ok",
        "sdk_available": True,
        "graph_compiled": True,
        "agent": "sparrow",
        "agents": [{"name": "sparrow", "status": "ready"}],
        "models": {
            "router": getattr(_settings, "router_model", None),
            "primary": getattr(_settings, "primary_agent_model", None),
            "log_analysis": getattr(_settings, "enhanced_log_model", None),
        },
    }
