# Memory UI Reference

Last updated: 2026-02-23

Companion implementation details for `docs/product-specs/memory-ui.md`.

## Current Read/Write Strategy

- Backend writes and admin actions run through `app/api/v1/endpoints/memory/endpoints.py`.
- Service logic (embedding, merge, stats, CRUD helpers) runs through `app/memory/memory_ui_service.py`.
- Frontend API adapter (`frontend/src/features/memory/lib/api.ts`) selectively uses Supabase read fallback for selected query paths, while preserving backend-mediated mutations.

## Graph and Search Behavior (Current)

- `/api/v1/memory/graph` is assembled by backend logic over current table state and relationship provenance.
- Graph payload includes edited-memory trust metadata such as `hasEditedMemory` and `hasEditedProvenance` to support UI trust indicators.
- `/api/v1/memory/search` currently uses backend text-query semantics aligned with runtime endpoint behavior.

## Reliability and Safety Controls

### Embedding generation safeguards

`MemoryUIService.generate_embedding` enforces:

- non-empty content
- API key presence
- rate-limit checks via internal limiter
- expected embedding dimension validation

### Add/update safeguards

`MemoryUIService.add_memory` and update flows include:

- PII redaction
- required `agent_id` / `tenant_id`
- title normalization
- reviewer validation safeguards for invalid placeholder UUID scenarios

### Duplicate and merge safeguards

- Duplicate handling routes support explicit dismiss/merge flows.
- Merge paths preserve data integrity via service-layer orchestration and DB-side merge RPC behavior.

### Import-job reliability

- Zendesk import routes support queueing + task polling (`/api/v1/memory/import/zendesk-tagged/{task_id}`).
- Backfill-v2 route supports reprocessing mode for existing imported records.

## Relationship Analysis/Split Tooling

Current advanced routes:

- `/api/v1/memory/relationships/{relationship_id:uuid}/analysis`
- `/api/v1/memory/relationships/{relationship_id:uuid}/split/preview`
- `/api/v1/memory/relationships/{relationship_id:uuid}/split/commit`
- `/api/v1/memory/relationships/{relationship_id:uuid}/acknowledge`

These flows are admin-oriented and designed for controlled relationship hygiene and explainability.

## Frontend Polling and Data Contracts

- `TIMING.GRAPH_POLL_INTERVAL_MS = 60000`
- `TIMING.GRAPH_STALE_TIME_MS = 60000`
- Stats polling and read windows are configured in `frontend/src/features/memory/hooks/useMemoryData.ts`.

## Security Posture (Current)

- All Memory UI backend routes require authenticated context; admin mutation routes use explicit admin checks.
- Asset rendering routes proxy authenticated access to avoid exposing raw signed URLs directly in UI state.
- Sensitive transformations are performed backend-side before persistence.

## Related

- `docs/product-specs/memory-ui.md`
- `docs/generated/db-schema.md`
- `docs/SECURITY.md`
