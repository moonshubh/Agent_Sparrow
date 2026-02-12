# Memory UI Reference

Last updated: 2026-02-12

> Companion implementation reference split from `docs/memory-ui.md`.

---

## 1. Entity Extraction Pipeline

Entity extraction runs as a Supabase Edge Function triggered by a database webhook on
memory inserts.

**Flow**: Memory INSERT -> DB trigger (`trigger_entity_extraction`) -> HTTP POST to Edge Function
-> LLM extraction (Gemini, temperature 0.1) -> Upsert entities -> Create relationships.

**Entity types**: `product`, `feature`, `issue`, `solution`, `customer`, `platform`, `version`, `error`.

**Relationship types**: `RESOLVED_BY`, `AFFECTS`, `REQUIRES`, `CAUSED_BY`, `REPORTED_BY`,
`WORKS_ON`, `RELATED_TO`, `SUPERSEDES`.

The Edge Function:
1. Receives the new memory record via webhook payload.
2. Calls Gemini with a structured extraction prompt requesting JSON output.
3. Upserts entities into `memory_entities` (dedup via `entity_type + normalized_name`).
4. Upserts relationships into `memory_relationships` (dedup via composite unique constraint).

**Post-edit graph sync**: After memory edits, the frontend shows a sync indicator, polls for
async extraction completion, displays a non-blocking timeout warning if slow, and offers a
manual refresh path.

---

## 2. Confidence Scoring

### 2.1 Composite Score Algorithm

Confidence is a 0.0--1.0 score computed from three weighted signals:

| Component | Weight | Calculation |
|-----------|--------|-------------|
| Usage frequency | 40% | `min(1.0, ln(1 + retrieval_count) / 5.0)` -- log scale to cap runaway growth |
| Human feedback | 30% | `positive / (positive + negative)` -- neutral (0.5) when no feedback |
| Resolution outcomes | 30% | `success / (success + failure)` -- pure ratio, no double penalty |

**Feedback stepping** (Feb 2026): Thumbs feedback applies deterministic fixed-step changes:
`+0.05` for `thumbs_up`, `-0.05` for `thumbs_down`, clamped to `[0, 1]`. This is enforced
in both the frontend optimistic state and the backend DB RPC
(`20260209124500_memory_feedback_confidence_step_five.sql`).

**Resolution outcomes**: The original spec's formula double-penalized failures. The implemented
version uses pure ratio (failures already reduce the numerator). See section 10.5.

### 2.2 Batch Recalculation

```sql
-- Scheduled via pg_cron, daily at 3 AM
SELECT cron.schedule('recalculate-confidence', '0 3 * * *',
  'SELECT recalculate_all_confidence()');
```

The `recalculate_all_confidence()` function recomputes all confidence scores from the raw
signal columns in a single UPDATE statement.

---

## 3. Duplicate Detection

### 3.1 Detection

- **Threshold**: 85% cosine similarity (aggressive, per design decision).
- **Scope**: Same `tenant_id` and `agent_id` (prevents cross-tenant leakage).
- **Method**: pgvector `find_similar_memories` RPC using embedding cosine distance.
- **Trigger**: On new memory insert + periodic batch scan.
- **Candidate ordering**: `CHECK (memory_id_1 < memory_id_2)` prevents reverse duplicates.

### 3.2 Merge Logic

When an admin confirms a duplicate:

1. Transfer all relationships from deleted memory to kept memory.
2. Combine confidence: `min(1.0, max(keep.confidence, delete.confidence) + 0.10)`.
3. Sum retrieval counts and feedback tallies.
4. Delete the duplicate memory.
5. Mark the candidate record as `merged` (audit trail preserved via ON DELETE SET NULL).

**Candidate statuses**: `pending`, `merged`, `dismissed`, `superseded`.

**Race protection**: `SELECT ... FOR UPDATE NOWAIT` on the candidate row prevents concurrent
merge of the same pair. Lock contention returns an explicit error message.

---

