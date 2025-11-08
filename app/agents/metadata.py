from __future__ import annotations

from typing import Dict, List, Optional


# Unified Agent System Metadata
# All agents are now part of the unified agent system with DeepAgents.
# Legacy agent IDs are maintained for backward compatibility with frontend.

AGENTS: List[Dict[str, object]] = [
    {
        "id": "unified",
        "destination": "unified_agent",
        "name": "Agent Sparrow (Unified)",
        "description": "Unified multi-agent system with research, log analysis, and conversational capabilities.",
        "tools": ["kb_search", "web_search", "firecrawl_fetch", "log_diagnoser"],
        "aliases": ["primary", "primary_agent", "sparrow"],
        "icon": "🦅",
    },
    {
        "id": "primary",
        "destination": "unified_agent",  # Routes to unified agent
        "name": "Primary Support",
        "description": "General queries and Mailbird knowledge base assistance (via unified agent).",
        "tools": ["kb_search", "web_search"],
        "aliases": ["primary_agent"],
        "icon": "🎯",
    },
    {
        "id": "log_analysis",
        "destination": "unified_agent",  # Routes to unified agent's log-diagnoser subagent
        "name": "Log Analysis",
        "description": "Diagnose issues from logs, errors, and performance traces (via unified agent).",
        "tools": ["log_diagnoser"],
        "aliases": ["log_analyst"],
        "icon": "🧪",
    },
    {
        "id": "research",
        "destination": "unified_agent",  # Routes to unified agent's research subagent
        "name": "Research",
        "description": "Web research, sources gathering, and comparisons (via unified agent).",
        "tools": ["web_search", "firecrawl_fetch", "kb_search"],
        "aliases": ["researcher"],
        "icon": "🧭",
    },
]


def list_agents() -> List[Dict[str, object]]:
    return AGENTS


def get_agent_metadata(agent_id: str) -> Optional[Dict[str, object]]:
    if not isinstance(agent_id, str):
        return None
    key = agent_id.strip().lower()
    for agent in AGENTS:
        if agent.get("id") == key:
            return agent
        aliases = agent.get("aliases") or []
        if isinstance(aliases, list) and key in aliases:
            return agent
    return None
