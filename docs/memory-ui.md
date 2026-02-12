# Memory UI

Last updated: 2026-02-12

---

## Table of Contents

1. [Overview](#1-overview)
2. [Database Schema](#2-database-schema)
3. [API Reference](#3-api-reference)
4. [Memory UI Implementation Reference](memory-ui-reference.md)

---

## 1. Overview

The Memory UI provides a visual knowledge graph and management interface for Agent Sparrow's
shared memory system. It exposes agent memories (auto-extracted and manually added) through
a 3D interactive graph, a searchable table, and admin tools for editing, merging duplicates,
importing knowledge, and tracking confidence.

### Architecture at a Glance

```
Frontend (/memory)                Backend (FastAPI)                 Supabase
 MemoryClient.tsx ──WRITE──> Memory API endpoints  ─────────> memories_new
 MemoryGraph.tsx  ──READ───> pg_graphql (GraphQL) ──────> entities, relationships
 MemoryTable.tsx  ──READ───> Supabase client   ──────────> memories_new
                             Edge Function (webhook) <──── entity extraction trigger
```

**Key design decisions** (from Phase I, Dec 2025):
- Reads via Supabase client / pg_graphql; writes via FastAPI for validation and side effects.
- Shared agent memory (global learning across all customer interactions).
- 3D graph visualization using `react-three-fiber` (upgraded from original react-force-graph spec).
- 30-second polling for real-time updates (simpler than WebSockets).
- Two-tier role access: agents (view + add) and admins (full CRUD + merge + export).

### Key file paths

| Layer | Path |
|-------|------|
| Page entry | `frontend/src/app/memory/page.tsx` |
| Feature module | `frontend/src/features/memory/` |
| Backend endpoints | `app/api/v1/endpoints/memory/endpoints.py` |
| Backend schemas | `app/api/v1/endpoints/memory/schemas.py` |
| Memory UI service | `app/memory/memory_ui_service.py` |
| Memory service (mem0) | `app/memory/service.py` |
| Styles | `frontend/src/features/memory/styles/memory.css` |

---

## 2. Database Schema

The Memory UI uses a dedicated `memories_new` table (separate from mem0's internal tables)
plus supporting graph, duplicate, and feedback tables. See also `docs/database-schema.md`.

### 2.1 Core Memory Table (`memories_new`)

Key columns added for UI/graph support:

```sql
source_type       VARCHAR(20)   DEFAULT 'auto_extracted'  -- 'auto_extracted' | 'manual'
confidence_score  DECIMAL(5,4)  DEFAULT 0.5000
retrieval_count   INTEGER       DEFAULT 0
last_retrieved_at TIMESTAMPTZ
feedback_positive INTEGER       DEFAULT 0
feedback_negative INTEGER       DEFAULT 0
resolution_success_count INTEGER DEFAULT 0
resolution_failure_count INTEGER DEFAULT 0
tenant_id         UUID          -- tenant isolation
agent_id          UUID          -- agent scope
review_status     VARCHAR       -- 'pending_review' for imports
reviewed_by       UUID          -- FK to auth.users (nullable, skip-invalid safe)
```

Index: `idx_memories_confidence ON memories_new(confidence_score DESC)`.

### 2.2 Entity Table (`memory_entities`)

```sql
CREATE TABLE IF NOT EXISTS memory_entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     VARCHAR(50) NOT NULL CHECK (entity_type IN (
        'product', 'feature', 'issue', 'solution',
        'customer', 'platform', 'version', 'error'
    )),
    entity_name     VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL,  -- lowercase, trimmed for dedup
    display_label   VARCHAR(100),
    first_seen_at   TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ DEFAULT NOW(),
    occurrence_count INTEGER DEFAULT 1,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(entity_type, normalized_name)
);

CREATE INDEX idx_entities_type ON memory_entities(entity_type);
CREATE INDEX idx_entities_name ON memory_entities(normalized_name);
CREATE INDEX idx_entities_gin  ON memory_entities USING GIN(metadata);
CREATE INDEX idx_entities_occurrence ON memory_entities(occurrence_count DESC);
```

### 2.3 Relationship Table (`memory_relationships`)

```sql
CREATE TABLE IF NOT EXISTS memory_relationships (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_entity_id  UUID NOT NULL REFERENCES memory_entities(id) ON DELETE CASCADE,
    target_entity_id  UUID NOT NULL REFERENCES memory_entities(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) NOT NULL CHECK (relationship_type IN (
        'RESOLVED_BY', 'AFFECTS', 'REQUIRES', 'CAUSED_BY',
        'REPORTED_BY', 'WORKS_ON', 'RELATED_TO', 'SUPERSEDES'
    )),
    weight            DECIMAL(5,4) DEFAULT 1.0000,
    occurrence_count  INTEGER DEFAULT 1,
    source_memory_id  UUID REFERENCES memories_new(id) ON DELETE SET NULL,
    first_seen_at     TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at      TIMESTAMPTZ DEFAULT NOW(),
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_entity_id, target_entity_id, relationship_type)
);

CREATE INDEX idx_rel_source ON memory_relationships(source_entity_id);
CREATE INDEX idx_rel_target ON memory_relationships(target_entity_id);
CREATE INDEX idx_rel_type   ON memory_relationships(relationship_type);
CREATE INDEX idx_relationships_composite
    ON memory_relationships(source_entity_id, target_entity_id, relationship_type);
```

### 2.4 Duplicate Candidates Table (`memory_duplicate_candidates`)

```sql
CREATE TABLE IF NOT EXISTS memory_duplicate_candidates (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id_1      UUID NOT NULL REFERENCES memories_new(id) ON DELETE SET NULL,
    memory_id_2      UUID NOT NULL REFERENCES memories_new(id) ON DELETE SET NULL,
    similarity_score DECIMAL(5,4) NOT NULL,
    status           VARCHAR(20) DEFAULT 'pending' CHECK (status IN (
        'pending', 'merged', 'dismissed', 'superseded'
    )),
    reviewed_by      UUID REFERENCES auth.users(id),
    reviewed_at      TIMESTAMPTZ,
    merge_target_id  UUID REFERENCES memories_new(id),
    detected_at      TIMESTAMPTZ DEFAULT NOW(),
    detection_method VARCHAR(50) DEFAULT 'cosine_similarity',
    CHECK (memory_id_1 < memory_id_2),
    UNIQUE(memory_id_1, memory_id_2)
);

CREATE INDEX idx_dup_pending
    ON memory_duplicate_candidates(status, detected_at DESC)
    WHERE status = 'pending';
```

### 2.5 Memory Feedback Table (`memory_feedback`)

```sql
CREATE TABLE IF NOT EXISTS memory_feedback (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id     UUID NOT NULL REFERENCES memories_new(id) ON DELETE CASCADE,
    user_id       UUID REFERENCES auth.users(id),
    feedback_type VARCHAR(20) NOT NULL CHECK (feedback_type IN (
        'thumbs_up', 'thumbs_down', 'resolution_success', 'resolution_failure'
    )),
    session_id    VARCHAR(100),
    ticket_id     VARCHAR(100),
    notes         TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_feedback_memory ON memory_feedback(memory_id, feedback_type);
```

### 2.6 Workspace Store (`store`)

Persistent workspace files for context engineering (handoff, progress, goals).
See `docs/DEVELOPMENT.md` for workspace route details.

| Column | Type | Description |
|--------|------|-------------|
| `prefix` | VARCHAR | Namespace path (e.g., `workspace:handoff:session-123`) |
| `key` | VARCHAR | File key (e.g., `summary.json`) |
| `value` | JSONB | File content |

### 2.7 Foreign Key Strategy

| FK | On Delete | Rationale |
|----|-----------|-----------|
| `duplicate_candidates -> memories_new` | SET NULL | Preserves audit trail of merges/dismissals |
| `memory_feedback -> memories_new` | CASCADE | Feedback meaningless without memory |
| `memory_relationships -> memory_entities` | CASCADE | Relationship invalid without entity |
| `memory_relationships -> memories_new` | SET NULL | Preserve relationship if source memory deleted |

### 2.8 Applied Migrations

| Migration | Description |
|-----------|-------------|
| `20251230053146_create_memory_ui_schema` | Core tables |
| `20251230053215_create_memory_ui_indexes` | Performance indexes (no vector index -- see 10.7) |
| `20251230053238_create_memory_ui_rls_policies` | RLS security policies |
| `20251230053306_create_memory_ui_functions` | Basic helper functions |
| `20251230053414_create_memory_ui_advanced_functions` | Vector search, duplicate detection |
| `20251230053820_fix_memory_ui_race_conditions_v2` | Race condition fixes |
| `20260209124500_memory_feedback_confidence_step_five` | Fixed-step feedback confidence |
| `036_fix_memory_vector_index.sql` | Vector index adjustments |

---

## 3. API Reference

### 3.1 FastAPI Write Endpoints

All writes go through FastAPI (`app/api/v1/endpoints/memory/endpoints.py`) for validation,
business logic, and side effects. Auth via JWT; admin-only endpoints use `require_admin`.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/memory/add` | Authenticated | Add a memory (manual or auto-extracted) |
| PUT | `/api/v1/memory/{memory_id:uuid}` | Admin | Update memory content |
| DELETE | `/api/v1/memory/{memory_id:uuid}` | Admin | Delete memory + cascade |
| POST | `/api/v1/memory/merge` | Admin | Merge duplicate memories |
| POST | `/api/v1/memory/{memory_id:uuid}/feedback` | Authenticated | Submit thumbs up/down feedback |
| POST | `/api/v1/memory/export` | Admin | Export filtered memories as JSON |
| POST | `/api/v1/memory/import/zendesk-tagged` | Admin | Import Zendesk tickets as memories |
| GET | `/api/v1/memory/import/zendesk-tagged/{task_id}` | Admin | Poll import task status |
| GET | `/api/v1/memory/assets/{bucket}/{object_path:path}` | Authenticated | Proxy for authenticated image serving |
| GET | `/api/v1/memory/search` | Authenticated | Semantic search with hybrid ranking |

### 3.2 Key RPCs (Supabase Functions)

| Function | Purpose |
|----------|---------|
| `find_similar_memories(query_embedding, match_threshold, match_count, exclude_id)` | pgvector cosine similarity search |
| `record_memory_feedback(memory_id, feedback_type, ...)` | Atomic feedback + confidence update |
| `merge_duplicate_memories(keep_id, delete_id, ...)` | Atomic merge with relationship transfer |
| `record_memory_retrieval(memory_id)` | Increment retrieval count (FOR UPDATE) |
| `update_memory_confidence(memory_id)` | Recalculate from signals (atomic subquery) |
| `recalculate_all_confidence()` | Batch recalculation (pg_cron daily at 3 AM) |

### 3.3 GraphQL Read Queries (pg_graphql)

Read operations use Supabase's pg_graphql for efficient graph data fetching.

**Graph data** -- entities (nodes) and relationships (edges):
```graphql
query GetMemoryGraph($limit: Int, $entityTypes: [String!]) {
  memoryEntitiesCollection(
    first: $limit
    filter: { entityType: { in: $entityTypes } }
    orderBy: [{ occurrenceCount: DescNullsLast }]
  ) {
    edges { node { id entityType entityName displayLabel occurrenceCount metadata } }
    pageInfo { hasNextPage endCursor }
  }
  memoryRelationshipsCollection(first: 500) {
    edges { node { id sourceEntityId targetEntityId relationshipType weight } }
  }
}
```

**Memory search** -- confidence-ordered with text filter:
```graphql
query SearchMemories($query: String!, $limit: Int, $minConfidence: Float) {
  memoriesCollection(
    filter: { and: [{ content: { ilike: $query } }, { confidenceScore: { gte: $minConfidence } }] }
    first: $limit
    orderBy: [{ confidenceScore: DescNullsLast }]
  ) {
    edges { node { id content confidenceScore sourceType retrievalCount createdAt metadata } }
    totalCount
  }
}
```

---

## Additional References

- Runtime behaviors, frontend implementation patterns, reliability hardening, security, and implementation decisions: `docs/memory-ui-reference.md`
- Broader schema context: `docs/database-schema.md`
