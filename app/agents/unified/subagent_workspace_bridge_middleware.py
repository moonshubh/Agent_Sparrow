"""DeepAgents `task` enhancements for Claude Code–style subagent runs.

Phase 1 goals:
- Inject a compact "context capsule" into every `task` invocation deterministically
  (without relying on prompt-following).
- Persist full subagent reports to the session workspace.
- Keep the main thread lean by returning a pointer + excerpt instead of the full report.
- Deterministically ingest (read) subagent reports before the coordinator continues.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, TYPE_CHECKING
from uuid import uuid4

from langchain_core.messages import AIMessage, ToolMessage
from loguru import logger

from app.security.pii_redactor import redact_sensitive_from_dict

try:  # pragma: no cover - optional dependency
    from langgraph.types import Command as LangGraphCommand
except Exception:  # pragma: no cover
    LangGraphCommand = None  # type: ignore[assignment]

try:
    from langchain.agents.middleware import AgentMiddleware
    from langchain.agents.middleware.types import ModelRequest, ModelResponse, ToolCallRequest
    MIDDLEWARE_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    AgentMiddleware = object  # type: ignore[assignment]
    ModelRequest = object  # type: ignore[assignment]
    ModelResponse = object  # type: ignore[assignment]
    ToolCallRequest = object  # type: ignore[assignment]
    MIDDLEWARE_AVAILABLE = False

if TYPE_CHECKING:  # pragma: no cover
    from app.agents.harness.store.workspace_store import SparrowWorkspaceStore


_TASK_TOOL_NAME = "task"
_READ_WORKSPACE_TOOL_NAME = "read_workspace_file"
_MARK_READ_TOOL_NAME = "mark_subagent_reports_read"

_SYSTEM_BUCKET_KEY = "_system"
_SUBAGENT_REPORTS_KEY = "subagent_reports"


def _state_get(state: Any, key: str, default: Any = None) -> Any:
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _to_dict(modelish: Any) -> dict[str, Any]:
    if modelish is None:
        return {}
    if isinstance(modelish, dict):
        return dict(modelish)
    if hasattr(modelish, "model_dump"):
        try:
            dumped = modelish.model_dump()
            return dumped if isinstance(dumped, dict) else {}
        except Exception:
            return {}
    if hasattr(modelish, "dict"):
        try:
            dumped = modelish.dict()
            return dumped if isinstance(dumped, dict) else {}
        except Exception:
            return {}
    return {}


def _sanitize_json_value(
    value: Any,
    *,
    max_depth: int,
    max_string_chars: int,
    max_list_items: int,
    max_dict_keys: int,
    _depth: int = 0,
) -> Any:
    if _depth >= max_depth:
        return "[...depth-limited...]"

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if len(value) <= max_string_chars:
            return value
        return value[: max_string_chars - 24] + "...[truncated]"

    if isinstance(value, list):
        return [
            _sanitize_json_value(
                item,
                max_depth=max_depth,
                max_string_chars=max_string_chars,
                max_list_items=max_list_items,
                max_dict_keys=max_dict_keys,
                _depth=_depth + 1,
            )
            for item in value[:max_list_items]
        ]

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for i, (k, v) in enumerate(list(value.items())[:max_dict_keys]):
            key = str(k)
            result[key] = _sanitize_json_value(
                v,
                max_depth=max_depth,
                max_string_chars=max_string_chars,
                max_list_items=max_list_items,
                max_dict_keys=max_dict_keys,
                _depth=_depth + 1,
            )
        if len(value) > max_dict_keys:
            result["..."] = f"[truncated {len(value) - max_dict_keys} keys]"
        return result

    return str(value)


def _build_context_capsule(state: Any) -> dict[str, Any]:
    """Build a compact, safe capsule for subagents (quality-first, bounded)."""
    forwarded = _state_get(state, "forwarded_props", {}) or {}
    scratchpad = _state_get(state, "scratchpad", {}) or {}
    thread_state = _state_get(state, "thread_state", None)

    forwarded_dict = _to_dict(forwarded)
    scratchpad_dict = _to_dict(scratchpad)
    thread_state_dict = _to_dict(thread_state)

    capsule: dict[str, Any] = {
        "session_id": _state_get(state, "session_id", None),
        "trace_id": _state_get(state, "trace_id", None),
        "user_id": _state_get(state, "user_id", None),
        "provider": _state_get(state, "provider", None),
        "model": _state_get(state, "model", None),
        "agent_type": _state_get(state, "agent_type", None),
        "forwarded_props": {
            k: forwarded_dict.get(k)
            for k in (
                "is_zendesk_ticket",
                "customer_id",
                "customerId",
                "zendesk_ticket_id",
                "zendeskTicketId",
                "formatting",
                "formatting_mode",
                "force_websearch",
                "websearch_max_results",
                "websearch_profile",
            )
            if k in forwarded_dict
        },
        "thread_state": thread_state_dict,
        "scratchpad_system": _to_dict(scratchpad_dict.get(_SYSTEM_BUCKET_KEY)),
    }

    # Redact and bound size for safety + token efficiency.
    try:
        capsule = redact_sensitive_from_dict(capsule)
    except Exception as exc:
        logger.warning("context_capsule_redaction_failed", error=str(exc))
        capsule = {"redaction_failed": True}
    capsule = _sanitize_json_value(
        capsule,
        max_depth=5,
        max_string_chars=2000,
        max_list_items=50,
        max_dict_keys=60,
    )
    return capsule


def _json_block(value: dict[str, Any], *, max_chars: int) -> str:
    encoded = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(encoded) <= max_chars:
        return encoded
    return encoded[: max_chars - 24] + "\n...[truncated]..."


def _extract_task_args(tool_call: dict[str, Any]) -> dict[str, Any]:
    raw = tool_call.get("args") or {}
    return raw if isinstance(raw, dict) else {}


def _get_task_description(args: dict[str, Any]) -> Optional[str]:
    for key in ("description", "prompt", "task"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _set_task_description(args: dict[str, Any], description: str) -> dict[str, Any]:
    next_args = dict(args)
    if "description" in next_args or "prompt" not in next_args:
        next_args["description"] = description
    else:
        next_args["prompt"] = description
    return next_args


def _get_subagent_type(args: dict[str, Any]) -> Optional[str]:
    value = args.get("subagent_type") or args.get("subagentType")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _report_paths(subagent_type: str, tool_call_id: str) -> tuple[str, str]:
    run_dir = f"/scratch/subagents/{subagent_type}/{tool_call_id}"
    report_path = f"{run_dir}/report.md"
    return run_dir, report_path


def _pointer_message(*, subagent_type: str, report_path: str, report: str) -> str:
    excerpt = (report or "").strip()
    if len(excerpt) > 1200:
        excerpt = excerpt[:1200].rstrip() + "...[truncated]"
    lines = [
        f"Subagent `{subagent_type}` report saved to `{report_path}`.",
    ]
    if excerpt:
        lines.extend(["", "Excerpt:", excerpt])
    lines.extend(
        [
            "",
            "Use `read_workspace_file` on the path above to review more (or use offset to continue).",
        ]
    )
    return "\n".join(lines)


class SubagentWorkspaceBridgeMiddleware(AgentMiddleware if MIDDLEWARE_AVAILABLE else object):
    """Middleware that bridges DeepAgents `task` runs into workspace-backed reports."""

    def __init__(
        self,
        *,
        workspace_store: Any,
        report_read_limit_chars: int = 20000,
        capsule_max_chars: int = 12000,
    ) -> None:
        self._store = workspace_store
        self._report_read_limit_chars = max(1024, int(report_read_limit_chars))
        self._capsule_max_chars = max(2048, int(capsule_max_chars))

    @property
    def name(self) -> str:  # pragma: no cover - trivial
        return "subagent_workspace_bridge"

    async def awrap_tool_call(  # type: ignore[override]
        self,
        request: "ToolCallRequest",
        handler: Callable[["ToolCallRequest"], Awaitable[Any]],
    ) -> Any:
        tool_call = getattr(request, "tool_call", None) or {}
        tool_name = tool_call.get("name")
        if tool_name != _TASK_TOOL_NAME:
            return await handler(request)

        args = _extract_task_args(tool_call)
        subagent_type = _get_subagent_type(args)
        original_description = _get_task_description(args)
        tool_call_id = tool_call.get("id") or getattr(getattr(request, "runtime", None), "tool_call_id", None)

        if not isinstance(tool_call_id, str) or not tool_call_id:
            return await handler(request)
        if not subagent_type or not original_description:
            return await handler(request)

        run_dir, report_path = _report_paths(subagent_type, tool_call_id)
        capsule = _build_context_capsule(getattr(request, "state", None))
        capsule["subagent"] = {
            "type": subagent_type,
            "tool_call_id": tool_call_id,
            "run_dir": run_dir,
            "report_path": report_path,
        }
        capsule_json = _json_block(capsule, max_chars=self._capsule_max_chars)

        augmented = (
            f"{original_description.strip()}\n\n"
            f"<context_capsule>\n{capsule_json}\n</context_capsule>\n\n"
            "<workspace_instructions>\n"
            f"- You MAY write intermediate artifacts under `{run_dir}/...`.\n"
            f"- Do NOT write to `{report_path}` (the system will overwrite it with your final report).\n"
            "- Produce a complete final report in your last message.\n"
            "</workspace_instructions>"
        )

        new_tool_call = dict(tool_call)
        new_args = _set_task_description(args, augmented)
        new_tool_call["args"] = new_args
        request = request.override(tool_call=new_tool_call)

        result = await handler(request)

        # Persist and replace tool output (Command update from DeepAgents task tool).
        if LangGraphCommand is None:
            return result
        if not isinstance(result, LangGraphCommand) or not isinstance(getattr(result, "update", None), dict):
            return result

        update = dict(getattr(result, "update", None) or {})
        messages = list(update.get("messages") or [])
        report_text: Optional[str] = None
        for msg in messages:
            if isinstance(msg, ToolMessage) and getattr(msg, "tool_call_id", None) == tool_call_id:
                content = getattr(msg, "content", None)
                report_text = content if isinstance(content, str) else str(content)
                break
        if not report_text:
            return result

        try:
            await self._store.write_file(
                report_path,
                report_text,
                metadata={
                    "kind": "subagent_report",
                    "subagent_type": subagent_type,
                    "tool_call_id": tool_call_id,
                    "stored_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("subagent_report_write_failed", path=report_path, error=str(exc))
            return result

        pointer = _pointer_message(subagent_type=subagent_type, report_path=report_path, report=report_text)
        replaced: list[Any] = []
        for msg in messages:
            if isinstance(msg, ToolMessage) and getattr(msg, "tool_call_id", None) == tool_call_id:
                replaced.append(ToolMessage(content=pointer, tool_call_id=tool_call_id))
            else:
                replaced.append(msg)
        update["messages"] = replaced

        # Record report metadata in scratchpad for deterministic ingestion.
        scratchpad_update = {
            _SYSTEM_BUCKET_KEY: {
                _SUBAGENT_REPORTS_KEY: {
                    tool_call_id: {
                        "subagent_type": subagent_type,
                        "path": report_path,
                        "run_dir": run_dir,
                        "read": False,
                    }
                }
            }
        }
        existing_scratchpad = update.get("scratchpad")
        if isinstance(existing_scratchpad, dict):
            system_bucket = existing_scratchpad.setdefault(_SYSTEM_BUCKET_KEY, {})
            if isinstance(system_bucket, dict):
                reports = system_bucket.setdefault(_SUBAGENT_REPORTS_KEY, {})
                if isinstance(reports, dict):
                    reports[tool_call_id] = scratchpad_update[_SYSTEM_BUCKET_KEY][_SUBAGENT_REPORTS_KEY][tool_call_id]
            update["scratchpad"] = existing_scratchpad
        else:
            update["scratchpad"] = scratchpad_update

        return LangGraphCommand(
            graph=getattr(result, "graph", None),
            update=update,
            resume=getattr(result, "resume", None),
            goto=getattr(result, "goto", ()),
        )

    async def awrap_model_call(  # type: ignore[override]
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], Awaitable["ModelResponse"]],
    ) -> Any:
        """Force ingestion of unread subagent reports before continuing."""
        try:
            state = getattr(request, "state", None)
            scratchpad = _state_get(state, "scratchpad", {}) or {}
            scratchpad_dict = _to_dict(scratchpad)
            system_bucket = _to_dict(scratchpad_dict.get(_SYSTEM_BUCKET_KEY))
            reports = _to_dict(system_bucket.get(_SUBAGENT_REPORTS_KEY))
        except Exception:
            return await handler(request)

        unread: dict[str, dict[str, Any]] = {}
        for tool_call_id, record in reports.items():
            rec = _to_dict(record)
            if rec.get("read") is True:
                continue
            path = rec.get("path")
            if isinstance(path, str) and path.strip():
                unread[str(tool_call_id)] = rec

        if not unread:
            return await handler(request)

        tool_calls: list[dict[str, Any]] = []
        for tool_call_id, rec in unread.items():
            tool_calls.append({
                "id": f"read_subagent_report_{uuid4().hex}",
                "name": _READ_WORKSPACE_TOOL_NAME,
                "args": {
                    "path": rec["path"],
                    "offset": 0,
                    "limit": self._report_read_limit_chars,
                },
            })

        tool_calls.append({
            "id": f"mark_subagent_reports_read_{uuid4().hex}",
            "name": _MARK_READ_TOOL_NAME,
            "args": {"report_tool_call_ids": list(unread.keys())},
        })

        return AIMessage(
            content="",
            tool_calls=tool_calls,
            additional_kwargs={
                "subagent_report_ingest": {
                    "count": len(unread),
                    "tool_call_ids": list(unread.keys()),
                }
            },
        )
