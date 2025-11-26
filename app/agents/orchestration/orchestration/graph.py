import asyncio
from pathlib import Path
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END

from app.core.logging_config import get_logger
from app.core.settings import settings
from app.agents.unified.quota_manager import QuotaExceededError

from .state import GraphState

logger = get_logger(__name__)


def _build_checkpointer() -> Optional[object]:
    """Select an appropriate checkpointer based on settings."""
    if not settings.checkpointer_enabled:
        logger.info("Checkpointer disabled via settings; compiling graph without persistence")
        return None

    db_url = settings.checkpointer_db_url
    if db_url:
        try:
            from app.agents.checkpointer.config import CheckpointerConfig
            from app.agents.checkpointer.postgres_checkpointer import SupabaseCheckpointer

            logger.info("Initializing Supabase checkpointer for unified graph")
            return SupabaseCheckpointer(
                CheckpointerConfig(
                    db_url=db_url,
                    pool_size=settings.checkpointer_pool_size,
                    max_overflow=settings.checkpointer_max_overflow,
                )
            )
        except Exception as exc:
            logger.exception("checkpointer_supabase_init_failed", error=str(exc))

    logger.info("checkpointer_selected", checkpointer="memory")
    return MemorySaver()


def _get_store() -> Optional[object]:
    """Return the shared LangGraph store if available."""
    try:
        from app.agents.harness.store import sparrow_memory_store
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("store_init_failed", error=str(exc))
        return None
    return sparrow_memory_store


def _export_graph_visualization(graph_app: object) -> None:
    """Render a Mermaid diagram for the unified graph when enabled."""
    if not settings.graph_viz_export_enabled:
        return

    try:
        graph_obj = getattr(graph_app, "get_graph", lambda: None)()
        if graph_obj is None:
            logger.warning("graph_viz_export_skipped", reason="no_graph_object")
            return

        mermaid_source = graph_obj.draw_mermaid()  # type: ignore[attr-defined]
        output_path = Path(settings.graph_viz_output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(mermaid_source)
        logger.info("graph_viz_exported", output=str(output_path))
    except Exception as exc:  # pragma: no cover - best effort diagnostics
        logger.exception("graph_viz_export_failed", error=str(exc))


def _build_tool_node():
    """Create a fresh ToolNode instance for the unified tool runner."""
    from app.agents.unified.tools import get_registered_tools
    from langgraph.prebuilt import ToolNode

    return ToolNode(get_registered_tools())


async def _run_agent_with_retry(state: GraphState, config: Optional[dict] = None) -> dict:
    """Run the unified agent with lightweight retry/backoff for transient errors."""

    from app.agents.unified.agent_sparrow import run_unified_agent

    max_attempts = getattr(settings, "graph_retry_attempts", 3) or 3
    backoff_factor = getattr(settings, "graph_retry_backoff", 2.0) or 2.0
    retryable_errors = (QuotaExceededError, asyncio.TimeoutError)

    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await run_unified_agent(state, config)
        except retryable_errors as exc:
            last_exc = exc
            if attempt >= max_attempts:
                logger.error(
                    "graph_agent_retry_exhausted",
                    attempts=max_attempts,
                    error=str(exc),
                )
                break

            delay = backoff_factor ** (attempt - 1)
            logger.warning(
                "graph_agent_retry",
                attempt=attempt,
                delay=delay,
                error=str(exc),
            )
            await asyncio.sleep(delay)
    if last_exc:
        raise last_exc
    raise RuntimeError("graph_agent_retry_failed_without_exception")


def build_unified_graph():
    """Construct the unified LangGraph app."""
    from app.agents.unified.agent_sparrow import should_continue

    workflow = StateGraph(GraphState)
    logger.debug("state_graph_instantiated")

    workflow.add_node("agent", _run_agent_with_retry)
    logger.debug("graph_node_added", node="agent")

    workflow.add_node("tools", _build_tool_node())
    logger.debug("graph_node_added", node="tools")

    workflow.set_entry_point("agent")
    logger.debug("graph_entry_point_set", node="agent")

    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "tools",
            "end": END,
        },
    )
    logger.debug("graph_conditional_edges_added", source="agent")

    workflow.add_edge("tools", "agent")
    logger.debug("graph_edge_added", source="tools", target="agent")

    checkpointer = _build_checkpointer()
    store = _get_store()
    app = workflow.compile(checkpointer=checkpointer, store=store)
    _export_graph_visualization(app)
    logger.info("graph_compile_complete")
    return app


app = build_unified_graph()
