# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agent Sparrow is a multi-agent AI system with a FastAPI backend and Next.js frontend. It uses LangGraph for orchestrated agent workflows, integrates with AG-UI protocol for native streaming conversations, and leverages Supabase for data persistence. It supports multiple LLM providers (Google Gemini by default, xAI Grok when selected) via a provider factory.

## Common Development Commands

### Full System Startup
```bash
# Start both backend and frontend with all services
./scripts/start_on_macos/start_system.sh

# Stop all services
./scripts/start_on_macos/stop_system.sh
```

### Backend (Python/FastAPI)
```bash
# Run backend only (requires Redis for Celery)
cd /
python -m uvicorn app.main:app --reload --port 8000

# Run tests
pytest
pytest app/tests/test_specific.py -v  # Specific test file
pytest -k "test_name" -v              # Specific test by name

# FeedMe Celery worker (background processing)
celery -A app.feedme.celery_app worker --loglevel=info
```

### Frontend (Next.js/TypeScript)
```bash
cd frontend/

# Development server
npm run dev

# Build for production
npm run build

# Type checking
npx tsc --noEmit

# Linting
npm run lint

# Run tests
npm test

# Security tests
npm run test:security
npm run test:security:full  # With rate limiting tests
```

## Architecture & Key Components

### Backend Structure
The backend follows a modular agent-based architecture:

- **Entry Point**: `app/main.py` - FastAPI application with unified streaming endpoint:
  - `/api/v1/copilot/stream` - AG-UI adapter streaming endpoint using DeepAgents v0.2.5

- **Unified Agent System** (`app/agents/`):
  - **Main Agent**: `unified/agent_sparrow.py` - DeepAgents implementation with middleware stack
  - **Subagents**: `unified/subagents.py` - Research and log diagnoser subagents
  - **Tools**: `unified/tools.py` - KB search, web search, Firecrawl, log analysis
  - **Orchestration Graph**: `orchestration/orchestration/graph.py` - LangGraph v1 workflow
  - **Simplified Log Analysis**: `log_analysis/log_analysis_agent/simplified_agent.py` - Used as tool
  - **Legacy Components** (preserved for reference only):
    - Reasoning schemas: `primary/primary_agent/reasoning/schemas.py`
    - Emotion templates: `primary/primary_agent/prompts/emotion_templates.py`

- **Integration Layer** (`app/integrations/`):
  - Zendesk: `zendesk/` - Ticket system integration with scheduler
  - AG-UI: Direct integration via `ag_ui_langgraph` package (no custom runtime needed)

- **FeedMe Module** (`app/feedme/`):
  - Advanced document processing with Celery background tasks
  - PDF extraction using Gemini vision API as primary method
  - OCR (Tesseract, EasyOCR) as fallback only when Gemini processing fails
  - Multi-modal content handling

- **Database** (`app/db/`):
  - Supabase client and models
  - Vector embeddings for semantic search
  - Session management

### Frontend Structure
React/Next.js application with native AG-UI protocol integration:

- **Entry Points**:
  - Main chat: `frontend/src/app/chat/page.tsx` → uses `frontend/src/features/ag-ui/AgUiChatClient.tsx`
  - FeedMe v2.0: `frontend/src/app/feedme/` - Document processing UI

- **AG-UI Integration**:
  - `/services/ag-ui/` - AG-UI client and types
  - `/features/ag-ui/` - AG-UI components (ChatContainer, MessageList, InterruptHandler)
  - Native SSE streaming without GraphQL translation
  - Direct RunAgentInput protocol support

- **Key Features**:
  - `/features/chat/` - Chat components with reasoning panel
  - `/services/` - API clients and utility services
  - `/shared/` - Reusable UI components
  - Human-in-the-loop interrupts via CUSTOM events

### State Management
- **Backend**: LangGraph state in `app/agents/orchestration/orchestration/state.py`
  - Supports attachments, trace_id, session management
  - Thread-safe with checkpointing

- **Frontend**: AG-UI agent state management
  - AgentContext provider for message and state management
  - Direct SSE event streaming
  - Real-time message updates via AG-UI events

## Model Configuration

Primary defaults remain Gemini-first, but Grok is fully supported:

- **Unified Agent (Primary)**: defaults to `gemini-2.5-flash` (or `grok-4-1-fast-reasoning` when provider=`xai`). Prompt displays friendly model/provider names.
- **Log Diagnoser Subagent**: `gemini-2.5-pro` by default; routed via provider factory (xAI available but not default).
- **Research Subagent**: `gemini-2.5-flash` by default; routed via provider factory (xAI available but not default).
- **FeedMe Document Processing**: `gemini-2.5-flash-lite-preview-09-2025` (vision-first; OCR as fallback).
- **Embeddings**: Gemini Embeddings 001.

Adapter / Provider system:
- Provider factory (`app/agents/unified/provider_factory.py`) builds Google (ChatGoogleGenerativeAI) and xAI (ChatXAI) with `reasoning_enabled` support.
- Settings: `PRIMARY_AGENT_PROVIDER`, `PRIMARY_AGENT_MODEL`, `XAI_API_KEY`, `XAI_DEFAULT_MODEL`, `XAI_REASONING_ENABLED`.
- Coordinator prompt (`app/agents/unified/prompts.py`) auto-injects model display names and adds a Grok-specific depth addendum for richer answers.

