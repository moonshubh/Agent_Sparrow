# Primary Agent Revamp Plan (CopilotKit + LangGraph + Gemini 2.5 Flash)

Status: Phase 2 complete (validation pending import fix)
Owners: Primary Agent, Orchestration, Frontend CopilotKit
Scope: Backend FastAPI + LangGraph, Frontend CopilotKit, Provider adapters

## 0) Goals

- Restore deterministic streaming for Primary Agent (SSE), and ensure CopilotKit AG‑UI runtime works end‑to‑end.
- Align with Gemini 2.5 Flash (thinking_budget support, JSON mode for reflection).
- Remove ResponseFormatter and rely on CopilotKit capabilities + LLM native structure.
- After each phase: verify and remove obsolete code/files.

Key repos/paths:
- Backend SSE endpoint: `app/api/v1/endpoints/chat_endpoints.py`
- CopilotKit runtime: `app/main.py` → `add_fastapi_endpoint("/api/v1/copilotkit")`; fallback adapter: `app/api/v1/endpoints/copilot_endpoints.py`
- Graph: `app/agents/orchestration/orchestration/graph.py`, `nodes.py`, `state.py`
- Primary Agent: `app/agents/primary/primary_agent/agent.py` (+ `reasoning/`, `tools/`)
- Reflection: `app/agents/reflection/reflection/node.py`
- Gemini adapters: `app/providers/Google/Gemini-2.5-Flash/adapter.py` (+ `registry.py`)
- Frontend Copilot UI: `frontend/src/app/chat/copilot/CopilotChatClient.tsx`

References (Oct 2025):
- LangGraph React streaming: `langgraph-main/docs/docs/cloud/how-tos/use_stream_react.md`
- CopilotKit AG‑UI + LangGraph guides:
  - https://dev.to/copilotkit/easily-build-a-ui-for-your-langgraph-ai-agent-in-minutes
  - https://medium.com/@sajith_k/copilotkit-ag-ui-integrating-langgraph-with-next-js-and-fastapi-435cac2df56b
  - AG‑UI protocol: https://github.com/ag-ui-protocol/ag-ui
- LangChain Google GenAI integration:
  - API docs: https://python.langchain.com/docs/integrations/chat/google_generative_ai/
  - Class ref: https://python.langchain.com/api_reference/google_genai/chat_models/langchain_google_genai.chatgooglegenerativeai.html
  - Issues: thinking_budget, JSON behavior
    - https://github.com/langchain-ai/langchain-google/issues/872
    - https://github.com/langchain-ai/langchain-google/issues/1265
- Gemini 2.5 Flash overview: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5

---

## Phase 1 — Fix SSE Streaming Regression (No behavior change beyond streaming reliability)

Problem
- `chat_endpoints.primary_agent_stream_generator` treats `run_primary_agent(...)` like an async generator, but `run_primary_agent` returns a dict in normal paths and only yields in error branches (`AIMessageChunk`), causing no deltas → fallback text.

Plan
- Make `run_primary_agent` a pure coroutine: remove the two `yield AIMessageChunk(...)` error branches and instead return `{ "messages": [..., AIMessage(...)] }`.
- In `primary_agent_stream_generator`, stop iterating; `result = await run_primary_agent(initial_state)`, then stream `final_msg.content` via `stream_text_by_characters`, and emit metadata events:
  - follow-ups → `data-followups`
  - structured payload → `assistant-structured`
  - thinking_trace → `reasoning-start/delta/end` + `data-thinking`
  - toolResults → `data-tool-result`
  - leftover metadata → `message-metadata`

Acceptance
- `text-start` → `text-delta` → `text-end` always emitted for valid runs.
- No generic fallback text unless agent truly returns nothing.
- Observability logs show nonzero `text_chars`.

Verify
- Manual: call `POST /api/v1/v2/agent/chat/stream` and confirm streaming events; confirm “fallback” not used.
- Frontend: `CopilotChatClient` shows smooth animation.

Cleanup
- Remove `AIMessageChunk` branches in `agent.py` (grep `yield AIMessageChunk`).
- Remove any generator‑only scaffolding that’s now dead.

### Phase 1 implementation (completed 2025-10-29)
- Updated `app/api/v1/endpoints/chat_endpoints.py` to stream final responses via `stream_text_by_characters` with a single `text-end`, added `_extract_latest_thought` helper, and tightened task cleanup to avoid redundant `RuntimeError` checks.
- Normalized Primary Agent error metadata in `app/agents/primary/primary_agent/agent.py` so validation/fallback paths now emit structured observability payloads; augmented Zendesk scheduler fallback with warning log context.
- Refactored `app/api/v1/endpoints/unified_endpoints.py` metadata emission into `_emit_*` helpers and introduced unit coverage in `tests/api/test_unified_endpoint_metadata_helpers.py`; lazy-loading fixes in `app/db/embedding/utils.py` now prevent numpy/pgvector segfaults so the helper suite passes cleanly.
- Confirmed Phase 1 scope delivered: SSE runs emit deterministic `text-start` → `text-delta` → `text-end`, metadata fan-out unchanged, and observability counters increment correctly.

