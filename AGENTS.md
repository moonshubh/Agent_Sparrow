# Repository Guidelines

## Project Structure & Module Organization

### Frontend (Next.js/TypeScript)
- `frontend/`: Next.js 16 app with feature-based architecture
  - `src/app/`: Routes and layouts (Next.js App Router)
  - `src/features/`: Domain-specific modules (chat, ag-ui, feedme, memory) with colocated components, hooks, and services
  - `src/shared/`: Reusable UI primitives and utilities
  - `src/services/`: API clients and Supabase integration
  - `src/state/`: Zustand stores organized by domain
  - `scripts/`: Helper scripts for development

### Backend (Python/FastAPI)
- `app/`: FastAPI application with modular agent architecture
  - `main.py`: Application entrypoint with CORS and router setup
  - `agents/`: Agent modules (unified, orchestration, harness)
  - `api/v1/endpoints/`: APIRouter modules by domain (chat, feedme, memory)
  - `core/`: Config, tracing, and shared utilities
  - `db/`: Supabase client and models
  - `integrations/`: External service integrations (Zendesk, AG-UI)
  - `memory/`: Memory UI service, search, and feedback propagation
  - `services/`: Business logic layer
  - `feedme/`: Document processing module with Celery tasks

### Other Directories
- `tests/`: Pytest suites by domain (`agents/`, `api/`, `backend/`, `frontend/`, `smoke/`) with shared fixtures in `conftest.py`
- `docs/`: Technical documentation and architecture references
- `scripts/`: Automation and deployment scripts

## Memory UI Implementation Notes (Feb 2026)

- `Import Knowledge` defaults to the `mb_playbook` tag across frontend, API schema defaults, and Celery fallback handling.
- Import jobs now support explicit status polling via `GET /api/v1/memory/import/zendesk-tagged/{task_id}` so queued jobs have visible completion/failure states.
- Import task results now include `processed_tickets`, `imported_memory_ids`, and per-ticket failure metadata for deterministic UI refresh/focus after completion.
- Memory UI now polls queued import tasks, surfaces completion/failure toasts, invalidates memory/graph/stats caches on completion, and focuses the latest imported memory in table view.
- Table UX is click-first on memory content (admin edit modal / non-admin read-only modal), with the eye action removed.
- Edited-memory retrieval uses hybrid ranking explainability fields (`is_edited`, `edited_boost`, `hybrid_score`) with additive response compatibility.
- Feedback confidence now uses deterministic step sizing for thumbs feedback: each `thumbs_up` applies `+5%` and each `thumbs_down` applies `-5%` (clamped to `0-100%`), aligned in both frontend optimistic state and backend persistence.
- Feedback UI reflection is hardened: table actions now coerce malformed confidence/count payloads safely, avoid click propagation side effects, and keep the selected detail view confidence in sync immediately after each feedback response.
- Imported-memory image resize persistence is hardened by storing image `width`/`height` as explicit TipTap image attributes during markdown parse/render, preventing resized inline images from reverting after reopen.
- `mb_playbook` edit view now highlights `Problem`, `Impact`, and `Environment` headings with stronger color + underline styling for faster scanability.
- Root-cause fix for failed edits in local/dev mode: memory updates now skip invalid placeholder reviewer IDs (for example `00000000-0000-0000-0000-000000000000`) and only set `reviewed_by` when the reviewer exists in `auth.users`, preventing FK failures that previously blocked image-resize persistence.
- `mb_playbook` emphasis now supports both Markdown headings and label-style paragraph lines (`Problem:`, `Impact:`, `Environment:`), since imported content can use either format.
- `mb_playbook` edit highlighting now includes a content-shape fallback (when metadata tags/source are missing) and stronger CSS specificity, so section emphasis remains visible after metadata-only edits.
- Inline image resize interaction now has guarded pointer lifecycle cleanup (`pointerup`/`pointercancel`/window `blur` + capture release) to prevent stuck drag listeners that could freeze modal interactions after resizing.

## Build, Test, and Development Commands

### Tooling Requirements
- **Node.js 18+** with pnpm 10 (`frontend/pnpm-workspace.yaml`)
- **Python 3.11** (`runtime.txt`)
- **Redis** for Celery background tasks

