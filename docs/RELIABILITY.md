# RELIABILITY

Last updated: 2026-02-23

## Reliability Principles

- Prefer explicit fallbacks for external dependencies.
- Fail safely with observable diagnostics.
- Keep startup and runtime checks deterministic.
- Treat docs drift as reliability risk for agent execution.

## Required Controls

- Health endpoints and startup checks must remain operational.
- AG-UI stream contract must be covered by smoke tests.
- Review loop findings must block unresolved high/medium defects.
- Incidents and recurring defects should feed into `docs/exec-plans/tech-debt-tracker.md`.

## Validation

- `pytest -q` (5-contract baseline)
- `python scripts/validate_docs_consistency.py`
- Review loop reports in `reports/reviews/`
