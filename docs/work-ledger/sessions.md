# Session Work Ledger

## 2025-12-10 - Phase 0 & 1: Context Engineering Infrastructure

### Completed

**Phase 0: Core Infrastructure Refactoring**
- 0.1: Multi-Scope Store Architecture - Refactored `SparrowWorkspaceStore` to support GLOBAL, CUSTOMER, and SESSION scopes
- 0.2: Path Validation & Security - Added `_validate_and_normalize_path()`, `_path_to_namespace_key()`, and `_get_scope_for_path()` methods
- 0.3: Content-Aware Search - Applied migration `add_store_content_search_index` with GIN index on `content_text` column
- 0.4: Safe Read Defaults - Implemented DEFAULT_READ_LIMIT_CHARS (2048) and MAX_READ_LIMIT_CHARS (50000)
- 0.5: Updated coordinator prompt with new workspace guidance

**Phase 1: Workspace Tools for Agent**
- Created `workspace_tools.py` with all tools: read, write, list, search, append, grep
- Implemented `WorkspaceRateLimiter` with per-scope rate limits
- Added file-like convenience methods to `SparrowWorkspaceStore`
- Added `cleanup_session_data()` for session TTL/cleanup

### Files Modified

| File | Changes |
|------|---------|
| `app/agents/harness/store/workspace_store.py` | Multi-scope routing, path validation, content search, file-like API, cleanup methods |
| `app/agents/unified/tools/workspace_tools.py` | NEW - All workspace tools with safe defaults and rate limiting |
| `app/agents/unified/tools/__init__.py` | NEW - Package exports |
| `app/agents/unified/prompts.py` | Updated `<workspace_files>` section with new tools and path structure |

### Migrations Applied

| Migration | Purpose |
|-----------|---------|
| `add_store_content_search_index` | GIN index for content search, `content_text` generated column |

### Architecture Decisions

1. **Scope Routing**: Paths automatically route to scopes:
   - `/playbooks/` → GLOBAL (shared, read-only)
   - `/customer/{id}/` → CUSTOMER (per-customer, persistent)
   - `/scratch/`, `/knowledge/`, etc. → SESSION (ephemeral)

2. **Rate Limits**: Per-scope per 60-second window:
   - GLOBAL: 10 reads, 0 writes
   - CUSTOMER: 20 reads, 5 writes
   - SESSION: 100 reads, 50 writes

3. **Safe Defaults**:
   - Read limit: 2048 chars default, 50000 max
   - Write limit: 100KB default, 500KB max

### Notes

- Content search uses PostgreSQL GIN trigram index for efficient ILIKE queries
- Customer history uses append-only per-ticket files to avoid race conditions
- Middleware integration (SessionInitMiddleware, HandoffCaptureMiddleware) unchanged but now compatible with new scope system

---

## 2025-12-10 - Phase 2: Issue-Pattern Memory

### Completed

**Phase 2: Issue-Pattern Memory**
- 2.1: Created `IssueResolutionStore` class with full CRUD operations and vector similarity search
- 2.2: Applied database migration `add_issue_resolutions_table_v3` with:
  - `issue_resolutions` table with UUID primary key
  - Untyped VECTOR column to support 3072-dim Gemini embeddings
  - Category, created_at, and ticket_id indexes for fast lookups
  - Partial index for non-escalated resolutions (common query pattern)
  - RLS enabled with permissive policy
  - `search_similar_resolutions` RPC function for semantic search

### Files Modified

| File | Changes |
|------|---------|
| `app/agents/harness/store/issue_resolution_store.py` | NEW - IssueResolutionStore with store_resolution, find_similar_resolutions, get_resolution_by_ticket, get_resolutions_by_category, get_category_stats methods |
| `app/agents/harness/store/__init__.py` | Added IssueResolutionStore and IssueResolution exports |

### Migrations Applied

| Migration | Purpose |
|-----------|---------|
| `add_issue_resolutions_table_v3` | Create issue_resolutions table with vector column, indexes, RLS, and search RPC |

### Architecture Decisions

1. **Vector Dimensions**: Using 3072-dim Gemini embeddings (consistent with model registry `GEMINI_EMBEDDING`)
2. **No Vector Index**: pgvector IVFFlat/HNSW indexes limited to 2000 dimensions; using exact search instead (acceptable for ~10k expected rows)
3. **Model Registry Integration**: Uses `get_registry().embedding.id` for embedding model selection
4. **Lazy Loading**: Both Supabase client and embeddings model are lazy-loaded with sentinel pattern for failed imports
5. **Dataclass for Results**: `IssueResolution` frozen dataclass for immutable, typed results

