"""Minimax MCP tools for Agent Sparrow.

Provides web search and image understanding capabilities via Minimax's Coding Plan API.
These tools use the same API key as the Minimax M2.1 model.

Minimax Coding Plan MCP Reference:
- https://platform.minimax.io/docs/coding-plan/mcp-guide
- https://github.com/MiniMax-AI/MiniMax-Coding-Plan-MCP

Available Tools:
- minimax_web_search: Search the web and get structured results
- minimax_understand_image: Analyze images from URLs or descriptions
"""

from __future__ import annotations

import base64
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Annotated

import httpx
from langgraph.prebuilt import InjectedState
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from app.agents.orchestration.orchestration.state import GraphState
from app.core.settings import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Minimax API Configuration
MINIMAX_API_HOST = "https://api.minimax.io"
MINIMAX_MCP_TIMEOUT = 60.0  # seconds


def _get_minimax_api_key() -> Optional[str]:
    """Get Minimax API key from settings."""
    return getattr(settings, "minimax_api_key", None)


def is_minimax_available() -> bool:
    """Check if Minimax tools are available (API key configured)."""
    return bool(_get_minimax_api_key())


# =============================================================================
# Input Schemas
# =============================================================================


class MinimaxWebSearchInput(BaseModel):
    """Input schema for Minimax web search tool."""

    query: str = Field(
        ...,
        description="The search query to execute. Be specific and descriptive for best results.",
    )
    max_results: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Maximum number of search results to return (1-20).",
    )


class MinimaxImageUnderstandingInput(BaseModel):
    """Input schema for Minimax image understanding tool."""

    prompt: str = Field(
        ...,
        description="Question or analysis request about the image. Be specific about what information you need.",
    )
    image_url: str = Field(
        ...,
        description="URL of the image to analyze (HTTP/HTTPS) or local file path. Supports JPEG, PNG, GIF, WebP up to 20MB.",
    )


# =============================================================================
# API Client
# =============================================================================


class MinimaxMCPClient:
    """Client for Minimax Coding Plan MCP API.

    Handles web search and image understanding requests via Minimax's API.
    """

    def __init__(self, api_key: str, base_url: str = MINIMAX_API_HOST):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(MINIMAX_MCP_TIMEOUT),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def web_search(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Perform web search via Minimax API.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.

        Returns:
            Dictionary containing search results with titles, links, snippets,
            and related searches.
        """
        client = await self._get_client()

        # Minimax uses OpenAI-compatible chat completions with tool calls
        # For web search, we use a direct search endpoint
        payload = {
            "model": "MiniMax-M2.1",
            "messages": [
                {
                    "role": "user",
                    "content": f"Search the web for: {query}\n\nReturn the top {max_results} most relevant results."
                }
            ],
            "tools": [
                {
                    "type": "web_search",
                    "web_search": {
                        "enable": True,
                        "search_query": query
                    }
                }
            ],
            "tool_choice": "auto"
        }

        try:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            # Extract search results from the response
            # Minimax returns results in a structured format
            return self._parse_search_response(result, query)

        except httpx.HTTPStatusError as e:
            logger.error(f"minimax_web_search_http_error status={e.response.status_code} body={e.response.text[:500]}")
            return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            logger.error(f"minimax_web_search_error error='{str(e)}'")
            return {"error": str(e)}

    def _parse_search_response(self, response: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Parse Minimax search response into structured results."""
        try:
            choices = response.get("choices", [])
            if not choices:
                return {"query": query, "results": [], "related_searches": []}

            message = choices[0].get("message", {})
            content = message.get("content", "")

            # Check for tool results in the response
            tool_calls = message.get("tool_calls", [])
            web_search_results = []

            for tool_call in tool_calls:
                if tool_call.get("type") == "web_search":
                    # Extract results from web_search tool response
                    function_result = tool_call.get("function", {}).get("result", {})
                    if isinstance(function_result, dict):
                        web_search_results = function_result.get("results", [])

            # If no tool results, parse from content
            if not web_search_results and content:
                return {
                    "query": query,
                    "results": [{"content": content}],
                    "related_searches": [],
                    "source": "minimax_content"
                }

            return {
                "query": query,
                "results": web_search_results,
                "related_searches": [],
                "source": "minimax_web_search"
            }

        except Exception as e:
            logger.warning(f"minimax_parse_search_error error='{str(e)}'")
            return {"query": query, "results": [], "error": str(e)}

    async def understand_image(self, prompt: str, image_url: str) -> Dict[str, Any]:
        """Analyze an image using Minimax's vision capabilities.

        Args:
            prompt: Question or analysis request about the image.
            image_url: URL of the image or local file path.

        Returns:
            Dictionary containing the analysis result.
        """
        client = await self._get_client()

        # Handle local file paths by converting to base64
        image_content = await self._prepare_image_content(image_url)
        if "error" in image_content:
            return image_content

        payload = {
            "model": "MiniMax-M2.1",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        image_content
                    ]
                }
            ],
            "max_tokens": 4096,
        }

        try:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            return self._parse_image_response(result, prompt, image_url)

        except httpx.HTTPStatusError as e:
            logger.error(f"minimax_understand_image_http_error status={e.response.status_code}")
            return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            logger.error(f"minimax_understand_image_error error='{str(e)}'")
            return {"error": str(e)}

    async def _prepare_image_content(self, image_url: str) -> Dict[str, Any]:
        """Prepare image content for API request.

        Handles both URLs and local file paths.
        """
        # Check if it's a URL or local path
        if image_url.startswith(("http://", "https://")):
            return {
                "type": "image_url",
                "image_url": {"url": image_url}
            }

        # Handle local file path
        path = Path(image_url)
        if not path.exists():
            return {"error": f"File not found: {image_url}"}

        # Check file size (max 20MB)
        if path.stat().st_size > 20 * 1024 * 1024:
            return {"error": "Image file exceeds 20MB limit"}

        # Determine MIME type
        suffix = path.suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(suffix, "image/jpeg")

        # Read and encode as base64
        try:
            with open(path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_data}"
                }
            }
        except Exception as e:
            return {"error": f"Failed to read image: {str(e)}"}

    def _parse_image_response(self, response: Dict[str, Any], prompt: str, image_url: str) -> Dict[str, Any]:
        """Parse Minimax image understanding response."""
        try:
            choices = response.get("choices", [])
            if not choices:
                return {"prompt": prompt, "image_url": image_url, "analysis": "", "error": "No response"}

            message = choices[0].get("message", {})
            content = message.get("content", "")

            return {
                "prompt": prompt,
                "image_url": image_url,
                "analysis": content,
                "source": "minimax_vision"
            }

        except Exception as e:
            logger.warning(f"minimax_parse_image_error error='{str(e)}'")
            return {"prompt": prompt, "image_url": image_url, "analysis": "", "error": str(e)}


