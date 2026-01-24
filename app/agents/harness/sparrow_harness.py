"""DeepAgents-style harness adapter for Agent Sparrow.

This module provides a factory function for creating Agent Sparrow instances
with proper middleware composition, following DeepAgents patterns.

Usage:
    agent = create_sparrow_agent(
        model=ChatGoogleGenerativeAI(model="gemini-2.5-flash"),
        tools=get_registered_tools(),
        subagents=get_subagent_specs(),
    )
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from langchain_core.tools import BaseTool
from langchain_core.language_models.chat_models import BaseChatModel
from loguru import logger
from langchain.agents.middleware.types import AgentMiddleware

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.store.base import BaseStore
    from langgraph.graph.state import CompiledStateGraph

# Try to import middleware classes
try:
    from langchain.agents import create_agent
    from langchain.agents.middleware import TodoListMiddleware
    from langchain.agents.middleware.summarization import SummarizationMiddleware
    from deepagents.middleware.subagents import SubAgentMiddleware
    from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware

    DEEPAGENTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"DeepAgents middleware not available: {e}")
    DEEPAGENTS_AVAILABLE = False

from app.agents.unified.prompts import COORDINATOR_PROMPT, TODO_PROMPT


# Constants
DEFAULT_MAX_TOKENS_BEFORE_SUMMARY = 170000
DEFAULT_MESSAGES_TO_KEEP = 6
DEFAULT_RECURSION_LIMIT = 120
BASE_AGENT_PROMPT = (
    "In order to complete the objective that the user asks of you, you have access to a number "
    "of standard tools."
)


@dataclass
class SubAgentSpec:
    """Specification for a subagent in the middleware stack.

    Mirrors DeepAgents SubAgent pattern but adapted for Sparrow's needs.
    """

    name: str
    description: str
    model: Optional[BaseChatModel] = None
    tools: List[BaseTool] = field(default_factory=list)
    middleware: List[Any] = field(default_factory=list)
    system_prompt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for middleware configuration."""
        return {
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "tools": self.tools,
            "middleware": self.middleware,
            "system_prompt": self.system_prompt,
        }


@dataclass
class SparrowAgentConfig:
    """Configuration for creating a Sparrow agent.

    This consolidates all agent configuration in a single dataclass,
    making it easier to override defaults and track configuration.
    """

    # Core configuration
    model: BaseChatModel
    tools: List[BaseTool] = field(default_factory=list)
    subagents: List[SubAgentSpec] = field(default_factory=list)

    # Prompts
    system_prompt: Optional[str] = None
    todo_prompt: str = TODO_PROMPT
    coordinator_prompt: str = COORDINATOR_PROMPT

    # Middleware configuration
    enable_memory_middleware: bool = True
    enable_rate_limit_middleware: bool = True
    enable_eviction_middleware: bool = True
    max_tokens_before_summary: int = DEFAULT_MAX_TOKENS_BEFORE_SUMMARY
    messages_to_keep: int = DEFAULT_MESSAGES_TO_KEEP
    cache: Optional[Any] = None
    name: Optional[str] = None

    # Backend configuration
    checkpointer: Optional["BaseCheckpointSaver"] = None
    store: Optional["BaseStore"] = None

    # Runtime configuration
    recursion_limit: int = DEFAULT_RECURSION_LIMIT
    interrupt_on: Optional[Dict[str, bool]] = None

    def build_system_prompt(self) -> str:
        """Build the complete system prompt from components."""
        if self.system_prompt:
            return self.system_prompt

        parts = [
            self.coordinator_prompt,
            self.todo_prompt,
            BASE_AGENT_PROMPT,
        ]
        return "\n\n".join(part for part in parts if part)


def _create_summarization_middleware(
    model: BaseChatModel,
    max_tokens_before_summary: int,
    messages_to_keep: int,
) -> AgentMiddleware:
    """Create SummarizationMiddleware across langchain versions."""
    try:
        params = inspect.signature(SummarizationMiddleware).parameters
    except (TypeError, ValueError):
        params = {}

    if "trigger" in params and "keep" in params:
        return SummarizationMiddleware(
            model=model,
            trigger=("tokens", max_tokens_before_summary),
            keep=("messages", messages_to_keep),
        )

    return SummarizationMiddleware(
        model=model,
        max_tokens_before_summary=max_tokens_before_summary,
        messages_to_keep=messages_to_keep,
    )


