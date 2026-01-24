"""Workspace write sandbox middleware for subagent runs.

Enforces that subagents may only write/append within their run directory:
`/scratch/subagents/{subagent_type}/{task_tool_call_id}/...`

This mirrors Claude Code SDK's deterministic tool gating (PreToolUse-like).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from langchain_core.messages import ToolMessage
from loguru import logger

try:  # pragma: no cover - optional dependency
    from langchain.agents.middleware import AgentMiddleware
    from langchain.agents.middleware.types import ToolCallRequest
    MIDDLEWARE_AVAILABLE = True
except Exception:  # pragma: no cover
    AgentMiddleware = object  # type: ignore[assignment]
    ToolCallRequest = object  # type: ignore[assignment]
    MIDDLEWARE_AVAILABLE = False


_WRITE_TOOL_NAMES = {"write_workspace_file", "append_workspace_file"}


def _normalize_path(path: str) -> str:
    normalized = (path or "").replace("\\", "/").strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized.rstrip("/")


def _get_run_dir(state: Any) -> str | None:
    if state is None:
        return None
    if isinstance(state, dict):
        ctx = state.get("subagent_context") or {}
    else:
        ctx = getattr(state, "subagent_context", None) or {}
    if isinstance(ctx, dict):
        run_dir = ctx.get("run_dir")
        return str(run_dir) if isinstance(run_dir, str) and run_dir else None
    return None


class WorkspaceWriteSandboxMiddleware(AgentMiddleware if MIDDLEWARE_AVAILABLE else object):
    """Restrict subagent workspace writes to their run directory."""

    @property
    def name(self) -> str:  # pragma: no cover - trivial
        return "workspace_write_sandbox"

    async def awrap_tool_call(  # type: ignore[override]
        self,
        request: "ToolCallRequest",
        handler: Callable[["ToolCallRequest"], Awaitable[Any]],
    ) -> Any:
        tool_call = getattr(request, "tool_call", None) or {}
        tool_name = tool_call.get("name")
        if tool_name not in _WRITE_TOOL_NAMES:
            return await handler(request)

        args = tool_call.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        path = args.get("path") if isinstance(args.get("path"), str) else ""
        run_dir = _get_run_dir(getattr(request, "state", None))

        if not run_dir:
            logger.warning("workspace_write_sandbox_missing_run_dir", tool_name=tool_name)
            return ToolMessage(
                content="Workspace write blocked: run directory missing for subagent.",
                tool_call_id=tool_call.get("id"),
            )

        normalized_path = _normalize_path(path)
        normalized_run_dir = _normalize_path(run_dir)
        if normalized_path == normalized_run_dir or normalized_path.startswith(normalized_run_dir + "/"):
            return await handler(request)

        logger.warning(
            "workspace_write_sandbox_blocked",
            tool_name=tool_name,
            path=normalized_path,
            run_dir=normalized_run_dir,
        )
        return ToolMessage(
            content=(
                "Workspace write blocked: subagents may only write within "
                f"{normalized_run_dir}/..."
            ),
            tool_call_id=tool_call.get("id"),
        )

    def wrap_tool_call(  # type: ignore[override]
        self,
        request: "ToolCallRequest",
        handler: Callable[["ToolCallRequest"], Any],
    ) -> Any:
        tool_call = getattr(request, "tool_call", None) or {}
        tool_name = tool_call.get("name")
        if tool_name not in _WRITE_TOOL_NAMES:
            return handler(request)

        args = tool_call.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        path = args.get("path") if isinstance(args.get("path"), str) else ""
        run_dir = _get_run_dir(getattr(request, "state", None))

        if not run_dir:
            logger.warning("workspace_write_sandbox_missing_run_dir", tool_name=tool_name)
            return ToolMessage(
                content="Workspace write blocked: run directory missing for subagent.",
                tool_call_id=tool_call.get("id"),
            )

        normalized_path = _normalize_path(path)
        normalized_run_dir = _normalize_path(run_dir)
        if normalized_path == normalized_run_dir or normalized_path.startswith(normalized_run_dir + "/"):
            return handler(request)

        logger.warning(
            "workspace_write_sandbox_blocked",
            tool_name=tool_name,
            path=normalized_path,
            run_dir=normalized_run_dir,
        )
        return ToolMessage(
            content=(
                "Workspace write blocked: subagents may only write within "
                f"{normalized_run_dir}/..."
            ),
            tool_call_id=tool_call.get("id"),
        )

