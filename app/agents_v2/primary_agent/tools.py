from pydantic import BaseModel, Field
from langchain_core.tools import tool
import os
try:
    from langchain_tavily import TavilySearch as _TavilySearch
except ImportError:
    from langchain_community.tools.tavily_search import TavilySearchResults as _TavilySearch  # Fallback (deprecated)

# Alias consistent name regardless of import source
TavilySearch = _TavilySearch

class KBSearchInput(BaseModel):
    """Input for the Knowledge Base search tool."""
    query: str = Field(..., description="The search query to find relevant articles in the Mailbird Knowledge Base.")

@tool("mailbird-kb-search", args_schema=KBSearchInput)
def mailbird_kb_search(query: str) -> str:
    """
    Searches the Mailbird Knowledge Base for articles relevant to the user's query.
    """
    # In a real implementation, this would query a vector store or other search index.
    # For now, it returns a placeholder response.
    print(f"Searching KB for: {query}")
    return "Placeholder: Found relevant articles about your query."

tavily_web_search = TavilySearch(max_results=5)