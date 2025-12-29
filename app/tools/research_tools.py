import os
import time
from typing import Any, Optional

from dotenv import load_dotenv
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

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

# NOTE: Redis caching for Firecrawl has been removed.
# Firecrawl caching is handled by the service itself via the `max_age` parameter
# when using scrape endpoints. The unified tool wrappers avoid extra cache layers.

class TavilySearchTool:
    """Enhanced Tavily Search Tool with full API feature support.

    Supports:
    - Basic and advanced search depth for comprehensive results
    - Domain filtering (include/exclude specific domains)
    - Recency filtering (limit results to recent days)
    - Image search results
    - Content extraction from URLs

    The Tavily API key must be set in the environment variable ``TAVILY_API_KEY``.

    Returns
    -------
    dict
        Example::

            {
                "query": "search query",
                "results": [...],
                "urls": ["https://example.com/foo", ...],
                "images": [{url, alt, source}, ...],
                "attribution": "..."
            }
    """

    def __init__(self, api_key: Optional[str] = None):
        # Disable tool if SDK missing or API key not set
        if TavilyClient is None:
            # SDK not installed – operate in disabled mode
            self.client = None  # type: ignore[assignment]
            self.disabled = True
            return

        api_key = api_key or os.getenv("TAVILY_API_KEY")
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
    def search(
        self,
        query: str,
        max_results: int = 10,
        include_images: bool = True,
        search_depth: str = "advanced",  # NEW: "basic" or "advanced"
        include_domains: list | None = None,  # NEW: Only search these domains
        exclude_domains: list | None = None,  # NEW: Exclude these domains
        days: int | None = None,  # NEW: Limit to results from last N days
        topic: str | None = None,  # NEW: "general" or "news"
    ) -> dict:  # noqa: D401
        """Search the web with Tavily and return structured results.

        Args:
            query: Search query string
            max_results: Maximum number of results (default: 10)
            include_images: Include image results (default: True)
            search_depth: "basic" for quick search, "advanced" for comprehensive (default: "advanced")
            include_domains: Only return results from these domains
            exclude_domains: Exclude results from these domains
            days: Limit results to last N days (useful for recent news)
            topic: "general" or "news" for topic-specific search

        Returns:
            dict with query, results, urls, images, and attribution
        """

        if self.disabled:
            # Return empty list while still conforming to schema
            return {"urls": [], "images": [], "results": []}

        # Build search kwargs with all supported parameters
        search_kwargs: dict = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,  # Use advanced by default
        }

        # Add optional parameters if provided
        if include_images:
            search_kwargs["include_images"] = True

        if include_domains:
            search_kwargs["include_domains"] = include_domains

        if exclude_domains:
            search_kwargs["exclude_domains"] = exclude_domains

        if days is not None:
            search_kwargs["days"] = days

        if topic:
            search_kwargs["topic"] = topic

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

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    def extract(self, urls: list[str]) -> dict:
        """Extract full content from URLs using Tavily's extract feature.

        This is more comprehensive than search results, providing full page content.

        Args:
            urls: List of URLs to extract content from (max 10)

        Returns:
            dict with extracted content for each URL
        """
        if self.disabled:
            return {"error": "tavily_disabled", "results": []}

        if not urls:
            return {"error": "no_urls_provided", "results": []}

        # Limit to 10 URLs as per Tavily's API limits
        urls = urls[:10]

        try:
            # Use Tavily's extract API if available
            if hasattr(self.client, 'extract'):
                results = self.client.extract(urls=urls)
                return {
                    "urls": urls,
                    "results": results.get("results", []),
                    "failed_results": results.get("failed_results", []),
                }
            else:
                # Fallback: use search with the URLs as queries
                all_results = []
                for url in urls:
                    try:
                        result = self.client.search(
                            query=f"site:{url}",
                            max_results=1,
                            include_answer=True,
                        )
                        if result.get("results"):
                            all_results.append({
                                "url": url,
                                "content": result["results"][0].get("content", ""),
                                "raw_content": result["results"][0].get("raw_content", ""),
                            })
                    except Exception:
                        all_results.append({"url": url, "error": "extraction_failed"})

                return {"urls": urls, "results": all_results}

        except Exception as e:
            return {"error": str(e), "results": []}


