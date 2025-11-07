"""Domain tools exposed to the unified agent."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from app.agents.log_analysis.log_analysis_agent.simplified_agent import (
    SimplifiedLogAnalysisAgent,
)
from app.agents.log_analysis.log_analysis_agent.simplified_schemas import (
    SimplifiedAgentState,
    SimplifiedLogAnalysisOutput,
)
from app.agents.primary.primary_agent.feedme_knowledge_tool import (
    EnhancedKBSearchInput,
    enhanced_mailbird_kb_search,
)
from app.core.rate_limiting.agent_wrapper import rate_limited
from app.core.settings import settings
from app.tools.research_tools import FirecrawlTool, TavilySearchTool


@lru_cache(maxsize=1)
def _tavily_client() -> TavilySearchTool:
    return TavilySearchTool()


@lru_cache(maxsize=1)
def _firecrawl_client() -> FirecrawlTool:
    return FirecrawlTool()


class WebSearchInput(BaseModel):
    query: str = Field(..., description="Natural language query to research.")
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of URLs to return.",
    )


@tool("kb_search", args_schema=EnhancedKBSearchInput)
async def kb_search_tool(input: EnhancedKBSearchInput) -> str:
    """Search Mailbird knowledge base and FeedMe support archives."""

    return enhanced_mailbird_kb_search(
        query=input.query,
        context=input.context,
        max_results=input.max_results,
        search_sources=input.search_sources,
        min_confidence=input.min_confidence,
    )


class LogDiagnoserInput(BaseModel):
    log_content: str = Field(..., description="Raw log text to analyze.")
    question: Optional[str] = Field(
        default=None,
        description="Specific question about the log contents.",
    )
    trace_id: Optional[str] = Field(
        default=None,
        description="Optional trace identifier for auditing.",
    )


class FirecrawlInput(BaseModel):
    url: str = Field(..., description="URL to scrape for detailed content.")


@tool("log_diagnoser", args_schema=LogDiagnoserInput)
async def log_diagnoser_tool(input: LogDiagnoserInput) -> Dict[str, Any]:
    """Analyze application logs and return targeted diagnostics with error handling."""
    try:
        state = SimplifiedAgentState(
            raw_log_content=input.log_content,
            question=input.question,
            trace_id=input.trace_id,
        )
        async with SimplifiedLogAnalysisAgent() as agent:
            result: SimplifiedLogAnalysisOutput = await agent.analyze(state)
        return result.model_dump()
    except Exception as e:
        # Return error information for graceful degradation
        return {
            "error": "log_analysis_failed",
            "message": str(e),
            "trace_id": input.trace_id,
            "suggestion": "Please check the log format and try again."
        }


@tool("web_search", args_schema=WebSearchInput)
async def web_search_tool(input: WebSearchInput) -> Dict[str, Any]:
    """Search the public web using Tavily for broader context with retry logic."""
    max_retries = 3
    tavily = _tavily_client()
    
    for attempt in range(max_retries):
        try:
            return await asyncio.to_thread(tavily.search, input.query, input.max_results)
        except Exception as e:
            if attempt == max_retries - 1:
                raise Exception(f"Web search failed after {max_retries} attempts: {e}")
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff


@tool("fetch_url", args_schema=FirecrawlInput)
async def firecrawl_fetch_tool(input: FirecrawlInput) -> Dict[str, Any]:
    """Fetch structured content from a URL via Firecrawl with retry logic."""
    max_retries = 3
    firecrawl = _firecrawl_client()
    
    for attempt in range(max_retries):
        try:
            return await asyncio.to_thread(firecrawl.scrape_url, input.url)
        except Exception as e:
            if attempt == max_retries - 1:
                raise Exception(f"URL fetch failed after {max_retries} attempts: {e}")
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff


def get_registered_tools() -> List[BaseTool]:
    """Return the tools bound to the unified agent."""

    return [
        kb_search_tool,
        web_search_tool,
        firecrawl_fetch_tool,
        log_diagnoser_tool,
    ]

