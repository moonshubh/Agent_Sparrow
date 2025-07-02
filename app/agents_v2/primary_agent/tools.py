from pydantic import BaseModel, Field
from langchain_core.tools import tool
import os
try:
    from langchain_tavily import TavilySearch as _TavilySearch
except ImportError:
    from langchain_community.tools.tavily_search import TavilySearchResults as _TavilySearch  # Fallback (deprecated)

# Import enhanced FeedMe knowledge tool
from .feedme_knowledge_tool import (
    enhanced_mailbird_kb_search,
    mailbird_kb_search,
    EnhancedKBSearchInput
)

# Alias consistent name regardless of import source
TavilySearch = _TavilySearch

# Legacy KBSearchInput for backward compatibility
class KBSearchInput(BaseModel):
    """Input for the Knowledge Base search tool."""
    query: str = Field(..., description="The search query to find relevant articles in the Mailbird Knowledge Base.")

# The enhanced mailbird_kb_search tool is now imported from feedme_knowledge_tool
# and automatically replaces the placeholder implementation

tavily_web_search = TavilySearch(max_results=5)