## 4. Frontend Architecture

### 4.1 Component Structure

The frontend lives in `frontend/src/features/memory/` with this organization:

```
features/memory/
  components/
    MemoryClient.tsx         -- Main orchestrator (table + graph + import)
    MemoryGraph.tsx          -- Graph visualization wrapper
    MemoryTree3D.tsx         -- 3D tree scene (react-three-fiber)
    TreeScene.tsx            -- R3F canvas setup
    TreeNode.tsx             -- Individual 3D node
    TreeBranch.tsx           -- 3D branch connections
    TreeTrunk.tsx            -- Central trunk
    FoliageCluster.tsx       -- Cluster foliage rendering
    NodeCluster.tsx          -- Spatial clustering
    MemoryTable.tsx          -- Tabular memory list
    MemoryForm.tsx           -- Add/edit memory form
    MemorySearch.tsx         -- Search with debounce + filters
    MemoryTipTapEditor.tsx   -- Rich text editor for memory content
    DuplicateReview.tsx      -- Duplicate merge interface
    ConfidenceBadge.tsx      -- Visual confidence indicator
    SourceBadge.tsx          -- Auto-extracted vs manual badge
    RelationshipEditor.tsx   -- Edit relationships
    RelationshipAnalysisPanel.tsx
    GraphErrorBoundary.tsx   -- Error boundary for 3D scene
    OrphanSidebar.tsx        -- Orphan memories panel
    ClusterPreview.tsx       -- Cluster hover preview
  hooks/
    useMemoryData.ts         -- Main data fetching + cache
    useTreeState.ts          -- Graph state management
    useTree3DLayout.ts       -- 3D layout computation
    useLOD.ts                -- Level-of-detail for 3D
    useAcknowledgment.ts     -- Feedback acknowledgment
  lib/
    api.ts                   -- FastAPI client calls
    treeTransform.ts         -- Graph -> tree transform
    spatialClustering.ts     -- Node clustering algorithm
    tree3DGeometry.ts        -- 3D geometry helpers
    cycleDetection.ts        -- Cycle detection in graph
    memoryAssetResolver.ts   -- Image asset URL resolution
    memoryImageSizing.ts     -- Image size extraction
    memoryImageMarkdown.ts   -- Markdown image rendering
    memoryTitle.ts           -- Title extraction
    memoryFlags.ts           -- Feature flags
  tiptap/
    memoryExtensions.ts      -- TipTap extension config
    MemoryImageExtension.tsx -- Custom image node with resize
    MemoryImageView.tsx      -- Image render view
  types/
    index.ts                 -- TypeScript types
  styles/
    memory.css               -- Memory-specific styles
```

### 4.2 Key Patterns

- **3D visualization**: Uses `react-three-fiber` with level-of-detail (LOD) rendering and
  spatial clustering for performance. Original spec called for `react-force-graph` but the
  implementation evolved to a 3D tree metaphor.
- **Progressive loading**: Initial load shows top nodes by occurrence, connected nodes load
  on interaction, remaining nodes load in background batches.
- **Polling**: Graph and table data poll on 30-second intervals via React Query
  (`staleTime: 25s`, `refetchInterval: 30s`).
- **Role-based UI**: Admin users see edit/delete/merge/import actions. Non-admin users see
  read-only modals. Determined by auth context role claim.
- **Optimistic updates**: Feedback (thumbs) applies immediately in UI, rolls back on failure.

---

## 5. Reliability & Trust

This section captures hardening decisions from the Feb 2026 sprint that addressed production
reliability, trust signals, and edit synchronization.

### 5.1 Import Knowledge

- `Import Knowledge` defaults to the `mb_playbook` tag across frontend, API schema defaults,
  and Celery fallback handling.
- Import jobs expose status polling: `GET /api/v1/memory/import/zendesk-tagged/{task_id}`.
- Results include `processed_tickets`, `imported_memory_ids`, and per-ticket failure metadata.
- Frontend polls queued imports, shows completion/failure toasts, invalidates caches on
  completion, and focuses the latest imported memory in table view.
