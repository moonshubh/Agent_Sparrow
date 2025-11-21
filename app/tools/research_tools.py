import os
from dotenv import load_dotenv
import json
import redis

from app.core.settings import settings
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import time

# Optional third-party SDKs – import gracefully so tests don't fail if
# the packages are not installed in the current environment.  Fallbacks
# are provided below so that the overall application can still import
# even when these optional dependencies are absent (e.g. in CI where we
# only run unit tests that don't require actual web requests).

try:  # pragma: no cover – optional dependency
    from firecrawl import FirecrawlApp  # type: ignore
except ImportError:  # pragma: no cover
    FirecrawlApp = None  # type: ignore

try:  # pragma: no cover – optional dependency
    from tavily import TavilyClient  # type: ignore
except ImportError:  # pragma: no cover
    TavilyClient = None  # type: ignore

# Load environment variables from .env file (noop if file missing)
load_dotenv()

# Redis URL
REDIS_URL = settings.redis_url
# 24 hours TTL for scrape cache
SCRAPE_CACHE_TTL_SEC = int(os.getenv("SCRAPE_CACHE_TTL_SEC", "86400"))

# Helper to get a singleton Redis client
_redis_client: redis.Redis | None = None

def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client

class TavilySearchTool:
    """LangChain-compatible tool that queries the Tavily Search API and returns a
    JSON object with a list of relevant URLs. The Tavily API key must be set in
    the environment variable ``TAVILY_API_KEY``.

    Returns
    -------
    dict
        Example::

            {
                "urls": [
                    "https://example.com/foo",
                    "https://example.com/bar"
                ]
            }
    """

    def __init__(self):
        # Disable tool if SDK missing or API key not set
        if TavilyClient is None:
            # SDK not installed – operate in disabled mode
            self.client = None  # type: ignore[assignment]
            self.disabled = True
            return

        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            # Operate in disabled mode when key missing
            self.client = None  # type: ignore[assignment]
            self.disabled = True
            return

        # `tavily-python` exposes a TavilyClient – full functionality
        self.client = TavilyClient(api_key=api_key)
        self.disabled = False

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    def search(self, query: str, max_results: int = 10) -> dict:  # noqa: D401
        """Search the web with Tavily and return the top *max_results* URLs."""

        if self.disabled:
            # Return empty list while still conforming to schema
            return {"urls": []}

        results = self.client.search(query=query, max_results=max_results)

        structured_results = results.get("results", [])
        urls = []
        for item in structured_results:
            url = item.get("url")
            if url:
                urls.append(url)
            if len(urls) >= max_results:
                break

        return {
            "query": query,
            "results": structured_results[:max_results],
            "urls": urls,
            "attribution": results.get("attribution"),
        }


class FirecrawlTool:
    def __init__(self):
        """
        Initializes the FirecrawlTool with the API key.
        """
        # Firecrawl SDK may be missing in local test envs – fall back to
        # a disabled stub instance when import fails or key missing.
        if FirecrawlApp is None:
            self.app = None  # type: ignore[assignment]
            self.disabled = True
            return

        api_key = os.getenv("FIRECRAWL_API_KEY")
        if not api_key:
            self.app = None  # type: ignore[assignment]
            self.disabled = True
            return

        self.app = FirecrawlApp(api_key=api_key)  # type: ignore[arg-type]
        self.disabled = False

        # Redis client for caching
        self.redis = _get_redis()

    def scrape_url(self, url: str):
        """
        Scrapes a URL using Firecrawl.

        Args:
            url (str): The URL to scrape.

        Returns:
            dict: The scraped data.
        """
        if self.disabled:
            return {"error": "firecrawl_disabled"}

        cache_key = f"firecrawl:{url}"

        # Check cache first
        if cached := self.redis.get(cache_key):
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                # Fall through to re-scrape if cache is corrupt
                pass

        # Respect a minimal delay between subsequent API calls (simple rate-limit)
        time.sleep(1)

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
        )
        def _call_firecrawl(u: str):
            # Firecrawl v2 exposes `.scrape()` rather than `scrape_url()`.
            scrape_fn = getattr(self.app, "scrape", None)
            if scrape_fn is None:
                raise AttributeError("Firecrawl client missing `scrape` method")
            return scrape_fn(u)

        try:
            scraped_data = _call_firecrawl(url)
            # Cache result
            self.redis.setex(cache_key, SCRAPE_CACHE_TTL_SEC, json.dumps(scraped_data))
            return scraped_data
        except Exception as e:  # pragma: no cover
            # Do not cache failures; propagate structured error
            return {"error": str(e)}

    def search(self, query: str):
        """
        Performs a search using Firecrawl.

        Args:
            query (str): The search query.

        Returns:
            dict: The search results.
        """
        if self.disabled:
            return {"error": "firecrawl_disabled"}

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
        )
        def _call_search(q: str):
            return self.app.search(q)

        try:
            results = _call_search(query)
            return results
        except Exception as e:  # pragma: no cover
            return {"error": str(e)}


# Convenience helper to expose all research-related tools from a single place

def get_research_tools() -> list[callable]:
    """Return instantiated research tools for agent binding.

    When optional dependencies or API keys are missing, we fall back to
    lightweight no-op lambdas so that the rest of the application and its
    tests can import without failure.  This approach avoids hard runtime
    requirements on heavy external services during CI while still allowing
    full functionality in production environments where the dependencies are
    installed and configured.
    """
    tools: list[callable] = []

    # Tavily search tool
    try:
        tavily_tool = TavilySearchTool()
        if getattr(tavily_tool, "disabled", False):  # type: ignore[attr-defined]
            raise RuntimeError("Tavily disabled")
        tools.append(tavily_tool.search)
    except Exception:  # pragma: no cover – fall back to stub
        tools.append(lambda query, max_results=10: {"urls": []})

    # Firecrawl scrape tool
    try:
        firecrawl_tool = FirecrawlTool()
        if getattr(firecrawl_tool, "disabled", False):  # type: ignore[attr-defined]
            raise RuntimeError("Firecrawl disabled")
        tools.append(firecrawl_tool.scrape_url)
    except Exception:  # pragma: no cover – fall back to stub
        tools.append(lambda url: {"error": "firecrawl_disabled"})

    return tools


if __name__ == '__main__':
    # Example usage (for testing purposes)
    firecrawl_tool = FirecrawlTool()

    # Example scrape
    url_to_scrape = "https://example.com"
    scraped_content = firecrawl_tool.scrape_url(url_to_scrape)
    print(f"Scraped Content for {url_to_scrape}:")
    print(scraped_content)

    # Example search
    search_query = "latest advancements in AI"
    search_results_data = firecrawl_tool.search(search_query)
    print(f"\nSearch Results for '{search_query}':")
    print(search_results_data)
