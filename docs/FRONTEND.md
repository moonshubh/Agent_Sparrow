# FRONTEND

Last updated: 2026-02-23

## Purpose

Canonical frontend architecture and UI/API contract map.

## Directory Contracts

- App routes: `frontend/src/app/`
- Domain features: `frontend/src/features/`
- Shared components/utilities: `frontend/src/shared/`
- API/service clients: `frontend/src/services/`
- Domain state stores: `frontend/src/state/`

## Primary Route Surfaces

| Route | Purpose | Core files |
|---|---|---|
| `/` and app shells | Main application entry and layout orchestration | `frontend/src/app/` |
| `/feedme` | FeedMe dashboard (dock, upload/folders/unassigned/stats flows) | `frontend/src/app/feedme/page.tsx` |
| `/feedme/conversation/[id]` | Two-panel conversation workspace with note/edit/version controls | `frontend/src/app/feedme/conversation/[id]/page.tsx` |
| `/memory` | Memory graph/table, admin controls, import/export flows | `frontend/src/app/memory/page.tsx`, `frontend/src/features/memory/components/MemoryClient.tsx` |

## FeedMe Frontend Contract

- Canonical API client: `frontend/src/features/feedme/services/feedme-api.ts`
- Health monitor integration: `frontend/src/services/monitoring/backend-health-check.ts`
- Stats polling/data shaping: `frontend/src/features/feedme/hooks/use-stats-data.ts`

Verified backend routes actively used by FeedMe frontend include:

- `/api/v1/feedme/conversations`
- `/api/v1/feedme/conversations/upload`
- `/api/v1/feedme/conversations/{conversation_id}`
- `/api/v1/feedme/conversations/{conversation_id}/status`
- `/api/v1/feedme/conversations/{conversation_id}/mark-ready`
- `/api/v1/feedme/conversations/{conversation_id}/ai-note/regenerate`
- `/api/v1/feedme/conversations/{conversation_id}/versions`
- `/api/v1/feedme/conversations/{conversation_id}/versions/{version_number}`
- `/api/v1/feedme/conversations/{conversation_id}/versions/{version_1}/diff/{version_2}`
- `/api/v1/feedme/conversations/{conversation_id}/revert/{target_version}`
- `/api/v1/feedme/search/examples`
- `/api/v1/feedme/folders`
- `/api/v1/feedme/folders/assign`
- `/api/v1/feedme/folders/{folder_id}`
- `/api/v1/feedme/folders/{folder_id}/conversations`
- `/api/v1/feedme/stats/overview`
- `/api/v1/feedme/settings`
- `/api/v1/feedme/health`

## Memory Frontend Contract

- Canonical API and fallback logic: `frontend/src/features/memory/lib/api.ts`
- Data hooks: `frontend/src/features/memory/hooks/useMemoryData.ts`
- Graph/table orchestration: `frontend/src/features/memory/components/MemoryClient.tsx`

Important behavior:

- Graph polling default is 60 seconds (`TIMING.GRAPH_POLL_INTERVAL_MS = 60000`).
- Read fallback to Supabase is intentional for selected flows.
- Admin write/mutation operations go through backend APIs.

## Frontend Invariants

- Strict TypeScript usage; avoid `any`.
- Keep feature modules cohesive and colocated.
- Preserve AG-UI event/stream compatibility.
- Keep frontend contracts aligned with backend route/schema contracts.

## Related Docs

- `docs/DESIGN.md`
- `docs/product-specs/feedme-hardening-notes.md`
- `docs/product-specs/memory-ui.md`
- `docs/SECURITY.md`
- `docs/RELIABILITY.md`
