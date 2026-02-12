# Coding Standards

Last updated: 2026-02-12

---

## TypeScript (Frontend)

### Type Safety (Strict Mode Required)

- **Enable strict mode** in `tsconfig.json`: `"strict": true`
- **Avoid `any` type** — use `unknown` with type guards or union types instead
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
function process(data: unknown) { ... }  // Better — requires type narrowing
```

### Naming Conventions

- **PascalCase**: Components, types, interfaces, classes (`UserProfile`, `ChatMessage`)
- **camelCase**: Variables, functions, hooks, selectors (`getUserById`, `useChat`)
- **kebab-case**: Folder names, file names (`chat-container/`, `use-auth.ts`)
- **SCREAMING_SNAKE_CASE**: Constants (`MAX_RETRY_COUNT`, `API_BASE_URL`)

### Component Architecture

- **Functional components only** with hooks for state and side effects
- **Single responsibility** — one component, one purpose
- **Composition over inheritance** — build complex UIs from simple pieces
- **Colocate related code** — component, styles, tests, types in same folder

### Code Formatting (Automated)

- **Prettier** for formatting (2-space indent, single quotes)
- **ESLint** with the Next.js flat-config setup
- Configure in `eslint.config.mjs`:

```javascript
// eslint.config.mjs
import { defineConfig } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";

export default defineConfig([...nextVitals]);
```

---

## Python (Backend)

### Style & Formatting

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

### Type Annotations (Required for New Code)

- **Annotate all function signatures** with parameter and return types
- **Use modern syntax** (Python 3.11+): `list[int]` not `List[int]`
- **Use `Optional[T]` or `T | None`** for nullable values
- **Run mypy** in CI: `mypy app/ --strict`

```toml
# pyproject.toml — mypy configuration
[tool.mypy]
python_version = "3.11"
strict = true
disallow_untyped_defs = true
warn_return_any = true
```

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

### Naming Conventions

- **snake_case**: Functions, variables, modules (`get_user`, `user_service.py`)
- **PascalCase**: Classes, type aliases (`UserService`, `ChatMessage`)
- **SCREAMING_SNAKE_CASE**: Constants (`MAX_CONNECTIONS`, `DEFAULT_TIMEOUT`)

### FastAPI Patterns

- **APIRouter per domain** — group related endpoints
- **Pydantic schemas** for request/response validation
- **Dependency injection** for DB sessions, auth, config
- **Service layer** for business logic (separate from routes)
- **Use `BaseSettings`** for configuration management (see `app/core/settings.py`)

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

---

## Architecture Principles

### Code Reuse

- **DRY** — Don't Repeat Yourself, but don't abstract too early
- **Rule of Three** — Abstract only after seeing pattern three times
- **Composition** — Build complex from simple, reusable pieces
- **Shared types** — Define common interfaces in one place

### Separation of Concerns

- **Presentation** — UI components render data
- **Business Logic** — Services/hooks process data
- **Data Access** — API clients/DB queries fetch data
- **Configuration** — Centralized settings and constants

### Scalability Patterns

- **Feature-based structure** — Group by domain, not file type
- **Lazy loading** — Dynamic imports for large components
- **Domain state** — Separate stores per feature area
- **Module boundaries** — Enforce import restrictions
