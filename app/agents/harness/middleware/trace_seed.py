"""Trace seed middleware to inject correlation identifiers."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from langchain.agents.middleware.types import AgentMiddleware


class TraceSeedMiddleware(AgentMiddleware):
    """Seed a correlation_id into sparrow_ctx."""

    name = "trace_seed"

    def before_agent(self, state: Dict[str, Any], runtime: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(state, dict):
            return None
        ctx = state.get("sparrow_ctx", {})
        if not isinstance(ctx, dict):
            ctx = {}
        ctx.setdefault("correlation_id", str(uuid.uuid4()))
        state["sparrow_ctx"] = ctx
        return {"sparrow_ctx": ctx}
