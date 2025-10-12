from app.agents.orchestration.orchestration.state import GraphState
from app.agents.orchestration.orchestration.store_adapter import (
    ALLOWED_SOURCES,
    get_hybrid_store_adapter,
)
from app.agents.research.research_agent.research_agent import get_research_graph
from app.cache.redis_cache import RedisCache
import structlog
import hashlib
from typing import Dict, Any, Optional
from app.core.settings import settings
from app.services.global_knowledge.retrieval import retrieve_global_knowledge

# Instantiate global singletons
logger = structlog.get_logger()
cache_layer = RedisCache()

# Instantiate the research agent graph
research_agent_graph = get_research_graph()

# ---------------------------------------------------------------------------
# Cache key generation helper
# ---------------------------------------------------------------------------

def _generate_cache_key(session_id: str, user_query: str) -> str:
    """
    Generate a secure cache key that namespaces by session and hashes the query.
    
    Args:
        session_id: Session identifier for namespacing
        user_query: User query to hash (prevents PII exposure in cache keys)
        
    Returns:
        str: Namespaced cache key with hashed query
    """
    # Use blake2b for fast, secure hashing
    query_hash = hashlib.blake2b(user_query.encode('utf-8'), digest_size=32).hexdigest()
    # Namespace by session to prevent cross-session data leakage
    return f"session:{session_id}:query:{query_hash}"

# ---------------------------------------------------------------------------
# Pre-processing node
# ---------------------------------------------------------------------------

async def pre_process(state: GraphState) -> Dict[str, Any]:
    """
    Check Redis cache for previously cached responses.
    
    Returns:
        Dict with updates including:
        - {"cached_response": <cached_value>} on cache hit
        - Optional "global_knowledge_context" metadata when the store adapter is enabled
        - {} on cache miss when no extra metadata is produced
    """

    updates: Dict[str, Any] = {}
    global_context: Dict[str, Any] = {}
    if settings.should_use_store_adapter():
        adapter = get_hybrid_store_adapter()
        global_context.update(
            {
                "adapter_ready": adapter.is_ready(),
                "sources": sorted(ALLOWED_SOURCES),
            }
        )

    if not state.messages:
        if global_context:
            state.global_knowledge_context = dict(global_context)
            updates["global_knowledge_context"] = state.global_knowledge_context
        return updates

    user_query = state.messages[-1].content
    session_id = getattr(state, 'session_id', 'default')

    # 1. Cache check with secure key
    cache_key = _generate_cache_key(session_id, user_query)
    cached = cache_layer.get(cache_key)
    if cached is not None:
        logger.info("cache_hit", session_id=session_id)
        updates["cached_response"] = cached
        if global_context:
            state.global_knowledge_context = dict(global_context)
            updates["global_knowledge_context"] = state.global_knowledge_context
        return updates

    # 2. No vector retrieval needed - using Supabase for context
    # Context will be retrieved directly by agents when needed
    logger.info("cache_miss", session_id=session_id)

    if settings.should_enable_global_knowledge():
        retrieval = await retrieve_global_knowledge(
            user_query,
            top_k=settings.global_knowledge_top_k,
        )
        global_context["retrieval"] = retrieval
        if retrieval.get("memory_snippet"):
            global_context["memory_snippet"] = retrieval["memory_snippet"]
        global_context.setdefault("sources", sorted(ALLOWED_SOURCES))

    if global_context:
        state.global_knowledge_context = dict(global_context)
        updates["global_knowledge_context"] = state.global_knowledge_context

    return updates  # Empty dict on cache miss aside from optional adapter context

# ---------------------------------------------------------------------------
# Post-processing node
# ---------------------------------------------------------------------------

def post_process(state: GraphState) -> Dict[str, Any]:
    """
    Persist interaction to Redis cache with TTL and proper scoping.
    
    Cache entries expire after 1 hour to prevent unbounded growth.
    Keys are namespaced by session and hashed to prevent PII exposure.
    """

    # Skip if we returned cached response (no new content)
    if state.cached_response is not None:
        return {}

    if len(state.messages) < 2:
        return {}

    user_query = state.messages[-2].content
    agent_response = state.messages[-1].content
    session_id = getattr(state, 'session_id', 'default')

    # Cache store with secure key and TTL (1 hour = 3600 seconds)
    cache_key = _generate_cache_key(session_id, user_query)
    cache_layer.set(cache_key, agent_response, ttl=3600)

    logger.info("post_process", session_id=session_id)
    return {"qa_retry_count": 0}

from langchain_core.messages import HumanMessage, AIMessage

async def run_researcher(state: GraphState):
    """
    Runs the research agent graph asynchronously using the last user query,
    and appends a synthesized answer + citations to the messages.
    """
    logger.debug("running_researcher_async")
    # Extract the latest user query (prefer last HumanMessage)
    query_text = None
    if state.messages:
        last_msg = state.messages[-1]
        if isinstance(last_msg, HumanMessage):
            query_text = last_msg.content
        else:
            for m in reversed(state.messages):
                if isinstance(m, HumanMessage):
                    query_text = m.content
                    break
    if not query_text:
        return {"messages": state.messages}

    # Prepare initial state for the research agent
    initial_state = {
        "query": query_text,
        "urls": [],
        "documents": [],
        "answer": None,
        "citations": None,
    }

    # Invoke the research graph asynchronously (synthesize node is async)
    final_state = await research_agent_graph.ainvoke(initial_state)

    answer = final_state.get("answer") or "I'm sorry, I couldn't find relevant information to answer your question."
    citations = final_state.get("citations") or []

    # Build assistant response including simple citation rendering
    citation_text = ""
    try:
        refs = [f"[{c.get('id')}] {c.get('url')}" for c in citations if isinstance(c, dict)]
        if refs:
            citation_text = "\n\nSources:\n" + "\n".join(refs)
    except Exception:
        pass

    new_message = AIMessage(content=answer + citation_text)
    return {"messages": state.messages + [new_message]}

# Helper function to decide what to do after an agent is called
def should_continue(state: GraphState):
    """
    Determines whether to continue with tool execution or end the flow.
    """
    last_message = state.messages[-1]
    if not last_message.tool_calls:
        return "end"
    return "continue"
