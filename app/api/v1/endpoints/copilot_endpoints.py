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
from typing import Any, Dict, List, Optional
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse
from types import SimpleNamespace

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
    from ag_ui.core.types import RunAgentInput  # type: ignore
    from ag_ui.encoder import EventEncoder  # type: ignore
    from app.agents.orchestration.orchestration.graph import app as compiled_graph
    _SDK_AVAILABLE = True
except Exception:  # pragma: no cover
    LangGraphAgent = object  # type: ignore
    RunAgentInput = object  # type: ignore
    EventEncoder = object  # type: ignore
    compiled_graph = None  # type: ignore
    _SDK_AVAILABLE = False

# Import for context merge and attachment validation
from app.agents.orchestration.orchestration.state import Attachment
from app.core.settings import get_settings


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
    if not _SDK_AVAILABLE or compiled_graph is None:
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
            if hasattr(RunAgentInput, "model_validate"):
                input_data = RunAgentInput.model_validate(candidate)  # type: ignore[attr-defined]
            elif hasattr(RunAgentInput, "parse_obj"):
                input_data = RunAgentInput.parse_obj(candidate)  # type: ignore[attr-defined]
            else:
                input_data = RunAgentInput(**candidate)  # type: ignore[call-arg]
            break
        except Exception as e:  # collect and try next variant
            try:
                # pydantic v2 ValidationError has .errors()
                errs = getattr(e, "errors", lambda: [])()
                errors.append(f"variant_{idx}: {str(errs) or str(e)}")
            except Exception:
                errors.append(f"variant_{idx}: {str(e)}")

    if input_data is None:
        # As a last resort, try duck-typing with SimpleNamespace or plain dict
        for idx, candidate in enumerate(variants):
            try:
                input_data = SimpleNamespace(**candidate)  # attribute-style access
                break
            except Exception as e:
                errors.append(f"namespace_variant_{idx}: {str(e)}")

    if input_data is None:
        logging.error(
            "RunAgentInput validation failed for all variants",
            extra={
                "errors": errors[:3],
                "raw_keys": list(raw.keys()) if isinstance(raw, dict) else None,
            },
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_failed",
                "detail": "All normalization variants failed",
                "variants_tried": len(variants),
                "errors": errors,
            },
        )

    agent = LangGraphAgent(name="sparrow", graph=compiled_graph)  # type: ignore
    accept_header = request.headers.get("accept")
    encoder = EventEncoder(accept=accept_header)  # type: ignore

    async def event_generator():
        async for event in agent.run(input_data):  # type: ignore
            yield encoder.encode(event)

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())  # type: ignore


@router.get("/copilot/stream/health")
async def copilot_stream_health():
    if not _SDK_AVAILABLE or compiled_graph is None:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok", "agent": "sparrow"}
