"""DeepAgents subagent specifications for the unified agent.

This module defines subagent specifications following DeepAgents patterns,
with proper middleware composition for each subagent type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from loguru import logger

from app.core.config import (
    coordinator_bucket_name,
    get_models_config,
    resolve_coordinator_config,
    resolve_subagent_config,
)
from app.core.settings import settings
from app.core.rate_limiting.agent_wrapper import RateLimitedAgent, wrap_gemini_agent
from .model_router import model_router

from .prompts import (
    DATABASE_RETRIEVAL_PROMPT,
    EXPLORER_PROMPT,
    LOG_ANALYSIS_PROMPT,
    RESEARCH_PROMPT,
    get_current_utc_date,
)
from .tools import (
    grounding_search_tool,
    kb_search_tool,
    log_diagnoser_tool,
    web_search_tool,
    tavily_extract_tool,
    feedme_search_tool,
    get_db_retrieval_tools,
    memory_list_tool,
    memory_search_tool,
    supabase_query_tool,
    is_firecrawl_agent_enabled,
    # Firecrawl tools for enhanced web scraping (MCP-backed)
    firecrawl_fetch_tool,
    firecrawl_map_tool,
    firecrawl_crawl_tool,
    firecrawl_extract_tool,
    firecrawl_search_tool,
    firecrawl_agent_tool,       # NEW: Autonomous data gathering
    firecrawl_agent_status_tool,  # NEW: Check agent job status
)
from .minimax_tools import (
    minimax_web_search_tool,
    minimax_understand_image_tool,
    is_minimax_available,
)

# Import middleware classes for per-subagent configuration
try:
    # LangChain provides TodoList and Summarization middleware
    from langchain.agents.middleware import TodoListMiddleware
    from langchain.agents.middleware.summarization import (
        SummarizationMiddleware,
        count_tokens_approximately,
    )

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


@dataclass(frozen=True)
class MiddlewareConfig:
    """Per-subagent middleware thresholds."""

    max_tokens_before_summary: int
    messages_to_keep: int


RESEARCH_MW_CONFIG = MiddlewareConfig(max_tokens_before_summary=100000, messages_to_keep=4)
LOG_ANALYSIS_MW_CONFIG = MiddlewareConfig(max_tokens_before_summary=150000, messages_to_keep=6)
DB_RETRIEVAL_MW_CONFIG = MiddlewareConfig(max_tokens_before_summary=80000, messages_to_keep=3)


def _subagent_read_tools() -> List[BaseTool]:
    """Shared read/search tools available to all subagents."""
    return [
        memory_search_tool,
        memory_list_tool,
        web_search_tool,
        tavily_extract_tool,
        grounding_search_tool,
        firecrawl_search_tool,
        firecrawl_fetch_tool,
    ]


def _merge_tools(
    tools: List[BaseTool],
    extra: Optional[List[BaseTool]] = None,
) -> List[BaseTool]:
    """Merge tool lists with stable ordering and name-based deduplication."""
    if not extra:
        return tools

    seen: set[str] = set()
    merged: list[BaseTool] = []
    for tool in [*tools, *extra]:
        name = getattr(tool, "name", None)
        if not isinstance(name, str) or not name:
            merged.append(tool)
            continue
        if name in seen:
            continue
        seen.add(name)
        merged.append(tool)
    return merged

def _get_chat_model(
    model_name: str,
    *,
    provider: str = "google",
    role: str = "default",
    temperature: float | None = None,
) -> BaseChatModel:
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
        temperature=temperature,
        role=role,  # Role-based temperature selection
    )


def _summarization_token_counter(model: BaseChatModel) -> Any:
    """Return a token counter safe for models without LangChain metadata."""
    if hasattr(model, "_llm_type"):
        return count_tokens_approximately

    def _counter(messages: Any) -> int:
        return count_tokens_approximately(messages)

    return _counter


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
            trigger=("tokens", RESEARCH_MW_CONFIG.max_tokens_before_summary),
            keep=("messages", RESEARCH_MW_CONFIG.messages_to_keep),
            token_counter=_summarization_token_counter(model),
        )
    )

    # NOTE: ToolResultEvictionMiddleware is NOT added here because it's already
    # included in SubAgentMiddleware's default_middleware in agent_sparrow.py.
    # Adding it here would cause "duplicate middleware instances" error.

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
            trigger=("tokens", LOG_ANALYSIS_MW_CONFIG.max_tokens_before_summary),
            keep=("messages", LOG_ANALYSIS_MW_CONFIG.messages_to_keep),
            token_counter=_summarization_token_counter(model),
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
            trigger=("tokens", DB_RETRIEVAL_MW_CONFIG.max_tokens_before_summary),
            keep=("messages", DB_RETRIEVAL_MW_CONFIG.messages_to_keep),
            token_counter=_summarization_token_counter(model),
        )
    )

    return middleware


def _provider_api_key_available(provider: str) -> bool:
    provider_key = (provider or "google").strip().lower()
    if provider_key == "google":
        return bool(settings.gemini_api_key)
    if provider_key == "xai":
        return bool(settings.xai_api_key)
    if provider_key == "openrouter":
        # OpenRouter is available if either OpenRouter key or Minimax key is set
        # (Minimax models route through OpenRouter code path)
        return bool(getattr(settings, "openrouter_api_key", None)) or bool(
            getattr(settings, "minimax_api_key", None)
        ) or bool(getattr(settings, "minimax_coding_plan_api_key", None))
    return False


def _is_minimax_model(model_id: str) -> bool:
    """Check if a model is a Minimax model.

    Args:
        model_id: The model identifier (e.g., "minimax/MiniMax-M2.1").

    Returns:
        True if the model is a Minimax model.
    """
    return "minimax" in (model_id or "").lower()


def _fallback_to_coordinator(
    *,
    config,
    role: str,
    zendesk: bool,
) -> tuple[str, str, BaseChatModel, str]:
    fallback_provider = config.fallback.coordinator_provider
    coordinator_cfg = resolve_coordinator_config(
        config,
        fallback_provider,
        with_subagents=True,
        zendesk=zendesk,
    )
    bucket_name = coordinator_bucket_name(
        fallback_provider,
        with_subagents=True,
        zendesk=zendesk,
    )
    model = _get_chat_model(
        coordinator_cfg.model_id,
        provider=fallback_provider,
        role=role,
        temperature=coordinator_cfg.temperature,
    )
    return coordinator_cfg.model_id, fallback_provider, model, bucket_name


def _get_subagent_model(
    subagent_name: str,
    role: str,
    *,
    zendesk: bool = False,
) -> tuple[str, str, BaseChatModel]:
    """Return the subagent model from YAML config with _default fallback."""
    config = get_models_config()
    subagent_config = resolve_subagent_config(config, subagent_name, zendesk=zendesk)
    model_name = subagent_config.model_id
    provider = subagent_config.provider or "google"
    bucket_name = (
        f"zendesk.subagents.{subagent_name}" if zendesk else f"subagents.{subagent_name}"
    )

    if not _provider_api_key_available(provider):
        logger.warning(
            "subagent_provider_unavailable",
            subagent=subagent_name,
            provider=provider,
        )
        model_name, provider, model, bucket_name = _fallback_to_coordinator(
            config=config,
            role=role,
            zendesk=zendesk,
        )
    elif not model_router.is_available(model_name):
        if getattr(settings, "subagent_allow_unverified_models", False):
            logger.warning(
                "subagent_model_allowlist_blocked",
                subagent=subagent_name,
                model=model_name,
                provider=provider,
                action="allow_unverified",
            )
            model = _get_chat_model(
                model_name,
                provider=provider,
                role=role,
                temperature=subagent_config.temperature,
            )
        else:
            logger.warning(
                "subagent_model_allowlist_blocked",
                subagent=subagent_name,
                model=model_name,
                provider=provider,
                action="fallback_to_coordinator",
            )
            model_name, provider, model, bucket_name = _fallback_to_coordinator(
                config=config,
                role=role,
                zendesk=zendesk,
            )
    else:
        model = _get_chat_model(
            model_name,
            provider=provider,
            role=role,
            temperature=subagent_config.temperature,
        )

    if model.__class__.__name__ == "ChatGoogleGenerativeAI":
        model = cast(BaseChatModel, wrap_gemini_agent(model, bucket_name, model_name))
    else:
        model = cast(BaseChatModel, RateLimitedAgent(model, bucket_name))
    return model_name, provider, model


def _research_subagent(
    *,
    zendesk: bool = False,
    workspace_tools: Optional[List[BaseTool]] = None,
) -> Dict[str, Any]:
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
    - Minimax tools (web_search, understand_image) - prioritized when Minimax MCP is available

    """
    model_name, provider, model = _get_subagent_model(
        "research-agent",
        role="research",
        zendesk=zendesk,
    )
    current_date = get_current_utc_date()

    # Prioritize Minimax MCP tools whenever available (regardless of model choice).
    use_minimax = is_minimax_available()

    tools: List[BaseTool] = [
        kb_search_tool,
        feedme_search_tool,
        supabase_query_tool,
        firecrawl_fetch_tool,
        firecrawl_map_tool,
        firecrawl_crawl_tool,
        firecrawl_extract_tool,
        firecrawl_search_tool,
        *(
            [firecrawl_agent_tool]
            if is_firecrawl_agent_enabled()
            else []
        ),
        firecrawl_agent_status_tool,
        web_search_tool,
        tavily_extract_tool,
        grounding_search_tool,
        *_subagent_read_tools(),
    ]
    if use_minimax:
        tools = [
            minimax_web_search_tool,       # AI-powered web search via Minimax
            minimax_understand_image_tool, # Image analysis via Minimax vision
            *tools,
        ]
        logger.info(
            "research_subagent_minimax_tools_prioritized",
            model=model_name,
            minimax_tools=["minimax_web_search", "minimax_understand_image"],
        )

    subagent_spec: Dict[str, Any] = {
        "name": "research-agent",
        "description": (
            "Deep research agent with access to KB, FeedMe documents, web search, and "
            "Firecrawl for advanced web scraping. Use for gathering evidence, fact-checking, "
            "extracting structured data, autonomous web research, and finding relevant "
            "information from any website. Can autonomously gather data without knowing URLs."
            + (" Also has Minimax vision for image analysis." if use_minimax else "")
        ),
        "system_prompt": f"{RESEARCH_PROMPT}\n\nCurrent date: {current_date}",
        "tools": _merge_tools(tools, workspace_tools),
        "model": model,
        "model_name": model_name,
        "model_provider": provider,
        "middleware": _build_research_middleware(model),
    }

    logger.debug(
        "research_subagent_created",
        model=model_name,
        provider=provider,
        tools=[t.name for t in subagent_spec["tools"]],
        middleware_count=len(subagent_spec["middleware"]),
        minimax_prioritized=use_minimax,
    )

    return subagent_spec