### Frontend Commands
```bash
cd frontend/

# Install dependencies
pnpm install

# Development
pnpm dev                    # Start dev server (port 3000)

# Quality checks
pnpm lint                   # ESLint with TypeScript rules
pnpm typecheck              # TypeScript strict mode check
npx prettier --check .      # Format verification

# Testing
pnpm test                   # Vitest + Testing Library
pnpm test -- --watch        # Watch mode for TDD
pnpm test:security          # Security validation tests
pnpm test -- --coverage     # Coverage report

# Build
pnpm verify:env             # Verify required env vars
pnpm build                  # Production build
pnpm start                  # Production preview
```

### Backend Commands
```bash
# Virtual environment setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Quality checks
ruff check .                # Fast linting (replaces Flake8)
ruff format --check .       # Format verification
black --check .             # Alternative formatter check
mypy app/                   # Static type checking

# Testing
pytest -q                   # Quick test run
pytest -v                   # Verbose output
pytest --cov=app            # With coverage
pytest -k "test_name" -v    # Specific test by name
pytest app/tests/test_specific.py -v  # Specific file

# Celery worker
celery -A app.feedme.celery_app worker --loglevel=info
```

### Full System Commands
```bash
./scripts/start_on_macos/start_system.sh   # Start all services
./scripts/start_on_macos/stop_system.sh    # Stop all services
```

## Deployment (Railway)

- **Railpack builder required**: backend uses `railway.json` with `"builder": "RAILPACK"` and `"dockerfilePath": null`.
- **Frontend** uses its own `frontend/railway.toml` with `builder = "RAILPACK"`.
- **feedme-worker** uses `railway.worker.json` (Railpack builder + Celery start command).
- Railpack build configuration lives in `railpack.json` (APT packages + runtime pins).
- Keep `docker/containerfile.dev` for local builds only; do not place a `Dockerfile` at repo root.
- Do not switch Railway builds to Dockerfile or Nixpacks unless explicitly requested.

### Railway Troubleshooting

- **Railway is “building an image” / using Docker unexpectedly**
  - Railway auto-detects a root `Dockerfile` and will prefer Docker builds; keep this repo root free of `Dockerfile`/`Containerfile`.
  - Ensure the service is configured to use `railway.json`/`railway.worker.json` and that the manifest shows `build.builder = RAILPACK` and `build.dockerfilePath = null`.
  - Check for sticky Railway UI overrides (Dockerfile path/build command) that can override config-as-code.
  - Useful checks: `railway status`, `railway deployment list --json | jq '.[0].meta.serviceManifest.build'`, `railway logs --build <deployment_id>`.

- **Runtime error: `uvicorn: not found` / `celery: not found`**
  - Under Railpack, dependencies install into `/app/.venv`; start commands must either activate the venv or run via `python -m …`.
  - `scripts/railway-entrypoint.sh` prepends `.venv/bin` to `PATH` and runs `python -m uvicorn` / `python -m celery` so binaries are always resolvable.

- **Worker health checks failing**
  - Worker services don’t expose HTTP by default; `scripts/railway-entrypoint.sh` starts a tiny `/health` server so Railway checks pass.
  - Keep `healthcheckPath = "/health"` in `railway.worker.json`.

## Coding Style & Conventions

### TypeScript (Frontend)

#### Type Safety (Strict Mode Required)
- **Enable strict mode** in `tsconfig.json`: `"strict": true`
- **Avoid `any` type** - use `unknown` with type guards or union types instead
- **Leverage generics** for reusable, type-safe functions and hooks
- **Use utility types**: `Partial<T>`, `Pick<T, K>`, `Omit<T, K>`, `Record<K, V>`
- **Mark immutable data** with `readonly` modifier
- **Use `never`** for exhaustive switch statements

```typescript
// Good: Precise types with generics
function useFetch<T>(url: string): { data: T | null; loading: boolean } { ... }

// Good: Utility types for derived types
type UserSummary = Pick<User, 'id' | 'email' | 'name'>;

// Avoid: any type
function process(data: any) { ... }  // Bad
function process(data: unknown) { ... }  // Better - requires type narrowing
```

#### Naming Conventions
- **PascalCase**: Components, types, interfaces, classes (`UserProfile`, `ChatMessage`)
- **camelCase**: Variables, functions, hooks, selectors (`getUserById`, `useChat`)
- **kebab-case**: Folder names, file names (`chat-container/`, `use-auth.ts`)
- **SCREAMING_SNAKE_CASE**: Constants (`MAX_RETRY_COUNT`, `API_BASE_URL`)

