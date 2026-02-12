# Database Schema Reference

Last updated: 2026-02-12

> Companion reference split from `docs/database-schema.md`. Contains full table definitions, vector search, RLS, functions, and migration history.

---

## 1. Table Reference

### 1.1 Chat System

#### `chat_sessions`

Primary table for conversation sessions.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | SERIAL | No | - | Primary key |
| `user_id` | VARCHAR | No | - | User identifier from JWT |
| `title` | VARCHAR | No | - | Session title |
| `agent_type` | VARCHAR | No | `'primary'` | Agent type: `primary`, `log_analysis`, `research`, `router` |
| `created_at` | TIMESTAMPTZ | Yes | `now()` | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Yes | `now()` | Last update |
| `last_message_at` | TIMESTAMPTZ | Yes | `now()` | Last message timestamp |
| `is_active` | BOOLEAN | Yes | `true` | Active status |
| `metadata` | JSONB | Yes | `'{}'` | Custom metadata |
| `message_count` | INTEGER | Yes | `0` | Cached message count |

**Constraints**:
- `user_id` must be non-empty
- `title` must be non-empty
- `agent_type` IN (`primary`, `log_analysis`, `research`, `router`)

**Indexes**:
- `(user_id, agent_type, is_active)` - User session lookup

---

#### `chat_messages`

Individual messages within sessions.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | SERIAL | No | - | Primary key |
| `session_id` | INTEGER | No | - | FK to chat_sessions |
| `message_type` | VARCHAR | No | `'user'` | Type: `user`, `assistant`, `system` |
| `content` | TEXT | No | - | Message content |
| `agent_type` | VARCHAR | Yes | - | Agent that generated message |
| `created_at` | TIMESTAMPTZ | Yes | `now()` | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Yes | `now()` | Last update |
| `metadata` | JSONB | Yes | `'{}'` | Custom metadata |

**Constraints**:
- `content` must be non-empty
- FK `session_id` → `chat_sessions.id`

---

#### `agent_configuration`

Per-agent-type settings.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `agent_type` | VARCHAR | - | Primary key |
| `max_active_sessions` | INTEGER | `5` | Max sessions per user |
| `max_message_length` | INTEGER | `10000` | Max message chars |
| `session_timeout_hours` | INTEGER | `24` | Inactivity timeout |

---

### 1.2 FeedMe Document Processing

#### `feedme_conversations`

Document ingestion records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | BIGSERIAL | No | - | Primary key |
| `uuid` | UUID | No | `uuid_generate_v4()` | Version group ID |
| `title` | TEXT | No | - | Document title |
| `original_filename` | TEXT | Yes | - | Source filename |
| `raw_transcript` | TEXT | No | - | Raw content |
| `parsed_content` | TEXT | Yes | - | Parsed/cleaned content |
| `processing_status` | TEXT | Yes | `'pending'` | Status: `pending`, `processing`, `completed`, `failed` |
| `approval_status` | TEXT | Yes | `'pending'` | Workflow: `pending`, `processed`, `approved`, `rejected`, `published` |
| `folder_id` | INTEGER | Yes | - | FK to folders |
| `version` | INTEGER | No | `1` | Version number |
| `is_active` | BOOLEAN | No | `true` | Active version flag |
| `mime_type` | VARCHAR | Yes | - | File MIME type |
| `pages` | INTEGER | Yes | - | Page count (PDFs) |
| `extraction_confidence` | FLOAT | Yes | - | AI extraction confidence |
| `processing_method` | TEXT | Yes | - | `gemini_vision`, `ocr` |
| `created_at` | TIMESTAMPTZ | No | `now()` | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | No | `now()` | Last update |

**Approval Workflow Fields**:
- `approved_by`, `approved_at`, `rejected_at`, `reviewer_notes`

**Processing Fields**:
- `processing_started_at`, `processing_completed_at`, `processing_error`

**Quality Fields**:
- `quality_score` (0.0-1.0), `high_quality_examples`, `medium_quality_examples`, `low_quality_examples`

---

#### `feedme_folders`

