"""Shared execution helpers for orchestration subgraphs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, cast

from langchain.agents import create_agent
from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from loguru import logger

from app.agents.orchestration.orchestration.subagent_state import PendingTaskCall
from app.agents.orchestration.orchestration.state import GraphState
from app.agents.unified.subagents import get_subagent_by_name


async def _emit_custom_event(
    stream_writer: Any,
    *,
    name: str,
    data: Dict[str, Any],
    config: Any,
) -> None:
    # AG-UI consumes graph events through `astream_events`; this dispatches a
    # first-class custom event that survives the adapter pipeline.
    try:
        await adispatch_custom_event(name, data, config=config)
        return
    except Exception as exc:  # pragma: no cover - fallback path
        logger.debug(
            "subgraph_custom_event_dispatch_failed", name=name, error=str(exc)
        )

    if stream_writer is None:
        return

    payload = {
        "event": "on_custom_event",
        "name": name,
        "data": data,
    }
    try:
        if callable(stream_writer):
            stream_writer(payload)
        elif hasattr(stream_writer, "write"):
            stream_writer.write(payload)
    except Exception as exc:  # pragma: no cover - best effort
        logger.debug("subgraph_custom_event_failed", name=name, error=str(exc))


def _coerce_last_message_text(result: Any) -> str:
    if isinstance(result, BaseMessage):
        content = getattr(result, "content", "")
        return content if isinstance(content, str) else str(content)

    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            content = getattr(last, "content", "") if isinstance(last, BaseMessage) else ""
            if isinstance(content, str):
                return content
        output = result.get("output")
        if isinstance(output, BaseMessage):
            content = getattr(output, "content", "")
            return content if isinstance(content, str) else str(content)
        if isinstance(output, str):
            return output

    return str(result)


def _build_subagent_state(parent_state: GraphState, call: PendingTaskCall) -> Dict[str, Any]:
    forwarded_props = getattr(parent_state, "forwarded_props", {}) or {}
    scratchpad = getattr(parent_state, "scratchpad", {}) or {}
    system_bucket = scratchpad.get("_system", {}) if isinstance(scratchpad, dict) else {}

    return {
        "session_id": getattr(parent_state, "session_id", None),
        "trace_id": getattr(parent_state, "trace_id", None),
        "user_id": getattr(parent_state, "user_id", None),
        "provider": getattr(parent_state, "provider", None),
        "model": getattr(parent_state, "model", None),
        "agent_type": getattr(parent_state, "agent_type", None),
        "use_server_memory": getattr(parent_state, "use_server_memory", False),
        "thread_state": getattr(parent_state, "thread_state", None),
        "forwarded_props": forwarded_props,
        "scratchpad": {"_system": system_bucket},
        "subagent_context": {
            "type": call.subagent_type,
            "tool_call_id": call.tool_call_id,
            "source": "langgraph_subgraph",
        },
        "messages": [HumanMessage(content=call.description)],
    }


def build_subagent_runner(
    *,
    subagent_name: str,
    subgraph_name: str,
) -> Callable[[GraphState, PendingTaskCall, Any, Any], Awaitable[ToolMessage]]:
    """Build a subgraph runner that executes one subagent task call."""

    async def _run(
        state: GraphState,
        call: PendingTaskCall,
        stream_writer: Any,
        config: Any,
    ) -> ToolMessage:
        logger.info(
            "subgraph_subagent_start",
            session_id=getattr(state, "session_id", None),
            subgraph=subgraph_name,
            subagent_type=call.subagent_type,
            tool_call_id=call.tool_call_id,
        )
        await _emit_custom_event(
            stream_writer,
            name="subagent_spawn",
            data={
                "subagentType": call.subagent_type,
                "toolCallId": call.tool_call_id,
                "task": call.description[:500],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            config=config,
        )

        await _emit_custom_event(
            stream_writer,
            name="subagent_thinking_delta",
            data={
                "subagentType": call.subagent_type,
                "toolCallId": call.tool_call_id,
                "delta": f"Routing to subgraph `{subgraph_name}`...",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            config=config,
        )

        status = "error"
        output_text = ""
        try:
            subagent_spec = get_subagent_by_name(subagent_name)
            if not subagent_spec:
                output_text = (
                    f"Subagent '{subagent_name}' is not configured in the current runtime."
                )
            else:
                model_value = subagent_spec.get("model")
                if not isinstance(model_value, (str, BaseChatModel)):
                    output_text = (
                        f"Subagent '{subagent_name}' has an invalid model configuration."
                    )
                else:
                    subagent_agent: Any = create_agent(
                        model=model_value,
                        tools=subagent_spec.get("tools") or [],
                        system_prompt=subagent_spec.get("system_prompt") or "",
                        middleware=subagent_spec.get("middleware") or [],
                    )
                    result = await cast(Any, subagent_agent).ainvoke(
                        cast(Any, _build_subagent_state(state, call)),
                        config=config,
                    )
                    output_text = _coerce_last_message_text(result).strip()
                    if not output_text:
                        output_text = "Subagent completed with no textual output."
                    status = "success"
        except Exception as exc:
            output_text = f"Subagent execution failed: {str(exc)[:800]}"
            logger.warning(
                "subgraph_subagent_execution_failed",
                subagent=subagent_name,
                tool_call_id=call.tool_call_id,
                error=str(exc),
            )

        await _emit_custom_event(
            stream_writer,
            name="subagent_end",
            data={
                "subagentType": call.subagent_type,
                "toolCallId": call.tool_call_id,
                "status": status,
                "reportPath": f"/scratch/subgraphs/{call.subagent_type}/{call.tool_call_id}",
                "excerpt": output_text[:500],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            config=config,
        )

        logger.info(
            "subgraph_subagent_end",
            session_id=getattr(state, "session_id", None),
            subgraph=subgraph_name,
            subagent_type=call.subagent_type,
            tool_call_id=call.tool_call_id,
            status=status,
        )

        return ToolMessage(
            content=output_text,
            tool_call_id=call.tool_call_id,
            name="task",
        )

    return _run