def _log_diagnoser_subagent(
    *,
    zendesk: bool = False,
    workspace_tools: Optional[List[BaseTool]] = None,
) -> Dict[str, Any]:
    """Create log diagnoser subagent specification.

    Heavy tier agent with full 9-step reasoning framework for complex log analysis.
    Uses high-precision temperature (0.1) for accurate error diagnosis.

    The log diagnoser specializes in:
    - Analyzing attached log files (directly in prompt context)
    - Producing customer-ready + internal diagnostic notes in the Phase 3 JSON contract
    - When using Minimax: Can also analyze error screenshots via image understanding

    """
    model_name, provider, model = _get_subagent_model(
        "log-diagnoser",
        role="log_analysis",
        zendesk=zendesk,
    )
    current_date = get_current_utc_date()

    # Prefer Minimax MCP tools whenever available.
    use_minimax = is_minimax_available()

    # Log diagnoser is typically minimal, but Minimax image understanding is useful
    # for analyzing error screenshots
    tools = []
    if use_minimax:
        tools.extend([
            minimax_understand_image_tool,  # Analyze error screenshots
            minimax_web_search_tool,        # Research error messages
        ])
        logger.info(
            "log_diagnoser_subagent_minimax_tools_added",
            model=model_name,
            minimax_tools=["minimax_understand_image", "minimax_web_search"],
        )
    tools.extend(_subagent_read_tools())

    subagent_spec: Dict[str, Any] = {
        "name": "log-diagnoser",
        "description": (
            "Specialized log analysis agent with web research capabilities. Use when user "
            "provides log files or asks about errors, troubleshooting, or system issues. "
            "Can research error messages and solutions online."
            + (" Can also analyze error screenshots using Minimax vision." if use_minimax else "")
        ),
        "system_prompt": f"{LOG_ANALYSIS_PROMPT}\n\nCurrent date: {current_date}",
        # Keep the log diagnoser deterministic and fast: analyze the provided log
        # text directly and return the strict JSON output contract.
        "tools": _merge_tools(tools, workspace_tools),
        "model": model,
        "model_name": model_name,
        "model_provider": provider,
        "middleware": _build_log_analysis_middleware(model),
    }

    logger.debug(
        "log_diagnoser_subagent_created",
        model=model_name,
        provider=provider,
        tools=[t.name for t in subagent_spec["tools"]],
        middleware_count=len(subagent_spec["middleware"]),
        minimax_prioritized=use_minimax,
    )

    return subagent_spec


