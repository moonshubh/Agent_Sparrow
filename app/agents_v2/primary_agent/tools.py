from pydantic import BaseModel, Field
from langchain_core.tools import tool
from typing import Dict, Any

# Import enhanced FeedMe knowledge tool
from .feedme_knowledge_tool import (
    enhanced_mailbird_kb_search,
    mailbird_kb_search,
    EnhancedKBSearchInput
)

# Import user-specific research tools
from app.tools.user_research_tools import tavily_web_search as user_tavily_search

# Legacy KBSearchInput for backward compatibility
class KBSearchInput(BaseModel):
    """Input for the Knowledge Base search tool."""
    query: str = Field(..., description="The search query to find relevant articles in the Mailbird Knowledge Base.")

class WebSearchInput(BaseModel):
    """Input for web search tool."""
    query: str = Field(..., description="The search query to find relevant information on the web.")

# The enhanced mailbird_kb_search tool is now imported from feedme_knowledge_tool
# and automatically replaces the placeholder implementation

@tool
async def tavily_web_search(query: str) -> Dict[str, Any]:
    """
    Search the web using Tavily API with user-specific API key.
    
    Args:
        query: The search query to find relevant information on the web.
        
    Returns:
        Dictionary containing search results with URLs.
    """
    return await user_tavily_search(query, max_results=5)