Organization folders for documents.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | SERIAL | - | Primary key |
| `uuid` | UUID | `gen_random_uuid()` | Public identifier |
| `name` | TEXT | - | Folder name |
| `color` | TEXT | `'#0095ff'` | Display color |
| `description` | TEXT | - | Optional description |
| `created_by` | TEXT | - | Creator user ID |

---

#### `feedme_text_chunks`

Chunked content with embeddings for semantic search.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | BIGSERIAL | No | - | Primary key |
| `conversation_id` | BIGINT | No | - | FK to conversations |
| `folder_id` | BIGINT | Yes | - | FK to folders |
| `chunk_index` | INTEGER | No | - | Chunk sequence number |
| `content` | TEXT | No | - | Chunk text |
| `metadata` | JSONB | No | `'{}'` | Chunk metadata |
| `embedding` | VECTOR(3072) | Yes | - | Gemini embedding |
| `created_at` | TIMESTAMPTZ | No | `now()` | Creation timestamp |

**Indexes**:
- IVFFlat on `embedding` using `vector_cosine_ops`

---

### 1.3 Knowledge Base

#### `mailbird_knowledge`

Primary knowledge base articles.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | BIGSERIAL | No | - | Primary key |
| `url` | TEXT | No | - | Article URL (unique) |
| `content` | TEXT | Yes | - | Plain text content |
| `markdown` | TEXT | Yes | - | Markdown content |
| `embedding` | VECTOR(3072) | Yes | - | Gemini embedding |
| `metadata` | JSONB | Yes | - | Article metadata |
| `scraped_at` | TIMESTAMPTZ | No | `now()` | Last scraped |
| `created_at` | TIMESTAMPTZ | Yes | `now()` | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Yes | `now()` | Last update |

**Indexes**:
- IVFFlat on `embedding` using `vector_cosine_ops`
- UNIQUE on `url`

**Current Row Count**: ~263 articles

---

#### `web_research_snapshots`

Cached web research results.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | BIGSERIAL | No | - | Primary key |
| `url` | TEXT | No | - | Page URL (unique) |
| `title` | TEXT | Yes | - | Page title |
| `content` | TEXT | Yes | - | Extracted content |
| `source` | TEXT | Yes | `'tavily'` | Source: `tavily`, `firecrawl` |
| `similarity_hint` | FLOAT | Yes | - | Relevance score |
| `embedding` | VECTOR(3072) | Yes | - | Optional embedding |
| `created_by` | UUID | Yes | - | Creator user |
| `created_at` | TIMESTAMPTZ | No | `now()` | Creation timestamp |

---

### 1.4 LangGraph Persistence

#### `langgraph_threads`

Conversation threads for LangGraph workflows.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `uuid_generate_v4()` | Primary key |
| `user_id` | UUID | No | - | Owner user |
| `session_id` | INTEGER | Yes | - | FK to chat_sessions |
| `thread_name` | TEXT | Yes | - | Display name |
| `thread_type` | VARCHAR | Yes | `'conversation'` | Type: `conversation`, `task`, `workflow`, `debug` |
| `status` | VARCHAR | Yes | `'active'` | Status: `active`, `paused`, `completed`, `archived` |
| `parent_thread_id` | UUID | Yes | - | FK for forked threads |
| `current_checkpoint_id` | UUID | Yes | - | Latest checkpoint |
| `checkpoint_count` | INTEGER | Yes | `0` | Total checkpoints |
| `total_tokens_used` | INTEGER | Yes | `0` | Cumulative tokens |
| `total_messages` | INTEGER | Yes | `0` | Message count |
| `metadata` | JSONB | Yes | `'{}'` | Custom metadata |
| `config` | JSONB | Yes | `'{}'` | Thread configuration |
| `tags` | TEXT[] | Yes | `'{}'` | Classification tags |

---

#### `langgraph_checkpoints`

