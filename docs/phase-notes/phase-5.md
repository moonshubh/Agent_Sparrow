# Phase 5 — Observability & Review Actions

## Summary
- Added telemetry service and Supabase action helpers so enhancer/persistence emit timeline events, queue counts, and summaries for Global Knowledge processing.
- Exposed REST and SSE endpoints for observability, including promotion actions for feedback and corrections.
- Built the frontend Observability tab with live metrics, timeline stream, and promotion flows that respect backend outcomes.

## Implementation Highlights
- Created `observability.py` service that publishes timeline events, computes summaries, and supports subscribers; integrated with enhancer and persistence stages.
- Added Supabase client accessors plus API routes for queue, summary, events, SSE streaming, and `promote_*` actions; registered router in FastAPI app.
- Implemented frontend API client, SSE-aware hook with reconnection/backoff, helper utilities, and UI components inside `ObservabilityTab`/`StatsPopover`.
- Addressed reviewer feedback to guard queue removals on successful promotions and to render store status badges only when data is present.

## Tests
- Backend: `tests/backend/test_global_knowledge_observability.py` covering queue merges, promotion actions, and summary aggregation.
- Frontend: `hooks/useGlobalKnowledgeObservability.test.ts` validating event upsert ordering and size limits.

## Verification
```bash
pytest -k global_knowledge
npx vitest run hooks/useGlobalKnowledgeObservability.test.ts
```
