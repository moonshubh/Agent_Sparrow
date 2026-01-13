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
