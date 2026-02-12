# CLAUDE.md

Project guidance for Claude Code in this repository.
Last updated: 2026-02-12

## Mission

Ship reliable product changes while keeping repository documentation current enough that the next agent can execute with minimal rediscovery.

This file is intentionally concise. `AGENTS.md` is the map; `docs/` is the system of record.

## Start Here Every Run

Before writing code, bootstrap in this order:

1. Read `AGENTS.md` for current structure, canonical doc paths, and task routing.
2. Read relevant domain docs in `docs/`.
3. For external APIs/libraries, verify with Ref MCP (`ref_search_documentation`, then `ref_read_url`).
4. Validate assumptions in code with targeted `rg` + focused file reads.
5. Implement changes.

After implementation in the same run:

1. Update affected docs in `docs/`.
2. Update `AGENTS.md` if map/index/workflow changed.
3. Update this file if runtime/ops guidance changed.
4. Run docs maintenance checks:
   - `python scripts/refresh_ref_docs.py` (if deps/models changed)
   - `python scripts/validate_docs_consistency.py`

Priority rule: if docs and code diverge, fix docs in the same run.

## Ref-First External Docs Protocol

Ref MCP is the primary source for external framework/library API verification.

Use Ref by default for fast-moving dependencies:

- LangGraph / LangChain / provider integrations
- AG-UI protocol
- Next.js / React
- Supabase / pgvector / vecs
- TipTap / react-three-fiber / drei / Motion

If Ref coverage is missing or partial:

1. Use official vendor docs directly.
2. Validate against local code usage.
3. Record the gap in `docs/ref-gaps.md` if persistent.

Budget guardrails:

- Prefer event-driven lookups during active implementation.
- Use biweekly verification cadence, not frequent broad sweeps.
- Target docs-maintenance spend: ~150-250 credits/month.

Reference docs:

- `docs/ref-source-registry.md`
- `docs/ref-gaps.md`
- `docs/ref-index-plan.md`
- `docs/dependency-watchlist.md`
- `docs/model-catalog.md`

## Project Snapshot

Agent Sparrow is a multi-agent system with:

- Backend: FastAPI + LangGraph + DeepAgents patterns
- Frontend: Next.js 16 + React 19 + TypeScript
- Data platform: Supabase (Postgres, Auth, Storage) + pgvector
- Streaming: Native AG-UI protocol over SSE
- Background jobs: Celery + Redis

Canonical architecture docs:

- `docs/backend-architecture.md`
- `docs/backend-runtime-reference.md`
- `docs/frontend-architecture.md`
- `docs/frontend-reference.md`
- `docs/database-schema.md`
- `docs/database-schema-reference.md`
- `docs/observability.md`

Domain docs:

- `docs/zendesk.md`
- `docs/zendesk-operations.md`
- `docs/memory-ui.md`
- `docs/memory-ui-reference.md`
- `docs/feedme-hardening-notes.md`

## Repository Layout (High Signal)

- `app/` backend services, agents, API endpoints, integrations
- `frontend/src/` UI routes, feature modules, shared components, services
- `app/core/config/models.yaml` single source of model configuration truth
- `docs/` canonical documentation system
- `scripts/` automation, startup, migrations, doc validators

For full map and routing table, always use `AGENTS.md`.

## Runtime Commands

### Full System

```bash
./scripts/start_on_macos/start_system.sh
./scripts/start_on_macos/stop_system.sh
```

### Backend

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
ruff check .
pytest -q
```

### Frontend

```bash
cd frontend/
pnpm install
pnpm dev
pnpm lint
pnpm typecheck
```

### Docs Maintenance

```bash
python scripts/refresh_ref_docs.py
python scripts/validate_docs_consistency.py
```

## Environment (Required)

Minimum expected env groups:

- LLM/API: `GEMINI_API_KEY` (plus optional provider-specific keys)
- Supabase: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`
- Auth/security: `SUPABASE_JWT_SECRET`, production auth toggles
- Search/tools as used: `TAVILY_API_KEY`, Firecrawl and related keys
- Infra: Redis URLs for Celery/rate limiting

Use `docs/SECURITY.md` and `docs/DEVELOPMENT.md` for exact expectations and production guardrails.

## Architecture Contracts to Preserve

1. AG-UI protocol is the primary streaming contract (`/api/v1/agui/stream`).
2. `models.yaml` is the model registry source of truth; avoid hardcoding model behavior in docs or code comments.
3. Supabase is the primary data/auth/storage platform.
4. Feature-based frontend organization should remain intact (`frontend/src/features/`).
5. Major backend logic should stay in service/agent layers rather than endpoint handlers.

## Model Configuration Rules

Model behavior, defaults, rate limits, and role assignments are defined in:

- `app/core/config/models.yaml`

When changing models:

1. Update `models.yaml`.
2. Regenerate derived docs: `python scripts/refresh_ref_docs.py`.
3. Confirm docs consistency: `python scripts/validate_docs_consistency.py`.
4. Update architecture docs if behavior/contracts changed.

## Quality Gates

For meaningful changes, run as relevant:

- Backend: `ruff check .`, `pytest -q`
- Frontend: `pnpm lint`, `pnpm typecheck`
- Docs: `python scripts/refresh_ref_docs.py`, `python scripts/validate_docs_consistency.py`

CI/pre-commit also enforce docs maintenance:

- `.github/workflows/docs-consistency.yml`
- `.github/workflows/docs-maintenance.yml`
- `.pre-commit-config.yaml`

## Documentation as Top Priority

Agents should treat documentation updates as part of done criteria, not optional cleanup.

Before any future run, agents should:

1. Bootstrap from `AGENTS.md`.
2. Read task-relevant docs from `docs/`.
3. Verify external APIs with Ref.
4. Then move to code exploration and implementation.

This keeps autonomous coding quality high and reduces repeated onboarding work between sessions.

## Quick Troubleshooting

- API route/path docs drift: run `python scripts/validate_docs_consistency.py`.
- Dependency/model drift in docs: run `python scripts/refresh_ref_docs.py`.
- Missing external API clarity: use Ref first, then official vendor docs.
- Deployment/runtime drift: check `docs/DEVELOPMENT.md` and `docs/SECURITY.md`.

## Canonical References

- Map/index: `AGENTS.md`
- Principles: `docs/core-beliefs.md`
- Standards: `docs/CODING_STANDARDS.md`, `docs/TESTING.md`, `docs/SECURITY.md`, `docs/RELIABILITY.md`
- Architecture: `docs/backend-architecture.md`, `docs/backend-runtime-reference.md`, `docs/frontend-architecture.md`, `docs/frontend-reference.md`, `docs/database-schema.md`, `docs/database-schema-reference.md`, `docs/observability.md`
- Domains: `docs/zendesk.md`, `docs/zendesk-operations.md`, `docs/memory-ui.md`, `docs/memory-ui-reference.md`, `docs/feedme-hardening-notes.md`
- Operations: `docs/DEVELOPMENT.md`, `docs/CONTRIBUTING.md`, `docs/QUALITY_SCORE.md`, `docs/work-ledger/sessions.md`
