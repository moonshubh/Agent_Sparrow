"""Trace seed middleware to inject correlation identifiers."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, cast

try:  # pragma: no cover - optional dependency
    from langchain.agents.middleware.types import AgentMiddleware, AgentState

    AGENT_MIDDLEWARE_AVAILABLE = True
except Exception:  # pragma: no cover
    AGENT_MIDDLEWARE_AVAILABLE = False

    class AgentMiddleware:  # type: ignore[no-redef]
        pass

    class AgentState(dict):  # type: ignore[no-redef]
        pass


class TraceSeedMiddleware(AgentMiddleware):
    """Seed a correlation_id into sparrow_ctx."""

    name = "trace_seed"

    def before_agent(self, state: AgentState, runtime: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(state, dict):
            return None
        state_dict = cast(Dict[str, Any], state)
        ctx = state_dict.get("sparrow_ctx", {})
        if not isinstance(ctx, dict):
            ctx = {}
        ctx.setdefault("correlation_id", str(uuid.uuid4()))
        state_dict["sparrow_ctx"] = ctx
        return {"sparrow_ctx": ctx}
