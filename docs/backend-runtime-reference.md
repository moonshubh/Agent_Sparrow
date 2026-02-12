# Backend Runtime Reference

> **Last updated**: 2026-02-12
>
> Companion reference for operational runtime details split from `docs/backend-architecture.md`.

This document contains operational/reference-heavy backend details to keep the core architecture doc focused and faster to load for autonomous coding tasks.

---

## 1. FeedMe Pipeline

### Overview

**Location**: `app/feedme/`

FeedMe is the document ingestion pipeline for processing PDFs and transcripts into searchable knowledge.

### Processing Pipeline

```
Upload -> Validation -> Queue (Celery) -> Processing -> Chunking -> Embedding -> Storage
                                              |
                                    Gemini Vision (primary)
                                    or OCR fallback
```

#### Stage 1: Upload (`POST /api/v1/feedme/conversations/upload`)
- Validate file size (max 50MB for PDFs, 10MB for other files)
- Check MIME type
- SHA-256 duplicate detection (30-day window)
- Create conversation record with `pending` status

#### Stage 2: Background Processing (Celery)
- **Primary**: Gemini Vision API for PDF extraction (pages -> markdown)
- **Fallback**: OCR (EasyOCR) when AI extraction fails
- Model fallback: `gemini-2.5-flash-preview-09-2025` when primary model fails
- Text normalization and cleanup

#### Stage 3: Chunking
- Split extracted text into chunks
- Max tokens per chunk: 8,000
- Overlap: 500 tokens

#### Stage 4: Embedding Generation
- Model: `models/gemini-embedding-001`
- Dimensions: 3,072
- Store in `feedme_text_chunks` table

### Celery Tasks

**Location**: `app/feedme/tasks.py`

| Task | Description |
|------|-------------|
| `process_transcript` | Main orchestration task |
| `generate_text_chunks_and_embeddings` | Chunk and embed content |
| `generate_ai_tags` | Auto-generate content tags (with Celery retry on failure) |
| `import_zendesk_tagged` | Import Zendesk tickets as mb_playbook memories |

### PDF Processing Methods

| Method | When Used | Model |
|--------|-----------|-------|
| `gemini_vision` | Primary | Gemini 2.5 Flash Lite (from `internal.feedme` in models.yaml) |
| `ocr_fallback` | When AI extraction fails | EasyOCR |
| `pypdf` | Simple text extraction | N/A |

### Approval Workflow

```
pending -> processed -> approved -> published
                     \-> rejected
```

**Endpoints**:
- `GET /api/v1/feedme/approval/pending` -- List pending approval items
- `GET /api/v1/feedme/approval/conversation/{conversation_id}/preview` -- Preview decision payload
- `POST /api/v1/feedme/approval/conversation/{conversation_id}/decide` -- Approve/reject conversation text
- `POST /api/v1/feedme/approval/bulk` -- Batch approval operations

### WebSocket Progress

**Endpoint**: `ws://localhost:8000/ws/feedme/progress/{task_id}`

Events: `processing_started`, `stage_update` (extraction, chunking, embedding), `processing_completed`, `processing_failed`.

### FeedMe Rate Limiting

**GeminiRateTracker** configuration:

| Setting | Default | Env Var |
|---------|---------|---------|
| Max tokens/minute | 250,000 | `FEEDME_MAX_TOKENS_PER_MINUTE` |
| Max tokens/chunk | 8,000 | `FEEDME_MAX_TOKENS_PER_CHUNK` |
| Concurrent limit | 5 | `FEEDME_PDF_CONCURRENT_LIMIT` |
| Processing timeout | 30s | `FEEDME_PDF_PROCESSING_TIMEOUT` |

See `docs/feedme-hardening-notes.md` for the full FeedMe hardening sprint details.

---

## 2. API Reference

### AG-UI Streaming (Primary Chat Interface)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/agui/stream` | POST | Primary AG-UI streaming endpoint |
| `/api/v1/agui/stream/health` | GET | Health check for AG-UI system |
| `/api/v1/agui/subgraphs/stream` | POST | Subgraphs demo endpoint |