class FirecrawlTool:
    """Enhanced Firecrawl integration with full API support.

    Supports: scrape, search, map, crawl, and extract operations.

    NOTE: Caching is handled by Firecrawl via the `max_age` parameter on scrape
    calls. This class provides the direct SDK interface without additional
    caching to avoid redundant cache layers.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initializes the FirecrawlTool with the API key.
        """
        # Firecrawl SDK may be missing in local test envs – fall back to
        # a disabled stub instance when import fails or key missing.
        if FirecrawlApp is None:
            self.app = None  # type: ignore[assignment]
            self.disabled = True
            return

        api_key = api_key or os.getenv("FIRECRAWL_API_KEY")
        if not api_key:
            self.app = None  # type: ignore[assignment]
            self.disabled = True
            return

        self.app = FirecrawlApp(api_key=api_key)  # type: ignore[arg-type]
        self.disabled = False

    @staticmethod
    def _normalize_result(result: Any) -> dict:
        if isinstance(result, dict):
            return result
        if hasattr(result, "model_dump"):
            return result.model_dump()  # type: ignore[call-arg]
        if hasattr(result, "dict"):
            return result.dict()  # type: ignore[call-arg]
        return {"data": result}

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
            return self._normalize_result(_call_firecrawl(url))
        except Exception as e:  # pragma: no cover
            return {"error": str(e)}

    def scrape_with_options(
        self,
        url: str,
        formats: list | None = None,
        actions: list | None = None,
        wait_for: int | None = None,
        only_main_content: bool = True,
        json_schema: dict | None = None,
        mobile: bool = False,
        location: dict | None = None,
        max_age: int | None = None,
        proxy: str | None = None,
        parsers: list | None = None,
        remove_base64_images: bool = False,
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
            if json_schema and "json" not in formats:
                processed_formats.append({"type": "json", "schema": json_schema})
            scrape_params["formats"] = processed_formats
        else:
            if json_schema:
                scrape_params["formats"] = [{"type": "json", "schema": json_schema}]
            else:
                scrape_params["formats"] = ["markdown"]

        if actions:
            scrape_params["actions"] = actions

        if wait_for is not None:
            scrape_params["wait_for"] = wait_for

        scrape_params["only_main_content"] = only_main_content

        if mobile:
            scrape_params["mobile"] = True

        if location:
            scrape_params["location"] = location

        if proxy:
            scrape_params["proxy"] = proxy

        if parsers:
            scrape_params["parsers"] = parsers

        if remove_base64_images:
            scrape_params["remove_base64_images"] = True

        if max_age is not None:
            scrape_params["max_age"] = max_age

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
            return self._normalize_result(result)
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
            return self._normalize_result(results)
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

        search_params: dict = {"query": query, "limit": limit}

        if sources:
            search_params["sources"] = sources

        if scrape_options:
            search_params["scrape_options"] = scrape_options

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
        )
        def _call_search():
            return self.app.search(**search_params)

        try:
            return self._normalize_result(_call_search())
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

        map_params: dict = {"url": url, "limit": limit}

        if search:
            map_params["search"] = search

        if include_subdomains:
            map_params["include_subdomains"] = True

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
        )
        def _call_map():
            return self.app.map(**map_params)

        try:
            return self._normalize_result(_call_map())
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
            "max_discovery_depth": min(max_depth, 5),
        }

        if include_paths:
            crawl_params["include_paths"] = include_paths

        if exclude_paths:
            crawl_params["exclude_paths"] = exclude_paths

        if scrape_options:
            crawl_params["scrape_options"] = scrape_options

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
            return self.app.start_crawl(**crawl_params)

        try:
            if limit <= 10:
                # Synchronous crawl for small jobs
                results = _call_crawl()
                return {
                    "status": "completed",
                    "data": self._normalize_result(results),
                }
            else:
                # Async crawl for larger jobs
                response = _start_async_crawl()
                normalized = self._normalize_result(response)
                crawl_id = normalized.get("id")
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
            return self.app.get_crawl_status(crawl_id)

        try:
            result = _call_status()
            return self._normalize_result(result)
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

        extract_params: dict = {"urls": urls}

        if prompt:
            extract_params["prompt"] = prompt

        if schema:
            extract_params["schema"] = schema

        if enable_web_search:
            extract_params["enable_web_search"] = True

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
        )
        def _call_extract():
            return self.app.extract(**extract_params)

        try:
            return self._normalize_result(_call_extract())
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
