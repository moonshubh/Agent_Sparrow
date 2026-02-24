# Frontend Agent Guide

Scope: `frontend/` and child paths.

## Read First

1. `../AGENTS.md`
2. `../CLAUDE.md`
3. `../docs/FRONTEND.md`
4. Relevant product spec in `../docs/product-specs/`

## Frontend Invariants

- Preserve feature-based structure under `src/features/`.
- Keep API contracts aligned with backend schemas.
- Avoid introducing `any` in TypeScript.
- Maintain responsive behavior and accessibility.

## Done Criteria

- Update affected canonical docs.
- Run lint/typecheck for frontend changes.
- Run full review loop via `../scripts/harness/review_loop.py`.
