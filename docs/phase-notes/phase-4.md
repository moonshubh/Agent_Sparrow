# Phase 4 — Enhancer LangGraph Subgraph

## Summary
- Replaced the synchronous enhancer helper with a dedicated LangGraph `StateGraph` that routes submissions through classification → normalization → moderation → finalize nodes.
- The subgraph uses a cached `MemorySaver` checkpointer and preserves structured error reporting/fallback paths.
- `FeedbackEnhancer` now invokes the graph (with a graceful fallback) while persistence continues to operate asynchronously.

## Implementation Highlights
- New `EnhancerState` Pydantic model captures submission, payload, classification, and errors for the graph.
- Added normalization nodes that reuse the previous payload construction helpers; moderation node currently annotates metadata with a `moderation.status="skipped"` placeholder for future extension.
- Unsupported submission types raise `TypeError`, maintaining previous external behaviour.

## Tests
- Added `tests/backend/test_global_knowledge_enhancer_graph.py` covering feedback, correction, and unsupported submission flows.
- Updated global knowledge suite (`pytest -k global_knowledge`) to confirm no regressions.

## Verification
```bash
pytest -k global_knowledge
```
