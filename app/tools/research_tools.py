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
    if not REDIS_URL:
        raise RuntimeError("REDIS_URL not configured")
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
    def search(self, query: str, max_results: int = 10, include_images: bool = True) -> dict:  # noqa: D401
        """Search the web with Tavily and return the top *max_results* URLs.
        
        When include_images is True, also attempts to retrieve image results
        which are surfaced in the 'images' key of the response.
        """

        if self.disabled:
            # Return empty list while still conforming to schema
            return {"urls": [], "images": []}

        # Request images if available (Tavily supports include_images parameter)
        search_kwargs = {
            "query": query,
            "max_results": max_results,
        }
        
        # Try to include images if the API supports it
        if include_images:
            search_kwargs["include_images"] = True
            
        results = self.client.search(**search_kwargs)

        structured_results = results.get("results", [])
        urls = []
        for item in structured_results:
            url = item.get("url")
            if url:
                urls.append(url)
            if len(urls) >= max_results:
                break

        # Extract images from results
        # Tavily may return images in the main response or within individual results
        images = []
        
        # Check for top-level images array (Tavily API may include this)
        raw_images = results.get("images", [])
        if isinstance(raw_images, list):
            for img in raw_images[:10]:  # Limit to 10 images
                if isinstance(img, str):
                    # Simple URL string
                    images.append({
                        "url": img,
                        "alt": f"Search result image for: {query}",
                        "source": "tavily",
                    })
                elif isinstance(img, dict):
                    # Structured image object
                    images.append({
                        "url": img.get("url") or img.get("src", ""),
                        "alt": img.get("alt") or img.get("title") or f"Image for: {query}",
                        "source": img.get("source") or "tavily",
                        "width": img.get("width"),
                        "height": img.get("height"),
                    })
        
        # Also check individual results for thumbnail/image fields
        for item in structured_results[:max_results]:
            thumbnail = item.get("thumbnail") or item.get("image") or item.get("img")
            if thumbnail and isinstance(thumbnail, str) and thumbnail.startswith("http"):
                # Avoid duplicates
                if not any(img.get("url") == thumbnail for img in images):
                    images.append({
                        "url": thumbnail,
                        "alt": item.get("title") or f"Thumbnail for: {query}",
                        "source": item.get("url") or "tavily",
                    })

        return {
            "query": query,
            "results": structured_results[:max_results],
            "urls": urls,
            "images": images,
            "attribution": results.get("attribution"),
        }


