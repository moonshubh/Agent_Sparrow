# Ref Index Plan

Practical indexing checklist for Agent Sparrow with budget-safe maintenance.

## Operating Mode

- Internal docs indexed through Ref GitHub resource sync.
- External docs consumed from Ref public index when available.
- Credit strategy: prioritize implementation-time lookups and biweekly verification.

## Priority 1: Internal Repository Sources

- [ ] Connect Agent Sparrow GitHub repository as a Ref resource
- [ ] Verify private search returns hits for `docs/backend-architecture.md`
- [ ] Verify private search returns hits for `docs/backend-runtime-reference.md`
- [ ] Verify private search returns hits for `docs/frontend-architecture.md`
- [ ] Verify private search returns hits for `docs/frontend-reference.md`
- [ ] Verify private search returns hits for `docs/database-schema-reference.md`
- [ ] Verify private search returns hits for `AGENTS.md` and `CLAUDE.md`
- [ ] Verify private search returns hits for `docs/zendesk-operations.md`
- [ ] Verify private search returns hits for `docs/memory-ui-reference.md`

## Priority 2: Critical External Libraries

- [x] AG-UI protocol docs/repo discoverable
- [x] LangGraph/LangChain docs discoverable
- [x] Next.js/React docs discoverable
- [x] Supabase/pgvector/vecs docs discoverable
- [x] TipTap/R3F/drei docs discoverable
- [x] Firecrawl/Tavily docs discoverable

## Priority 3: Known Gaps to Track

- [ ] DeepAgents official docs/source indexed in Ref
- [ ] Streamdown docs/source indexed in Ref
- [ ] Minimax platform docs deeper indexing
- [ ] Gemini `ai.google.dev` docs deeper indexing

## Verification Cadence

- Biweekly: run focused Ref coverage checks.
- Event-driven: run coverage checks after dependency/model changes.
- Every PR: run docs consistency validator.

## Related Docs

- `docs/ref-source-registry.md`
- `docs/ref-gaps.md`
- `docs/dependency-watchlist.md`
- `docs/model-catalog.md`
