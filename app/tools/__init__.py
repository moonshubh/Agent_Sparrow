# Tools package
"""
Reusable tools for the Agent Sparrow system.

This package contains domain-specific tools that can be used by agents:
- feedme_knowledge: Enhanced KB search with FeedMe integration
- research_tools: Tavily and Firecrawl web research tools
"""

from app.tools.feedme_knowledge import (
    enhanced_mailbird_kb_search,
    mailbird_kb_search,
    enhanced_mailbird_kb_search_call,
    enhanced_mailbird_kb_search_structured,
    EnhancedKBSearchInput,
    SearchResultSummary,
    ENHANCED_KB_SEARCH_TOOL,
    LEGACY_KB_SEARCH_TOOL,
)
from app.tools.research_tools import (
    FirecrawlTool,
    TavilySearchTool,
)

__all__ = [
    # FeedMe Knowledge tools
    'enhanced_mailbird_kb_search',
    'mailbird_kb_search',
    'enhanced_mailbird_kb_search_call',
    'enhanced_mailbird_kb_search_structured',
    'EnhancedKBSearchInput',
    'SearchResultSummary',
    'ENHANCED_KB_SEARCH_TOOL',
    'LEGACY_KB_SEARCH_TOOL',
    # Research tools
    'FirecrawlTool',
    'TavilySearchTool',
]