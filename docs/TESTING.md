# Testing Guidelines

Last updated: 2026-02-12

---

## Frontend (Vitest + Testing Library)

### Test Organization

- Colocate tests with source: `Component.tsx` -> `Component.test.tsx`
- Or use `__tests__/` subfolder within feature directories
- Name test files `*.test.ts` or `*.test.tsx`

### Testing Principles

- **Test behavior, not implementation** — query by role, text, label
- **Use `userEvent`** for realistic interaction simulation
- **Mock at boundaries** — API calls, not internal functions
- **Keep tests isolated** — no shared state between tests

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

### What to Test

- User interactions and their effects
- Component rendering with different props
- Error states and edge cases
- Hooks and state management logic
- Accessibility (queries by role)

---

## Backend (Pytest)

### Test Organization

- Mirror source structure where practical: `app/api/v1/endpoints/feedme/analytics.py` -> `tests/backend/test_feedme_release_hardening.py`
- Share fixtures in `tests/conftest.py`
- Name test files `test_*.py` and functions `test_*`

### Fixtures for Setup/Teardown

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
    session = get_test_session()
    yield session
    session.rollback()
```

### Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_create_item(async_client):
    response = await async_client.post("/items/", json={"name": "Test"})
    assert response.status_code == 200
    assert response.json()["name"] == "Test"
```

### Testing Patterns

- **Unit tests** for service functions (bypass HTTP)
- **Integration tests** for API endpoints (via TestClient)
- **Use `pytest.mark.parametrize`** for multiple test cases
- **Override dependencies** in tests with `app.dependency_overrides`

---

## Commands

```bash
# Frontend
cd frontend/
pnpm test                   # Run all tests
pnpm test -- --watch        # Watch mode
pnpm test:security          # Security validation
pnpm test:security:full     # Security with rate limiting tests
pnpm test -- --coverage     # Coverage report

# Backend
pytest -q                   # Quick run
pytest -v                   # Verbose
pytest --cov=app            # With coverage
pytest -k "test_name" -v    # By name
```

See also: [`docs/QUALITY_SCORE.md`](QUALITY_SCORE.md) for test coverage grades per domain.
