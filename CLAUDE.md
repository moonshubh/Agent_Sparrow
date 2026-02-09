# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
Last updated: 2026-02-09

## Project Overview

Agent Sparrow is a multi-agent AI system with a FastAPI backend and Next.js frontend. It uses LangGraph for orchestrated agent workflows, integrates with AG-UI protocol for native streaming conversations, and leverages Supabase for data persistence. It supports multiple LLM providers (Google Gemini by default, xAI Grok when selected) via a provider factory.

## Implementation Update (2026-02-09)

- mem0 v1 backend activation completed via `mem0ai==1.0.3` with `vecs==0.4.5` and `pgvector==0.3.6`.
- `MemoryService` now uses mem0 public APIs and includes production-safe fallbacks:
  - embedding dimension clamp to 2000 for vecs/pgvector index limits
  - collection fallback for dimension mismatch (`*_dim{n}`)
  - telemetry vector-store fallback to avoid `mem0migrations` startup failures blocking primary memory.
- Unified tool input hardening added to prevent model-argument validation failures (`db_unified_search`, `db_grep_search`, and `web_search` max-result coercion/clamping).
- Tool execution reliability fixed for timeout-disabled mode in `tool_executor` (prevents false `Unknown error` returns).
- Subgraph compatibility/event contract work is in place with smoke coverage for `task -> subgraph -> subagent_spawn/subagent_end`.
- CI now includes fresh-venv dependency integrity checks (`pip install -r requirements.txt` + `pip check`).
- Latest backend gate status: `pytest -q` pass, `ruff check .` pass, `mypy app/` still blocked by pre-existing baseline typing debt outside this rollout.

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

## Railway Deployment

- Backend deploys via Railpacks: `railway.json` sets `"builder": "RAILPACK"` and `"dockerfilePath": null`.
- Frontend deploys via `frontend/railway.toml` with `builder = "RAILPACK"`.
- feedme-worker uses `railway.worker.json` (Railpack builder + Celery start command).
- Railpack settings (APT packages/runtime pins) live in `railpack.json`.
- Keep `docker/containerfile.dev` for local builds only; no root `Dockerfile` in the repo.
- Avoid Dockerfile/Nixpacks on Railway unless explicitly approved.

### Troubleshooting Notes

- If Railway starts doing Docker builds, first check for a root `Dockerfile`/`Containerfile` and remove it (Railway auto-detection prefers Docker).
- Confirm the active deployment is using Railpack: `railway deployment list --json | jq '.[0].meta.serviceManifest.build'`.
- If the service crashes with `uvicorn: not found` or `celery: not found`, it means the Railpack venv (`/app/.venv`) is not on `PATH`; `scripts/railway-entrypoint.sh` is the supported start command because it bootstraps the venv and runs `python -m uvicorn` / `python -m celery`.

## Architecture & Key Components

### Backend Structure
The backend follows a modular agent-based architecture:

- **Entry Point**: `app/main.py` - FastAPI application with unified streaming endpoint:
  - `/api/v1/agui/stream` - AG-UI adapter streaming endpoint using DeepAgents v0.2.5

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
  - Memory UI: `frontend/src/app/memory/page.tsx` - 3D knowledge graph visualization

- **AG-UI Integration**:
  - `/services/ag-ui/` - AG-UI client and types
  - `/features/ag-ui/` - AG-UI components (ChatContainer, MessageList, InterruptHandler)
  - Native SSE streaming without GraphQL translation
  - Direct RunAgentInput protocol support

- **Key Features**:
  - `/features/chat/` - Chat components with reasoning panel
  - `/features/memory/` - 3D knowledge graph using react-three-fiber
  - `/services/` - API clients and utility services
  - `/shared/` - Reusable UI components
  - Human-in-the-loop interrupts via CUSTOM events

### Memory UI Module (Jan 2026)
The Memory UI provides a 3D knowledge graph visualization for managing agent memories:

- **Backend**: `app/api/v1/endpoints/memory/` - CRUD endpoints for memories, entities, relationships
- **Service**: `app/memory/memory_ui_service.py` - Memory search, feedback, confidence scoring
- **Frontend**: `frontend/src/features/memory/` - 3D visualization with react-three-fiber

