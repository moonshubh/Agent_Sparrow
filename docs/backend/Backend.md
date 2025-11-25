# Agent Sparrow Backend Architecture Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Core Components](#core-components)
4. [Directory Structure](#directory-structure)
5. [Agent System](#agent-system)
6. [API Layer](#api-layer)
7. [Database Integration](#database-integration)
8. [Frontend-Backend Communication](#frontend-backend-communication)
9. [Security & Authentication](#security--authentication)
10. [Rate Limiting](#rate-limiting)
11. [Development Setup](#development-setup)

## System Overview

Agent Sparrow is a unified DeepAgent-based AI system built on FastAPI with a Next.js frontend. The backend implements an orchestrated LangGraph graph with a single Unified Agent Sparrow that internally uses subagents and tools for different tasks (e.g. research and log analysis). The system integrates with Supabase for data persistence, uses Google Gemini as the model provider, and exposes a CopilotKit‑compatible streaming runtime at `/api/v1/copilot/stream`.

**Recent Changes (2025-11-04)**:
- ✅ **Phase 7 Migration Complete**: Removed legacy CopilotKit GraphQL shim and UI components
- ✅ **Dead Code Cleanup**: Removed 9 files (~1,350 lines total):
  - `app/api/middleware/security_middleware.py` (unused, never registered)
  - `app/config/error_patterns.yaml` (unused YAML config)
  - `app/integrations/copilotkit/` (GraphQL shim superseded by stream endpoint)
  - Legacy frontend UI components (CopilotChatClient, AppSidebarLeft, etc.)
- ✅ Removed legacy formatters (~118 KB, 7 files) - Gemini 2.5 Pro generates natural markdown
- ✅ Simplified response generation by 70% (120 lines → 20 lines)
- ✅ All endpoints now use `/api/v1/copilot/stream` (CopilotKit AG-UI adapter)

Re-organization note: canonical imports are `app.agents.*` and legacy `app.agents_v2.*` paths have been removed; all endpoints now import from `app.agents.*`.

## Architecture Diagram

```mermaid
graph TB
    subgraph "Frontend Layer"
        NextJS[Next.js App]
        Copilot[CopilotKit / AG-UI Client]
    end

    subgraph "API Layer"
        CORS[CORS Middleware]
        RL[Rate Limiter]
        Auth[Auth Middleware]
        FastAPI[FastAPI Server]
        CopilotEP[AG-UI Stream<br/>/api/v1/copilot/stream]
        LogsEP[Log Analysis APIs]
        ResearchEP[Research APIs]
    end

    subgraph "Unified Agent Layer"
        Graph[LangGraph Graph<br/>app/agents/orchestration/orchestration/graph.py]
        Unified[Unified Agent Sparrow<br/>app/agents/unified/agent_sparrow.py]
        Subagents[Subagents (research, log diagnoser)<br/>app/agents/unified/subagents.py]
    end

    subgraph "Tools & Services"
        Tools[Unified Tools<br/>app/agents/unified/tools.py]
        GK[Global Knowledge<br/>app/services/global_knowledge/*]
        FeedMeSvc[FeedMe Intelligence<br/>app/feedme/*]
    end

    subgraph "Data Layer"
        SC[Supabase Client<br/>app/db/supabase/client.py]
        Models[DB Models<br/>app/db/models.py]
        Embeddings[Embedding Utils<br/>app/db/embedding/*]
    end

    subgraph "Core Services"
        Settings[Settings<br/>app/core/settings.py]
        UserContext[User Context<br/>app/core/user_context.py]
        Security[Security Module<br/>app/core/security.py]
        RateLimiting[Rate Limiting<br/>app/core/rate_limiting/]
        Memory[Mem0 Memory Service<br/>app/memory/service.py]
        Cache[Redis Cache<br/>app/cache/redis_cache.py]
    end

    subgraph "External Services"
        Supabase[(Supabase DB)]
        Redis[(Redis)]
        Gemini[Google Gemini API]
        Tavily[Tavily API]
        Firecrawl[Firecrawl API]
    end

    %% Frontend to Backend connections
    NextJS --> Copilot
    Copilot --> |HTTP/SSE| FastAPI

    %% API Layer flow
    FastAPI --> CORS
    CORS --> RL
    RL --> Auth
    Auth --> CopilotEP
    Auth --> LogsEP
    Auth --> ResearchEP

    %% Unified agent flow
    CopilotEP --> Graph
    LogsEP --> Graph
    ResearchEP --> Graph
    Graph --> Unified
    Unified --> Subagents
    Unified --> Tools

    %% Tools & services interactions
    Tools --> GK
    Tools --> FeedMeSvc

    %% Data layer connections
    Tools --> SC
    GK --> SC
    FeedMeSvc --> SC
    SC --> Supabase
    Tools --> Embeddings
    Embeddings --> Models

    %% Core services
    FastAPI --> Settings
    FastAPI --> UserContext
    FastAPI --> Security
    FastAPI --> RateLimiting
    FastAPI --> Memory
    RateLimiting --> Cache
    Cache --> Redis

    %% External providers
    Unified --> Gemini
    Tools --> Tavily
    Tools --> Firecrawl

    style Unified fill:#e1f5fe
    style Graph fill:#fff3e0
    style FastAPI fill:#f3e5f5
    style Supabase fill:#c8e6c9
    style Redis fill:#ffccbc
    style Gemini fill:#ffeb3b
```

## Core Components

### 1. FastAPI Application (`app/main.py`)
- **Purpose**: Main application entry point and API server
- **Key Features**:
  - CORS middleware for cross-origin requests
  - Rate limiting via SlowAPI
  - OpenTelemetry integration for tracing
  - Dynamic router registration based on configuration
  - Global exception handlers for rate limiting

### 2. Agent Graph (`app/agents/orchestration/orchestration/graph.py`)
- **Purpose**: Orchestrates the flow of the unified agent and its subagents
- **Components**:
  - StateGraph for managing agent state
  - Unified agent node wrapping DeepAgents runtime
  - Subagent nodes (research, log diagnoser)
  - Tool node for external tool execution
  - Pre/post processing nodes

### 3. Unified Agent (`app/agents/unified/agent_sparrow.py`)
- **Purpose**: Main conversational agent handling all chat flows (primary, research, log analysis) via DeepAgents
- **Features**:
  - Model routing and runtime config resolution
  - Mem0-based memory integration
  - PII redaction and observability hooks
  - Streaming via LangGraph + AG‑UI
  - Subagent orchestration (research, log diagnoser)

### 4. Log Analysis (Unified Tool)
- **Location**:
  - `app/agents/log_analysis/log_analysis_agent/simplified_agent.py`
  - `app/agents/log_analysis/log_analysis_agent/simplified_schemas.py`
- **Purpose**: Simplified log analysis agent surfaced as the `log_diagnoser` tool
- **Usage**:
  - Exposed through `app/agents/unified/tools.py` as `log_diagnoser_tool`
  - Consumed by `app/api/v1/endpoints/logs_endpoints.py` (JSON + SSE)

### 5. Research (Unified Subagent)
- **Location**:
  - Subagent spec in `app/agents/unified/subagents.py`
  - Runtime via `run_unified_agent` in `app/agents/unified/agent_sparrow.py`
- **Purpose**: Handles research/information‑gathering queries using web search, global knowledge, and FeedMe
- **Usage**:
  - Exposed through `app/api/v1/endpoints/research_endpoints.py` (JSON + SSE)

### 6. DeepAgents Harness & Middleware Stack

The unified agent uses a DeepAgents-inspired harness architecture with composable middleware:

#### Middleware Components (`app/agents/harness/middleware/`)
- **MemoryMiddleware** (`memory_middleware.py`): Mem0-based memory injection with sentinel pattern for failed imports, standardized dict access for memory objects
- **RateLimitMiddleware** (`rate_limit_middleware.py`): Per-model rate limiting with fallback chain support, model injection for retries
- **EvictionMiddleware** (`eviction_middleware.py`): Large result eviction to ephemeral storage with async-safe stats tracking

#### Storage Backends (`app/agents/harness/backends/`)
- **CompositeBackend** (`composite.py`): Routes paths to appropriate storage:
  - `/memories/*` → Persistent (Supabase)
  - `/knowledge/*` → Persistent (Supabase)
  - `/scratch/*` → Ephemeral (in-memory)
  - `/large_results/*` → Ephemeral (auto-cleanup)
- **SupabaseStoreBackend** (`supabase_store.py`): Persistent storage with UTF-8 byte size validation, optimized queries

#### Streaming Infrastructure (`app/agents/streaming/`)
- **StreamEventEmitter** (`emitter.py`): Centralized AG-UI event emission with timeline/trace/todos state tracking
- **Normalizers** (`normalizers.py`): Transform raw tool outputs into typed event structures
- **StreamHandler** (`handler.py`): Orchestrates streaming with fallback path event emission

#### Session Management (`app/agents/unified/`)
- **SessionCache** (`session_cache.py`): Thread-safe LRU cache with double-checked locking singleton
- **ToolContracts** (`tool_contracts.py`): Consistent error handling across sync/async tool wrappers
- **MessagePreparer** (`message_preparation.py`): Pre-agent transformations (memory injection, query rewriting, history summarization)

## Directory Structure

```
app/
├── agents/                      # Canonical agents package
│   ├── unified/                 # Unified DeepAgent implementation
│   │   ├── agent_sparrow.py
│   │   ├── subagents.py
│   │   ├── tools.py
│   │   ├── tool_contracts.py   # Sync/async tool wrappers with error handling
│   │   ├── session_cache.py    # Thread-safe LRU cache singleton
│   │   ├── message_preparation.py  # Pre-agent message transformations
│   │   ├── model_router.py
│   │   ├── prompts.py
│   │   └── grounding.py
│   ├── harness/                 # DeepAgents-inspired harness
│   │   ├── backends/            # Storage backends
│   │   │   ├── composite.py     # Path-based routing
│   │   │   └── supabase_store.py  # Persistent storage
│   │   └── middleware/          # Composable middleware
│   │       ├── memory_middleware.py
│   │       ├── rate_limit_middleware.py
│   │       └── eviction_middleware.py
│   ├── streaming/               # AG-UI streaming infrastructure
│   │   ├── emitter.py           # Centralized event emission
│   │   ├── normalizers.py       # Output normalization
│   │   ├── handler.py           # Stream orchestration
│   │   └── event_types.py       # Typed event definitions
│   ├── orchestration/
│   │   └── orchestration/       # Graph + state for unified agent
│   │       ├── graph.py
│   │       └── state.py
│   ├── checkpointer/
│   │   ├── postgres_checkpointer.py
│   │   └── thread_manager.py
│   └── metadata.py
├── api/
│   └── v1/
│       ├── endpoints/           # copilot (AG‑UI), logs, research, feedme, api-keys, rate-limits, etc.
│       │   ├── copilot_endpoints.py
│       │   ├── logs_endpoints.py
│       │   ├── research_endpoints.py
│       │   ├── feedme_endpoints.py
│       │   ├── feedme_intelligence.py
│       │   ├── chat_session_endpoints.py
│       │   ├── text_approval_endpoints.py
│       │   ├── api_key_endpoints.py
│       │   ├── rate_limit_endpoints.py
│       │   ├── agents_endpoints.py
│       │   ├── agent_interrupt_endpoints.py
│       │   └── tavily_selftest.py
│       └── websocket/           # FeedMe WebSocket
│           └── feedme_websocket.py
├── core/
│   ├── transport/sse.py         # Unified SSE formatting
│   ├── rate_limiting/           # Gemini limiters, circuit breaker, config
│   ├── settings.py
│   ├── user_context.py
│   └── security.py
├── db/
│   ├── supabase/client.py       # Canonical Supabase client
│   ├── supabase/repository.py
│   ├── embedding/utils.py
│   ├── models.py
│   └── migrations/
├── memory/
│   └── service.py               # Mem0-based memory service
├── security/
│   └── pii_redactor.py          # PII redaction hooks
├── services/
│   └── global_knowledge/        # Global knowledge retrieval + observability
├── providers/
│   └── limits/                  # Thin wrappers around core rate limiting (optional)
├── tools/
│   └── research_tools.py        # Tavily/Firecrawl clients used by unified tools
├── cache/redis_cache.py
└── feedme/
    └── ...                      # FeedMe ingestion, analytics, WebSocket, etc.
```

## Agent System

### Agent State Management
The system uses a Pydantic GraphState to maintain state across the orchestration graph (`app/agents/orchestration/orchestration/state.py`):
```python
class GraphState(BaseModel):
    session_id: str = "default"
    messages: List[BaseMessage] = Field(default_factory=list)
    destination: Optional[Literal["primary_agent", "log_analyst", "researcher", "__end__"]] = None
    raw_log_content: Optional[str] = None
    final_report: Optional[StructuredLogAnalysisOutput] = None
    cached_response: Optional[Any] = None
    tool_invocation_output: Optional[Any] = None
    reflection_feedback: Optional[ReflectionFeedback] = None
    qa_retry_count: int = 0
```

### Agent Flow
1. **Pre-processing**: Cache check, user context setup
2. **Routing**: Query classification to appropriate agent
3. **Agent Execution**: Specialized agent processes query
4. **Tool Execution**: External tools if needed
5. **Reflection**: Quality check and refinement
6. **Post-processing**: Response formatting and caching

### Reasoning Engine
The reasoning engine (`reasoning_engine.py`) implements:
- Multi-step reasoning chains
- Context-aware decision making
- Tool selection intelligence
- Problem decomposition
- Solution synthesis

## API Layer

For detailed developer guides, see:
- `docs/Unified-Agent-Implementation-Guide.md`
- `docs/AG-UI-DeepAgent-Implementation-Plan.md`
- `docs/Unified-Agent-Migration-Report.md`

### Key Endpoints

#### AG‑UI / Chat Endpoints
- `copilot_endpoints.py`:
  - `POST /api/v1/copilot/stream` – Unified AG‑UI streaming endpoint (SSE)
  - `GET /api/v1/copilot/stream/health` – Health and diagnostics

#### Agent Endpoints (JSON/SSE)
- `logs_endpoints.py`:
  - `POST /api/v1/agent/logs` – Log analysis (JSON) via unified `log_diagnoser` tool
  - `POST /api/v1/agent/logs/stream` – Log analysis (SSE) with timeline steps
- `research_endpoints.py`:
  - `POST /api/v1/agent/research` – Research queries (JSON) via unified research subagent
  - `POST /api/v1/agent/research/stream` – Research (SSE)

Streaming contracts:
- AG‑UI chat stream emits AG‑UI events (e.g. `text-delta`, `tool-call`, `tool-result`, `finish`) as defined by the AG‑UI LangGraph adapter.
- Log analysis stream emits timeline steps as `{ type: 'step', data: {...} }`, a final assistant message with `analysis_results`, and a terminal `[DONE]` marker.

#### API Key Management (`api_key_endpoints.py`)
- `GET /api/v1/api-keys` – List masked keys; `POST /api/v1/api-keys` – Create/update; `PUT/DELETE /api/v1/api-keys/{type}`
- `POST /api/v1/api-keys/validate` – Validate format; `POST /api/v1/api-keys/test` – Connectivity
- `GET /api/v1/api-keys/status` – Status summary; `GET /api/v1/api-keys/internal/{type}` – Internal-only decrypted fetch

#### Rate Limit Monitoring (`rate_limit_endpoints.py`)
- `GET /api/v1/rate-limits/status|usage|health|config|metrics`, `POST /api/v1/rate-limits/check/{model}`, `POST /api/v1/rate-limits/reset`

#### FeedMe Endpoints (`feedme_endpoints.py`)
- `POST /api/v1/feedme/ingest` – Transcript ingestion
- `GET /api/v1/feedme/conversations` – List conversations
- `POST /api/v1/feedme/folders` – Folder management
- WebSocket support: `/ws/feedme` for real-time updates

#### Authentication Endpoints (`auth.py`)
- `POST /api/v1/auth/login` – User login (when enabled)
- `POST /api/v1/auth/refresh` – Token refresh
- `POST /api/v1/auth/logout` – User logout
- JWT-based authentication (Supabase)

### Global Knowledge Observability Endpoints
- `GET /api/v1/global-knowledge/queue` – Review queue (feedback/corrections)
- `GET /api/v1/global-knowledge/summary` – Aggregated metrics (windowed)
- `GET /api/v1/global-knowledge/events` – Recent timeline events
- `GET /api/v1/global-knowledge/stream` – SSE timeline stream (`{ type: 'timeline-step', data }`)
- `POST /api/v1/global-knowledge/promote/feedback/{id}` – Promote feedback to KB
- `POST /api/v1/global-knowledge/promote/correction/{id}` – Promote correction to KB

## Database Integration

Canonical imports:
- Supabase: `from app.db.supabase.client import get_supabase_client`
- Embeddings utils: `from app.db.embedding.utils import ...`

### Supabase Client (`app/db/supabase/client.py`)
Provides typed operations for:
- **Folder Management**: Create, update, delete folders
- **Conversation Persistence**: Store chat sessions
- **User Data**: User preferences and settings
- **API Key Storage**: Encrypted key management

### Database Models (`models.py`)
```python
class UserAPIKey:
    - id: Primary key
    - user_id: User identifier
    - api_key_type: Provider type (gemini, openai, etc.)
    - encrypted_key: Encrypted API key
    - is_active: Status flag
    - created_at/updated_at: Timestamps

class APIKeyAuditLog:
    - Audit trail for API key operations
    - No sensitive data storage
```

### Global Knowledge Migrations
- `032_create_sparrow_feedback.sql` – feedback table with `vector(3072)`, RLS, indexes
- `033_create_sparrow_corrections.sql` – corrections table with `vector(3072)`, RLS, indexes
RLS policies compare `user_id` to `auth.uid()::text`. Apply these before enabling store writes.

## Frontend-Backend Communication

[DEPRECATED] Unified client removed after CopilotKit migration.

#### SSE Helpers
Streaming endpoints use `app/core/transport/sse.py` → `format_sse_data(payload)` for consistent Server‑Sent Event formatting across agents.

### Communication Flow
1. Frontend sends request via CopilotKit runtime to `/api/v1/copilot/stream`
2. Request includes Supabase JWT, session ID, memory toggle, attachments, provider/model/agent_type, trace_id
3. Backend CopilotKit adapter invokes our LangGraph graph
4. Streaming events sent back via CopilotKit protocol
5. Frontend renders incremental updates in Copilot chat UI

### Authentication Flow
1. User logs in via Supabase Auth
2. JWT token stored in cookies
3. Middleware validates token on each request
4. User context injected into agent state

## Security & Authentication

### Authentication System
- **Supabase Auth Integration**: Primary auth provider
- **JWT Tokens**: Session management
- **Local Auth Bypass**: Development mode option
- **Middleware Protection**: Route-level auth checks

### Security Features
- **API Key Encryption**: All keys encrypted at rest
- **Rate Limiting**: Multi-level rate limiting
- **CORS Configuration**: Controlled origin access
- **Input Validation**: Pydantic models for validation
- **Audit Logging**: API key operation tracking
- **Secure Log Analysis Enforcement**: Production log analysis uses Google Gemini 2.5 Pro (`gemini-2.5-pro`).

## Global Knowledge (Phases 1–6)

Global Knowledge implements store-backed retrieval for slash commands (`/feedback`, `/correct`) with phased rollout and flags.

### Components
- Services: `app/services/global_knowledge/{models,enhancer,persistence,retrieval,store,observability}.py`
- Endpoints: `app/api/v1/endpoints/global_knowledge_observability.py`
- Supabase client helpers: insert/list/get/update feedback/corrections

### Feature Flags (Settings)
- `ENABLE_GLOBAL_KNOWLEDGE_INJECTION` – inject retrieved facts into agent memory
- `ENABLE_STORE_ADAPTER` – use RPC-backed Store adapter for retrieval
- `ENABLE_STORE_WRITES` – enable dual writes to LangGraph Store
- `RETRIEVAL_PRIMARY=rpc|store` – prefer Store (with adapter fallback) or RPC
- `GLOBAL_STORE_DB_URI` – direct Postgres URI for LangGraph Store (requires direct DB; pooled hosts won’t work)

### Phase Highlights
- Phase 1 (Hybrid Adapter): Store-like search backed by Supabase RPC for parity and fallback
- Phase 2 (Dual Writes): Persist normalized payloads + embeddings; upsert to Store when enabled
- Phase 3 (Store-First Retrieval): Query embeddings → `store.search()` with adapter fallback; configurable top‑k/truncation
- Phase 4 (Enhancer Subgraph): LangGraph `StateGraph` normalizes submissions; durable with `MemorySaver`
- Phase 5 (Observability & Actions): In‑memory telemetry (timeline/summary) + REST/SSE; review queue and promote actions
- Phase 6 (Security Hardening): Attachment allowlist, length caps, metadata sanitization; sanitized telemetry/logging

### Observability
- Telemetry stages: `received`, `classified`, `normalized_*`, `embedding_*`, `supabase_persisted`, `store_upserted`, `completed`
- SSE emits `{ type: 'timeline-step', data: TimelineEvent }`; aggregate via `/summary`

### Deployment Notes
- Supabase free tier exposes only pooled hosts; LangGraph Store requires direct Postgres. Use paid Supabase or external Postgres (e.g., Railway) for `GLOBAL_STORE_DB_URI`. Otherwise run adapter‑only (`ENABLE_STORE_WRITES=false`).

## Rate Limiting

### Multi-Level System
1. **Global Rate Limiter** (SlowAPI):
   - Request-level limiting
   - IP-based throttling

2. **Service-Specific Limiters**:
   - **Gemini Rate Limiter**: Token bucket + circuit breaker; per-family (Flash/Pro) limits
   - **Embedding Limiter**: Embedding API limits
   - **Circuit Breaker**: Failure protection

3. **Configuration** (`app/core/rate_limiting/config.py`):
   ```python
   RATE_LIMITS = {
       "gemini-2.5-flash": {
           "rpm": 1000,
           "tpm": 4000000,
           "rpd": 10000
       }
   }
   ```

## Development Setup

### Environment Variables
```bash
# Core Configuration
ENVIRONMENT=development
SKIP_AUTH=true  # Development only
DEVELOPMENT_USER_ID=dev-user-12345

# API Keys
GEMINI_API_KEY=your-gemini-key
TAVILY_API_KEY=your-tavily-key

# Supabase
SUPABASE_URL=your-supabase-url
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key

# Redis (optional)
REDIS_URL=redis://localhost:6379

# Security
JWT_SECRET_KEY=your-jwt-secret
ENABLE_LOCAL_AUTH_BYPASS=false
```

### Running the Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --port 8000

# Or use the start script
python app/main.py
```

### Key Development Features
- **Hot Reload**: Automatic restart on code changes
- **Mock Mode**: Run without external dependencies
- **Debug Logging**: Comprehensive logging system
- **OpenTelemetry**: Performance tracing (optional)

## Provider System

### Model Provider

The current system is **Gemini-only**. Models are instantiated directly via
`langchain_google_genai.ChatGoogleGenerativeAI` using names configured in
`app/core/settings.py` (e.g. `gemini-2.5-flash`, `gemini-2.5-pro`).

- `PRIMARY_AGENT_PROVIDER` / `primary_agent_provider` are expected to be `google`.
- OpenAI adapters and the old provider registry (`app/providers/registry.py`) have
  been removed from the runtime path; adding new providers now requires wiring
  them into the unified agent implementation instead of the legacy registry.

## Troubleshooting Module (Legacy)

The legacy troubleshooting module under
`app/agents/primary/primary_agent/troubleshooting/` has been removed as part of
the unified agent migration. Historical details are preserved in
`docs/reference/legacy_architecture.md`.

## Cache System

### Redis Cache (`app/cache/redis_cache.py`)
- Response caching for repeated queries
- Session state caching
- Rate limit state storage
- Configurable TTL

## WebSocket Support

### FeedMe WebSocket (`app/api/v1/websocket/feedme_websocket.py`)
- Real-time transcript processing
- Live conversation updates
- Bidirectional communication
- Connection management

## Quality Management

### Quality Manager (`app/core/quality_manager.py`)
- Response quality metrics
- Performance monitoring
- Error tracking
- User satisfaction signals

## Best Practices for New Developers

### 1. Agent Development
- Extend base agent classes
- Implement proper error handling
- Use structured logging
- Follow state management patterns

### 2. API Development
- Use Pydantic for validation
- Implement proper status codes
- Add comprehensive documentation
- Include rate limiting decorators

### 3. Testing
- Unit tests for agent logic
- Integration tests for API endpoints
- Mock external services
- Load testing for performance

### 4. Security
- Never log sensitive data
- Encrypt all stored credentials
- Validate all inputs
- Use parameterized queries

### 5. Performance
- Use caching strategically
- Implement pagination
- Optimize database queries
- Monitor rate limits

## Common Patterns

### Stream Processing
```python
async def stream_response():
    async for chunk in agent.astream(state):
        yield format_chunk(chunk)
```

### Error Handling
```python
try:
    result = await agent.process(query)
except RateLimitExceeded:
    return rate_limit_response()
except Exception as e:
    logger.error(f"Agent error: {e}")
    return error_response()
```

### State Management
```python
state = GraphState(
    messages=[HumanMessage(content=query)],
    user_info=user_context,
    api_key=user_api_key
)
```

## Monitoring & Debugging

### Logging
- Structured logging with context
- Log levels: DEBUG, INFO, WARNING, ERROR
- Centralized logging configuration

### OpenTelemetry
- Distributed tracing
- Performance metrics
- Error tracking
- Custom spans for agent operations

### Health Checks
- `/health`: System health
- `/api/v1/rate-limits/status`: Rate limit status
- Database connectivity checks

## Deployment Considerations

### Production Setup
1. Set `ENVIRONMENT=production`
2. Configure proper JWT secret
3. Enable authentication endpoints
4. Set up Redis for caching
5. Configure rate limits appropriately
6. Set up monitoring/alerting

### Scaling
- Horizontal scaling via load balancer
- Redis for shared state
- Database connection pooling
- Async processing for heavy operations

### Security Hardening
- Enable all security features
- Regular security audits
- API key rotation policy
- Audit log retention

## CopilotKit Runtime Integration

### Overview
The backend provides a CopilotKit-compatible streaming runtime at `/api/v1/copilot/stream` using the AG-UI LangGraph adapter. The legacy GraphQL endpoint has been **deprecated** as of Phase 7 (2025-11-04).

### Current Endpoint
- **POST** `/api/v1/copilot/stream` – Auth-protected AG-UI streaming endpoint (SSE)
  - **Status**: ✅ Production (Phases 1-7 complete)
  - **Implementation**: `app/api/v1/endpoints/copilot_endpoints.py`
  - **Features**: Context merge, attachment validation, OpenTelemetry tracing

- **GET** `/api/v1/copilot/stream/health` – Health check endpoint
  - Returns: `{ "status": "ok"|"503", "sdk_available": bool, "graph_compiled": bool, "agents": [...], "models": {...} }`

### Deprecated Endpoint (Removed in Phase 7)
- **POST** `/api/v1/copilotkit` – ❌ **DEPRECATED** (Returns 410 Gone)
  - **Removed**: GraphQL shim (`app/integrations/copilotkit/`)
  - **Migration Path**: Use `/api/v1/copilot/stream` instead
  - **Frontend**: All clients migrated to stream endpoint

Companion utility:
- **GET** `/api/v1/models?agent_type=primary|log_analysis` – Returns provider model lists used by the frontend `ModelSelector`.

### Dependencies
- AG-UI adapter: `pip install "ag-ui-langgraph[fastapi]"`
- Requires FastAPI >=0.115.x
- Optional: OpenTelemetry (`ENABLE_OTEL=true`)

### Implementation
- Stream endpoint: `app/api/v1/endpoints/copilot_endpoints.py`
  - Context merge for session_id, trace_id, provider, model, agent_type, attachments
  - Attachment validation (size, MIME type, data URL format)
  - OpenTelemetry spans with non-PII attributes
  - Comprehensive logging for debugging
- Auth: Supabase JWT via `get_current_user_id` dependency
- Streaming: Server-Sent Events (SSE) with `EventEncoder`

### Expected Request Schema (SSE adapter)
The SSE adapter expects a Pydantic `RunAgentInput` with:
- `messages`: List of messages with discriminator `role` and `id`/`content`
- `threadId`, `runId`: Session and run identifiers
- `state`, `tools`, `context`: Runtime objects (often empty)
- `forwardedProps`: Our custom per-request properties:
  - `session_id`: Session identifier for persistence
  - `use_server_memory`: Boolean for memory toggle
  - `provider`/`model`: Provider and model selection
  - `agent_type`: 'primary' | 'log_analysis'
  - `trace_id`: Optional tracing identifier
  - `attachments`: Array of `{ filename, media_type, data_url }`

### Example Payload (SSE adapter)
```json
{
  "messages": [
    {
      "role": "user",
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "content": "Hello, Sparrow!"
    }
  ],
  "threadId": "session-123",
  "runId": "run-abc",
  "state": {},
  "tools": [],
  "context": [],
  "forwardedProps": {
    "session_id": "session-123",
    "use_server_memory": true,
    "provider": "google",
    "model": "gemini-2.5-flash-preview-09-2025",
    "agent_type": "primary",
    "trace_id": "trace-xyz",
    "attachments": []
  }
}
```

### Runtime Behavior
- Stream endpoint validates requests via `RunAgentInput` (Pydantic)
- Instantiates `LangGraphAgent(name="sparrow", graph=compiled_graph)`
- Streams events from `agent.run(input_data)` via `EventEncoder`
- Supports LangGraph interrupts (HITL) with `useLangGraphInterrupt`
- Includes user context from Supabase JWT in agent state

### Phase 1 Enhancements (Context Merge & Validation)
The stream endpoint includes comprehensive context merge logic:
- **Properties**: session_id, trace_id, provider, model, agent_type, use_server_memory
- **Attachments**: Validated for size (10MB limit), MIME type allowlist, data URL format
- **Configuration**: Merged into both `state` dict and `config.configurable`
- **Error Handling**: Fails loudly with actionable HTTPException messages
- **Logging**: Comprehensive logs at request, merge, and execution points

See Phase 1 completion doc for full context merge implementation details.

### Integration Notes
- ✅ **Phase 0**: Feature flags and baseline metrics
- ✅ **Phase 1**: Backend context merge and attachment validation
- ✅ **Phase 2**: Frontend transport switch (feature-flagged)
- ✅ **Phase 3**: CopilotKit UI components (CopilotSidebar)
- ✅ **Phase 4**: Document integration (KB + FeedMe) and suggestions
- ✅ **Phase 5**: Multi-agent selection and exposure
- ✅ **Phase 6**: OpenTelemetry observability and health diagnostics
- ✅ **Phase 7**: Legacy GraphQL cleanup (410 Gone)

### Frontend Integration
- Uses `CopilotKit` provider with `runtimeUrl="/api/v1/copilot/stream"`
- Properties forwarded: session_id, use_server_memory, provider, model, agent_type, trace_id, attachments
- UI components: CopilotSidebar, CustomAssistantMessage, ChatActions, ChatInterrupts
- Feature flags: Documents, Suggestions, Multi-Agent Selection, Observability

## Conclusion

This backend architecture provides a robust, scalable foundation for the Agent Sparrow system. The multi-agent orchestration, combined with comprehensive security, caching, and rate limiting, ensures reliable and performant AI interactions. New developers should focus on understanding the agent graph flow and state management patterns before making modifications.