**`POST /api/v1/agui/stream` -- Request Body** (AG-UI `RunAgentInput`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `thread_id` | string | Yes | Conversation thread identifier |
| `run_id` | string | Yes | Run identifier |
| `messages` | array | No | AG-UI message array |
| `state` | object | No | Initial state for the agent |
| `tools` | array | No | Available tools |
| `context` | array | No | Additional context |
| `forwarded_props` | object | No | Custom properties (see below) |

**Forwarded Properties**:

| Property | Type | Description |
|----------|------|-------------|
| `session_id` | string | Session identifier for persistence |
| `trace_id` | string | Trace ID for LangSmith correlation |
| `provider` | string | LLM provider (`google`, `xai`, `openrouter`, `minimax`) |
| `model` | string | Model identifier |
| `agent_type` | string | Agent type (`primary`, `log_analysis`) |
| `use_server_memory` | boolean | Enable server-side memory |
| `force_websearch` | boolean | Force web search execution |
| `websearch_max_results` | integer | Max web search results |
| `attachments` | array | File attachments (max 10MB each) |

Response: Server-Sent Events (SSE) stream with AG-UI protocol events.

### Chat Sessions

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/chat-sessions` | POST | Optional | Create new chat session |
| `/api/v1/chat-sessions` | GET | Optional | List chat sessions |
| `/api/v1/chat-sessions/{session_id}` | GET | Required | Get session with messages |
| `/api/v1/chat-sessions/{session_id}` | PUT | Optional | Update session |
| `/api/v1/chat-sessions/{session_id}` | DELETE | Optional | Soft delete session |
| `/api/v1/chat-sessions/{session_id}/messages` | POST | Optional | Add message to session |
| `/api/v1/chat-sessions/{session_id}/messages` | GET | Optional | List session messages |
| `/api/v1/chat-sessions/{session_id}/messages/{message_id}` | PUT | Optional | Update message |
| `/api/v1/chat-sessions/{session_id}/messages/{message_id}/append` | PATCH | Optional | Append to message |
| `/api/v1/chat-sessions/stats/user` | GET | Required | User statistics |
| `/api/v1/chat-sessions/test` | GET | None | API health test |

### FeedMe Document Processing

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/feedme/conversations` | GET | List conversations |
| `/api/v1/feedme/conversations/{conversation_id}` | GET | Get conversation details |
| `/api/v1/feedme/conversations/{conversation_id}` | PUT | Update conversation |
| `/api/v1/feedme/conversations/{conversation_id}` | DELETE | Delete conversation |
| `/api/v1/feedme/conversations/{conversation_id}/status` | GET | Check processing status |
| `/api/v1/feedme/conversations/upload` | POST | Upload document (SHA-256 duplicate detection) |
| `/api/v1/feedme/conversations/{conversation_id}/reprocess` | POST | Re-run processing pipeline |
| `/api/v1/feedme/conversations/{conversation_id}/mark-ready` | POST | Mark conversation as KB-ready |
| `/api/v1/feedme/conversations/{conversation_id}/ai-note/regenerate` | POST | Regenerate AI note |
| `/api/v1/feedme/conversations/{conversation_id}/approve` | POST | Approve conversation output |
| `/api/v1/feedme/conversations/{conversation_id}/reject` | POST | Reject conversation output |
| `/api/v1/feedme/conversations/{conversation_id}/edit` | PUT | Create a new edited version |
| `/api/v1/feedme/conversations/{conversation_id}/versions` | GET | List version history |
| `/api/v1/feedme/conversations/{conversation_id}/versions/{version_number}` | GET | Get specific version |
| `/api/v1/feedme/conversations/{conversation_id}/versions/{version_1}/diff/{version_2}` | GET | Diff two versions |
| `/api/v1/feedme/conversations/{conversation_id}/revert/{target_version}` | POST | Revert to prior version |
| `/api/v1/feedme/folders` | GET | List folders |
| `/api/v1/feedme/folders` | POST | Create folder |
| `/api/v1/feedme/folders/{folder_id}` | PUT | Update folder |
| `/api/v1/feedme/folders/{folder_id}` | DELETE | Delete folder |
| `/api/v1/feedme/folders/{folder_id}/conversations` | GET | List conversations in folder |
| `/api/v1/feedme/folders/assign` | POST | Bulk assign conversations to folder (max 50) |
| `/api/v1/feedme/stats/overview` | GET | Stats overview (queue depth, failure rate, latency, SLA) |
| `/api/v1/feedme/analytics` | GET | Legacy analytics payload |
| `/api/v1/feedme/analytics/pdf-storage` | GET | PDF storage analytics |
| `/api/v1/feedme/gemini-usage` | GET | Gemini usage metrics |
| `/api/v1/feedme/embedding-usage` | GET | Embedding usage metrics |
| `/api/v1/feedme/health` | GET | FeedMe subsystem health |
| `/api/v1/feedme/settings` | GET | Get FeedMe settings |
| `/api/v1/feedme/settings` | PUT | Update FeedMe settings |
| `/api/v1/feedme/approval/pending` | GET | List pending approval items |
| `/api/v1/feedme/approval/conversation/{conversation_id}/preview` | GET | Preview approval payload |
| `/api/v1/feedme/approval/conversation/{conversation_id}/decide` | POST | Approve/reject decision |
| `/api/v1/feedme/approval/bulk` | POST | Batch approval operations |
| `/api/v1/feedme/approval/stats` | GET | Approval workflow stats |
| `/api/v1/feedme/approval/queue/summary` | GET | Approval queue summary |

### Log Analysis

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/agent/logs` | POST | Submit logs for analysis (JSON) |
| `/api/v1/agent/logs/stream` | POST | Stream log analysis (SSE) |
| `/api/v1/agent/logs/sessions` | GET | List log analysis sessions |
| `/api/v1/agent/logs/sessions/{session_id}` | GET | Get session details |
| `/api/v1/agent/logs/sessions/{session_id}/insights` | POST | Generate additional insights for a session |
| `/api/v1/agent/logs/rate-limits` | GET | Rate-limit status for log-analysis calls |

### Research

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/agent/research` | POST | Submit research query (JSON) |
| `/api/v1/agent/research/stream` | POST | Stream research (SSE) |

### Models & Configuration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/models` | GET | List available models |
| `/api/v1/models/config` | GET | Model configuration (registry + providers) |
| `/api/v1/agents` | GET | List agent metadata |

### Rate Limiting

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/rate-limits/status` | GET | Current rate limit status |
| `/api/v1/rate-limits/usage` | GET | Detailed usage statistics |
| `/api/v1/rate-limits/health` | GET | Rate limiter health check |
| `/api/v1/rate-limits/check/{bucket}` | POST | Check if request allowed |
| `/api/v1/rate-limits/config` | GET | Current rate limit configuration |
| `/api/v1/rate-limits/metrics` | GET | Prometheus-style metrics |
| `/api/v1/rate-limits/reset` | POST | Reset limits (requires confirmation) |

### Memory UI

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/memory/list` | GET | List memories |
| `/api/v1/memory/search` | GET | Search memories |
| `/api/v1/memory/{memory_id:uuid}` | GET/PUT/DELETE | Memory CRUD by ID |
| `/api/v1/memory/graph` | GET | Graph view data |
| `/api/v1/memory/import/zendesk-tagged` | POST | Import Zendesk tickets as mb_playbook memories |
| `/api/v1/memory/import/zendesk-tagged/{task_id}` | GET | Poll import task status |
| `/api/v1/memory/assets/{bucket}/{object_path:path}` | GET | Authenticated image serving proxy |

See `docs/memory-ui.md` for Memory UI details.

### Global Knowledge

No public `global-knowledge` API routes are currently registered in `app.main`.
Global knowledge behavior is handled inside unified-agent services and tools.

### Message Feedback

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/feedback/message` | POST | Submit message feedback (thumbs up/down) |

### Metadata

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/metadata/memory/{session_id}/stats` | GET | Memory service statistics |
| `/api/v1/metadata/quotas/status` | GET | Quota and rate limit status |
| `/api/v1/metadata/sessions/{session_id}/traces/{trace_id}` | GET | Trace metadata |
| `/api/v1/metadata/link-preview` | GET | Link preview metadata |
| `/api/v1/metadata/health` | GET | Metadata service health |

### Zendesk Integration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/integrations/zendesk/webhook` | POST | Zendesk webhook receiver |
| `/api/v1/integrations/zendesk/health` | GET | Integration health + usage snapshot (internal token) |
| `/api/v1/integrations/zendesk/models` | GET | Available Zendesk model options (internal token) |
| `/api/v1/integrations/zendesk/feature` | POST | Toggle feature flag/dry-run mode (internal token) |
| `/api/v1/integrations/zendesk/admin/health` | GET | Admin health snapshot (internal token) |
| `/api/v1/integrations/zendesk/admin/queue` | GET | Queue listing with pagination/filter (internal token) |
| `/api/v1/integrations/zendesk/admin/queue/{item_id}/retry` | POST | Retry one queue item (internal token) |
| `/api/v1/integrations/zendesk/admin/queue/retry-batch` | POST | Retry multiple queue items (internal token) |

See `docs/zendesk.md` for Zendesk-specific pipeline and context engineering details.

### Search Tools

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/tools/web-search` | POST | Execute web search query |
| `/api/v1/tools/internal-search` | POST | Execute internal KB/FeedMe search |
| `/api/v1/tools/tavily/self-test` | GET | Tavily connectivity test |

### Authentication (When Enabled)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/signin` | POST | User login |
| `/api/v1/auth/signout` | POST | User logout |
| `/api/v1/auth/signup` | POST | User signup |
| `/api/v1/auth/refresh` | POST | Refresh access token |
| `/api/v1/auth/me` | GET | Current user info |
| `/api/v1/auth/me` | PUT | Update current user |
| `/api/v1/api-keys/` | GET | List API keys |
| `/api/v1/api-keys/` | POST | Create API key |
| `/api/v1/api-keys/{api_key_type}` | PUT | Update API key |
| `/api/v1/api-keys/{api_key_type}` | DELETE | Revoke API key |
| `/api/v1/api-keys/status` | GET | API key status summary |

### Agent Interrupts

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/v2/agent/graph/run` | POST | Run graph with interrupt-capable state |
| `/api/v1/v2/agent/graph/threads/{thread_id}` | GET | Retrieve graph thread state |

### WebSocket

| Endpoint | Protocol | Description |
|----------|----------|-------------|
| `/ws/feedme/progress/{task_id}` | WebSocket | FeedMe task progress |

### General

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Welcome message |
| `/health` | GET | Application health |
| `/health/global-knowledge` | GET | Global knowledge health |
| `/security-status` | GET | Security configuration status |

---

## 3. Configuration Reference

All settings are loaded from environment variables via `app/core/settings.py`.

### LLM Provider Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | -- | Google Gemini API key |
| `XAI_API_KEY` | -- | xAI/Grok API key |
| `XAI_DEFAULT_MODEL` | `grok-4-1-fast-reasoning` | Default xAI model |
| `XAI_REASONING_ENABLED` | `true` | Enable Grok reasoning |
| `OPENROUTER_API_KEY` | -- | OpenRouter API key |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter endpoint |
| `OPENROUTER_DEFAULT_MODEL` | `x-ai/grok-4.1-fast` | Default OpenRouter model |
| `MINIMAX_API_KEY` | -- | Minimax API key |
| `MINIMAX_CODING_PLAN_API_KEY` | -- | Minimax Coding Plan key (preferred) |

### Primary Agent Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PRIMARY_AGENT_PROVIDER` | `google` | Default provider (`google`, `xai`, `openrouter`, `minimax`) |
| `PRIMARY_AGENT_MODEL` | `gemini-3-flash-preview` | Default model ID |
| `PRIMARY_AGENT_TEMPERATURE` | `0.2` | Generation temperature (0.0-2.0) |
| `THINKING_BUDGET` | -- | Token budget for reasoning (-1 for dynamic) |
| `PRIMARY_AGENT_FORMATTING` | `natural` | Output format (`natural`, `strict`, `lean`) |
| `PRIMARY_AGENT_QUALITY_LEVEL` | `balanced` | Quality level |
| `TRACE_MODE` | `narrated` | Thinking trace mode (`narrated`, `hybrid`, `provider_reasoning`, `off`) |

### Supabase Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPABASE_URL` | -- | Supabase project URL |
| `SUPABASE_ANON_KEY` | -- | Supabase anonymous key |
| `SUPABASE_SERVICE_KEY` | -- | Supabase service role key |
| `SUPABASE_JWT_SECRET` | -- | JWT verification secret |
| `SUPABASE_DB_CONN` | -- | Direct PostgreSQL connection string |

### Redis Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `CACHE_TTL_SEC` | `3600` | Default cache TTL in seconds |

### LangSmith Tracing

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGSMITH_TRACING_ENABLED` | `false` | Enable LangSmith tracing |
| `LANGSMITH_API_KEY` | -- | LangSmith API key |
| `LANGSMITH_ENDPOINT` | -- | Custom LangSmith endpoint |
| `LANGSMITH_PROJECT` | -- | Project name for runs |

### FeedMe Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FEEDME_ENABLED` | `true` | Enable FeedMe module |
| `FEEDME_HTML_ENABLED` | `true` | Allow HTML document processing |
| `FEEDME_PDF_ENABLED` | `true` | Enable PDF processing |
| `FEEDME_MAX_FILE_SIZE_MB` | `10` | Max file size in MB |
| `FEEDME_MAX_PDF_SIZE_MB` | `50` | Max PDF size in MB |
| `FEEDME_PDF_PROCESSING_TIMEOUT` | `30` | PDF processing timeout (seconds) |
| `FEEDME_PDF_CONCURRENT_LIMIT` | `5` | Max concurrent PDF jobs |
| `FEEDME_MAX_TOKENS_PER_MINUTE` | `250000` | Token rate limit |
| `FEEDME_MAX_TOKENS_PER_CHUNK` | `8000` | Max tokens per chunk |
| `FEEDME_CHUNK_OVERLAP_TOKENS` | `500` | Chunk overlap |
| `FEEDME_MODEL_NAME` | `gemini-2.5-flash-lite-preview-09-2025` | FeedMe model |
| `FEEDME_AI_PDF_ENABLED` | `true` | Use Gemini Vision for PDF |
| `FEEDME_AI_MAX_PAGES` | `10` | Max pages per PDF call |
| `FEEDME_AI_PAGES_PER_CALL` | `3` | Pages per API call |
| `FEEDME_CELERY_BROKER` | `redis://localhost:6379/1` | Celery broker URL |
| `FEEDME_RESULT_BACKEND` | `redis://localhost:6379/2` | Celery result backend |
| `FEEDME_RATE_LIMIT_PER_MINUTE` | `15` | Upload rate limit |
| `FEEDME_REQUESTS_PER_DAY_LIMIT` | `1000` | Daily request limit |

### Gemini Grounding Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_GROUNDING_SEARCH` | `false` | Enable Gemini search grounding |
| `GROUNDING_MODEL` | `gemini-2.5-flash-preview-09-2025` | Grounding model |
| `GROUNDING_MAX_RESULTS` | `5` | Max search results |
| `GROUNDING_TIMEOUT_SEC` | `10.0` | Search timeout |
| `GROUNDING_SNIPPET_CHARS` | `480` | Snippet length |
| `GROUNDING_MINUTE_LIMIT` | `30` | Searches per minute |
| `GROUNDING_DAILY_LIMIT` | `1000` | Searches per day |

### Tavily Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TAVILY_API_KEY` | -- | Tavily API key |
| `TAVILY_DEFAULT_SEARCH_DEPTH` | `advanced` | Search depth |
| `TAVILY_DEFAULT_MAX_RESULTS` | `10` | Max results |
| `TAVILY_INCLUDE_IMAGES` | `true` | Include images |

### Firecrawl Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FIRECRAWL_MCP_ENABLED` | `true` | Enable Firecrawl MCP |
| `FIRECRAWL_API_KEY` | -- | Firecrawl API key |
| `FIRECRAWL_DEFAULT_MAX_AGE_MS` | `172800000` | Cache age (48 hours) |
| `FIRECRAWL_DEFAULT_TIMEOUT_SEC` | `60.0` | Request timeout |
| `FIRECRAWL_RATE_LIMIT_RPM` | `60` | Requests per minute |

### Rate Limiting Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_USE_MEMORY` | `true` | Use in-memory rate limiting |
| `RATE_LIMIT_REDIS_URL` | `redis://localhost:6379` | Redis URL for rate limiting |
| `RATE_LIMIT_REDIS_PREFIX` | `mb_sparrow_rl` | Redis key prefix |
| `RATE_LIMIT_REDIS_DB` | `3` | Redis database number |
| `GEMINI_FLASH_RPM_LIMIT` | `10` | Flash requests/minute |
| `GEMINI_FLASH_RPD_LIMIT` | `250` | Flash requests/day |
| `GEMINI_PRO_RPM_LIMIT` | `100` | Pro requests/minute |
| `GEMINI_PRO_RPD_LIMIT` | `1000` | Pro requests/day |
| `CIRCUIT_BREAKER_ENABLED` | `true` | Enable circuit breaker |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Failures before open |
| `CIRCUIT_BREAKER_TIMEOUT` | `60` | Recovery timeout (seconds) |
| `CIRCUIT_BREAKER_SUCCESS_THRESHOLD` | `3` | Successes to close |
| `RATE_LIMIT_SAFETY_MARGIN` | `0.2` | Safety buffer (20%) |

### Memory Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_AGENT_MEMORY` | `false` | Enable memory service |
| `AGENT_MEMORY_DEFAULT_ENABLED` | `false` | Memory on by default |
| `MEMORY_BACKEND` | `supabase` | Memory backend type |
| `MEMORY_COLLECTION_PRIMARY` | `mem_primary` | Primary collection |
| `MEMORY_COLLECTION_LOGS` | `mem_logs` | Logs collection |
| `MEMORY_TOP_K` | `5` | Results to retrieve |
| `MEMORY_CHAR_BUDGET` | `2000` | Character budget |
| `MEMORY_TTL_SEC` | `180` | Cache TTL |
| `MEMORY_EMBED_PROVIDER` | `gemini` | Embedding provider |
| `MEMORY_EMBED_MODEL` | `models/gemini-embedding-001` | Embedding model |
| `MEMORY_EMBED_DIMS` | `3072` | Embedding dimensions |
| `ENABLE_MEMORY_UI_RETRIEVAL` | `false` | Enable Memory UI as retrieval source |
| `MEMORY_UI_AGENT_ID` | -- | Agent ID for Memory UI queries |
| `MEMORY_UI_TENANT_ID` | -- | Tenant ID for Memory UI queries |

### Zendesk Integration Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ZENDESK_ENABLED` | `false` | Enable Zendesk integration |
| `ZENDESK_SUBDOMAIN` | -- | Zendesk subdomain |
| `ZENDESK_EMAIL` | -- | Zendesk email |
| `ZENDESK_API_TOKEN` | -- | Zendesk API token |
| `ZENDESK_SIGNING_SECRET` | -- | Webhook signing secret |
| `ZENDESK_BRAND_ID` | -- | Default brand ID |
| `ZENDESK_DRY_RUN` | `true` | Dry run mode (no posting) |
| `ZENDESK_POLL_INTERVAL_SEC` | `60` | Polling interval |
| `ZENDESK_RPM_LIMIT` | `300` | API requests/minute |
| `ZENDESK_MONTHLY_API_BUDGET` | `350` | Monthly API budget |
| `ZENDESK_GEMINI_DAILY_LIMIT` | `380` | Gemini calls/day for Zendesk |
| `ZENDESK_MAX_RETRIES` | `5` | Max retry attempts |
| `ZENDESK_QUEUE_RETENTION_DAYS` | `30` | Queue retention |
| `ZENDESK_WEB_PREFETCH_ENABLED` | `true` | Enable web context prefetch |
| `ZENDESK_WEB_PREFETCH_PAGES` | `3` | Pages to prefetch |
| `ZENDESK_USE_HTML` | `true` | Use HTML notes |
| `ZENDESK_FORMAT_ENGINE` | `markdown_v2` | Note formatting engine |
| `ZENDESK_EXCLUDED_STATUSES` | `["solved", "closed"]` | Skip these statuses |
| `ZENDESK_EXCLUDED_TAGS` | `["mac_general__feature_delivered"]` | Skip these tags |
| `ZENDESK_ISSUE_PATTERN_LEARNING_ENABLED` | `true` | Enable pattern learning |
| `ZENDESK_PLAYBOOK_LEARNING_ENABLED` | `true` | Enable playbook extraction |

### Security Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SKIP_AUTH` | `false` | Skip authentication (dev only) |
| `DEVELOPMENT_USER_ID` | `00000000-0000-0000-0000-000000000000` | Dev user ID |
| `ENABLE_AUTH_ENDPOINTS` | `true` | Enable auth endpoints |
| `ENABLE_API_KEY_ENDPOINTS` | `true` | Enable API key endpoints |
| `FORCE_PRODUCTION_SECURITY` | `true` | Force production mode |
| `JWT_SECRET_KEY` | -- | JWT signing secret |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token expiry |
| `API_KEY_ENCRYPTION_SECRET` | -- | API key encryption secret (32+ bytes) |
| `ALLOWED_OAUTH_EMAIL_DOMAINS` | `["getmailbird.com"]` | Allowed OAuth domains |
| `INTERNAL_API_TOKEN` | -- | Internal service token |

See `docs/SECURITY.md` for the full security checklist and patterns.

### Chat Session Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_SESSIONS_PER_AGENT` | `5` | Max active sessions per agent type |
| `CHAT_MESSAGE_MAX_LENGTH` | `10000` | Max message length |
| `CHAT_TITLE_MAX_LENGTH` | `255` | Max session title length |
| `CHAT_SESSION_CLEANUP_DAYS` | `30` | Days before cleanup |
| `CHAT_DEFAULT_PAGE_SIZE` | `10` | Default pagination size |
| `CHAT_MAX_PAGE_SIZE` | `100` | Max pagination size |

---

## 4. Services Reference

### Knowledge Retrieval Service

**Location**: `app/services/knowledge_base/hybrid_retrieval.py`

Implements hybrid retrieval primitives used by unified-agent internal search flows.

### Memory Service

**Location**: `app/memory/`

Long-term memory using `mem0` library (v1 via `mem0ai==1.0.3`).

**Key Functions**:
- `retrieve()` -- Get relevant facts for context
- `add()` -- Persist extracted facts/memories
- `delete()` -- Remove stored memory records

**Configuration**:
- Backend: Supabase
- Collection: `mem_primary`
- Top-K: 5 results
- Embedding dimension clamp to 2000 for vecs/pgvector index limits
- Collection fallback for dimension mismatch (`*_dim{n}`)

**Memory UI Integration**: When `ENABLE_MEMORY_UI_RETRIEVAL=true`, the unified agent retrieves from both mem0 and Memory UI sources. Feedback (thumbs up/down) propagates as confidence score changes (fixed 5% steps).

### Embedding Service

**Locations**:
- `app/db/embedding/utils.py` (registry-backed Gemini embeddings)
- `app/feedme/embeddings/embedding_pipeline.py` (FeedMe pipeline embeddings)

Vector embedding generation for semantic search.

- Primary model/dimensions are sourced from `app/core/config/models.yaml` via `app/db/embedding_config.py`.
- FeedMe pipeline also includes a local SentenceTransformer flow for selected operations.

### Tracing Service

**Location**: `app/core/tracing/`

LangSmith tracing configuration. Initialized via `configure_langsmith()` at startup.

All agent runs are automatically traced with metadata:

| Metadata | Content |
|----------|---------|
| `model_selection` | Task type, selected model, health trace |
| `memory_stats` | Facts retrieved/written |
| `fallback_occurred` | Boolean flag |
| `agent_config` | Provider, model, feature flags |

**Tags**: `model:gemini-2.5-flash`, `task_type:log_analysis`, `memory_enabled`

See `docs/observability.md` for monitoring playbooks.

### Skills System

**Location**: `app/agents/skills/`

Auto-detected skills based on message content:

| Trigger | Skills Activated |
|---------|-----------------|
| Default | Writing, Empathy |
| `pdf`, `docx` | Document handling |
| `brainstorm` | Creative thinking |
| `research company` | Business research |

---

## 5. Rate Limiting

### Architecture

**Location**: `app/core/rate_limiting/`

The rate limiting system uses a **token bucket algorithm** with **circuit breaker pattern**. Rate limits are bucket-based and driven by `models.yaml`.

**Components**:
- `GeminiRateLimiter` -- Main rate limiter class
- `RateLimitConfig` -- Configuration from environment
- `CircuitBreaker` -- Failure protection per model
- `MemoryRateLimiter` -- In-memory fallback when Redis is unavailable

### Rate Limit Configuration Source

All rate limits come from `models.yaml` under the `rate_limits` key for each model. A global `safety_margin` (default 6%) is applied automatically to all quotas.

Example from `models.yaml`:
```yaml
rate_limiting:
  safety_margin: 0.06

coordinators:
  google:
    rate_limits:
      rpm: 1000
      tpm: 1000000
      rpd: 10000
```

### Circuit Breaker States

| State | Description | Behavior |
|-------|-------------|----------|
| **CLOSED** | Normal operation | Requests allowed |
| **OPEN** | Too many failures (>5) | Requests blocked |
| **HALF_OPEN** | Testing recovery | Limited requests allowed |

Configuration: `CIRCUIT_BREAKER_FAILURE_THRESHOLD=5`, `CIRCUIT_BREAKER_TIMEOUT=60s`, `CIRCUIT_BREAKER_SUCCESS_THRESHOLD=3`.

### Rate Limit Check Response

```python
class RateLimitResult:
    allowed: bool          # Whether request is allowed
    blocked_by: str | None # "rpm", "rpd", "circuit_breaker", or None
    retry_after: int | None # Seconds until retry
    metadata: RateLimitMetadata
```

### Rate Limit Error Responses

| Status | Error Type | Retry-After |
|--------|------------|-------------|
| 429 | Rate limit exceeded | 60 seconds |
| 503 | Circuit breaker open | 300 seconds |
| 503 | Service unavailable | 120 seconds |

### FeedMe-Specific Rate Limiting

Rate-limiter fail-open fallbacks are implemented for FeedMe processing when Redis/loop state is temporarily unavailable (see `app/feedme/processors/gemini_pdf_processor.py` and `app/feedme/tasks.py`).

See `docs/RELIABILITY.md` for retry patterns, database query retries, and web tool fallback chains.

---

## Authentication & Security

### Authentication Flow

1. **JWT-based Auth** -- Standard Bearer token in Authorization header
2. **Guest Mode** -- Cookie-based guest user ID for unauthenticated users (`guest_<uuid>`)
3. **Development Bypass** -- `SKIP_AUTH=true` disables all auth checks

### Security Headers

CORS settings:
- **Allowed Origins**: Configurable via `CORS_ALLOW_ORIGINS` env var (defaults to localhost:3000, 3001, 3010)
- **Origin Regex**: LAN IPs (`192.168.x.x:3000`) allowed in non-production mode
- **Credentials**: `allow_credentials=True`
- **Methods**: All (`*`)
- **Headers**: All (`*`)

FeedMe mutation endpoints use JWT role-claim admin guard (`app/api/v1/endpoints/feedme/auth.py`), while read endpoints remain open.

See `docs/SECURITY.md` for the full security checklist.

---

## Related Documentation

| Document | Location | Description |
|----------|----------|-------------|
| Database Schema | `docs/database-schema.md` | Complete schema reference |
| Zendesk Integration | `docs/zendesk.md` | Zendesk pipeline and context engineering |
| Observability | `docs/observability.md` | LangSmith monitoring playbooks |
| Reliability Patterns | `docs/RELIABILITY.md` | Retries, fallbacks, error handling |
| Security | `docs/SECURITY.md` | Env vars, auth patterns, checklist |
| Development | `docs/DEVELOPMENT.md` | Build commands, debugging, CI |
| Coding Standards | `docs/CODING_STANDARDS.md` | Full TS + Python conventions |
| FeedMe Hardening | `docs/feedme-hardening-notes.md` | FeedMe hardening sprint details |
| Memory UI | `docs/memory-ui.md` | Memory UI architecture and hardening |
