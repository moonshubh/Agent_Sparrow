# Primary Agent – Developer Guide

## Overview
The Primary Agent powers general conversational support with structured reasoning, tool usage, and streaming. It is orchestrated by LangGraph and exposed via authenticated SSE endpoints consumed by the frontend unified client.

Re-organization note: prefer `from app.agents.primary import run_primary_agent, PrimaryAgentState` (compat exists for `app.agents_v2.primary_agent.*`).

## Key Files
- app/agents_v2/primary_agent/agent.py – streaming runner (Gemini/OpenAI selection, reasoning, SSE metadata)
- app/agents_v2/primary_agent/reasoning/* – ReasoningEngine, configs, schemas
- app/agents_v2/primary_agent/prompts/* – prompt templates and response formatting
- app/agents_v2/primary_agent/tools.py – Tavily web search bridge; KB tool imports
- app/agents_v2/primary_agent/feedme_knowledge_tool.py – Enhanced KB + FeedMe retrieval tool
- app/providers/adapters – Unified registry API; provider-specific modules live under app/providers/<Provider>/<Model>/
- app/api/v1/endpoints/chat_endpoints.py – v2 streaming chat endpoint
- DB utilities: use `from app.db.supabase.client import get_supabase_client` and `from app.db.embedding.utils import ...`

## Request → Response Flow
1. Frontend: unified-client.ts sends SSE request to POST /api/v1/v2/agent/chat/stream with history and current message.
2. Backend: agent_endpoints.primary_agent_stream_generator builds PrimaryAgentState and streams chunks from run_primary_agent().
3. Stream contract (SSE data lines):
   - text-start → first text token boundary
   - text-delta → content string chunks (filtered of internal/system blocks)
   - data-followups (optional) → suggested follow-up questions
   - data-thinking (optional) → thinking snapshot (if enabled)
   - data-tool-result (optional) → tool decision summary
   - message-metadata (optional) → any remaining metadata
   - text-end, finish → completion markers

SSE formatting: all streaming endpoints use `app/core/transport/sse.format_sse_data(payload)` for consistent event emission.

## Provider and API Key Resolution
- Provider: settings.primary_agent_provider (default: google); override via request provider/model.
- Keys: user context (Supabase-stored encrypted keys) via app/core/user_context and app/api_keys/supabase_service; fallback to env when allowed.
- Rate limiting: app/providers/limits/* exposes wrap_gemini_agent() (provider-scoped re-export of core limiter).

## Tools
- Enhanced KB + FeedMe: app/agents_v2/primary_agent/feedme_knowledge_tool.py (Supabase-backed KB/articles, FeedMe conversations, saved web snapshots).
- Tavily web search: app/tools/user_research_tools.py used via primary_agent/tools.py tavily_web_search().

## Global Knowledge Injection (Phases 1–3)
- Pre‑process computes query embedding and performs retrieval:
  - Primary path: LangGraph Store search when `RETRIEVAL_PRIMARY=store` and `GLOBAL_STORE_DB_URI` configured.
  - Fallback: RPC adapter (`ENABLE_STORE_ADAPTER=true`) or direct RPC in `rpc` mode.
- Flags:
  - `ENABLE_GLOBAL_KNOWLEDGE_INJECTION`, `ENABLE_STORE_ADAPTER`, `ENABLE_STORE_WRITES`, `RETRIEVAL_PRIMARY`, `GLOBAL_STORE_DB_URI`.
- Injection: top‑k facts are compacted to a bounded system memory segment (configurable char budget) and attached to the Primary Agent grounding.

## Security
- Never log API keys or PII; Primary Agent logs use OpenTelemetry spans and structured logging.
- Auth gating handled in app/main.py (Supabase endpoints enabled by settings); v2 chat stream uses Depends(get_current_user_id).

## Testing and Local Smoke
- Start server: uvicorn app.main:app --reload
- Chat SSE: curl -N -X POST http://localhost:8000/api/v1/v2/agent/chat/stream -H 'Content-Type: application/json' -d '{"message":"Hello"}'
- Expect SSE events as listed above; verify no internal/self_critique blocks appear in stream.

## Troubleshooting
- If Gemini key missing, stream emits error payload; configure via Settings → API Keys or GEMINI_API_KEY env.
- Rate limit/circuit breaker errors are surfaced via HTTP handlers in app/main.py.
