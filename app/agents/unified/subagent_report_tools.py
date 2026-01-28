"""Internal tools for coordinating subagent report ingestion.

These tools are not meant to be called by end users directly. They exist so
middleware can deterministically update GraphState without relying on the model
to follow prompt instructions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, tool
from langgraph.types import Command
from pydantic import BaseModel, Field

try:  # pragma: no cover - optional dependency / version compatibility
    # Canonical ToolRuntime type used elsewhere in the codebase.
    from langgraph.prebuilt import ToolRuntime  # type: ignore
except Exception:  # pragma: no cover
    ToolRuntime = Any  # type: ignore


class MarkSubagentReportsReadInput(BaseModel):
    """Input schema for mark_subagent_reports_read."""

    report_tool_call_ids: List[str] = Field(
        default_factory=list,
        description="Tool call ids for `task` runs whose workspace reports were read.",
    )


def create_mark_subagent_reports_read_tool() -> BaseTool:
    """Create a tool that marks subagent reports as read in scratchpad."""

    @tool(args_schema=MarkSubagentReportsReadInput)
    async def mark_subagent_reports_read(
        report_tool_call_ids: List[str],
        runtime: ToolRuntime | None = None,
    ) -> Command:
        """Mark one or more subagent reports as read.

        This tool updates `scratchpad._system.subagent_reports[*].read = true` to
        prevent repeated forced ingestion of the same reports.
        """
        now = datetime.now(timezone.utc).isoformat()
        valid_ids = [
            tool_call_id
            for tool_call_id in report_tool_call_ids
            if isinstance(tool_call_id, str) and tool_call_id
        ]
        updates: Dict[str, Any] = {
            "scratchpad": {
                "_system": {
                    "subagent_reports": {
                        tool_call_id: {"read": True, "read_at": now}
                        for tool_call_id in valid_ids
                    }
                }
            }
        }

        tool_call_id = (
            str(getattr(runtime, "tool_call_id", "")).strip()
            if runtime is not None
            else ""
        ) or "mark_subagent_reports_read"
        message = ToolMessage(
            content=f"Marked {len(valid_ids)} subagent report(s) as read.",
            tool_call_id=tool_call_id,
        )
        return Command(update={**updates, "messages": [message]})

    return mark_subagent_reports_read
