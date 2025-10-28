from __future__ import annotations

"""
CopilotKit Remote Endpoint (AG-UI LangGraph)

Exposes `/api/v1/copilot/stream` as an auth-protected POST streaming endpoint
compatible with CopilotKit's runtime client. Uses the official `ag_ui_langgraph`
adapter to wrap our compiled LangGraph graph.
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse

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
async def copilot_stream(input_data: "RunAgentInput", request: Request, user_id: str = Depends(get_current_user_id)):
    """Auth-protected CopilotKit streaming endpoint using AG-UI LangGraph adapter."""
    if not _SDK_AVAILABLE or compiled_graph is None:
        return JSONResponse(
            status_code=501,
            content={
                "error": "CopilotKit backend SDK not available",
                "detail": "Install 'copilotkit' (ag_ui_langgraph) and ensure the primary graph compiles.",
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