**Key Components:**
- Entity nodes and relationship edges in 3D space
- Confidence-based ordering and duplicate detection
- Feedback loop: message thumbs up/down → memory confidence updates
- Semantic search across memory content

### State Management
- **Backend**: LangGraph state in `app/agents/orchestration/orchestration/state.py`
  - Supports attachments, trace_id, session management
  - Thread-safe with checkpointing

- **Frontend**: AG-UI agent state management
  - AgentContext provider for message and state management
  - Direct SSE event streaming
  - Real-time message updates via AG-UI events

## Model Configuration

### Single Source of Truth: models.yaml

All model configuration lives in `app/core/config/models.yaml` (coordinators, internal models,
subagents, Zendesk variants, and per-bucket rate limits). The YAML is validated at startup;
missing or invalid config is a fatal error. `model_registry.py` derives from this YAML for
UI-friendly metadata.

### Editing Models

- Update model IDs, temperatures, context windows, and rate limits in `app/core/config/models.yaml`.
- Optional override path: `MODELS_CONFIG_PATH`.
- Optional dev reload: `MODELS_CONFIG_RELOAD=true`.

### Runtime Overrides

Runtime overrides (e.g., `GraphState.model` / `GraphState.provider`) are allowed only for models
defined in `models.yaml`. Unknown overrides are dropped and fallback rules apply.

### Startup Health Checks

On startup, the backend performs **real API calls** to all configured models (coordinators, internal
models, subagents, and Zendesk variants). Failures mark the model unavailable and trigger fallback;
startup continues. A missing OpenRouter key logs a warning and forces subagent fallback to the
coordinator.

### Rate Limiting

Rate limits are bucket-based and driven by `models.yaml` (coordinator, coordinator-with-subagents,
each subagent, internal models, Zendesk variants). A safety margin is applied automatically.

### Usage in Code

```python
from app.core.config import get_models_config, resolve_coordinator_config, get_registry

config = get_models_config()
coordinator = resolve_coordinator_config(config, "google")
model_id = coordinator.model_id

registry = get_registry()
names = registry.get_display_names()
```

### Frontend API Endpoints

```http
GET /api/v1/models
GET /api/v1/models/config
```

These endpoints expose YAML-derived registry metadata and provider availability.

## Prompt Architecture (Nov 2025)

All agent prompts use a **tiered architecture** based on Google's 9-step reasoning framework, optimized for Gemini 3.0 Pro and Grok 4.1.

**Full documentation**: See `docs/Unified-Agent-Prompts.md`

### Tiered Prompt System

| Tier | Agents | Reasoning | Temperature |
|------|--------|-----------|-------------|
| **Heavy** | Coordinator, Log Analysis | Full 9-step framework | 0.1-0.2 |
| **Standard** | Research | 4-step workflow | 0.5 |
| **Lite** | DB Retrieval, FeedMe | Minimal task-focused | 0.1-0.3 |

### Google's 9-Step Reasoning Framework (Heavy Tier)

Agents implement a reasoning framework:
1. **Logical Dependencies** - Analyze constraints, prerequisites, order of operations
2. **Risk Assessment** - LOW for searches, HIGH for state-changing actions
3. **Abductive Reasoning** - Generate 1-3 hypotheses, prioritize by likelihood
4. **Adaptability** - Update hypotheses when observations contradict assumptions
5. **Information Sources** - Check: Memory → KB → FeedMe → Macros → Web → User
6. **Precision & Grounding** - Quote exact sources, distinguish evidence from reasoning
7. **Completeness** - Exhaust all relevant options before concluding
8. **Persistence** - Retry transient errors (max 2x), change strategy on other errors
9. **Inhibited Response** - Complete reasoning BEFORE taking action

### Temperature Configuration

Role-based temperature in `app/agents/unified/provider_factory.py`:

```python
TEMPERATURE_CONFIG = {
    "coordinator": 0.2,       # Deterministic reasoning
    "log_analysis": 0.1,      # High precision for error diagnosis
    "research": 0.5,          # Creative synthesis of sources
    "db_retrieval": 0.1,      # Exact pattern matching
    "feedme": 0.3,            # Balanced
    "default": 0.3,
}
```

