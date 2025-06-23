"""Research Agent implementation using Tavily search + Firecrawl scraper.

Workflow:
1. Search Tavily for relevant URLs (max 5)
2. Scrape each URL with Firecrawl (Redis-cached, retries)
3. Synthesize answer with Gemini 2.5 Flash, returning structured JSON:
   {
       "answer": "... [1] ...",
       "citations": [{"id": 1, "url": "..."}, ...]
   }

Errors are handled gracefully; failures on individual URLs are logged and
ignored. If search fails, an apologetic answer is returned.
"""

from __future__ import annotations

import json
import logging
import os
from typing import List, Optional, TypedDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph

from app.tools.research_tools import get_research_tools


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class ResearchState(TypedDict):
    """State carried between graph nodes."""

    query: str
    urls: List[str]
    documents: List[dict]  # {"url": str, "content": str}
    answer: Optional[str]
    citations: Optional[List[dict]]


# ---------------------------------------------------------------------------
# Tool instances (search, scrape)
# ---------------------------------------------------------------------------

tools = get_research_tools()
search_tool_func = tools[0]  # TavilySearchTool.search
scrape_tool_func = tools[1]  # FirecrawlTool.scrape_url


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def search_node(state: ResearchState):
    """Call Tavily search tool to discover URLs."""

    query = state["query"]
    try:
        result = search_tool_func(query, max_results=5)
        urls = result.get("urls", [])
    except Exception as exc:
        logging.exception("Tavily search failed: %s", exc)
        # Return empty list so downstream nodes can decide what to do
        urls = []

    return {"urls": urls}


def scrape_node(state: ResearchState):
    """Scrape each URL with Firecrawl, accumulating documents."""

    urls = state.get("urls", [])
    documents: List[dict] = []

    for url in urls:
        try:
            scraped = scrape_tool_func(url)
            if isinstance(scraped, dict) and "error" in scraped:
                logging.warning("Scrape error for %s: %s", url, scraped["error"])
                continue

            # Firecrawl returns dict with key `markdown` (preferred) or `content`
            content = (
                scraped.get("markdown")
                or scraped.get("content")
                or json.dumps(scraped)[:2000]
            )

            # Trim very long docs to avoid blowing prompt
            content = content[:5000]
            documents.append({"url": url, "content": content})
        except Exception as exc:
            logging.exception("Scrape failed for %s: %s", url, exc)
            continue

    return {"documents": documents}


def synthesize_node(state: ResearchState):
    """Use Gemini to synthesize answer + citations."""

    query = state["query"]
    documents = state.get("documents", [])

    if not documents:
        return {
            "answer": "I'm sorry, I couldn't find relevant information to answer your question.",
            "citations": [],
        }

    # Build sources text
    sources_text = "\n\n".join(
        [f"[{i+1}] URL: {doc['url']}\nContent:\n{doc['content']}" for i, doc in enumerate(documents)]
    )

    prompt = f"""
You are a diligent research assistant. Using ONLY the information in the SOURCES
section, write a comprehensive answer to the USER QUESTION. Add citation
markers like [1], [2] whenever you use information from a source. Do not invent
information. After the answer, return valid JSON **ONLY** with keys 'answer'
and 'citations'.

USER QUESTION:
{query}

SOURCES:
{sources_text}

Return JSON in this format (no markdown block):
{{
  "answer": "<answer text with citations>",
  "citations": [{{"id": 1, "url": "<url>"}}, ...]
}}
"""

    model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )

    try:
        response = model.invoke(prompt)
        text = response.content.strip()
        data = json.loads(text)
        # Fallback if model didn't return expected schema
        answer = data.get("answer") if isinstance(data, dict) else text
        citations = data.get("citations", []) if isinstance(data, dict) else []
    except Exception as exc:
        logging.exception("Gemini synthesis failed: %s", exc)
        answer = "Failed to generate answer due to an internal error."
        citations = []

    return {"answer": answer, "citations": citations}


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def get_research_graph():
    graph = StateGraph(ResearchState)

    graph.add_node("search", search_node)
    graph.add_node("scrape", scrape_node)
    graph.add_node("synthesize", synthesize_node)

    # Connections: search -> scrape -> synthesize -> END
    graph.set_entry_point("search")
    graph.add_edge("search", "scrape")
    graph.add_edge("scrape", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# CLI test harness
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    query_text = " ".join(sys.argv[1:]) or "What are the latest advancements in generative AI?"

    graph = get_research_graph()
    state: ResearchState = {
        "query": query_text,
        "urls": [],
        "documents": [],
        "answer": None,
        "citations": None,
    }

    result = graph.invoke(state)
    print(json.dumps({k: v for k, v in result.items() if k in ("answer", "citations")}, indent=2))