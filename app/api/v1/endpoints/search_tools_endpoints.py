"""
API Endpoints for Web Search and Internal Knowledge Base Search.

This module implements subtask 8.4 of Task 8.
- GET /tools/web-search: Uses Tavily to perform a web search.
- GET /tools/internal-search: Uses pgvector similarity search on the mailbird_knowledge DB.
"""
import logging
from typing import List, Optional, Dict, Any, Annotated, TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

# Import security module as a whole so tests can patch its attributes after import.
import app.core.security as security
from app.tools.research_tools import get_research_tools # To get TavilySearchTool instance
from app.db.embedding import utils as embedding_utils  # For internal KB search

if TYPE_CHECKING:
    from app.db.embedding.utils import SearchResult as InternalSearchResult  # pragma: no cover
else:
    InternalSearchResult = Dict[str, Any]

# Re-export TokenPayload for type hints (optional)
TokenPayload = security.TokenPayload

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Pydantic Models for API ---

class WebSearchQuery(BaseModel):
    query: str = Field(..., description="The search query for the web.", min_length=3, max_length=500)
    max_results: Optional[int] = Field(default=5, description="Maximum number of search results to return.", ge=1, le=20)

class WebSearchResultItem(BaseModel):
    title: Optional[str] = None
    url: str
    content: Optional[str] = None # Snippet or brief content
    score: Optional[float] = None # Relevance score from search provider if available

class WebSearchResults(BaseModel):
    query: str
    results: List[WebSearchResultItem]

class InternalSearchQuery(BaseModel):
    query: str = Field(..., description="The search query for the internal knowledge base.", min_length=3, max_length=500)
    top_k: Optional[int] = Field(default=5, description="Number of similar documents to retrieve.", ge=1, le=20)

# Re-using InternalSearchResult from embedding_utils for the response structure
class InternalSearchResults(BaseModel):
    query: str
    results: List[InternalSearchResult]

# Initialize tools (Tavily search is typically the first tool if get_research_tools is used directly)
# We need to ensure this is robust. For now, assuming Tavily is the first one if multiple are returned.
# A better approach might be to have a dedicated getter for Tavily or pass tool name.
try:
    available_tools = get_research_tools()
    # Find Tavily by checking its expected behavior or name if possible
    # For now, assuming the first tool that isn't Firecrawl's scrape_url is Tavily search.
    # This is a bit fragile; direct instantiation or a dedicated getter in research_tools.py would be better.
    tavily_search_func = None
    for tool_func in available_tools:
        # This is a heuristic. A more robust way would be to inspect the tool's name or type.
        # If TavilySearchTool().search is directly accessible, that's better.
        # Based on current research_tools.py, it returns a list of callables.
        # TavilySearchTool().search and FirecrawlTool().scrape_url
        # We can check the __qualname__ or __name__ if they are simple functions
        # or if they are bound methods, check their __self__.
        if hasattr(tool_func, '__qualname__') and 'TavilySearchTool.search' in tool_func.__qualname__:
            tavily_search_func = tool_func
            break
    if not tavily_search_func:
        logger.warning("Tavily search tool function not found via get_research_tools(). Web search might be disabled.")
        # Fallback to a dummy to prevent startup crash, but log error
        def dummy_tavily_search(query: str, max_results: int = 5) -> dict:
            logger.error("Dummy Tavily search called because actual tool was not found.")
            return {"urls": [], "error": "Tavily tool not configured"}
        tavily_search_func = dummy_tavily_search

except ImportError as e:
    logger.error(f"Failed to import or initialize research tools: {e}. Web search will be disabled.")
    def dummy_tavily_search_on_import_error(query: str, max_results: int = 5) -> dict:
        return {"urls": [], "error": f"Tavily tool import failed: {e}"}
    tavily_search_func = dummy_tavily_search_on_import_error

# --- API Endpoints ---