def create_sparrow_agent(
    model: BaseChatModel,
    tools: List[BaseTool],
    *,
    subagents: Optional[List[SubAgentSpec]] = None,
    checkpointer: Optional["BaseCheckpointSaver"] = None,
    store: Optional["BaseStore"] = None,
    config: Optional[SparrowAgentConfig] = None,
    enable_memory_middleware: bool = True,
    enable_rate_limit_middleware: bool = True,
    enable_eviction_middleware: bool = True,
    max_tokens_before_summary: int = DEFAULT_MAX_TOKENS_BEFORE_SUMMARY,
    messages_to_keep: int = DEFAULT_MESSAGES_TO_KEEP,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    cache: Optional[Any] = None,
    interrupt_on: Optional[Dict[str, bool]] = None,
) -> "CompiledStateGraph":
    """Factory function for creating Agent Sparrow instances.

    This function wraps the DeepAgents create_agent pattern with Sparrow-specific
    defaults and middleware composition.

    Differences from vanilla DeepAgents:
    - Uses Gemini models by default
    - Excludes FilesystemMiddleware (not exposed to users)
    - Adds SparrowMemoryMiddleware for mem0 integration
    - Adds SparrowRateLimitMiddleware for quota management
    - Adds ToolResultEvictionMiddleware for context safety

    Args:
        model: Chat model to use (e.g., ChatGoogleGenerativeAI).
        tools: List of tools available to the agent.
        subagents: Optional list of subagent specifications.
        checkpointer: Optional checkpointer for state persistence.
        store: Optional store for cross-session data.
        config: Optional full configuration object (overrides other params).
        enable_memory_middleware: Enable mem0 memory integration.
        enable_rate_limit_middleware: Enable Gemini quota management.
        enable_eviction_middleware: Enable large result eviction.
        max_tokens_before_summary: Token threshold for summarization.
        messages_to_keep: Number of recent messages to keep after summarization.
        recursion_limit: Maximum recursion depth for agent.
        interrupt_on: Optional dict specifying interrupt conditions.

    Returns:
        Compiled LangGraph StateGraph ready for invocation.

    Example:
        ```python
        from langchain_google_genai import ChatGoogleGenerativeAI
        from app.agents.unified.tools import get_registered_tools
        from app.agents.unified.subagents import get_subagent_specs

        agent = create_sparrow_agent(
            model=ChatGoogleGenerativeAI(model="gemini-2.5-flash"),
            tools=get_registered_tools(),
            subagents=get_subagent_specs(),
        )

        result = await agent.ainvoke({"messages": [HumanMessage(content="Hello")]})
        ```
    """
    if not DEEPAGENTS_AVAILABLE:
        raise ImportError(
            "DeepAgents middleware is required for create_sparrow_agent. "
            "Install with: pip install deepagents langchain[agents]"
        )

    # Build config if not provided
    if config is None:
        config = SparrowAgentConfig(
            model=model,
            tools=tools,
            subagents=subagents or [],
            checkpointer=checkpointer,
            store=store,
            enable_memory_middleware=enable_memory_middleware,
            enable_rate_limit_middleware=enable_rate_limit_middleware,
            enable_eviction_middleware=enable_eviction_middleware,
            max_tokens_before_summary=max_tokens_before_summary,
            messages_to_keep=messages_to_keep,
            recursion_limit=recursion_limit,
            cache=cache,
            interrupt_on=interrupt_on,
        )

    # Build middleware stack
    middleware_stack = _build_middleware_stack(config)

    logger.debug(
        "Creating Sparrow agent with middleware: {}",
        [getattr(mw, "name", type(mw).__name__) for mw in middleware_stack],
    )

    # Create the agent using DeepAgents pattern
    agent = create_agent(
        config.model,
        system_prompt=config.build_system_prompt(),
        tools=config.tools,
        middleware=middleware_stack,
        checkpointer=config.checkpointer,
        store=config.store,
        cache=config.cache,
        debug=False,
        name=config.name,
    )

    # Apply configuration
    compiled = agent.with_config({"recursion_limit": config.recursion_limit})

    return compiled