- Import task records per-ticket failure reasons and falls back to direct embedding generation
  when rate-limit infrastructure is temporarily unavailable.

### 5.2 Edited Memory Detection & Retrieval

- Edited-memory detection standardized to `updated_at > created_at` plus editor identity
  metadata/reviewer fields (frontend + backend parity).
- `search_memories` returns hybrid ranking fields: `is_edited`, `edited_boost` (conservative
  `+0.05`), `hybrid_score`. Results ordered by hybrid score.
- Agent memory context consumes and surfaces ranking details: `similarity`, `confidence`,
  `edited`, `edited_boost`, `hybrid`.

### 5.3 Feedback Determinism

- Each `thumbs_up` applies `+5%`, each `thumbs_down` applies `-5%`, clamped to `[0%, 100%]`.
- Aligned in frontend optimistic state AND backend DB RPC.
- Table feedback handlers safely coerce malformed confidence/count payloads, prevent
  action-click propagation side effects, and sync the selected detail panel confidence
  immediately from the response.

### 5.4 Graph Sync

- Post-edit graph sync indicator with async extraction polling.
- Non-blocking timeout warning when extraction is slow.
- Manual refresh path available.
- Trust visuals: edited-influence amber overlay accents, legend updates, node-level
  edited-influence chip/counter.

### 5.5 Table UX

- Content cell single-click opens admin edit modal or non-admin read-only modal (eye
  action removed).
- Description preview has robust fallback and explicit show more / show less expansion
  to prevent blank/truncated post-edit previews.

### 5.6 TipTap / Rich Content

- **Image resize persistence**: TipTap image nodes store `width`/`height` as explicit
  attributes during markdown parse/render, so resized images persist across save/reopen.
- **mb_playbook emphasis**: Edit view highlights `Problem`, `Impact`, and `Environment`
  headings and label-style paragraph lines with strong color + underline styling. Includes
  content-shape fallback (when metadata tags/source are missing) and stronger CSS specificity.
- **Inline resize safety**: Uses guarded pointer lifecycle cleanup (`pointerup`,
  `pointercancel`, window `blur`, capture release, unmount-safe listener disposal) to prevent
  stuck drag listeners from freezing modal interactions.

### 5.7 Edge Cases

- Memory updates defensively skip invalid/nonexistent reviewer IDs (notably the
  `00000000-0000-0000-0000-000000000000` SKIP_AUTH dev placeholder) when setting
  `reviewed_by`, avoiding `memories_reviewed_by_fkey` failures.
- Authenticated image rendering routes through backend asset proxy
  (`GET /api/v1/memory/assets/{bucket}/{object_path}`) to avoid exposing signed
  Supabase storage URLs to the browser.

---

## 6. Security

See also `docs/SECURITY.md` for project-wide security patterns.

### 6.1 Row-Level Security

All memory tables have RLS enabled.

```sql
-- Read: all authenticated users
CREATE POLICY "Memories are viewable by all authenticated users"
    ON memories_new FOR SELECT TO authenticated USING (true);

-- Insert: service role only (backend writes through service key)
CREATE POLICY "Memories can be inserted by service role"
    ON memories_new FOR INSERT TO service_role WITH CHECK (true);

-- Update: admin role only
CREATE POLICY "Memories can be updated by admins"
    ON memories_new FOR UPDATE TO authenticated
    USING (
      EXISTS (
        SELECT 1 FROM auth.users
        WHERE auth.uid() = id AND raw_user_meta_data->>'role' = 'admin'
      )
    );
```

Same pattern applied to `memory_entities`, `memory_relationships`, `memory_duplicate_candidates`,
and `memory_feedback`.

### 6.2 API Authentication

- All FastAPI write endpoints require valid JWT tokens.
- Admin-only endpoints (`PUT`, `DELETE`, merge, import, export) use the `require_admin`
  dependency.
