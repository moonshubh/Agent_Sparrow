"""DeepAgents subagent specifications for the unified agent."""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.settings import settings

from .tools import (
    firecrawl_fetch_tool,
    kb_search_tool,
    log_diagnoser_tool,
    web_search_tool,
)

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


def _get_chat_model(model_name: str) -> ChatGoogleGenerativeAI:
    """Create a pre-initialized ChatGoogleGenerativeAI instance."""
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0.3,
        google_api_key=settings.gemini_api_key,
    )


def _research_subagent() -> Dict[str, Any]:
    subagent_spec = {
        "name": "research-agent",
        "description": "Gathers supporting evidence from Mailbird KB and the public web.",
        "system_prompt": (
            "You are a focused research assistant for Agent Sparrow.\n"
            "Use search tools to gather up-to-date information, cite reliable sources,"
            " and return concise findings with relevant URLs."
        ),
        "tools": [kb_search_tool, web_search_tool, firecrawl_fetch_tool],
        "model": _get_chat_model(settings.primary_agent_model),
    }

    # Add lightweight middleware for research agent (no TodoList needed for simple research)
    if MIDDLEWARE_AVAILABLE:
        subagent_spec["middleware"] = [
            SummarizationMiddleware(
                model=_get_chat_model(settings.primary_agent_model),
                max_tokens_before_summary=100000,  # Lower threshold for research
                messages_to_keep=4,
            ),
            PatchToolCallsMiddleware(),
        ]

    return subagent_spec


def _log_diagnoser_subagent() -> Dict[str, Any]:
    subagent_spec = {
        "name": "log-diagnoser",
        "description": "Analyzes attached log files to identify issues and fixes.",
        "system_prompt": (
            "You specialize in parsing application logs. Provide root-cause analysis,"
            " actionable fixes, and confidence levels."
        ),
        "tools": [log_diagnoser_tool],
        "model": _get_chat_model(settings.enhanced_log_model),
    }

    # Add comprehensive middleware for log analysis (including TodoList for tracking issues)
    if MIDDLEWARE_AVAILABLE:
        subagent_spec["middleware"] = [
            TodoListMiddleware(),  # Track issues found and fixes to apply
            SummarizationMiddleware(
                model=_get_chat_model(settings.enhanced_log_model),
                max_tokens_before_summary=170000,  # Large threshold for extensive logs
                messages_to_keep=6,
            ),
            PatchToolCallsMiddleware(),
        ]

    return subagent_spec


def get_subagent_specs() -> List[Dict[str, Any]]:
    """Return subagent specifications consumed by DeepAgents."""

    return [_research_subagent(), _log_diagnoser_subagent()]

