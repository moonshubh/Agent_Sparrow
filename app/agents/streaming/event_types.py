"""Typed event dataclasses for AG-UI streaming events.

These types define the contract between the backend agent and frontend UI
for all custom events emitted during agent execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional


@dataclass
class TraceStep:
    """A single step in the agent's thinking trace.

    Represents either a thought (model reasoning), action (tool call),
    or result (tool output or final response).
    """

    id: str
    timestamp: str
    type: Literal["thought", "action", "result"]
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        step_id: str,
        step_type: Literal["thought", "action", "result"],
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "TraceStep":
        """Factory method to create a TraceStep with current timestamp."""
        return cls(
            id=step_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            type=step_type,
            content=content,
            metadata=metadata or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "type": self.type,
            "content": self.content,
            "metadata": _safe_metadata(self.metadata),
        }


@dataclass
class TimelineOperation:
    """An operation in the agent timeline.

    Operations form a tree structure representing the agent's execution:
    - Root: The main agent execution
    - Children: Tool calls, thoughts, and todos
    """

    id: str
    type: Literal["agent", "tool", "thought", "todo"]
    name: str
    status: Literal["pending", "running", "success", "error"]
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration: Optional[int] = None  # milliseconds
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create_root(cls, root_id: str, name: str = "Unified Agent", **metadata: Any) -> "TimelineOperation":
        """Create the root agent operation."""
        return cls(
            id=root_id,
            type="agent",
            name=name,
            status="running",
            start_time=datetime.now(timezone.utc).isoformat(),
            metadata=metadata,
        )

    @classmethod
    def create_tool(
        cls,
        tool_call_id: str,
        tool_name: str,
        parent_id: str,
        **metadata: Any,
    ) -> "TimelineOperation":
        """Create a tool operation."""
        return cls(
            id=tool_call_id,
            type="tool",
            name=tool_name,
            status="running",
            parent=parent_id,
            start_time=datetime.now(timezone.utc).isoformat(),
            metadata={"toolName": tool_name, **metadata},
        )

    @classmethod
    def create_thought(
        cls,
        run_id: str,
        parent_id: str,
        model: Optional[str] = None,
    ) -> "TimelineOperation":
        """Create a thought/reasoning operation."""
        return cls(
            id=run_id,
            type="thought",
            name="Thinking",
            status="running",
            parent=parent_id,
            start_time=datetime.now(timezone.utc).isoformat(),
            metadata={"model": model} if model else {},
        )

    @classmethod
    def create_todo(
        cls,
        todo_id: str,
        title: str,
        parent_id: str,
        status: str = "pending",
        todo_data: Optional[Dict[str, Any]] = None,
    ) -> "TimelineOperation":
        """Create a todo operation."""
        op_status: Literal["pending", "running", "success", "error"] = "pending"
        if status == "in_progress":
            op_status = "running"
        elif status == "done":
            op_status = "success"

        return cls(
            id=todo_id,
            type="todo",
            name=title,
            status=op_status,
            parent=parent_id,
            metadata={"todo": todo_data or {}},
        )

    def complete(self, success: bool = True) -> None:
        """Mark operation as completed and calculate duration."""
        now = datetime.now(timezone.utc)
        self.end_time = now.isoformat()
        self.status = "success" if success else "error"

        if self.start_time:
            try:
                start_dt = datetime.fromisoformat(self.start_time)
                self.duration = int((now - start_dt).total_seconds() * 1000)
            except Exception:
                pass

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        result: Dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "status": self.status,
            "children": list(self.children),
        }
        if self.parent:
            result["parent"] = self.parent
        if self.start_time:
            result["startTime"] = self.start_time
        if self.end_time:
            result["endTime"] = self.end_time
        if self.duration is not None:
            result["duration"] = self.duration
        if self.metadata:
            result["metadata"] = _safe_metadata(self.metadata)
        return result


@dataclass
class TodoItem:
    """A single todo item."""

    id: str
    title: str
    status: Literal["pending", "in_progress", "done"]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "metadata": _safe_metadata(self.metadata),
        }


@dataclass
class AgentThinkingTraceEvent:
    """Event payload for agent_thinking_trace custom event.

    Sent to update the thinking trace sidebar with model reasoning steps.
    """

    total_steps: int
    thinking_trace: Optional[List[TraceStep]] = None
    latest_step: Optional[TraceStep] = None
    active_step_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-safe dictionary with camelCase keys."""
        result: Dict[str, Any] = {"totalSteps": self.total_steps}

        if self.thinking_trace is not None:
            result["thinkingTrace"] = [step.to_dict() for step in self.thinking_trace]
        if self.latest_step is not None:
            result["latestStep"] = self.latest_step.to_dict()
        if self.active_step_id is not None:
            result["activeStepId"] = self.active_step_id

        return result


@dataclass
class AgentTimelineUpdateEvent:
    """Event payload for agent_timeline_update custom event.

    Sent to update the agentic timeline visualization.
    """

    operations: List[TimelineOperation]
    current_operation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-safe dictionary with camelCase keys."""
        result: Dict[str, Any] = {
            "operations": [op.to_dict() for op in self.operations],
        }
        if self.current_operation_id is not None:
            result["currentOperationId"] = self.current_operation_id
        return result


@dataclass
class ToolEvidenceUpdateEvent:
    """Event payload for tool_evidence_update custom event.

    Sent to surface tool output and evidence in the Tool Evidence sidebar.
    """

    tool_call_id: str
    tool_name: str
    output: Any
    summary: Optional[str] = None
    cards: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-safe dictionary with camelCase keys."""
        result: Dict[str, Any] = {
            "toolCallId": self.tool_call_id,
            "toolName": self.tool_name,
            "output": _safe_json_value(self.output),
            "cards": self.cards,
        }
        if self.summary is not None:
            result["summary"] = self.summary
        return result


@dataclass
class AgentTodosUpdateEvent:
    """Event payload for agent_todos_update custom event.

    Sent to update the task/todo list in the Run Tasks sidebar.
    """

    todos: List[TodoItem]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        return {"todos": [todo.to_dict() for todo in self.todos]}


# Utility functions

def _safe_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all metadata values are JSON-serializable."""
    import json

    safe: Dict[str, Any] = {}
    for key, value in metadata.items():
        try:
            json.dumps(value)
            safe[key] = value
        except TypeError:
            safe[key] = str(value)
    return safe


def _safe_json_value(value: Any) -> Any:
    """Convert a value to be JSON-serializable."""
    import json

    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        if isinstance(value, str):
            trimmed = value.strip()
            if (trimmed.startswith("{") and trimmed.endswith("}")) or (
                trimmed.startswith("[") and trimmed.endswith("]")
            ):
                try:
                    parsed = json.loads(trimmed)
                    json.dumps(parsed, ensure_ascii=False)
                    return parsed
                except Exception:
                    return value
            return value
        return str(value)
