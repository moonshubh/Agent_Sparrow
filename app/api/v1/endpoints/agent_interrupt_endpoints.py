from __future__ import annotations

import uuid
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.agents import agent_graph

router = APIRouter()


def _to_serializable(value: Any) -> Any:
    """Best-effort conversion of LangGraph objects into JSON-friendly payloads."""
    if value is None:
        return None
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        try:
            return value.model_dump()
        except Exception:
            pass
    if hasattr(value, "dict") and callable(getattr(value, "dict")):
        try:
            return value.dict()
        except Exception:
            pass
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return {k: _to_serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_serializable(v) for v in value]
    return value


def _require_agent_graph() -> Any:
    if agent_graph is None:
        raise HTTPException(
            status_code=503,
            detail="Agent graph unavailable; install optional dependencies.",
        )
    return agent_graph


class HumanDecisionPayload(BaseModel):
    """Payload describing a supervisor decision for resuming an interrupt."""

    type: Literal["accept", "ignore", "response", "edit"] = Field(
        description="Decision made by the supervisor."
    )
    message: Optional[str] = Field(
        default=None,
        description="Optional free-form message supplied with the decision.",
    )
    action: Optional[str] = Field(
        default=None,
        description="Action identifier when applying an edit decision.",
    )
    args: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured arguments for edit decisions.",
    )


class GraphRunRequest(BaseModel):
    """Request to start or resume an orchestration graph run."""

    query: Optional[str] = Field(
        default=None,
        description="User query to initiate a new graph run.",
    )
    log_content: Optional[str] = Field(
        default=None,
        description="Optional log transcript attached to the query.",
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="Thread identifier used for checkpointing/resume. Generated when omitted.",
    )
    resume: Optional[HumanDecisionPayload] = Field(
        default=None,
        description="Supervisor decision to resume an interrupted thread.",
    )


class GraphRunResponse(BaseModel):
    """Response describing the graph state after executing a step."""

    thread_id: str = Field(description="Thread identifier associated with the run.")
    status: Literal["completed", "interrupted"] = Field(
        description="Execution outcome indicating whether an interrupt is pending."
    )
    state: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Serialized view of the latest graph state.",
    )
    interrupts: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Pending interrupts that require supervisor input.",
    )


def _decision_to_human_response(decision: HumanDecisionPayload) -> Dict[str, Any]:
    """Convert API payload into the LangGraph HumanResponse structure."""
    decision_type = decision.type
    if decision_type == "response":
        message = (decision.message or "").strip()
        return {"type": "response", "args": message}
    if decision_type == "ignore":
        return {"type": "ignore", "args": None}
    if decision_type == "edit":
        action_request = {
            "action": decision.action or "manual_edit",
            "args": decision.args or {},
        }
        return {"type": "edit", "args": action_request}
    # accept is the default fallthrough
    return {"type": "accept", "args": None}


async def _run_graph_step(
    run_input: Any,
    *,
    config: Dict[str, Any],
) -> tuple[Dict[str, Any] | None, List[Dict[str, Any]] | None]:
    """Execute the graph until completion or interrupt."""
    interrupts: List[Dict[str, Any]] | None = None
    graph = _require_agent_graph()
    async for event in graph.astream(run_input, config=config, stream_mode="values"):
        if "__interrupt__" in event:
            raw_interrupts = event["__interrupt__"]
            interrupts = _to_serializable(raw_interrupts) or []
            break
    snapshot = await graph.aget_state(config)
    state_view = _to_serializable(snapshot.values) if snapshot else None
    return state_view, interrupts


@router.post("/v2/agent/graph/run", response_model=GraphRunResponse)
async def run_graph(request: GraphRunRequest) -> GraphRunResponse:
    """Execute a graph step, returning pending interrupts if supervision is required."""
    if request.resume is None and not request.query:
        raise HTTPException(
            status_code=400,
            detail="Provide a query to start a run or a resume payload to continue one.",
        )

    thread_id = request.thread_id or f"thread-{uuid.uuid4().hex}"
    config = {"configurable": {"thread_id": thread_id}}

    run_input: Command[Any] | Dict[str, Any]
    if request.resume:
        human_response = _decision_to_human_response(request.resume)
        run_input = Command(resume=[human_response])
    else:
        run_input = {
            "messages": [HumanMessage(content=request.query or "")],
            "raw_log_content": request.log_content,
        }

    state_view, interrupts = await _run_graph_step(run_input, config=config)

    status: Literal["completed", "interrupted"] = "completed"
    if interrupts:
        status = "interrupted"

    return GraphRunResponse(
        thread_id=thread_id,
        status=status,
        state=state_view if isinstance(state_view, dict) else {"state": state_view},
        interrupts=interrupts or None,
    )


class GraphStateResponse(BaseModel):
    """Current snapshot for a graph thread."""

    thread_id: str = Field(
        description="Thread identifier associated with the snapshot."
    )
    state: Optional[Dict[str, Any]] = Field(
        default=None, description="Serialized state values stored in the checkpoint."
    )
    interrupts: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Pending interrupts awaiting supervisor action."
    )


@router.get("/v2/agent/graph/threads/{thread_id}", response_model=GraphStateResponse)
async def get_graph_state(thread_id: str) -> GraphStateResponse:
    """Return the latest checkpointed state for a thread."""
    config = {"configurable": {"thread_id": thread_id}}
    graph = _require_agent_graph()
    snapshot = await graph.aget_state(config)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Thread not found.")
    interrupts = _to_serializable(snapshot.interrupts) if snapshot.interrupts else None
    state_view = _to_serializable(snapshot.values)
    return GraphStateResponse(
        thread_id=thread_id,
        state=state_view if isinstance(state_view, dict) else {"state": state_view},
        interrupts=interrupts or None,
    )
