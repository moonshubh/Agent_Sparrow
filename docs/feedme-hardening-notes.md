# Feed Me — Hardening Notes

Last updated: 2026-02-12

These notes capture the single-release hardening sprint (Feb 2026) and subsequent
reliability fixes. For architecture details, see [`backend-architecture.md`](backend-architecture.md).

---

## Schema & Migrations

Added migration `app/db/migrations/040_feedme_single_release_hardening.sql` with additive schema updates:
- `feedme_conversations.os_category` normalization/check/default (`windows`, `macos`, `both`, `uncategorized`)
- `feedme_conversations.upload_sha256` + duplicate-detection indexes
- `feedme_settings` table (KB-ready folder + SLA thresholds)
- `feedme_action_audit` table for mutation audit trail
- `feedme_conversation_versions` table + deterministic version backfill

---

## Authorization

Enforced via JWT role claims (`app/api/v1/endpoints/feedme/auth.py`):
- **Admin-gated**: Upload, conversation mutate/delete, folder mutate/assign, approval actions, reprocess/cleanup, versioning edit/revert, workflow/settings endpoints
- **Open**: Read/list/status endpoints

---

## Upload Hardening

In `app/api/v1/endpoints/feedme/ingestion.py`:
- Strict 10MB/PDF validation preserved
- SHA-256 duplicate detection (30-day window)
- Deterministic duplicate response payload with existing conversation reuse (no new processing job)
- Duplicate + upload audit events recorded

---

## Folder Workflow

In `app/api/v1/endpoints/feedme/folders.py`:
- Standardized assign response: `assigned_count`, `requested_count`, `failed`, `partial_success`
- Max 50 IDs per assign request (schema + endpoint)
- Folder delete blocked for non-empty folders and configured KB folder
- TOCTOU race condition fixed with DB constraint catch
- Safe client IP extraction for proxies

---

## Workflow & Settings Endpoints

In `app/api/v1/endpoints/feedme/workflow.py`:
- `POST /feedme/conversations/{conversation_id}/mark-ready` (OS required, KB-config required, confirm-move behavior)
- `POST /feedme/conversations/{conversation_id}/ai-note/regenerate` — runs sync task logic in threadpool (`run_in_threadpool`)
- `GET/PUT /feedme/settings`

---

## Stats Endpoint

`GET /feedme/stats/overview` in `app/api/v1/endpoints/feedme/analytics.py`:
- Default 7-day range
- Folder + OS filters
- Metrics: queue depth, failure rate, p50/p95 latency, assign throughput, KB-ready throughput, OS distribution (including uncategorized), SLA warning/breach counters

---

## Model Fallback

- PDF extraction: `app/feedme/processors/gemini_pdf_processor.py` falls back to `gemini-2.5-flash-preview-09-2025`
- AI tag/note generation: `app/feedme/tasks.py` uses same fallback strategy with attempted/usage metadata

---

## Versioning

`app/feedme/versioning_service.py` uses persisted `feedme_conversation_versions` for coherent list/get/diff/edit/revert behavior.

---

## Reliability Fixes (Feb 10, 2026)

- Applied migration `040_feedme_single_release_hardening.sql` on active Supabase (unblocked `feedme_settings`, action audit, version-history)
- Rate-limiter lifecycle: scoped to process+thread identity in `app/core/rate_limiting/agent_wrapper.py`
- Fail-open handling in processing paths when rate-limit infrastructure unstable:
  - `app/feedme/processors/gemini_pdf_processor.py`
  - `app/feedme/tasks.py`
- Extraction metadata durability: merges extracted metadata into persisted conversation metadata
- FeedMe-only retrieval: `search_sources=['feedme']` no longer leaks KB/web results
- Status-transition race: conversations stay `processing` until all downstream steps complete
- AI-note readiness: embedding finalization performs best-effort inline note generation; AI tagging retries via Celery retry

---

## Deprecated Cleanup

- Removed unreferenced legacy components:
  - `FeedMeConversationManager` (deleted in Feb 2026)
  - `ConversationCard` (deleted in Feb 2026)
- Removed deprecated example-oriented backend routes from Feed Me conversations/analytics endpoints.

---

## Frontend Polish (Feb 10, 2026)

- Conversation sidebar uses 1.5s autosave debounce + blur save, note status/timestamp metadata, regenerate wiring, mark-ready flow, and admin-action gating
- Stats popover uses `/feedme/stats/overview` with OS/folder/range filters, SLA indicators, and admin settings panel
- `isSupersededRequestError` prevents intentional abort/replacement events from surfacing as errors
- `FolderConversationsDialog` fetch lifecycle: in-flight dedupe + stale-request guards
- Folder modal layout: grouped refresh/close, centered bulk controls, checkbox spacing fix
- Glow effect synced with Aceternity implementation, lint drift resolved
- Cleanup: no test folders/conversations remain, no `feedme_e2e_*.pdf` artifacts

---

## E2E Validation

Latest clean validated run (Feb 10, 2026):
- Conversations `157`, `158`, `159`
- `0` failed steps
- Full embedding coverage (`chunk_count == embedding_count`)
- Successful retrieval hits through connector and tool paths
