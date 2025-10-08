# Review: Phase 9 — Legacy Cleanup + SSE Smoke Tests

Status: Approved

Scope:
- Deprecate legacy `agent_endpoints.py` (not registered in `app.main`).
- Re-export `_filter_system_text` from `agent_common` for compatibility.
- Align canonical DB import: `app.db.embedding_utils` now uses `app.db.supabase.client.get_supabase_client`.
- Added SSE smoke tests locally (ignored by VCS per .gitignore) covering chat, unified, and logs streams via `TestClient.stream()`.

Diff risk analysis:
- No route changes; only deprecation of an unused module and util re-export.
- Tests updated to import the util from `agent_common` to enforce canonical path.
- SSE smoke tests read-only; do not depend on external keys (assert first SSE line only).

Checks:
- Ran targeted tests: `tests/api/test_sse_smoke.py` and `tests/test_agent_stream_filter.py` → pass.
- No secrets added; accidental additions removed from commit.

Recommendation:
- Keep `agent_endpoints.py` temporarily as a thin shim for backwards-compatibility; schedule deletion after downstream consumers migrate.
