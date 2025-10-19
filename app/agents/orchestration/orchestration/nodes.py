import asyncio
import hashlib
import re
from typing import Dict, Any, Optional, List

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from langgraph.checkpoint.memory import MemorySaver

from app.agents.orchestration.orchestration.state import GraphState
from app.agents.orchestration.orchestration.store_adapter import (
    ALLOWED_SOURCES,
    get_hybrid_store_adapter,
)
from app.agents.research.research_agent.research_agent import get_research_graph
from app.cache.redis_cache import RedisCache
from app.core.logging_config import get_logger
from app.core.settings import settings
from app.memory.service import memory_service
from app.services.global_knowledge.retrieval import retrieve_global_knowledge

# Instantiate global singletons
logger = get_logger(__name__)
cache_layer = RedisCache()
tracer = trace.get_tracer(__name__)

# Instantiate the research agent graph with a MemorySaver fallback by default.
_default_research_checkpointer = MemorySaver()
_current_research_checkpointer = _default_research_checkpointer
research_agent_graph = get_research_graph(checkpointer=_default_research_checkpointer)

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
# Memory helpers
# ---------------------------------------------------------------------------

PRIMARY_AGENT_ID = "primary"
PRIMARY_MEMORY_SOURCE = "primary_agent"
PRIMARY_MEMORY_TYPE = "fact"
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SECRET_PATTERN = re.compile(r"\b(?:[A-Za-z0-9]{16,}|\d{5,})\b")
_API_SECRET_PATTERN = re.compile(r"(?i)\b(?:api|token|secret|key)[-_ ]?(?:id|key)?=?[A-Za-z0-9_\-]{6,}")