### Key Features

- **Semantic Search**: `find_similar_resolutions()` uses cosine similarity with configurable threshold
- **Category Filtering**: Search can be filtered by category for more relevant results
- **Statistics**: `get_category_stats()` provides escalation rates per category
- **Async-First**: All operations are async with proper executor fallback for sync embedding APIs

### Notes

- Migration initially failed with IVFFlat and HNSW indexes due to 2000-dim limit; resolved by using untyped VECTOR column without index
- Existing tables (mailbird_knowledge, feedme_text_chunks) also use 3072-dim embeddings without vector indexes
- RPC function `search_similar_resolutions` uses SECURITY DEFINER with explicit search_path for security

---

## 2025-12-10 - Phase 3: Large Result Eviction

### Completed

**Phase 3: Large Result Eviction**
- 3.1: Enhanced `ToolResultEvictionMiddleware` with:
  - Optional `workspace_store` parameter for session-scoped `/knowledge/tool_results/` storage
  - `max_file_size_bytes` parameter for size caps (default 100KB, max 500KB)
  - Content truncation with warning when exceeding size limit
  - Content type hints in metadata (`content_type`, `original_size`, `truncated`)
  - New `evict_large_result()` async method for direct eviction API
  - Updated `_evict_and_pointer_async()` to use workspace store when available
  - Updated `_create_pointer_message()` with truncation info and workspace-aware read instructions

### Files Modified

| File | Changes |
|------|---------|
| `app/agents/harness/middleware/eviction_middleware.py` | Added workspace_store param, max_file_size_bytes, evict_large_result(), size caps, content type metadata |

### Architecture Decisions

1. **Backward Compatibility**: Existing code using the middleware without workspace_store continues to work with legacy backend
2. **Size Caps**: Default 100KB, max 500KB per evicted file - prevents unbounded storage growth
3. **Truncation Strategy**: Content exceeding limit is truncated with clear warning message appended
4. **Session-Scoped Storage**: When workspace_store is provided, evicted results go to `/knowledge/tool_results/{tool_call_id}.md`
5. **Metadata Enrichment**: Evicted files include `content_type`, `original_size`, `truncated`, `tool_name`, `evicted_at` for retrieval context

### Key Features

- **`evict_large_result()`**: Direct eviction API for custom tools/preprocessors
  ```python
  pointer = await middleware.evict_large_result(
      tool_call_id="call_123",
      result="<large content>",
      content_type="application/json",
      tool_name="web_search",
  )
  ```

- **Workspace Integration**: Seamless integration with Phase 1 workspace tools
  ```python
  middleware = ToolResultEvictionMiddleware(
      workspace_store=SparrowWorkspaceStore(session_id="sess123"),
      max_file_size_bytes=100_000,
  )
  ```

- **Smart Read Instructions**: Pointer messages direct agent to use `read_workspace_file` for workspace paths

### Notes

- Existing `__init__.py` already exports `ToolResultEvictionMiddleware`, no changes needed
- Size cap applies before writing, ensuring stored content never exceeds limit
- Truncation warning is embedded in the stored content itself, not just the pointer message

---

## 2025-12-10 - Phase 4: Issue-Category Playbooks

### Completed

**Phase 4: Issue-Category Playbooks**
- 4.1: Applied database migration `add_playbook_learned_entries_table` with:
  - `playbook_learned_entries` table with UUID primary key
  - Trust status column (`pending_review`, `approved`, `rejected`) to prevent hallucinated solutions
  - Unique constraint on `conversation_id` to prevent duplicates
  - `resolution_steps` and `diagnostic_questions` as JSONB columns
  - Quality score for ranking approved entries
  - Review metadata (`reviewed_by`, `reviewed_at`)
  - Indexes for category, status, and composite category+status queries
  - Partial index for approved entries sorted by quality score
  - RLS enabled with permissive policy

- 4.2: Created playbooks module at `app/agents/unified/playbooks/` with:
  - `__init__.py` - Package exports for Playbook, PlaybookEntry, PlaybookExtractor, PlaybookEnricher
  - `extractor.py` - PlaybookExtractor class that:
    - Builds category-specific playbooks combining static content and learned entries
    - Only includes APPROVED entries in active playbooks (prevents hallucination risks)
    - Shows pending entries separately with warnings for transparency
    - Provides approve/reject workflow methods
    - Generates prompt context for agent consumption
  - `enricher.py` - PlaybookEnricher class that:
    - Uses Model Registry for model selection (feedme model for cost-effective extraction)
    - Extracts structured playbook entries from resolved conversations
    - Creates all entries with `status='pending_review'` (requires human approval)
    - Supports both direct conversation extraction and session-based enrichment
    - Validates minimum message/word counts before extraction