# Singleton client instance
_minimax_client: Optional[MinimaxMCPClient] = None
_client_lock = asyncio.Lock()


async def get_minimax_client() -> Optional[MinimaxMCPClient]:
    """Get or create Minimax client singleton."""
    global _minimax_client

    api_key = _get_minimax_api_key()
    if not api_key:
        return None

    async with _client_lock:
        if _minimax_client is None:
            base_url = getattr(settings, "minimax_base_url", MINIMAX_API_HOST)
            _minimax_client = MinimaxMCPClient(api_key, base_url)

    return _minimax_client


# =============================================================================
# Tool Definitions
# =============================================================================


@tool("minimax_web_search", args_schema=MinimaxWebSearchInput)
async def minimax_web_search_tool(
    query: Optional[str] = None,
    max_results: int = 10,
    input: Optional[MinimaxWebSearchInput] = None,
    state: Annotated[Optional[GraphState], InjectedState] = None,
) -> Dict[str, Any]:
    """Search the web using Minimax's AI-powered search.

    Performs web searches and returns structured results including titles,
    links, snippets, and related search suggestions. Best for finding
    current information, documentation, and research.

    Args:
        query: The search query to execute.
        max_results: Maximum number of results (1-20, default 10).

    Returns:
        Dictionary containing:
        - query: The search query used
        - results: List of search results with title, link, snippet
        - related_searches: Related search suggestions
        - source: "minimax_web_search"
    """
    # Handle both input object and raw kwargs
    if input is not None:
        query = input.query
        max_results = input.max_results

    if not query:
        return {"error": "Query is required"}

    client = await get_minimax_client()
    if not client:
        logger.warning("minimax_web_search_unavailable reason='api_key_not_configured'")
        return {"error": "Minimax API key not configured. Set MINIMAX_API_KEY in environment."}

    logger.info(f"minimax_web_search_invoked query='{query[:100]}' max_results={max_results}")

    result = await client.web_search(query, max_results)

    if "error" not in result:
        result_count = len(result.get("results", []))
        logger.info(f"minimax_web_search_success query='{query[:50]}' results={result_count}")
    else:
        logger.warning(f"minimax_web_search_failed query='{query[:50]}' error='{result.get('error', 'unknown')}'")

    return result


@tool("minimax_understand_image", args_schema=MinimaxImageUnderstandingInput)
async def minimax_understand_image_tool(
    prompt: Optional[str] = None,
    image_url: Optional[str] = None,
    input: Optional[MinimaxImageUnderstandingInput] = None,
    state: Annotated[Optional[GraphState], InjectedState] = None,
) -> Dict[str, Any]:
    """Analyze and understand images using Minimax's vision AI.

    Performs AI-powered image analysis to answer questions, extract information,
    describe content, or analyze visual elements. Supports JPEG, PNG, GIF, and
    WebP formats up to 20MB.

    Args:
        prompt: Question or analysis request about the image.
        image_url: URL of the image (HTTP/HTTPS) or local file path.

    Returns:
        Dictionary containing:
        - prompt: The analysis prompt used
        - image_url: The image URL/path
        - analysis: The AI analysis result
        - source: "minimax_vision"
    """
    # Handle both input object and raw kwargs
    if input is not None:
        prompt = input.prompt
        image_url = input.image_url

    if not prompt:
        return {"error": "Prompt is required"}
    if not image_url:
        return {"error": "Image URL is required"}

    client = await get_minimax_client()
    if not client:
        logger.warning("minimax_understand_image_unavailable reason='api_key_not_configured'")
        return {"error": "Minimax API key not configured. Set MINIMAX_API_KEY in environment."}

    logger.info(f"minimax_understand_image_invoked prompt='{prompt[:100]}' image='{image_url[:100]}'")

    result = await client.understand_image(prompt, image_url)

    if "error" not in result:
        logger.info(f"minimax_understand_image_success prompt='{prompt[:50]}'")
    else:
        logger.warning(f"minimax_understand_image_failed prompt='{prompt[:50]}' error='{result.get('error', 'unknown')}'")

    return result


# =============================================================================
# Tool Registration
# =============================================================================


def get_minimax_tools() -> List[BaseTool]:
    """Get all Minimax tools if available.

    Returns:
        List of Minimax tools if API key is configured, empty list otherwise.
    """
    if not is_minimax_available():
        logger.debug("minimax_tools_skipped reason='api_key_not_configured'")
        return []

    return [
        minimax_web_search_tool,
        minimax_understand_image_tool,
    ]