def _truncate_text(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _format_memory_snippet(memories: List[Dict[str, Any]], char_budget: int) -> str:
    lines: List[str] = []
    for memory in memories:
        content = str(memory.get("memory") or "").strip()
        if not content:
            continue
        metadata = memory.get("metadata") or {}
        component = metadata.get("component")
        prefix = f"[{component}] " if component else ""
        score = memory.get("score")
        if isinstance(score, (float, int)):
            formatted = f"{prefix}{content} (score={score:.2f})"
        else:
            formatted = f"{prefix}{content}"
        lines.append(formatted)
    joined = "\n".join(lines)
    return _truncate_text(joined, char_budget)


def _redact_text(text: str) -> str:
    redacted = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    redacted = _API_SECRET_PATTERN.sub("[REDACTED_SECRET]", redacted)
    redacted = _SECRET_PATTERN.sub("[REDACTED]", redacted)
    return redacted


def _distill_facts(answer: str, *, max_facts: int, char_budget: int) -> List[str]:
    if not answer:
        return []

    candidates: List[str] = []
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    for line in lines:
        normalized = line.lstrip("-*•").strip()
        if len(normalized) < 24:
            continue
        candidates.append(normalized)
        if len(candidates) >= max_facts:
            break

    if not candidates:
        sentences = re.split(r"(?<=[.!?])\s+", answer)
        for sentence in sentences:
            normalized = sentence.strip()
            if len(normalized) < 24:
                continue
            candidates.append(normalized)
            if len(candidates) >= max_facts:
                break

    if not candidates:
        return []

    per_item_budget = max(1, char_budget // max_facts) if max_facts else char_budget
    distilled: List[str] = []
    for candidate in candidates:
        redacted = _redact_text(candidate)
        truncated = _truncate_text(redacted, per_item_budget)
        if truncated:
            distilled.append(truncated)
        if len(distilled) >= max_facts:
            break
    return distilled

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
    session_id = getattr(state, "session_id", "default")
    trace_id = getattr(state, "trace_id", None)
    bound_logger = logger.bind(session_id=session_id, trace_id=trace_id)

    should_use_adapter = getattr(settings, "should_use_store_adapter", lambda: False)
    if should_use_adapter():
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

    with tracer.start_as_current_span("orchestration.pre_process") as span:
        span.set_attribute("session.id", session_id)
        if trace_id:
            span.set_attribute("trace.id", trace_id)
        span.set_attribute("cache.query_length", len(user_query))

        # 1. Cache check with secure key
        cache_key = _generate_cache_key(session_id, user_query)
        cached = cache_layer.get(cache_key)
        if cached is not None:
            bound_logger.info("cache_hit")
            span.set_attribute("cache.hit", True)
            updates["cached_response"] = cached
            if global_context:
                state.global_knowledge_context = dict(global_context)
                updates["global_knowledge_context"] = state.global_knowledge_context
            return updates

        # 2. No vector retrieval needed - using Supabase for context
        # Context will be retrieved directly by agents when needed
        bound_logger.info("cache_miss")
        span.set_attribute("cache.hit", False)

        memory_snippet: Optional[str] = None
        if settings.should_enable_agent_memory():
            span.set_attribute("memory.enabled", True)
            memory_cache_key = f"memory:{cache_key}"
            cached_snippet = cache_layer.get(memory_cache_key)
            if isinstance(cached_snippet, str):
                memory_snippet = cached_snippet
                span.set_attribute("memory.cache_hit", True)
            else:
                span.set_attribute("memory.cache_hit", False)
                try:
                    memories = await memory_service.retrieve(PRIMARY_AGENT_ID, user_query, top_k=settings.memory_top_k)
                except Exception as exc:  # pragma: no cover - defensive log
                    bound_logger.warning("memory_retrieval_error", error=str(exc))
                    span.record_exception(exc)
                    memories = []
                span.set_attribute("memory.results_count", len(memories))
                if memories:
                    memory_snippet = _format_memory_snippet(memories, settings.memory_char_budget)
                    cache_layer.set(memory_cache_key, memory_snippet, ttl=settings.memory_ttl_sec)
                    global_context["memory_results"] = memories
        else:
            span.set_attribute("memory.enabled", False)

        should_enable_global = getattr(settings, "should_enable_global_knowledge", lambda: False)
        if should_enable_global():
            retrieval = await retrieve_global_knowledge(
                user_query,
                top_k=settings.global_knowledge_top_k,
            )
            global_context["retrieval"] = retrieval
            if retrieval.get("memory_snippet"):
                global_context["memory_snippet"] = retrieval["memory_snippet"]
            global_context.setdefault("sources", sorted(ALLOWED_SOURCES))
        elif settings.should_enable_agent_memory():
            global_context.setdefault("sources", sorted(ALLOWED_SOURCES))

        if memory_snippet:
            sources = set(global_context.get("sources", []))
            sources.add("memory")
            global_context["sources"] = sorted(sources)
            global_context["memory_snippet"] = memory_snippet

        if global_context:
            state.global_knowledge_context = dict(global_context)
            updates["global_knowledge_context"] = state.global_knowledge_context

        span.set_status(Status(StatusCode.OK))

    return updates  # Empty dict on cache miss aside from optional adapter context

# ---------------------------------------------------------------------------
# Post-processing node
# ---------------------------------------------------------------------------

async def post_process(state: GraphState) -> Dict[str, Any]:
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
    session_id = getattr(state, "session_id", "default")
    trace_id = getattr(state, "trace_id", None)
    bound_logger = logger.bind(session_id=session_id, trace_id=trace_id)

    with tracer.start_as_current_span("orchestration.post_process") as span:
        span.set_attribute("session.id", session_id)
        if trace_id:
            span.set_attribute("trace.id", trace_id)
        span.set_attribute("cache.write_length", len(agent_response))

        # Cache store with secure key and TTL (1 hour = 3600 seconds)
        cache_key = _generate_cache_key(session_id, user_query)
        cache_layer.set(cache_key, agent_response, ttl=3600)

        bound_logger.info("post_process_cache_store")
        persisted = await _maybe_persist_memory(state, user_query, agent_response)
        span.set_attribute("memory.persisted_count", persisted)
        span.set_status(Status(StatusCode.OK))

    return {"qa_retry_count": 0}

from langchain_core.messages import HumanMessage, AIMessage

async def run_researcher(state: GraphState):
    """
    Runs the research agent graph asynchronously using the last user query,
    and appends a synthesized answer + citations to the messages.
    """
    timeout_sec = getattr(settings, "node_timeout_sec", 30.0)
    trace_id = getattr(state, "trace_id", None)
    session_id = getattr(state, "session_id", "default")
    bound_logger = logger.bind(trace_id=trace_id, session_id=session_id)
    bound_logger.debug("running_researcher_async", timeout_sec=timeout_sec)
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
    with tracer.start_as_current_span("orchestration.run_researcher") as span:
        span.set_attribute("session.id", session_id)
        if trace_id:
            span.set_attribute("trace.id", trace_id)
        span.set_attribute("research.timeout_sec", timeout_sec)

        try:
            final_state = await asyncio.wait_for(
                research_agent_graph.ainvoke(initial_state),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            bound_logger.warning("research_agent_timeout", timeout_sec=timeout_sec)
            span.set_status(Status(StatusCode.ERROR, "timeout"))
            timeout_msg = AIMessage(
                content="I couldn't complete the external research in time, so I'll continue with the information already gathered."
            )
            return {"messages": state.messages + [timeout_msg]}
        except Exception as exc:  # pragma: no cover - defensive logging
            bound_logger.exception("research_agent_error")
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        else:
            span.set_status(Status(StatusCode.OK))

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


def _resolve_reflection_confidence(state: GraphState) -> Optional[float]:
    """Extract confidence score from reflection feedback if present."""
    feedback = getattr(state, "reflection_feedback", None)
    if feedback is None:
        return None
    if isinstance(feedback, dict):
        value = feedback.get("confidence_score")
        return float(value) if isinstance(value, (float, int)) else None
    return getattr(feedback, "confidence_score", None)


async def _maybe_persist_memory(state: GraphState, user_query: str, agent_response: str) -> int:
    """Persist distilled facts to long-term memory when enabled."""
    if not settings.should_enable_agent_memory():
        return 0

    confidence = _resolve_reflection_confidence(state)
    if confidence is not None and confidence < 0.6:
        return 0

    facts = _distill_facts(agent_response, max_facts=3, char_budget=settings.memory_char_budget)
    if not facts:
        return 0

    metadata = {
        "memory_type": PRIMARY_MEMORY_TYPE,
        "source": PRIMARY_MEMORY_SOURCE,
        "confidence": confidence,
        "query_hash": hashlib.blake2b(user_query.encode("utf-8"), digest_size=16).hexdigest(),
        "session_id": getattr(state, "session_id", None),
        "trace_id": getattr(state, "trace_id", None),
    }
    cleaned_meta = {k: v for k, v in metadata.items() if v is not None}

    try:
        await memory_service.add_facts(
            agent_id=PRIMARY_AGENT_ID,
            facts=facts,
            meta=cleaned_meta,
        )
    except Exception as exc:  # pragma: no cover - best effort logging
        logger.warning("memory_write_failed", error=str(exc))
        return 0

    return len(facts)

# Helper function to decide what to do after an agent is called
def should_continue(state: GraphState):
    """
    Determines whether to continue with tool execution or end the flow.
    """
    last_message = state.messages[-1]
    if not last_message.tool_calls:
        return "end"
    return "continue"
def configure_research_agent_graph(checkpointer: Optional[object]) -> None:
    """
    Recompile the research subgraph with the supplied checkpointer.

    Args:
        checkpointer: Shared checkpointer from the primary orchestration graph.
            If None, falls back to the module-level MemorySaver instance.
    """
    global research_agent_graph, _current_research_checkpointer

    effective = checkpointer or _default_research_checkpointer
    if _current_research_checkpointer is effective:
        return

    research_agent_graph = get_research_graph(checkpointer=effective)
    logger.info(
        "research_graph_checkpointer_configured",
        checkpointer_type=type(effective).__name__,
    )
    _current_research_checkpointer = effective