### Grok 4.1 Configuration

Grok reasoning is **always enabled** for maximum quality:

```python
GROK_CONFIG = {
    "reasoning_enabled": True,   # Always enabled
    "thinking_budget": "medium", # Balanced latency/quality
}
```

When using Grok, prompts automatically include guidance to:
- NOT output explicit step-by-step reasoning (internal only)
- Focus user-facing output on clear, actionable answers
- Let internal reasoning guide tool selection

### Prompt Files

- `app/agents/unified/prompts.py` - All prompt templates, `get_coordinator_prompt()`
- `app/agents/unified/provider_factory.py` - `TEMPERATURE_CONFIG`, `GROK_CONFIG`, `build_chat_model()`

### Building Models with Role-Based Temperature

```python
from app.agents.unified.provider_factory import build_chat_model

# Role-based temperature (recommended)
model = build_chat_model(
    provider="google",
    model="gemini-2.5-flash",
    role="coordinator",  # Uses temperature 0.2
)

# Grok with always-enabled reasoning
model = build_chat_model(
    provider="xai",
    model="grok-4-1-fast-reasoning",
    role="log_analysis",
    # reasoning_enabled=True applied automatically
)
```

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
- `memories_new` - Knowledge graph memories with embeddings
- `entities` - Graph nodes (topics, concepts)
- `relationships` - Graph edges between entities
- `memory_feedback` - User feedback on memory accuracy
- `zendesk_pending_tickets` - Zendesk ticket processing queue with `status`, `status_details` (JSON context report), `last_public_comment_at`
- `store` - Workspace file storage for context engineering (handoff, progress, goals, per-ticket Zendesk data)

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
- **Dual retrieval**: Queries both mem0 and Memory UI sources
- **Retrieval stats**: Facts retrieved, relevance scores, query length
- **Memory ID tracking**: Retrieved memory IDs tracked for feedback attribution
- **Write stats**: Facts extracted/written, response length
- **Feedback propagation**: Message thumbs up/down updates memory confidence scores
- Stored in: `state.scratchpad["_system"]["memory_stats"]`

#### 3. **Search Services** (`app/agents/unified/grounding.py`)
- Service used: `gemini_grounding`, `tavily_fallback`, `firecrawl`
- Success rates: URLs found, extraction successes
- Fallback reasons tracked in metadata

#### 4. **AG-UI Stream Context** (`app/api/v1/endpoints/agui_endpoints.py`)
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
- ✅ Native AG-UI client (@ag-ui/client) integrated
- ✅ Direct SSE streaming without GraphQL translation
- ✅ AG-UI protocol fully integrated (RunAgentInput/SSE events)
- ✅ DeepAgents v0.2.5 middleware stack operational
- ✅ Frontend using `/api/v1/agui/stream` endpoint with native protocol
- ✅ Human-in-the-loop interrupts via CUSTOM events
- ✅ Legacy troubleshooting and reasoning pipelines removed (~12,000 lines)
- See `docs/reference/` for historical architecture documentation

## Coding Standards & Best Practices

This section provides comprehensive coding guidelines for both TypeScript (frontend) and Python (backend) development. See `AGENTS.md` for detailed conventions.

### TypeScript Best Practices

#### Type Safety (Strict Mode Required)
```typescript
// tsconfig.json - strict mode is mandatory
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true
  }
}
```

**Key Rules:**
- **Never use `any`** - Use `unknown` with type guards or union types
- **Leverage generics** for reusable, type-safe functions
- **Use utility types**: `Partial<T>`, `Pick<T, K>`, `Omit<T, K>`, `Record<K, V>`
- **Mark immutable data** with `readonly`
- **Use `never`** for exhaustive switch statements

```typescript
// Good: Precise types
function processMessage<T extends BaseMessage>(msg: T): ProcessedMessage<T> { ... }
type ChatSummary = Pick<ChatSession, 'id' | 'title' | 'createdAt'>;

// Avoid
function process(data: any) { ... }  // Bad - disables type checking
```

