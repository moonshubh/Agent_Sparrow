# FeedMe Hardening Notes

Last updated: 2026-02-23

Canonical implementation snapshot for FeedMe backend/frontend contracts and schema hardening.

## Scope

FeedMe handles PDF ingest, extraction, approval workflow, foldering, version history,
KB-ready transitions, AI note generation, and operational analytics.

## Schema Snapshot

Important migrations and what they introduced:

| Migration | Key additions |
|---|---|
| `app/db/migrations/005_feedme_supabase.sql` | Base folders/workflow primitives |
| `app/db/migrations/009_feedme_approval_workflow.sql` | Approval statuses + quality workflow |
| `app/db/migrations/012_feedme_v2_phase2_optimization.sql` | Partitioned v2 tables + analytics materialized views |
| `app/db/migrations/019_feedme_text_chunks.sql` | Chunk table + semantic search function |
| `app/db/migrations/021_migrate_embeddings_3072.sql` | 3072 embedding compatibility |
| `app/db/migrations/039_restore_feedme_examples_tables.sql` | `feedme_examples`, `feedme_temp_examples`, `feedme_review_history` |
| `app/db/migrations/040_feedme_single_release_hardening.sql` | `feedme_settings`, `feedme_action_audit`, `feedme_conversation_versions`, os-category normalization |

## Backend Contract Snapshot

Verified route families under the FeedMe router:

- Conversations: `/api/v1/feedme/conversations`, `/api/v1/feedme/conversations/upload`, `/api/v1/feedme/conversations/{conversation_id}`
- Conversation workflow: `/api/v1/feedme/conversations/{conversation_id}/status`, `/api/v1/feedme/conversations/{conversation_id}/mark-ready`, `/api/v1/feedme/conversations/{conversation_id}/ai-note/regenerate`, `/api/v1/feedme/conversations/{conversation_id}/reprocess`
- Versioning: `/api/v1/feedme/conversations/{conversation_id}/edit`, `/api/v1/feedme/conversations/{conversation_id}/versions`, `/api/v1/feedme/conversations/{conversation_id}/versions/{version_number}`, `/api/v1/feedme/conversations/{conversation_id}/versions/{version_1}/diff/{version_2}`, `/api/v1/feedme/conversations/{conversation_id}/revert/{target_version}`
- Approval: `/api/v1/feedme/conversations/{conversation_id}/approve`, `/api/v1/feedme/conversations/{conversation_id}/reject`, `/api/v1/feedme/approval/stats`, `/api/v1/feedme/approval/pending`, `/api/v1/feedme/approval/conversation/{conversation_id}/preview`, `/api/v1/feedme/approval/conversation/{conversation_id}/decide`, `/api/v1/feedme/approval/bulk`, `/api/v1/feedme/approval/queue/summary`
- Search: `/api/v1/feedme/search/examples`
- Foldering: `/api/v1/feedme/folders`, `/api/v1/feedme/folders/{folder_id}`, `/api/v1/feedme/folders/assign`, `/api/v1/feedme/folders/{folder_id}/conversations`
- Operations and analytics: `/api/v1/feedme/stats/overview`, `/api/v1/feedme/analytics`, `/api/v1/feedme/gemini-usage`, `/api/v1/feedme/embedding-usage`, `/api/v1/feedme/settings`, `/api/v1/feedme/health`, `/api/v1/feedme/cleanup/pdfs/batch`
- Intelligence: `/api/v1/feedme/intelligence/summarize`, `/api/v1/feedme/intelligence/analyze-batch`, `/api/v1/feedme/intelligence/smart-search`

Approval note: `/api/v1/feedme/approval/stats`, `/api/v1/feedme/approval/pending`, `/api/v1/feedme/approval/conversation/{conversation_id}/preview`, `/api/v1/feedme/approval/conversation/{conversation_id}/decide`, `/api/v1/feedme/approval/bulk`, and `/api/v1/feedme/approval/queue/summary` are exposed by the dedicated text-approval router (`app/api/v1/endpoints/text_approval_endpoints.py`) and coexist with `/api/v1/feedme/conversations/{conversation_id}/approve` and `/api/v1/feedme/conversations/{conversation_id}/reject` in `app/api/v1/endpoints/feedme/approval.py`.

## Authorization and Reliability

- Read/list/status/search workflows require authenticated users.
- Mutating/admin workflows are role-gated in FeedMe auth dependencies.
- Upload path enforces PDF/size constraints and SHA-256 duplicate reuse.
- Processing paths include fallback model behavior and fail-open guards when rate-limit infrastructure is unstable.
- Versioning is persisted in `feedme_conversation_versions` and exposed via explicit diff/revert endpoints.

## Frontend Contract Snapshot

Primary route surfaces:

- FeedMe dashboard: `frontend/src/app/feedme/page.tsx`
- Conversation workspace: `frontend/src/app/feedme/conversation/[id]/page.tsx`

Primary UI modules:

- Upload and duplicate UX: `frontend/src/features/feedme/components/UploadDialog.tsx`
- Folder workflows: `frontend/src/features/feedme/components/FoldersDialog.tsx`, `frontend/src/features/feedme/components/FolderConversationsDialog.tsx`
- Unassigned queue: `frontend/src/features/feedme/components/UnassignedDialog.tsx`
- Conversation side controls: `frontend/src/features/feedme/components/ConversationSidebar.tsx`
- Text editing canvas: `frontend/src/features/feedme/components/UnifiedTextCanvas.tsx`
- Stats and settings: `frontend/src/features/feedme/components/StatsPopover.tsx`, `frontend/src/features/feedme/hooks/use-stats-data.ts`

Client contract source:

- `frontend/src/features/feedme/services/feedme-api.ts`

Notable behavior:

- Upload dialog handles duplicate-response reuse and progress/status polling.
- Conversation sidebar supports autosave + blur-save patterns and workflow actions.
- Stats/settings view consumes `/api/v1/feedme/stats/overview` and `/api/v1/feedme/settings`.
- Search store uses `/api/v1/feedme/search/examples` for filtered FeedMe discovery.
- Backend availability checks run through `frontend/src/services/monitoring/backend-health-check.ts`.

## Notes for Future Work

- Keep frontend/backend endpoint mapping in sync whenever FeedMe APIs change.
- If deprecated compatibility paths are removed from frontend client wrappers, update this doc and `docs/FRONTEND.md` in the same run.
