"""Middleware to enforce log-analysis subagent routing for attachments.

Phase 3 requirement:
- If the user attached log file(s), spawn ONE `log_diagnoser` tool call per file in a
  single tool batch (parallelizable), before the coordinator writes the final
  answer.

Rationale:
- Relying on the coordinator model to follow a prompt instruction is not
  deterministic. This middleware short-circuits the first model call and returns
  a synthetic `AIMessage` containing multiple `log_diagnoser` tool calls.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from .attachment_processor import get_attachment_processor

try:
    from langchain.agents.middleware import AgentMiddleware
    from langchain.agents.middleware.types import ModelRequest, ModelResponse

    MIDDLEWARE_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    AgentMiddleware = object  # type: ignore[assignment]
    ModelRequest = object  # type: ignore[assignment]
    ModelResponse = object  # type: ignore[assignment]
    MIDDLEWARE_AVAILABLE = False


_AUTOROUTE_MESSAGE_NAME = "log_autoroute_instruction"
_ATTACHMENT_HEADER = "Attachment:"
_AUTOROUTE_SIGNATURE_KEY = "log_autoroute_signature"
_LOG_TOOL_NAME = "log_diagnoser"


def _coerce_message_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for chunk in content:
            if isinstance(chunk, dict) and chunk.get("type") == "text":
                parts.append(str(chunk.get("text") or ""))
            else:
                parts.append(str(chunk))
        return "".join(parts)
    return str(content) if content is not None else ""


def _extract_last_user_objective(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            text = _coerce_message_text(msg).strip()
            if text:
                return text
    return ""


def _find_log_autoroute_instruction(messages: list[BaseMessage]) -> Optional[SystemMessage]:
    for msg in messages:
        if isinstance(msg, SystemMessage) and getattr(msg, "name", None) == _AUTOROUTE_MESSAGE_NAME:
            return msg
    return None


def _parse_file_names_from_instruction(content: str) -> list[str]:
    names: list[str] = []
    for line in (content or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("1)"):
            break
        if not stripped.startswith("- "):
            continue
        candidate = stripped[2:].strip()
        if not candidate or candidate.startswith("("):
            continue
        names.append(candidate)
    return names


def _parse_attachment_blocks_from_text(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    current_name: Optional[str] = None
    current_lines: list[str] = []

    for line in (text or "").splitlines():
        if line.startswith(f"{_ATTACHMENT_HEADER} "):
            if current_name and current_lines:
                blocks.append((current_name, "\n".join(current_lines).strip()))
            current_name = line[len(_ATTACHMENT_HEADER) :].strip()
            current_lines = [line]
            continue
        if current_name is not None:
            current_lines.append(line)

    if current_name and current_lines:
        blocks.append((current_name, "\n".join(current_lines).strip()))

    return blocks


def _strip_attachment_header(block: str) -> str:
    if not block:
        return ""
    lines = block.splitlines()
    if not lines:
        return ""
    if lines[0].startswith(f"{_ATTACHMENT_HEADER} "):
        return "\n".join(lines[1:]).lstrip()
    return block.strip()


def _extract_attachment_blocks(messages: list[BaseMessage]) -> dict[str, str]:
    """Return a map of attachment filename (lowercased) -> full attachment block."""
    blocks_by_name: dict[str, str] = {}
    for msg in messages:
        text = _coerce_message_text(msg)
        if _ATTACHMENT_HEADER not in text:
            continue
        for name, block in _parse_attachment_blocks_from_text(text):
            key = (name or "").strip().lower()
            if not key or key in blocks_by_name:
                continue
            blocks_by_name[key] = block
    return blocks_by_name


def _get_attachment_attr(attachment: Any, attr: str) -> Optional[Any]:
    if isinstance(attachment, dict):
        return attachment.get(attr)
    return getattr(attachment, attr, None)


def _get_state_attachments(state: Any) -> list[Any]:
    if state is None:
        return []
    if isinstance(state, dict):
        return list(state.get("attachments") or [])
    return list(getattr(state, "attachments", []) or [])


def _clear_state_attachments(state: Any) -> None:
    if state is None:
        return
    if isinstance(state, dict):
        state["attachments"] = []
        return
    try:
        setattr(state, "attachments", [])
    except Exception:
        return


def _extract_log_pairs_from_state(attachments: list[Any]) -> list[tuple[str, str]]:
    processor = get_attachment_processor()
    pairs: list[tuple[str, str]] = []
    for idx, attachment in enumerate(attachments or []):
        is_log, _ = processor.is_log_attachment(attachment)
        if not is_log:
            continue
        name = _get_attachment_attr(attachment, "name") or ""
        data_url = _get_attachment_attr(attachment, "data_url")
        if not data_url:
            continue
        decoded = processor.decode_data_url(str(data_url))
        if not decoded:
            continue
        content = processor.extract_log_content(decoded)
        file_name = str(name).strip() or f"attachment_{idx + 1}.log"
        pairs.append((file_name, content))
    return pairs


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _compute_signature(pairs: list[tuple[str, str]]) -> str:
    """Compute a stable signature for a set of per-file blocks (without storing content)."""
    payload = [
        {"file": file_name, "sha256": _sha256_text(block)}
        for file_name, block in sorted(pairs, key=lambda item: item[0].lower())
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return _sha256_text(encoded)


def _find_prev_signature(messages: list[BaseMessage]) -> Optional[str]:
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        sig = (getattr(msg, "additional_kwargs", {}) or {}).get(_AUTOROUTE_SIGNATURE_KEY)
        if isinstance(sig, str) and sig:
            return sig
    return None


class LogAutorouteMiddleware(AgentMiddleware if MIDDLEWARE_AVAILABLE else object):
    """Force per-file log analysis tool calls when log attachments are present."""

    @property
    def name(self) -> str:  # pragma: no cover - trivial
        return "log_autoroute"

    def wrap_model_call(  # type: ignore[override]
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], "ModelResponse"],
    ) -> Any:
        # Sync wrapper delegates to the async implementation when possible.
        return handler(request)

    async def awrap_model_call(  # type: ignore[override]
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], Awaitable["ModelResponse"]],
    ) -> Any:
        # Only route when the run_unified_agent injected the explicit autoroute instruction.
        instruction = _find_log_autoroute_instruction(list(request.messages or []))
        if instruction is None:
            return await handler(request)

        file_names = _parse_file_names_from_instruction(_coerce_message_text(instruction))
        selected: list[tuple[str, str]] = []

        attachments = _get_state_attachments(getattr(request, "state", None))
        if attachments:
            attachment_pairs = _extract_log_pairs_from_state(attachments)
            if attachment_pairs:
                by_name: dict[str, tuple[str, str]] = {}
                for name, content in attachment_pairs:
                    key = name.strip().lower()
                    if key and key not in by_name:
                        by_name[key] = (name, content)

                if file_names:
                    for name in file_names:
                        block = by_name.get(name.strip().lower())
                        if block:
                            selected.append(block)
                else:
                    selected = list(by_name.values())

        if not selected:
            attachment_blocks = _extract_attachment_blocks(list(request.messages or []))
            if not attachment_blocks:
                return await handler(request)

            if file_names:
                for name in file_names:
                    block = attachment_blocks.get(name.strip().lower())
                    if block:
                        selected.append((name.strip(), block))
            else:
                selected = [(name, block) for name, block in attachment_blocks.items()]

            if not selected:
                return await handler(request)

        signature = _compute_signature(selected)
        prev_sig = _find_prev_signature(list(request.messages or []))
        if prev_sig == signature:
            return await handler(request)

        user_objective = _extract_last_user_objective(list(request.messages or []))
        tool_calls: list[dict[str, Any]] = []
        for file_name, block in selected:
            log_content = _strip_attachment_header(block)
            tool_calls.append({
                # OpenAI tool_call_id expects a call_* format; keep synthetic IDs compatible.
                "id": f"call_{uuid4().hex}",
                "name": _LOG_TOOL_NAME,
                "args": {
                    "file_name": file_name.strip(),
                    "log_content": log_content,
                    "question": user_objective or None,
                },
            })

        # Return a single tool-call batch (parallelizable): one log analysis call per file.
        response = AIMessage(
            content="",
            tool_calls=tool_calls,
            additional_kwargs={_AUTOROUTE_SIGNATURE_KEY: signature},
        )
        if attachments:
            _clear_state_attachments(getattr(request, "state", None))
        return response