#### Component Architecture
- **Functional components only** with hooks for state and side effects
- **Single responsibility** - one component, one purpose
- **Composition over inheritance** - build complex UIs from simple pieces
- **Colocate related code** - component, styles, tests, types in same folder

#### Code Formatting (Automated)
- **Prettier** for formatting (2-space indent, single quotes)
- **ESLint** with `@typescript-eslint` for linting
- Configure in `.eslintrc.json`:
```json
{
  "extends": ["eslint:recommended", "plugin:@typescript-eslint/recommended", "prettier"],
  "parser": "@typescript-eslint/parser",
  "plugins": ["@typescript-eslint"]
}
```

### Python (Backend)

#### Style & Formatting
- **PEP 8** compliance with 88-character line limit (Black default)
- **Black** for auto-formatting: `black .`
- **Ruff** for fast linting: `ruff check . --fix`
- **4-space indentation** (never tabs)

```toml
# pyproject.toml
[tool.ruff]
select = ["E", "F", "I", "B", "ANN"]  # Errors, Pyflakes, isort, Bugbear, Annotations
line-length = 88
extend-ignore = ["E203"]  # Black compatibility

[tool.black]
line-length = 88
target-version = ["py311"]
```

#### Type Annotations (Required for New Code)
- **Annotate all function signatures** with parameter and return types
- **Use modern syntax** (Python 3.10+): `list[int]` not `List[int]`
- **Use `Optional[T]` or `T | None`** for nullable values
- **Run mypy** in CI: `mypy app/ --strict`

```python
# Good: Fully typed function
def get_user_by_id(user_id: str, include_profile: bool = False) -> User | None:
    ...

# Good: Generic type for reusable functions
from typing import TypeVar, Sequence

T = TypeVar('T')
def first_or_none(items: Sequence[T]) -> T | None:
    return items[0] if items else None
```

#### Naming Conventions
- **snake_case**: Functions, variables, modules (`get_user`, `user_service.py`)
- **PascalCase**: Classes, type aliases (`UserService`, `ChatMessage`)
- **SCREAMING_SNAKE_CASE**: Constants (`MAX_CONNECTIONS`, `DEFAULT_TIMEOUT`)

#### FastAPI Patterns
- **APIRouter per domain** - group related endpoints
- **Pydantic schemas** for request/response validation
- **Dependency injection** for DB sessions, auth, config
- **Service layer** for business logic (separate from routes)

```python
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

## Testing Guidelines

### Frontend (Vitest + Testing Library)

#### Test Organization
- Colocate tests with source: `Component.tsx` → `Component.test.tsx`
- Or use `__tests__/` subfolder within feature directories
- Name test files `*.test.ts` or `*.test.tsx`

#### Testing Principles
- **Test behavior, not implementation** - query by role, text, label
- **Use `userEvent`** for realistic interaction simulation
- **Mock at boundaries** - API calls, not internal functions
- **Keep tests isolated** - no shared state between tests

```typescript
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ChatInput } from './ChatInput';

describe('ChatInput', () => {
  it('submits message on enter key', async () => {
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} />);

    const input = screen.getByRole('textbox');
    await userEvent.type(input, 'Hello world{enter}');

    expect(onSubmit).toHaveBeenCalledWith('Hello world');
  });
});
```

#### What to Test
- User interactions and their effects
- Component rendering with different props
- Error states and edge cases
- Hooks and state management logic
- Accessibility (queries by role)

### Backend (Pytest)

#### Test Organization
- Mirror source structure: `app/services/user.py` → `tests/services/test_user.py`
- Share fixtures in `tests/conftest.py`
- Name test files `test_*.py` and functions `test_*`

#### Fixtures for Setup/Teardown
```python
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from app.main import app

@pytest.fixture
def client():
    """Sync test client for FastAPI."""
    with TestClient(app) as c:
        yield c

