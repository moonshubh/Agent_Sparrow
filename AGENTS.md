# Agent Sparrow — Repository Guide

Last updated: 2026-02-12

> This file is a **map**, not an encyclopedia. It points to deeper sources of truth.
> See [docs/core-beliefs.md](docs/core-beliefs.md) for operating principles.

---

## Quick Start

```bash
# Full system
./scripts/start_on_macos/start_system.sh    # Start all services
./scripts/start_on_macos/stop_system.sh     # Stop all services

# Frontend (port 3000)
cd frontend/ && pnpm install && pnpm dev

# Backend (port 8000)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Quality checks
cd frontend/ && pnpm lint && pnpm typecheck  # Frontend
ruff check . && pytest -q                     # Backend
python scripts/refresh_ref_docs.py            # Regenerate docs artifacts
python scripts/validate_docs_consistency.py   # Documentation consistency
```

---

## Agent Bootstrap Protocol (Docs First)

Before touching code, agents should bootstrap from docs in this exact order:

1. Read `AGENTS.md` (this map) for current structure and canonical doc paths.
2. Read domain docs from the routing table below.
3. Verify external library APIs with Ref (`ref_search_documentation`, then `ref_read_url`) for fast-moving dependencies.
4. Validate assumptions in code with targeted `rg` + file reads.
5. Implement changes.
6. Update docs in the same run if behavior/architecture/contracts changed.

### Task-to-Doc Routing

| If the task is about... | Read first | Then inspect code under... |
|-------------------------|------------|-----------------------------|
| Backend core architecture, orchestration, models | `docs/backend-architecture.md` | `app/agents/`, `app/core/` |
| Backend APIs/config/services/runtime | `docs/backend-runtime-reference.md` | `app/api/`, `app/services/`, `app/core/`, `app/feedme/` |
| Frontend architecture, AG-UI protocol, directory strategy | `docs/frontend-architecture.md` | `frontend/src/app/`, `frontend/src/services/ag-ui/` |
| Frontend feature implementation, state, services, patterns | `docs/frontend-reference.md` | `frontend/src/features/`, `frontend/src/services/`, `frontend/src/state/` |
| Zendesk pipeline and context engineering | `docs/zendesk.md` | `app/integrations/zendesk/`, `app/api/v1/endpoints/` |
| Zendesk config, runbooks, operations | `docs/zendesk-operations.md` | `app/integrations/zendesk/`, `scripts/` |
| Memory UI core architecture + APIs | `docs/memory-ui.md` | `app/memory/`, `app/api/v1/endpoints/memory/` |
| Memory UI frontend/reliability/security details | `docs/memory-ui-reference.md` | `frontend/src/features/memory/`, `app/memory/` |
| FeedMe processing + reliability | `docs/feedme-hardening-notes.md`, `docs/backend-runtime-reference.md` | `app/feedme/`, `app/api/v1/endpoints/feedme/`, `frontend/src/features/feedme/` |
| Data schema overview | `docs/database-schema.md` | `app/db/`, `app/db/migrations/` |
| Data table-level details / RLS / functions | `docs/database-schema-reference.md` | `app/db/`, `app/db/migrations/` |
| Tracing/monitoring incidents | `docs/observability.md` | `app/core/tracing/`, `app/agents/` |
| External library APIs / SDK usage | `docs/ref-source-registry.md`, `docs/ref-gaps.md` | `requirements.txt`, `frontend/package.json`, `app/core/config/models.yaml` |

---

## Repository Map

```
AGENTS.md                   ← You are here (map / table of contents)
CLAUDE.md                   ← Detailed project context for Claude Code

frontend/                   ← Next.js 16 / TypeScript / App Router
  src/app/                    Routes and layouts
  src/features/               Domain modules: auth, feedme, librechat, memory, settings, zendesk
  src/shared/                 Reusable UI primitives
  src/services/               API clients, Supabase integration
  src/state/                  Zustand stores by domain

app/                        ← FastAPI / Python 3.11 backend
  main.py                    Entrypoint, CORS, routers
  agents/                    Unified agent, orchestration, harness, subagents
  api/v1/endpoints/          Routes by domain (chat, feedme, memory, zendesk)
  core/                      Config (models.yaml), tracing, rate limiting
  db/                        Supabase client, models, migrations
  integrations/              Zendesk, AG-UI
  memory/                    Memory UI service, search, feedback
  feedme/                    Document processing, Celery tasks
  services/                  Business logic layer

docs/                       ← System of record (see index below)
tests/                      ← Pytest suites by domain
scripts/                    ← Automation, deployment, startup
```