### Files Created

| File | Purpose |
|------|---------|
| `app/agents/unified/playbooks/__init__.py` | Package exports for Playbook, PlaybookEntry, PlaybookExtractor, PlaybookEnricher |
| `app/agents/unified/playbooks/extractor.py` | PlaybookExtractor with trust workflow and playbook building |
| `app/agents/unified/playbooks/enricher.py` | PlaybookEnricher using Model Registry for conversation analysis |

### Migrations Applied

| Migration | Purpose |
|-----------|---------|
| `add_playbook_learned_entries_table` | Create playbook_learned_entries table with trust status, indexes, and RLS |

### Architecture Decisions

1. **Trust-First Design**: All learned entries start in `pending_review` status - prevents hallucinated solutions from being surfaced without human verification
2. **Model Registry Integration**: Uses `get_registry().feedme.id` for extraction model, ensuring single-line model updates propagate here
3. **Role-Based Temperature**: Extraction uses `role="feedme"` which maps to temperature 0.3 via provider_factory
4. **Lazy Loading Pattern**: Both Supabase client and extraction model use sentinel pattern for failed imports (consistent with IssueResolutionStore)
5. **Separation of Concerns**:
   - `PlaybookExtractor`: Reads/assembles playbooks, manages approval workflow
   - `PlaybookEnricher`: Creates new entries from conversations (write-only to pending)
6. **Quality Scoring**: Approved entries can be scored 0-1 for ranking within categories

### Key Features

- **PlaybookExtractor**:
  ```python
  extractor = PlaybookExtractor()
  playbook = await extractor.build_playbook_with_learned("account_setup")

  # Only approved entries in active playbook
  context = playbook.to_prompt_context()

  # Approve/reject workflow
  await extractor.approve_entry(entry_id, reviewed_by="admin", quality_score=0.8)
  ```

- **PlaybookEnricher**:
  ```python
  enricher = PlaybookEnricher()
  entry_id = await enricher.extract_from_conversation(
      conversation_id="session-123",
      messages=conversation_messages,
      category="account_setup",
  )
  # Entry created with status='pending_review'
  ```

- **Playbook Prompt Context**: `playbook.to_prompt_context()` generates formatted context for agent prompts with:
  - Static playbook content
  - Verified solutions from past tickets
  - Optional pending entries with warnings
  - Related KB articles and macros

### Database Schema

