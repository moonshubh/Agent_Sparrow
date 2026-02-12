# Zendesk Operations Reference

> **Last updated**: 2026-02-12
>
> Companion operations/configuration/runbook reference split from `docs/zendesk.md`.

Use this reference for environment/config values, operational runbooks, and coding conventions specific to Zendesk workflows.

---

## 1. Configuration Reference

### 1.1 Core Credentials

| Variable | Default | Description |
|----------|---------|-------------|
| `ZENDESK_ENABLED` | `false` | Enable integration |
| `ZENDESK_SUBDOMAIN` | -- | Zendesk subdomain |
| `ZENDESK_EMAIL` | -- | Zendesk email |
| `ZENDESK_API_TOKEN` | -- | Zendesk API token |
| `ZENDESK_SIGNING_SECRET` | -- | Webhook signing secret |
| `ZENDESK_BRAND_ID` | -- | Default brand ID |

### 1.2 Processing Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ZENDESK_DRY_RUN` | `true` | Dry run mode (no posting) |
| `ZENDESK_POLL_INTERVAL_SEC` | `60` | Queue polling interval (seconds) |
| `ZENDESK_MAX_RETRIES` | `5` | Max retry attempts |
| `ZENDESK_QUEUE_RETENTION_DAYS` | `30` | Queue item retention |
| `ZENDESK_AGENT_PROVIDER` | `google` | LLM provider for agent |
| `ZENDESK_AGENT_MODEL` | `gemini-3-flash-preview` | LLM model for agent |

### 1.3 Content & Formatting Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ZENDESK_USE_HTML` | `true` | Use HTML formatting |
| `ZENDESK_FORMAT_ENGINE` | `markdown_v2` | `legacy` or `markdown_v2` |
| `ZENDESK_FORMAT_STYLE` | `compact` | `compact` or `relaxed` |
| `ZENDESK_HEADING_LEVEL` | `h3` | `h2` or `h3` |
| `ZENDESK_EXCLUDED_STATUSES` | `["solved", "closed"]` | Skip these statuses |
| `ZENDESK_EXCLUDED_TAGS` | `["mac_general__feature_delivered", "mb_spam_suspected"]` | Skip these tags |

### 1.4 Spam Guard Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ZENDESK_SPAM_GUARD_STRICT_ENABLED` | `true` | Enable strict multi-signal spam scoring |
| `ZENDESK_SPAM_SCORE_THRESHOLD` | `0.65` | Score threshold for strict mode |
| `ZENDESK_SPAM_RECIPIENT_BURST_THRESHOLD` | `20` | Recipient count for burst signal |
| `ZENDESK_SPAM_HIGH_RISK_DOMAIN_SUFFIXES` | `["8b.io"]` | Extra high-risk domain suffixes |
| `ZENDESK_SPAM_ALWAYS_BLOCK_EXPLICIT_LINK` | `true` | Hard-block explicit-content + link pattern |

### 1.5 Context & Retrieval Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ZENDESK_WEB_PREFETCH_ENABLED` | `true` | Prefetch web context |
| `ZENDESK_WEB_PREFETCH_PAGES` | `3` | Pages to prefetch |
| `ZENDESK_INTERNAL_RETRIEVAL_MIN_RELEVANCE` | -- | Min relevance for internal retrieval |
| `ZENDESK_INTERNAL_RETRIEVAL_MAX_PER_SOURCE` | -- | Max results per source |
| `ZENDESK_MACRO_MIN_RELEVANCE` | -- | Min relevance for macro retrieval |
| `ZENDESK_FEEDME_MIN_RELEVANCE` | -- | Min relevance for FeedMe retrieval |
| `ZENDESK_ISSUE_PATTERN_MAX_HITS` | `5` | Max similar scenario hits |
| `ZENDESK_ISSUE_PATTERN_MIN_SIMILARITY` | `0.62` | Min similarity for pattern match |

