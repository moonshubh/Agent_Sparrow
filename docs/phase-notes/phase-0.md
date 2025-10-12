# Phase 0 – Global Knowledge Flags

## Overview
- Added environment-driven toggles in `app/core/settings.py` for:
  - `ENABLE_GLOBAL_KNOWLEDGE_INJECTION`
  - `ENABLE_STORE_ADAPTER`
  - `ENABLE_STORE_WRITES`
  - `RETRIEVAL_PRIMARY` (validated against `rpc` or `store`)
  - `GLOBAL_STORE_DB_URI` (presence only checked; never logged)
- Introduced helper methods (`should_enable_global_knowledge`, `should_use_store_adapter`, `should_enable_store_writes`, `has_global_store_configuration`, `get_retrieval_primary`) to centralize downstream decisions.
- Startup logging now surfaces global knowledge feature states without exposing connection strings.
- New `/health/global-knowledge` probe reports flag status, store configuration presence, and `EXPECTED_DIM` from the embedding config.

## Health Check Contract
```json
{
  "status": "ready" | "degraded",
  "flags": {
    "enable_global_knowledge_injection": bool,
    "enable_store_adapter": bool,
    "enable_store_writes": bool,
    "retrieval_primary": "rpc" | "store"
  },
  "store_configured": bool,
  "embedding_expected_dim": 3072
}
```
- `status` is `ready` when all flags are disabled with `retrieval_primary="rpc"` **or** when store features are enabled and a store URI is configured; otherwise `degraded`.
- Errors are downgraded to a 503 response with `status="degraded"` and a generic `error` field while keeping secrets redacted.

## Test Coverage
- `tests/backend/test_global_knowledge_flags.py`
  - Validates default flag values when no environment overrides are present.
  - Ensures invalid `RETRIEVAL_PRIMARY` values fall back to `rpc` and emit a warning.
  - Exercises the `/health/global-knowledge` endpoint with default flags, asserting the readiness contract.

Run focused tests with:

```bash
pytest -k global_knowledge_flags
```

## Manual Verification
1. Start the FastAPI app and observe startup logs; confirm the new “Global Knowledge Configuration” block reflects expected boolean states and does not print secrets.
2. Call `GET /health/global-knowledge` and verify the response shape matches the contract above.
3. Toggle `ENABLE_STORE_ADAPTER=true` and omit `GLOBAL_STORE_DB_URI`; ensure the health probe reports `status="degraded"`.
4. Provide a valid `GLOBAL_STORE_DB_URI` with store features enabled and verify the probe returns `status="ready"`.
