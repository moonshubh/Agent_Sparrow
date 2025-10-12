# Phase 1 — Hybrid Store Adapter

## Summary
- Introduced `HybridStoreAdapter`, a lightweight bridge that wraps Supabase RPC search calls while exposing a store-like interface for future phases.
- `GraphState` now carries an optional `global_knowledge_context` so orchestration nodes can publish adapter readiness metadata.
- `pre_process` attaches adapter context when `settings.should_use_store_adapter()` evaluates to True, leaving existing cache behavior untouched.

## Adapter Details
- Location: `app/agents/orchestration/orchestration/store_adapter.py`
- Filters results to approved `metadata.source` values (`correction`, `feedback`).
- `search()` returns simplified dictionaries containing conversation/chunk identifiers, content, similarity, and source.
- `is_ready()` checks Supabase mock mode to avoid false positives when credentials are absent.
- Factory: `get_hybrid_store_adapter()` exposes a singleton instance, while allowing dependency overrides (useful for tests).

## Orchestration Integration
- `pre_process` now sets `state.global_knowledge_context` only when the adapter flag is enabled.
- Returned context includes `{"adapter_ready": bool, "sources": [...]}` so downstream phases can determine readiness without making RPC calls.
- Default flows (cache hit/miss) remain unchanged when the flag is off.

## Tests
- `tests/backend/test_store_adapter.py`
  - Validates adapter filtering behavior and readiness reporting.
  - Verifies `pre_process` emits context only when the adapter is enabled, and that cache hits still return expected values.
- Command: `pytest -k store_adapter`
  - Output: 4 passed, 129 deselected (warnings only from existing dependencies / FastAPI lifecycle).

## Manual Verification
1. Leave adapter flags disabled (default) and ensure `/health/global-knowledge` reflects `status=ready` with no `global_knowledge_context` updates in runtime logs.
2. Temporarily set `ENABLE_STORE_ADAPTER=true` with `RETRIEVAL_PRIMARY=store` but without Supabase store credentials; observe `global_knowledge_context.adapter_ready=false` in debug logs.
3. Provide valid Supabase credentials and confirm `adapter_ready=true` while default message flow remains unaffected.