class FirecrawlTool:
    """Enhanced Firecrawl integration with full API support.

    Supports: scrape, search, map, crawl, and extract operations.
    """

    # Cache TTL constants (in seconds)
    MAP_CACHE_TTL = 3600  # 1 hour for map results (sites change)
    SEARCH_CACHE_TTL = 3600  # 1 hour for search results
    EXTRACT_CACHE_TTL = 86400  # 24 hours for extract results

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
        try:
            self.redis = _get_redis()
        except Exception:
            # Cache is best-effort; Firecrawl should still work without Redis.
            self.redis = None

    def _get_cache(self, cache_key: str) -> dict | None:
        """Retrieve cached result if available."""
        if self.redis is None:
            return None
        try:
            cached = self.redis.get(cache_key)
            if not cached:
                return None
            return json.loads(cached)
        except Exception:
            return None

    def _set_cache(self, cache_key: str, data: dict, ttl: int = SCRAPE_CACHE_TTL_SEC):
        """Store result in cache with TTL."""
        if self.redis is None:
            return
        try:
            self.redis.setex(cache_key, ttl, json.dumps(data, default=str))
        except Exception:
            pass  # Don't fail on cache errors

    def scrape_url(self, url: str) -> dict:
        """
        Scrapes a URL using Firecrawl (basic mode).

        Args:
            url (str): The URL to scrape.

        Returns:
            dict: The scraped data.
        """
        if self.disabled:
            return {"error": "firecrawl_disabled"}

        cache_key = f"firecrawl:scrape:{url}"

        # Check cache first
        if cached := self._get_cache(cache_key):
            return cached

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
            self._set_cache(cache_key, scraped_data)
            return scraped_data
        except Exception as e:  # pragma: no cover
            # Do not cache failures; propagate structured error
            return {"error": str(e)}

    def scrape_with_options(
        self,
        url: str,
        formats: list | None = None,
        actions: list | None = None,
        wait_for: int | None = None,
        only_main_content: bool = True,
        json_schema: dict | None = None,
    ) -> dict:
        """
        Scrape a URL with advanced options (screenshots, actions, JSON mode).

        Args:
            url: The URL to scrape.
            formats: Output formats - markdown, html, screenshot, links, rawHtml.
            actions: Page actions before scraping (click, scroll, wait, write, press).
            wait_for: Wait time in milliseconds for dynamic content.
            only_main_content: Extract main content only (default True).
            json_schema: JSON schema for structured extraction.

        Returns:
            dict: Scraped content in requested formats.
        """
        if self.disabled:
            return {"error": "firecrawl_disabled"}

        # Build scrape options
        scrape_params: dict = {"url": url}

        if formats:
            # Handle JSON mode format
            processed_formats = []
            for fmt in formats:
                if fmt == "json" and json_schema:
                    processed_formats.append({"type": "json", "schema": json_schema})
                else:
                    processed_formats.append(fmt)
            scrape_params["formats"] = processed_formats
        else:
            scrape_params["formats"] = ["markdown"]

        if actions:
            scrape_params["actions"] = actions

        if wait_for:
            scrape_params["waitFor"] = wait_for

        time.sleep(1)  # Rate limiting

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
        )
        def _call_scrape():
            scrape_args = dict(scrape_params)
            scrape_url = scrape_args.pop("url", url)
            return self.app.scrape(scrape_url, **scrape_args)

        try:
            result = _call_scrape()
            return result
        except Exception as e:
            return {"error": str(e)}

    def search(self, query: str) -> dict:
        """
        Performs a basic search using Firecrawl.

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

    def search_web(
        self,
        query: str,
        limit: int = 5,
        sources: list | None = None,
        scrape_options: dict | None = None,
    ) -> dict:
        """
        Enhanced web search with multiple sources and scraping options.

        Args:
            query: Search query string.
            limit: Maximum number of results (1-10).
            sources: List of sources - "web", "images", "news".
            scrape_options: Optional scrape configuration for results.

        Returns:
            dict: Search results with optional scraped content.
        """
        if self.disabled:
            return {"error": "firecrawl_disabled"}

        # Check cache
        import hashlib
        cache_key = f"firecrawl:search:{hashlib.md5(f'{query}:{limit}:{sources}'.encode()).hexdigest()}"
        if cached := self._get_cache(cache_key):
            return cached

        search_params: dict = {"query": query, "limit": limit}

        if sources:
            search_params["sources"] = [{"type": s} for s in sources]

        if scrape_options:
            search_params["scrapeOptions"] = scrape_options

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
        )
        def _call_search():
            return self.app.search(**search_params)

        try:
            results = _call_search()
            self._set_cache(cache_key, results, self.SEARCH_CACHE_TTL)
            return results
        except Exception as e:
            return {"error": str(e)}

    def map_website(
        self,
        url: str,
        limit: int = 100,
        search: str | None = None,
        include_subdomains: bool = False,
    ) -> dict:
        """
        Map a website to discover all URLs (extremely fast).

        Args:
            url: Base URL to map.
            limit: Maximum URLs to discover (1-1000).
            search: Filter URLs containing this string.
            include_subdomains: Include subdomains in results.

        Returns:
            dict: List of discovered URLs.
        """
        if self.disabled:
            return {"error": "firecrawl_disabled"}

        # Check cache
        cache_key = f"firecrawl:map:{url}:{limit}:{search or ''}"
        if cached := self._get_cache(cache_key):
            return cached

        map_params: dict = {"url": url, "limit": limit}

        if search:
            map_params["search"] = search

        if include_subdomains:
            map_params["includeSubdomains"] = True

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
        )
        def _call_map():
            return self.app.map(**map_params)

        try:
            results = _call_map()
            self._set_cache(cache_key, results, self.MAP_CACHE_TTL)
            return results
        except Exception as e:
            return {"error": str(e)}

    def crawl(
        self,
        url: str,
        limit: int = 10,
        max_depth: int = 2,
        include_paths: list | None = None,
        exclude_paths: list | None = None,
        scrape_options: dict | None = None,
    ) -> dict:
        """
        Crawl a website and extract content from multiple pages.

        For limit <= 10: Synchronous crawl (waits for completion).
        For limit > 10: Async crawl (returns crawl_id for status polling).

        Args:
            url: Starting URL to crawl.
            limit: Maximum pages to crawl (1-50).
            max_depth: Maximum link depth to follow (1-5).
            include_paths: Only crawl paths matching these patterns.
            exclude_paths: Skip paths matching these patterns.
            scrape_options: Options for scraping each page.

        Returns:
            dict: Crawl results or crawl_id for async jobs.
        """
        if self.disabled:
            return {"error": "firecrawl_disabled"}

        crawl_params: dict = {
            "url": url,
            "limit": min(limit, 50),
            "maxDiscoveryDepth": min(max_depth, 5),
        }

        if include_paths:
            crawl_params["includePaths"] = include_paths

        if exclude_paths:
            crawl_params["excludePaths"] = exclude_paths

        if scrape_options:
            crawl_params["scrapeOptions"] = scrape_options

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
        )
        def _call_crawl():
            return self.app.crawl(**crawl_params)

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
        )
        def _start_async_crawl():
            return self.app.async_crawl(**crawl_params)

        try:
            if limit <= 10:
                # Synchronous crawl for small jobs
                results = _call_crawl()
                return {"status": "completed", "data": results}
            else:
                # Async crawl for larger jobs
                response = _start_async_crawl()
                crawl_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
                return {
                    "status": "started",
                    "crawl_id": crawl_id,
                    "message": f"Async crawl started. Use firecrawl_crawl_status to check progress.",
                }
        except Exception as e:
            return {"error": str(e)}

    def get_crawl_status(self, crawl_id: str) -> dict:
        """
        Check the status of an async crawl job.

        Args:
            crawl_id: The crawl job ID returned from async crawl.

        Returns:
            dict: Crawl status and results if completed.
        """
        if self.disabled:
            return {"error": "firecrawl_disabled"}

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
        )
        def _call_status():
            return self.app.check_crawl_status(crawl_id)

        try:
            result = _call_status()
            return result
        except Exception as e:
            return {"error": str(e)}

    def extract(
        self,
        urls: list,
        prompt: str | None = None,
        schema: dict | None = None,
        enable_web_search: bool = False,
    ) -> dict:
        """
        Extract structured data from web pages using AI.

        Args:
            urls: List of URLs to extract data from.
            prompt: Natural language extraction prompt.
            schema: JSON schema for structured extraction.
            enable_web_search: Enable web search for additional context.

        Returns:
            dict: Extracted structured data.
        """
        if self.disabled:
            return {"error": "firecrawl_disabled"}

        if not prompt and not schema:
            return {"error": "Either prompt or schema must be provided for extraction"}

        # Check cache
        import hashlib
        urls_str = ",".join(sorted(urls))
        cache_key = f"firecrawl:extract:{hashlib.md5(f'{urls_str}:{prompt}:{schema}'.encode()).hexdigest()}"
        if cached := self._get_cache(cache_key):
            return cached

        extract_params: dict = {"urls": urls}

        if prompt:
            extract_params["prompt"] = prompt

        if schema:
            extract_params["schema"] = schema

        if enable_web_search:
            extract_params["enableWebSearch"] = True

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
        )
        def _call_extract():
            return self.app.extract(**extract_params)

        try:
            results = _call_extract()
            self._set_cache(cache_key, results, self.EXTRACT_CACHE_TTL)
            return results
        except Exception as e:
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
