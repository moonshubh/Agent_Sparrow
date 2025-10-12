# Phase 6 — Security & Privacy Hardening

## Summary
- Locked down attachment ingestion with allowlisted kinds, HTTPS-only URLs, MIME validation, and strict length limits.
- Sanitized submission metadata and enhanced payloads to bound depth, keys, and string sizes before persistence or telemetry publication.
- Ensured observability events redact oversized metadata prior to buffering or streaming to the frontend.

## Implementation Highlights
- Updated `Attachment`, submission, and payload models with validation guards, attachment count caps, and normalization helpers.
- Introduced shared `sanitize_metadata` utility leveraged by submissions, persistence writes, and observability events.
- Persistence now re-sanitizes merged metadata before Supabase inserts; observability wraps `start_trace`/`publish_stage` metadata with the same helper.
- Added backend security tests covering attachment validation, metadata truncation, and observability sanitization paths.
- Security review completed via `security-lead`; follow-up recommendation logged to evaluate a configurable host allowlist for attachments if dereferenced server-side.

## Tests
- Backend: `tests/backend/test_global_knowledge_security.py`
- Regression: `pytest -k global_knowledge`

## Verification
```bash
pytest -k global_knowledge
```

## Deployment Notes
- The Supabase free tier only exposes the pooled Postgres endpoint, so LangGraph’s direct PostgresStore can’t be initialised there. For production, plan to point `GLOBAL_STORE_DB_URI` at either a paid Supabase project (direct connection unlocked) or a standalone Postgres service (e.g., Railway) so store writes and retrieval operate end to end.
