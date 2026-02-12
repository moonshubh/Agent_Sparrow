# Ref Gaps and Fallbacks

Libraries and sources that currently have weak or missing Ref coverage, with fallback procedures.

## Confirmed Gaps

| Library/Domain | Ref Status | Fallback Source |
|----------------|-----------|-----------------|
| DeepAgents (`deepagents`) | Not indexed in Ref search | Package repo/PyPI and project-local usage under `app/agents/` |
| Streamdown (`streamdown`) | Not indexed in Ref search | Package repo/npm docs and local usage in `frontend/src/shared/components/Response.tsx` |
| Minimax platform docs | Partial (MCP wrapper surfaced, platform docs weak) | Official Minimax platform docs |
| Gemini `ai.google.dev` site | Partial (SDK repos indexed, docs site weak) | `https://ai.google.dev/gemini-api/docs` + SDK repo |

## Fallback Protocol

1. Use Ref first for candidate sources.
2. If missing/partial, switch to official vendor docs directly.
3. Validate against local code usage before implementing.
4. Capture any newly confirmed source in `docs/ref-source-registry.md`.
5. If a gap is persistent, request indexing through Ref support and track in `docs/ref-index-plan.md`.

## Gap Review Cadence

- Biweekly: re-check known gaps with targeted Ref queries.
- Event-driven: re-check when a dependency is upgraded or major feature work starts.