State snapshots for thread persistence.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `uuid_generate_v4()` | Primary key |
| `thread_id` | UUID | No | - | FK to threads |
| `version` | INTEGER | No | - | Version number (>0) |
| `channel` | VARCHAR | No | `'main'` | Channel name |
| `checkpoint_type` | VARCHAR | Yes | `'full'` | Type: `full`, `delta`, `snapshot` |
| `is_latest` | BOOLEAN | Yes | `false` | Latest flag |
| `state` | JSONB | No | `'{}'` | Full state |
| `delta_from_parent` | JSONB | Yes | - | Delta changes |
| `graph_state` | JSONB | Yes | `'{}'` | LangGraph state |
| `pending_tasks` | JSONB | Yes | `'[]'` | Pending task queue |
| `completed_tasks` | JSONB | Yes | `'[]'` | Completed tasks |
| `execution_time_ms` | INTEGER | Yes | - | Execution time |
| `tokens_used` | INTEGER | Yes | - | Token usage |
| `parent_checkpoint_id` | UUID | Yes | - | FK for delta chains |

---

#### `langgraph_checkpoint_blobs`

Binary/large data for checkpoints.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `checkpoint_id` | UUID | FK to checkpoints |
| `blob_key` | VARCHAR | Blob identifier |
| `blob_type` | VARCHAR | Type (default: `state`) |
| `data` | BYTEA | Binary data |
| `data_text` | TEXT | Text data |
| `compressed` | BOOLEAN | Compression flag |
| `size_bytes` | INTEGER | Data size |
| `checksum` | VARCHAR | Data checksum |

---

#### `langgraph_checkpoint_writes`

Write-ahead log for checkpoint durability.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `thread_id` | UUID | FK to threads |
| `checkpoint_id` | UUID | FK to checkpoints |
| `channel` | VARCHAR | Target channel |
| `operation` | VARCHAR | Operation: `create`, `update`, `partial_update`, `delete` |
| `write_data` | JSONB | Write payload |
| `status` | VARCHAR | Status: `pending`, `processing`, `completed`, `failed` |
| `sequence_number` | BIGINT | Ordering sequence |

---

#### `langgraph_channels`

Channel configuration per thread.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | UUID | - | Primary key |
| `thread_id` | UUID | - | FK to threads |
| `channel_name` | VARCHAR | - | Channel identifier |
| `channel_type` | VARCHAR | `'standard'` | Channel type |
| `config` | JSONB | `'{}'` | Channel config |
| `retention_policy` | JSONB | `{"max_age_days": 30, "max_versions": 100}` | Retention rules |
| `is_active` | BOOLEAN | `true` | Active flag |
| `last_checkpoint_id` | UUID | - | Latest checkpoint FK |

---

#### `langgraph_checkpoint_cache`

Performance cache for hot checkpoints.

| Column | Type | Description |
|--------|------|-------------|
| `checkpoint_id` | UUID | Primary key, FK to checkpoints |
| `thread_id` | UUID | FK to threads |
| `cached_state` | JSONB | Cached state |
| `cache_version` | INTEGER | Cache version |
| `hit_count` | INTEGER | Access count |
| `expires_at` | TIMESTAMPTZ | Expiration (default: +1 hour) |

---

#### `langgraph_thread_switch_cache`

Optimizes thread switching (<100ms target).

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | UUID | PK part 1 |
| `thread_id` | UUID | PK part 2, FK to threads |
| `last_checkpoint_state` | JSONB | Cached state |
| `last_messages` | JSONB | Recent messages |
| `summary` | TEXT | Thread summary |
| `access_count` | INTEGER | Usage count |

---

#### `langgraph_thread_access`

Shared thread access control.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | UUID | - | Primary key |
| `thread_id` | UUID | - | FK to threads |
| `user_id` | UUID | - | Granted user |
| `access_level` | VARCHAR | `'read'` | Level: `read`, `write`, `admin` |
| `granted_by` | UUID | - | Granting user |
| `expires_at` | TIMESTAMPTZ | - | Optional expiration |

---

### 1.5 Zendesk Integration

#### `zendesk_pending_tickets`

