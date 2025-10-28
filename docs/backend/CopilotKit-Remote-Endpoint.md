# CopilotKit Remote Endpoint (FastAPI + LangGraph)

Goal: Expose a CopilotKit-compatible remote endpoint at `/api/v1/copilot/stream` (POST) that:
- Authenticates the user (Supabase JWT in `Authorization: Bearer <token>`)
- Invokes our existing LangGraph agents/tools
- Streams CopilotKit runtime events (text delta, tool activity, interrupts)
- Accepts per-request properties like `session_id`, `use_server_memory`, `agent_type`, `provider`, `model`, `trace_id`, `attachments`, and optional `mcpEndpoints`

This endpoint powers the new Copilot chat UI: `frontend/src/app/chat/copilot/*`.

## TL;DR — Implementation Outline
1) Install the Python SDK: `pip install copilotkit`
2) Use the AG‑UI LangGraph adapter to wrap our compiled LangGraph graph
3) Add a FastAPI route at `/api/v1/copilot/stream` that accepts POST and streams events
4) Enforce auth (Supabase JWT) and pass user context
5) Forward request-scoped properties (session/memory/attachments)
6) Emit interrupts via LangGraph tasks and support resume

The CopilotKit client (via AG‑UI) consumes a structured event stream we emit from the LangGraph adapter. We rely on `ag_ui_langgraph` to format SSE or HTTP event streams that the frontend understands.

## Expected Request Contract (from frontend)
- Auth: `Authorization: Bearer <supabase_jwt>`
- Body: AG‑UI `RunAgentInput` with fields:
  - `messages`: CopilotKit/AG‑UI messages (TextMessage/ImageMessage/etc.)
  - `threadId`, `runId`: identifiers for the current run/session
  - `forwardedProps`: request-scoped properties object (see below)
- Forwarded properties (request-scoped via `forwardedProps`):
  - `session_id: string`
  - `use_server_memory: boolean`
  - `agent_type?: 'primary' | 'log_analysis'`
  - `provider?: 'google' | 'openai'`
  - `model?: string`
  - `trace_id?: string`
  - `attachments?: Array<{ filename: string; media_type: string; data_url: string }>`
  - `mcpEndpoints?: Array<{ endpoint: string }>`

## Minimal FastAPI Wiring (in repo)
- Route file: `app/api/v1/endpoints/copilot_endpoints.py`
- Implementation uses:
  - `from ag_ui_langgraph.agent import LangGraphAgent`
  - `from ag_ui.core.types import RunAgentInput`
  - `from ag_ui.encoder import EventEncoder`
  - Compiled graph from `app.agents.orchestration.orchestration.graph import app as compiled_graph`
- Endpoint shape:
  - `POST /api/v1/copilot/stream`
  - Body: `RunAgentInput` (includes `messages`, `threadId`, `forwardedProps`, etc.)
  - Response: streaming (SSE/HTTP events) based on `Accept` header
  - Auth: enforced via `Depends(get_current_user_id)` (Supabase JWT)
  - Health: `GET /api/v1/copilot/stream/health` returns `{ status: 'ok' }` when active

Endpoint implemented in repo
- `app/api/v1/endpoints/copilot_endpoints.py` is wired in `app/main.py` under `/api/v1/copilot/stream`.
- Behavior:
  - If `copilotkit` SDK is unavailable, the route returns HTTP 501 with installation guidance.
  - If available, the route streams LangGraph events using the adapter. Interrupts are surfaced via LangGraph tasks and can be resumed.

## Auth and User Context
- Reuse existing Supabase auth middleware/util from FastAPI.
- Pass `user.id` to the agent for auditing and downstream data access.
- Optional: support your existing secure stream token scheme, but it’s not required for CopilotKit’s runtime.

## Interrupts (HITL)
- The runtime client surfaces LangGraph interrupts as `langGraphInterruptEvent`.
- In the handler above, you can emit: `runtime.emit(langgraph_interrupt_event(value={...}))`
- The frontend registers `useLangGraphInterrupt` and, when the user clicks Approve/Reject, CopilotKit sends a follow-up call to your runtime to resume the graph with the provided resolution.
- Ensure your `run_graph` supports a resume entrypoint (thread/run identifier) if your graph is long-running. For a simple model:
  - Persist `thread_id` + `run_id` in your state when you emit an interrupt event
  - On resume, look up the pending run and apply the user’s decision

Backend TODO
- Confirm forwarded properties mapping inside graph nodes; propagate `session_id`, `use_server_memory`, provider/model, and `attachments` into the graph state where needed.
- Verify interrupt resume semantics end-to-end with the queueing UI.
 - If `mcpEndpoints` provided, construct server-side MCP client(s) and restrict outbound targets via an allowlist.

## Attachments Contract
- Frontend forwards: `properties.attachments = [{ filename, media_type, data_url }]`
- You can either:
  - Convert and save to temp storage, pass a file handle to tools; or
  - Decode in-memory as shown above and pass raw bytes.
- Images may also appear in `messages` as `ImageMessage` in addition to `properties.attachments`.

### Limits and validation
- The frontend enforces basic limits: up to 4 files per send, and a 10MB per-file cap by default.
- Recommended: validate on the server as well and return a 400 with a clear message if limits are exceeded.
- Consider normalizing `media_type` and sanitizing `filename` for safe downstream handling.

## Emitting Runtime Events
Map your existing stream callbacks to CopilotKit runtime events:
- Text stream:
  - `runtime.emit({ type: 'text-start', id })`
  - `runtime.emit({ type: 'text-delta', id, delta: '...' })`
  - `runtime.emit({ type: 'text-end', id })`
- Tool state:
  - `runtime.emit({ type: 'tool-start', id, name })`
  - `runtime.emit({ type: 'tool-input-delta', id, inputTextDelta })`
  - `runtime.emit({ type: 'tool-output-available', id, outputText })`
  - `runtime.emit({ type: 'tool-error', id, errorText })`
- Message metadata (memory snippet, log metadata, etc.):
  - `runtime.emit({ type: 'message-metadata', messageMetadata: { memory_snippet: '...', logMetadata: {...} } })`
- Interrupt:
  - `runtime.emit(langgraph_interrupt_event(value={ 'prompt': 'Approve running tool [X]?' }))`

> The Python SDK provides utilities for LangGraph events; prefer those where available.

## Observability
- Add trace ids from `properties.trace_id` if provided by the client.
- Extend your OTel spans to include CopilotKit runtime handler.

## Testing Checklist
- Auth: Request with missing/invalid JWT is rejected.
- Text-only: Simple conversation streams and completes.
- Attachments: Non-image file reaches your tool layer; image embeds and persists.
- Interrupts: UI modal appears; Approve/Reject resumes the run as expected.
- Performance: p95 stream start comparable to legacy.

## Switching the Frontend Runtime URL (optional)
If you prefer a GraphQL-looking path, you can mount at `/api/v1/copilot/graphql` and update `runtimeUrl` in `frontend/src/app/chat/copilot/CopilotChatClient.tsx` accordingly.

## Security: MCP Endpoint Allowlist (SSRF Protection)
- Do not proxy arbitrary MCP URLs from the client. Treat `mcpEndpoints` as hints only.
- Enforce a strict allowlist and scheme check (http/https only) before attempting any outbound connection.
- Block localhost/loopback and private networks (10/172.16–31/192.168/169.254) and IPv6 link-local.
- Instantiate MCP clients server-side with validated endpoints and timeouts; never store client-supplied URLs verbatim.
