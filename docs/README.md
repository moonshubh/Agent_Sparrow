# Agent Sparrow Documentation System

Last updated: 2026-02-23

This directory is the canonical knowledge base for humans and agents.

## Start Here

1. `../AGENTS.md`
2. `../CLAUDE.md`
3. This index

## Canonical Top-Level Docs

- `DESIGN.md` - backend architecture, orchestration, runtime boundaries
- `FRONTEND.md` - frontend architecture and implementation contracts
- `PLANS.md` - planning and execution system
- `PRODUCT_SENSE.md` - product intent and acceptance framing
- `QUALITY_SCORE.md` - quality posture and current gaps
- `RELIABILITY.md` - runtime resilience and fallback patterns
- `SECURITY.md` - security controls and required practices

## Structured Knowledge Folders

- `design-docs/` stable design decisions and principles
- `product-specs/` domain-level implementation specs
- `exec-plans/` active/completed plans and debt ledger
- `generated/` derived docs from source configs/manifests
- `references/` external docs governance and source registry
- `archive/` superseded docs with migration history

## Mandatory Review Loop

All significant work must pass:

- Architecture reviewer
- Quality reviewer
- Security reviewer (`security-best-practices` skill)

Tooling entrypoint: `../scripts/harness/review_loop.py`
