print("--- [graph.py] Top of file ---")
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

print("--- [graph.py] Importing GraphState ---")
from .state import GraphState
print("--- [graph.py] Imported GraphState ---")
print("--- [graph.py] Importing run_primary_agent ---")
from app.agents_v2.primary_agent.agent import run_primary_agent
from app.agents_v2.primary_agent.schemas import PrimaryAgentState
print("--- [graph.py] Imported run_primary_agent ---")
print("--- [graph.py] Importing mailbird_kb_search ---")
from app.agents_v2.primary_agent.tools import mailbird_kb_search
from app.agents_v2.primary_agent.tools import tavily_web_search
print("--- [graph.py] Imported mailbird_kb_search ---")

# Create wrapper for primary agent that converts GraphState to PrimaryAgentState
async def primary_agent_wrapper(state: GraphState):
    """Wrapper that converts GraphState to PrimaryAgentState and passes selected model."""
    primary_state = PrimaryAgentState(
        messages=state.messages,
        model=state.selected_model,
        routing_metadata=state.routing_metadata
    )
    return await run_primary_agent(primary_state)

print("--- [graph.py] Importing query_router ---")
from app.agents_v2.router.router import query_router
print("--- [graph.py] Imported query_router ---")
print("--- [graph.py] Importing run_log_analysis_agent ---")
from app.agents_v2.log_analysis_agent.agent import run_log_analysis_agent
print("--- [graph.py] Imported run_log_analysis_agent ---")
print("--- [graph.py] Importing run_researcher, should_continue, pre_process, post_process ---")
from .nodes import pre_process, post_process, run_researcher, should_continue

# Define the graph
print("--- [graph.py] Instantiating StateGraph ---")
workflow = StateGraph(GraphState)
print("--- [graph.py] Instantiated StateGraph ---")

# Add the router node
print("--- [graph.py] Adding node: router ---")
workflow.add_node("router", query_router)
print("--- [graph.py] Added node: router ---")

# Add the agent nodes
print("--- [graph.py] Adding node: primary_agent ---")
workflow.add_node("primary_agent", primary_agent_wrapper)
print("--- [graph.py] Added node: primary_agent ---")
print("--- [graph.py] Adding node: log_analyst ---")
workflow.add_node("log_analyst", run_log_analysis_agent)
print("--- [graph.py] Added node: log_analyst ---")
print("--- [graph.py] Adding node: researcher ---")
workflow.add_node("researcher", run_researcher)
print("--- [graph.py] Added node: researcher ---")

# Add the tool node
tools = [mailbird_kb_search, tavily_web_search]
print("--- [graph.py] Adding node: tools ---")
workflow.add_node("tools", ToolNode(tools))
print("--- [graph.py] Added node: tools ---")

# -------------------- Reflection QA Node ----------------------------
print("--- [graph.py] Adding node: reflection ---")
from app.agents_v2.reflection.node import reflection_runnable, reflection_route
workflow.add_node("reflection", reflection_runnable)

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
print("--- [graph.py] Added reflection edges ---")

# Add pre_process node and set entry
print("--- [graph.py] Adding node: pre_process ---")
workflow.add_node("pre_process", pre_process)
print("--- [graph.py] Added node: pre_process ---")

# Set entry to pre_process
print("--- [graph.py] Setting entry point: pre_process ---")
workflow.set_entry_point("pre_process")

# Add edge pre_process -> router (cached?)
print("--- [graph.py] Adding conditional edges for pre_process ---")
workflow.add_conditional_edges(
    "pre_process",
    lambda state: "router" if state.cached_response is None else "__end__",
    {
        "router": "router",
        "__end__": END,
    },
)
print("--- [graph.py] Added conditional edges for pre_process ---")

# Add the conditional edges from the router
print("--- [graph.py] Adding conditional edges for router ---")
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
print("--- [graph.py] Added conditional edges for router ---")

# Add edges from the agents back to the graph logic
print("--- [graph.py] Adding conditional edges for primary_agent ---")
workflow.add_conditional_edges(
    "primary_agent",
    should_continue,
    {
        "continue": "tools",
        "end": "reflection",
    },
)
print("--- [graph.py] Added conditional edges for primary_agent ---")

# Add edge from the tool node back to the primary agent
print("--- [graph.py] Adding edge: tools to primary_agent ---")
workflow.add_edge("tools", "primary_agent")
print("--- [graph.py] Added edge: tools to primary_agent ---")

# Add post_process node
print("--- [graph.py] Adding node: post_process ---")
workflow.add_node("post_process", post_process)
print("--- [graph.py] Added node: post_process ---")

# Add post_process edges
workflow.add_edge("researcher", "post_process")
workflow.add_edge("log_analyst", "post_process")
workflow.add_edge("post_process", END)

# Compile the graph with memory checkpointer for state persistence
print("--- [graph.py] Compiling workflow with memory checkpointer ---")
checkpointer = MemorySaver()
app = workflow.compile(checkpointer=checkpointer)
print("--- [graph.py] Compiled workflow with memory support. Graph setup complete. ---") 