"""DeepAgents subagent specifications for the unified agent.

This module defines subagent specifications following DeepAgents patterns,
with proper middleware composition for each subagent type.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from loguru import logger

from app.core.settings import settings
from app.core.config import get_registry

from .prompts import LOG_ANALYSIS_PROMPT, RESEARCH_PROMPT, DATABASE_RETRIEVAL_PROMPT
from .tools import (
    grounding_search_tool,
    kb_search_tool,
    log_diagnoser_tool,
    web_search_tool,
    feedme_search_tool,
    supabase_query_tool,
    get_db_retrieval_tools,
    # Firecrawl tools for enhanced web scraping
    firecrawl_fetch_tool,
    firecrawl_map_tool,
    firecrawl_crawl_tool,
    firecrawl_extract_tool,
    firecrawl_search_tool,
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
DB_RETRIEVAL_MAX_TOKENS_BEFORE_SUMMARY = 80000
DB_RETRIEVAL_MESSAGES_TO_KEEP = 3


def _get_chat_model(model_name: str, provider: str = "google", role: str = "default") -> BaseChatModel:
    """Create a pre-initialized chat model instance using the provider factory.

    Uses role-based temperature selection from provider_factory.TEMPERATURE_CONFIG.

    Args:
        model_name: The model identifier.
        provider: The provider name ("google" or "xai"). Defaults to "google".
        role: The agent role for temperature selection (e.g., "research", "log_analysis").
            Uses TEMPERATURE_CONFIG to select appropriate temperature per role.

    Returns:
        A configured chat model instance.
    """
    from .provider_factory import build_chat_model

    return build_chat_model(
        provider=provider,
        model=model_name,
        role=role,  # Role-based temperature selection
    )


def _build_research_middleware(model: BaseChatModel) -> List[Any]:
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


def _build_log_analysis_middleware(model: BaseChatModel) -> List[Any]:
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


def _build_db_retrieval_middleware(model: BaseChatModel) -> List[Any]:
    """Build lightweight middleware stack for db retrieval subagent.

    DB retrieval agent middleware:
    1. SummarizationMiddleware - Compact long retrieval sessions

    Note: Minimal middleware since retrieval is typically single-step.
    """
    middleware: List[Any] = []

    if not MIDDLEWARE_AVAILABLE:
        return middleware

    # Summarization with lower threshold for quick retrieval operations
    middleware.append(
        SummarizationMiddleware(
            model=model,
            max_tokens_before_summary=DB_RETRIEVAL_MAX_TOKENS_BEFORE_SUMMARY,
            messages_to_keep=DB_RETRIEVAL_MESSAGES_TO_KEEP,
        )
    )

    return middleware


def _get_subagent_model_for_provider(
    task_type: str,
    provider: str,
    role: str = "default",
) -> tuple[str, BaseChatModel]:
    """Get the appropriate model for a subagent based on provider.

    For Google provider, uses the model router to select the best model.
    For XAI/Grok provider, uses appropriate Grok models from registry.
    For OpenRouter, uses the OpenRouter defaults from registry/settings.

    Args:
        task_type: The task type for model selection (e.g., "lightweight", "log_analysis").
        provider: The provider name ("google", "xai", or "openrouter").
        role: The agent role for temperature selection (e.g., "research", "log_analysis").

    Returns:
        Tuple of (model_name, model_instance).
    """
    provider = provider.lower().strip()
    registry = get_registry()

    if provider == "xai":
        # Map task types to appropriate Grok models from registry
        xai_default = registry.coordinator_xai.id
        xai_model_map = {
            "lightweight": xai_default,
            "db_retrieval": xai_default,
            "log_analysis": xai_default,  # Use default XAI model for analysis
            "coordinator": xai_default,
        }
        model_name = xai_model_map.get(task_type, xai_default)
        model = _get_chat_model(model_name, provider="xai", role=role)
        return model_name, model

    if provider == "openrouter":
        or_default = registry.coordinator_openrouter.id
        or_model_map = {
            "lightweight": or_default,
            "db_retrieval": or_default,
            "log_analysis": or_default,
            "coordinator": or_default,
            "coordinator_heavy": or_default,
        }
        model_name = or_model_map.get(task_type, or_default)
        model = _get_chat_model(model_name, provider="openrouter", role=role)
        return model_name, model

    # Default to Google provider
    model_name = model_router.select_model(task_type)
    model = _get_chat_model(model_name, provider="google", role=role)
    return model_name, model


def _research_subagent(provider: str = "google") -> Dict[str, Any]:
    """Create research subagent specification.

    Standard tier agent with streamlined 4-step workflow (Search → Evaluate → Synthesize → Cite).
    Uses creative temperature (0.5) for source synthesis.

    The research agent gathers supporting evidence from:
    - Mailbird knowledge base (kb_search)
    - FeedMe document chunks (feedme_search)
    - Supabase database (supabase_query)
    - Google grounding search (grounding_search)
    - Tavily web search (web_search)
    - Firecrawl tools (fetch, map, crawl, extract, search)

    Args:
        provider: The provider name ("google" or "xai"). Defaults to "google".
    """
    model_name, model = _get_subagent_model_for_provider("lightweight", provider, role="research")

    subagent_spec: Dict[str, Any] = {
        "name": "research-agent",
        "description": (
            "Deep research agent with access to KB, FeedMe documents, web search, and "
            "Firecrawl for advanced web scraping. Use for gathering evidence, fact-checking, "
            "extracting structured data, and finding relevant information from any website."
        ),
        "system_prompt": RESEARCH_PROMPT,
        "tools": [
            kb_search_tool,
            feedme_search_tool,
            supabase_query_tool,
            grounding_search_tool,
            web_search_tool,
            # Firecrawl tools for advanced web research
            firecrawl_fetch_tool,      # Single-page scrape with screenshots/actions
            firecrawl_map_tool,        # Discover all URLs on a website
            firecrawl_crawl_tool,      # Multi-page extraction
            firecrawl_extract_tool,    # AI-powered structured data extraction
            firecrawl_search_tool,     # Enhanced web search (web/images/news)
        ],
        "model": model,
        "middleware": _build_research_middleware(model),
    }

    logger.debug(
        "research_subagent_created",
        model=model_name,
        provider=provider,
        tools=[t.name for t in subagent_spec["tools"]],
        middleware_count=len(subagent_spec["middleware"]),
    )

    return subagent_spec


def _log_diagnoser_subagent(provider: str = "google") -> Dict[str, Any]:
    """Create log diagnoser subagent specification.

    Heavy tier agent with full 9-step reasoning framework for complex log analysis.
    Uses high-precision temperature (0.1) for accurate error diagnosis.

    The log diagnoser specializes in:
    - Analyzing attached log files (log_diagnoser)
    - Cross-referencing with KB (kb_search)
    - Finding related documentation (feedme_search)
    - Querying historical issues (supabase_query)
    - Researching error messages online (Firecrawl tools)

    Args:
        provider: The provider name ("google" or "xai"). Defaults to "google".
    """
    # Temporarily force Gemini 3.0 Pro (preview) for log diagnosis unless explicitly overridden
    if provider == "google":
        model_name = getattr(settings, "zendesk_log_model_override", None) or "gemini-3-pro-preview"
        model = _get_chat_model(model_name, provider="google", role="log_analysis")
    else:
        model_name, model = _get_subagent_model_for_provider("log_analysis", provider, role="log_analysis")

    subagent_spec: Dict[str, Any] = {
        "name": "log-diagnoser",
        "description": (
            "Specialized log analysis agent with web research capabilities. Use when user "
            "provides log files or asks about errors, troubleshooting, or system issues. "
            "Can research error messages and solutions online using Firecrawl."
        ),
        "system_prompt": LOG_ANALYSIS_PROMPT,
        "tools": [
            log_diagnoser_tool,
            kb_search_tool,
            feedme_search_tool,
            supabase_query_tool,
            # Firecrawl tools for researching errors and solutions online
            firecrawl_fetch_tool,      # Fetch documentation/solutions from URLs
            firecrawl_search_tool,     # Search for error messages and fixes
            firecrawl_extract_tool,    # Extract structured error/solution data
        ],
        "model": model,
        "middleware": _build_log_analysis_middleware(model),
    }

    logger.debug(
        "log_diagnoser_subagent_created",
        model=model_name,
        provider=provider,
        tools=[t.name for t in subagent_spec["tools"]],
        middleware_count=len(subagent_spec["middleware"]),
    )

    return subagent_spec


def _db_retrieval_subagent(provider: str = "google") -> Dict[str, Any]:
    """Create database retrieval subagent specification.

    Lite tier agent with minimal task-focused prompts for cost-efficient data retrieval.
    Uses high-precision temperature (0.1) for exact pattern matching.

    The db retrieval agent specializes in:
    - Semantic search across KB, macros, FeedMe (db_unified_search)
    - Pattern-based grep search (db_grep_search)
    - Full document context retrieval (db_context_search)

    Uses lightweight models for cost-efficient retrieval:
    - Google: Gemini Flash Lite (~50% cost savings vs Flash)
    - XAI: Grok mini models for fast retrieval

    Returns FULL content for KB/macros, polished summaries for long FeedMe.
    Does NOT synthesize - only retrieves and formats data.

    Args:
        provider: The provider name ("google" or "xai"). Defaults to "google".
    """
    model_name, model = _get_subagent_model_for_provider("db_retrieval", provider, role="db_retrieval")

    subagent_spec: Dict[str, Any] = {
        "name": "db-retrieval",
        "description": (
            "Database retrieval specialist for KB articles, Zendesk macros, "
            "and FeedMe history. Returns structured results with relevance "
            "scores. Does NOT synthesize - only retrieves and formats data. "
            "Use for finding specific information before synthesis."
        ),
        "system_prompt": DATABASE_RETRIEVAL_PROMPT,
        "tools": get_db_retrieval_tools(),
        "model": model,
        "middleware": _build_db_retrieval_middleware(model),
    }

    logger.debug(
        "db_retrieval_subagent_created",
        model=model_name,
        provider=provider,
        tools=[t.name for t in subagent_spec["tools"]],
        middleware_count=len(subagent_spec["middleware"]),
    )

    return subagent_spec


def get_subagent_specs(provider: str = "google") -> List[Dict[str, Any]]:
    """Return subagent specifications consumed by DeepAgents.

    Args:
        provider: The provider name ("google" or "xai"). Defaults to "google".
            When the coordinator uses Grok, pass "xai" to create subagents
            with Grok models. Otherwise, subagents use Gemini models.

    Returns:
        List of subagent specification dicts with:
        - name: Unique identifier
        - description: Human-readable description for routing
        - system_prompt: System prompt for the subagent
        - tools: List of available tools
        - model: ChatModel instance (matching the provider)
        - middleware: List of middleware instances
    """
    logger.info(
        "creating_subagent_specs",
        provider=provider,
    )
    return [
        _research_subagent(provider=provider),
        _log_diagnoser_subagent(provider=provider),
        _db_retrieval_subagent(provider=provider),
    ]


def get_subagent_by_name(name: str, provider: str = "google") -> Optional[Dict[str, Any]]:
    """Get a specific subagent specification by name.

    Args:
        name: Subagent name (e.g., "research-agent", "log-diagnoser", "db-retrieval").
        provider: The provider name ("google" or "xai"). Defaults to "google".

    Returns:
        Subagent spec dict or None if not found.
    """
    for spec in get_subagent_specs(provider=provider):
        if spec["name"] == name:
            return spec
    return None
