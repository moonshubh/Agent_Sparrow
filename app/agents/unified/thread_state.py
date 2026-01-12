from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import BaseMessage, ToolMessage
from pydantic import BaseModel, ConfigDict, Field


class ThreadDecision(BaseModel):
    decision: str
    made_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(extra="ignore")


class ThreadState(BaseModel):
    one_line_status: str = Field(default="")
    user_intent: str | None = None
    progress_so_far: str | None = None
    constraints: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    active_todos: list[str] = Field(default_factory=list)
    decisions: list[ThreadDecision] = Field(default_factory=list)
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(extra="ignore")

    def to_prompt(self) -> str:
        lines: list[str] = ["Thread State (compressed truth)"]

        if self.one_line_status.strip():
            lines.append(f"Status: {self.one_line_status.strip()}")
        if self.user_intent and self.user_intent.strip():
            lines.append(f"User intent: {self.user_intent.strip()}")
        if self.progress_so_far and self.progress_so_far.strip():
            lines.append(f"Progress so far: {self.progress_so_far.strip()}")
        if self.constraints:
            lines.append("Constraints:")
            for constraint in self.constraints[:8]:
                if str(constraint).strip():
                    lines.append(f"- {str(constraint).strip()}")
        if self.next_steps:
            lines.append("Next steps:")
            for step in self.next_steps[:5]:
                if str(step).strip():
                    lines.append(f"- {str(step).strip()}")
        if self.active_todos:
            lines.append("Active todos:")
            for todo in self.active_todos[:10]:
                if str(todo).strip():
                    lines.append(f"- {str(todo).strip()}")
        if self.decisions:
            lines.append("Key decisions:")
            for d in self.decisions[:8]:
                if d.decision.strip():
                    lines.append(f"- {d.decision.strip()}")

        return "\n".join(lines).strip() + "\n"


def map_workspace_handoff_to_thread_state(handoff: dict[str, Any]) -> ThreadState:
    summary = str(handoff.get("summary") or "").strip()
    user_intent: str | None = None
    progress_so_far: str | None = None

    if summary.lower().startswith("user request:"):
        remainder = summary.split(":", 1)[1].strip()
        first_line, sep, rest = remainder.partition("\n")
        user_intent = first_line.strip() or None
        progress_so_far = rest.strip() if sep else None
    else:
        first_line, sep, rest = summary.partition("\n")
        user_intent = first_line.strip() or None
        progress_so_far = rest.strip() if sep else None

    next_steps: list[str] = []
    raw_next_steps = handoff.get("next_steps")
    if isinstance(raw_next_steps, list):
        next_steps = [str(s).strip() for s in raw_next_steps if str(s).strip()]

    active_todos: list[str] = []
    raw_todos = handoff.get("active_todos")
    if isinstance(raw_todos, list):
        for item in raw_todos:
            if isinstance(item, dict):
                content = str(item.get("content") or "").strip()
                status = str(item.get("status") or "").strip()
                if content:
                    prefix = f"[{status}]" if status else ""
                    active_todos.append(f"{prefix} {content}".strip())
            elif isinstance(item, str) and item.strip():
                active_todos.append(item.strip())

    decisions: list[ThreadDecision] = []
    raw_decisions = handoff.get("key_decisions")
    if isinstance(raw_decisions, list):
        for item in raw_decisions:
            if isinstance(item, str) and item.strip():
                decisions.append(ThreadDecision(decision=item.strip()))
            elif isinstance(item, dict):
                decision = str(item.get("decision") or "").strip()
                if decision:
                    decisions.append(ThreadDecision(decision=decision))

    one_line_status = "Resuming: " + (user_intent or "previous context")
    if next_steps:
        one_line_status += f" (next: {next_steps[0]})"

    return ThreadState(
        one_line_status=one_line_status,
        user_intent=user_intent,
        progress_so_far=progress_so_far,
        next_steps=next_steps,
        active_todos=active_todos,
        decisions=decisions,
        last_updated_at=datetime.now(timezone.utc),
    )


def compute_tool_burst_signature(messages: list[BaseMessage]) -> str:
    trailing: list[ToolMessage] = []
    for msg in reversed(messages or []):
        if isinstance(msg, ToolMessage):
            trailing.append(msg)
            continue
        break

    if not trailing:
        return ""

    parts: list[str] = []
    for msg in reversed(trailing):
        name = str(getattr(msg, "name", "") or "")
        tool_call_id = str(getattr(msg, "tool_call_id", "") or "")
        content = str(getattr(msg, "content", "") or "")
        parts.append(f"{name}:{tool_call_id}:{len(content)}")

    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return digest
