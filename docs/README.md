# Documentation System Guide

This folder is the system of record for Agent Sparrow.

## How Agents Should Read Docs

1. Start at `AGENTS.md` for routing.
2. Read architecture overview docs first.
3. Read runtime/reference companion docs only for implementation details.
4. Verify external APIs via Ref before coding.

## Split Strategy

Large docs are intentionally split into:

- **Architecture overview docs** (high-signal, faster context load)
- **Runtime/reference docs** (dense endpoint/config/runbook details)

Current split pairs:

- `backend-architecture.md` + `backend-runtime-reference.md`
- `frontend-architecture.md` + `frontend-reference.md`
- `database-schema.md` + `database-schema-reference.md`
- `zendesk.md` + `zendesk-operations.md`
- `memory-ui.md` + `memory-ui-reference.md`

## Core Architecture Docs

- `backend-architecture.md`
- `frontend-architecture.md`
- `database-schema.md`
- `database-schema-reference.md`
- `observability.md`

## Runtime / Implementation References

- `backend-runtime-reference.md`
- `frontend-reference.md`
- `zendesk-operations.md`
- `memory-ui.md`
- `memory-ui-reference.md`
- `feedme-hardening-notes.md`

## Governance and Drift Control

- `ref-source-registry.md`
- `ref-gaps.md`
- `ref-index-plan.md`
- `model-catalog.md` (generated)
- `dependency-watchlist.md` (generated)

Refresh generated docs:

```bash
python scripts/refresh_ref_docs.py
```

Validate docs consistency:

```bash
python scripts/validate_docs_consistency.py
```