#### Code Formatting & Linting
- **Prettier** for formatting (auto-applied on save)
- **ESLint** with `@typescript-eslint/recommended` + `prettier` config
- Run `pnpm lint` before commits

```json
// .eslintrc.json
{
  "extends": ["eslint:recommended", "plugin:@typescript-eslint/recommended", "prettier"],
  "parser": "@typescript-eslint/parser"
}
```

#### React/Next.js Patterns
- **Functional components only** with hooks
- **Single responsibility** - one component, one purpose
- **Colocate related code** - component, tests, types in same folder
- **Use feature-based structure** in `src/features/`
- **Query by role/text** in tests (Testing Library best practices)

### Python Best Practices

#### Type Annotations (Required for New Code)
```python
# All function signatures must have type hints
def get_user_by_id(user_id: str, include_profile: bool = False) -> User | None:
    """Fetch user by ID, optionally including profile data."""
    ...

# Use modern Python 3.10+ syntax
def process_items(items: list[str]) -> dict[str, int]:  # Not List[str]
    ...

# Generic types for reusable functions
from typing import TypeVar, Sequence
T = TypeVar('T')
def first_or_none(items: Sequence[T]) -> T | None:
    return items[0] if items else None
```

**Mypy Configuration:**
```ini
# mypy.ini or pyproject.toml
[tool.mypy]
python_version = "3.11"
strict = true
disallow_untyped_defs = true
warn_return_any = true
```

#### Code Formatting (Black + Ruff)
```bash
# Auto-format with Black
black .

# Lint with Ruff (10-100x faster than Flake8)
ruff check . --fix
ruff format .
```

```toml
# pyproject.toml
[tool.ruff]
select = ["E", "F", "I", "B", "ANN"]  # Errors, Pyflakes, isort, Bugbear, Annotations
line-length = 88
extend-ignore = ["E203"]

[tool.black]
line-length = 88
target-version = ["py311"]
```

#### FastAPI Architecture Patterns
```python
# Domain separation: routes call services, services handle logic
# app/api/v1/endpoints/users.py
from fastapi import APIRouter, Depends
from app.schemas.user import UserCreate, UserOut
from app.services import user_service
from app.api.deps import get_db

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/", response_model=UserOut)
async def create_user(user_in: UserCreate, db=Depends(get_db)) -> UserOut:
    return await user_service.create_user(db, user_in)
```

**Key Patterns:**
- **APIRouter per domain** - group related endpoints
- **Pydantic schemas** for request/response validation
- **Dependency injection** for DB sessions, auth, config
- **Service layer** for business logic (separate from routes)
- **Use `BaseSettings`** for configuration management

### Testing Standards

#### Frontend (Vitest + Testing Library)
```typescript
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';

describe('ChatInput', () => {
  it('submits message on enter key', async () => {
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} />);

    // Query by role (accessibility-focused)
    const input = screen.getByRole('textbox');
    await userEvent.type(input, 'Hello{enter}');

    expect(onSubmit).toHaveBeenCalledWith('Hello');
  });
});
```

**Principles:**
- Test behavior, not implementation
- Query by role/text (not test IDs)
- Use `userEvent` for realistic interactions
- Colocate tests with components

#### Backend (Pytest)
```python
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_create_item(async_client):
    response = await async_client.post("/items/", json={"name": "Test"})
    assert response.status_code == 200
    assert response.json()["name"] == "Test"
```

**Principles:**
- Use fixtures for setup/teardown
- Test both happy path and edge cases
- Use `pytest.mark.asyncio` for async tests
- Override dependencies with `app.dependency_overrides`

### Dependency Management

#### Frontend (pnpm)
- Commit `pnpm-lock.yaml` for reproducibility
- Use exact versions for critical dependencies
- Separate dev dependencies properly

#### Backend (pip-tools or Poetry)
```bash
# pip-tools workflow
pip-compile requirements.in -o requirements.txt
pip install -r requirements.txt

# Poetry workflow
poetry install
poetry add <package>
poetry lock
```

**Always commit lock files** (`poetry.lock` or compiled `requirements.txt`)

