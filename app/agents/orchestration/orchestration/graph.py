import logging
from pathlib import Path
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from .state import GraphState
from app.agents.primary.primary_agent.agent import run_primary_agent
from app.agents.primary.primary_agent.tools import mailbird_kb_search
from app.agents.primary.primary_agent.tools import tavily_web_search
from app.agents.router.router import query_router
from app.agents.log_analysis.log_analysis_agent.agent import run_log_analysis_agent
from .nodes import pre_process, post_process, run_researcher, should_continue
from app.core.settings import settings

logger = logging.getLogger(__name__)


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

            logger.info("Initializing Supabase checkpointer for primary graph")
            return SupabaseCheckpointer(
                CheckpointerConfig(
                    db_url=db_url,
                    pool_size=settings.checkpointer_pool_size,
                    max_overflow=settings.checkpointer_max_overflow,
                )
            )
        except Exception:
            logger.exception("Failed to initialize Supabase checkpointer; falling back to MemorySaver")

    logger.info("Using in-memory MemorySaver checkpointer for primary graph")
    return MemorySaver()


def _export_graph_visualization(graph_app: object) -> None:
    """Render a Mermaid diagram for the primary graph when enabled."""
    if not settings.graph_viz_export_enabled:
        return

    try:
        graph_obj = getattr(graph_app, "get_graph", lambda: None)()
        if graph_obj is None:
            logger.warning("Graph visualization skipped; no graph object available")
            return

        mermaid_source = graph_obj.draw_mermaid()  # type: ignore[attr-defined]
        output_path = Path(settings.graph_viz_output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(mermaid_source)
        logger.info("Primary agent graph exported to %s", output_path)
    except Exception:  # pragma: no cover - best effort diagnostics
        logger.exception("Failed to export primary graph visualization")

# Define the graph
workflow = StateGraph(GraphState)
logger.debug("StateGraph instantiated")

# Add the router node
workflow.add_node("router", query_router)
logger.debug("Added node: router")

# Add the agent nodes
workflow.add_node("primary_agent", run_primary_agent)
logger.debug("Added node: primary_agent")
workflow.add_node("log_analyst", run_log_analysis_agent)
logger.debug("Added node: log_analyst")
workflow.add_node("researcher", run_researcher)
logger.debug("Added node: researcher")

# Add the tool node
tools = [mailbird_kb_search, tavily_web_search]
workflow.add_node("tools", ToolNode(tools))
logger.debug("Added node: tools")

# -------------------- Reflection QA Node ----------------------------
from app.agents.reflection.reflection.node import reflection_runnable, reflection_route
workflow.add_node("reflection", reflection_runnable)
logger.debug("Added node: reflection")

# Add escalation stub node
from .escalation import escalate_for_human
workflow.add_node("escalate", escalate_for_human)
# Escalation is a terminal path
workflow.add_edge("escalate", END)

# Edge from primary_agent to reflection
workflow.add_edge("primary_agent", "reflection")

# Conditional edges based on reflection result
workflow.add_conditional_edges(
    "reflection",
    reflection_route,
    {
        "refine": "primary_agent",
        "post_process": "post_process",
        "escalate": "escalate",
    },
)
logger.debug("Added reflection edges")

# Add pre_process node and set entry
workflow.add_node("pre_process", pre_process)
logger.debug("Added node: pre_process")

# Set entry to pre_process
workflow.set_entry_point("pre_process")
logger.debug("Set entry point: pre_process")

# Add edge pre_process -> router (cached?)
workflow.add_conditional_edges(
    "pre_process",
    lambda state: "router" if state.cached_response is None else "__end__",
    {
        "router": "router",
        "__end__": END,
    },
)
logger.debug("Added conditional edges for pre_process")

# Add the conditional edges from the router
workflow.add_conditional_edges(
    "router",
    lambda state: state.destination, # Access destination from Pydantic model
    {
        "primary_agent": "primary_agent",
        "log_analyst": "log_analyst",
        "researcher": "researcher",
        "__end__": END,
    },
)
logger.debug("Added conditional edges for router")

# Add edges from the agents back to the graph logic
workflow.add_conditional_edges(
    "primary_agent",
    should_continue,
    {
        "continue": "tools",
        "end": "reflection",
    },
)
logger.debug("Added conditional edges for primary_agent")

# Add edge from the tool node back to the primary agent
workflow.add_edge("tools", "primary_agent")
logger.debug("Added edge: tools -> primary_agent")

# Add post_process node
workflow.add_node("post_process", post_process)
logger.debug("Added node: post_process")

# Add post_process edges
workflow.add_edge("researcher", "post_process")
workflow.add_edge("log_analyst", "post_process")
workflow.add_edge("post_process", END)

# Compile the graph with persistence
checkpointer = _build_checkpointer()
app = workflow.compile(checkpointer=checkpointer)
_export_graph_visualization(app)
logger.info("Graph compiled and setup complete")
