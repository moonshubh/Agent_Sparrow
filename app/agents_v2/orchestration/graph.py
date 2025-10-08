import logging
logger = logging.getLogger(__name__)
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from .state import GraphState
from app.agents_v2.primary_agent.agent import run_primary_agent
from app.agents_v2.primary_agent.tools import mailbird_kb_search
from app.agents_v2.primary_agent.tools import tavily_web_search
from app.agents_v2.router.router import query_router
from app.agents_v2.log_analysis_agent.agent import run_log_analysis_agent
from .nodes import pre_process, post_process, run_researcher, should_continue

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
from app.agents_v2.reflection.node import reflection_runnable, reflection_route
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

# Compile the graph
app = workflow.compile()
logger.info("Graph compiled and setup complete")