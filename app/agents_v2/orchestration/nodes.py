from app.agents_v2.orchestration.state import GraphState
from app.agents_v2.research_agent.research_agent import get_research_graph
from app.cache.redis_cache import RedisCache
from app.services.qdrant_memory import QdrantMemory
import structlog

# Instantiate global singletons
logger = structlog.get_logger()
cache_layer = RedisCache()
vector_memory = QdrantMemory()

# Instantiate the research agent graph
research_agent_graph = get_research_graph()

# ---------------------------------------------------------------------------
# Pre-processing node
# ---------------------------------------------------------------------------

def pre_process(state: GraphState):
    """Check Redis cache and fetch contextual docs from Qdrant."""

    if not state.messages:
        return {"context": []}

    user_query = state.messages[-1].content

    # 1. Cache check
    cached = cache_layer.get(user_query)
    if cached is not None:
        logger.info("cache_hit", session_id=state.session_id)
        return {"cached_response": cached}

    # 2. Vector context retrieval
    query_embedding = vector_memory.embed_query(user_query)
    session_id = state.session_id or "default"
    context_snippets = vector_memory.retrieve_context(
        session_id, query_embedding, top_k=3
    )
    logger.info("cache_miss", session_id=state.session_id, context_docs=len(context_snippets))
    return {"context": context_snippets}

# ---------------------------------------------------------------------------
# Post-processing node
# ---------------------------------------------------------------------------

def post_process(state: GraphState):
    """Persist interaction to Qdrant and Redis."""

    # Skip if we returned cached response (no new content)
    if state.cached_response is not None:
        return {"qa_retry_count": 0}

    if len(state.messages) < 2:
        return {"qa_retry_count": 0}

    user_query = state.messages[-2].content
    agent_response = state.messages[-1].content

    # Qdrant store
    session_id = state.session_id or "default"
    vector_memory.add_interaction(session_id, user_query, agent_response)

    # Cache store
    cache_layer.set(user_query, agent_response)

    logger.info("post_process", session_id=state.session_id)
    return {"qa_retry_count": 0}

def run_researcher(state: GraphState):
    """
    Runs the research agent graph.
    """
    print("---RUNNING RESEARCHER---")
    # The research agent graph expects a specific input format
    research_input = {"messages": state.messages}
    # Invoke the research agent graph
    final_research_state = research_agent_graph.invoke(research_input)
    # Return the final messages from the research agent to update the main graph state
    return {"messages": final_research_state.messages}

# Helper function to decide what to do after an agent is called
def should_continue(state: GraphState):
    """
    Determines whether to continue with tool execution or end the flow.
    """
    last_message = state.messages[-1]
    # Safely check for presence of tool calls; HumanMessage objects do not have this attr
    if getattr(last_message, "tool_calls", None):
        return "continue"
    return "end"