### 1.6 Learning Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ZENDESK_ISSUE_PATTERN_LEARNING_ENABLED` | `true` | Enable pattern learning |
| `ZENDESK_PLAYBOOK_LEARNING_ENABLED` | `true` | Enable playbook extraction |

### 1.7 Memory & Retrieval Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_MEMORY_UI_RETRIEVAL` | `false` | Enable Memory UI as retrieval source |
| `MEMORY_UI_AGENT_ID` | -- | Agent ID for Memory UI queries |
| `MEMORY_UI_TENANT_ID` | -- | Tenant ID for Memory UI queries |

### 1.8 Rate Limiting & Quotas

**Zendesk API limits**:

| Setting | Default | Env Var |
|---------|---------|---------|
| RPM Limit | 240 | `ZENDESK_RPM_LIMIT` |
| Monthly Budget | 1500 | `ZENDESK_MONTHLY_API_BUDGET` |
| Import RPM | 60 | `ZENDESK_IMPORT_RPM_LIMIT` |

**Gemini daily limit**:

| Table | Column | Default |
|-------|--------|---------|
| `zendesk_daily_usage` | `gemini_daily_limit` | 1000 |

Env override: `ZENDESK_GEMINI_DAILY_LIMIT=380`

**Monthly usage tracking**: `zendesk_usage` table with `month_key` (YYYY-MM), `calls_used`, `budget`.

### 1.9 Feature Flag (Database)

**Table**: `feature_flags`, **Key**: `zendesk_enabled`

```json
{
  "enabled": true,
  "dry_run": false,
  "provider": "google",
  "model": "gemini-3-flash-preview"
}
```

### 1.10 Historical Import Settings

| Variable | Description |
|----------|-------------|
| `ZENDESK_WINDOWS_BRAND_IDS` | Windows brand IDs (e.g., `273414`) |
| `ZENDESK_NATURE_FIELD_IDS` | Nature-of-inquiry custom field IDs (comma-separated) |
| `ZENDESK_NATURE_CATEGORY_MAP` | JSON mapping of field values to categories |
| `ZENDESK_NATURE_REQUIRE_FIELD` | Require nature field match (default `true`) |

---

## 2. Operational Runbook

### 2.1 Prerequisites

- `.env` (or `.env.local`) must include Zendesk credentials, Supabase keys, and `ZENDESK_ENABLED=true`
- Set `ZENDESK_DRY_RUN=false` for live note posting
- Virtualenv created and installed

### 2.2 Zendesk Admin Setup

**Create webhook** (Zendesk Admin Center > Apps & Integrations > Webhooks):
- URL: `https://agentsparrow-production.up.railway.app/api/v1/integrations/zendesk/webhook`
- Method: `POST`, Format: `JSON`
- Signing secret: same as `ZENDESK_SIGNING_SECRET`

**Create trigger** (Zendesk Admin Center > Objects and rules > Triggers):
- Conditions: Ticket is Created, Status is New, (optional) Tag does not contain `mb_auto_triaged`
- Actions: Notify active webhook with JSON payload:
```json
{
  "ticket": {
    "id": "{{ticket.id}}",
    "subject": "{{ticket.title}}",
    "description": "{{ticket.description}}",
    "brand_id": "{{ticket.brand.id}}"
  }
}
```

### 2.3 Admin UI Access

The Settings > Zendesk (Admin) panel requires:
- Frontend service env: `API_BASE` (backend URL) and `INTERNAL_API_TOKEN`
- Frontend admin allowlist: `ZENDESK_ADMIN_EMAILS` or `ZENDESK_ADMIN_ROLES`

### 2.4 One-off Ticket Processing