@pytest.fixture
async def async_client():
    """Async test client for async endpoints."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def db_session():
    """Database session with transaction rollback."""
    # Setup: create transaction
    session = get_test_session()
    yield session
    # Teardown: rollback
    session.rollback()
```

#### Async Tests
```python
import pytest

@pytest.mark.asyncio
async def test_create_item(async_client):
    response = await async_client.post("/items/", json={"name": "Test"})
    assert response.status_code == 200
    assert response.json()["name"] == "Test"
```

#### Testing Patterns
- **Unit tests** for service functions (bypass HTTP)
- **Integration tests** for API endpoints (via TestClient)
- **Use `pytest.mark.parametrize`** for multiple test cases
- **Override dependencies** in tests with `app.dependency_overrides`

## Security & Configuration

### Environment Variables
- **Never commit secrets** - use `.env.local` (frontend) and `.env` (backend)
- **Validate on startup** - fail fast if required vars missing
- **Use Pydantic BaseSettings** for backend config

```python
# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    GOOGLE_API_KEY: str
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str

    class Config:
        env_file = ".env"

settings = Settings()
```

### Required Environment Variables
| Variable | Description | Required By |
|----------|-------------|-------------|
| `SUPABASE_URL` | Supabase project URL | Backend |
| `SUPABASE_ANON_KEY` | Supabase anonymous key | Backend |
| `GOOGLE_API_KEY` | Gemini API key | Backend |
| `TAVILY_API_KEY` | Web search API | Backend |
| `ENABLE_MEMORY_UI_RETRIEVAL` | Enable Memory UI retrieval | Backend |
| `MEMORY_UI_AGENT_ID` | Agent ID for Memory UI | Backend |
| `MEMORY_UI_TENANT_ID` | Tenant ID for Memory UI | Backend |
| `NEXT_PUBLIC_API_URL` | Backend API URL | Frontend |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase URL | Frontend |
| `ZENDESK_DRY_RUN` | Skip real Zendesk note posting when `true` | Backend |
| `API_KEY_ENCRYPTION_SECRET` | Encryption key for API keys (required in prod) | Backend |

### Security Checklist
- [ ] No secrets in code or version control
- [ ] Input validation via Pydantic schemas
- [ ] CORS configured for allowed origins only
- [ ] Authentication required for protected endpoints
- [ ] Rate limiting on public endpoints
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (proper output encoding)

## Commit & Pull Request Guidelines

### Commit Messages
- **Short, imperative, scoped** - describe what the commit does
- **Use conventional prefixes** when helpful:
  - `feat:` New feature
  - `fix:` Bug fix
  - `refactor:` Code restructuring without behavior change
  - `docs:` Documentation only
  - `test:` Adding or fixing tests
  - `chore:` Maintenance tasks

```
# Good examples
feat: Add user authentication flow
fix: Resolve race condition in session cache
refactor: Extract shared JSON helpers to utils
test: Add integration tests for chat endpoints
```

### Pull Request Checklist
- [ ] Concise description of changes
- [ ] Linked issue/ticket (if applicable)
- [ ] Tests pass: `pnpm test`, `pytest`
- [ ] Linting passes: `pnpm lint`, `ruff check .`
- [ ] Type checking passes: `pnpm typecheck`, `mypy app/`
- [ ] Screenshots/GIFs for UI changes
- [ ] Environment/migration impacts documented
- [ ] Changes focused (avoid unrelated modifications)

## Dependency Management

### Frontend (pnpm)
- Lock file committed: `pnpm-lock.yaml`
- Use exact versions for critical deps
- Separate dev dependencies properly

### Backend (pip + requirements.txt)
- Use `pip-compile` for reproducible installs:
  ```bash
  pip-compile requirements.in -o requirements.txt
  pip install -r requirements.txt
  ```
- Or use Poetry for modern dependency management:
  ```bash
  poetry install
  poetry add <package>
  poetry lock
  ```
- Always commit lock files for reproducibility

## Code Quality Automation

### Pre-commit Hooks (Recommended)
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]

  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v3.0.0
    hooks:
      - id: prettier
        types_or: [javascript, typescript, tsx, json, yaml, markdown]
```

### CI Pipeline Checks
1. **Lint**: `pnpm lint` + `ruff check .`
2. **Format**: `prettier --check .` + `ruff format --check .`
3. **Type Check**: `pnpm typecheck` + `mypy app/`
4. **Test**: `pnpm test` + `pytest --cov=app`
5. **Build**: `pnpm build`

## Zendesk Integration Conventions

### File Organization
Zendesk integration code lives in `app/integrations/zendesk/`:
- `scheduler.py` - Ticket processing orchestration, context report persistence, attachment handling
- `client.py` - Zendesk API wrapper, attachment fetching (`public_only=True`), PII redaction
- `attachments.py` - URL scrubbing, attachment type summarization, log file detection
- `spam_guard.py` - Rate-limiting and deduplication for internal note posting

### Key Patterns

#### Attachment Handling
- Only process **public comments** — never expose private/internal data to the agent
- Fetch attachments via Zendesk API (signed URLs expire); do not embed raw URLs in agent output
- Scrub all Zendesk attachment URLs from generated content before posting
- Summarize attachment types for the agent context instead of passing raw file data

#### Memory & Retrieval for Zendesk
- Zendesk runs use `use_server_memory=True` in `GraphState` for read access
- Memory UI retrieval is gated by `ENABLE_MEMORY_UI_RETRIEVAL` env var
- Zendesk runs are **read-only** for memory — they do not write new memories
- mem0 is optional; if the package is missing, only Memory UI is queried

#### Reply Formatting Rules
- Internal notes must use **"Suggested Reply only"** format
- A sanitization pass removes internal planning artifacts, scratchpad references, and raw tool output
- Replies must follow policy: proper greeting, empathetic tone, no unsupported claims
- No log requests if log attachments are already present

#### Context Report Persistence
- Every processed ticket gets a `context_report` persisted to `zendesk_pending_tickets.status_details`
- Uses JSON serialization with fallback for non-serializable values
- Reports include evidence summary, tool usage, and memory retrieval stats

#### Telemetry
- `zendesk_run_telemetry` logs tool usage, memory stats, and evidence summaries
- All telemetry is captured as LangSmith metadata (no separate metrics infrastructure)

### Testing Zendesk Changes
```bash
# Set ZENDESK_DRY_RUN=false in .env for real note posting
# Start system, then check:
# 1. zendesk_pending_tickets status in Supabase
# 2. Backend logs: grep -i zendesk system_logs/backend/backend.log
# 3. Internal notes posted to correct tickets
# 4. context_report persisted in status_details
```

## Reliability & Error Handling Patterns

### Transient Database Retries
Use `_run_supabase_query_with_retry` from `app/agents/tools/tool_executor.py` for Supabase queries that may fail transiently:
```python
# Retries 2x with backoff for patterns in _TRANSIENT_SUPABASE_ERRORS
result = await _run_supabase_query_with_retry(lambda: supabase.table("t").select("*").execute())
```

### Web Tool Fallback Chain
- Primary: Tavily for web search
- Fallback: Minimax when Tavily quota is exhausted
- Firecrawl: For URL-specific content extraction
- All web tools have retry configuration for transient failures

### Retrieval Bounds Clamping
Always clamp `max_results_per_source` to stay within tool validation limits. The scheduler enforces this before passing to `db_unified_search`.

### Serialization Safety
When persisting JSON to Supabase JSONB columns, wrap with try/except for `TypeError` (non-serializable values) and fall back to a simplified representation.

## Memory UI Frontend Conventions

### Zendesk Import Flow
- The "Import Knowledge" button in `MemoryClient.tsx` triggers `importZendeskTagged` via the `useImportZendeskTagged` hook
- Backend endpoint: `POST /api/v1/memory/import/zendesk-tagged`
- Imported tickets get `review_status='pending_review'` in the `memories_new` table
- Toast notifications for success/error feedback

### Authenticated Image Rendering
- `MemoryMarkdown.tsx` uses a custom `img` component that routes through the backend asset proxy
- Asset proxy endpoint: `GET /api/v1/memory/assets/{bucket}/{object_path}`
- This avoids exposing signed Supabase storage URLs to the browser

### TypeScript Types
Zendesk import types are in `frontend/src/features/memory/types/index.ts`:
- `ImportZendeskTaggedRequest` - Request payload with ticket IDs and options
- `ImportZendeskTaggedResponse` - Response with import status and counts

## Architecture Principles

### Code Reuse
- **DRY** - Don't Repeat Yourself, but don't abstract too early
- **Rule of Three** - Abstract only after seeing pattern three times
- **Composition** - Build complex from simple, reusable pieces
- **Shared types** - Define common interfaces in one place

### Separation of Concerns
- **Presentation** - UI components render data
- **Business Logic** - Services/hooks process data
- **Data Access** - API clients/DB queries fetch data
- **Configuration** - Centralized settings and constants

### Scalability Patterns
- **Feature-based structure** - Group by domain, not file type
- **Lazy loading** - Dynamic imports for large components
- **Domain state** - Separate stores per feature area
- **Module boundaries** - Enforce import restrictions
