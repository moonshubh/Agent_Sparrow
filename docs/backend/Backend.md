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

Agent Sparrow is a sophisticated multi-agent AI system built on FastAPI with a Next.js frontend. The backend implements an orchestrated agent graph using LangGraph, with specialized agents for different tasks (primary agent, log analysis, research, reflection). The system integrates with Supabase for data persistence, supports multiple AI providers, and now includes a CopilotKit-compatible streaming runtime at `/api/v1/copilot/stream`.

**Recent Changes (2025-11-04)**:
- ✅ Removed legacy formatters (~118 KB, 7 files) - Gemini 2.5 Pro now generates natural markdown directly
- ✅ CopilotKit handles all UI rendering - no structured envelope needed
- ✅ Cleaned up dead code: unused test files, empty directories
- ✅ Simplified response generation by 70% (120 lines → 20 lines)

Re-organization note: canonical imports are `app.agents.*` and legacy `app.agents_v2.*` paths have been removed; all endpoints now import from `app.agents.*`.

## Architecture Diagram

```mermaid
graph TB
    subgraph "Frontend Layer"
        NextJS[Next.js App]
        MW[Middleware]
        UC[Unified Client]
    end

    subgraph "API Gateway"
        CORS[CORS Middleware]
        RL[Rate Limiter]
        Auth[Auth Middleware]
        FastAPI[FastAPI Server]
    end

    subgraph "Agent Orchestration Layer"
        AG[Agent Graph<br/>app/agents/orchestration/orchestration/graph.py]
        Router[Query Router<br/>app/agents/router/router/router.py]
        PreProc[Pre-Process Node]
        PostProc[Post-Process Node]
        Escalate[Escalation Node]
    end

    subgraph "Agent Nodes"
        PA[Primary Agent<br/>app/agents/primary/primary_agent/agent.py]
        LA[Log Analysis Agent<br/>app/agents/log_analysis/log_analysis_agent/agent.py]
        RA[Research Agent<br/>app/agents/research/research_agent/research_agent.py]
        RF[Reflection Agent<br/>app/agents/reflection/reflection/node.py]
    end

    subgraph "Agent Components"
        RE[Reasoning Engine<br/>reasoning_engine.py]
        TS[Troubleshooting Module<br/>troubleshooting/]
        PS[Problem Solver<br/>problem_solver.py]
        TI[Tool Intelligence<br/>tool_intelligence.py]
        AB[Adapter Bridge<br/>adapter_bridge.py]
    end

    subgraph "Tools Layer"
        ToolNode[Tool Node]
        MKB[Mailbird KB Search]
        TWS[Tavily Web Search]
        RT[Research Tools<br/>app/tools/research_tools.py]
        LAT[Log Analysis Tools<br/>app/tools/log_analysis_tools.py]
        URT[User Research Tools<br/>app/tools/user_research_tools.py]
    end

    subgraph "Provider Layer"
        PR[Provider Registry<br/>app/providers/registry.py]
        GeminiAdapter[Gemini Adapter<br/>Google/Gemini-2.5-Flash/adapter.py]
        OpenAIAdapter[OpenAI Adapter<br/>OpenAI/GPT-5-Mini/adapter.py]
    end

    subgraph "Data Layer"
        SC[Supabase Client<br/>app/db/supabase/client.py]
        Models[DB Models<br/>app/db/models.py]
        Embeddings[Embedding Utils<br/>app/db/embedding_utils.py]
        Session[Session Manager<br/>app/db/session.py]
    end

    subgraph "Core Services"
        Settings[Settings<br/>app/core/settings.py]
        UserContext[User Context<br/>app/core/user_context.py]
        Security[Security Module<br/>app/core/security.py]
        RateLimiting[Rate Limiting<br/>app/core/rate_limiting/]
        QualityMgr[Quality Manager<br/>app/core/quality_manager.py]
        Cache[Redis Cache<br/>app/cache/redis_cache.py]
    end

    subgraph "External Services"
        Supabase[(Supabase DB)]
        Redis[(Redis)]
        Gemini[Google Gemini API]
        OpenAI[OpenAI API]
        Tavily[Tavily API]
    end

    %% Frontend to Backend connections
    NextJS --> MW
    MW --> UC
    UC --> |HTTP/WebSocket| FastAPI

    %% API Gateway flow
    FastAPI --> CORS
    CORS --> RL
    RL --> Auth
    Auth --> AG

    %% Agent Graph flow
    AG --> PreProc
    PreProc --> |Check Cache| Router
    Router --> |Route Decision| PA
    Router --> |Log Query| LA
    Router --> |Research Query| RA

    %% Agent interactions
    PA --> RE
    PA --> AB
    RE --> PS
    RE --> TI
    PA --> RF
    RF --> |Refine| PA
    RF --> |Complete| PostProc
    RF --> |Escalate| Escalate

    %% Tool interactions
    PA --> ToolNode
    LA --> ToolNode
    RA --> ToolNode
    ToolNode --> MKB
    ToolNode --> TWS
    ToolNode --> RT
    ToolNode --> LAT
    ToolNode --> URT

    %% Provider connections
    AB --> PR
    PR --> GeminiAdapter
    PR --> OpenAIAdapter
    GeminiAdapter --> Gemini
    OpenAIAdapter --> OpenAI
    TWS --> Tavily

    %% Data layer connections
    FastAPI --> SC
    SC --> Supabase
    FastAPI --> Models
    FastAPI --> Session
    FastAPI --> Embeddings

    %% Core services
    FastAPI --> Settings
    FastAPI --> UserContext
    FastAPI --> Security
    FastAPI --> RateLimiting
    FastAPI --> QualityMgr
    RateLimiting --> Cache
    Cache --> Redis

    style PA fill:#e1f5fe
    style LA fill:#e1f5fe
    style RA fill:#e1f5fe
    style RF fill:#e1f5fe
    style AG fill:#fff3e0
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
- **Purpose**: Orchestrates the flow between different agents
- **Components**:
  - StateGraph for managing agent state
  - Router node for query classification
  - Agent nodes (primary, log analysis, research)
  - Tool node for external tool execution
  - Reflection node for quality assurance
  - Pre/post processing nodes

### 3. Primary Agent (`app/agents/primary/primary_agent/agent.py`)
- **Purpose**: Main conversational agent handling general queries
- **Features**:
  - Reasoning engine integration
  - Tool intelligence for smart tool usage
  - Troubleshooting capabilities
  - Support for thinking budget (Gemini 2.5)
  - Streaming responses
- **Key Files**:
  - `reasoning_engine.py`: Core reasoning logic
  - `problem_solver.py`: Problem-solving strategies
  - `tool_intelligence.py`: Tool selection intelligence
  - `adapter_bridge.py`: Provider abstraction

### 4. Log Analysis Agent (`app/agents/log_analysis/log_analysis_agent/`)
- **Purpose**: Specialized agent for analyzing logs and debugging
- **Response Generation**: Gemini 2.5 Pro generates natural, conversational markdown directly (no formatters)
- **Components**:
  - `comprehensive_agent.py`: Quality-first pipeline (defaults to Google Gemini 2.5 Pro)
  - `agent.py`: Main agent logic
  - `simplified_agent.py`: Simplified version for basic analysis
  - `extractors/`: Log pattern extractors (metadata, patterns)
  - `reasoning/`: Reasoning engine and root cause classifier
  - `tools/`: Log-specific tools (KB search, web search, FeedMe)
  - `privacy/`: Sanitization and cleanup managers
  - `security/`: Security validation and compliance
  - `context/`: Context ingestion and settings loaders

### 5. Research Agent (`app/agents/research/research_agent/research_agent.py`)
- **Purpose**: Handles research queries and information gathering
- **Features**:
  - Web search integration
  - Knowledge base search
  - Multi-source aggregation

### 6. Reflection Agent (`app/agents/reflection/reflection/node.py`)
- **Purpose**: Quality assurance and response refinement
- **Features**:
  - Response quality checking
  - Iterative refinement
  - Escalation for complex issues

## Directory Structure

```
app/
├── agents/                      # Canonical agents package
│   ├── orchestration/
│   │   └── orchestration/       # Graph, nodes, state, escalation
│   │       ├── graph.py
│   │       ├── nodes.py
│   │       ├── state.py
│   │       └── escalation.py
│   ├── router/
│   │   └── router/              # Query routing logic
│   │       ├── router.py
│   │       └── schemas.py
│   ├── primary/
│   │   └── primary_agent/       # Primary conversational agent
│   │       ├── agent.py
│   │       ├── reasoning/
│   │       ├── troubleshooting/
│   │       ├── prompts/
│   │       └── tools.py
│   ├── log_analysis/
│   │   └── log_analysis_agent/  # Log analysis specialist
│   │       ├── comprehensive_agent.py  # Main quality-first pipeline
│   │       ├── agent.py
│   │       ├── simplified_agent.py
│   │       ├── extractors/      # Pattern analysis & metadata
│   │       ├── reasoning/       # Reasoning engine & root cause
│   │       ├── tools/          # KB search, web search, orchestrator
│   │       ├── privacy/        # Sanitization & cleanup
│   │       ├── security/       # Validation & compliance
│   │       ├── context/        # Context ingestion
│   │       ├── schemas/        # Data models
│   │       └── templates/      # Response templates
│   ├── research/
│   │   └── research_agent/
│   │       └── research_agent.py
│   ├── reflection/
│   │   └── reflection/
│   │       ├── node.py
│   │       └── schema.py
│   └── checkpointer/
│       ├── postgres_checkpointer.py
│       └── thread_manager.py
├── api/
│   └── v1/
│       ├── endpoints/           # chat, unified, logs, secure logs, research, feedme, api-keys, rate-limits, etc.
│       └── websocket/           # FeedMe
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
├── providers/
│   ├── registry.py
│   ├── adapters/__init__.py     # Bootstraps known adapters
│   ├── Google/
│   │   ├── Gemini-2.5-Flash/adapter.py
│   │   ├── Gemini-2.5-Pro/adapter.py
│   │   └── LogAnalysis/Gemini-2.5-Pro/adapter.py
│   └── OpenAI/GPT-5-Mini/adapter.py
├── tools/
├── cache/redis_cache.py
└── feedme/
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
- docs/backend/primary-agent.md
- docs/backend/log-analysis-agent.md

