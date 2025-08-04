"""Simple helper for human escalation path."""
from typing import Dict, Any

from loguru import logger


def escalate_for_human(state: Dict[str, Any]) -> Dict[str, Any]:
    """Handles escalation – stub implementation logs and returns marker."""
    logger.warning(
        "Escalating session %s to human with last answer: %s",
        state.get("session_id"),
        state["messages"][-1].content if state.get("messages") else "<no msg>",
    )
    # In production we could enqueue into ticketing system, etc.
    return {"destination": "__end__"}
