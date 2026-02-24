# Ref Source Registry

Last updated: 2026-02-23

This registry tracks high-value documentation sources used during implementation.

## In-Repo Canonical Sources

| Source | Purpose |
|---|---|
| `docs/DESIGN.md` | Backend/system architecture map |
| `docs/FRONTEND.md` | Frontend architecture and contracts |
| `docs/PRODUCT_SENSE.md` | Product intent and acceptance framing |
| `docs/SECURITY.md` | Security baseline and review requirements |
| `docs/RELIABILITY.md` | Reliability and fallback expectations |
| `docs/product-specs/index.md` | Domain behavior specs |
| `docs/generated/model-catalog.md` | Model registry snapshot |
| `docs/generated/dependency-watchlist.md` | Dependency drift watchlist |
| `docs/generated/db-schema.md` | DB schema snapshot |

## External Source Policy

1. Prefer primary official documentation.
2. Verify fast-moving APIs before implementation.
3. Record recurring gaps in `ref-gaps.md`.
