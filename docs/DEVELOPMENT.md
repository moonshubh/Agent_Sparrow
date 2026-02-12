# Development Guide

Last updated: 2026-02-12

## Tooling Requirements

- **Node.js 20.9+** with pnpm 10 (`frontend/package.json` engines)
- **Python 3.11** (`runtime.txt`)
- **Redis** for Celery background tasks

---

## Frontend Commands

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

## Backend Commands

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
python scripts/refresh_ref_docs.py          # Regenerate docs watchlist/model catalog
python scripts/validate_docs_consistency.py  # Docs path/endpoint consistency

# Testing
pytest -q                   # Quick test run
pytest -v                   # Verbose output
pytest --cov=app            # With coverage
pytest -k "test_name" -v    # Specific test by name
pytest app/tests/test_specific.py -v  # Specific file

# Celery worker
celery -A app.feedme.celery_app worker --loglevel=info
```

## Full System Commands

```bash
./scripts/start_on_macos/start_system.sh   # Start all services
./scripts/start_on_macos/stop_system.sh    # Stop all services
```

---

## Dependency Management

### Frontend (pnpm)

- Lock file committed: `pnpm-lock.yaml`
- Use exact versions for critical deps
- Separate dev dependencies properly

### Backend (pip + requirements.txt)

- Canonical install path:
  ```bash
  pip install -r requirements.txt
  ```
- Keep `requirements.txt` and `requirements-lock.txt` aligned when dependency versions change.
- This repository currently does not maintain a committed `requirements.in`.

---

## Code Quality Automation

### Pre-commit Hooks (Recommended)

```yaml
# .pre-commit-config.yaml (project-local)
repos:
  - repo: local
    hooks:
      - id: refresh-ref-docs
        name: refresh-ref-docs
        entry: python scripts/refresh_ref_docs.py
        language: system
        pass_filenames: false
      - id: docs-consistency
        name: docs-consistency
        entry: python scripts/validate_docs_consistency.py
        language: system
        pass_filenames: false
```

Install hooks locally:

```bash
pip install pre-commit
pre-commit install
```

### CI Pipeline Checks

1. **Lint**: `pnpm lint` + `ruff check .`
2. **Format**: `prettier --check .` + `ruff format --check .`
3. **Type Check**: `pnpm typecheck` + `mypy app/`
4. **Test**: `pnpm test` + `pytest --cov=app`
5. **Build**: `pnpm build`
6. **Docs Refresh**: `python scripts/refresh_ref_docs.py`
7. **Docs Consistency**: `python scripts/validate_docs_consistency.py`

### Docs Automation Workflows

- `.github/workflows/docs-consistency.yml` runs docs consistency checks on PRs/pushes.
- `.github/workflows/docs-maintenance.yml` runs on a biweekly schedule and dependency/model/doc changes to regenerate docs artifacts and enforce alignment.

---

## Port Allocation

| Service | Port | Notes |
|---------|------|-------|
| Backend API | 8000 | FastAPI + uvicorn |
| Frontend UI | 3000 | Next.js dev server |
| Celery Health | 8001 | Auto-detects port collision |
| Redis | 6379 | Default |

---

## Railway Deployment

Production deploys to Railway with Railpack builder.

### Builder Configuration

- Backend: `railway.json` sets `"builder": "RAILPACK"`, `"dockerfilePath": null`
- Frontend: `frontend/railway.toml` with `builder = "RAILPACK"`
- FeedMe worker: `railway.worker.json` (Railpack + Celery start command)
- Railpack settings (APT packages/runtime pins): `railpack.json`
- Keep `docker/containerfile.dev` for local builds only; no root `Dockerfile` in repo

### Backend Env Vars (Railway)

**Mandatory**:
- `GEMINI_API_KEY` — Google Generative AI key
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY` — Supabase credentials
- `SUPABASE_JWT_SECRET` — JWT secret (verify tokens)
- `ALLOWED_OAUTH_EMAIL_DOMAINS` — e.g., `getmailbird.com`
- `FORCE_PRODUCTION_SECURITY` — `true`
- `ENABLE_AUTH_ENDPOINTS` — `true`
- `ENABLE_API_KEY_ENDPOINTS` — `true`
- `SKIP_AUTH` — `false`
- `ENABLE_LOCAL_AUTH_BYPASS` — `false`

**Recommended**: `CORS_ALLOW_ORIGINS`, `TAVILY_API_KEY`

### Frontend Env Vars (Railway)

- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_ENABLE_OAUTH` — `true`
- `NEXT_PUBLIC_ALLOWED_EMAIL_DOMAIN` — `getmailbird.com`
- `NEXT_PUBLIC_API_URL` — `https://<backend-domain>`
- `NEXT_PUBLIC_AUTH_REDIRECT_URL` — `https://<frontend-domain>/auth/callback`

### Deploy Commands

```bash
# Backend
railway init && railway variables set <vars...> && railway up

# Frontend
cd frontend && railway init && railway variables set <vars...> && railway up

# Validate
curl https://<backend-domain>/health
curl https://<backend-domain>/security-status
```

### Railway Troubleshooting

- **Docker builds unexpected**: Check for root `Dockerfile`/`Containerfile` and remove it (Railway auto-detection prefers Docker)
- **Confirm Railpack**: `railway deployment list --json | jq '.[0].meta.serviceManifest.build'`
- **`uvicorn: not found` / `celery: not found`**: Railpack venv (`/app/.venv`) not on PATH; use `scripts/railway-entrypoint.sh`
- **401/403 after OAuth**: Verify `SUPABASE_JWT_SECRET` matches project JWT secret; check email domain
- **OAuth redirect loop**: Check `NEXT_PUBLIC_AUTH_REDIRECT_URL` and Supabase Auth redirect URLs
- **CORS errors**: Set `CORS_ALLOW_ORIGINS` to your frontend domain
- Never set `ENABLE_LOCAL_AUTH_BYPASS` in production; keep `FORCE_PRODUCTION_SECURITY=true`

---

## Debugging Tips

### Backend Logs

```bash
tail -f system_logs/backend/backend.log       # Real-time backend logs
tail -f system_logs/celery/celery_worker.log   # Celery worker logs
```

### Frontend Debugging

- Browser DevTools Network tab for API calls
- React Developer Tools for component state
- Check `/api/v1/agui/stream` responses for streaming issues

### Common Issues

1. **Redis not running** — FeedMe features won't work
2. **Port conflicts** — Use `lsof -i :PORT` to check
3. **Missing env vars** — Verify with `frontend/scripts/verify-env.js`
4. **Gemini rate limits** — Monitor usage in FeedMe's gemini_tracker
5. **PDF processing fallback** — Check logs if OCR is being triggered unnecessarily (Gemini vision is primary)
6. **CORS errors** — Ensure backend allows frontend port (3000/3001) in `app/main.py`
7. **SSE connection issues** — Check browser console for AG-UI event errors
8. **Zendesk 404 on attachments** — Attachment URLs are signed and expire; scheduler fetches via API
9. **Zendesk context_report missing** — Check serialization in `scheduler.py`; fallbacks should catch JSON errors
10. **Memory UI retrieval silent** — Set `ENABLE_MEMORY_UI_RETRIEVAL=true` and configure `MEMORY_UI_AGENT_ID`/`MEMORY_UI_TENANT_ID`
11. **`API_KEY_ENCRYPTION_SECRET` missing** — Required in production; causes `OSError` in `app/core/encryption.py` if absent
