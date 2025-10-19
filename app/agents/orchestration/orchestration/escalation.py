"""Human-in-the-loop escalation hook."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.prebuilt.interrupt import (
    ActionRequest,
    HumanInterrupt,
    HumanInterruptConfig,
    HumanResponse,
)
from langgraph.types import Command, interrupt
from loguru import logger


def _extract_last_message(messages: List[BaseMessage], kind: str) -> Optional[str]:
    """Return the content of the latest message of the requested type."""
    for message in reversed(messages):
        msg_type = getattr(message, "type", None)
        if msg_type == kind:
            try:
                return str(message.content)
            except Exception:
                return None
    return None


def _build_interrupt_payload(state: Dict[str, Any]) -> HumanInterrupt:
    """Assemble a rich interrupt payload for the supervisor UI."""
    messages: List[BaseMessage] = list(state.get("messages") or [])
    latest_user = _extract_last_message(messages, "human")
    latest_assistant = _extract_last_message(messages, "ai")

    action_request: ActionRequest = {
        "action": "review_primary_agent_escalation",
        "args": {
            "session_id": state.get("session_id"),
            "trace_id": state.get("trace_id"),
            "last_user_message": latest_user,
            "assistant_summary": latest_assistant,
        },
    }
    config: HumanInterruptConfig = {
        "allow_ignore": True,
        "allow_respond": True,
        "allow_edit": False,
        "allow_accept": True,
    }
    description = (
        "The primary agent requested human escalation. Review the context and choose how to proceed."
    )
    return HumanInterrupt(
        action_request=action_request,
        config=config,
        description=description,
    )


def _record_supervisor_message(
    messages: List[BaseMessage],
    response: HumanResponse,
) -> List[BaseMessage]:
    """Append a supervisor-authored message when a response is provided."""
    payload = response.get("args")
    if isinstance(payload, str) and payload.strip():
        supervisor_note = payload.strip()
        messages = list(messages)
        messages.append(
            AIMessage(
                content=supervisor_note,
                additional_kwargs={
                    "role": "supervisor",
                    "source": "human_escalation",
                },
            )
        )
    return messages


def _format_edit_instruction(edit_args: Dict[str, Any]) -> str:
    """Create a readable message summarizing supervisor edit instructions."""
    action = edit_args.get("action")
    details = edit_args.get("args")

    parts: List[str] = []
    if isinstance(action, str) and action.strip():
        parts.append(f"Supervisor requested action: {action.strip()}")

    if details is not None:
        if isinstance(details, str) and details.strip():
            parts.append(f"Details: {details.strip()}")
        else:
            try:
                parts.append(f"Details: {json.dumps(details, ensure_ascii=False)}")
            except Exception:
                parts.append(f"Details: {details!r}")

    return "\n".join(parts) if parts else json.dumps(edit_args, ensure_ascii=False)


def escalate_for_human(state: Dict[str, Any]) -> Command:
    """Pause execution and request a human decision before finalizing escalation."""
    messages: List[BaseMessage] = list(state.get("messages") or [])
    try:
        request = _build_interrupt_payload(state)
        logger.warning(
            "Escalation requested for session %s; awaiting human review",
            state.get("session_id"),
        )
        responses = interrupt([request])
        human_response: HumanResponse = responses[0] if responses else {"type": "accept", "args": None}
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("Failed to obtain human response during escalation: %s", exc)
        return Command(update={"destination": "__end__", "escalation_review": {"type": "error", "detail": str(exc)}})

    decision_type = human_response.get("type", "accept")
    logger.info(
        "Supervisor decision received",
        decision=decision_type,
        session_id=state.get("session_id"),
    )

    updates: Dict[str, Any] = {
        "escalation_review": {
            "type": decision_type,
        }
    }
    payload = human_response.get("args")
    if payload is not None:
        updates["escalation_review"]["payload"] = payload
        if isinstance(payload, str):
            updates["escalation_review"]["note"] = payload

    if decision_type == "ignore":
        updates["destination"] = "primary_agent"
    elif decision_type == "response":
        updates["messages"] = _record_supervisor_message(messages, human_response)
        updates["destination"] = "__end__"
    elif decision_type == "edit":
        # Treat edit instructions as a supervisor response; they are surfaced back to the agent.
        edit_args = payload
        if isinstance(edit_args, dict):
            action = edit_args.get("action")
            if isinstance(action, str):
                updates["escalation_review"]["action"] = action
                updates["escalation_review"]["note"] = action
            instructions = edit_args.get("args")
            if instructions is not None:
                updates["escalation_review"]["instructions"] = instructions

            messages.append(
                HumanMessage(
                    content=_format_edit_instruction(edit_args),
                    additional_kwargs={
                        "role": "supervisor",
                        "source": "human_escalation",
                        "action": action,
                    },
                )
            )
            updates["messages"] = messages
        updates["destination"] = "primary_agent"
    else:  # accept or unknown fallthrough
        updates["destination"] = "__end__"

    return Command(update=updates)