def _db_retrieval_subagent(
    *,
    zendesk: bool = False,
    workspace_tools: Optional[List[BaseTool]] = None,
) -> Dict[str, Any]:
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

    """
    model_name, provider, model = _get_subagent_model(
        "db-retrieval",
        role="db_retrieval",
        zendesk=zendesk,
    )
    current_date = get_current_utc_date()

    use_minimax = is_minimax_available()
    tools = []
    if use_minimax:
        tools.extend([
            minimax_web_search_tool,
            minimax_understand_image_tool,
        ])
        logger.info(
            "db_retrieval_subagent_minimax_tools_added",
            model=model_name,
            minimax_tools=["minimax_web_search", "minimax_understand_image"],
        )
    tools.extend(get_db_retrieval_tools())
    tools.extend(_subagent_read_tools())

    subagent_spec: Dict[str, Any] = {
        "name": "db-retrieval",
        "description": (
            "Database retrieval specialist for KB articles, Zendesk macros, "
            "and FeedMe history. Returns structured results with relevance "
            "scores. Does NOT synthesize - only retrieves and formats data. "
            "Use for finding specific information before synthesis."
        ),
        "system_prompt": f"{DATABASE_RETRIEVAL_PROMPT}\n\nCurrent date: {current_date}",
        "tools": _merge_tools(tools, workspace_tools),
        "preferred_tool_priority": [
            "db_unified_search",  # semantic/hybrid first
            "db_context_search",  # full doc/context retrieval
            "db_grep_search",     # exact/pattern matches
        ],
        "model": model,
        "model_name": model_name,
        "model_provider": provider,
        "middleware": _build_db_retrieval_middleware(model),
    }

    logger.debug(
        "db_retrieval_subagent_created",
        model=model_name,
        provider=provider,
        tools=[t.name for t in subagent_spec["tools"]],
        middleware_count=len(subagent_spec["middleware"]),
        minimax_prioritized=use_minimax,
    )

    return subagent_spec


def _explorer_subagent(
    *,
    zendesk: bool = False,
    workspace_tools: Optional[List[BaseTool]] = None,
) -> Dict[str, Any]:
    """Create explorer subagent specification (suggestions-only).

    Phase 2 requirement:
    - Read/search/list capabilities only.
    - Suggestions-only output contract (no final answers, no actions).
    - Minimax tools prioritized when Minimax MCP is available.
    """
    model_name, provider, model = _get_subagent_model(
        "explorer",
        role="research",
        zendesk=zendesk,
    )
    current_date = get_current_utc_date()

    # Prefer Minimax MCP tools whenever available.
    use_minimax = is_minimax_available()

    tools: List[BaseTool] = [
        kb_search_tool,
        feedme_search_tool,
        firecrawl_search_tool,
        firecrawl_fetch_tool,
        firecrawl_map_tool,
        firecrawl_extract_tool,
        web_search_tool,
        tavily_extract_tool,
        grounding_search_tool,
        *_subagent_read_tools(),
    ]
    if use_minimax:
        tools = [
            minimax_web_search_tool,
            minimax_understand_image_tool,
            *tools,
        ]
        logger.info(
            "explorer_subagent_minimax_tools_prioritized",
            model=model_name,
            minimax_tools=["minimax_web_search", "minimax_understand_image"],
        )

    subagent_spec: Dict[str, Any] = {
        "name": "explorer",
        "description": (
            "Exploration agent for quickly scanning sources and proposing next steps. "
            "Use for broad discovery, hypothesis generation, and suggesting which tools/queries "
            "the coordinator should run next."
            + (" Has Minimax vision for analyzing images." if use_minimax else "")
        ),
        "system_prompt": f"{EXPLORER_PROMPT}\n\nCurrent date: {current_date}",
        "tools": _merge_tools(tools, workspace_tools),
        "model": model,
        "model_name": model_name,
        "model_provider": provider,
        "middleware": _build_research_middleware(model),
    }

    logger.debug(
        "explorer_subagent_created",
        model=model_name,
        provider=provider,
        tools=[t.name for t in subagent_spec["tools"]],
        middleware_count=len(subagent_spec["middleware"]),
        minimax_prioritized=use_minimax,
    )

    return subagent_spec


def get_subagent_specs(
    provider: str = "google",
    *,
    zendesk: bool = False,
    workspace_tools: Optional[List[BaseTool]] = None,
) -> List[Dict[str, Any]]:
    """Return subagent specifications consumed by DeepAgents.

    Args:
        provider: Deprecated; subagents are derived from models.yaml.
        zendesk: When True, use zendesk-specific subagent configs.

    Returns:
        List of subagent specification dicts with:
        - name: Unique identifier
        - description: Human-readable description for routing
        - system_prompt: System prompt for the subagent
        - tools: List of available tools
        - model: ChatModel instance (matching the provider)
        - middleware: List of middleware instances
    """
    config = get_models_config()
    default_subagent = resolve_subagent_config(config, "_default", zendesk=zendesk)
    logger.info(
        "creating_subagent_specs",
        provider=default_subagent.provider,
        model=default_subagent.model_id,
    )
    return [
        _explorer_subagent(zendesk=zendesk, workspace_tools=workspace_tools),
        _research_subagent(zendesk=zendesk, workspace_tools=workspace_tools),
        _log_diagnoser_subagent(zendesk=zendesk, workspace_tools=workspace_tools),
        _db_retrieval_subagent(zendesk=zendesk, workspace_tools=workspace_tools),
    ]


def get_subagent_by_name(
    name: str,
    provider: str = "google",
    *,
    zendesk: bool = False,
) -> Optional[Dict[str, Any]]:
    """Get a specific subagent specification by name.

    Args:
        name: Subagent name (e.g., "research-agent", "log-diagnoser", "db-retrieval").
        provider: Deprecated; subagents are derived from models.yaml.
        zendesk: When True, use zendesk-specific subagent configs.

    Returns:
        Subagent spec dict or None if not found.
    """
    for spec in get_subagent_specs(provider=provider, zendesk=zendesk):
        if spec["name"] == name:
            return spec
    return None
