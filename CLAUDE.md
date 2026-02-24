# CLAUDE.md

Last updated: 2026-02-23

Execution guide for agent work in this repository.

## Core Principle

Humans steer intent; agents execute implementation. The repository is the single
source of truth.

## Required Workflow

For each task:

1. Bootstrap context from `AGENTS.md` and `docs/README.md`.
2. Implement with focused changes.
3. Update canonical docs in the same run.
4. Run mandatory review loop (`scripts/harness/review_loop.py`).
5. Ship only when loop passes.

## Mandatory Review Loop Contract

The loop has three independent passes each cycle:

1. Architecture reviewer (`docs/reviewers/architecture-reviewer.md`)
2. Quality reviewer (`docs/reviewers/quality-reviewer.md`)
3. Security reviewer (`docs/reviewers/security-reviewer.md`)

Security pass is always required and must apply the installed
`security-best-practices` skill.

Loop rules:

- Max 3 cycles.
- Stop only when all high/medium findings are resolved.
- Write reports to `reports/reviews/<task-id>/`.

## Docs and Generated Artifacts

Canonical docs live in `docs/`.

Generated docs:

- `docs/generated/model-catalog.md`
- `docs/generated/dependency-watchlist.md`

Regenerate when dependencies or model registry changes:

```bash
python scripts/refresh_ref_docs.py
```

Consistency check:

```bash
python scripts/validate_docs_consistency.py
```

## Baseline Commands

```bash
# Backend
ruff check .
pytest -q

# Frontend
cd frontend && pnpm lint && pnpm typecheck
```

## Design and Planning Records

- Stable design decisions: `docs/design-docs/`
- Active execution plans: `docs/exec-plans/active/`
- Completed execution plans: `docs/exec-plans/completed/`
- Technical debt ledger: `docs/exec-plans/tech-debt-tracker.md`