Processing queue for Zendesk tickets.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | BIGSERIAL | No | - | Primary key |
| `ticket_id` | BIGINT | No | - | Zendesk ticket ID (unique) |
| `brand_id` | TEXT | Yes | - | Zendesk brand |
| `subject` | TEXT | Yes | - | Ticket subject |
| `description` | TEXT | Yes | - | Ticket description |
| `requester_hashed` | TEXT | Yes | - | Hashed requester email |
| `payload` | JSONB | No | `'{}'` | Full webhook payload |
| `status` | TEXT | No | `'pending'` | Status: `pending`, `retry`, `processing`, `processed`, `failed` |
| `retry_count` | INTEGER | No | `0` | Retry attempts (max 10) |
| `next_attempt_at` | TIMESTAMPTZ | Yes | - | Next retry time |
| `last_error` | TEXT | Yes | - | Last error message |
| `processed_at` | TIMESTAMPTZ | Yes | - | Completion timestamp |

**Current Row Count**: ~422 tickets

---

#### `zendesk_macros`

Cached Zendesk macros with embeddings.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `gen_random_uuid()` | Primary key |
| `zendesk_id` | BIGINT | No | - | Zendesk macro ID (unique) |
| `title` | TEXT | No | - | Macro title |
| `description` | TEXT | Yes | - | Macro description |
| `comment_value` | TEXT | Yes | - | Plain text template |
| `comment_value_html` | TEXT | Yes | - | HTML template |
| `actions` | JSONB | Yes | `'[]'` | Macro actions |
| `active` | BOOLEAN | Yes | `true` | Active status |
| `usage_7d` | INTEGER | Yes | `0` | 7-day usage count |
| `usage_30d` | INTEGER | Yes | `0` | 30-day usage count |
| `embedding` | VECTOR(3072) | Yes | - | Semantic embedding |
| `synced_at` | TIMESTAMPTZ | Yes | `now()` | Last sync time |

**Current Row Count**: ~812 macros

---

#### `zendesk_usage`

Monthly API usage tracking.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `month_key` | TEXT | - | Primary key (YYYY-MM) |
| `calls_used` | INTEGER | `0` | API calls used |
| `budget` | INTEGER | `350` | Monthly budget |

---

#### `zendesk_daily_usage`

Daily Gemini call tracking.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `usage_date` | DATE | - | Primary key |
| `gemini_calls_used` | INTEGER | `0` | Gemini calls used |
| `gemini_daily_limit` | INTEGER | `1000` | Daily limit |

---

#### `zendesk_webhook_events`

Replay protection for webhooks.

| Column | Type | Description |
|--------|------|-------------|
| `sig_key` | TEXT | Primary key (signature hash) |
| `ts` | BIGINT | Timestamp |
| `seen_at` | TIMESTAMPTZ | First seen time |

---

#### `issue_resolutions`

Learned issue patterns with embeddings.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | UUID | No | Primary key |
| `ticket_id` | TEXT | No | Source ticket |
| `category` | TEXT | No | Issue category |
| `problem_summary` | TEXT | No | Problem description |
| `solution_summary` | TEXT | No | Resolution description |
| `was_escalated` | BOOLEAN | Yes | Escalation flag |
| `kb_articles_used` | TEXT[] | Yes | Referenced KB articles |
| `macros_used` | TEXT[] | Yes | Used macros |
| `embedding` | VECTOR(3072) | Yes | Semantic embedding |

**Current Row Count**: ~746 resolutions

---

#### `playbook_learned_entries`

Extracted playbooks from resolved tickets.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | - | Primary key |
| `conversation_id` | TEXT | No | - | Source conversation (unique) |
| `category` | TEXT | No | - | Issue category |
| `problem_summary` | TEXT | No | - | Problem description |
| `resolution_steps` | JSONB | No | - | Array of steps |
| `diagnostic_questions` | JSONB | Yes | - | Follow-up questions |
| `final_solution` | TEXT | No | - | Final resolution |
| `why_it_worked` | TEXT | Yes | - | Explanation |
| `status` | TEXT | Yes | `'pending_review'` | Review status: `pending_review`, `approved`, `rejected` |
| `quality_score` | FLOAT | Yes | - | Quality rating (0-1) |

**Current Row Count**: ~806 entries

---

### 1.6 Global Knowledge & Feedback

#### `sparrow_feedback`

User feedback submissions.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | BIGSERIAL | - | Primary key |
| `user_id` | TEXT | - | User identifier |
| `kind` | TEXT | `'feedback'` | Entry type |
| `feedback_text` | TEXT | - | Feedback content |
| `selected_text` | TEXT | - | Referenced text |
| `attachments` | JSONB | `'[]'` | Attachments array |
| `embedding` | VECTOR(3072) | - | Semantic embedding |
| `status` | TEXT | `'received'` | Processing status |