- Read endpoints and feedback submission are open to any authenticated user.
- Function execution revoked from `anon` role, granted to `authenticated` only.
- All `SECURITY DEFINER` functions set `search_path = public, extensions` to prevent
  search_path injection.

### 6.3 Tenant Isolation

- Similarity search filters by `tenant_id` AND `agent_id` to prevent cross-tenant data leakage.
- Duplicate detection scoped to same tenant/agent.
- Stats function is global (admin dashboard) but RLS restricts per-user access.

---

## 7. Implementation Decisions

These decisions were made during Phase I (Dec 2025) and subsequent hardening (Feb 2026).
They represent architectural choices worth preserving for context.

### 7.1 Table Strategy

Created a new `memories_new` table rather than extending mem0's internal tables. This
provides UI-specific columns without modifying mem0, and allows the two systems to
operate independently.

### 7.2 Migration Tooling

Initial implementation used Supabase MCP. Subsequent work uses Supabase CLI to reduce
context consumption during agent-assisted development.

### 7.3 Error Handling Philosophy

| Context | Strategy |
|---------|----------|
| Scalar-returning functions | `RAISE EXCEPTION` for clear error propagation |
| JSONB-returning functions | Return `jsonb_build_object('error', ...)` for consistent API contract |
| Lock contention | `FOR UPDATE NOWAIT` + catch exception with explicit "locked" message |
| Not found errors | Explicit exception (not silent NULL) to prevent undetected failures |

### 7.4 Race Condition Mitigations

| Function | Fix |
|----------|-----|
| `record_memory_feedback` | `SELECT ... FOR UPDATE` before counter increment |
| `merge_duplicate_memories` | `FOR UPDATE NOWAIT` + exception handling |
| `record_memory_retrieval` | `SELECT ... FOR UPDATE` before increment |
| `update_memory_confidence` | Single atomic UPDATE with subquery (no TOCTOU) |

### 7.5 Confidence Scoring Fix

The original spec double-penalized failures in the resolution component:

```sql
-- Original (broken): penalty applied on top of already-reduced ratio
resolution_score := success / total - 0.1 * failures;
```

**Implemented**: Pure ratio `success / total`. Failures already reduce the score through the
denominator, so additional penalty was double-counting.

### 7.6 Feedback Stepping (Feb 2026)

Changed from formula-based confidence updates to deterministic fixed-step changes (`+/-0.05`)
so that table UI percentages stay consistent with persisted DB values. This was a reliability
fix -- the formula-based approach caused drift between optimistic frontend state and backend
truth.

### 7.7 Vector Index Limitation

pgvector IVFFlat index is limited to 2000 dimensions; Gemini embeddings are 3072-dim.
**Decision**: No vector index (exact search via table scan). Acceptable for < 100K memories.

Future options:
1. Reduce embedding dimensions via PCA to 1536.
2. Use HNSW index when pgvector adds high-dim support.
3. Use a dedicated vector database.

### 7.8 Graph Visualization Evolution

The original spec called for `react-force-graph` (2D WebGL). The actual implementation uses
`react-three-fiber` for a 3D tree metaphor with spatial clustering, level-of-detail rendering,
foliage effects, and trust-signal visual indicators. The 3D approach provides better spatial
separation and more room for visual encoding of confidence and edit state.

### 7.9 Duplicate Candidate Statuses

| Status | Meaning |
|--------|---------|
| `pending` | Awaiting review |
| `merged` | Memories were merged (audit trail preserved) |
| `dismissed` | Marked as false positive (not duplicates) |
| `superseded` | Another merge made this irrelevant |

---

## Cross-References

- Database schema details: `docs/database-schema.md`
- Security patterns: `docs/SECURITY.md`
- Development commands: `docs/DEVELOPMENT.md`
- Coding standards: `docs/CODING_STANDARDS.md`
- Zendesk integration (import source): `docs/zendesk.md`
- Backend architecture: `docs/backend-architecture.md`
