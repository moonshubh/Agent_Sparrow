from __future__ import annotations

"""
CopilotKit Remote Endpoint (AG-UI LangGraph)

Exposes `/api/v1/copilot/stream` as an auth-protected POST streaming endpoint
compatible with CopilotKit's runtime client. Uses the official `ag_ui_langgraph`
adapter to wrap our compiled LangGraph graph.
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

    variants: List[Dict[str, Any]] = []
    # 1) forwardedProps as dict
    variants.append({**base, "forwardedProps": forwarded})
    # 2) forwardedProps as JSON string
    try:
        variants.append({**base, "forwardedProps": json.dumps(forwarded)})
    except Exception:
        variants.append({**base, "forwardedProps": json.dumps({})})
    # 3) forwardedProperties as dict
    variants.append({**base, "forwardedProperties": forwarded})
    # 4) forwardedProperties as JSON string
    try:
        variants.append({**base, "forwardedProperties": json.dumps(forwarded)})
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