### CI Pipeline Checks
1. **Lint**: `pnpm lint` + `ruff check .`
2. **Format**: `prettier --check .` + `ruff format --check .`
3. **Type Check**: `pnpm typecheck` + `mypy app/`
4. **Test**: `pnpm test` + `pytest --cov=app`
5. **Build**: `pnpm build`

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

## Context Engineering (Dec 2025)

Agent Sparrow implements **Deep Agent** patterns from LangChain and Anthropic's "Effective Harnesses for Long-Running Agents" for session continuity and progress tracking.

### Architecture Overview

The context engineering system provides:
- **Session handoff** - Capture context before summarization for seamless continuity
- **Progress tracking** - Persistent notes survive across messages and sessions
- **Goal management** - Track feature completion with pass/fail/pending status
- **Virtual file system** - Organized workspace with ephemeral and persistent storage

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `SparrowWorkspaceStore` | `app/agents/harness/store/workspace_store.py` | LangGraph BaseStore backed by Supabase `store` table |
| `SessionInitMiddleware` | `app/agents/harness/middleware/session_init_middleware.py` | Loads handoff context on first message |
| `HandoffCaptureMiddleware` | `app/agents/harness/middleware/handoff_capture_middleware.py` | Captures context at 60% of context window |
| `SparrowCompositeBackend` | `app/agents/harness/backends/composite.py` | Routes storage to ephemeral vs persistent backends |

### Workspace Routes

```python
# Ephemeral (cleared per session)
/scratch/          # Working notes, intermediate results

# Persistent (survives across sessions)
/progress/         # Session progress notes (markdown)
/goals/            # Active goals with pass/fail status (JSON)
/handoff/          # Session handoff context for resumption (JSON)
```

### Usage Example

```python
from app.agents.harness.store import SparrowWorkspaceStore
from app.agents.harness.middleware import (
    SessionInitMiddleware,
    HandoffCaptureMiddleware,
)

# Create workspace store for session
store = SparrowWorkspaceStore(session_id="session-123")

# Middleware stack
middleware = [
    SessionInitMiddleware(store),           # Load context on first message
    # ... other middleware ...
    HandoffCaptureMiddleware(
        store,
        context_window=128000,              # Model's context window
        capture_threshold_fraction=0.6,     # Capture before 70% summarization
    ),
]

# Convenience methods
await store.set_progress_notes("## Current Status\n- Working on feature X")
await store.set_active_goals({
    "description": "Implement user auth",
    "features": [
        {"name": "Login form", "status": "pass"},
        {"name": "Session tokens", "status": "pending"},
    ]
})
handoff = await store.get_handoff_context()  # Returns previous session context
```

### Handoff Context Structure

When context approaches 60% of the model's context window, `HandoffCaptureMiddleware` automatically captures:

```json
{
  "summary": "User Request: ... Key Findings: ...",
  "active_todos": [{"content": "Task 1", "status": "in_progress"}],
  "next_steps": ["Step 1", "Step 2"],
  "key_decisions": ["I've decided to use X pattern"],
  "message_count": 42,
  "estimated_tokens": 76800,
  "capture_number": 1,
  "timestamp": "2025-12-03T05:43:42.631685+00:00"
}
```

### Session Initialization

On the first message of a new session, `SessionInitMiddleware` injects system messages:

1. **[Session Handoff Context]** - Previous session summary, next steps, pending todos
2. **[Active Goals]** - Current goals with pass/fail/pending status
3. **[Session Progress Notes]** - Markdown progress notes (if < 2000 chars)

### Prompt Integration

The coordinator prompt includes workspace instructions in `<workspace_files>` section:

```xml
<workspace_files>
You have access to a virtual file system for organizing complex tasks:

**Working Files (ephemeral - cleared per session):**
- `/scratch/notes.md` - Working notes for current task

**Persistent Files (survive across messages and sessions):**
- `/progress/session_notes.md` - Progress notes auto-captured during long tasks
- `/goals/active.json` - Current goals and their status (pass/fail/pending)
- `/handoff/summary.json` - Session handoff context loaded at start
</workspace_files>
```

### Database Storage

Workspace files are stored in the Supabase `store` table:

