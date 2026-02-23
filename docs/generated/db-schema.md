# DB Schema Snapshot

Last updated: 2026-02-23

Verified schema overview for active feature domains. This is a routing map, not a full DDL dump.

## Source of Truth

- Migrations: `app/db/migrations/`
- Runtime DB usage: `app/db/`, `app/memory/memory_ui_service.py`, `app/feedme/`, `app/integrations/zendesk/`

## Memory Domain

Runtime memory UI code currently reads/writes `memories` (not `memories_new`).

Core tables in active code paths:

- `memories`
- `memory_entities`
- `memory_relationships`
- `memory_duplicate_candidates`
- `memory_feedback`
- `store` (workspace/persistence support)

Key references:

- `app/memory/memory_ui_service.py`
- `app/api/v1/endpoints/memory/endpoints.py`

## FeedMe Domain

Core workflow tables:

- `feedme_conversations`
- `feedme_folders`
- `feedme_text_chunks`
- `feedme_examples`
- `feedme_temp_examples`
- `feedme_review_history`
- `feedme_settings`
- `feedme_action_audit`
- `feedme_conversation_versions`

Optimization/support tables or views present in migrations:

- `feedme_conversations_v2` + monthly partition tables
- materialized views: analytics/quality/approval snapshots

Key constraints/defaults to preserve:

- `feedme_conversations.os_category` check: `windows|macos|both|uncategorized`
- `processing_status` and `approval_status` constrained enums
- `upload_sha256` duplicate-detection support indexes
- 3072-dimension embedding support in `feedme_text_chunks`
- SLA checks in `feedme_settings` (`sla_breach_minutes > sla_warning_minutes`)

Primary migration anchors:

- `app/db/migrations/005_feedme_supabase.sql`
- `app/db/migrations/009_feedme_approval_workflow.sql`
- `app/db/migrations/012_feedme_v2_phase2_optimization.sql`
- `app/db/migrations/016_feedme_pdf_text_restructure.sql`
- `app/db/migrations/018_feedme_pdf_cleanup.sql`
- `app/db/migrations/019_feedme_text_chunks.sql`
- `app/db/migrations/021_migrate_embeddings_3072.sql`
- `app/db/migrations/039_restore_feedme_examples_tables.sql`
- `app/db/migrations/040_feedme_single_release_hardening.sql`

## Zendesk Domain

Core Zendesk integration tables:

- `feature_flags` (key: `zendesk_enabled`)
- `zendesk_pending_tickets`
- `zendesk_usage`
- `zendesk_daily_usage`
- `zendesk_webhook_events`

Operational behavior notes:

- Monthly budget enforcement is currently disabled in runtime logic (`budget` forced to `0`).
- Replay protection depends on `zendesk_webhook_events` records.

Primary migration anchors:

- `app/db/migrations/034_create_zendesk_integration.sql`
- `app/db/migrations/035_update_zendesk_tables.sql`
- `app/db/migrations/036_create_zendesk_webhook_events.sql`

## Security Posture Snapshot

- FeedMe tables have RLS/policy hardening in security-focused migrations.
- Zendesk tables enforce RLS and rely on backend service access patterns.
- Memory tables are accessed through authenticated backend endpoints plus controlled service-role RPC usage.

See `docs/SECURITY.md` for application-level policy requirements.
