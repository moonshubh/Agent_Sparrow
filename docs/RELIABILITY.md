# Reliability & Error Handling Patterns

Last updated: 2026-02-12

---

## Transient Database Retries

Use `_run_supabase_query_with_retry` from `app/agents/tools/tool_executor.py` for Supabase queries that may fail transiently:

```python
# Retries 2x with backoff for patterns in _TRANSIENT_SUPABASE_ERRORS
result = await _run_supabase_query_with_retry(
    lambda: supabase.table("t").select("*").execute()
)
```

- Retries up to 2x with exponential backoff
- Only retries on patterns in `_TRANSIENT_SUPABASE_ERRORS` (server disconnected, connection reset)
- Non-transient errors propagate immediately

---

## Web Tool Fallback Chain

```
Primary: Tavily (web search)
    ↓ quota exhausted
Fallback: Minimax (automatic switch)
    ↓ specific URL needed
Alternative: Firecrawl (URL-specific extraction)
```

- All web tools have retry configuration for transient failures
- Minimax has built-in retry logic
- Tavily quota exhaustion triggers automatic Minimax fallback

---

## Unified Tool Input Hardening

Model-provided arguments can exceed tool validation limits. All three search tools
have coercion/clamping applied to prevent validation failures:

- `db_unified_search` — `max_results_per_source` clamped before passing to tool
- `db_grep_search` — max-result coercion to stay within tool limits
- `web_search` — max-result clamping applied

The scheduler enforces this in `app/integrations/zendesk/scheduler.py`.

## Tool Execution Reliability

`app/agents/tools/tool_executor.py` handles timeout-disabled mode correctly to
prevent false `Unknown error` returns when tools run without a timeout constraint.

---

## Serialization Safety

When persisting JSON to Supabase JSONB columns, wrap with try/except for `TypeError` (non-serializable values) and fall back to a simplified representation:

```python
try:
    json_data = json.dumps(context_report)
except TypeError:
    json_data = json.dumps({"error": "serialization_failed", "summary": str(context_report)[:500]})
```

---

## Rate Limiter Lifecycle

- Rate-limiter singletons are scoped per process + thread identity (`app/core/rate_limiting/agent_wrapper.py`)
- Safe under Celery prefork and threadpool usage
- Feed Me processing paths have fail-open handling when rate-limit infrastructure is temporarily loop-unstable:
  - `app/feedme/processors/gemini_pdf_processor.py` (PDF extraction/merge)
  - `app/feedme/tasks.py` (AI tagging + chunk embedding)

---

## Model Fallback Strategy

- PDF extraction: Primary model -> fallback `gemini-2.5-flash-preview-09-2025`
- AI tag/note generation: Same fallback model
- Coordinator: Provider factory handles model routing and fallback chains
- All fallbacks are logged in LangSmith metadata (`fallback_occurred: true`)

---

## FeedMe Processing Status Guards

- Conversations remain `processing` until all downstream steps (embedding, note generation) complete
- Prevents transient `completed` status before finalization
- Embedding finalization performs best-effort inline note generation if `ai_note` is missing
- AI tagging retries on task-level failures via Celery retry semantics

---

## mem0 Availability Check

`app/core/settings.py` accurately reports whether the mem0 backend is configured
(checking actual backend availability) rather than just checking for package
presence. This prevents misleading retrieval signals — if mem0 is not configured,
the system does not falsely claim memory retrieval is available.

---

## Zendesk Reliability

- Context report unconditionally persisted to `zendesk_pending_tickets.status_details`
- Serialization error fallbacks prevent context report loss
- Spam guard provides rate-limiting and deduplication for note posting
- Session cleanup deletes per-ticket workspace data 7 days after `last_public_comment_at`
