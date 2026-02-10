"""Helpers for extracting and routing pending `task` tool calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage

from .state import GraphState

SUBAGENT_TO_SUBGRAPH: Dict[str, str] = {
    "research-agent": "research",
    "log-diagnoser": "log_analysis",
    "db-retrieval": "db_retrieval",
    "draft-writer": "draft_writer",
    "data-analyst": "data_analyst",
}


@dataclass(frozen=True)
class PendingTaskCall:
    """Normalized task call payload extracted from the last AI message."""

    tool_call_id: str
    subagent_type: str
    description: str
    args: Dict[str, Any]



def _extract_tool_calls(message: AIMessage) -> List[Dict[str, Any]]:
    tool_calls = getattr(message, "tool_calls", None)
    if isinstance(tool_calls, list):
        return [tc for tc in tool_calls if isinstance(tc, dict)]

    additional = getattr(message, "additional_kwargs", {}) or {}
    fallback = additional.get("tool_calls")
    if isinstance(fallback, list):
        return [tc for tc in fallback if isinstance(tc, dict)]

    return []



def _extract_description(args: Dict[str, Any]) -> str:
    for key in ("description", "prompt", "task"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""



def resolve_subgraph_key(subagent_type: str) -> Optional[str]:
    """Return the subgraph key for a subagent type, if supported."""
    return SUBAGENT_TO_SUBGRAPH.get((subagent_type or "").strip())



def extract_pending_task_calls(state: GraphState) -> List[PendingTaskCall]:
    """Extract pending `task` calls from the latest assistant message."""
    messages = getattr(state, "messages", []) or []
    if not messages:
        return []

    last = messages[-1]
    if not isinstance(last, AIMessage):
        return []

    scratchpad = getattr(state, "scratchpad", {}) or {}
    system_bucket = scratchpad.get("_system", {}) if isinstance(scratchpad, dict) else {}
    executed_ids = set(system_bucket.get("_executed_tool_calls") or [])

    pending: List[PendingTaskCall] = []
    for tool_call in _extract_tool_calls(last):
        if tool_call.get("name") != "task":
            continue

        tool_call_id = tool_call.get("id")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            continue
        if tool_call_id in executed_ids:
            continue

        args = tool_call.get("args") or tool_call.get("arguments") or {}
        if not isinstance(args, dict):
            continue

        subagent_type = args.get("subagent_type") or args.get("subagentType")
        if not isinstance(subagent_type, str) or not subagent_type.strip():
            continue

        description = _extract_description(args)
        if not description:
            continue

        pending.append(
            PendingTaskCall(
                tool_call_id=tool_call_id,
                subagent_type=subagent_type.strip(),
                description=description,
                args=args,
            )
        )

    return pending



def has_routable_pending_task_calls(state: GraphState) -> bool:
    """Return True when at least one pending task call maps to a subgraph."""
    for call in extract_pending_task_calls(state):
        if resolve_subgraph_key(call.subagent_type):
            return True
    return False
