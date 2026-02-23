# Memory UI

Last updated: 2026-02-23

Canonical implementation-level contract for Memory UI backend/frontend behavior.

## Scope

Memory UI provides searchable/shared memories, graph relationships, duplicate management,
feedback/confidence tracking, and Zendesk import flows.

## Architecture Snapshot

| Layer | Current implementation |
|---|---|
| Frontend route | `frontend/src/app/memory/page.tsx` |
| Frontend feature module | `frontend/src/features/memory/` |
| Backend endpoints | `app/api/v1/endpoints/memory/endpoints.py` |
| Backend schemas | `app/api/v1/endpoints/memory/schemas.py` |
| Service layer | `app/memory/memory_ui_service.py` |
| Primary memory table | `memories` |

## Data Model (Current)

Runtime code uses `memories` plus support tables:

- `memories`
- `memory_entities`
- `memory_relationships`
- `memory_duplicate_candidates`
- `memory_feedback`

The service selects these memory fields for UI/API responses:

- `id`, `content`, `metadata`, `source_type`
- `review_status`, `reviewed_by`, `reviewed_at`
- `confidence_score`, `retrieval_count`, `last_retrieved_at`
- `feedback_positive`, `feedback_negative`
- `resolution_success_count`, `resolution_failure_count`
- `agent_id`, `tenant_id`, `created_at`, `updated_at`

Reference: `app/memory/memory_ui_service.py`.

## API Contract Snapshot

### Read/authenticated routes

- `/api/v1/memory/list`
- `/api/v1/memory/search`
- `/api/v1/memory/graph`
- `/api/v1/memory/entities`
- `/api/v1/memory/relationships`
- `/api/v1/memory/duplicates`
- `/api/v1/memory/entities/{entity_id}/memories`
- `/api/v1/memory/stats`
- `/api/v1/memory/{memory_id:uuid}`
- `/api/v1/memory/assets/{bucket}/{object_path:path}`
- `/api/v1/memory/assets/{bucket}/{object_path:path}/signed`

### Write/admin-heavy routes

- `/api/v1/memory/add`
- `/api/v1/memory/{memory_id:uuid}` (PUT/DELETE)
- `/api/v1/memory/merge`
- `/api/v1/memory/merge/arbitrary`
- `/api/v1/memory/duplicate/{candidate_id}/dismiss`
- `/api/v1/memory/export`
- `/api/v1/memory/import/zendesk-tagged`
- `/api/v1/memory/import/zendesk-tagged/backfill-v2`
- `/api/v1/memory/import/zendesk-tagged/{task_id}`
- `/api/v1/memory/relationships/merge`
- `/api/v1/memory/relationships/{relationship_id:uuid}` (PUT/DELETE)
- `/api/v1/memory/relationships/{relationship_id:uuid}/acknowledge`
- `/api/v1/memory/relationships/{relationship_id:uuid}/analysis`
- `/api/v1/memory/relationships/{relationship_id:uuid}/split/preview`
- `/api/v1/memory/relationships/{relationship_id:uuid}/split/commit`
- `/api/v1/memory/{memory_id:uuid}/feedback`

### Deprecated route behavior

- `/api/v1/memory/import` remains mounted for backward compatibility but currently returns `410 Gone`.
- Use `/api/v1/memory/import/zendesk-tagged` and `/api/v1/memory/import/zendesk-tagged/backfill-v2` for import workflows.

## Frontend Behavior Snapshot

Canonical frontend contract source: `frontend/src/features/memory/lib/api.ts`.

Important runtime behavior:

- Graph polling default: 60 seconds (`TIMING.GRAPH_POLL_INTERVAL_MS = 60000`).
- Graph stale time also set to 60 seconds by default.
- Select read paths can fall back to Supabase client queries when needed.
- Write paths remain backend-mediated for validation and side effects.

## Reliability Notes

- New memory writes trigger embedding generation and async duplicate detection scheduling.
- Graph response includes edited-memory provenance flags used for trust visuals.
- Feedback updates use deterministic +/-5% confidence stepping.
- Zendesk imports expose explicit task polling for completion/failure state.

## Related

- `docs/product-specs/memory-ui-reference.md`
- `docs/generated/db-schema.md`
- `docs/SECURITY.md`
- `docs/RELIABILITY.md`
