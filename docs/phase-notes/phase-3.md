# Phase 3 — Store-First Retrieval

## Summary
- Added settings knobs `GLOBAL_KNOWLEDGE_TOP_K` and `GLOBAL_KNOWLEDGE_MAX_CHARS` to control retrieval breadth and injected memory budget.
- Created `app/services/global_knowledge/retrieval.py` to query the LangGraph Postgres store first and automatically fall back to the hybrid Supabase adapter when needed.
- Converted `pre_process` to async so it can fetch global knowledge snippets ahead of routing and attach structured context to the `GraphState` (including memory snippets, latency diagnostics, and fallback state).
- Updated the primary agent to weave global knowledge highlights into the grounding digest and emit tracing metadata for observability.

## Implementation Details
- `get_async_store()` now configures LangGraph’s async store with the Gemini embedding model (when available) and degrades gracefully if the optional dependency is missing.
- Retrieval truncates summaries, key facts, and correction pairs to stay under the configured character budget and emits a compact multi-line memory string.
- Adapter fallback shares the same embedding model and now runs both when store results are missing and when `RETRIEVAL_PRIMARY="rpc"`, preserving legacy Supabase-only behaviour.

## Tests
- Added `tests/backend/test_global_knowledge_retrieval.py` covering store hits and adapter fallback behaviour with stubs.
- Existing global knowledge persistence and flag suites continue to pass (`pytest -k global_knowledge`).

## Verification
```bash
pytest -k global_knowledge
```
