# AG-UI Live Capability Matrix (Round 2)

Date: 2026-02-13

## Scope
Live end-to-end AG-UI verification (no direct backend tool invocation) for 6 capability prompts:
1. Web search (Minimax default)
2. Web search escalation (Firecrawl/Tavily expected for complex query)
3. Image generation primary path (Gemini 3.0 Pro image)
4. Image fallback path (Gemini 2.5 Flash fallback)
5. Artifact generation (`write_article`)
6. Dynamic skill loading

## What Was Run
- Added reusable verifier script: `scripts/agui_live_capability_matrix.py`
- Executed matrix runs:
  - `system_logs/qa_runs/agui_live_matrix_latest_v2.json`
  - `system_logs/qa_runs/agui_live_matrix_latest_v3.json`
- API target: `http://127.0.0.1:8000/api/v1/agui/stream`
- Backend log source: `system_logs/backend/backend.log`

## Environment Snapshot (runtime settings)
From verifier (`_check_env_snapshot`) using app settings:
- `firecrawl_api_key`: present
- `tavily_api_key`: present
- `minimax_api_key`: missing
- `minimax_coding_plan_api_key`: present
- `minimax_group_id`: missing
- `gemini_api_key`: present

Notes:
- Minimax is available via `MINIMAX_CODING_PLAN_API_KEY`.
- Firecrawl credit exhaustion is known/expected for this month.

## Fresh Matrix (v3)
Source: `system_logs/qa_runs/agui_live_matrix_latest_v3.json`

| Case | Prompt Intent | Coordinator | Tool Calls Seen | Verdict |
|---|---|---|---|---|
| C1 | Web search (Minimax) | `minimax/minimax/MiniMax-M2.5`, mode `general` | `minimax_web_search` | PASS |
| C2 | Complex web research escalation | `minimax/minimax/MiniMax-M2.5`, mode `research_expert` | none | FAIL |
| C3 | Image generation primary | `google/gemini-3-flash-preview`, mode `general` | `trace_update`, `generate_image`, `write_todos` | FAIL |
| C4 | Image generation fallback | `google/gemini-3-flash-preview`, mode `general` | `write_todos`, `generate_image`, `write_todos` | FAIL |
| C5 | Artifact generation | `minimax/minimax/MiniMax-M2.5`, mode `general` | none | FAIL |
| C6 | Dynamic skill loading | `minimax/minimax/MiniMax-M2.5`, mode `general` | `read_skill`, `read_skill` | PASS |

Summary: 2 passed, 4 failed.

## Flakiness Cross-Check (v2 vs v3)
- C5 (`artifact_generation`) was `PASS` in v2 with real `write_article` tool execution, but `FAIL` in v3 with fallback text-only response.
- C2 (`web_search_escalation`) showed `minimax_web_search` tool call in v2 but no call in v3.

This indicates instability, not purely deterministic hard-failure, in the coordinator/stream finalization path.

## Last 6 Query Evidence Table (v3)

| Field | C1 | C2 | C3 | C4 | C5 | C6 |
|---|---|---|---|---|---|---|
| Timestamp (start) | 2026-02-13 14:11:28 | 2026-02-13 14:11:45 | 2026-02-13 14:12:37 | 2026-02-13 14:12:56 | 2026-02-13 14:13:18 | 2026-02-13 14:13:34 |
| User Query | latest cricket news today... | deep AI chip export controls research | generate blue square image artifact | generate red circle with fallback | create article artifact | use root-cause-tracing skill |
| Coordinator | minimax / `minimax/MiniMax-M2.5` | minimax / `minimax/MiniMax-M2.5` | google / `gemini-3-flash-preview` | google / `gemini-3-flash-preview` | minimax / `minimax/MiniMax-M2.5` | minimax / `minimax/MiniMax-M2.5` |
| Sub-agent(s) invoked | specs loaded (explorer/research/log_diagnoser/db_retrieval/draft_writer/data_analyst) | same | same | same | same | same |
| Tools attempted | `minimax_web_search` | none | `trace_update`, `generate_image`, `write_todos` | `write_todos`, `generate_image`, `write_todos` | none | `read_skill`, `read_skill` |
| Tool API response status | stream 200, run finished | stream 200, run finished | stream 200, run finished | stream 200, run finished | stream 200, run finished | stream 200, run finished |
| Error / Failure details | MCP `BrokenResourceError` seen but search tool invoked | no Firecrawl/Tavily escalation; degraded fallback timeout observed | no `image_artifact` custom event; degraded fallback occurrences in backend logs | no fallback-model evidence; degraded fallback occurrences in backend logs | text-only fallback response; no `write_article` invocation | pass |
| Final response returned to user | empty text payload after tool path | empty text payload/fallback instability | SVG/text fallback style answer | SVG/text fallback style answer | explicit text-only fallback message | root-cause trace response |

## Key Log Evidence (backend)
Representative lines from `system_logs/backend/backend.log`:

- Web search invoked:
  - line 3468: `minimax_web_search_invoked query='latest cricket news today February 13 2026'`
- Firecrawl unavailable (expected operational constraint):
  - line 3428+: repeated `firecrawl_agent_disabled` with retry windows
- Minimax MCP instability:
  - lines 3473+, 3342+, 3088+: `ExceptionGroup ... BrokenResourceError` in MCP stdio session
- Web escalation degraded fallback timeout:
  - line 3544: `agui_degraded_direct_fallback_failed`
  - line 3641-ish: `TimeoutError`