---

## Phase 2 — CopilotKit Alignment (AG‑UI runtime)

Baseline
- `app/main.py` registers `/api/v1/copilotkit` with `LangGraphAgent(name="sparrow")`.
- Fallback adapter: `/api/v1/copilot/stream` in `app/api/v1/endpoints/copilot_endpoints.py` (normalizes forwardedProps/messages).

Plan
- Keep `/api/v1/copilotkit` as primary CopilotKit runtime. Ensure:
  - `threadId=sessionId` (frontend already sets CopilotKit `threadId` = sessionId).
  - `properties` include `session_id`, `provider`, `model`, `attachments` when provided.
  - AG‑UI event flow preserved; LangGraph graph compiled successfully.

Acceptance
- Frontend `useCopilotChat` + `useCoAgent({ name: "sparrow" })` receives agent stream; messages visible; no 422 payload issues.

Verify
- `GET /api/v1/copilot/stream/health` returns ok (fallback adapter).
- Frontend points `runtimeUrl` to `/api/v1/copilotkit` (see `CopilotChatClient.tsx`).

Cleanup
- Keep `copilot_endpoints.py` as compatibility layer for now; revisit after Phase 6 (tool calls). Remove if unused.

### Phase 2 implementation (completed 2025-10-29)
- Wrapped LangGraph runtime with `SparrowLangGraphAgent` (`app/integrations/copilotkit/runtime.py`) so CopilotKit `properties` hydrate `GraphState`—session/model/provider/attachments now propagate, and thread identifiers default to the session id.
- Extended orchestration/primary agent schemas to carry attachment metadata and taught `run_primary_agent` to fold image data URLs into the final `HumanMessage`, ensuring multimodal prompts hit Gemini when CopilotKit uploads screenshots.
- Updated `app/main.py` to register the new wrapper per-request via CopilotKit context and kept compatibility fallback on `/api/v1/copilot/stream`.
- Frontend Copilot UI now persists provider/model/agent type inside the CopilotKit `properties` payload so every run ships the intended LLM hints without waiting for the first send.
- Smoke validation: manual instantiation of `SparrowLangGraphAgent` verifies property merging and attachments propagation; helper pytest suite passes after the embedding-utils lazy import fix. Full CopilotKit streaming still needs a live Gemini key to exercise end-to-end.

---

## Phase 3 — Gemini Prompt and Settings Tuning

Plan
- Keep V10 system prompt but add “lean” mode for CopilotKit sessions (less rigid skeleton).
- Defaults: `temperature≈0.2`, optional `thinking_budget` for `gemini-2.5-flash`.
- Ensure adapter passes through `top_p`, `top_k`, `max_output_tokens`, and supports `thinking_budget`.

Acceptance
- Logs confirm selected provider/model, temperature, thinking_budget.
- No regressions with current content quality.

Verify
- Set `PRIMARY_AGENT_MODEL=gemini-2.5-flash-preview-09-2025` and test; check logs and output.

Cleanup
- None yet.

Config toggles
- `PRIMARY_AGENT_FORMATTING=strict|natural` (default natural for CopilotKit)
- `PRIMARY_AGENT_TEMPERATURE` (float)
- `PRIMARY_AGENT_MODEL`, `PRIMARY_AGENT_PROVIDER`
- `THINKING_BUDGET` (optional int)

---

## Phase 4 — Remove Response Formatter (use CopilotKit + LLM native structuring)

Current
- `app/agents/primary/primary_agent/prompts/response_formatter.py` enforces a 7‑section output and generates follow‑ups.

Decision
- Remove the ResponseFormatter entirely. Let the LLM structure responses naturally under V10 lean prompt + CopilotKit UI.
- If short “suggestions” are desired, instruct the LLM in-system prompt to include 2‑3 short follow‑ups at end or return minimal metadata; avoid backend post-processing.

Plan
- Delete `response_formatter.py` and remove all imports/references (agent.py, reasoning engine).
- Adjust the reasoning engine to not call formatter for validation or follow‑ups.
- Keep the V10 prompt’s guidance but do not mandate strict sections.

Acceptance
- No import errors; responses read naturally; Copilot UI displays messages without missing features.

Verify
- Grep for `ResponseFormatter` and ensure references removed.
- Run SSE and CopilotKit flows; confirm output structure remains good.

Cleanup (delete)
- `app/agents/primary/primary_agent/prompts/response_formatter.py`
- Any references in `agent.py` / `reasoning_engine.py`

