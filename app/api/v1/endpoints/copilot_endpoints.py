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


try:  # pragma: no cover - import-time guard
    from ag_ui_langgraph.agent import LangGraphAgent  # type: ignore
    from ag_ui.core.types import (
        RunAgentInput,  # type: ignore
        DeveloperMessage,  # type: ignore
        SystemMessage,  # type: ignore
        AssistantMessage,  # type: ignore
        UserMessage,  # type: ignore
        ToolMessage,  # type: ignore
        Tool as AgentTool,  # type: ignore
        Context as AgentContext,  # type: ignore
        ToolCall as AgentToolCall,  # type: ignore
        FunctionCall as AgentFunctionCall,  # type: ignore
    )
    from ag_ui.encoder import EventEncoder  # type: ignore
    from app.agents.orchestration.orchestration.graph import app as compiled_graph
    _SDK_AVAILABLE = True
except Exception:  # pragma: no cover
    LangGraphAgent = object  # type: ignore
    RunAgentInput = object  # type: ignore
    EventEncoder = object  # type: ignore
    DeveloperMessage = object  # type: ignore
    SystemMessage = object  # type: ignore
    AssistantMessage = object  # type: ignore
    UserMessage = object  # type: ignore
    ToolMessage = object  # type: ignore
    AgentTool = object  # type: ignore
    AgentContext = object  # type: ignore
    AgentToolCall = object  # type: ignore
    AgentFunctionCall = object  # type: ignore
    compiled_graph = None  # type: ignore
    _SDK_AVAILABLE = False

# Import for context merge and attachment validation
from app.agents.orchestration.orchestration.state import Attachment
from app.core.settings import get_settings

# OpenTelemetry tracer for this module
tracer = trace.get_tracer(__name__)