def _build_middleware_stack(config: SparrowAgentConfig) -> List[Any]:
    """Build the middleware stack based on configuration.

    Order matters:
    1. Trace seed (correlation id)
    2. Memory middleware (prepends context to messages)
    3. Rate limit middleware (handles quota and fallback)
    4. Tool resilience (retry + circuit breaker)
    5. SubAgent middleware (enables subagent delegation)
    6. Summarization middleware (compacts long conversations)
    7. Eviction middleware (handles large tool results)
    8. PatchToolCalls middleware (normalizes tool call format)
    """
    from .middleware import (
        SafeMiddleware,
        SparrowMemoryMiddleware,
        SparrowRateLimitMiddleware,
        ToolResultEvictionMiddleware,
        ToolRetryMiddleware,
        ToolCircuitBreakerMiddleware,
        TraceSeedMiddleware,
        WorkspaceWriteSandboxMiddleware,
    )

    middleware: List[Any] = []

    # 1. Trace seed
    middleware.append(TraceSeedMiddleware())

    # 2. Memory middleware
    if config.enable_memory_middleware:
        middleware.append(SparrowMemoryMiddleware(enabled=True))

    # 3. Rate limit middleware
    if config.enable_rate_limit_middleware:
        middleware.append(SparrowRateLimitMiddleware())

    # 4. Tool resilience
    middleware.append(ToolRetryMiddleware())
    middleware.append(ToolCircuitBreakerMiddleware())

    # 5. SubAgent middleware (if subagents configured)
    if config.subagents:
        # Build subagent middleware for each subagent
        subagent_default_middleware = [
            _create_summarization_middleware(
                model=config.model,
                max_tokens_before_summary=config.max_tokens_before_summary,
                messages_to_keep=config.messages_to_keep,
            ),
            WorkspaceWriteSandboxMiddleware(),
            PatchToolCallsMiddleware(),
        ]

        coordinator_middleware = SubAgentMiddleware(
            default_model=config.model,
            default_tools=config.tools,
            subagents=[spec.to_dict() for spec in config.subagents],
            default_middleware=subagent_default_middleware,
            default_interrupt_on=config.interrupt_on,
            general_purpose_agent=False,
        )
        middleware.append(coordinator_middleware)

    # 6. Summarization middleware
    middleware.append(
        _create_summarization_middleware(
            model=config.model,
            max_tokens_before_summary=config.max_tokens_before_summary,
            messages_to_keep=config.messages_to_keep,
        )
    )

    # 7. Eviction middleware
    if config.enable_eviction_middleware:
        middleware.append(ToolResultEvictionMiddleware())

    # 8. PatchToolCalls middleware (always last for normalization)
    middleware.append(PatchToolCallsMiddleware())

    # Wrap unsafe middleware with SafeMiddleware to avoid hard failures
    wrapped: List[Any] = []
    for mw in middleware:
        if isinstance(mw, SafeMiddleware):
            wrapped.append(mw)
        elif hasattr(mw, "awrap_tool_call") or hasattr(mw, "wrap_model_call"):
            wrapped.append(SafeMiddleware(mw))
        else:
            wrapped.append(mw)

    return wrapped


def create_lightweight_agent(
    model: BaseChatModel,
    tools: List[BaseTool],
    *,
    system_prompt: Optional[str] = None,
) -> "CompiledStateGraph":
    """Create a lightweight agent without subagent delegation.

    Used for subagents or simple tasks that don't need full coordination.

    Args:
        model: Chat model to use.
        tools: List of tools available.
        system_prompt: Optional system prompt.

    Returns:
        Compiled agent graph.
    """
    if not DEEPAGENTS_AVAILABLE:
        raise ImportError("DeepAgents middleware is required")

    middleware = [
        _create_summarization_middleware(
            model=model,
            max_tokens_before_summary=100000,
            messages_to_keep=4,
        ),
        PatchToolCallsMiddleware(),
    ]

    agent = create_agent(
        model,
        system_prompt=system_prompt or "You are a helpful assistant.",
        tools=tools,
        middleware=middleware,
    )

    return agent.with_config({"recursion_limit": 50})
