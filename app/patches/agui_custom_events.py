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
from ag_ui_langgraph.agent import LangGraphAgent
from ag_ui_langgraph.types import LangGraphEventTypes, State
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

    output = data.get("output")
    tool_name = event.get("name") or data.get("name") or "tool"

    if isinstance(output, ToolMessage):
        if not getattr(output, "name", None):
            normalized = dict(data)
            normalized["output"] = ToolMessage(
                content=str(getattr(output, "content", "") or ""),
                tool_call_id=str(getattr(output, "tool_call_id", "") or "unknown"),
                name=str(tool_name),
            )
            updated = dict(event)
            updated["data"] = normalized
            return updated
        return event

    if isinstance(output, Command):
        try:
            update_payload = getattr(output, "update", None)
            if isinstance(update_payload, dict) and isinstance(update_payload.get("messages"), list):
                changed = False
                new_messages: list[Any] = []
                for msg in update_payload.get("messages") or []:
                    if isinstance(msg, ToolMessage) and not getattr(msg, "name", None):
                        changed = True
                        new_messages.append(
                            ToolMessage(
                                content=str(getattr(msg, "content", "") or ""),
                                tool_call_id=str(getattr(msg, "tool_call_id", "") or "unknown"),
                                name=str(tool_name),
                            )
                        )
                    else:
                        new_messages.append(msg)
                if changed:
                    normalized = dict(data)
                    normalized["output"] = Command(
                        update={
                            **update_payload,
                            "messages": new_messages,
                        }
                    )
                    updated = dict(event)
                    updated["data"] = normalized
                    return updated
        except Exception:
            return event
        return event

    if isinstance(output, list) and output and all(isinstance(item, ToolMessage) for item in output):
        normalized_messages: list[ToolMessage] = []
        for msg in output:
            if not getattr(msg, "name", None):
                normalized_messages.append(
                    ToolMessage(
                        content=str(getattr(msg, "content", "") or ""),
                        tool_call_id=str(getattr(msg, "tool_call_id", "") or "unknown"),
                        name=str(tool_name),
                    )
                )
            else:
                normalized_messages.append(msg)

        normalized = dict(data)
        normalized["output"] = Command(update={"messages": normalized_messages})
        updated = dict(event)
        updated["data"] = normalized
        return updated

    tool_call_id = data.get("tool_call_id") or data.get("id") or "unknown"
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
        kwargs = original(self, input, subgraphs=subgraphs, version=version, config=config, context=context, fork=fork)
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
            if isinstance(chunk, dict) and chunk.get("event") == LangGraphEventTypes.OnCustomEvent.value:
                yield self._dispatch_event(
                    CustomEvent(
                        type=EventType.CUSTOM,
                        name=chunk.get("name"),
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