## Environment Setup

### Required Environment Variables
Create `.env.local` in project root with:
- Supabase credentials (`SUPABASE_URL`, `SUPABASE_ANON_KEY`)
- Google Gemini API key (`GOOGLE_API_KEY`)
- OpenAI key for adapter testing (`OPENAI_API_KEY`)
- Tavily API key for web search (`TAVILY_API_KEY`)
- Redis configuration for Celery
- See `.env` for full template

### Dependencies
- **Python 3.10+** (specified in `runtime.txt`)
- **Node.js 18+** for frontend
- **Redis** for Celery background tasks
- **PostgreSQL** via Supabase

## Database Schema
Key tables (see `docs/Database.md`):
- `chat_sessions` - Conversation history
- `mailbird_knowledge` - Knowledge base articles
- `web_research_snapshots` - Cached web research
- `langgraph_*` - LangGraph checkpointing
- `feedme_*` - Document processing queue

## Testing Strategy

### Backend Testing
```bash
# Unit tests for agents
pytest app/agents/tests/

# Integration tests with mocked providers
pytest app/tests/integration/ -v

# Coverage report
pytest --cov=app --cov-report=html
```

### Frontend Testing
```bash
cd frontend/
npm test                    # Run all tests
npm run test -- --watch    # Watch mode
npm run test:security      # Security validation
```

## Observability Strategy (LangSmith-Only)

**DECISION (Nov 2025)**: All observability is consolidated within LangSmith. No Prometheus/StatsD/Grafana required.

### LangSmith Configuration
- **Tracing**: Automatic for all LangGraph runs via `app/core/tracing/__init__.py`
- **Project**: Configure via `LANGSMITH_PROJECT` env var
- **API Key**: Set `LANGSMITH_API_KEY` in environment

### What's Tracked
All metrics are captured as LangSmith metadata and tags:

#### 1. **Model Routing & Fallbacks** (`app/agents/unified/model_router.py`)
- Fallback chains: `fallback_chain` metadata shows model progression
- Fallback reasons: `quota_exhausted`, `circuit_open`, `health_check_failed`
- Model health: RPM/RPD usage, circuit breaker state
- Tags: `model:gemini-2.5-flash`, `coordinator_mode:heavy/light`

#### 2. **Memory Operations** (`app/agents/unified/agent_sparrow.py`)
- Retrieval stats: Facts retrieved, relevance scores, query length
- Write stats: Facts extracted/written, response length
- Stored in: `state.scratchpad["_system"]["memory_stats"]`

#### 3. **Search Services** (`app/agents/unified/grounding.py`)
- Service used: `gemini_grounding`, `tavily_fallback`, `firecrawl`
- Success rates: URLs found, extraction successes
- Fallback reasons tracked in metadata

#### 4. **AG-UI Stream Context** (`app/api/v1/endpoints/copilot_endpoints.py`)
- Enhanced metadata: agent_config, feature_flags, search_config
- Tags: `agui-stream`, `memory_enabled`, `attachments:true`
- Session/trace IDs for correlation

### How to Use LangSmith UI
1. **Filter runs** by tags: `model:gemini-2.5-pro`, `task_type:log_analysis`
2. **Analyze latency**: P50/P95/P99 automatically calculated
3. **Track fallbacks**: Search metadata for `fallback_occurred: true`
4. **Memory performance**: Filter by `memory_enabled` tag, examine memory_stats
5. **Cost tracking**: Configure model pricing in LangSmith settings

### Example Queries in LangSmith
- High latency runs: `latency > 5000ms`
- Fallback analysis: `metadata.fallback_occurred = true`
- Memory-enabled sessions: `tags contains "memory_enabled"`
- Pro model usage: `tags contains "model:gemini-2.5-pro"`

### Benefits vs Prometheus
- ✅ Zero additional infrastructure
- ✅ Automatic correlation with traces
- ✅ Native LangGraph integration
- ✅ Built-in cost tracking
- ✅ No metrics aggregation needed
- ✅ Single source of truth for observability

See `docs/LangSmith-Observability-Guide.md` for detailed monitoring playbooks.

## Current Migration Status
The codebase has successfully migrated to the native AG-UI client implementation:
- ✅ Legacy CopilotKit artifacts removed (dependencies, hooks, and UI shims)
- ✅ Native AG-UI client (@ag-ui/client) integrated
- ✅ Direct SSE streaming without GraphQL translation
- ✅ AG-UI protocol fully integrated (RunAgentInput/SSE events)
- ✅ DeepAgents v0.2.5 middleware stack operational
- ✅ Frontend using `/api/v1/copilot/stream` endpoint with native protocol
- ✅ Human-in-the-loop interrupts via CUSTOM events
- ✅ Legacy troubleshooting and reasoning pipelines removed (~12,000 lines)
- See `docs/reference/` for historical architecture documentation