### Key Endpoints

#### Agent Endpoints (modularized)
- chat_endpoints.py: `POST /api/v1/v2/agent/chat/stream` – Primary Agent streaming (SSE)
- unified_endpoints.py: `POST /api/v1/agent/unified/stream` – Unified stream routing to primary/log-analysis/research
- logs_endpoints.py: `POST /api/v1/agent/logs` (JSON), `POST /api/v1/agent/logs/stream` (SSE), sessions and rate-limits
- research_endpoints.py: `POST /api/v1/agent/research` (JSON), `POST /api/v1/agent/research/stream` (SSE)

#### Secure Log Analysis (`secure_log_analysis.py`)
- `POST /api/v1/agent/secure/logs` – Paranoid secure JSON analysis (Gemini 2.5 Pro enforced)
- `POST /api/v1/agent/secure/logs/file` – Secure file upload variant
- `POST /api/v1/agent/secure/logs/stream` – Secure SSE stream with real-time security updates
- `GET /api/v1/agent/secure/audit` – Security audit snapshot
- `POST /api/v1/agent/secure/compliance/check` – Full compliance check
- `DELETE /api/v1/agent/secure/cleanup` – Force immediate cleanup

Streaming contracts:
- Primary chat stream emits: `text-start`, `text-delta`, optional `data-*` metadata, `text-end`, `finish`.
- Unified stream (log analysis) emits timeline steps as `{ type: 'step', data: {...} }`, a final assistant message with `analysis_results`, and a terminal `[DONE]` marker.
- Secure log stream emits: `security` (status/redaction) → `analysis` (processing) → `result` → `done`.