---

## Phase 5 — Reflection JSON‑mode (Gemini)

Problem
- Reflection node parses JSON using a rubric; without strict JSON mode the model can produce extra text.

Plan
- In `app/agents/reflection/reflection/node.py`, when provider=google, load reasoning model with `response_mime_type="application/json"` (adapter already passes through). Parse with `ReflectionFeedback.model_validate_json`.
- Keep fallback to default provider/model if loading fails.

Acceptance
- Reflection reliably returns parsed JSON; routing works (refine/post_process/escalate).

Verify
- Force reflection run; confirm confidence thresholds route correctly; logs show parsed JSON.

Cleanup
- None (keep cache + routing).

---

## Phase 6 — Tool‑call Bridging (activate ToolNode + CopilotKit tool UI)

Current
- Primary Agent performs its own grounding (KB + Tavily) and never emits `tool_calls`; ToolNode is not used in the main path.

Plan
- When `ReasoningEngine.tool_reasoning.decision_type` indicates a fetch (KB or web), emit `AIMessage` with `tool_calls` (e.g., `tavily_web_search`, `mailbird_kb_search`) so the graph routes to `tools`. Return to agent afterwards and produce the final answer.
- Preserve current grounding as fallback (if tool execution fails), but avoid duplicate calls.

Acceptance
- State shows `messages[-1].tool_calls` triggering ToolNode.
- SSE emits tool events (through CopilotKit AG‑UI runtime); final answer follows.

Verify
- Simulate a query requiring retrieval; observe tool events in UI and backend logs; ensure no duplicate Tavily requests.

Cleanup
- Remove redundant direct calls if ToolNode path is stable; keep safe fallback only.

---

## Phase 7 — Frontend UX polish

Plan
- Suggestions: rely on LLM output text (optional minimal metadata). If provided, package them under `messageMetadata.suggestions` so `CopilotChatClient` presents chips.
- Reasoning micro‑events: continue emitting `reasoning-start/delta/end` with sparse deltas derived from thinking trace; do not expose chain‑of‑thought.

Acceptance
- Suggestion chips show when provided; reasoning micro‑events display as before.

Verify
- Send a few prompts; confirm suggestions and reasoning UI.

Cleanup
- None.

---

## Phase 8 — Tests and Validation

Unit
- Streaming: ensure text-start/delta/end, no fallback in healthy runs.
- Reflection: JSON mode returns parsed structure; routing thresholds respected.
- Tool calls: messages contain `tool_calls`; ToolNode executed; agent continues.
- Provider config: `thinking_budget` + temperature pass-through.

E2E
- CopilotKit UI sends/receives streams; messages recorded; attachments OK.
- SSE endpoint behaves consistently (heartbeats, prelude, finish events).

CI
- Add checks for greps that should disappear: `ResponseFormatter`, `AIMessageChunk`.

---

## Proposed Config/Env

- `PRIMARY_AGENT_PROVIDER=google|openai` (default google)
- `PRIMARY_AGENT_MODEL=gemini-2.5-flash-preview-09-2025`
- `PRIMARY_AGENT_TEMPERATURE=0.2`
- `PRIMARY_AGENT_FORMATTING=strict|natural` (default natural)
- `THINKING_BUDGET=<int or unset>`
- `QA_MAX_RETRIES`, `QA_CONFIDENCE_THRESHOLD`, `QA_CRITICAL_THRESHOLD` (reflection)
- `GEMINI_API_KEY` / `GOOGLE_GENERATIVE_AI_API_KEY`, `OPENAI_API_KEY`

---

## Inventory for Cleanup (after phases)

Delete when verified:
- `app/agents/primary/primary_agent/prompts/response_formatter.py`
- Any imports of `ResponseFormatter` in agent or reasoning files
- Any leftover generator-based code paths in `run_primary_agent` (`AIMessageChunk` yields)

Deprecate after Phase 6 if unused:
- `app/api/v1/endpoints/copilot_endpoints.py` (fallback adapter)

---

## Appendix — Code Pointers

- SSE streaming: `app/api/v1/endpoints/chat_endpoints.py`
- CopilotKit runtime: `app/main.py` → `add_fastapi_endpoint(app, sdk, "/api/v1/copilotkit")`
- LangGraph graph: `app/agents/orchestration/orchestration/graph.py`, `nodes.py`, `state.py`
- Primary Agent: `app/agents/primary/primary_agent/agent.py`
- Reasoning engine: `app/agents/primary/primary_agent/reasoning/reasoning_engine.py`
- Reflection: `app/agents/reflection/reflection/node.py`
- Providers: `app/providers/registry.py`, `app/providers/Google/Gemini-2.5-Flash/adapter.py`
- Frontend CopilotKit: `frontend/src/app/chat/copilot/CopilotChatClient.tsx`
