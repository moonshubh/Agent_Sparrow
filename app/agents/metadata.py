from __future__ import annotations

from typing import Dict, List, Optional


# Phase 5: Static agent metadata for discovery and simple UI consumption.
# Keep lightweight and explicit; avoid dynamic registry complexity.

AGENTS: List[Dict[str, object]] = [
    {
        "id": "primary",
        "destination": "primary_agent",
        "name": "Primary Support",
        "description": "General queries and Mailbird knowledge base assistance.",
        "tools": ["mailbird_kb_search", "tavily_web_search"],
        "aliases": ["primary_agent"],
        "icon": "🎯",
    },
    {
        "id": "log_analysis",
        "destination": "log_analyst",
        "name": "Log Analysis",
        "description": "Diagnose issues from logs, errors, and performance traces.",
        "tools": [],
        "aliases": ["log_analyst"],
        "icon": "🧪",
    },
    {
        "id": "research",
        "destination": "researcher",
        "name": "Research",
        "description": "Web research, sources gathering, and comparisons.",
        "tools": ["tavily_search", "firecrawl_scraper"],
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