#### API Key Management (`api_key_endpoints.py`)
- `GET /api/v1/api-keys` – List masked keys; `POST /api/v1/api-keys` – Create/update; `PUT/DELETE /api/v1/api-keys/{type}`
- `POST /api/v1/api-keys/validate` – Validate format; `POST /api/v1/api-keys/test` – Connectivity
- `GET /api/v1/api-keys/status` – Status summary; `GET /api/v1/api-keys/internal/{type}` – Internal-only decrypted fetch

#### Rate Limit Monitoring (`rate_limit_endpoints.py`)
- `GET /api/v1/rate-limits/status|usage|health|config|metrics`, `POST /api/v1/rate-limits/check/{model}`, `POST /api/v1/rate-limits/reset`

#### Advanced Agent Endpoints (`advanced_agent_endpoints.py`)
- `POST /api/v1/advanced/reasoning/structured` – Structured reasoning
- `POST /api/v1/advanced/troubleshoot/mailbird` – Mailbird-specific troubleshooting
- `POST /api/v1/advanced/research` – Research mode

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
OPENAI_API_KEY=your-openai-key
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

### Provider Registry (`app/providers/registry.py`)
- Dynamic provider registration
- Adapter pattern for multiple AI providers
- Fallback mechanisms

### Supported Providers
1. **Google Gemini** (Primary):
   - Models: gemini-2.5-flash, gemini-2.5-pro
   - Features: Thinking mode, streaming, function calling (secure log analysis enforces Pro)

