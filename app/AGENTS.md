# Backend Agent Guide

Scope: `app/` and child paths.

## Read First

1. `../AGENTS.md`
2. `../CLAUDE.md`
3. `../docs/DESIGN.md`
4. `../docs/SECURITY.md`
5. Relevant product spec in `../docs/product-specs/`

## Backend Invariants

- Keep endpoint handlers thin; business logic belongs in services/agents.
- Preserve AG-UI stream contract behavior.
- Do not hardcode model behavior outside `app/core/config/models.yaml`.
- Keep Supabase access guarded and validated.
- Use typed schemas at API boundaries.

## Done Criteria

- Update impacted docs.
- Run tests relevant to backend changes.
- Run full review loop via `../scripts/harness/review_loop.py`.