---

## Documentation Index

### Principles & Standards
| Document | Path | Purpose |
|----------|------|---------|
| **Core Beliefs** | [`docs/core-beliefs.md`](docs/core-beliefs.md) | Agent-first operating principles |
| **Coding Standards** | [`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md) | TypeScript + Python conventions, naming, patterns |
| **Testing Guide** | [`docs/TESTING.md`](docs/TESTING.md) | Vitest, Pytest, fixtures, what to test |
| **Security** | [`docs/SECURITY.md`](docs/SECURITY.md) | Env vars, auth patterns, security checklist |
| **Contributing** | [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) | Commits, PRs, branch naming, release workflow |
| **Reliability** | [`docs/RELIABILITY.md`](docs/RELIABILITY.md) | Retries, fallbacks, error handling patterns |

### Architecture & Design
| Document | Path | Purpose |
|----------|------|---------|
| **Backend Architecture** | [`docs/backend-architecture.md`](docs/backend-architecture.md) | Core system design, agents, middleware, model config |
| **Backend Runtime Reference** | [`docs/backend-runtime-reference.md`](docs/backend-runtime-reference.md) | FeedMe pipeline, API/config/services/rate limiting reference |
| **Frontend Architecture** | [`docs/frontend-architecture.md`](docs/frontend-architecture.md) | Next.js 16, AG-UI protocol, directory strategy |
| **Frontend Reference** | [`docs/frontend-reference.md`](docs/frontend-reference.md) | Feature modules, state, services, routing, implementation patterns |
| **Database Schema** | [`docs/database-schema.md`](docs/database-schema.md) | Database overview, schemas/extensions, table-family map |
| **Database Schema Reference** | [`docs/database-schema-reference.md`](docs/database-schema-reference.md) | Full table definitions, vector search, RLS, functions, migration history |
| **Observability** | [`docs/observability.md`](docs/observability.md) | LangSmith tracing, monitoring playbooks |

### Domain-Specific
| Document | Path | Purpose |
|----------|------|---------|
| **Zendesk Integration** | [`docs/zendesk.md`](docs/zendesk.md) | Pipeline, context engineering, playbook, formatting |
| **Zendesk Operations** | [`docs/zendesk-operations.md`](docs/zendesk-operations.md) | Env config, runbooks, troubleshooting, coding conventions |
| **Memory UI** | [`docs/memory-ui.md`](docs/memory-ui.md) | Core architecture, schema, API overview |
| **Memory UI Reference** | [`docs/memory-ui-reference.md`](docs/memory-ui-reference.md) | Entity extraction, confidence, duplicates, frontend, reliability, security |
| **FeedMe Hardening** | [`docs/feedme-hardening-notes.md`](docs/feedme-hardening-notes.md) | Schema, auth, upload, reliability fixes |

### Operations & Planning
| Document | Path | Purpose |
|----------|------|---------|
| **Quality Scores** | [`docs/QUALITY_SCORE.md`](docs/QUALITY_SCORE.md) | Domain grading and gap tracking |
| **Tech Debt** | [`docs/exec-plans/tech-debt-tracker.md`](docs/exec-plans/tech-debt-tracker.md) | Known debt, paydown cadence |
| **Exec Plans** | [`docs/exec-plans/`](docs/exec-plans/) | Active plans, completed, debt |
| **Development Guide** | [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | Build commands, Railway deployment, debugging tips |
| **Docs Guide** | [`docs/README.md`](docs/README.md) | How to navigate architecture vs runtime docs quickly |
| **Ref Source Registry** | [`docs/ref-source-registry.md`](docs/ref-source-registry.md) | External docs policy, tiers, and budget guardrails |
| **Ref Gaps** | [`docs/ref-gaps.md`](docs/ref-gaps.md) | Missing Ref coverage and fallback protocol |
| **Ref Index Plan** | [`docs/ref-index-plan.md`](docs/ref-index-plan.md) | Practical indexing checklist |
| **Model Catalog** | [`docs/model-catalog.md`](docs/model-catalog.md) | Generated model inventory from `models.yaml` |
| **Dependency Watchlist** | [`docs/dependency-watchlist.md`](docs/dependency-watchlist.md) | Generated high-drift dependency tracking |
| **Work Ledger** | [`docs/work-ledger/sessions.md`](docs/work-ledger/sessions.md) | Session-by-session changelog |

---

## Key Architectural Decisions

| Decision | Rationale | Reference |
|----------|-----------|-----------|
| AG-UI protocol for streaming | Native SSE, no GraphQL translation needed | `docs/backend-architecture.md` |
| LangGraph v1 for orchestration | Checkpointing, subgraph support, state management | `app/agents/orchestration/` |
| Supabase for everything | Auth, DB, vectors, storage — single platform | `docs/database-schema.md` |
| models.yaml as single source | All model config in one validated YAML | `app/core/config/models.yaml` |
| Gemini primary, Grok optional | Provider factory pattern for swappable LLMs | `app/agents/unified/provider_factory.py` |
| Feature-based frontend structure | Colocated components, hooks, types per domain | `frontend/src/features/` |
| Celery for background processing | PDF extraction, imports, async tasks | `app/feedme/celery_app.py` |

---

## Coding Standards (Summary)

**TypeScript**: Strict mode, no `any`, functional components, Prettier + ESLint.
**Python**: Type annotations required, Black + Ruff, Pydantic schemas, service layer pattern.
**Testing**: Behavior-driven (Testing Library), fixtures (Pytest), mock at boundaries.
**Security**: Never commit secrets, validate inputs, parameterized queries, CORS.

Full details: [`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md) | [`docs/TESTING.md`](docs/TESTING.md) | [`docs/SECURITY.md`](docs/SECURITY.md)