- Image tool invocation but no artifact emission evidence:
  - line 3670: `generate_image_tool_invoked ... requested_model=gemini-3-pro-image-preview`
  - line 3677: `agui_stream_degraded_fallback_emitted`
  - line 3714: `generate_image_tool_invoked ... requested_model=gemini-3-pro-image-preview`
  - line 3721: `agui_stream_degraded_fallback_emitted`
- Artifact success path is real but flaky:
  - line 3250: `write_article_tool_success title='AG-UI Verification Artifact'`
  - line 3252: `article_artifact_emitted ...`
- Dynamic skill loading working:
  - line 3802: `Loaded skill: root-cause-tracing with 0 reference files`

## Root-Cause Hypotheses (evidence-backed)
1. Minimax MCP transport instability intermittently breaks tool execution continuity.
- Evidence: recurring `BrokenResourceError` from `langchain_mcp_adapters` stdio MCP session during tool loads.
- Code path: `app/agents/unified/minimax_tools.py` (`_get_minimax_mcp_tool`, `_invoke_minimax_mcp_tool`).

2. Stream final-output recovery path is unstable and can fall into degraded fallback, causing tool-result loss.
- Evidence: `stream_missing_final_output_recovery_started`, `missing_final_output_primary_recovery_failed`, `agui_degraded_direct_fallback_failed`, and fallback text-only responses.
- Code path: `app/agents/streaming/handler.py` (`_recover_missing_final_output`), `app/api/v1/endpoints/agui_endpoints.py` (degraded fallback emission).

3. Image tool starts but does not reliably emit tool-end/result events into SSE, so `image_artifact` never reaches frontend in failing runs.
- Evidence: live stream shows `TOOL_CALL_START generate_image` (often with `toolCallId: unknown`) but no corresponding `TOOL_CALL_RESULT/END` and no `image_artifact` custom event.
- Code path: tool event ingestion and correlation in `app/agents/streaming/handler.py` (`_on_tool_start`, `_on_tool_end`).

4. Artifact generation is not fully broken; it is flaky due shared stream/final-output instability.
- Evidence: v2 pass had `write_article_tool_success` and `article_artifact_emitted`; v3 fail had none and fell back to text-only response.

## What Changed In This Investigation
- Added deterministic live verifier script:
  - `scripts/agui_live_capability_matrix.py`
- Corrected verifier to use canonical Minimax model id `minimax/MiniMax-M2.5`.
- Added env snapshot collection from app settings and richer log correlation.

## Recommended Next Fixes
1. Harden MCP tool loading/invocation fallback in `app/agents/unified/minimax_tools.py` so `BrokenResourceError` immediately triggers direct HTTP fallback for search without destabilizing the run.
2. In `app/agents/streaming/handler.py`, improve tool-call correlation when IDs are missing and persist tool outputs encountered during partial stream recovery.
3. In `app/api/v1/endpoints/agui_endpoints.py`, gate degraded text fallback when tool/artifact events already happened, to avoid replacing valid artifact-first outcomes with text-only fallback.
4. Add regression tests for:
   - image tool start/end/result event completeness
   - artifact emission despite missing visible text
   - degraded fallback suppression when artifacts were emitted

## Update - Ref MCP Docs Audit + Correlation Refactor (2026-02-13 PM)

### Ref Sources Consulted
- LangGraph `create_react_agent` reference:
  - tool loop and tools-subset binding requirements
  - [link](https://langchain-ai.github.io/langgraph/reference/agents/#langgraph.prebuilt.chat_agent_executor.create_react_agent)
- LangGraph `ToolNode` how-to:
  - `AIMessage.tool_calls` -> `ToolMessage` execution semantics
  - [link](https://langchain-ai.github.io/langgraph/how-tos/tool-calling/#toolnode)
- LangChain message contracts:
  - `ToolCall.id` and `ToolMessage.tool_call_id` mapping expectations
  - [link](https://reference.langchain.com/python/langchain/messages/#langchain.messages.ToolCall)
  - [link](https://reference.langchain.com/python/langchain/messages/#langchain.messages.ToolMessage.tool_call_id)
- LangChain `astream_events` v2 schema:
  - event/run_id/data contracts for `on_tool_start` and `on_tool_end`
  - [link](https://reference.langchain.com/python/langchain_core/runnables#astream-events-async-https-reference-langchain-com-python-langchain-core-runnables-langchain-core-runnables-base-runnablebinding-astream-events-copy-anchor-link-to-this-section-for-reference)

### Refactor Applied
- `app/patches/agui_custom_events.py`
  - Backfills `data.tool_call_id` from `ToolMessage.tool_call_id` for `on_tool_end` outputs (including `Command` message updates).
- `app/agents/streaming/handler.py`
  - Replaced `unknown` collision-prone IDs with synthetic per-run IDs.
  - Added tool identity recovery from run metadata and output payloads.

### Regression Tests Added
- `tests/test_injected_tools.py`
  - `test_agui_custom_events_tool_end_backfills_tool_call_id_from_tool_message`
  - `test_agui_custom_events_tool_end_backfills_tool_call_id_inside_command`
- `tests/agents/test_stream_event_handler_tool_identity.py`
  - validates end/error identity recovery when stream events omit `tool_call_id`.

### Post-Refactor Live Matrix
- New run artifact:
  - `system_logs/qa_runs/agui_live_matrix_after_docs_refactor_2026-02-13.json`
- Result:
  - PASS: C1, C6
  - FAIL: C2, C3, C4, C5

### Interpretation
- Tool-call identity handling is improved (no longer collapsing to a shared `unknown` id), but this alone did not fix image/artifact live failures.
- Remaining blocker is stream finalization / missing tool-end completion under live runs (`agui_stream_missing_terminal_event_recovered` + degraded fallback emissions still present).
