"""
User-specific research tools that use per-user API keys.
Provides tools that dynamically use user API keys from context.
"""

import os
import json
import redis
import logging
from typing import Optional, Dict, Any

from app.core.settings import settings
from app.core.user_context import get_current_user_context
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# Optional third-party SDKs
try:
    from firecrawl import FirecrawlApp
except ImportError:
    FirecrawlApp = None

try:
    from tavily import Tavily
except ImportError:
    Tavily = None

logger = logging.getLogger(__name__)

# Redis URL
REDIS_URL = settings.redis_url
SCRAPE_CACHE_TTL_SEC = int(os.getenv("SCRAPE_CACHE_TTL_SEC", "86400"))

# Helper to get a singleton Redis client
_redis_client: Optional[redis.Redis] = None

def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


class UserTavilySearchTool:
    """
    User-specific Tavily search tool that uses API keys from user context.
    """
    
    def __init__(self):
        self.name = "tavily_web_search"
        self.description = "Search the web using Tavily API with user-specific API key"
    
    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def search(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Search the web with user's Tavily API key."""
        
        if Tavily is None:
            logger.warning("Tavily SDK not installed")
            return {"urls": []}
        
        # Get user context
        user_context = get_current_user_context()
        if not user_context:
            logger.warning("No user context available for Tavily search")
            return {"urls": []}
        
        # Get user's Tavily API key
        api_key = await user_context.get_tavily_api_key()
        if not api_key:
            logger.info("No Tavily API key configured for user")
            return {"urls": []}
        
        try:
            client = Tavily(api_key=api_key)
            results = client.search(query=query, max_results=max_results)
            
            # Extract URLs from results
            urls = [item["url"] for item in results.get("results", [])]
            return {"urls": urls}
            
        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return {"urls": []}


class UserFirecrawlScrapeTool:
    """
    User-specific Firecrawl scraping tool that uses API keys from user context.
    """
    
    def __init__(self):
        self.name = "firecrawl_scrape"
        self.description = "Scrape web content using Firecrawl API with user-specific API key"
    
    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def scrape(self, url: str) -> Dict[str, Any]:
        """Scrape a URL with user's Firecrawl API key."""
        
        if FirecrawlApp is None:
            logger.warning("Firecrawl SDK not installed")
            return {"content": "", "error": "Firecrawl SDK not available"}
        
        # Check cache first
        try:
            redis_client = _get_redis()
            cache_key = f"firecrawl_scrape:{url}"
            cached_result = redis_client.get(cache_key)
            if cached_result:
                logger.debug(f"Cache hit for URL: {url}")
                return json.loads(cached_result)
        except Exception as e:
            logger.debug(f"Cache lookup error: {e}")
        
        # Get user context
        user_context = get_current_user_context()
        if not user_context:
            logger.warning("No user context available for Firecrawl scraping")
            return {"content": "", "error": "No user context"}
        
        # Get user's Firecrawl API key
        api_key = await user_context.get_firecrawl_api_key()
        if not api_key:
            logger.info("No Firecrawl API key configured for user")
            return {"content": "", "error": "No Firecrawl API key configured"}
        
        try:
            firecrawl_app = FirecrawlApp(api_key=api_key)
            scrape_result = firecrawl_app.scrape_url(url)
            
            # Extract content
            content = ""
            if scrape_result and scrape_result.get("success"):
                content = scrape_result.get("data", {}).get("content", "")
            
            result = {"content": content}
            
            # Cache the result
            try:
                redis_client = _get_redis()
                cache_key = f"firecrawl_scrape:{url}"
                redis_client.setex(cache_key, SCRAPE_CACHE_TTL_SEC, json.dumps(result))
                logger.debug(f"Cached result for URL: {url}")
            except Exception as e:
                logger.debug(f"Cache storage error: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Firecrawl scraping error for {url}: {e}")
            return {"content": "", "error": str(e)}


# Global tool instances
_tavily_tool: Optional[UserTavilySearchTool] = None
_firecrawl_tool: Optional[UserFirecrawlScrapeTool] = None


def get_user_tavily_tool() -> UserTavilySearchTool:
    """Get singleton user-specific Tavily search tool."""
    global _tavily_tool
    if _tavily_tool is None:
        _tavily_tool = UserTavilySearchTool()
    return _tavily_tool


def get_user_firecrawl_tool() -> UserFirecrawlScrapeTool:
    """Get singleton user-specific Firecrawl scraping tool."""
    global _firecrawl_tool
    if _firecrawl_tool is None:
        _firecrawl_tool = UserFirecrawlScrapeTool()
    return _firecrawl_tool


# LangChain-compatible tool functions
async def tavily_web_search(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    LangChain tool function for Tavily web search using user API key.
    """
    tool = get_user_tavily_tool()
    return await tool.search(query, max_results)


async def firecrawl_scrape(url: str) -> Dict[str, Any]:
    """
    LangChain tool function for Firecrawl scraping using user API key.
    """
    tool = get_user_firecrawl_tool()
    return await tool.scrape(url)


def get_user_research_tools():
    """
    Get list of research tools that use user-specific API keys.
    """
    return [
        tavily_web_search,
        firecrawl_scrape,
    ]