```bash
cd /Users/shubhpatel/Downloads/Agent_Sparrow-Frontend-2.0

./venv/bin/python - <<'PY'
import asyncio
from app.core.settings import settings
from app.integrations.zendesk.scheduler import _generate_reply
from app.integrations.zendesk.client import ZendeskClient

TICKET_ID = 123456  # <-- replace
PROVIDER = getattr(settings, "zendesk_agent_provider", None) or "google"
MODEL = getattr(settings, "zendesk_agent_model", None) or "gemini-3-flash-preview"

async def main():
    zc_read = ZendeskClient(
        subdomain=str(settings.zendesk_subdomain),
        email=str(settings.zendesk_email),
        api_token=str(settings.zendesk_api_token),
        dry_run=True,
    )
    t = zc_read.get_ticket(TICKET_ID) or {}
    subject, desc = t.get("subject"), t.get("description")

    run = await _generate_reply(TICKET_ID, subject, desc, provider=PROVIDER, model=MODEL)
    reply = run.reply

    zc = ZendeskClient(
        subdomain=str(settings.zendesk_subdomain),
        email=str(settings.zendesk_email),
        api_token=str(settings.zendesk_api_token),
        dry_run=False,  # set True to preview without posting
    )
    res = zc.add_internal_note(
        TICKET_ID,
        reply,
        add_tag="mb_auto_triaged",
        use_html=getattr(settings, "zendesk_use_html", True),
    )
    print("Posted:", res.get("ticket", {}).get("id"), res.get("ticket", {}).get("updated_at"))

asyncio.run(main())
PY
```

### 2.5 Batch Processing from a Zendesk View

**Script**: `scripts/zendesk_process_view_batch.py`

| Flag | Description |
|------|-------------|
| `--view-id` or `--view-title` | Zendesk view (title does substring match) |
| `--start-ticket` | Start scanning from this ticket ID |
| `--count` | Number of notes to post |
| `--post` | Actually post (otherwise dry run) |
| `--tag` | Tag to apply (default `mb_auto_triaged`) |
| `--skip-if-tagged` | Skip if already tagged (default `mb_auto_triaged`) |
| `--max-minutes` | Timebox the run (0 disables) |
| `--log-level` | Logging level |

### 2.6 API Endpoints

**Webhook**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/integrations/zendesk/webhook` | POST | Receive webhooks |

**Status & Management**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/integrations/zendesk/health` | GET | Integration health + usage snapshot (requires `X-Internal-Token`) |
| `/api/v1/integrations/zendesk/models` | GET | Available provider/model options (requires `X-Internal-Token`) |
| `/api/v1/integrations/zendesk/feature` | POST | Toggle feature flag/dry-run mode (requires `X-Internal-Token`) |

**Admin**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/integrations/zendesk/admin/health` | GET | Admin health/status snapshot |
| `/api/v1/integrations/zendesk/admin/queue` | GET | List queue entries (supports pagination/filtering) |
| `/api/v1/integrations/zendesk/admin/queue/{item_id}/retry` | POST | Retry a queue item |
| `/api/v1/integrations/zendesk/admin/queue/retry-batch` | POST | Retry multiple queue items |

**Memory Import**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/memory/import/zendesk-tagged` | POST | Import tickets to memory |
| `/api/v1/memory/import/zendesk-tagged/{task_id}` | GET | Poll import task status |

### 2.7 Scheduler Mode

Enabling `ZENDESK_ENABLED=true` + `ZENDESK_DRY_RUN=false` and running the backend will let the background scheduler drain `zendesk_pending_tickets`. For ad-hoc tickets, prefer the one-off snippet in section 7.4.

Session cleanup: daily maintenance deletes per-ticket workspace data 7 days after `last_public_comment_at`.

### 2.8 Troubleshooting