2. **OpenAI**:
   - Models: GPT5-mini
   - Features: Thinking mode, Function calling, streaming

### Adding New Providers
1. Create adapter in `app/providers/<provider>/`
2. Implement base adapter interface
3. Register in provider registry
4. Update configuration

## Troubleshooting Module

### Components (`app/agents/primary/primary_agent/troubleshooting/`)
- **Error Analysis**: Pattern matching for common errors
- **Solution Database**: Known issue resolutions
- **Diagnostic Tools**: System state inspection
- **Guided Debugging**: Step-by-step troubleshooting

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
The backend provides two CopilotKit-compatible runtimes:

- `/api/v1/copilotkit` – CopilotKit SDK GraphQL runtime (preferred for React provider).
- `/api/v1/copilot/stream` – AG-UI LangGraph streaming adapter (SSE).

Both connect to the existing LangGraph orchestration layer.

### Endpoint Details
- **POST** `/api/v1/copilotkit` – GraphQL runtime used by the `<CopilotKit>` provider.
- **POST** `/api/v1/copilot/stream` – Auth-protected streaming endpoint (SSE adapter).
- **GET** `/api/v1/copilot/stream/health` – Health check returns `{ "status": "ok", "agent": "sparrow" }` when adapter available.

Companion utility:
- **GET** `/api/v1/models?agent_type=primary|log_analysis` – Returns provider model lists used by the frontend `ModelSelector`.

### Dependencies
- CopilotKit SDK runtime: `pip install copilotkit`
- AG-UI adapter (optional SSE path): `pip install "ag-ui-langgraph[fastapi]"`
- Requires FastAPI >=0.115.x

### Implementation
- GraphQL runtime: Registered in `app/main.py` (lazy import) via `copilotkit.integrations.fastapi.add_fastapi_endpoint` using `CopilotKitSDK` + `LangGraphAgent` with our compiled graph.
- SSE adapter: `app/api/v1/endpoints/copilot_endpoints.py` wraps the compiled LangGraph graph and streams via `EventEncoder`.
- Auth: Existing `get_current_user_id` dependency (Supabase JWT) applies.
- Streaming: `EventEncoder` produces SSE or HTTP events based on `Accept` header for the SSE path.

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
- GraphQL runtime handles discovery and streaming via the CopilotKit SDK; used by the React provider.
- SSE adapter path validates the request via `RunAgentInput`, instantiates `LangGraphAgent(name="sparrow", graph=compiled_graph)`, and streams events from `agent.run(input_data)` via `EventEncoder`.
- Both paths support LangGraph interrupts where applicable and include user context from JWT in downstream calls.

### Compatibility Fixes
- Normalizes inbound payloads at `/api/v1/copilot/stream` to avoid 422 errors:
  - Accepts `{ data: {...} }` wrappers and GraphQL `{ query, variables: { input|data } }` shapes.
  - Accepts `forwardedProps | forwardedProperties | properties` and serializes when necessary.
  - Normalizes `messages` from GraphQL-like inputs and preserves `id`.
  - Provides multiple validation variants (dict/string) for forwarded props.
  - Returns structured validation errors for quick debugging.

### Integration Notes
- Reuses existing provider/model selection logic
- Forwards attachments to tools as before
- Respects session memory and preferences
- Emits CopilotKit runtime events compatible with CopilotKit client

## Conclusion

This backend architecture provides a robust, scalable foundation for the Agent Sparrow system. The multi-agent orchestration, combined with comprehensive security, caching, and rate limiting, ensures reliable and performant AI interactions. New developers should focus on understanding the agent graph flow and state management patterns before making modifications.