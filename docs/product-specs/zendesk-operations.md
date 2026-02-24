# Zendesk Operations Reference

Last updated: 2026-02-23

Operational/runtime contract for Zendesk integration.

## Configuration Defaults (Current)

### Core controls

| Variable | Default | Notes |
|---|---|---|
| `ZENDESK_ENABLED` | `false` | Integration feature toggle |
| `ZENDESK_DRY_RUN` | `true` | Prevents real note posting when enabled |
| `ZENDESK_POLL_INTERVAL_SEC` | `60` | Scheduler queue poll interval |
| `ZENDESK_MAX_RETRIES` | `5` | Retry attempts |
| `ZENDESK_QUEUE_RETENTION_DAYS` | `30` | Queue retention |

### API/rate controls

| Variable | Default | Notes |
|---|---|---|
| `ZENDESK_RPM_LIMIT` | `240` | Zendesk API rate limit target |
| `ZENDESK_IMPORT_RPM_LIMIT` | `10` | Historical import/backfill limiter |
| `ZENDESK_MONTHLY_API_BUDGET` | `0` | Monthly budget enforcement disabled in current runtime logic |
| `ZENDESK_GEMINI_DAILY_LIMIT` | `380` | Daily model budget used by scheduler checks |

### Formatting and spam guard controls

| Variable | Default |
|---|---|
| `ZENDESK_FORMAT_ENGINE` | `markdown_v2` |
| `ZENDESK_USE_HTML` | `true` |
| `ZENDESK_SPAM_GUARD_STRICT_ENABLED` | `true` |
| `ZENDESK_SPAM_SCORE_THRESHOLD` | `0.65` |
| `ZENDESK_SPAM_RECIPIENT_BURST_THRESHOLD` | `20` |

## Endpoint Contract

### Core integration endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/integrations/zendesk/webhook` | Zendesk webhook ingestion |
| `GET` | `/api/v1/integrations/zendesk/health` | Health + usage snapshot (requires `X-Internal-Token`) |
| `GET` | `/api/v1/integrations/zendesk/models` | Current provider/model snapshot (requires `X-Internal-Token`) |
| `POST` | `/api/v1/integrations/zendesk/feature` | Feature toggle + dry-run state updates (requires `X-Internal-Token`) |

### Admin endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/integrations/zendesk/admin/health` | Admin health/status summary (requires `X-Internal-Token`) |
| `GET` | `/api/v1/integrations/zendesk/admin/queue` | Queue list/pagination/filtering (requires `X-Internal-Token`) |
| `POST` | `/api/v1/integrations/zendesk/admin/queue/{item_id}/retry` | Retry one queue item (requires `X-Internal-Token`) |
| `POST` | `/api/v1/integrations/zendesk/admin/queue/retry-batch` | Retry multiple queue items (requires `X-Internal-Token`) |

### Memory import endpoints used by Zendesk workflows

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/memory/import/zendesk-tagged` | Queue Zendesk-tagged import |
| `POST` | `/api/v1/memory/import/zendesk-tagged/backfill-v2` | Queue reprocess/backfill-v2 import job |
| `GET` | `/api/v1/memory/import/zendesk-tagged/{task_id}` | Poll import task status |

## Runtime Notes

- Monthly usage row is still tracked (`zendesk_usage`) but runtime logic currently forces `budget=0` and does not enforce monthly caps.
- Scheduler still enforces RPM and Gemini daily checks.
- Webhook replay protection depends on `zendesk_webhook_events` records.

## Operational Checklist

1. Confirm Zendesk credentials and signing secret are set.
2. Confirm internal token is configured for admin/health endpoints.
3. Confirm Supabase service credentials for scheduler/import paths.
4. Validate webhook signature and queue insertion by test ticket.
5. Check queue progress via `/api/v1/integrations/zendesk/admin/queue`.

## Related

- `docs/product-specs/zendesk.md`
- `docs/generated/db-schema.md`
- `docs/SECURITY.md`
- `docs/RELIABILITY.md`
