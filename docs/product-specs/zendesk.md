# Zendesk Integration

Last updated: 2026-02-23

Canonical implementation snapshot for Zendesk ingestion, processing, and response workflows.

## Purpose

Zendesk integration receives support tickets, enriches context (internal retrieval + patterns),
generates suggested replies, and posts internal notes while maintaining safety and auditability.

## Pipeline Snapshot

1. Webhook received at `/api/v1/integrations/zendesk/webhook`.
2. Signature verification and replay protection.
3. Queue insertion into `zendesk_pending_tickets`.
4. Scheduler claims pending/retry work.
5. Exclusion checks and spam guard checks.
6. Context assembly (attachments, retrieval, patterns/playbooks).
7. Unified agent invocation for reply draft.
8. Output sanitization/quality formatting.
9. Internal note post + telemetry/context report persistence.

## Core Components

| Component | File |
|---|---|
| Webhook + feature endpoints | `app/integrations/zendesk/endpoints.py` |
| Admin queue endpoints | `app/integrations/zendesk/admin_endpoints.py` |
| Scheduler/orchestration | `app/integrations/zendesk/scheduler.py` |
| Zendesk API wrapper | `app/integrations/zendesk/client.py` |
| Webhook signature security | `app/integrations/zendesk/security.py` |
| Spam guard | `app/integrations/zendesk/spam_guard.py` |
| Attachment processing | `app/integrations/zendesk/attachments.py` |
| Formatting engine | `app/integrations/zendesk/formatters/markdown_v2.py` |
| Historical import utility | `app/integrations/zendesk/historical_import.py` |

## Queue and Status Model

Primary queue table: `zendesk_pending_tickets`.

Typical statuses:

- `pending`
- `processing`
- `retry`
- `processed`
- `failed`

Status details are persisted for troubleshooting and context reporting.

## Endpoint Snapshot

| Method | Endpoint |
|---|---|
| `POST` | `/api/v1/integrations/zendesk/webhook` |
| `GET` | `/api/v1/integrations/zendesk/health` |
| `GET` | `/api/v1/integrations/zendesk/models` |
| `POST` | `/api/v1/integrations/zendesk/feature` |
| `GET` | `/api/v1/integrations/zendesk/admin/health` |
| `GET` | `/api/v1/integrations/zendesk/admin/queue` |
| `POST` | `/api/v1/integrations/zendesk/admin/queue/{item_id}/retry` |
| `POST` | `/api/v1/integrations/zendesk/admin/queue/retry-batch` |

## Safety and Quality Behaviors

- Public-comment attachment handling only.
- URL and sensitive-content scrubbing before output.
- Spam guard can divert suspicious tickets and add tags.
- Reply sanitization strips planning/internal artifacts.
- Context reports are persisted for each processed ticket.

## Memory/Knowledge Integration

Zendesk processing can retrieve from:

- Internal KB and macro retrieval flows.
- FeedMe knowledge retrieval.
- Memory UI retrieval (when enabled by config).

Zendesk import/backfill into Memory UI uses:

- `/api/v1/memory/import/zendesk-tagged`
- `/api/v1/memory/import/zendesk-tagged/backfill-v2`
- `/api/v1/memory/import/zendesk-tagged/{task_id}`

## Related

- `docs/product-specs/zendesk-operations.md`
- `docs/SECURITY.md`
- `docs/RELIABILITY.md`
