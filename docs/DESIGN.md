# DESIGN

Last updated: 2026-02-23

## Purpose

Canonical backend/system architecture map for agent implementation work.

## Runtime Entry

- App bootstrap: `app/main.py`
- Unified orchestration graph: `app/agents/orchestration/orchestration/graph.py`
- Shared graph state: `app/agents/orchestration/orchestration/state.py`
- AG-UI streaming bridge: `app/api/v1/endpoints/agui_endpoints.py`

## Layer Model

1. API layer
- FastAPI routers under `app/api/v1/endpoints/`
- Request/response contracts in endpoint schemas

2. Orchestration layer
- LangGraph graph compilation and execution
- Subgraph/task delegation and event streaming

3. Service layer
- Domain logic in `app/services/`, `app/memory/`, `app/feedme/`, integration modules

4. Integration/data layer
- Supabase DB/storage/auth client wrappers under `app/db/`
- Zendesk integration under `app/integrations/zendesk/`

5. Runtime infrastructure
- Settings and config in `app/core/settings.py` and `app/core/config/`
- Rate limiting, tracing, health checks, scheduler startup

## API Domain Snapshot

Verified against current `app.main` routes on 2026-02-23.

| Domain | Representative routes |
|---|---|
| AG-UI streaming | `/api/v1/agui/stream`, `/api/v1/agui/subgraphs/stream`, `/api/v1/agui/stream/health` |
| Agent research/log analysis | `/api/v1/agent/research`, `/api/v1/agent/research/stream`, `/api/v1/agent/logs`, `/api/v1/agent/logs/stream` |
| FeedMe | `/api/v1/feedme/conversations`, `/api/v1/feedme/conversations/upload`, `/api/v1/feedme/search/examples`, `/api/v1/feedme/stats/overview`, `/api/v1/feedme/settings` |
| FeedMe intelligence | `/api/v1/feedme/intelligence/summarize`, `/api/v1/feedme/intelligence/analyze-batch`, `/api/v1/feedme/intelligence/smart-search` |
| Memory UI | `/api/v1/memory/list`, `/api/v1/memory/graph`, `/api/v1/memory/search`, `/api/v1/memory/import/zendesk-tagged` |
| Zendesk integration | `/api/v1/integrations/zendesk/webhook`, `/api/v1/integrations/zendesk/health`, `/api/v1/integrations/zendesk/admin/queue` |
| Tooling/metadata | `/api/v1/tools/web-search`, `/api/v1/tools/internal-search`, `/api/v1/metadata/link-preview`, `/api/v1/metadata/memory/{session_id}/stats`, `/api/v1/metadata/quotas/status`, `/api/v1/metadata/sessions/{session_id}/traces/{trace_id}`, `/api/v1/metadata/health` |

## Architecture Invariants

- AG-UI streaming contract remains backward compatible.
- Model registry source of truth is `app/core/config/models.yaml`.
- Typed boundaries are required for external input/output.
- Security enforcement occurs at API and DB boundaries.
- Business logic should stay in service/orchestration layers, not route handlers.

## Related Docs

- `docs/FRONTEND.md`
- `docs/generated/db-schema.md`
- `docs/product-specs/index.md`
- `docs/SECURITY.md`
- `docs/RELIABILITY.md`