| Problem | Solution |
|---------|----------|
| 401/403 posting | Verify `ZENDESK_EMAIL`/`ZENDESK_API_TOKEN` and that the token has ticket update rights |
| Empty/plan-like replies | Switch model (e.g., Grok to Gemini) for more support-oriented tone |
| Numbering resets in steps | Ensure `ZENDESK_USE_HTML=true` with current codebase (HTML formatter fix uses `start` attribute) |
| Pattern context missing | Verify Supabase connectivity and `store` table has `content_text` configured |
| LangSmith rate limiting | Monthly trace limits can be hit during batch runs; non-blocking but reduces observability |
| Tavily quota exhausted | Web search falls back to Minimax automatically |
| mem0 not installed | System logs warning and continues with Memory UI only |
| Recursion limit override | `ZENDESK_RECURSION_LIMIT` (30) may be overridden by global LangGraph default (400); check `GraphState` construction |
| Zendesk 404 on attachments | Attachment URLs are signed and expire; scheduler fetches via API |
| Context report missing | Check serialization in `scheduler.py`; fallbacks should catch JSON errors |

### 2.9 Telemetry

- `zendesk_run_telemetry` logs tool usage, memory stats, and evidence summaries per ticket
- All telemetry captured as LangSmith metadata (no separate metrics infrastructure)
- See `docs/DEVELOPMENT.md` for LangSmith observability details

---

## 3. Coding Conventions

Guidelines for agents (Codex, Claude Code) working on Zendesk code.

### 3.1 File Organization

All Zendesk integration code lives in `app/integrations/zendesk/`:
- `scheduler.py` -- Ticket processing orchestration, context report persistence, attachment handling
- `client.py` -- Zendesk API wrapper, attachment fetching (`public_only=True`), PII redaction
- `attachments.py` -- URL scrubbing, attachment type summarization, log file detection
- `spam_guard.py` -- Rate-limiting and deduplication for internal note posting
- `security.py` -- HMAC signature verification
- `exclusions.py` -- Skip logic for tickets
- `endpoints.py` -- Webhook endpoint
- `historical_import.py` -- Batch ticket import
- `formatters/markdown_v2.py` -- Markdown v2 formatting engine

Playbook code lives in `app/agents/unified/playbooks/`:
- `enricher.py` -- LLM extraction to `playbook_learned_entries`
- `extractor.py` -- Compiles playbooks from source + approved entries
- `review_cli.py` -- Markdown export/import/compile workflow

### 3.2 Key Rules

**Attachments**:
- Only process public comments -- never expose private/internal data to the agent
- Fetch attachments via Zendesk API (signed URLs expire); do not embed raw URLs in agent output
- Scrub all Zendesk attachment URLs from generated content before posting
- Summarize attachment types for agent context instead of passing raw file data

**Memory**:
- Zendesk runs use `use_server_memory=True` for read access
- Zendesk runs are read-only for memory -- they do not write new memories
- mem0 is optional; if missing, only Memory UI is queried

**Reply formatting**:
- Internal notes must use "Suggested Reply only" format
- A sanitization pass removes internal planning artifacts, scratchpad references, and raw tool output
- Replies must follow policy: proper greeting, empathetic tone, no unsupported claims
- No log requests if log attachments are already present

**Context report**:
- Every processed ticket gets a `context_report` persisted to `status_details`
- Uses JSON serialization with fallback for non-serializable values

**Testing**:
```bash
# Set ZENDESK_DRY_RUN=false in .env for real note posting
# Start system, then check:
# 1. zendesk_pending_tickets status in Supabase
# 2. Backend logs: grep -i zendesk system_logs/backend/backend.log
# 3. Internal notes posted to correct tickets
# 4. context_report persisted in status_details
```

See `docs/RELIABILITY.md` for retry patterns and fallback conventions.

---

## Cross-References

| Topic | Document |
|-------|----------|
| General architecture | `docs/backend-architecture.md` |
| Retry and fallback patterns | `docs/RELIABILITY.md` |
| Build commands and debugging | `docs/DEVELOPMENT.md` |
| Database schema | `docs/database-schema.md` |
| Observability | `docs/observability.md` |
| Model configuration | `app/core/config/models.yaml` |