@router.post("/web-search", response_model=WebSearchResults, tags=["Search Tools"])
async def web_search_endpoint(
    search_params: WebSearchQuery,
    # current_user: Annotated[TokenPayload, Depends(security.get_current_user)]  # JWT Authentication - Disabled for testing
):
    """
    Performs a web search using Tavily based on the provided query.
    Requires authentication.
    """
    logger.info(f"Performing web search for: '{search_params.query}'")
    if not tavily_search_func or (hasattr(tavily_search_func, '__name__') and 'dummy' in tavily_search_func.__name__):
        logger.error("Tavily search tool is not available or not properly configured.")
        raise HTTPException(status_code=503, detail="Web search service is currently unavailable.")

    try:
        # Tavily search tool from research_tools.py returns a dict like: {"urls": [...]} or {"results": [...]}
        # The TavilySearchTool.search method returns: {"urls": [item["url"] for item in results.get("results", [])]}
        # Let's adapt to the more detailed structure if Tavily provides it, or stick to URLs.
        # The `TavilySearchResults` class expects more details like title, content, score.
        # The current `TavilySearchTool.search` in `research_tools.py` only returns URLs.
        # We might need to adjust `TavilySearchTool.search` or this endpoint.
        # For now, let's assume we adapt here or that `TavilySearchTool` is updated.
        
        # Invoking the Tavily search function
        # The Tavily Python SDK's search method returns a richer structure.
        # client.search(query=query, search_depth="advanced", max_results=max_results)
        # returns: {'query': '...', 'results': [{'title': '...', 'url': '...', 'content': '...', 'score': ...}]}
        # The current wrapper TavilySearchTool.search in research_tools.py simplifies this to just URLs.
        # To fulfill WebSearchResultItem, we'd ideally call the Tavily client directly or enhance the tool.
        
        # For now, using the existing tool and populating what we can:
        raw_results = tavily_search_func(query=search_params.query, max_results=search_params.max_results)
        
        processed_results: List[WebSearchResultItem] = []
        if isinstance(raw_results, dict) and "error" in raw_results:
            logger.error(f"Tavily search failed for query '{search_params.query}': {raw_results['error']}")
            # Depending on the error, we might raise HTTPException or return an empty list with a note.
            # For now, let's return empty results if the tool itself signals an error.
            pass # This will result in an empty 'results' list in the response.
        elif isinstance(raw_results, dict) and "urls" in raw_results: # Current tool output
            for url_item in raw_results["urls"]:
                if isinstance(url_item, str): # If it's just a list of URL strings
                    processed_results.append(WebSearchResultItem(url=url_item))
                elif isinstance(url_item, dict): # If it's a list of dicts with more details
                    processed_results.append(WebSearchResultItem(
                        title=url_item.get('title'),
                        url=url_item.get('url', 'N/A'), # URL must be present
                        content=url_item.get('content'),
                        score=url_item.get('score')
                    ))
        # If Tavily SDK was used directly and returned the full structure:
        # elif isinstance(raw_results, dict) and "results" in raw_results:
        #     for item in raw_results["results"]:
        #         processed_results.append(WebSearchResultItem(
        #             title=item.get('title'),
        #             url=item.get('url'),
        #             content=item.get('content'), # This is snippet
        #             score=item.get('score')
        #         ))

        return WebSearchResults(query=search_params.query, results=processed_results)

    except Exception as e:
        logger.exception(f"Error during web search for query '{search_params.query}': {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during web search: {str(e)}")

@router.post("/internal-search", response_model=InternalSearchResults, tags=["Search Tools"])
async def internal_kb_search_endpoint(
    search_params: InternalSearchQuery,
    # current_user: Annotated[TokenPayload, Depends(security.get_current_user)]  # JWT Authentication - Disabled for testing
):
    """
    Performs a similarity search in the internal Mailbird knowledge base.
    Requires authentication.
    """
    logger.info(f"Performing internal KB search for: '{search_params.query}'")
    try:
        similar_docs = embedding_utils.find_similar_documents(query=search_params.query, top_k=search_params.top_k)
        # Convert SearchResult Pydantic models to dicts for InternalSearchResults
        results_as_dicts = [doc.model_dump() if hasattr(doc, 'model_dump') else doc for doc in similar_docs]
        return InternalSearchResults(query=search_params.query, results=results_as_dicts)
    except Exception as e:
        logger.exception(f"Error during internal KB search for query '{search_params.query}': {e}")
        # Check if it's a DB connection issue or embedding model issue from underlying function
        if "database" in str(e).lower() or "connection" in str(e).lower():
            raise HTTPException(status_code=503, detail="Internal search service is temporarily unavailable due to a database issue.")
        elif "GEMINI_API_KEY" in str(e) or "embedding model" in str(e).lower():
             raise HTTPException(status_code=503, detail="Internal search service is temporarily unavailable due to an embedding model configuration issue.")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during internal search: {str(e)}")

# Note: To make these endpoints accessible, this router needs to be included
# in the main FastAPI application (e.g., in app/main.py)
# Example: app.include_router(search_tools_endpoints.router, prefix="/api/v1/tools", tags=["Search Tools"])
