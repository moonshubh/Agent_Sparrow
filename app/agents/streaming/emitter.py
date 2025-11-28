"""Centralized AG-UI event emission with state tracking.

Extracted from agent_sparrow.py to provide a clean interface for
emitting custom events to the AG-UI frontend.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from loguru import logger

from .event_types import (
    AgentThinkingTraceEvent,
    AgentTimelineUpdateEvent,
    AgentTodosUpdateEvent,
    TimelineOperation,
    TodoItem,
    ToolEvidenceUpdateEvent,
    TraceStep,
)
from .normalizers import normalize_todos


class StreamEventEmitter:
    """Centralized AG-UI event emission with state tracking.

    This class manages all state related to the agent timeline, thinking trace,
    and todos, and provides methods for emitting properly typed events to the
    AG-UI frontend via the LangGraph stream writer.

    Usage:
        emitter = StreamEventEmitter(writer, root_id="trace-123")
        emitter.start_root_operation(provider="google", model="gemini-2.5-flash")

        # Tool execution
        emitter.start_tool(tool_call_id, tool_name)
        emitter.end_tool(tool_call_id, output)

        # Thinking
        emitter.start_thought(run_id, model="gemini-2.5-flash")
        emitter.end_thought(run_id, content="...")

        # Todos
        emitter.update_todos(raw_todos)
    """

    def __init__(
        self,
        writer: Optional[Callable[[Dict[str, Any]], None]],
        root_id: Optional[str] = None,
    ):
        """Initialize the emitter.

        Args:
            writer: LangGraph stream writer function, or None for no-op mode.
            root_id: Root operation ID (defaults to timestamp-based ID).
        """
        self.writer = writer
        self.root_id = root_id or f"run-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        # State tracking
        self.operations: Dict[str, TimelineOperation] = {}
        self.thinking_trace: List[TraceStep] = []
        self.trace_step_aliases: Dict[str, TraceStep] = {}
        self.todo_items: List[TodoItem] = []
        self.todo_operation_ids: Set[str] = set()

        # Counters
        self._trace_step_counter = itertools.count(1)

    # -------------------------------------------------------------------------
    # Low-level emission
    # -------------------------------------------------------------------------

    def emit_custom_event(self, name: str, payload: Dict[str, Any]) -> None:
        """Emit a custom AG-UI event."""
        if self.writer is None:
            return
        self.writer({
            "event": "on_custom_event",
            "name": name,
            "data": payload,
        })

    def emit_tool_call_start(self, tool_call_id: str, tool_name: str) -> None:
        """Emit TOOL_CALL_START event."""
        if self.writer is None:
            return
        self.writer({
            "type": "TOOL_CALL_START",
            "toolCallId": tool_call_id,
            "toolCallName": tool_name,
        })

    def emit_tool_call_end(
        self,
        tool_call_id: str,
        tool_name: str,
        result: Optional[str] = None,
    ) -> None:
        """Emit TOOL_CALL_END event."""
        if self.writer is None:
            return
        self.writer({
            "type": "TOOL_CALL_END",
            "toolCallId": tool_call_id,
            "toolCallName": tool_name,
            "result": result,
        })

    def emit_genui_state(self, data: Dict[str, Any]) -> None:
        """Emit GenUI state update via CUSTOM event."""
        if self.writer is None or not data:
            return
        self.writer({
            "type": "CUSTOM",
            "name": "genui_state_update",
            "value": data,
        })

    # -------------------------------------------------------------------------
    # Text message emission (AG-UI protocol)
    # -------------------------------------------------------------------------

    def start_text_message(self, message_id: Optional[str] = None) -> str:
        """Emit TEXT_MESSAGE_START event.

        Returns:
            The message_id used for the message.
        """
        if message_id is None:
            message_id = f"msg-{self.root_id}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"

        self._current_message_id = message_id
        self._message_started = True

        if self.writer is not None:
            self.writer({
                "type": "TEXT_MESSAGE_START",
                "messageId": message_id,
                "role": "assistant",
            })
        return message_id

    def emit_text_content(self, delta: str) -> None:
        """Emit TEXT_MESSAGE_CONTENT event with streaming text delta.

        Args:
            delta: The text chunk to emit.
        """
        if self.writer is None or not delta:
            logger.debug(f"emit_text_content skipped: writer={self.writer is not None}, delta={bool(delta)}")
            return

        # Ensure message is started
        if not getattr(self, '_message_started', False):
            logger.info("emit_text_content: Starting new text message")
            self.start_text_message()

        event = {
            "type": "TEXT_MESSAGE_CONTENT",
            "messageId": getattr(self, '_current_message_id', self.root_id),
            "delta": delta,
        }
        logger.info(f"emit_text_content: Emitting event with delta length={len(delta)}")
        self.writer(event)

    def end_text_message(self) -> None:
        """Emit TEXT_MESSAGE_END event."""
        if self.writer is None:
            return

        message_id = getattr(self, '_current_message_id', self.root_id)
        self._message_started = False

        self.writer({
            "type": "TEXT_MESSAGE_END",
            "messageId": message_id,
        })

    # -------------------------------------------------------------------------
    # Timeline operations
    # -------------------------------------------------------------------------

    def start_root_operation(
        self,
        name: str = "Unified Agent",
        **metadata: Any,
    ) -> TimelineOperation:
        """Initialize the root agent operation."""
        root_op = TimelineOperation.create_root(
            root_id=self.root_id,
            name=name,
            **metadata,
        )
        self.operations[self.root_id] = root_op
        self._emit_timeline_update(self.root_id)
        return root_op

    def start_tool(
        self,
        tool_call_id: str,
        tool_name: str,
        input_data: Optional[Any] = None,
    ) -> TimelineOperation:
        """Record a tool operation starting."""
        tool_op = self.operations.get(tool_call_id)
        if tool_op is None:
            tool_op = TimelineOperation.create_tool(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                parent_id=self.root_id,
            )
            self.operations[tool_call_id] = tool_op
            self._add_to_parent(tool_call_id)

        # Emit events
        self._emit_timeline_update(tool_call_id)
        self.emit_tool_call_start(tool_call_id, tool_name)

        # Add trace step
        trace_meta: Dict[str, Any] = {
            "toolCallId": tool_call_id,
            "toolName": tool_name,
        }
        if input_data is not None:
            from .event_types import _safe_json_value
            trace_meta["input"] = _safe_json_value(input_data)

        self.add_trace_step(
            step_type="action",
            content=f"Executing {tool_name}",
            metadata=trace_meta,
        )

        return tool_op

    def end_tool(
        self,
        tool_call_id: str,
        tool_name: str,
        output: Any,
        summary: Optional[str] = None,
        cards: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Record a tool operation completing."""
        from .event_types import _safe_json_value

        tool_op = self.operations.get(tool_call_id)
        if tool_op is None:
            # Create if missing
            tool_op = TimelineOperation.create_tool(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                parent_id=self.root_id,
            )
            self.operations[tool_call_id] = tool_op

        # Complete the operation
        tool_op.complete(success=True)

        # Add output preview to metadata
        safe_output = _safe_json_value(output) if output is not None else None
        if safe_output is not None:
            tool_op.metadata["rawOutputPreview"] = str(safe_output)[:1000]

        # Emit events
        self._emit_timeline_update(tool_call_id)
        # Use explicit None check to preserve falsy but valid outputs (0, False, "")
        self.emit_tool_call_end(
            tool_call_id, tool_name, str(output) if output is not None else None
        )

        # Emit tool evidence with cards
        self.emit_custom_event(
            "tool_evidence_update",
            ToolEvidenceUpdateEvent(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                output=safe_output,
                summary=summary,
                cards=cards or [],
            ).to_dict(),
        )

        # Add trace step
        result_meta: Dict[str, Any] = {
            "toolCallId": tool_call_id,
            "toolName": tool_name,
        }
        if safe_output is not None:
            result_meta["output"] = safe_output
        if tool_op.duration is not None:
            result_meta["durationMs"] = tool_op.duration

        self.add_trace_step(
            step_type="result",
            content=f"{tool_name} completed",
            metadata=result_meta,
        )

    def error_tool(
        self,
        tool_call_id: str,
        tool_name: str,
        error: Any,
    ) -> None:
        """Record a tool operation failing."""
        tool_op = self.operations.get(tool_call_id)
        if tool_op:
            tool_op.complete(success=False)
            tool_op.metadata["error"] = str(error)

        self._emit_timeline_update(tool_call_id)

        # Emit error event
        self.emit_custom_event(
            "tool_error",
            {
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "error": str(error),
            },
        )

        # Add trace step
        self.add_trace_step(
            step_type="result",
            content=f"{tool_name} failed",
            metadata={"toolCallId": tool_call_id, "error": str(error)},
        )

        logger.error("Tool error", tool_name=tool_name, tool_call_id=tool_call_id, error=error)

    def start_thought(
        self,
        run_id: str,
        model: Optional[str] = None,
        prompt_preview: Optional[str] = None,
    ) -> TimelineOperation:
        """Record a thought/reasoning operation starting."""
        thought_op = TimelineOperation.create_thought(
            run_id=run_id,
            parent_id=self.root_id,
            model=model,
        )
        self.operations[run_id] = thought_op
        self._add_to_parent(run_id)

        self._emit_timeline_update(run_id)

        # Add trace step
        thinking_meta: Dict[str, Any] = {}
        if model:
            thinking_meta["model"] = model
        if prompt_preview:
            thinking_meta["promptPreview"] = prompt_preview[:600]

        self.add_trace_step(
            step_type="thought",
            content="Model reasoning",
            metadata=thinking_meta,
            alias=str(run_id),
        )

        return thought_op

    def end_thought(
        self,
        run_id: str,
        content: Optional[str] = None,
    ) -> None:
        """Record a thought/reasoning operation completing."""
        thought_op = self.operations.get(run_id)
        if thought_op:
            thought_op.complete(success=True)
            if content:
                thought_op.metadata["content"] = str(content)

        self._emit_timeline_update(run_id)

        # Update trace step
        self.update_trace_step(
            alias=str(run_id),
            metadata={"finalOutput": content} if content else None,
            finalize=True,
        )

    def stream_thought_chunk(self, run_id: str, chunk_text: str) -> None:
        """Append streaming content to a thought trace step."""
        if not chunk_text:
            return

        updated = self.update_trace_step(str(run_id), append_content=chunk_text)
        if updated is None:
            # Create if missing
            self.add_trace_step(
                step_type="thought",
                content=chunk_text,
                alias=str(run_id),
            )

    def complete_root(self) -> None:
        """Mark the root operation as completed."""
        root_op = self.operations.get(self.root_id)
        if root_op and root_op.end_time is None:
            root_op.complete(success=True)
            self._emit_timeline_update(self.root_id)

    # -------------------------------------------------------------------------
    # Thinking trace
    # -------------------------------------------------------------------------

    def add_trace_step(
        self,
        step_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        alias: Optional[str] = None,
    ) -> TraceStep:
        """Add a new step to the thinking trace."""
        step = TraceStep.create(
            step_id=f"{self.root_id}-trace-{next(self._trace_step_counter)}",
            step_type=step_type,  # type: ignore
            content=content,
            metadata=metadata,
        )
        self.thinking_trace.append(step)

        if alias:
            self.trace_step_aliases[alias] = step

        self._emit_thinking_trace(step)
        return step

    def update_trace_step(
        self,
        alias: str,
        append_content: Optional[str] = None,
        replace_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        step_type: Optional[str] = None,
        finalize: bool = False,
    ) -> Optional[TraceStep]:
        """Update an existing trace step by alias."""
        step = self.trace_step_aliases.get(alias)
        if step is None:
            return None

        if append_content:
            step.content = f"{step.content}{append_content}"
        if replace_content is not None:
            step.content = replace_content
        if metadata:
            step.metadata.update(metadata)
        if step_type:
            step.type = step_type  # type: ignore

        step.timestamp = datetime.now(timezone.utc).isoformat()

        self._emit_thinking_trace(step)

        if finalize:
            self.trace_step_aliases.pop(alias, None)

        return step

    # -------------------------------------------------------------------------
    # Todos
    # -------------------------------------------------------------------------

    def update_todos(self, raw_todos: Any) -> List[TodoItem]:
        """Update the todo list from raw tool output."""
        from .event_types import _safe_json_value

        # Debug logging to understand the raw_todos structure
        raw_type = type(raw_todos).__name__
        raw_repr_str = repr(raw_todos)[:500] if raw_todos else "None"
        logger.info(
            f"write_todos_debug: type={raw_type}, repr={raw_repr_str}"
        )

        normalized = normalize_todos(raw_todos, self.root_id)
        if not normalized:
            logger.info(f"write_todos_no_new_items: prior_count={len(self.todo_items)}, raw_type={raw_type}")
            # Emit current state even if no changes
            self._sync_todo_operations()
            self._emit_todos()
            return self.todo_items

        logger.info(
            "write_todos_normalized",
            normalized_count=len(normalized),
            todos=_safe_json_value(normalized),
        )

        # Convert to TodoItem objects
        self.todo_items.clear()
        for todo_dict in normalized:
            self.todo_items.append(TodoItem(
                id=todo_dict["id"],
                title=todo_dict["title"],
                status=todo_dict["status"],  # type: ignore
                metadata=todo_dict.get("metadata", {}),
            ))

        # Update timeline and emit events
        self._sync_todo_operations()
        self._emit_todos()

        return self.todo_items

    def get_todos_as_dicts(self) -> List[Dict[str, Any]]:
        """Get todos as list of dicts for state storage."""
        return [todo.to_dict() for todo in self.todo_items]

    def start_next_todo(self) -> bool:
        """Mark the next pending todo as in_progress."""
        for todo in self.todo_items:
            status = (todo.status or "pending").lower()  # type: ignore[attr-defined]
            if status == "pending":
                todo.status = "in_progress"  # type: ignore[attr-defined]
                self._sync_todo_operations()
                self._emit_todos()
                return True
        return False

    def complete_active_todo(self) -> bool:
        """Mark the first in-progress todo as done."""
        for todo in self.todo_items:
            status = (todo.status or "pending").lower()  # type: ignore[attr-defined]
            if status == "in_progress":
                todo.status = "done"  # type: ignore[attr-defined]
                self._sync_todo_operations()
                self._emit_todos()
                return True
        return False

    def mark_all_todos_done(self) -> None:
        """Mark all todos as done and emit updates."""
        if not self.todo_items:
            return

        changed = False
        for todo in self.todo_items:
            if (todo.status or "pending").lower() != "done":  # type: ignore[attr-defined]
                todo.status = "done"  # type: ignore[attr-defined]
                changed = True

        if changed:
            self._sync_todo_operations()
            self._emit_todos()

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _add_to_parent(self, child_id: str) -> None:
        """Add a child operation to the root parent."""
        parent_op = self.operations.get(self.root_id)
        if parent_op is not None and child_id not in parent_op.children:
            parent_op.children.append(child_id)

    def _emit_timeline_update(self, current_op_id: Optional[str] = None) -> None:
        """Emit a timeline update event."""
        self.emit_custom_event(
            "agent_timeline_update",
            AgentTimelineUpdateEvent(
                operations=list(self.operations.values()),
                current_operation_id=current_op_id,
            ).to_dict(),
        )

    def _emit_thinking_trace(
        self,
        step: Optional[TraceStep] = None,
    ) -> None:
        """Emit a thinking trace update event with the full trace for deterministic UI sync."""
        payload = AgentThinkingTraceEvent(
            total_steps=len(self.thinking_trace),
            thinking_trace=self.thinking_trace,
            latest_step=step,
            active_step_id=step.id if step else (
                self.thinking_trace[-1].id if self.thinking_trace else None
            ),
        )
        self.emit_custom_event("agent_thinking_trace", payload.to_dict())

    def _emit_todos(self) -> None:
        """Emit a todos update event."""
        self.emit_custom_event(
            "agent_todos_update",
            AgentTodosUpdateEvent(todos=self.todo_items).to_dict(),
        )
        logger.info(
            "agent_todos_update_emit",
            todo_count=len(self.todo_items),
        )

    def _sync_todo_operations(self) -> None:
        """Sync todo items to timeline operations."""
        # Remove old todo operations
        for tid in list(self.todo_operation_ids):
            self.operations.pop(tid, None)

        # Remove from parent children
        parent_op = self.operations.get(self.root_id)
        if parent_op is not None:
            parent_op.children = [c for c in parent_op.children if c not in self.todo_operation_ids]

        self.todo_operation_ids.clear()

        # Create new todo operations
        for idx, todo in enumerate(self.todo_items):
            op_id = f"{self.root_id}-todo-{idx + 1}"
            status = (todo.status or "pending").lower()  # type: ignore[attr-defined]
            op = TimelineOperation.create_todo(
                todo_id=op_id,
                title=todo.title,
                parent_id=self.root_id,
                status=status,
                todo_data=todo.to_dict(),
            )
            self.operations[op_id] = op
            self.todo_operation_ids.add(op_id)

            if parent_op is not None and op_id not in parent_op.children:
                parent_op.children.append(op_id)

        self._emit_timeline_update()
