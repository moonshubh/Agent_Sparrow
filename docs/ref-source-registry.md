# Ref Source Registry

Canonical registry of documentation sources used by agents for implementation-time API verification.

## Objectives

- Keep external API usage accurate while controlling Ref credit consumption.
- Prefer internal repository docs for architecture and contract context.
- Route agents to stable, official sources for fast-moving dependencies.

## Credit Budget Policy

- Total monthly plan credits: ~1,000.
- Target maintenance envelope: 150-250 credits/month.
- Default strategy: event-driven lookups during active work, not broad daily sweeps.
- Scheduled verification cadence: biweekly.

## Ingestion and Sync Model

- Internal docs are maintained in-repo and indexed via Ref GitHub resource sync.
- Ref MCP tools are read-only at runtime (`ref_search_documentation`, `ref_read_url`).
- Private docs ingestion is performed through Ref dashboard/GitHub resources.
- Programmatic indexing API is not currently documented by Ref.

## Tier 0: Internal Sources (Highest Priority)

| Source | Purpose | Refresh Method |
|--------|---------|----------------|
| `AGENTS.md` | Bootstrap map and routing | In-repo updates + GitHub sync |
| `CLAUDE.md` | Runtime/ops guidance and architecture notes | In-repo updates + GitHub sync |
| `docs/backend-architecture.md` | Backend system of record | In-repo updates + GitHub sync |
| `docs/backend-runtime-reference.md` | Backend runtime/API/config/services reference | In-repo updates + GitHub sync |
| `docs/frontend-architecture.md` | Frontend system of record | In-repo updates + GitHub sync |
| `docs/frontend-reference.md` | Frontend implementation reference | In-repo updates + GitHub sync |
| `docs/database-schema.md` | Data and migration contracts | In-repo updates + GitHub sync |
| `docs/database-schema-reference.md` | Full schema table/reference details | In-repo updates + GitHub sync |
| `docs/zendesk.md` | Zendesk pipeline and policy details | In-repo updates + GitHub sync |
| `docs/zendesk-operations.md` | Zendesk config/runbook/troubleshooting reference | In-repo updates + GitHub sync |
| `docs/memory-ui.md` | Memory UI behavior and contracts | In-repo updates + GitHub sync |
| `docs/memory-ui-reference.md` | Memory UI implementation/runtime reference | In-repo updates + GitHub sync |
| `docs/observability.md` | Tracing and diagnostics | In-repo updates + GitHub sync |
| `docs/model-catalog.md` | Generated model inventory | `python scripts/refresh_ref_docs.py` |
| `docs/dependency-watchlist.md` | Generated dependency drift list | `python scripts/refresh_ref_docs.py` |

## Tier 1: External Sources (Frequent Drift)

| Domain | Official Sources |
|--------|------------------|
| AG-UI | `https://github.com/ag-ui-protocol/ag-ui`, `https://docs.ag-ui.com` |
| LangGraph/LangChain | `https://langchain-ai.github.io/langgraph/`, `https://docs.langchain.com/oss/python/`, `https://reference.langchain.com/python/` |
| Next.js/React | `https://nextjs.org/docs`, `https://react.dev` |
| Supabase/pgvector/vecs | `https://supabase.com/docs`, `https://github.com/pgvector/pgvector`, `https://supabase.com/docs/guides/ai/vecs-python-client` |
| TipTap | `https://tiptap.dev/docs` |
| R3F/drei | `https://r3f.docs.pmnd.rs`, `https://github.com/pmndrs/drei` |
| Motion | `https://motion.dev/docs` |
| Zod | `https://zod.dev` |

## Tier 2: Targeted/Gap Sources

See `docs/ref-gaps.md` for libraries with weak or missing Ref indexing and fallback handling.

## Maintenance Rules

1. Run `python scripts/refresh_ref_docs.py` when dependency or model config changes.
2. Keep `AGENTS.md` and `CLAUDE.md` aligned with any docs/protocol changes in the same run.
3. Validate with `python scripts/validate_docs_consistency.py` before merge.
4. Use Ref lookups selectively for implementation-critical APIs.
