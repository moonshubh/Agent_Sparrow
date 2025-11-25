"""DeepAgents subagent specifications for the unified agent.

This module defines subagent specifications following DeepAgents patterns,
with proper middleware composition for each subagent type.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from loguru import logger

from app.core.settings import settings

from .prompts import LOG_ANALYSIS_PROMPT, RESEARCH_PROMPT
from .tools import (
    grounding_search_tool,
    kb_search_tool,
    log_diagnoser_tool,
    web_search_tool,
    feedme_search_tool,
    supabase_query_tool,
)
from .model_router import model_router

# Import middleware classes for per-subagent configuration
try:
    # LangChain provides TodoList and Summarization middleware
    from langchain.agents.middleware import TodoListMiddleware
    from langchain.agents.middleware.summarization import SummarizationMiddleware

    # DeepAgents provides PatchToolCalls middleware
    from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware

    MIDDLEWARE_AVAILABLE = True
except ImportError:
    # Fallback if middleware not available
    MIDDLEWARE_AVAILABLE = False
    logger.warning("DeepAgents middleware not available - subagents will run without middleware")

# Import custom middleware
try:
    from app.agents.harness.middleware import ToolResultEvictionMiddleware

    CUSTOM_MIDDLEWARE_AVAILABLE = True
except ImportError:
    CUSTOM_MIDDLEWARE_AVAILABLE = False


# Middleware configuration constants
RESEARCH_MAX_TOKENS_BEFORE_SUMMARY = 100000
RESEARCH_MESSAGES_TO_KEEP = 4
LOG_ANALYSIS_MAX_TOKENS_BEFORE_SUMMARY = 150000
LOG_ANALYSIS_MESSAGES_TO_KEEP = 6


def _get_chat_model(model_name: str) -> ChatGoogleGenerativeAI:
    """Create a pre-initialized ChatGoogleGenerativeAI instance."""
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0.3,
        google_api_key=settings.gemini_api_key,
    )


def _build_research_middleware(model: ChatGoogleGenerativeAI) -> List[Any]:
    """Build middleware stack for research subagent.

    Research agent middleware:
    1. SummarizationMiddleware - Compact long conversations
    2. ToolResultEvictionMiddleware - Evict large search results
    3. PatchToolCallsMiddleware - Normalize tool call format
    """
    middleware: List[Any] = []

    if not MIDDLEWARE_AVAILABLE:
        return middleware

    # Summarization for long research conversations
    middleware.append(
        SummarizationMiddleware(
            model=model,
            max_tokens_before_summary=RESEARCH_MAX_TOKENS_BEFORE_SUMMARY,
            messages_to_keep=RESEARCH_MESSAGES_TO_KEEP,
        )
    )

    # Evict large search results to prevent context overflow
    if CUSTOM_MIDDLEWARE_AVAILABLE:
        middleware.append(ToolResultEvictionMiddleware(char_threshold=60000))

    # NOTE: PatchToolCallsMiddleware is NOT added here because it's already
    # included in SubAgentMiddleware's default_middleware in agent_sparrow.py.
    # Adding it here would cause "duplicate middleware instances" error.

    return middleware


def _build_log_analysis_middleware(model: ChatGoogleGenerativeAI) -> List[Any]:
    """Build middleware stack for log analysis subagent.

    Log analysis agent middleware:
    1. SummarizationMiddleware - Handle long log analysis sessions
    2. PatchToolCallsMiddleware - Normalize tool call format

    Note: No eviction middleware - log analysis needs full context.
    """
    middleware: List[Any] = []

    if not MIDDLEWARE_AVAILABLE:
        return middleware

    # Summarization with higher threshold for log analysis
    middleware.append(
        SummarizationMiddleware(
            model=model,
            max_tokens_before_summary=LOG_ANALYSIS_MAX_TOKENS_BEFORE_SUMMARY,
            messages_to_keep=LOG_ANALYSIS_MESSAGES_TO_KEEP,
        )
    )

    # NOTE: PatchToolCallsMiddleware is NOT added here because it's already
    # included in SubAgentMiddleware's default_middleware in agent_sparrow.py.
    # Adding it here would cause "duplicate middleware instances" error.

    return middleware


def _research_subagent() -> Dict[str, Any]:
    """Create research subagent specification.

    The research agent gathers supporting evidence from:
    - Mailbird knowledge base (kb_search)
    - FeedMe document chunks (feedme_search)
    - Supabase database (supabase_query)
    - Google grounding search (grounding_search)
    - Tavily web search (web_search)
    """
    model_name = model_router.select_model("lightweight")
    model = _get_chat_model(model_name)

    subagent_spec: Dict[str, Any] = {
        "name": "research-agent",
        "description": (
            "Deep research agent with access to KB, FeedMe documents, and web search. "
            "Use for gathering evidence, fact-checking, and finding relevant information."
        ),
        "system_prompt": RESEARCH_PROMPT,
        "tools": [
            kb_search_tool,
            feedme_search_tool,
            supabase_query_tool,
            grounding_search_tool,
            web_search_tool,
        ],
        "model": model,
        "middleware": _build_research_middleware(model),
    }

    logger.debug(
        "research_subagent_created",
        model=model_name,
        tools=[t.name for t in subagent_spec["tools"]],
        middleware_count=len(subagent_spec["middleware"]),
    )

    return subagent_spec


def _log_diagnoser_subagent() -> Dict[str, Any]:
    """Create log diagnoser subagent specification.

    The log diagnoser specializes in:
    - Analyzing attached log files (log_diagnoser)
    - Cross-referencing with KB (kb_search)
    - Finding related documentation (feedme_search)
    - Querying historical issues (supabase_query)
    """
    model_name = model_router.select_model("log_analysis")
    model = _get_chat_model(model_name)

    subagent_spec: Dict[str, Any] = {
        "name": "log-diagnoser",
        "description": (
            "Specialized log analysis agent. Use when user provides log files or asks "
            "about errors, troubleshooting, or system issues."
        ),
        "system_prompt": LOG_ANALYSIS_PROMPT,
        "tools": [
            log_diagnoser_tool,
            kb_search_tool,
            feedme_search_tool,
            supabase_query_tool,
        ],
        "model": model,
        "middleware": _build_log_analysis_middleware(model),
    }

    logger.debug(
        "log_diagnoser_subagent_created",
        model=model_name,
        tools=[t.name for t in subagent_spec["tools"]],
        middleware_count=len(subagent_spec["middleware"]),
    )

    return subagent_spec


def get_subagent_specs() -> List[Dict[str, Any]]:
    """Return subagent specifications consumed by DeepAgents.

    Returns:
        List of subagent specification dicts with:
        - name: Unique identifier
        - description: Human-readable description for routing
        - system_prompt: System prompt for the subagent
        - tools: List of available tools
        - model: ChatModel instance
        - middleware: List of middleware instances
    """
    return [_research_subagent(), _log_diagnoser_subagent()]


def get_subagent_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Get a specific subagent specification by name.

    Args:
        name: Subagent name (e.g., "research-agent", "log-diagnoser").

    Returns:
        Subagent spec dict or None if not found.
    """
    for spec in get_subagent_specs():
        if spec["name"] == name:
            return spec
    return None
