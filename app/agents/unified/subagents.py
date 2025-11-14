"""DeepAgents subagent specifications for the unified agent."""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.settings import settings

from .prompts import LOG_ANALYSIS_PROMPT, RESEARCH_PROMPT
from .tools import (
    firecrawl_fetch_tool,
    grounding_search_tool,
    kb_search_tool,
    log_diagnoser_tool,
    web_search_tool,
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


def _get_chat_model(model_name: str) -> ChatGoogleGenerativeAI:
    """Create a pre-initialized ChatGoogleGenerativeAI instance."""
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0.3,
        google_api_key=settings.gemini_api_key,
    )


def _research_subagent() -> Dict[str, Any]:
    model_name = model_router.select_model("lightweight")
    subagent_spec = {
        "name": "research-agent",
        "description": "Gathers supporting evidence from Mailbird KB and the public web.",
        "system_prompt": RESEARCH_PROMPT,
        "tools": [kb_search_tool, grounding_search_tool, web_search_tool, firecrawl_fetch_tool],
        "model": _get_chat_model(model_name),
    }

    # No middleware configured for research agent (placeholder for future additions)
    if MIDDLEWARE_AVAILABLE:
        subagent_spec["middleware"] = []

    return subagent_spec


def _log_diagnoser_subagent() -> Dict[str, Any]:
    model_name = model_router.select_model("log_analysis")
    subagent_spec = {
        "name": "log-diagnoser",
        "description": "Analyzes attached log files to identify issues and fixes.",
        "system_prompt": LOG_ANALYSIS_PROMPT,
        "tools": [log_diagnoser_tool],
        "model": _get_chat_model(model_name),
    }

    # No middleware configured for log diagnoser (intentionally empty, placeholder for future)
    if MIDDLEWARE_AVAILABLE:
        subagent_spec["middleware"] = []

    return subagent_spec


def get_subagent_specs() -> List[Dict[str, Any]]:
    """Return subagent specifications consumed by DeepAgents."""

    return [_research_subagent(), _log_diagnoser_subagent()]