class FallbackRunAgentInput:
    """Lightweight stand-in for RunAgentInput when SDK validation fails."""

    __slots__ = (
        "thread_id",
        "run_id",
        "state",
        "messages",
        "tools",
        "context",
        "forwarded_props",
        "config",
    )

    def __init__(
        self,
        *,
        thread_id: str,
        run_id: str,
        state: Any,
        messages: List[Any],
        tools: List[Any],
        context: List[Any],
        forwarded_props: Dict[str, Any],
        config: Dict[str, Any] | None = None,
    ) -> None:
        self.thread_id = thread_id
        self.run_id = run_id
        self.state = state
        self.messages = messages
        self.tools = tools
        self.context = context
        self.forwarded_props = forwarded_props
        self.config = config or {}

    @staticmethod
    def _build_tool_call(raw_call: Dict[str, Any]) -> Optional[AgentToolCall]:
        if not isinstance(raw_call, dict):
            return None

        function = raw_call.get("function") or {}
        if not isinstance(function, dict):
            function = {}

        name = function.get("name") or raw_call.get("name")
        if not name:
            return None

        arguments = function.get("arguments") or raw_call.get("arguments") or "{}"
        if not isinstance(arguments, str):
            try:
                arguments = json.dumps(arguments)
            except Exception:
                arguments = "{}"

        try:
            return AgentToolCall(
                id=str(raw_call.get("id") or uuid4()),
                function=AgentFunctionCall(name=str(name), arguments=arguments),
            )
        except Exception:
            return None

    @staticmethod
    def _build_message(raw_message: Any) -> Optional[Any]:
        if not isinstance(raw_message, dict):
            return None

        role = str(raw_message.get("role") or "").lower()
        mid = str(raw_message.get("id") or uuid4())
        name = raw_message.get("name")

        if role == "user":
            content = raw_message.get("content", "")
            try:
                return UserMessage(id=mid, content=str(content or ""), name=name)
            except Exception:
                return None

        if role == "assistant":
            content = raw_message.get("content") or ""
            tool_calls_raw = raw_message.get("tool_calls") or raw_message.get("toolCalls") or []
            tool_calls: List[AgentToolCall] = []
            if isinstance(tool_calls_raw, list):
                for call in tool_calls_raw:
                    tc = FallbackRunAgentInput._build_tool_call(call)
                    if tc:
                        tool_calls.append(tc)
            try:
                return AssistantMessage(
                    id=mid,
                    content=str(content),
                    name=name,
                    tool_calls=tool_calls or None,
                )
            except Exception:
                return None

        if role == "developer":
            content = raw_message.get("content", "")
            try:
                return DeveloperMessage(id=mid, content=str(content or ""), name=name)
            except Exception:
                return None

        if role == "system":
            content = raw_message.get("content", "")
            try:
                return SystemMessage(id=mid, content=str(content or ""), name=name)
            except Exception:
                return None

        if role == "tool":
            tool_call_id = raw_message.get("tool_call_id") or raw_message.get("toolCallId")
            content = raw_message.get("content", "")
            if not tool_call_id:
                return None
            try:
                return ToolMessage(
                    id=mid,
                    tool_call_id=str(tool_call_id),
                    content=str(content or ""),
                    error=raw_message.get("error"),
                )
            except Exception:
                return None

        return None

    @staticmethod
    def _build_context(raw: Any) -> Optional[AgentContext]:
        if not isinstance(raw, dict):
            return None
        description = raw.get("description")
        value = raw.get("value")
        if description is None or value is None:
            return None
        try:
            return AgentContext(description=str(description), value=str(value))
        except Exception:
            return None

    @staticmethod
    def _build_tool(raw: Any) -> Optional[AgentTool]:
        if not isinstance(raw, dict):
            return None
        name = raw.get("name")
        description = raw.get("description", "")
        parameters = raw.get("parameters", {})
        if not name:
            return None
        try:
            return AgentTool(name=str(name), description=str(description or ""), parameters=parameters)
        except Exception:
            return None

    @classmethod
    def from_candidate(cls, candidate: Dict[str, Any]) -> "FallbackRunAgentInput":
        forwarded_candidate = candidate.get("forwarded_props")
        if forwarded_candidate is None:
            forwarded_candidate = candidate.get("forwardedProps") or candidate.get("forwardedProperties") or {}
        forwarded_props = forwarded_candidate if isinstance(forwarded_candidate, dict) else {}

        thread_id = str(
            candidate.get("thread_id")
            or candidate.get("threadId")
            or candidate.get("threadID")
            or uuid4()
        )
        run_id = str(
            candidate.get("run_id")
            or candidate.get("runId")
            or candidate.get("runID")
            or uuid4()
        )

        state = candidate.get("state") if isinstance(candidate.get("state"), dict) else {}

        messages: List[Any] = []
        for raw_message in candidate.get("messages") or []:
            built = cls._build_message(raw_message)
            if built is not None:
                messages.append(built)

        tools: List[Any] = []
        for raw_tool in candidate.get("tools") or []:
            built_tool = cls._build_tool(raw_tool)
            if built_tool is not None:
                tools.append(built_tool)

        context_items: List[Any] = []
        for raw_context in candidate.get("context") or []:
            built_context = cls._build_context(raw_context)
            if built_context is not None:
                context_items.append(built_context)

        config = candidate.get("config")
        config_dict = config if isinstance(config, dict) else {}

        return cls(
            thread_id=thread_id,
            run_id=run_id,
            state=state,
            messages=messages,
            tools=tools,
            context=context_items,
            forwarded_props=forwarded_props,
            config=config_dict,
        )

    def copy(self, update: Optional[Dict[str, Any]] = None) -> "FallbackRunAgentInput":
        data: Dict[str, Any] = {
            "thread_id": self.thread_id,
            "run_id": self.run_id,
            "state": deepcopy(self.state),
            "messages": [m.model_copy(deep=True) if hasattr(m, "model_copy") else deepcopy(m) for m in self.messages],
            "tools": [t.model_copy(deep=True) if hasattr(t, "model_copy") else deepcopy(t) for t in self.tools],
            "context": [c.model_copy(deep=True) if hasattr(c, "model_copy") else deepcopy(c) for c in self.context],
            "forwarded_props": deepcopy(self.forwarded_props),
            "config": deepcopy(self.config),
        }
        if update:
            data.update(update)
        return FallbackRunAgentInput(**data)

    def dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "run_id": self.run_id,
            "state": deepcopy(self.state),
            "messages": [
                m.model_dump() if hasattr(m, "model_dump") else deepcopy(m)
                for m in self.messages
            ],
            "tools": [
                t.model_dump() if hasattr(t, "model_dump") else deepcopy(t)
                for t in self.tools
            ],
            "context": [
                c.model_dump() if hasattr(c, "model_dump") else deepcopy(c)
                for c in self.context
            ],
            "forwarded_props": deepcopy(self.forwarded_props),
            "config": deepcopy(self.config),
        }

    model_dump = dict


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
        settings = get_settings()
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
    """Auth-protected CopilotKit streaming endpoint using AG-UI LangGraph adapter.

    Accepts raw JSON from CopilotKit runtime client and normalizes it into RunAgentInput.
    This avoids 422 errors due to minor schema drift (e.g., forwardedProps vs forwardedProperties).
    """
    with tracer.start_as_current_span("copilot.stream") as span:
        if not _SDK_AVAILABLE or compiled_graph is None:
            span.set_status(Status(StatusCode.ERROR, "sdk_or_graph_unavailable"))
            return JSONResponse(
                status_code=501,
                content={
                    "error": "CopilotKit backend SDK not available",
                    "detail": "Install 'copilotkit' (ag_ui_langgraph) and ensure the primary graph compiles.",
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
        # - Runtime client style { data: { ...RunAgentInput } }
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

        # Update base with merged state and add config
        base["state"] = state_dict
        base["config"] = config_dict

        # Phase 1: Use forwarded props WITHOUT attachments (attachments are in state now)
        variants: List[Dict[str, Any]] = []
        # 1) forwardedProps as dict (without attachments - already in state)
        variants.append({**base, "forwardedProps": forwarded_without_attachments})
        # 2) forwardedProps as JSON string
        try:
            variants.append({**base, "forwardedProps": json.dumps(forwarded_without_attachments)})
        except Exception:
            variants.append({**base, "forwardedProps": json.dumps({})})
        # 3) forwardedProperties as dict
        variants.append({**base, "forwardedProperties": forwarded_without_attachments})
        # 4) forwardedProperties as JSON string
        try:
            variants.append({**base, "forwardedProperties": json.dumps(forwarded_without_attachments)})
        except Exception:
            variants.append({**base, "forwardedProperties": json.dumps({})})

        logging.info(
            "copilot_stream_normalized_attempts",
            extra={
                "attempts": len(variants),
                "has_messages": isinstance(messages, list),
                "messages_len": len(messages) if isinstance(messages, list) else None,
                "thread_present": bool(thread_id),
                "run_present": bool(run_id),
            },
        )

        input_data = None
        errors: List[str] = []
        for idx, candidate in enumerate(variants):
            try:
                candidate_payload = dict(candidate)
                candidate_payload.pop("config", None)
                if hasattr(RunAgentInput, "model_validate"):
                    input_data = RunAgentInput.model_validate(candidate_payload)  # type: ignore[attr-defined]
                elif hasattr(RunAgentInput, "parse_obj"):
                    input_data = RunAgentInput.parse_obj(candidate_payload)  # type: ignore[attr-defined]
                else:
                    input_data = RunAgentInput(**candidate_payload)  # type: ignore[call-arg]
                break
            except Exception as e:  # collect and try next variant
                try:
                    # pydantic v2 ValidationError has .errors()
                    errs = getattr(e, "errors", lambda: [])()
                    errors.append(f"variant_{idx}: {str(errs) or str(e)}")
                except Exception:
                    errors.append(f"variant_{idx}: {str(e)}")

    if input_data is None:
        logging.warning(
            "RunAgentInput validation failed. Falling back to permissive namespace.",
            extra={"errors_sample": errors[:3]},
        )
        # As a last resort, try duck-typing with SimpleNamespace or plain dict
        for idx, candidate in enumerate(variants):
            try:
                fallback_candidate = FallbackRunAgentInput.from_candidate(candidate)
            except Exception as e:
                errors.append(f"namespace_variant_{idx}: {str(e)}")
                continue

            try:
                if hasattr(RunAgentInput, "model_validate") and callable(getattr(RunAgentInput, "model_validate")):
                    fallback_payload = fallback_candidate.dict()
                    fallback_payload.pop("config", None)
                    input_data = RunAgentInput.model_validate(fallback_payload)  # type: ignore[attr-defined]
                elif hasattr(RunAgentInput, "parse_obj"):
                    fallback_payload = fallback_candidate.dict()
                    fallback_payload.pop("config", None)
                    input_data = RunAgentInput.parse_obj(fallback_payload)  # type: ignore[attr-defined]
                else:
                    input_data = fallback_candidate  # Final fallback when SDK model not available
                break
            except Exception as e:
                errors.append(f"namespace_variant_{idx}: {str(e)}")
                # Accept permissive fallback even if strict validation failed
                input_data = fallback_candidate
                break

        if input_data is None:
            logging.error(
                "RunAgentInput validation failed for all variants",
                extra={
                    "errors": errors[:3],
                    "raw_keys": list(raw.keys()) if isinstance(raw, dict) else None,
                },
            )
            span.set_status(Status(StatusCode.ERROR, "validation_failed"))
            return JSONResponse(
                status_code=422,
                content={
                    "error": "validation_failed",
                    "detail": "All normalization variants failed",
                    "variants_tried": len(variants),
                    "errors": errors,
                },
            )

    agent = LangGraphAgent(name="sparrow", graph=compiled_graph, config=config_dict)  # type: ignore
    accept_header = request.headers.get("accept")
    encoder = EventEncoder(accept=accept_header)  # type: ignore

    async def event_generator():
        # Nested span around the actual agent run (streaming)
        with tracer.start_as_current_span("copilot.stream.run") as run_span:
            try:
                # Repeat key attributes for easier correlation at run-level
                cfg = config_dict.get("configurable", {})
                run_span.set_attribute("copilot.session_id", str(cfg.get("session_id") or ""))
                run_span.set_attribute("copilot.trace_id", str(cfg.get("trace_id") or ""))
                run_span.set_attribute("copilot.provider", str(cfg.get("provider") or ""))
                run_span.set_attribute("copilot.model", str(cfg.get("model") or ""))
                run_span.set_attribute("copilot.agent_type", str(cfg.get("agent_type") or ""))
            except Exception:
                pass

            try:
                async for event in agent.run(input_data):  # type: ignore
                    yield encoder.encode(event)
                run_span.set_status(Status(StatusCode.OK))
            except Exception as exc:  # pragma: no cover - defensive capture
                run_span.record_exception(exc)
                run_span.set_status(Status(StatusCode.ERROR, "agent_run_failed"))
                raise

    span.set_status(Status(StatusCode.OK))
    # Explicitly set 200 to avoid ambiguous 204 responses in some clients
    return StreamingResponse(
        event_generator(), status_code=200, media_type=encoder.get_content_type()
    )  # type: ignore


@router.get("/copilot/stream/health")
async def copilot_stream_health():
    """Return availability and configuration snapshot for the Copilot stream path."""
    sdk = bool(_SDK_AVAILABLE)
    graph_ok = compiled_graph is not None
    from app.core.settings import settings as _settings
    if not sdk or not graph_ok:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "sdk_available": sdk,
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