---

## Harness Engineering Workflow

Adopted from [OpenAI's harness engineering practices](https://openai.com/index/harness-engineering/).

**Operating principles**: See [`docs/core-beliefs.md`](docs/core-beliefs.md) for the full set.

### Agent Workflow Loop

```
Observe problem → Identify missing capability → Encode into repo → Agent executes → Validate → Ship
```

### Decision Capture Template

When making architectural decisions, add to `docs/design-docs/` or comment in code:
```markdown
## Decision: [Title]
**Date**: YYYY-MM-DD
**Context**: What prompted this decision
**Decision**: What we chose
**Rationale**: Why this over alternatives
**Status**: Active | Superseded by [link]
```

---

## Documentation Maintenance Protocol

Documentation is part of done criteria for every substantial change.

After each run:

1. Update relevant canonical docs in `docs/` when behavior, endpoints, schemas, workflows, or architecture changed.
2. Update `AGENTS.md` if repo map, doc index, startup commands, or architectural decision references changed.
3. Update `CLAUDE.md` if environment requirements, major architecture notes, or operational guidance changed.
4. Add/refresh a session entry in `docs/work-ledger/sessions.md` for significant work.
5. Regenerate generated docs when dependency/model config changed: `python scripts/refresh_ref_docs.py`.
6. Verify no stale references remain (especially renamed/moved docs), e.g. `python scripts/validate_docs_consistency.py`.

Ref usage and budget policy:

1. Use Ref lookups selectively for implementation-critical API verification.
2. Keep maintenance usage in a budget band of ~150-250 credits/month.
3. Prefer event-driven lookups plus biweekly verification over daily sweeps.

If docs and code disagree, prioritize fixing docs in the same run so the next agent can onboard without rediscovery.

---

## Environment

| Service | Port | Required |
|---------|------|----------|
| Backend API | 8000 | Yes |
| Frontend UI | 3000 | Yes |
| Redis | 6379 | For Celery/FeedMe |
| Celery Health | 8001 | Auto-detected |

**Required env vars**: See `CLAUDE.md` > "Required Environment Variables" for full list.
