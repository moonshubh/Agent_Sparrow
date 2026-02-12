# Zendesk Integration

> **Last updated**: 2026-02-12
>
> Canonical Zendesk integration architecture and pipeline behavior reference.

---

## Table of Contents

1. [Overview & Architecture](#1-overview--architecture)
2. [Pipeline & Processing Flow](#2-pipeline--processing-flow)
3. [Context Engineering](#3-context-engineering)
4. [Reply Formatting & Quality Gates](#4-reply-formatting--quality-gates)
5. [Pattern Learning & Playbook Workflow](#5-pattern-learning--playbook-workflow)
6. [Zendesk Operations Reference](zendesk-operations.md)

---

## 1. Overview & Architecture

### 1.1 Purpose

The Zendesk integration automatically processes support tickets by:
- Receiving tickets via webhook
- Processing with the Unified Agent (full toolset minus image generation)
- Generating support responses using KB, macros, learned patterns, and web research
- Posting internal notes with suggested replies

### 1.2 Architecture

```
Zendesk Webhook -> Signature Verification -> Queue (zendesk_pending_tickets)
                                                  |
                                     Exclusion Check + Spam Guard
                                                  |
                              Context Assembly (patterns, playbooks, retrieval)
                                                  |
                                        Unified Agent Run
                                                  |
                                  Quality Gate + Sanitization + Formatting
                                                  |
                                       Internal Note Posted
                                                  |
                                  Pattern Learning (optional)
```

### 1.3 Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Webhook Endpoint | `app/integrations/zendesk/endpoints.py` | Receive and validate webhooks |
| Scheduler | `app/integrations/zendesk/scheduler.py` | Orchestrate ticket processing |
| Client | `app/integrations/zendesk/client.py` | Zendesk API wrapper, attachment fetching, PII redaction |
| Security | `app/integrations/zendesk/security.py` | HMAC signature verification |
| Exclusions | `app/integrations/zendesk/exclusions.py` | Skip logic for tickets |
| Spam Guard | `app/integrations/zendesk/spam_guard.py` | Rate-limiting and deduplication for note posting |
| Attachments | `app/integrations/zendesk/attachments.py` | URL scrubbing, type summarization, log file detection |
| Formatters | `app/integrations/zendesk/formatters/markdown_v2.py` | Markdown v2 formatting engine |
| Historical Import | `app/integrations/zendesk/historical_import.py` | Batch ticket import for pattern learning |
| Playbook Enricher | `app/agents/unified/playbooks/enricher.py` | LLM extraction to `playbook_learned_entries` |
| Playbook Extractor | `app/agents/unified/playbooks/extractor.py` | Compiles playbooks from source + approved entries |
| Review CLI | `app/agents/unified/playbooks/review_cli.py` | Markdown export/import/compile workflow |
| Batch Script | `scripts/zendesk_process_view_batch.py` | Process tickets from a Zendesk view |

---

## 2. Pipeline & Processing Flow

### 2.1 Webhook Reception

**Endpoint**: `POST /api/v1/integrations/zendesk/webhook`

1. Receive raw webhook payload
2. Verify HMAC-SHA256 signature (`x-zendesk-webhook-signature` header)
3. Check timestamp freshness (replay protection via `zendesk_webhook_events` table)
4. Extract ticket ID and brand ID
5. Queue for processing in `zendesk_pending_tickets`

**Signature computation**:
```
Signature = HMAC-SHA256(timestamp + "." + body, ZENDESK_SIGNING_SECRET)
```

### 2.2 Ticket Queue

**Table**: `zendesk_pending_tickets`

| Status | Description |
|--------|-------------|
| `pending` | Awaiting processing |
| `retry` | Failed, scheduled for retry |
| `processing` | Currently being processed |
| `processed` | Successfully completed |
| `failed` | Permanently failed |

**Key fields**: `ticket_id` (unique), `brand_id`, `subject`, `description`, `payload` (JSONB), `retry_count` (max 10), `next_attempt_at`, `last_error`, `status_details` (JSONB context report + spam telemetry).

### 2.3 Exclusion Logic

**Location**: `app/integrations/zendesk/exclusions.py`

Tickets are skipped when:
- Status is in `ZENDESK_EXCLUDED_STATUSES` (default: `solved`, `closed`)
- Has tags in `ZENDESK_EXCLUDED_TAGS` (default: `mac_general__feature_delivered`, `mb_spam_suspected`)
- Brand ID does not match configured brand

### 2.4 Spam Guard

Before agent generation, the scheduler runs multi-signal spam scoring:
- Explicit content + external link patterns
- Link/domain risk assessment (configurable high-risk domain suffixes)
- Recipient burst detection
- Low-support intent signals
- Explicit image checks (when available)

On spam detection:
- No customer-ready suggested reply is generated
- Ticket receives `mb_spam_suspected` plus one reason tag (`mb_spam_explicit_link`, `mb_spam_recipient_burst`, `mb_spam_explicit_image`, `mb_spam_suspicious_link`)
- Queue `status_details` includes spam telemetry: `spam_score`, `spam_signals`, `spam_reason_tag`, `recipient_count`, `top_link_domains`, `explicit_image_confidence`
- A short internal note is posted

**False-positive recovery**: Remove spam tags in Zendesk, then retry via `POST /api/v1/integrations/zendesk/admin/queue/{item_id}/retry`.

### 2.5 Processing Pipeline

The scheduler (`app/integrations/zendesk/scheduler.py`) orchestrates:

```
Queue Poll
  -> Exclusion Check
  -> Spam Guard
  -> PII Redaction
  -> Category Inference
  -> Context Assembly (similar scenarios, playbooks, internal retrieval, web prefetch)
  -> Agent Invocation
  -> Rewrite Pass (if draft is not customer-ready)
  -> Quality Gate + Sanitization
  -> Formatting (HTML)
  -> Internal Note Post
  -> Pattern Learning (if enabled)
  -> Context Report Persistence
```

### 2.6 Category Inference

Tickets are categorized into:

| Category | Trigger Keywords |
|----------|------------------|
| `account_setup` | add account, set up, login, password |
| `sync_auth` | oauth, imap, smtp, gmail, outlook |
| `licensing` | license, subscription, billing, refund |
| `sending` | can't send, smtp error, relay |
| `performance` | slow, lag, freeze, crash, high cpu |
| `features` | feature request, how to, template |

**Inference priority**:
1. High-confidence match from similar resolutions (similarity >= 0.78)
2. Majority vote from top 5 similar resolutions
3. Keyword heuristics on ticket text

### 2.7 Agent Invocation

```python
GraphState(
    messages=[HumanMessage(content=ticket_text)],
    forwarded_props={
        "is_zendesk_ticket": True,  # Use support tool set
        "session_id": session_id,
        "trace_id": trace_id,
        "provider": "google",
        "model": "gemini-3-flash-preview",
    },
)
```

Key behaviors:
- **Recursion limit**: 30 (vs default 400) -- sufficient for KB search + FeedMe + web research + subagent + response
- **Full toolset**: Uses `get_registered_tools()` (excluding only image generation)
- **Memory**: Read-only via `use_server_memory=True`; Memory UI retrieval gated by `ENABLE_MEMORY_UI_RETRIEVAL`; mem0 is optional
- **Attachments**: Only public comments processed; Zendesk attachment URLs scrubbed from output; log files routed to `log_diagnoser` subagent automatically

### 2.8 ZendeskReplyResult

| Field | Type | Description |
|-------|------|-------------|
| `reply` | str | Generated reply text |
| `session_id` | str | Agent session ID |
| `ticket_id` | str | Zendesk ticket ID |
| `category` | str | Inferred issue category |
| `redacted_ticket_text` | str | PII-redacted ticket content |
| `kb_articles_used` | list[str] | Referenced KB articles |
| `macros_used` | list[str] | Applied macros |
| `learning_messages` | list | Messages for pattern learning |

### 2.9 Context Report Persistence

Every processed ticket gets a `context_report` persisted to `zendesk_pending_tickets.status_details`:
- Uses JSON serialization with fallback for non-serializable values
- Includes evidence summary, tool usage, and memory retrieval stats

---

## 3. Context Engineering

### 3.1 Context Assembly Overview

Before agent execution, the scheduler populates workspace files and constructs a prompt with structured context sections.

**Pipeline flow**:
1. Input: Zendesk ticket `subject`, `description`, `attachments`
2. PII redaction
3. Internal retrieval preflight (Supabase-backed): macros, KB, FeedMe via `db_unified_search_tool`; adds policy macros when applicable
4. Pattern-first preflight: searches `issue_resolutions`, writes `/context/similar_scenarios.md`, infers category, compiles playbook
5. Optional: web prefetch (Firecrawl / Tavily) when internal sources are weak
6. Prompt assembly: `prompt_text = user_query + internal_context + web_context`
7. Unified agent run

### 3.2 Workspace Artifacts

**Session-scoped** (per ticket, via Supabase `store` table with prefix `workspace:zendesk:{session_id}`):

| Path | Content |
|------|---------|
| `/context/similar_scenarios.md` | Pattern matches from `IssueResolutionStore` |
| `/context/similar_resolutions.md` | Legacy alias for compatibility |
| `/context/ticket_category.json` | Best-effort category inference |
| `/context/ticket_playbook.md` | Pointer to the relevant compiled playbook |

**Global-scoped**:

| Path | Content |
|------|---------|
| `/playbooks/{category}.md` | Compiled "gold standard" playbook for the category |
| `/playbooks/source/{category}.md` | Curated source playbooks (human-maintained) |

### 3.3 Similar Scenario Retrieval

**Source**: `issue_resolutions` table (~746 resolutions)

**Search process**:
1. Infer initial category from ticket text
2. Search resolutions with same category (min similarity 0.80)
3. If no matches, cross-category search (min similarity 0.88)
4. Filter by lexical overlap (prevent false positives)

**Similarity thresholds**:

| Condition | Threshold |
|-----------|-----------|
| Auto-include | >= 0.86 |
| Category-specific | >= 0.80 |
| Cross-category | >= 0.88 |

**Fallback chain**: If `search_similar_resolutions` RPC is unavailable, falls back to client-side cosine similarity over stored embeddings, then lexical overlap as a last resort.

**Format injected into context**:
```markdown
# Similar Scenarios (auto-retrieved)

Use these as reference patterns. Do NOT mention internal ticket IDs,
similarity scores, or this file in the customer reply.

Ticket: 12345

## Current Ticket (redacted)
[Redacted ticket content]

## Scenario 1 (sync_auth, similarity 0.892)
- Created: 2025-12-15T10:30:00Z

**Problem**
User cannot authenticate with Gmail after enabling 2FA.

**Resolution**
Guide user to generate app password in Google account security settings.
```

**Env knobs**: `ZENDESK_ISSUE_PATTERN_MAX_HITS`, `ZENDESK_ISSUE_PATTERN_MIN_SIMILARITY`.

### 3.4 Playbook Compilation

**Source**: `playbook_learned_entries` table (~806 entries)

**Compilation process**:
1. Load base playbook from `/playbooks/source/{category}.md`
2. Query approved learned entries for category
3. Merge procedures by similarity deduplication
4. Write compiled playbook to `/playbooks/{category}.md`

**Entry structure**:
```json
{
  "category": "sync_auth",
  "problem_summary": "Gmail 2FA authentication failure",
  "resolution_steps": [
    {"step": 1, "action": "Navigate to Google Account Security", "rationale": "..."},
    {"step": 2, "action": "Generate app password", "rationale": "..."}
  ],
  "diagnostic_questions": ["Is 2FA enabled?", "When did the issue start?"],
  "final_solution": "Use app password instead of regular password",
  "status": "approved"
}
```

### 3.5 Internal Retrieval

Retrieval via `db_unified_search_tool` across sources: macros, KB, FeedMe.

**Macro retrieval fallback**: If `search_zendesk_macros` semantic RPC is unavailable, the system falls back to lightweight `ilike` search against `zendesk_macros` table.

**Env knobs**: `ZENDESK_INTERNAL_RETRIEVAL_MIN_RELEVANCE`, `ZENDESK_INTERNAL_RETRIEVAL_MAX_PER_SOURCE`, `ZENDESK_MACRO_MIN_RELEVANCE`, `ZENDESK_FEEDME_MIN_RELEVANCE`.

### 3.6 Existing Guardrails (Baseline)

These are implemented and in production:

1. **Category-seeded similar-scenario retrieval**: Similar scenarios retrieved within the inferred category first; cross-category only with stricter threshold.

2. **Lexical relevance filtering (anti-pollution)**: Before injecting similar scenarios or internal retrieval results, filter out items without meaningful keyword overlap with the current ticket (unless similarity is very high).

3. **Prompt de-templating**: The system no longer mandates a single fixed opener phrase; requires one sentence restating the customer's issue with varied openers. Includes instruction: "If retrieved context seems unrelated, ignore it completely."

### 3.7 Context Failure Modes

| Failure Mode | Description | Current Mitigation |
|--------------|-------------|---------------------|
| Context Poisoning | Incorrect info enters context and compounds | Lexical relevance filtering; memory hygiene |
| Context Distraction | Over-reliance on past behavior vs fresh reasoning | Category seeding constrains retrieval scope |
| Context Confusion | Irrelevant tools/docs cause wrong selection | Source-specific gating; entity overlap checks |
| Context Clash | Contradictory info misleads the agent | Not yet implemented (roadmap Phase 3) |

### 3.8 Roadmap: Context Quality Improvements

The following improvements are designed but **not yet implemented**. They are documented here for incremental execution.

**Phase 1 -- Query Agent**: Replace simple query rewriting with an iterative Query Agent that can extract structured intent, construct optimized retrieval queries, and reformulate on low-confidence results (max 2 attempts). See Section 3.8 above for the full context quality roadmap.

**Phase 2 -- Multi-issue handling**: Decompose multi-intent tickets into sub-queries with per-issue context packs and complexity detection.

**Phase 3 -- Quality-first retrieval**: LLM reranking of candidates, pre-generation clash detection, dynamic token budgets by confidence score.

**Phase 4 -- Output validation**: Post-generation topic drift detection and hybrid high-risk statement detection (keywords + LLM verification).

**Phase 5 -- Procedural memory**: Capture full resolution procedures alongside outcomes, with supervisor approval queue and combined-signal pruning.

**Phase 6 -- Advanced retrieval**: Late chunking for FeedMe conversations, source-specific chunking improvements.

**Phase 7 -- Observability**: Dynamic + static golden test sets, LangSmith integration, weekly regression harness.

---

## 4. Reply Formatting & Quality Gates

### 4.1 Quality Gates

Before posting, responses are validated by `_quality_gate_issues()`.

**Prohibited content**:
- Internal ticket IDs
- Similarity scores
- File references (`/context/`, `/playbooks/`)
- Meta-commentary (`I must output...`, `tool results`)
- Order/reference tokens from customer billing context (e.g., `MAI...` variants replaced with "the order reference you shared")

**Required content**:
- Actionable guidance
- Appropriate tone (empathetic for frustration)

**Section filtering** -- Only "Suggested Reply" content is kept. These sections are stripped: Issue Summary, Root Cause Analysis, Relevant Resources, Follow-up Considerations.

**Meta-line detection** -- Lines starting with these prefixes are removed:
`assistant:`, `system:`, `developer:`, `tool:`, `analysis:`, `reasoning:`, `thought process:`, `scratchpad:`

**Inline pattern filtering** -- These patterns are removed from output:
`zendesk ticket scenario`, `I must/should/need to output`, `do not mention/include/output`, tool references (`db-retrieval`, `kb_search`)

### 4.2 Formatting Engines

Two formatter engines are available:

| Engine | Location | Status |
|--------|----------|--------|
| Markdown v2 (default) | `app/integrations/zendesk/formatters/markdown_v2.py` | Active default |
| Legacy | `app/integrations/zendesk/scheduler.py::_format_zendesk_internal_note_html` | Fallback |

**Engine selection** is in `app/integrations/zendesk/scheduler.py::_format_html_for_zendesk()`, controlled by `ZENDESK_FORMAT_ENGINE` (default `markdown_v2`).

### 4.3 Zendesk HTML Constraints

Zendesk's rich-text rendering has specific quirks:
- HTML support is limited and sanitized differently for public vs internal notes
- `<p>` inside `<li>` renders unpredictably
- Lists render "too tight" by default; reliable spacing uses `<br>&nbsp;<br>`
- Nested lists require 4-space indentation for Mistune parsing
- `<img>` tags are unreliable; images render as links instead
- `<table>` support is poor; pipe tables convert to ASCII in fenced code blocks

### 4.4 Markdown v2 Formatter Pipeline

**File**: `app/integrations/zendesk/formatters/markdown_v2.py`

**Dependencies**: `mistune==3.0.2`, `bleach==6.3.0`, `beautifulsoup4==4.14.3`, `lxml==6.0.2`

**Pipeline steps**:

**Step 1 -- Normalize Markdown** (`_normalize_markdown`):
- `\r\n`/`\r` to `\n`; collapse 3+ blank lines to 2
- Unicode bullets (`\u2022 \u25CF \u25E6 \u2023 \u25AA \u2219 \u00B7`) to `-`
- Bolded ordinals (`**2. Title**`) rewritten to `2. **Title**`
- `Label: value` lines converted to `- **Label:** value`
- Pipe tables converted to ASCII in fenced code blocks
- "Suggested Reply" heading dropped
- Literal `` `inline code` `` artifact stripped

**Step 2 -- Render Markdown to HTML** (Mistune v3):
- Custom renderer `_ZendeskMarkdownV2Renderer`
- Images render as `<a>` links, not `<img>` tags

**Step 3 -- Sanitize HTML** (Bleach):
- Allowed tags: `p, br, strong, em, code, pre, ul, ol, li, a, blockquote, h2, h3`
- Allowed attributes: `a[href, title, rel]`
- Allowed protocols: `http, https, mailto`

**Step 4 -- Post-process HTML** (BeautifulSoup):
- `<p>` outside `<li>`: unwrap and insert `<br>\u00a0<br>` spacing
- `<p>` inside `<li>`: unwrap and insert `<br>\u00a0` spacing
- Unordered lists: compact style (trailing `<br>\u00a0` on last item only)
- Ordered lists: loose style (`<br>\u00a0` on each item unless it contains a nested list)
- Secondary `<ol start="1">` after `<ul>` flattened to continue numbering from the first `<ol>`
- Trailing break cleanup

### 4.5 Legacy Formatter

**Location**: `app/integrations/zendesk/scheduler.py::_format_zendesk_internal_note_html`

Bespoke Markdown-ish to HTML converter:
- Supports headings; de-dupes repeated headings ("Pro Tips" guard)
- Renders inline Markdown (`**bold**`, `*italic*`, `` `code` ``)
- Builds nested lists from indentation heuristics
- Unicode bullet support at line start
- `relaxed` mode appends `<br/>&nbsp;` before closing list items

### 4.6 Posting Internal Notes

**API**: `PUT /api/v2/tickets/{id}.json` via `ZendeskClient.add_internal_note()`

- Posts `comment["html_body"]` when content looks like HTML; falls back to `comment["body"]` (plain text) if Zendesk rejects it
- Tags are merged into the explicit `ticket["tags"]` list (not `additional_tags`) because some Zendesk accounts ignore `additional_tags`; falls back to `additional_tags` if tag fetch fails
- The `mb_auto_triaged` tag is applied on successful processing

### 4.7 Formatting Config

| Variable | Default | Options |
|----------|---------|---------|
| `ZENDESK_USE_HTML` | `true` | Boolean |
| `ZENDESK_FORMAT_ENGINE` | `markdown_v2` | `legacy`, `markdown_v2` |
| `ZENDESK_FORMAT_STYLE` | `compact` | `compact`, `relaxed` |
| `ZENDESK_HEADING_LEVEL` | `h3` | `h2`, `h3` |

### 4.8 Tests

- Unit tests: `tests/test_zendesk_note_formatting.py`
- Note: BeautifulSoup emits NBSP as literal `\u00a0`; tests should assert for that rather than `&nbsp;`

---

## 5. Pattern Learning & Playbook Workflow

### 5.1 Issue Resolution Store

**Table**: `issue_resolutions`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `ticket_id` | TEXT | Source ticket |
| `category` | TEXT | Issue category |
| `problem_summary` | TEXT | Problem description |
| `solution_summary` | TEXT | Resolution description |
| `was_escalated` | BOOLEAN | Escalation flag |
| `kb_articles_used` | TEXT[] | Referenced KB articles |
| `macros_used` | TEXT[] | Used macros |
| `embedding` | VECTOR(3072) | Semantic embedding |

### 5.2 Playbook Learned Entries

**Table**: `playbook_learned_entries`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `conversation_id` | TEXT | Source conversation (unique) |
| `category` | TEXT | Issue category |
| `problem_summary` | TEXT | Problem description |
| `resolution_steps` | JSONB | Step-by-step procedure |
| `diagnostic_questions` | JSONB | Follow-up questions |
| `final_solution` | TEXT | Final resolution |
| `why_it_worked` | TEXT | Explanation |
| `status` | TEXT | `pending_review`, `approved`, `rejected` |
| `quality_score` | FLOAT | Quality rating (0-1) |

### 5.3 Learning Flow

```
Successful Response -> Extract Learnings -> Store Resolution (issue_resolutions)
                                         -> Generate Playbook Entry (playbook_learned_entries, pending_review)
                                              -> Human Review (Markdown workflow)
                                                -> Approve/Reject
                                                  -> Compile to Playbook (/playbooks/{category}.md)
```

**Extraction triggers**:
- Pattern learning: `ZENDESK_ISSUE_PATTERN_LEARNING_ENABLED=true` + ticket successfully processed + category in `_ZENDESK_PATTERN_CATEGORIES`
- Playbook extraction: `ZENDESK_PLAYBOOK_LEARNING_ENABLED=true` + conversation has sufficient quality signals

### 5.4 Historical Import

**File**: `app/integrations/zendesk/historical_import.py`

Imports resolved Zendesk tickets for pattern learning.

**Key behaviors**:
- Uses incremental cursor export: `GET /api/v2/incremental/tickets/cursor.json`
- Filters to `status in ("solved", "closed")`
- Windows-only filter by `ZENDESK_WINDOWS_BRAND_IDS`
- Nature-of-inquiry field filter via `ZENDESK_NATURE_FIELD_IDS` and `ZENDESK_NATURE_CATEGORY_MAP`
- Quality gates: >= 2 public comments, agent word count >= 50, problem summary >= 40 chars, solution summary >= 60 chars, satisfaction rating `bad` is skipped
- PII redaction via `app/security/pii_redactor.py`
- Extraction: audits + role detection for full conversation; macros from audit events; KB URLs from support domain links

**Commands**:
```bash
# Dry-run (recommended first)
python -m app.integrations.zendesk.historical_import --days 7 --dry-run

# Real import for a date range
python -m app.integrations.zendesk.historical_import \
  --start-date 2025-10-01 --end-date 2025-10-31 --no-dry-run
```

### 5.5 Markdown Review Workflow

**File**: `app/agents/unified/playbooks/review_cli.py`

**Export** pending entries to Markdown:
```bash
python -m app.agents.unified.playbooks.review_cli export \
  --out playbooks_review/YYYY-MM-DD \
  --categories sending,features,licensing \
  --status pending_review
```

Each exported file has YAML frontmatter (`id`, `conversation_id`, `category`, `status`, `quality_score`, `reviewed_by`, `reviewed_at`) and Markdown sections (Problem Summary, Diagnostic Questions, Resolution Steps, Final Solution, Why It Worked, Key Learnings).

**Review**: Edit sections directly; set frontmatter `status` to `approved` or `rejected`.

**Import** reviewed files back:
```bash
python -m app.agents.unified.playbooks.review_cli import \
  --in playbooks_review/YYYY-MM-DD \
  --reviewed-by "your_name"
```

**Compile** approved entries into playbooks:
```bash
python -m app.agents.unified.playbooks.review_cli compile \
  --categories sending,features,licensing
```

Compiled playbooks are stored in Supabase workspace storage at `/playbooks/{category}.md`, not the local filesystem. Only approved entries are included by default; use `--include-pending` for review-only outputs.

### 5.6 Status Values

| Status | Meaning |
|--------|---------|
| `pending_review` | Default after extraction |
| `approved` | Reviewed, included in compiled playbooks |
| `rejected` | Reviewed, excluded |

---

## Additional References

- Runtime and operational details: `docs/zendesk-operations.md`