## Code Quality & Architecture (Nov 2025)

**Recent Improvements** (CodeRabbit review, 2025-11-25):

### Backend Middleware & Harness
- **Thread-Safety**: Session cache uses double-checked locking singleton, async locks for middleware stats
- **Error Handling**: Tool contracts have consistent exception handling across sync/async wrappers
- **Memory Middleware**: Sentinel pattern for failed imports, standardized dict access
- **Rate Limiting**: Proper model initialization, fallback model injection support
- **Eviction Middleware**: Race-condition-free stats, `functools.wraps` preserved

### Storage Backends (`app/agents/harness/backends/`)
- **Composite Backend**: Path normalization prevents false matches (`/scratch` vs `/scratchpad`)
- **Supabase Store**: UTF-8 byte size validation, N+1 query elimination, unlimited grep reads
- **InMemoryBackend (protocol.py)**: Negative offset/limit validation, proper path prefix matching

### Memory Store (`app/agents/harness/store/memory_store.py`)
- **Async Compatibility**: Python 3.10+ compatible asyncio handling (no deprecated `get_event_loop()`)
- **Pagination**: Fixed double-pagination bug in `_execute_search` - pagination now applied once at the end

### Streaming Infrastructure (`app/agents/streaming/`)
- **Emitter**: Proper falsy value handling (`0`, `False`, `""` preserved)
- **Normalizers**: Dict mutation prevention via shallow copy, clear control flow
- **Handler**: Event emission on fallback paths for observability

### FeedMe API Endpoints (`app/api/v1/endpoints/feedme/`)
- **folders.py**: TOCTOU race condition fixed with DB constraint catch, safe client IP extraction for proxies
- **analytics.py**: Fixed status key mapping, None handling with `or 0` pattern, safe dict access
- **conversations.py**: Error messages sanitized (no internal details), KeyError prevention with `.get()`
- **versioning.py**: HTTPException re-raise before generic Exception handlers
- **ingestion.py**: Safe request.client access, error message sanitization
- **approval.py**: Fixed `rejected_by` field name (was incorrectly using `approved_by`)

### Knowledge Tools (`app/tools/feedme_knowledge.py`)
- **Thread Safety**: Double-checked locking for FeedMe connector singleton
- **Fallback Logic**: Combined fallback only runs when NO results (doesn't overwrite partial results)

### Frontend AG-UI Services
- **Validators**: Unknown events return `null` (consistent validation contract)
- **Event Types**: `KNOWN_EVENT_NAMES` const with type derivation
- **Event Handlers**: Getter functions prevent stale closure references

### Message Preparation
- **LangChain Compatibility**: Uses `.type` attribute (not `.role`) for message types

## Deployment Considerations

### Production Startup
```bash
./scripts/production-startup.sh  # Full production setup with optimizations
```

### Service Dependencies
1. **Redis** must be running for Celery workers
2. **Supabase** project must be configured and accessible
3. **Environment variables** must be properly set
4. **Google Gemini API** quota and rate limits must be monitored

### Port Allocation
- Backend API: `http://localhost:8000`
- Frontend UI: `http://localhost:3000`
- Redis: Default port 6379

## Key Integration Points

### AG-UI Streaming
- Preferred endpoint: `POST /api/v1/copilot/stream`
- Native SSE event streaming with AG-UI protocol
- Handles interrupts via CUSTOM events
- Supports file attachments via BinaryInputContent in RunAgentInput

### Unified Agent with Subagents
The unified agent (`app/agents/unified/agent_sparrow.py`) handles all queries with subagents:
- General queries → Primary unified agent (Gemini 2.5 Flash)
- Log analysis → Log diagnoser subagent (Gemini 2.5 Pro)
- Research tasks → Research subagent (Gemini 2.5 Flash)
- No routing needed - subagents called as tools when appropriate

### FeedMe Document Processing
Advanced document pipeline at `/feedme`:
- **Primary**: Gemini 2.5 Flash Lite vision API for PDF-to-Markdown
- **Fallback only**: OCR (Tesseract/EasyOCR) when Gemini fails
- Background processing via Celery
- Multi-modal content support
- Budget-aware processing with rate limiting

## Debugging Tips

### Backend Logs
```bash
# View real-time backend logs
tail -f system_logs/backend/backend.log

# Celery worker logs
tail -f system_logs/celery/celery_worker.log
```

### Frontend Debugging
- Browser DevTools Network tab for API calls
- React Developer Tools for component state
- Check `/api/v1/copilot/stream` responses for streaming issues

### Common Issues
1. **Redis not running**: FeedMe features won't work
2. **Port conflicts**: Use `lsof -i :PORT` to check
3. **Missing env vars**: Verify with `frontend/scripts/verify-env.js`
4. **Gemini rate limits**: Monitor usage in FeedMe's gemini_tracker
5. **PDF processing fallback**: Check logs if OCR is being triggered unnecessarily
6. **CORS errors**: Ensure backend allows frontend port (3000/3001) in `app/main.py`
7. **SSE connection issues**: Check browser console for AG-UI event errors
