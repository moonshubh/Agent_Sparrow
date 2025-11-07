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


def _get_chat_model(model_name: str) -> ChatGoogleGenerativeAI:
    """Create a pre-initialized ChatGoogleGenerativeAI instance."""
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0.3,
        google_api_key=settings.gemini_api_key,
    )


def _research_subagent() -> Dict[str, Any]:
    return {
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


def _log_diagnoser_subagent() -> Dict[str, Any]:
    return {
        "name": "log-diagnoser",
        "description": "Analyzes attached log files to identify issues and fixes.",
        "system_prompt": (
            "You specialize in parsing application logs. Provide root-cause analysis,"
            " actionable fixes, and confidence levels."
        ),
        "tools": [log_diagnoser_tool],
        "model": _get_chat_model(settings.enhanced_log_model),
    }


def get_subagent_specs() -> List[Dict[str, Any]]:
    """Return subagent specifications consumed by DeepAgents."""

    return [_research_subagent(), _log_diagnoser_subagent()]