| Column | Type | Description |
|--------|------|-------------|
| `prefix` | VARCHAR | Namespace path (e.g., `workspace:handoff:session-123`) |
| `key` | VARCHAR | File key (e.g., `summary.json`) |
| `value` | JSONB | File content |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update timestamp |

### Testing

Run context engineering tests:

```bash
# Test workspace store and middleware
python -c "
import asyncio
from app.agents.harness.store import SparrowWorkspaceStore
from app.agents.harness.middleware import SessionInitMiddleware, HandoffCaptureMiddleware

async def test():
    store = SparrowWorkspaceStore('test-session')
    await store.set_progress_notes('Test notes')
    notes = await store.get_progress_notes()
    print(f'Progress notes: {notes}')

asyncio.run(test())
"
```

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
- Celery Health: `http://localhost:8001` (auto-detects port collision)
- Redis: Default port 6379

## Zendesk Integration (Jan 2026)

The Zendesk integration processes support tickets automatically, generating internal notes with suggested replies using the full agent toolset.

### Architecture

| Component | Location | Purpose |
|-----------|----------|---------|
| Scheduler | `app/integrations/zendesk/scheduler.py` | Polls `zendesk_pending_tickets`, orchestrates agent runs |
| Client | `app/integrations/zendesk/client.py` | Zendesk API wrapper with attachment fetching and PII redaction |
| Attachments | `app/integrations/zendesk/attachments.py` | URL scrubbing, attachment type summarization, log detection |
| Spam Guard | `app/integrations/zendesk/spam_guard.py` | Rate-limiting and deduplication for note posting |
| Import Endpoint | `app/api/v1/endpoints/memory/endpoints.py` | `POST /api/v1/memory/import/zendesk-tagged` for ticket-to-memory ingestion |
| Asset Proxy | `app/api/v1/endpoints/memory/endpoints.py` | `GET /api/v1/memory/assets/{bucket}/{object_path}` for authenticated image serving |
| Celery Task | `app/feedme/tasks.py` | `import_zendesk_tagged` background job for ticket ingestion |
| Queue Routing | `app/feedme/celery_app.py` | Routes Zendesk import tasks to appropriate Celery queues |

### Key Behaviors

- **Full toolset**: Zendesk runs use `get_registered_tools()` (not the restricted `get_registered_support_tools()`), excluding only image generation.
- **Memory retrieval**: Enabled via `use_server_memory=True` in GraphState. Memory UI retrieval is active when `ENABLE_MEMORY_UI_RETRIEVAL=true`. mem0 is optional.
- **Attachment handling**: Only public comments are processed. Attachments are fetched via API, PII is redacted, and Zendesk attachment URLs are scrubbed from generated content.
- **Log detection**: Log attachments (`.log`, `.txt` with log patterns) are detected and routed to the `log_diagnoser` subagent automatically. The agent avoids requesting logs if attachments already contain them.
- **Context report**: A structured `context_report` is unconditionally persisted in `zendesk_pending_tickets.status_details` for every processed ticket, with serialization error fallbacks.
- **Reply formatting**: Internal notes use "Suggested Reply only" format. A sanitization pass removes planning artifacts, enforces policy-compliant greetings, and ensures empathetic phrasing.
- **Telemetry**: `zendesk_run_telemetry` logging captures tool usage, memory stats, and evidence summaries per ticket run.
- **Session cleanup**: Daily maintenance deletes per-ticket workspace data 7 days after `last_public_comment_at`.

### Zendesk Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ZENDESK_DRY_RUN` | When `true`, notes are logged but not posted | `true` |
| `ENABLE_MEMORY_UI_RETRIEVAL` | Enable Memory UI as retrieval source for Zendesk | `false` |
| `MEMORY_UI_AGENT_ID` | Agent ID for Memory UI queries | — |
| `MEMORY_UI_TENANT_ID` | Tenant ID for Memory UI queries | — |

### Testing Zendesk Locally

```bash
# 1. Ensure .env has Zendesk credentials and ZENDESK_DRY_RUN=false
# 2. Start system
./scripts/start_on_macos/start_system.sh

# 3. Check queue status
# Query zendesk_pending_tickets in Supabase for status='pending'

# 4. View logs
tail -f system_logs/backend/backend.log | grep -i zendesk
```

