# Docs Agent Guide

Scope: `docs/` and child paths.

## Canonical Structure

- Stable design decisions: `design-docs/`
- Product/domain specs: `product-specs/`
- Execution planning: `exec-plans/`
- Generated artifacts: `generated/`
- External/source references: `references/`
- Archived superseded docs: `archive/YYYY-MM/`

## Documentation Rules

- One canonical source per topic.
- Superseded docs must move to archive and be listed in archive index.
- Keep `AGENTS.md` files concise and map-like.
- Update cross-links when moving docs.
- Do not treat archive docs as active source of truth.

## Validation

Run:

```bash
python ../scripts/validate_docs_consistency.py
python ../scripts/refresh_ref_docs.py
```