```sql
CREATE TABLE playbook_learned_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    problem_summary TEXT NOT NULL,
    resolution_steps JSONB NOT NULL,
    diagnostic_questions JSONB,
    final_solution TEXT NOT NULL,
    why_it_worked TEXT,
    key_learnings TEXT,
    source_word_count INTEGER,
    source_message_count INTEGER,
    status TEXT DEFAULT 'pending_review' CHECK (status IN ('pending_review', 'approved', 'rejected')),
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    quality_score FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Notes

- Extraction prompt uses structured JSON schema for reliable parsing
- Minimum thresholds: 4 messages, 100 words (prevents extraction from trivial conversations)
- Upsert on conversation_id prevents duplicate entries when re-extracting
- Review queue API available via `extractor.get_review_queue()`
- Statistics available via `enricher.get_extraction_stats()`

---

## 2025-12-10 - Phase 5 & 6: Observability & TTL/Cleanup

### Completed

**Phase 5: Observability & Rate Limits**
- 5.1: Added workspace operation logging to `workspace_store.py`:
  - `workspace_read` log events with scope, namespace, key, content_size_bytes, session_id, customer_id, cache_hit
  - `workspace_search` log events with scope, namespace, query, has_filter, result_count, limit, offset
  - `workspace_write` already existed from Phase 1
  - Cache hits logged at debug level (low volume), DB reads/searches at info level

- 5.2: Per-scope rate limits (already implemented in Phase 1):
  - `WorkspaceRateLimiter` class in workspace_tools.py
  - GLOBAL: 10 reads, 0 writes per 60s
  - CUSTOMER: 20 reads, 5 writes per 60s
  - SESSION: 100 reads, 50 writes per 60s

**Phase 6: TTL & Cleanup**
- 6.1: Session scope cleanup (already implemented in Phase 1):
  - `cleanup_session_data()` method on SparrowWorkspaceStore
  - Deletes all SESSION scope data for a session

- 6.2: Attachment cache TTL:
  - `cache_attachment_summary()` - stores attachment with 24h TTL metadata (already in Phase 1)
  - `get_cached_attachment()` - NEW - retrieves cached attachment, returns None if expired
  - `cleanup_expired_attachments()` - NEW - scans and removes expired attachment caches
  - Constants: `ATTACHMENT_TTL_HOURS = 24`, `ATTACHMENT_MAX_SIZE_BYTES = 50_000`

### Files Modified

| File | Changes |
|------|---------|
| `app/agents/harness/store/workspace_store.py` | Added workspace_read and workspace_search logging with scope, size, and cache_hit metadata |
| `app/agents/unified/tools/workspace_tools.py` | Added get_cached_attachment() and cleanup_expired_attachments() functions |
| `app/agents/unified/tools/__init__.py` | Exported new functions and TTL constants |

### Architecture Decisions

1. **Log Levels**: Cache hits logged at debug level (avoid log spam), DB operations at info level
2. **Query Truncation**: Search queries truncated to 50 chars in logs to prevent log bloat
3. **TTL Enforcement**: TTL checked at read time (lazy expiration) + explicit cleanup function available
4. **Metadata Storage**: Expiration metadata stored in file's value.metadata field

### Key Features

- **Workspace Operation Logging**:
  ```python
  # Logged automatically on operations:
  logger.info("workspace_read", scope="session", namespace="scratch", key="notes.md", ...)
  logger.info("workspace_search", scope="session", query="error", result_count=3, ...)
  logger.info("workspace_write", scope="customer", content_size_bytes=1024, ...)
  ```

- **Attachment TTL Helpers**:
  ```python
  from app.agents.unified.tools import (
      cache_attachment_summary,
      get_cached_attachment,
      cleanup_expired_attachments,
  )

  # Cache with 24h TTL
  await cache_attachment_summary(store, "attach-123", "Summary text...")

  # Retrieve (returns None if expired)
  summary = await get_cached_attachment(store, "attach-123")

  # Cleanup expired attachments
  deleted = await cleanup_expired_attachments(store)
  ```

### Notes

- All observability is designed for LangSmith integration (structured logging with metadata)
- Rate limits already protect against runaway tool calls (from Phase 1)
- Session cleanup should be called after ticket resolution or session timeout
- Attachment cleanup can be scheduled via Celery or called on-demand

---

## Plan Completion Summary

All 7 phases of the Context Engineering Improvements plan are now complete:

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 0** | Core Infrastructure Refactoring | ✅ Complete |
| **Phase 1** | Workspace Tools for Agent | ✅ Complete |
| **Phase 2** | Issue-Pattern Memory | ✅ Complete |
| **Phase 3** | Large Result Eviction | ✅ Complete |
| **Phase 4** | Issue-Category Playbooks | ✅ Complete |
| **Phase 5** | Observability & Rate Limits | ✅ Complete |
| **Phase 6** | TTL & Cleanup | ✅ Complete |

### Total Changes Summary

**New Files Created:**
- `app/agents/unified/tools/workspace_tools.py` - Workspace file tools
- `app/agents/unified/tools/__init__.py` - Package exports
- `app/agents/harness/store/issue_resolution_store.py` - Issue resolution tracking
- `app/agents/unified/playbooks/__init__.py` - Playbooks package
- `app/agents/unified/playbooks/extractor.py` - Playbook extractor with trust workflow
- `app/agents/unified/playbooks/enricher.py` - Playbook enricher with Model Registry

**Files Modified:**
- `app/agents/harness/store/workspace_store.py` - Multi-scope routing, path validation, observability
- `app/agents/harness/store/__init__.py` - Added exports
- `app/agents/harness/middleware/eviction_middleware.py` - Workspace integration, size caps
- `app/agents/unified/prompts.py` - Workspace guidance in coordinator prompt

**Migrations Applied:**
1. `add_store_content_search_index` - GIN index for content search
2. `add_issue_resolutions_table_v3` - Issue resolutions with vector search
3. `add_playbook_learned_entries_table` - Playbook entries with trust status


## 2025-12-10 - Post-review fixes

### Completed
- Added the missing Supabase migrations required by workspace search, issue resolution memory, and learned playbooks

### Files Modified
- `supabase/migrations/202512101000_add_store_content_search_index.sql` - Generates `content_text` and trigram GIN index for workspace search
- `supabase/migrations/202512101010_add_issue_resolutions_table_v3.sql` - Creates issue_resolutions table, supporting indexes, RLS policy, and `search_similar_resolutions` RPC
- `supabase/migrations/202512101020_add_playbook_learned_entries_table.sql` - Creates learned playbook entries table with trust status, indexes, and service-role RLS policy

### Notes
- Apply these migrations before using workspace search, issue resolution similarity, or learned playbook features. Policies are service-role scoped to avoid accidental exposure.
