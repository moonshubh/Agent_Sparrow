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

import asyncio
import base64
import json
import os
import shutil
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Annotated, cast

import httpx
from langgraph.prebuilt import InjectedState
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from app.agents.orchestration.orchestration.state import GraphState
from app.core.rate_limiting.agent_wrapper import rate_limited
from app.core.settings import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# MCP adapters are optional; fall back to direct API if unavailable.
try:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    MultiServerMCPClient = None  # type: ignore[misc, assignment]

# Minimax API Configuration
MINIMAX_API_HOST = "https://api.minimax.io"
MINIMAX_MCP_TIMEOUT = float(
    getattr(settings, "minimax_mcp_timeout_sec", 60.0) or 60.0
)  # seconds
MINIMAX_TOOL_RATE_LIMIT_BUCKET = "internal.minimax_tools"
MINIMAX_MCP_SERVER_NAME = "minimax"
MINIMAX_MCP_TOOL_WEB_SEARCH = "web_search"
MINIMAX_MCP_TOOL_UNDERSTAND_IMAGE = "understand_image"


def _get_minimax_api_key() -> Optional[str]:
    """Get Minimax API key from settings.

    Prefer a dedicated Coding Plan token when configured, falling back to the
    general Minimax API key for compatibility.
    """
    return getattr(settings, "minimax_coding_plan_api_key", None) or getattr(
        settings, "minimax_api_key", None
    )


def _get_minimax_api_host() -> str:
    """Get Minimax API host for MCP/Coding Plan endpoints."""
    return getattr(settings, "minimax_api_host", MINIMAX_API_HOST)


def _get_minimax_mcp_command() -> str:
    """Resolve the MCP server command."""
    command = (getattr(settings, "minimax_mcp_command", None) or "").strip()
    if not command or command == "python":
        return sys.executable
    return command


def _get_minimax_mcp_args() -> List[str]:
    """Resolve the MCP server arguments."""
    args = getattr(settings, "minimax_mcp_args", None) or "-m minimax_mcp.server"
    return shlex.split(args)


def is_minimax_available() -> bool:
    """Check if Minimax tools are available (API key configured)."""
    return bool(_get_minimax_api_key())


def _minimax_mcp_command_available() -> bool:
    command = _get_minimax_mcp_command()
    return bool(shutil.which(command))


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