---

#### `sparrow_corrections`

User-submitted corrections.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | BIGSERIAL | - | Primary key |
| `user_id` | TEXT | - | User identifier |
| `kind` | TEXT | `'correction'` | Entry type |
| `incorrect_text` | TEXT | - | Wrong content |
| `corrected_text` | TEXT | - | Correct content |
| `explanation` | TEXT | - | Correction reason |
| `embedding` | VECTOR(3072) | - | Semantic embedding |
| `status` | TEXT | `'received'` | Processing status |

---

### 1.7 Authentication & API Keys

#### `user_api_keys`

Encrypted user API keys.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | SERIAL | No | Primary key |
| `user_id` | VARCHAR | No | User identifier |
| `user_uuid` | UUID | Yes | Supabase Auth UUID |
| `api_key_type` | VARCHAR | No | Type: `gemini`, `tavily`, `firecrawl` |
| `encrypted_key` | TEXT | No | Encrypted API key |
| `key_name` | VARCHAR | Yes | Display name |
| `masked_key` | VARCHAR | Yes | Display mask (e.g., `sk-...xyz`) |
| `is_active` | BOOLEAN | No | Active status |
| `last_used_at` | TIMESTAMPTZ | Yes | Last usage time |

---

#### `api_key_audit_log`

API key operation audit trail.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `user_id` | VARCHAR | User identifier |
| `api_key_type` | VARCHAR | Key type |
| `operation` | VARCHAR | Operation: `CREATE`, `UPDATE`, `DELETE`, `USE`, `VALIDATE` |
| `operation_details` | JSONB | Operation metadata |
| `ip_address` | INET | Client IP |
| `user_agent` | TEXT | Client user agent |

---

### 1.8 Workspace Store

#### `store`

Generic key-value store for workspace files.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `prefix` | TEXT | - | PK part 1 (namespace) |
| `key` | TEXT | - | PK part 2 (file key) |
| `value` | JSONB | - | File content |
| `content_text` | TEXT | - | Generated: `value->>'content'` for FTS |
| `expires_at` | TIMESTAMPTZ | - | Optional expiration |
| `ttl_minutes` | INTEGER | - | TTL setting |

**Current Row Count**: ~1280 entries

**Used for**:
- `/scratch/*` - Ephemeral working files
- `/progress/*` - Session progress notes
- `/goals/*` - Active goals
- `/handoff/*` - Session handoff context

---

#### `store_vectors`

Vector embeddings for store entries.

| Column | Type | Description |
|--------|------|-------------|
| `prefix` | TEXT | PK part 1, FK to store |
| `key` | TEXT | PK part 2, FK to store |
| `field_name` | TEXT | PK part 3 |
| `embedding` | VECTOR(3072) | Embedding vector |

---

### 1.9 System Tables

#### `feature_flags`

Runtime feature toggles.

| Column | Type | Description |
|--------|------|-------------|
| `key` | TEXT | Primary key |
| `value` | JSONB | Flag configuration |
| `updated_at` | TIMESTAMPTZ | Last update |

---

#### `cache_invalidation_tracker`

Cache invalidation signals.

| Column | Type | Description |
|--------|------|-------------|
| `cache_key` | VARCHAR | Primary key |
| `invalidated_at` | TIMESTAMPTZ | Invalidation time |
| `reason` | TEXT | Invalidation reason |

---

## 2. Vector Search

### Embedding Configuration

- **Model**: `models/gemini-embedding-001`
- **Dimensions**: 3072
- **Distance Metric**: Cosine similarity
- **Index Type**: IVFFlat (inverted file flat)

### Tables with Embeddings

| Table | Column | Index |
|-------|--------|-------|
| `mailbird_knowledge` | `embedding` | IVFFlat |
| `feedme_text_chunks` | `embedding` | IVFFlat |
| `zendesk_macros` | `embedding` | IVFFlat |
| `issue_resolutions` | `embedding` | None (exact search) |
| `sparrow_feedback` | `embedding` | None |
| `sparrow_corrections` | `embedding` | None |
| `web_research_snapshots` | `embedding` | None |
| `store_vectors` | `embedding` | None |

