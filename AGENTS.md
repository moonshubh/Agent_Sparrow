# Agent Sparrow - Repository Map

Last updated: 2026-02-23

This file is a map, not an encyclopedia. Canonical knowledge lives in `docs/`.

## Bootstrap Order

Follow this exact order at the start of every task:

1. Read this file.
2. Read `CLAUDE.md` for execution protocol.
3. Read `docs/README.md`.
4. Read only the domain docs needed for your task.
5. Validate assumptions in code with targeted search.

## Repository Structure

- `app/` FastAPI backend and orchestration.
- `frontend/` Next.js frontend.
- `docs/` system of record.
- `scripts/` automation (including harness review loop).
- `tests/` minimal contract baseline.

Scoped instructions:

- `app/AGENTS.md`
- `frontend/AGENTS.md`
- `docs/AGENTS.md`

## Canonical Docs Index

Core system docs:

- `docs/DESIGN.md`
- `docs/FRONTEND.md`
- `docs/PLANS.md`
- `docs/PRODUCT_SENSE.md`
- `docs/QUALITY_SCORE.md`
- `docs/RELIABILITY.md`
- `docs/SECURITY.md`

Structured knowledge:

- `docs/design-docs/index.md`
- `docs/product-specs/index.md`
- `docs/exec-plans/`
- `docs/generated/`
- `docs/references/index.md`

Archived docs:

- `docs/archive/2026-02/index.md`

## Mandatory Post-Task Review Loop

Every meaningful task must run the harness loop:

1. Architecture reviewer pass.
2. Quality reviewer pass.
3. Security reviewer pass (must use `security-best-practices` skill).
4. If any high/medium findings remain, fix and rerun.
5. Maximum 3 cycles.

Orchestrator:

- `scripts/harness/review_loop.py`

Output location:

- `reports/reviews/<task-id>/`

Exit criteria:

- No high/medium findings across all three reviewers.
- Low findings allowed only if added to `docs/exec-plans/tech-debt-tracker.md`.

## Quality Gates

Run these before handoff:

```bash
python scripts/validate_docs_consistency.py
python scripts/refresh_ref_docs.py
pytest -q
```

## Rules

- Keep docs and code aligned in the same run.
- Do not add long instructions to this file.
- Add durable decisions to `docs/design-docs/`.
- Add execution work to `docs/exec-plans/`.
- Superseded docs go to archive; do not leave duplicate active truth.
