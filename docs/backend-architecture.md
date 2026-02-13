# Agent Sparrow Backend Architecture

> **Last updated**: 2026-02-12
>
> Canonical backend architecture reference. Covers system design, unified agent architecture, models, prompts, tools, orchestration, and context engineering.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Unified Agent Architecture](#2-unified-agent-architecture)
3. [Model Configuration](#3-model-configuration)
4. [Prompt Architecture](#4-prompt-architecture)
5. [Tool System](#5-tool-system)
6. [Orchestration Graph](#6-orchestration-graph)
7. [Context Engineering](#7-context-engineering)
8. [Runtime Reference (FeedMe, API, Config, Services, Rate Limiting)](backend-runtime-reference.md)

---

## 1. System Overview

### What is Agent Sparrow?

Agent Sparrow is a **multi-agent AI system** for intelligent customer support automation. It combines:

- **LangGraph v1** for orchestrated agent workflows
- **AG-UI Protocol** for native SSE streaming conversations
- **Supabase** (PostgreSQL + pgvector) for data persistence and vector search
- **Multiple LLM Providers** (Google Gemini, xAI Grok, OpenRouter, Minimax)

### Primary Use Cases

1. **Customer Support Automation** -- Process Zendesk tickets with AI-generated responses
2. **Knowledge Base Search** -- Semantic search across documentation and support history
3. **Document Processing (FeedMe)** -- Extract knowledge from PDFs and support transcripts
4. **Log Analysis** -- Diagnose technical issues from log files

### High-Level Architecture

```
+---------------------------------------------------------------------------+
|                           FRONTEND (Next.js)                              |
|                      AG-UI Client + Chat Interface                        |
+---------------------------------------+-----------------------------------+
                                        |
                                        | SSE Streaming
                                        v
+---------------------------------------------------------------------------+
|                        FASTAPI APPLICATION (app/main.py)                  |
|  +------------------+  +------------------+  +-------------------------+  |
|  | AG-UI Endpoint   |  | FeedMe Module    |  | Zendesk Integration     |  |
|  | /agui/stream     |  | /feedme/*        |  | /integrations/zendesk/* |  |
|  +--------+---------+  +--------+---------+  +------------+------------+  |
|           |                     |                         |               |
|           +---------------------+-------------------------+               |
|                                 |                                         |
|                     +-----------v-----------+                             |
|                     |    UNIFIED AGENT      |                             |
|                     |  (DeepAgents + LCL)   |                             |
|                     |  + Middleware Stack    |                             |
|                     +-----------+-----------+                             |
|                                 |                                         |
|           +---------------------+---------------------+                   |
|           v                     v                     v                   |
|  +----------------+   +----------------+   +----------------+             |
|  | Research       |   | Log Diagnoser  |   | DB Retrieval   |             |
|  | Subagent       |   | Subagent       |   | Subagent       |             |
|  +----------------+   +----------------+   +----------------+             |
+---------------------------------------------------------------------------+
                                 |
        +------------------------+------------------------+
        v                        v                        v
+---------------+       +---------------+       +---------------+
|   Supabase    |       |    Redis      |       |  External     |
|  (PostgreSQL  |       |  (Cache +     |       |  APIs         |
|  + pgvector)  |       |   Celery)     |       |  (LLM, Web)   |
+---------------+       +---------------+       +---------------+
```

### Key Entry Points

| Entry Point | Purpose | Protocol |
|-------------|---------|----------|
| `POST /api/v1/agui/stream` | Primary chat streaming | AG-UI SSE |
| `POST /api/v1/agent/logs` | Log analysis | JSON |
| `POST /api/v1/feedme/conversations/upload` | Document upload | Multipart |
| `POST /integrations/zendesk/webhook` | Ticket webhook | JSON |

### Data Flow: Chat Request

```
1. Frontend sends RunAgentInput to /api/v1/agui/stream
2. AG-UI adapter converts to GraphState
3. Unified agent determines task type (coordinator/heavy/log_analysis)
4. Model selected with health check and fallback chain
5. Memory context retrieved (if enabled)
6. Messages prepared with attachments
7. Agent streams response via SSE
8. Facts extracted and stored in memory
9. Context captured if approaching limit
```

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Web Framework | FastAPI | Async HTTP server |
| Agent Framework | LangChain + LangGraph v1 | Agent orchestration |
| Agent Patterns | DeepAgents | Middleware stack |
| Protocol | ag-ui-langgraph | Native SSE streaming |
| Primary Database | Supabase (PostgreSQL) | Application data |
| Vector Store | pgvector | Semantic search |
| Cache / Queue | Redis + Celery | Caching, rate limiting, background tasks |
| Observability | LangSmith | Agent tracing and monitoring (primary) |
| Tracing | OpenTelemetry | Distributed tracing (optional, via `ENABLE_OTEL`) |

### External Service Integrations

| Service | Purpose | Rate Limits |
|---------|---------|-------------|
| Google Gemini API | LLM + Embeddings | RPM/RPD per model (see models.yaml) |
| xAI Grok API | Alternative LLM | RPM/RPD per model |
| Minimax API | Subagent LLM + web search | RPM/RPD per model |
| OpenRouter | Fallback LLM routing | RPM/RPD per model |
| Tavily | Web search | As needed |
| Firecrawl | Web scraping / extraction | RPM limited |
| Zendesk API | Ticket operations | 300 RPM |

---

## 2. Unified Agent Architecture

### Overview

**Location**: `app/agents/unified/`

All queries flow through a **single coordinator agent** that:
1. **Classifies** the task type using fast keyword matching (<5ms)
2. **Selects** the appropriate model with health checks and fallback chains
3. **Delegates** to specialized subagents when needed
4. **Manages** context and memory across the conversation

**Key Files**:
- `agent_sparrow.py` -- Main orchestrator, agent construction, middleware assembly
- `subagents.py` -- Subagent specifications
- `tools.py` -- Tool definitions
- `prompts.py` -- Tiered prompt templates
- `provider_factory.py` -- Multi-provider model building
- `model_router.py` -- Health-aware model selection

### Task Classification

Task classification now runs under a **hard user-selected mode switch**:

| Mode | Key | Behavior |
|------|-----|----------|
| General Assistant | `general` | Broad assistant behavior with full general toolset |
| Mailbird Expert | `mailbird_expert` | Support-focused behavior, Zendesk-safe guidance |
| Research Expert | `research_expert` | Evidence-first research and synthesis |
| Creative Expert | `creative_expert` | Artifact-first creative execution (image/article workflows) |

**Routing Priority** (source: `app/agents/unified/agent_sparrow.py`):
1. Resolve effective mode from `forwarded_props.agent_mode` (explicit), else map legacy `agent_type`, else default to `general`.
2. Allow legacy tactical override `agent_type=log_analysis` only when mode permits (`general`, `mailbird_expert`, `research_expert`).
3. Apply fast keyword and attachment detection as **hints only** (`task_hint`, `log_detection`) without mode switching.
4. Default coordinator execution path remains `coordinator`.

This prevents automatic cross-mode persona flips while retaining internal subagent orchestration inside the chosen mode.

### Model Selection

**Location**: `app/agents/unified/model_router.py`

The model router performs health-aware selection:

1. Determine task type (coordinator, log_analysis, coordinator_heavy)
2. Get primary model from Model Registry
3. Run async health check (RPM/RPD usage, circuit breaker state)
4. If unavailable, traverse fallback chain
5. Return `ModelSelectionResult` with health trace

**Fallback Chains** (from `models.yaml`):

| Family | Chain |
|--------|-------|
| Google Standard | `gemini-3-flash-preview` -> `gemini-2.5-flash` -> `gemini-2.5-flash-lite` |
| Google Heavy | `gemini-3-pro-preview` -> `gemini-2.5-pro` -> `gemini-2.5-flash` -> `gemini-2.5-flash-lite` |
| OpenRouter | `x-ai/grok-4.1-fast` -> `minimax/minimax-m2.5` |
| XAI | `grok-4-1-fast-reasoning` (no fallback) |

### Subagent Architecture

**Location**: `app/agents/unified/subagents.py`

The coordinator delegates to specialized subagents via the `task` tool:

| Subagent | Purpose | Default Model |
|----------|---------|---------------|
| **research-agent** | Web research, evidence gathering | Minimax M2.5 (via `_default`) |
| **log-diagnoser** | Log analysis, error diagnosis | Minimax M2.5 (via `_default`) |
| **db-retrieval** | KB/macro/FeedMe lookups | Minimax M2.5 (via `_default`) |
| **explorer** | Broad discovery | Minimax M2.5 (via `_default`) |
| **draft-writer** | Structured writing and response composition | Minimax M2.5 (via `_default`) |
| **data-analyst** | Data retrieval and trend analysis | Minimax M2.5 (via `_default`) |

All subagents default to `minimax/MiniMax-M2.5` via the `_default` key in `models.yaml` `subagents` section. Subagent models are configured independently from the coordinator.

**Per-Subagent Summarization Thresholds**:

| Subagent | Summarization Threshold | Messages to Keep |
|----------|------------------------|------------------|
| Research | 100,000 tokens | 4 |
| Log Analysis | 150,000 tokens | 6 |
| DB Retrieval | 80,000 tokens | 3 |

### Middleware Stack

**Source of truth**: `app/agents/unified/agent_sparrow.py` (lines ~791-953)

The agent uses a **DeepAgents middleware stack** for request/response processing. The actual middleware stack is assembled at agent construction time and consists of two layers: a `default_middleware` list (used by subagents) and the outer `middleware_stack` (used by the coordinator).

#### Coordinator Middleware Stack (outer, in order)

| Order | Middleware | Purpose |
|-------|-----------|---------|
| 1 | `LogAutorouteMiddleware` | Deterministically autoroute log attachments into per-file `task` calls |
| 2 | `SubAgentWorkspaceBridge` | Bridge workspace context to subagents (when available) |
| 3 | `SubAgentMiddleware` | Handle subagent delegation (wraps `default_middleware` for subagent runs) |
| 4 | `ToolCallIdSanitizationMiddleware` | Sanitize tool call IDs for OpenAI-compatible providers |
| 5 | `MessageNameSanitizationMiddleware` | Strip `name` fields from non-user messages (xAI compatibility) |

#### Subagent Default Middleware (inner, in order)

| Order | Middleware | Purpose |
|-------|-----------|---------|
| 1 | `ModelRetryMiddleware` | Retry on context overflow / quota exhaustion (max 2 retries, graceful `on_failure="continue"`) |
| 2 | `FractionBasedSummarizationMiddleware` | Summarize at 70% of context window |
| 3 | `ContextEditingMiddleware` | Clear old tool results at 60% of context window (keeps 3 most recent) |
| 4 | `ToolResultEvictionMiddleware` | Evict large tool results (>50K chars) to workspace store |
| 5 | `ToolCallIdSanitizationMiddleware` | Sanitize tool call IDs |
| 6 | `WorkspaceWriteSandboxMiddleware` | Restrict subagent writes to their run directory |
| 7 | `PatchToolCallsMiddleware` | Normalize tool call format (must be last) |

**Provider Token Limits for Summarization** (from `agent_sparrow.py`):

| Provider | Token Limit |
|----------|-------------|
| Google | 50,000 |
| XAI | 80,000 |
| OpenRouter | 50,000 |
| Default | 50,000 |

---

## 3. Model Configuration

### Single Source of Truth: models.yaml

**Location**: `app/core/config/models.yaml`

All model configuration lives in this YAML file: coordinators, internal models, subagents, Zendesk variants, and per-bucket rate limits. The YAML is validated at startup; missing or invalid config is a fatal error.

**Structure**:

```yaml
rate_limiting:
  safety_margin: 0.06       # ~6% headroom

coordinators:
  google:                    # Default Google coordinator
  google_with_subagents:     # Separate quota bucket when subagents enabled
  xai:                       # XAI coordinator
  openrouter:                # OpenRouter coordinator
  minimax:                   # Minimax coordinator

internal:
  summarizer:                # Summarization / state extraction (always Google)
  helper:                    # Lightweight rewrite/rerank (GemmaHelper)
  image:                     # Image generation
  minimax_tools:             # Minimax MCP tools (web search + image understanding)
  feedme:                    # FeedMe extraction / structured parsing
  grounding:                 # Gemini Search Grounding
  embedding:                 # Vector embeddings (gemini-embedding-001)

subagents:
  _default:                  # Default model for all subagents (Minimax M2.5)
  research-agent:            # Falls back to _default
  log-diagnoser:             # Falls back to _default
  db-retrieval:              # Falls back to _default
  explorer:                  # Falls back to _default
  draft-writer:              # Falls back to _default
  data-analyst:              # Falls back to _default

zendesk:
  coordinators:              # Separate Zendesk coordinator quotas
  subagents:                 # Separate Zendesk subagent quotas

fallback:
  strategy: "coordinator"    # When subagent/internal model fails
  coordinator_provider: "google"
```

### Coordinator Models (from models.yaml)

| Key | Model ID | Temperature | Context Window | RPM | RPD |
|-----|----------|-------------|----------------|-----|-----|
| `google` | `gemini-3-flash-preview` | 1.0 | 1,048,576 | 1000 | 10000 |
| `xai` | `grok-4-1-fast-reasoning` | 0.2 | 2,000,000 | 60 | 1000 |
| `openrouter` | `x-ai/grok-4.1-fast` | 0.2 | 2,000,000 | 60 | 1000 |
| `minimax` | `minimax/MiniMax-M2.5` | 1.0 | 204,800 | 100 | 5000 |

### Internal Models (from models.yaml)

| Key | Model ID | Temperature | Purpose |
|-----|----------|-------------|---------|
| `summarizer` | `gemini-2.5-flash-preview-09-2025` | 0.2 | Summarization / state extraction |
| `helper` | `gemini-2.5-flash-lite` | 0.2 | Lightweight rewrite/rerank |
| `image` | `gemini-3-pro-image-preview` | 1.0 | Image generation |
| `feedme` | `gemini-2.5-flash-lite` | 0.3 | FeedMe extraction |
| `grounding` | `gemini-2.5-flash` | 0.2 | Gemini Search Grounding |
| `embedding` | `models/gemini-embedding-001` | -- | Vector embeddings (3072 dims) |

### Model Registry (Legacy Dataclass Interface)

**Location**: `app/core/config/model_registry.py`

The `ModelRegistry` dataclass provides a code-level interface for role-to-model mapping. It coexists with `models.yaml` and supports backward-compatible environment variable overrides.

**Core Dataclasses**:

```python
@dataclass(frozen=True)
class ModelSpec:
    id: str                       # API identifier (e.g., "gemini-3-pro-preview")
    display_name: str             # Human-readable name
    provider: Provider            # GOOGLE or XAI
    tier: ModelTier               # PRO, STANDARD, LITE, or EMBEDDING
    rpm_limit: int = 10
    rpd_limit: int = 250
    supports_reasoning: bool = False
    supports_vision: bool = False
    embedding_dims: Optional[int] = None
```

**Model Tiers**:

| Tier | Description | Models |
|------|-------------|--------|
| `PRO` | Highest capability -- complex reasoning | Gemini 3.0 Pro, Gemini 2.5 Pro, Grok 4 |
| `STANDARD` | Balanced -- general purpose | Gemini 3.0 Flash, Gemini 2.5 Flash, Grok 4.1 Fast |
| `LITE` | Cost-efficient -- simple tasks | Gemini 2.5 Flash Lite |
| `EMBEDDING` | Vector embeddings | Gemini Embedding 001 |

**Environment Variable Overrides**:

| Env Var | Registry Field | Description |
|---------|----------------|-------------|
| `PRIMARY_AGENT_MODEL` | `coordinator_google` | Primary agent model |
| `ENHANCED_LOG_MODEL` | `log_analysis`, `coordinator_heavy` | Heavy reasoning model |
| `ROUTER_MODEL` | `db_retrieval` | Lightweight model |
| `GROUNDING_MODEL` | `grounding` | Search grounding model |
| `FEEDME_MODEL_NAME` | `feedme` | Document processing model |
| `XAI_DEFAULT_MODEL` | `coordinator_xai` | XAI/Grok default |

### Provider Factory

**Location**: `app/agents/unified/provider_factory.py`

`build_chat_model()` constructs a `BaseChatModel` for a given provider/model pair:

```python
from app.agents.unified.provider_factory import build_chat_model

model = build_chat_model(
    provider="google",
    model="gemini-3-flash-preview",
    role="coordinator",  # Optional: resolves temperature from models.yaml
)
```

**Temperature Resolution** (in `get_temperature_for_role()`):
1. If model found in `models.yaml`, use its configured temperature
2. If role matches an internal model key (summarizer, feedme, helper), use that temperature
3. Default: 0.3

**Grok Configuration** (from `provider_factory.py`):

```python
GROK_CONFIG = {
    "reasoning_enabled": True,   # Always enabled per user choice
    "thinking_budget": "medium", # Balanced latency/quality
}
```

When using Grok, reasoning is always enabled. For Grok 3 models, `reasoning_effort: high` is passed via `extra_body`. Grok 4+ models handle reasoning natively.

**Supported Providers**: `google`, `xai`, `openrouter`, `minimax` (routes through OpenRouter code path). Unknown providers fall back to Google.

**Startup Health Checks**: On startup (`app/main.py`), the backend performs real API calls to all configured models. Failures mark the model unavailable and trigger fallback; startup continues.

### API Endpoints for Model Config

```
GET /api/v1/models        -- List available models
GET /api/v1/models/config -- Full model configuration (registry + providers + fallback chains)
```

---

## 4. Prompt Architecture

### Tiered Prompt System

**Location**: `app/agents/unified/prompts.py`

| Tier | Agents | Reasoning | Temperature |
|------|--------|-----------|-------------|
| **Coordinator** | Main coordinator | Canonical 9-step base + mode role overlay | Per models.yaml |
| **Subagents** | `log-diagnoser`, `research-agent`, `explorer`, `db-retrieval`, `draft-writer`, `data-analyst` | Canonical 9-step base + task-specific output contract | Per models.yaml |
| **Zendesk Addendum** | Coordinator in Zendesk / Mailbird contexts | Policy overlays (`ZENDESK_TICKET_GUIDANCE`, conflict resolution) | N/A |

### Canonical 9-Step Reasoning Base

`NINE_STEP_REASONING_BASE` is the shared canonical reasoning framework used by coordinator and subagents.
The block is injected into:
- Coordinator prompt static section
- `LOG_ANALYSIS_PROMPT`
- `RESEARCH_PROMPT`
- `EXPLORER_PROMPT`
- `DATABASE_RETRIEVAL_PROMPT`
- `DRAFT_WRITER_PROMPT`
- `DATA_ANALYST_PROMPT`

1. **Logical Dependencies** -- Analyze constraints, prerequisites, order of operations. Resolve conflicts by priority: Policies > Prerequisites > User preferences.
2. **Risk Assessment** -- LOW for exploratory actions (searches); HIGH for state-changing actions.
3. **Abductive Reasoning** -- Generate 1-3 hypotheses for any problem, prioritize by likelihood but do not discard less probable causes.
4. **Adaptability** -- If observations contradict hypotheses, generate new ones. Update plan based on new information.
5. **Information Sources** -- Prefer internal sources (Memory UI, KB, FeedMe, Macros/playbooks). Use web tools only when internal sources are thin/conflicting. Web tool preference: Minimax -> Tavily -> Firecrawl -> Grounding.
6. **Precision & Grounding** -- Quote exact KB/macro content when referencing. Distinguish evidence from reasoning.
7. **Completeness** -- Exhaust all relevant options before concluding.
8. **Persistence** -- On transient errors: retry (max 2x). On other errors: change strategy.
9. **Inhibited Response** -- Complete reasoning BEFORE taking action.

### Coordinator Prompt Structure

The coordinator prompt is cache-optimized for Gemini implicit caching (large static content first, dynamic content last), with **mode-specific role overlays**:

```
<reasoning_framework>
  [NINE_STEP_REASONING_BASE]
</reasoning_framework>

<instructions>
  [4-step process: PLAN -> EXECUTE -> VALIDATE -> FORMAT]
</instructions>

<mode_role>
  [GENERAL_ASSISTANT_ROLE | MAILBIRD_EXPERT_ROLE | RESEARCH_EXPERT_ROLE | CREATIVE_EXPERT_ROLE]
</mode_role>

<tool_usage>
  [Tool priority and subagent guidance]
</tool_usage>

<web_scraping_guidance>
  [Firecrawl, Tavily, Minimax, Grounding tool decision tree]
</web_scraping_guidance>

<creative_tools>
  [write_article, generate_image guidance]
</creative_tools>

[Optional mode/context overlays]
- Zendesk ticket guidance (ticket contexts)
- Zendesk conflict resolution addendum (Zendesk and Mailbird Expert mode)

[Dynamic tail]
- model name
- current date
- effective mode marker
- skills context
```

### Grok Prompt Addendum

When using Grok, an additional `<grok_configuration>` block is injected:

```xml
<grok_configuration>
Grok reasoning is ALWAYS enabled for maximum quality. Since you use internal
chain-of-thought:
- Do NOT output explicit step-by-step reasoning to the user
- Let your internal reasoning guide tool selection and responses
- Focus user-facing output on clear, actionable answers
- Use your deeper reasoning for hypothesis testing and evidence synthesis
</grok_configuration>
```

### Trace Narration

When trace mode is `narrated`, a `<trace_updates>` block instructs the agent to use the `trace_update` tool for the Progress Updates panel (~3-6 calls per run max, using `kind="phase"` for major stages and `kind="thought"` otherwise).

---

## 5. Tool System

### Overview

**Location**: `app/agents/unified/tools.py`

Tools are registered using LangChain's `@tool` decorator and selected through a mode-scoped registry:
- `get_registered_tools_for_mode(mode, zendesk=False)` (authoritative)
- `get_registered_tools()` (backward-compatible alias to `general`)
- `get_registered_support_tools()` (Mailbird/Zendesk projection)

Image generation (`generate_image`) is registered in all coordinator modes (`general`, `mailbird_expert`, `research_expert`, `creative_expert`) so image generation remains system-wide regardless of active expert mode.

### Tool Categories

#### Knowledge & Retrieval

| Tool | Description |
|------|-------------|
| `kb_search` | Search Mailbird knowledge base |
| `feedme_search` | Search FeedMe document chunks |
| `macro_search` | Search Zendesk macros |
| `supabase_query` | Execute database queries |
| `db_unified_search` | Semantic/hybrid search (used by db-retrieval subagent) |
| `db_grep_search` | Pattern-based search (used by db-retrieval subagent) |
| `db_context_search` | Full document retrieval (used by db-retrieval subagent) |

#### Web Search & Scraping

| Tool | Description |
|------|-------------|
| `minimax_web_search` | Minimax web search (preferred, high quota) |
| `grounding_search` | Gemini search grounding |
| `web_search` | Tavily web search |
| `tavily_extract` | Extract content from URLs |
| `firecrawl_fetch` | Fetch single page content |
| `firecrawl_map` | Discover site URLs |
| `firecrawl_crawl` | Multi-page extraction |
| `firecrawl_extract` | Structured data extraction |
| `firecrawl_search` | Enhanced web search |
| `firecrawl_agent` | Autonomous web research (rate-limited) |

#### Analysis & Creation

| Tool | Description |
|------|-------------|
| `log_diagnoser` | Analyze log file attachments |
| `trace_update` | Add progress updates to the thinking panel |
| `write_article` | Create structured documents/articles as artifacts |
| `generate_image` | Generate images via Gemini |
| `task` | Delegate to a subagent |

### Tool Priority

For Zendesk tickets:
```
db-retrieval (macros/KB) -> kb_search -> feedme_search -> Minimax web search -> Tavily -> Firecrawl -> grounding_search
```

### Mode-Scoped Tool Registry

| Mode | Registry Function | Tooling Profile |
|------|-------------------|-----------------|
| `general` | `_general_mode_tools()` | Full general toolset: retrieval + web + artifacts + optional image generation |
| `mailbird_expert` | `_mailbird_mode_tools()` | Support retrieval + full web suite + artifact/image tools |
| `research_expert` | `_research_mode_tools()` | Retrieval + full web suite + synthesis/article + image tools |
| `creative_expert` | `_creative_mode_tools()` | Image generation + article/artifact workflows + web support |

Zendesk contexts force Mailbird-mode tool selection via `get_registered_tools_for_mode(..., zendesk=True)`.

### Input Hardening

Unified tool input hardening prevents model-argument validation failures:
- `db_unified_search.max_results_per_source` is clamped to prevent validation errors
- `db_grep_search` max results are coerced/clamped
- `web_search` max results are coerced/clamped

See `docs/RELIABILITY.md` for detailed retry and fallback patterns.

---

## 6. Orchestration Graph

### LangGraph v1 Workflow

**Location**: `app/agents/orchestration/orchestration/graph.py`

The orchestration graph is a `StateGraph(GraphState)` with three nodes:

```
                    +-------+
          +-------->| agent |<--------+
          |         +---+---+         |
          |             |             |
          |     (conditional edges)   |
          |        /    |    \        |
          |       /     |     \       |
       +--+--+   |  +---+---+  |  +--+--+
       |tools|   |  |subgraphs| |  | END |
       +-----+   |  +---------+ |  +-----+
          |       |       |      |
          +-------+       +------+
```

**Nodes**:
- `agent` -- Runs the unified agent with retry logic (`_run_agent_with_retry`)
- `tools` -- Executes non-task tool calls
- `subgraphs` -- Runs subagent delegations (task tool calls)

**Routing** (`_route_from_agent`):
- No tool calls -> `end`
- Only `task` tool calls -> `subgraphs`
- Only non-task tool calls -> `tools`
- Mixed task + non-task calls -> `tools` first (non-task calls execute, then back to agent)

**Compilation**: The graph is compiled once as a singleton via `get_compiled_graph()` with a checkpointer and optional store.

### GraphState

**Location**: `app/agents/orchestration/orchestration/state.py`

`GraphState` is a Pydantic `BaseModel` with annotated field-level reducers:

| Field | Type | Reducer | Description |
|-------|------|---------|-------------|
| `session_id` | `str` | Replace | Logical conversation/thread identifier |
| `trace_id` | `Optional[str]` | Replace | LangSmith trace correlation |
| `user_id` | `Optional[str]` | Replace | Authenticated user for memory scoping |
| `messages` | `List[BaseMessage]` | `bounded_add_messages(30)` | Conversation history with dedup |
| `attachments` | `List[Attachment]` | Replace | Client-provided attachments (max 10 MiB each) |
| `agent_mode` | `Optional[str]` | Replace | Frontend-selected hard mode (`general`, `mailbird_expert`, `research_expert`, `creative_expert`) |
| `scratchpad` | `Dict[str, Any]` | `merge_scratchpad` | Deep-merged internal state |
| `forwarded_props` | `Dict[str, Any]` | `merge_forwarded_props` | Shallow-merged client properties |

**`bounded_add_messages(30)`** preserves memory system messages and keeps the last 30 non-memory messages.

**ThreadState** (stored in scratchpad): Ephemeral structured state ("compressed truth") with fields for `one_line_status`, `user_intent`, `constraints`, `decisions`, `active_todos`, `progress_so_far`, `open_questions`, `artifacts`, `risks`, `assumptions`.

### Checkpointing

The graph uses `SanitizingMemorySaver` for checkpointing (from `app/agents/harness/persistence/memory_checkpointer.py`), with an optional Supabase-backed store for workspace files.

---

## 7. Context Engineering

Session continuity is maintained through a workspace-backed context system implementing Deep Agent patterns.

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `SparrowWorkspaceStore` | `app/agents/harness/store/workspace_store.py` | LangGraph BaseStore backed by Supabase `store` table |
| `SessionInitMiddleware` | `app/agents/harness/middleware/session_init_middleware.py` | Loads handoff context on first message |
| `HandoffCaptureMiddleware` | `app/agents/harness/middleware/handoff_capture_middleware.py` | Captures context at 60% of context window |
| `SparrowCompositeBackend` | `app/agents/harness/backends/composite.py` | Routes storage to ephemeral vs persistent backends |

### Workspace Routes

| Route | Persistence | Description |
|-------|-------------|-------------|
| `/scratch/` | Ephemeral (cleared per session) | Working notes, intermediate results |
| `/progress/session_notes.md` | Persistent | Progress notes across sessions (markdown) |
| `/goals/active.json` | Persistent | Current goals with pass/fail/pending status |
| `/handoff/summary.json` | Persistent | Session handoff context |

### Handoff Context Structure

When context approaches 60% of the model's context window, `HandoffCaptureMiddleware` automatically captures:

```json
{
  "summary": "User Request: ... Key Findings: ...",
  "active_todos": [{"content": "Task 1", "status": "in_progress"}],
  "next_steps": ["Step 1", "Step 2"],
  "key_decisions": ["Decision 1"],
  "message_count": 42,
  "estimated_tokens": 76800,
  "capture_number": 1,
  "timestamp": "ISO-8601"
}
```

### Session Initialization

On the first message of a new session, `SessionInitMiddleware` injects system messages:
1. **[Session Handoff Context]** -- Previous session summary, next steps, pending todos
2. **[Active Goals]** -- Current goals with pass/fail/pending status
3. **[Session Progress Notes]** -- Markdown progress notes (if < 2000 chars)

### Database Storage

Workspace files are stored in the Supabase `store` table:

| Column | Type | Description |
|--------|------|-------------|
| `prefix` | VARCHAR | Namespace path (e.g., `workspace:handoff:session-123`) |
| `key` | VARCHAR | File key (e.g., `summary.json`) |
| `value` | JSONB | File content |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update timestamp |

---

## Additional References

- Runtime and operational details: `docs/backend-runtime-reference.md`