### Search RPCs

**`search_mailbird_knowledge_rpc(query_embedding, match_count, match_threshold)`**
- Cosine similarity search on knowledge base
- Returns: `id`, `url`, `content`, `markdown`, `metadata`, `similarity`

**`search_web_research_snapshots(query_embedding, match_count)`**
- Search cached web research
- Returns: `id`, `url`, `title`, `content`, `source`, `similarity`

---

## 3. Row Level Security

All public tables have RLS enabled with these patterns:

### User Isolation Pattern

```sql
-- Users can only access their own rows
CREATE POLICY "user_isolation" ON table_name
FOR ALL USING (user_id = auth.uid());
```

### Service Role Bypass

```sql
-- Service role can access all rows
CREATE POLICY "service_bypass" ON table_name
FOR ALL USING (auth.role() = 'service_role');
```

### Tables with RLS

| Table | Policy Pattern |
|-------|---------------|
| `chat_sessions` | User isolation + service bypass |
| `chat_messages` | Via session ownership |
| `user_api_keys` | User isolation |
| `feedme_conversations` | User isolation + folder ownership |
| `feedme_text_chunks` | Via conversation ownership |
| `langgraph_*` | User isolation + access grants |
| `mailbird_knowledge` | Read-all, write-service-only |
| `zendesk_*` | Service-only access |

---

## 4. Functions and Triggers

### Session Management

**`check_session_limits_health()`**
- Validates session limit constraints are working

**`deactivate_oldest_session(user_id, agent_type)`**
- Deactivates oldest session when limit reached

**`cleanup_expired_sessions(batch_size DEFAULT 1000)`**
- Batch cleanup of expired sessions

### LangGraph Operations

**`create_checkpoint(thread_id, channel, state, metadata)`**
- Creates new checkpoint with version tracking

**`get_latest_checkpoint(thread_id, channel DEFAULT 'main')`**
- Retrieves latest checkpoint for thread

**`fork_thread(source_thread_id, checkpoint_id, user_id, thread_name)`**
- Creates forked thread from checkpoint

**`cleanup_old_checkpoints(days_to_keep DEFAULT 30, dry_run DEFAULT false)`**
- Removes old checkpoints based on retention

### Triggers

**`auto_transition_approval_status`** on `feedme_conversations`
- Automatically transitions approval workflow states

**`enforce_chat_session_limits_after`** on `chat_sessions`
- Enforces per-user session limits after insert

---

## 5. Migration History

### Migration Naming Convention

```
NNN_description_in_snake_case.sql
```

The repository currently includes mostly numeric migrations plus a small number of legacy date-prefixed files.

### Recent Migrations (Repository Snapshot: Feb 12, 2026)

| Version | Name | Description |
|---------|------|-------------|
| 040 | feedme_single_release_hardening | FeedMe schema, audit, settings, versioning hardening |
| 039 | restore_feedme_examples_tables | Restored FeedMe example tables |
| 038 | alter_status_check_not_valid | Relaxed/updated status check enforcement |
| 037 | add_status_check | Added status check constraints |
| 036 | fix_memory_vector_index | Memory vector index adjustments |
| 036 | create_zendesk_webhook_events | Zendesk webhook event persistence |

### Migration Categories

Representative categories in `app/db/migrations/`:
- Schema creation and table evolution
- Security hardening (RLS/search-path advisories)
- Performance/index optimization
- Feature-specific migrations (FeedMe, Zendesk, Memory UI)
- Corrective fixes for constraints/RPC/indexes

### Total Migration Files in Repository: 46

---

## Related Documentation

- [`docs/backend-architecture.md`](backend-architecture.md) — System design, API reference
- [`docs/zendesk.md`](zendesk.md) — Zendesk pipeline and ticket tables
- [`docs/memory-ui.md`](memory-ui.md) — Memory UI schema extensions
- [`docs/SECURITY.md`](SECURITY.md) — RLS patterns and auth

---

*Run `supabase db pull` for the latest schema.*
