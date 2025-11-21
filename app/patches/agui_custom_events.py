"""
Runtime monkey patch for ag_ui_langgraph to ensure:
- stream_mode defaults to \"custom\" so writer-emitted events are not lost.
- on_chain_stream chunks that wrap LangGraph on_custom_event are converted to AG-UI CustomEvent.

This keeps the behavior stable even if the site-packages file is overwritten (e.g., reinstall).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, AsyncGenerator

from ag_ui.core.events import CustomEvent, EventType
from ag_ui_langgraph.agent import LangGraphAgent
from ag_ui_langgraph.types import LangGraphEventTypes, State


_PATCH_FLAG = "_agui_custom_event_patch_applied"
_PATCH_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


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
        # Detect writer-emitted custom events coming through custom stream_mode.
        if event.get("event") == LangGraphEventTypes.OnChainStream:
            chunk = event.get("data", {}).get("chunk")
            if isinstance(chunk, dict) and chunk.get("event") == LangGraphEventTypes.OnCustomEvent.value:
                yield self._dispatch_event(
                    CustomEvent(
                        type=EventType.CUSTOM,
                        name=chunk.get("name"),
                        value=chunk.get("data"),
                        raw_event=event,
                    )
                )
                return

        async for ev in original(self, event, state):
            yield ev

    LangGraphAgent._handle_single_event = patched_handle_single_event  # type: ignore[assignment]


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
        except Exception:
            logger.exception("Failed to apply AG-UI custom event patch")
            raise
        setattr(LangGraphAgent, _PATCH_FLAG, True)
        logger.info("AG-UI custom event patch applied")


# Apply eagerly on import (FastAPI/uvicorn startup)
apply_patch()
