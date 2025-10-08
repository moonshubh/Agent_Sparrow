# Log Analysis Agent – Developer Guide

## Overview
Specialized agent for analyzing Mailbird logs. Two modes:
- Simplified (default): question-driven, fast summaries and actions
- Comprehensive: quality-first pipeline with privacy/security controls

Re-organization note: prefer `from app.agents.log_analysis import run_log_analysis_agent, SimplifiedLogAnalysisOutput` (compat exists for `app.agents_v2.log_analysis_agent.*`).

## Key Files
- app/agents_v2/log_analysis_agent/agent.py – router between simplified/comprehensive
- app/agents_v2/log_analysis_agent/simplified_agent.py, simplified_schemas.py – fast path
- app/agents_v2/log_analysis_agent/comprehensive_agent.py – advanced pipeline
- app/api/v1/middleware/log_analysis_middleware.py – validation, rate limits, sessions
- app/api/v1/endpoints/logs_endpoints.py – /api/v1/agent/logs, /api/v1/agent/logs/stream, sessions, rate limits
- app/api/v1/endpoints/unified_endpoints.py – unified stream integration
- app/providers/adapters – Unified provider registry access (get_adapter/load_model)
- app/api/v1/endpoints/secure_log_analysis.py – paranoid secure streaming endpoint
- DB utilities: prefer `app.db.supabase.client` and `app.db.embedding.utils` for canonical imports

## Endpoints
- POST /api/v1/agent/logs – returns JSON (SimplifiedLogAnalysisOutput + trace_id)
- POST /api/v1/agent/unified/stream – SSE for unified routing; when agent_type=log_analysis and log_content provided, streams timeline + final content
- POST /api/v1/secure/log-analysis/stream – strict secure SSE variant (privacy redaction)

## Unified SSE Contract (frontend/lib/providers/unified-client.ts)
- Server sends events like:
  - { type: 'step', data: { type, description, status } } → client maps to timeline-step
  - Final assistant payload includes content and analysis_results (structured)
- Client maps analysis_results into message metadata (logMetadata, errorSnippets, rootCause)

SSE formatting is unified via `app/core/transport/sse.py` using `format_sse_data(payload)`.

## Rate Limiting & Sessions
- Middleware enforces per-minute/hour/day and concurrent limits; creates session records (in-memory manager) with metadata (time_range, line_count, etc.).
- agent_endpoints releases concurrent slots in a finally block.
- Provider wrappers: use app/providers/limits/wrap_gemini_agent for Gemini models.

## Security & Privacy
- secure_log_analysis.py provides paranoid redaction pipeline knobs.
- Avoid logging raw log content; structured metrics only (error_count, line_count, etc.).
- API keys loaded from user context; fallback env when permitted.

## Behavior Notes
- Mode selection: env LOG_ANALYSIS_MODE (comprehensive|simplified), defaults to comprehensive when available.
- Simplified flow: preprocess → relevant sections (LLM-assisted) → answer/issues/solutions JSON → normalized output.
- Comprehensive flow: structured parsing, root causes, executive summary, quality scoring; result mapped to simplified schema for compatibility.

## Testing and Local Smoke
- JSON API: curl -X POST http://localhost:8000/api/v1/agent/logs -H 'Content-Type: application/json' -d '{"content":"<paste logs>"}'
- Unified SSE: curl -N -X POST http://localhost:8000/api/v1/agent/unified/stream -H 'Content-Type: application/json' -d '{"agent_type":"log_analysis","message":"analyze","log_content":"<logs>"}'
- Expect timeline steps, then assistant content with analysis_results; frontend maps metadata for cards.

## Troubleshooting
- Missing Gemini key → handler returns actionable error
- Rate limit exceeded → 429 with guidance (headers include Retry-After)
- Large files → validator enforces size limits (LOG_ANALYSIS_RATE_LIMITS)