class MinimaxAPIClient:
    """Client for Minimax Coding Plan API (direct HTTP fallback)."""

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

        # Direct Coding Plan search endpoint (same backend used by MCP server).
        payload = {"q": query}

        try:
            response = await client.post(
                f"{self.base_url}/v1/coding_plan/search",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            return self._parse_search_response(result, query, max_results)

        except httpx.HTTPStatusError as e:
            logger.error(
                f"minimax_web_search_http_error status={e.response.status_code} body={e.response.text[:500]}"
            )
            return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            logger.error(f"minimax_web_search_error error='{str(e)}'")
            return {"error": str(e)}

    def _parse_search_response(
        self, response: Dict[str, Any] | str, query: str, max_results: int
    ) -> Dict[str, Any]:
        """Parse Minimax search response into structured results."""
        try:
            payload: Dict[str, Any] | None
            if isinstance(response, str):
                payload = json.loads(response)
            else:
                payload = response

            if not isinstance(payload, dict):
                return {"query": query, "results": [], "related_searches": []}

            error = _extract_base_resp_error(payload)
            if error:
                return {
                    "query": query,
                    "results": [],
                    "related_searches": [],
                    "error": error,
                    "source": "minimax_search",
                }

            organic = payload.get("organic") or payload.get("results") or []
            results: List[Dict[str, Any]] = []
            for item in organic:
                if not isinstance(item, dict):
                    continue
                results.append(
                    {
                        "title": item.get("title") or item.get("name"),
                        "link": item.get("link") or item.get("url"),
                        "snippet": item.get("snippet")
                        or item.get("content")
                        or item.get("summary"),
                    }
                )

            if max_results and len(results) > max_results:
                results = results[:max_results]

            related = payload.get("related") or payload.get("related_searches") or []

            return {
                "query": query,
                "results": results,
                "related_searches": related,
                "source": "minimax_search",
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

        # Handle local file paths by converting to base64 for direct API calls.
        image_source = await self._prepare_image_source(image_url)
        if isinstance(image_source, dict) and "error" in image_source:
            return image_source

        payload = {
            "prompt": prompt,
            "image_url": image_source,
        }

        try:
            response = await client.post(
                f"{self.base_url}/v1/coding_plan/vlm",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            return self._parse_image_response(result, prompt, image_url)

        except httpx.HTTPStatusError as e:
            logger.error(
                f"minimax_understand_image_http_error status={e.response.status_code}"
            )
            return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            logger.error(f"minimax_understand_image_error error='{str(e)}'")
            return {"error": str(e)}

    async def _prepare_image_source(self, image_url: str) -> str | Dict[str, Any]:
        """Prepare image source for Coding Plan VLM endpoint.

        Accepts URLs, base64 data URLs, or local file paths. Returns a data URL
        for local files so the request can be sent directly to Minimax.
        """
        if image_url.startswith(("http://", "https://", "data:")):
            return image_url

        path = Path(image_url)
        if not path.exists():
            return {"error": f"File not found: {image_url}"}

        if path.stat().st_size > 20 * 1024 * 1024:
            return {"error": "Image file exceeds 20MB limit"}

        suffix = path.suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(suffix, "image/jpeg")

        try:
            with open(path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            return f"data:{mime_type};base64,{image_data}"
        except Exception as e:
            return {"error": f"Failed to read image: {str(e)}"}

    def _parse_image_response(
        self, response: Dict[str, Any], prompt: str, image_url: str
    ) -> Dict[str, Any]:
        """Parse Minimax image understanding response."""
        try:
            error = _extract_base_resp_error(response)
            if error:
                return {
                    "prompt": prompt,
                    "image_url": image_url,
                    "analysis": "",
                    "error": error,
                    "source": "minimax_vision",
                }

            content = response.get("content")
            if content is None and "choices" in response:
                choices = response.get("choices", [])
                if choices:
                    message = choices[0].get("message", {})
                    content = message.get("content", "")

            if content is None:
                return {
                    "prompt": prompt,
                    "image_url": image_url,
                    "analysis": "",
                    "error": "No response",
                }

            return {
                "prompt": prompt,
                "image_url": image_url,
                "analysis": content,
                "source": "minimax_vision",
            }

        except Exception as e:
            logger.warning(f"minimax_parse_image_error error='{str(e)}'")
            return {
                "prompt": prompt,
                "image_url": image_url,
                "analysis": "",
                "error": str(e),
            }


# Singleton client instances
_minimax_api_client: Optional[MinimaxAPIClient] = None
_api_client_lock = asyncio.Lock()

_minimax_mcp_client: Optional[MultiServerMCPClient] = None
_minimax_mcp_tools: Dict[str, BaseTool] = {}
_mcp_client_lock = asyncio.Lock()
_mcp_tools_lock = asyncio.Lock()


def _resolve_mcp_timeout() -> Optional[float]:
    """Resolve the timeout for MCP tool calls (seconds)."""
    try:
        timeout = float(getattr(settings, "minimax_mcp_timeout_sec", 60.0) or 60.0)
    except (TypeError, ValueError):
        timeout = 60.0
    if timeout <= 0:
        return None
    return timeout


async def _reset_minimax_mcp_client(reason: str) -> None:
    """Reset MCP client/tool cache after failures to avoid stuck sessions."""
    global _minimax_mcp_client
    async with _mcp_client_lock:
        _minimax_mcp_client = None
        _minimax_mcp_tools.clear()
    logger.warning("minimax_mcp_client_reset", reason=reason)


async def get_minimax_api_client() -> Optional[MinimaxAPIClient]:
    """Get or create Minimax API client singleton."""
    global _minimax_api_client

    api_key = _get_minimax_api_key()
    if not api_key:
        return None

    async with _api_client_lock:
        if _minimax_api_client is None:
            base_url = _get_minimax_api_host()
            _minimax_api_client = MinimaxAPIClient(api_key, base_url)

    return _minimax_api_client


def _build_minimax_mcp_connection(api_key: str) -> Dict[str, Any]:
    """Build MCP connection configuration for the Minimax Coding Plan server."""
    env = os.environ.copy()
    env.update(
        {
            "MINIMAX_API_KEY": api_key,
            "MINIMAX_API_HOST": _get_minimax_api_host(),
        }
    )
    env["MINIMAX_MCP_REAL_COMMAND"] = _get_minimax_mcp_command()
    env["MINIMAX_MCP_REAL_ARGS"] = json.dumps(_get_minimax_mcp_args())
    return {
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-m", "app.agents.unified.minimax_mcp_wrapper"],
        "env": env,
    }


async def _get_minimax_mcp_client() -> Optional[MultiServerMCPClient]:
    if not MCP_AVAILABLE:
        return None
    api_key = _get_minimax_api_key()
    if not api_key:
        return None
    if not _minimax_mcp_command_available():
        logger.warning(
            "minimax_mcp_command_missing",
            command=_get_minimax_mcp_command(),
        )
        return None

    global _minimax_mcp_client
    async with _mcp_client_lock:
        if _minimax_mcp_client is None:
            config: Dict[str, Any] = {
                MINIMAX_MCP_SERVER_NAME: _build_minimax_mcp_connection(api_key)
            }
            _minimax_mcp_client = MultiServerMCPClient(cast(Any, config))
            _minimax_mcp_tools.clear()
            logger.info(
                "minimax_mcp_client_initialized", server=MINIMAX_MCP_SERVER_NAME
            )

    return _minimax_mcp_client


async def _get_minimax_mcp_tool(tool_name: str) -> Optional[BaseTool]:
    client = await _get_minimax_mcp_client()
    if client is None:
        return None

    cached = _minimax_mcp_tools.get(tool_name)
    if cached is not None:
        return cached

    timeout = _resolve_mcp_timeout()
    reset_reason: Optional[str] = None

    async with _mcp_tools_lock:
        # Another caller may have loaded the cache while we were waiting.
        cached = _minimax_mcp_tools.get(tool_name)
        if cached is not None:
            return cached

        try:
            if timeout:
                tools = await asyncio.wait_for(
                    client.get_tools(server_name=MINIMAX_MCP_SERVER_NAME),
                    timeout=timeout,
                )
            else:
                tools = await client.get_tools(server_name=MINIMAX_MCP_SERVER_NAME)
        except asyncio.TimeoutError:
            logger.warning(
                "minimax_mcp_tools_load_timeout",
                timeout=timeout,
                server=MINIMAX_MCP_SERVER_NAME,
            )
            reset_reason = "tools_load_timeout"
            tools = []
        except Exception as exc:
            sub_errors = []
            if hasattr(exc, "exceptions"):
                try:
                    sub_errors = [str(sub_exc) for sub_exc in getattr(exc, "exceptions")]
                except Exception:
                    sub_errors = []
            logger.warning(
                "minimax_mcp_tools_load_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                sub_errors=sub_errors or None,
            )
            reset_reason = "tools_load_failed"
            tools = []

        for tool_item in tools:
            _minimax_mcp_tools[tool_item.name] = tool_item

        if _minimax_mcp_tools:
            logger.debug(
                "minimax_mcp_tools_cached",
                count=len(_minimax_mcp_tools),
                server=MINIMAX_MCP_SERVER_NAME,
            )

    if reset_reason:
        await _reset_minimax_mcp_client(reset_reason)
        return None

    return _minimax_mcp_tools.get(tool_name)


def _extract_base_resp_error(payload: Dict[str, Any]) -> Optional[str]:
    base_resp = payload.get("base_resp") or payload.get("baseResp")
    if not isinstance(base_resp, dict):
        return None
    status_code = base_resp.get("status_code") or base_resp.get("statusCode")
    if status_code is None:
        return None
    try:
        code = int(status_code)
    except Exception:
        code = None
    if not code or code == 0:
        return None
    message = base_resp.get("status_msg") or base_resp.get("statusMsg") or "unknown"
    return f"{code}: {message}"


async def _invoke_minimax_mcp_tool(
    tool_name: str,
    args: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    tool = await _get_minimax_mcp_tool(tool_name)
    if tool is None:
        return None

    timeout = _resolve_mcp_timeout()
    try:
        if timeout:
            result = await asyncio.wait_for(tool.ainvoke(args), timeout=timeout)
        else:
            result = await tool.ainvoke(args)
    except asyncio.TimeoutError:
        logger.warning(
            "minimax_mcp_tool_invoke_timeout",
            tool=tool_name,
            timeout=timeout,
        )
        await _reset_minimax_mcp_client("invoke_timeout")
        return {"error": "minimax_mcp_timeout"}
    except Exception as exc:
        logger.warning("minimax_mcp_tool_invoke_failed", tool=tool_name, error=str(exc))
        await _reset_minimax_mcp_client("invoke_failed")
        return {"error": str(exc)}

    if isinstance(result, dict):
        return result
    return {"data": result}


def _extract_mcp_text(result: Any) -> Optional[str]:
    """Extract text content from MCP tool responses."""
    if result is None:
        return None

    if hasattr(result, "content"):
        return _extract_mcp_text(getattr(result, "content"))

    if isinstance(result, dict):
        if "structured_content" in result:
            try:
                return json.dumps(result["structured_content"])
            except Exception:
                return None
        if "data" in result:
            return _extract_mcp_text(result["data"])

    if isinstance(result, list):
        texts = []
        for item in result:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        if texts:
            return "\n".join(texts)

    if isinstance(result, str):
        return result

    return None


def _normalize_mcp_web_search_result(
    result: Any,
    query: str,
    max_results: int,
) -> Dict[str, Any]:
    """Normalize Minimax MCP web search results."""
    payload: Dict[str, Any] | None = None
    text: Optional[str] = None

    if isinstance(result, dict) and isinstance(result.get("structured_content"), dict):
        payload = result["structured_content"]
    else:
        text = _extract_mcp_text(result)
        if text:
            try:
                payload = json.loads(text)
            except Exception:
                payload = None

    if not isinstance(payload, dict):
        if text:
            return {
                "query": query,
                "results": [{"content": text}],
                "related_searches": [],
                "source": "minimax_mcp_web_search",
            }
        return {
            "query": query,
            "results": [],
            "related_searches": [],
            "source": "minimax_mcp_web_search",
        }

    error = _extract_base_resp_error(payload)
    if error:
        return {
            "query": query,
            "results": [],
            "related_searches": [],
            "error": error,
            "source": "minimax_mcp_web_search",
        }

    organic = payload.get("organic") or payload.get("results") or []
    results: List[Dict[str, Any]] = []
    for item in organic:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": item.get("title") or item.get("name"),
                "link": item.get("link") or item.get("url"),
                "snippet": item.get("snippet")
                or item.get("content")
                or item.get("summary"),
            }
        )

    if max_results and len(results) > max_results:
        results = results[:max_results]

    related = payload.get("related") or payload.get("related_searches") or []

    return {
        "query": query,
        "results": results,
        "related_searches": related,
        "source": "minimax_mcp_web_search",
    }


def _normalize_mcp_image_result(
    result: Any,
    prompt: str,
    image_url: str,
) -> Dict[str, Any]:
    """Normalize Minimax MCP image understanding output."""
    content = _extract_mcp_text(result) or ""
    if content.lower().startswith("failed to perform vlm analysis"):
        return {
            "prompt": prompt,
            "image_url": image_url,
            "analysis": "",
            "error": content,
            "source": "minimax_mcp_vision",
        }
    return {
        "prompt": prompt,
        "image_url": image_url,
        "analysis": content,
        "source": "minimax_mcp_vision",
    }


# =============================================================================
# Tool Definitions
# =============================================================================


@tool("minimax_web_search", args_schema=MinimaxWebSearchInput)
@rate_limited(MINIMAX_TOOL_RATE_LIMIT_BUCKET, fail_gracefully=True)
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

    logger.info(
        f"minimax_web_search_invoked query='{query[:100]}' max_results={max_results}"
    )

    mcp_result = await _invoke_minimax_mcp_tool(
        MINIMAX_MCP_TOOL_WEB_SEARCH,
        {"query": query},
    )
    if mcp_result is not None and not mcp_result.get("error"):
        normalized = _normalize_mcp_web_search_result(mcp_result, query, max_results)
        if normalized.get("error"):
            logger.warning(
                f"minimax_mcp_web_search_failed query='{query[:50]}' error='{normalized.get('error')}'"
            )
        else:
            result_count = len(normalized.get("results", []))
            logger.info(
                f"minimax_mcp_web_search_success query='{query[:50]}' results={result_count}"
            )
            return normalized
    if mcp_result is not None and mcp_result.get("error"):
        logger.warning(
            f"minimax_mcp_web_search_failed query='{query[:50]}' error='{mcp_result.get('error')}'"
        )

    client = await get_minimax_api_client()
    if not client:
        logger.warning("minimax_web_search_unavailable reason='api_key_not_configured'")
        return {
            "error": "Minimax API key not configured. Set MINIMAX_API_KEY in environment."
        }

    result = await client.web_search(query, max_results)

    if "error" not in result:
        result_count = len(result.get("results", []))
        logger.info(
            f"minimax_web_search_success query='{query[:50]}' results={result_count}"
        )
    else:
        logger.warning(
            f"minimax_web_search_failed query='{query[:50]}' error='{result.get('error', 'unknown')}'"
        )

    return result


@tool("minimax_understand_image", args_schema=MinimaxImageUnderstandingInput)
@rate_limited(MINIMAX_TOOL_RATE_LIMIT_BUCKET, fail_gracefully=True)
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

    logger.info(
        f"minimax_understand_image_invoked prompt='{prompt[:100]}' image='{image_url[:100]}'"
    )

    mcp_result = await _invoke_minimax_mcp_tool(
        MINIMAX_MCP_TOOL_UNDERSTAND_IMAGE,
        {"prompt": prompt, "image_source": image_url},
    )
    if mcp_result is not None and not mcp_result.get("error"):
        normalized = _normalize_mcp_image_result(mcp_result, prompt, image_url)
        if normalized.get("error"):
            logger.warning(
                f"minimax_mcp_understand_image_failed prompt='{prompt[:50]}' error='{normalized.get('error')}'"
            )
        else:
            logger.info(f"minimax_mcp_understand_image_success prompt='{prompt[:50]}'")
            return normalized
    if mcp_result is not None and mcp_result.get("error"):
        logger.warning(
            f"minimax_mcp_understand_image_failed prompt='{prompt[:50]}' error='{mcp_result.get('error')}'"
        )

    client = await get_minimax_api_client()
    if not client:
        logger.warning(
            "minimax_understand_image_unavailable reason='api_key_not_configured'"
        )
        return {
            "error": "Minimax API key not configured. Set MINIMAX_API_KEY in environment."
        }

    result = await client.understand_image(prompt, image_url)

    if "error" not in result:
        logger.info(f"minimax_understand_image_success prompt='{prompt[:50]}'")
    else:
        logger.warning(
            f"minimax_understand_image_failed prompt='{prompt[:50]}' error='{result.get('error', 'unknown')}'"
        )

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