### Known Issues & Gotchas

- **LangSmith rate limiting**: Monthly trace limits can be hit during batch Zendesk runs. Non-blocking but reduces observability.
- **Tavily quota**: When exhausted, web search falls back to Minimax automatically.
- **mem0 not installed**: If `mem0` package is missing, the system logs a warning and continues with Memory UI only. No false-positive retrieval signals.
- **Recursion limit**: `ZENDESK_RECURSION_LIMIT` (30) may be overridden by the global LangGraph default (400). Check `GraphState` construction.

## Reliability Patterns (Jan 2026)

### Database Query Retries
Transient Supabase errors (server disconnected, connection reset) are handled by `_run_supabase_query_with_retry` in `app/agents/tools/tool_executor.py`:
- Retries up to 2x with exponential backoff
- Only retries on patterns in `_TRANSIENT_SUPABASE_ERRORS`
- Non-transient errors propagate immediately

### Web Tool Fallbacks
- **Tavily -> Minimax**: When Tavily quota is exhausted, web search falls back to Minimax tools automatically
- **Minimax retries**: Configured with built-in retry logic for transient failures
- **Firecrawl**: Used as an alternative for URL-specific content extraction

### Internal Retrieval Bounds
`db_unified_search.max_results_per_source` is clamped to prevent validation errors when the value exceeds tool limits. Applied in `app/integrations/zendesk/scheduler.py`.

### mem0 Availability Check
`app/core/settings.py` accurately reports whether mem0 backend is configured rather than just checking for package availability, preventing misleading retrieval signals.

## Key Integration Points

### AG-UI Streaming
- Preferred endpoint: `POST /api/v1/agui/stream`
- Native SSE event streaming with AG-UI protocol
- Handles interrupts via CUSTOM events
- Supports file attachments via BinaryInputContent in RunAgentInput

### Unified Agent with Subagents
The unified agent (`app/agents/unified/agent_sparrow.py`) handles all queries with tiered subagents:

| Subagent | Tier | Model | Temperature | Use Case |
|----------|------|-------|-------------|----------|
| **Coordinator** | Heavy | Gemini 2.5 Flash | 0.2 | General queries, orchestration |
| **Log Diagnoser** | Heavy | Gemini 3.0 Pro | 0.1 | Log/error analysis with 9-step reasoning |
| **Research** | Standard | Gemini 2.5 Flash | 0.5 | Web research, source synthesis |
| **DB Retrieval** | Lite | Gemini 2.5 Flash Lite | 0.1 | KB/FeedMe/macro lookups |

- No routing needed - subagents called as tools when appropriate
- Each subagent uses tier-appropriate prompts (see `docs/Unified-Agent-Prompts.md`)
- Model assignments configurable via Model Registry (see `docs/Model-Registry.md`)
- Temperature automatically set based on role via `provider_factory.py`

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
- Check `/api/v1/agui/stream` responses for streaming issues

### Common Issues
1. **Redis not running**: FeedMe features won't work
2. **Port conflicts**: Use `lsof -i :PORT` to check
3. **Missing env vars**: Verify with `frontend/scripts/verify-env.js`
4. **Gemini rate limits**: Monitor usage in FeedMe's gemini_tracker
5. **PDF processing fallback**: Check logs if OCR is being triggered unnecessarily
6. **CORS errors**: Ensure backend allows frontend port (3000/3001) in `app/main.py`
7. **SSE connection issues**: Check browser console for AG-UI event errors
8. **Zendesk 404 on attachments**: Attachment URLs are signed and expire; the scheduler fetches via API and stores locally
9. **Zendesk context_report missing**: Check serialization in `scheduler.py`; fallbacks should catch JSON errors
10. **Memory UI retrieval silent**: Set `ENABLE_MEMORY_UI_RETRIEVAL=true` and configure `MEMORY_UI_AGENT_ID`/`MEMORY_UI_TENANT_ID`
11. **`API_KEY_ENCRYPTION_SECRET` missing**: Required for production; causes `OSError` in `app/core/encryption.py` if absent
