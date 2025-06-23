# Research Agent (v2)

> Production-ready multi-step agent for deep web research with external citations.

This agent addresses complex user queries that **cannot** be fully answered by our internal knowledge base. It automatically:

1. **Searches the web** using Tavily (quality search API).
2. **Scrapes** the discovered pages with Firecrawl and caches results in Redis (24 h TTL).
3. **Synthesises** a concise, cited answer with Google Gemini 2.5 Flash (or optionally Google Gemini 2.5 Pro for more complex queries).

The final JSON response contains `answer` and `citations` keys so the frontend can render linked references.

---

## Setup

### Install dependencies
All required packages are listed in the project-root `requirements.txt` (see `tavily-python`, `firecrawl-py`, `redis`, `tenacity`, `langgraph`, etc.).

```bash
pip install -r requirements.txt
```

### Environment variables
Create/extend your local `.env` with:

| Var | Description |
|-----|-------------|
| `GEMINI_API_KEY` | Google Generative AI key. |
| `TAVILY_API_KEY` | Tavily search key. |
| `FIRECRAWL_API_KEY` | Firecrawl scraping key. |
| `REDIS_URL` | Redis connection URL (default `redis://localhost:6379`). |
| `SCRAPE_CACHE_TTL_SEC` | Optional cache TTL in seconds (default 86400). |

**Important:** Never commit real keys; `.env` is git-ignored.

### Redis (optional, but recommended)
Run a local instance:

```bash
docker run -d --name mb-sparrow-redis -p 6379:6379 redis:7
```

---

## Architecture

```
┌──────────────┐     Tavily Search     ┌─────────────┐
│  search_node │ ───────────────────▶ │   Tavily    │
└──────────────┘                      └─────────────┘
        │ urls (≤5)                          ▲
        ▼                                    │
┌──────────────┐    Firecrawl Scrape   ┌─────────────┐
│  scrape_node │ ───────────────────▶ │  Firecrawl  │
└──────────────┘                      └─────────────┘
        │ documents                           ▲
        ▼                                    │
┌──────────────┐  Gemini 2.5 Flash / Pro  ┌─────────────┐
│ synthesize   │ ────────────────▶ │   Google    │
└──────────────┘                  └─────────────┘
        │ answer + citations
        ▼
      RETURN
```

LangGraph linear flow: `search → scrape → synthesize → END`.

### Source files
* `research_agent.py` – node logic & graph compilation.
* `app/tools/research_tools.py` – Tavily & Firecrawl tools with retry/caching.

---

## Usage

```python
from app.agents_v2.research_agent.research_agent import get_research_graph

graph = get_research_graph()
state = {
    "query": "What were the key features in Windows 11 24H1?",
    "urls": [],
    "documents": [],
    "answer": None,
    "citations": None,
}

result = graph.invoke(state)
print(result["answer"])
# e.g. "Windows 11 24H1 introduces ... [1] ... [2]"
print(result["citations"])
# [{'id': 1, 'url': 'https://...'}, ...]
```

For quick CLI testing:

```bash
python -m app.agents_v2.research_agent.research_agent "Impact of RCS on SMS market"
```

---

## Output Schema

```json
{
  "answer": "string",   // human-readable answer with [n] markers
  "citations": [          // list aligns ids with markers used
    {"id": 1, "url": "https://..."},
    {"id": 2, "url": "https://..."}
  ]
}
```

---

## Error Handling & Observability
* Tenacity retries (3 attempts) & exponential back-off for all external calls.
* Redis cache prevents redundant scrapes, reducing latency & API cost.
* Each failure is **logged** with `logging.exception`; synthesis falls back to an apology or generic error message.
* Instrumentation can be added via OpenTelemetry spans similar to the Primary Agent.

---

## Extending / Future Work
* Replace simple rate-limit sleep with token-bucket if hitting provider caps.
* Add HTML -> markdown post-processing improvements.
* Integrate vector-based deduplication before prompting to further cut token usage.
