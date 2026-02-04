"""
Runtime monkey patch for ag_ui_langgraph to ensure:
- stream_mode defaults to \"custom\" so writer-emitted events are not lost.
- on_chain_stream chunks that wrap LangGraph on_custom_event are converted to AG-UI CustomEvent.

This keeps the behavior stable even if the site-packages file is overwritten (e.g., reinstall).
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, AsyncGenerator

from ag_ui.core.events import CustomEvent, EventType
from ag_ui_langgraph.agent import LangGraphAgent  # type: ignore[import-untyped]
from ag_ui_langgraph.types import LangGraphEventTypes, State  # type: ignore[import-untyped]
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.patches.agui_json_safe import make_json_safe_with_cycle_detection

_PATCH_FLAG = "_agui_custom_event_patch_applied"
_PATCH_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


def _sanitize_event_for_json(event: Any) -> Any:
    """Ensure event['data']['input'] is JSON-serializable before AG-UI processing.

    This prevents "Object of type HumanMessage is not JSON serializable" errors
    originating from ag_ui_langgraph.agent._handle_single_event when it calls
    json.dumps(event["data"]["input"]).
    """
    try:
        if not isinstance(event, dict):
            return event

        data = event.get("data")
        if not isinstance(data, dict):
            return event

        if "input" not in data:
            return event

        safe_event = dict(event)
        safe_data = dict(data)
        safe_data["input"] = make_json_safe_with_cycle_detection(safe_data["input"])
        safe_event["data"] = safe_data
        return safe_event
    except Exception:
        # Never break the stream due to sanitization issues; log for diagnostics.
        logger.exception("Failed to sanitize AG-UI event for JSON", exc_info=True)
        return event


def _normalize_tool_end_output(event: Any) -> Any:
    """Ensure on_tool_end outputs are ToolMessage/Command for AG-UI compatibility."""
    if not isinstance(event, dict):
        return event

    if event.get("event") != LangGraphEventTypes.OnToolEnd:
        return event

    data = event.get("data")
    if not isinstance(data, dict):
        return event

    def _coerce_tool_name(value: Any) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return "tool"

    def _ensure_tool_message_name(tool_msg: ToolMessage, fallback: str) -> ToolMessage:
        name = getattr(tool_msg, "name", None)
        if isinstance(name, str) and name.strip():
            return tool_msg
        try:
            return tool_msg.model_copy(update={"name": fallback})
        except Exception:
            return ToolMessage(
                content=tool_msg.content,
                tool_call_id=str(getattr(tool_msg, "tool_call_id", "") or ""),
                name=fallback,
                id=getattr(tool_msg, "id", None),
                additional_kwargs=getattr(tool_msg, "additional_kwargs", {}) or {},
                response_metadata=getattr(tool_msg, "response_metadata", {}) or {},
                artifact=getattr(tool_msg, "artifact", None),
                status=getattr(tool_msg, "status", "success") or "success",
            )

    fallback_tool_name = _coerce_tool_name(event.get("name") or data.get("name"))

    output = data.get("output")
    if isinstance(output, (ToolMessage, Command)):
        if isinstance(output, ToolMessage):
            updated_tool_msg = _ensure_tool_message_name(output, fallback_tool_name)
            if updated_tool_msg is output:
                return event
            normalized = dict(data)
            normalized["output"] = updated_tool_msg
            updated = dict(event)
            updated["data"] = normalized
            return updated

        # Command output - ensure any ToolMessages have a valid name.
        try:
            update = getattr(output, "update", None)
            if isinstance(update, dict):
                messages = update.get("messages")
                if isinstance(messages, list):
                    changed = False
                    normalized_messages = []
                    for msg in messages:
                        if isinstance(msg, ToolMessage):
                            normalized_msg = _ensure_tool_message_name(
                                msg, fallback_tool_name
                            )
                            changed = changed or (normalized_msg is not msg)
                            normalized_messages.append(normalized_msg)
                        else:
                            normalized_messages.append(msg)
                    if not changed:
                        return event

                    new_update = dict(update)
                    new_update["messages"] = normalized_messages
                    normalized = dict(data)
                    normalized["output"] = Command(
                        graph=getattr(output, "graph", None),
                        update=new_update,
                        resume=getattr(output, "resume", None),
                        goto=getattr(output, "goto", ()),
                    )
                    updated = dict(event)
                    updated["data"] = normalized
                    return updated
        except Exception:
            # Fall back to leaving the event as-is; downstream will handle failures.
            return event

    if (
        isinstance(output, list)
        and output
        and all(isinstance(item, ToolMessage) for item in output)
    ):
        output = [
            _ensure_tool_message_name(item, fallback_tool_name) for item in output
        ]
        normalized = dict(data)
        normalized["output"] = Command(update={"messages": output})
        updated = dict(event)
        updated["data"] = normalized
        return updated

    tool_call_id = data.get("tool_call_id") or data.get("id") or "unknown"
    tool_name = fallback_tool_name
    safe_output = make_json_safe_with_cycle_detection(output)

    if isinstance(safe_output, str):
        content = safe_output
    else:
        try:
            content = json.dumps(safe_output, ensure_ascii=False, default=str)
        except Exception:
            content = str(safe_output)

    normalized = dict(data)
    normalized["output"] = ToolMessage(
        content=content,
        tool_call_id=str(tool_call_id),
        name=str(tool_name),
    )
    updated = dict(event)
    updated["data"] = normalized
    return updated


def _patch_get_stream_kwargs() -> None:
    original = LangGraphAgent.get_stream_kwargs

    def patched_get_stream_kwargs(
        self: LangGraphAgent,
        input: Any,
        subgraphs: bool = False,
        version: str = "v2",
        config: Any = None,
        context: Any = None,
        fork: Any = None,
    ):
        kwargs = original(
            self,
            input,
            subgraphs=subgraphs,
            version=version,
            config=config,
            context=context,
            fork=fork,
        )
        # Ensure writer-emitted custom events propagate (appear as on_chain_stream with chunk.event == on_custom_event)
        kwargs.setdefault("stream_mode", "custom")
        return kwargs

    LangGraphAgent.get_stream_kwargs = patched_get_stream_kwargs  # type: ignore[assignment]


def _patch_handle_single_event() -> None:
    original = LangGraphAgent._handle_single_event

    async def patched_handle_single_event(
        self: LangGraphAgent, event: Any, state: State
    ) -> AsyncGenerator[str, None]:
        # Normalize event payloads so that any nested HumanMessage or other
        # complex objects under data["input"] are JSON-safe before the original
        # handler attempts json.dumps on them.
        safe_event = _normalize_tool_end_output(_sanitize_event_for_json(event))

        # Detect writer-emitted custom events coming through custom stream_mode.
        if safe_event.get("event") == LangGraphEventTypes.OnChainStream:
            chunk = safe_event.get("data", {}).get("chunk")
            if (
                isinstance(chunk, dict)
                and chunk.get("event") == LangGraphEventTypes.OnCustomEvent.value
            ):
                name = chunk.get("name")
                event_name = name if isinstance(name, str) and name else "custom_event"
                yield self._dispatch_event(
                    CustomEvent(
                        type=EventType.CUSTOM,
                        name=event_name,
                        value=chunk.get("data"),
                        raw_event=safe_event,
                    )
                )
                return

        async for ev in original(self, safe_event, state):
            yield ev

    LangGraphAgent._handle_single_event = patched_handle_single_event  # type: ignore[assignment]


def _patch_messages_in_process_contract() -> None:
    """Prevent ag_ui_langgraph crashes when `messages_in_process[run_id]` is None.

    ag_ui_langgraph sets `messages_in_process[run_id] = None` after emitting certain
    end events (e.g. TOOL_CALL_END / TEXT_MESSAGE_END). Some models then emit
    additional stream events for the same run_id, and the library's
    `set_message_in_progress()` attempts `**current_message_in_progress`, which
    raises `TypeError: 'NoneType' object is not a mapping`.

    We treat None/non-dicts as an empty dict so streaming can continue.
    """

    def patched_set_message_in_progress(
        self: LangGraphAgent, run_id: str, data: Any
    ) -> None:
        record = getattr(self, "messages_in_process", None)
        if not isinstance(record, dict):
            record = {}
            setattr(self, "messages_in_process", record)

        current = record.get(run_id)
        if not isinstance(current, dict):
            current = {}
        if not isinstance(data, dict):
            data = {}
        record[run_id] = {
            **current,
            **data,
        }

    LangGraphAgent.set_message_in_progress = patched_set_message_in_progress  # type: ignore[assignment]


def apply_patch() -> None:
    """Idempotent patch application."""
    if getattr(LangGraphAgent, _PATCH_FLAG, False):
        return

    with _PATCH_LOCK:
        if getattr(LangGraphAgent, _PATCH_FLAG, False):
            return
        try:
            _patch_get_stream_kwargs()
            _patch_handle_single_event()
            _patch_messages_in_process_contract()
        except Exception:
            logger.exception("Failed to apply AG-UI custom event patch")
            raise
        setattr(LangGraphAgent, _PATCH_FLAG, True)
        logger.info("AG-UI custom event patch applied")


# Apply eagerly on import (FastAPI/uvicorn startup)
apply_patch()
