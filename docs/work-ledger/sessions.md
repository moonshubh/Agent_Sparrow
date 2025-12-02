# Session Work Ledger – AG-UI Timeline Integration

*Note: Older session entries were pruned on 2025-11-27 per request. Check git history if you need the previous session details.*

## 2025-11-28 – CodeRabbit review hardening

- Preserved backend-provided evidence cards by widening the validator schema (typed card objects + metadata) and keeping cards in the validated payload.
- Refactored `ToolEvidenceSidebar` to use a single helper for mapping evidence to cards (typed inputs, consistent type/snippet/url derivation, timestamp/status normalization).
- Improved accessibility: central trigger and color nodes in `SpatialColorPicker` now announce labels/states, folder tiles expose real `aria-expanded`, and attachment sizes avoid `NaN`.
- Ensured multimodal attachments still inline when no human message is present by creating a fallback Gemini-ready human message in `message_preparation.py`.
- Hardened multi-provider defaults and prompts: non-Google runs now default to the configured XAI model when unspecified, provider/model metadata flows into the coordinator prompt with friendlier display names (including preview Geminis), and model lists include configured defaults for UI selection.
- Added Grok-specific prompt addendum for deeper reasoning/step breakdowns and expanded XAI model build logging.

## 2025-11-29 – CodeRabbit issue verification and fixes

- Verified all CodeRabbit findings and applied fixes:
  - Evidence cards: validators keep typed `cards`/metadata; sidebar mapping deduped into a single helper with typed payloads.
  - A11y: SpatialColorPicker buttons/central trigger announce labels/states; folder tiles expose dynamic `aria-expanded`.
  - UI safety: AttachmentPreview guards size math to avoid `NaN`; empty model stream chunks are logged for diagnostics.
  - Backend resilience: `message_preparation.py` now builds a multimodal human message even when no prior human message exists.
- Documentation refreshed:
  - `CLAUDE.md` documents multi-provider (Gemini + Grok) setup, provider factory settings, and Grok depth prompt addendum.
  - `docs/backend/Backend.md` notes multi-provider support and provider factory placement in the architecture diagram.

## 2025-11-27 – Log attachment routing fix

- Added layered log detection heuristics (MIME/extension/timestamp/log-level/stack traces) in `app/agents/unified/attachment_processor.py` and exposed `detect_log_attachments`.
- `_determine_task_type` now flips to `log_analysis`, stamps `forwarded_props`, and mirrors the agent type when logs are attached; SubAgentMiddleware gets a log-specific task prompt via `_build_task_system_prompt`.
- Introduced `_maybe_autoroute_log_analysis` to pre-run the log-diagnoser subagent with inlined attachments and inject its report before streaming so Gemini Pro is selected and the coordinator synthesizes the result.
- Updated `docs/oracle-solutions/issue-1-agent-router-malfunction.md` to record the completed routing fix and implementation details.
- Ledger trimmed to only this session per request.

## 2025-11-27 – Thinking trace visibility fix

- Backend emitter now always sends the full thinking trace list on every update, preventing UI gaps when incremental `latestStep` deltas are missed (`app/agents/streaming/emitter.py`).
- ThinkingTrace UI now falls back to `metadata.finalOutput` or `metadata.promptPreview` when `content` is empty, so reasoning text shows instead of "No transcript yet" (`frontend/src/features/ag-ui/sidebar/ThinkingTrace.tsx`).
- Documented the fix in `docs/oracle-solutions/issue-4-agent-thinking-steps.md`.

## 2025-11-27 – Harness resilience & robustness

- Added safety wrappers and tool resilience middleware (retry + circuit breaker) plus correlation seeding in `app/agents/harness/middleware/agent_mw_adapters.py` and `trace_seed.py`.
- Harness now passes checkpointer/store/cache, propagates `interrupt_on` to subagents, and wraps middleware defensively (`app/agents/harness/sparrow_harness.py`).
- Memory and rate-limit middleware stats updates are now lock-guarded for thread safety (`memory_middleware.py`, `rate_limit_middleware.py`).
- Documented the robustness work in `docs/oracle-solutions/issue-5-system-robustness-harness.md`.

## 2025-11-27 – LangGraph optimization pass

- Added bounded message reducer (keeps memory context + last 30 messages) and a step counter to `app/agents/orchestration/orchestration/state.py`.
- Swapped the tool runner for a parallel, idempotent tool node with unknown-tool guards (`app/agents/orchestration/orchestration/graph.py`).
- Hardened continuation routing and ensured rate-limit slots are released even on successful runs (`app/agents/unified/agent_sparrow.py`).
- Documented the LangGraph optimization in `docs/oracle-solutions/issue-6-langgraph-framework-optimization.md`.

## 2025-11-27 – CodeRabbit review fixes

- Fixed harness config indent/name/caching and SafeMiddleware wrapping; added AgentMiddleware import, cache/name fields to config (`app/agents/harness/sparrow_harness.py`).
- Added missing asyncio import to rate-limit middleware and guarded memory stats reads/resets with locks (`app/agents/harness/middleware/rate_limit_middleware.py`, `memory_middleware.py`).
- Trace seed now no-ops on non-dict state (`trace_seed.py`).
- Parallel tool runner now checks tool IDs and lets `CancelledError` propagate (`app/agents/orchestration/orchestration/graph.py`).
- Hardened FeedMe Gemini helpers: removed unused embed client, safe candidate access, API key change detection for PDF processor (`app/feedme/tasks.py`, `app/feedme/processors/gemini_pdf_processor.py`).

## 2025-11-27 – To-do list consolidation (Issue 2)

- Consolidated to-do list display to a single location in the EnhancedReasoningPanel strategic planning card.
- Changed `initialExpanded` default from `false` to `true` so panel opens by default showing todos.
- Added `useEffect` hooks to auto-select Planning phase on mount and when todos arrive.
- Computed todo counts internally from the `todos` prop (single source of truth) instead of using deprecated external props.
- Renamed section title from "Run Tasks" to "To-Do".
- Removed duplicate "Run Tasks" sidebar section from `ChatContainer.tsx` (lines 331-371).
- Files modified: `frontend/src/features/ag-ui/reasoning/EnhancedReasoningPanel.tsx`, `frontend/src/features/ag-ui/ChatContainer.tsx`.

## 2025-11-27 – Tool evidence presentation improvement (Issue 3)

- Added `build_tool_evidence_cards()` function in `app/agents/streaming/normalizers.py` to normalize raw tool output into structured evidence cards with: type inference, title/snippet extraction, score normalization, and metadata preservation.
- Updated `ToolEvidenceUpdateEvent` in `app/agents/streaming/event_types.py` to include a `cards` field for pre-built evidence cards.
- Modified `StreamEventHandler._on_tool_end()` in `app/agents/streaming/handler.py` to build cards using the new normalizer and pass them to the emitter. Also changed `_summarize_structured_content()` to return plain text instead of markdown.
- Updated `StreamEventEmitter.end_tool()` in `app/agents/streaming/emitter.py` to accept optional `cards` parameter and include in the `tool_evidence_update` event.
- Enhanced `ToolEvidenceCard.tsx` in `frontend/src/features/ag-ui/evidence/` with:
  - JSON detection and structured rendering (key-value grid for objects, bullet list for arrays)
  - Expandable/collapsible card via header click
  - "View raw JSON" toggle for power users (collapsed by default)
  - Score bars for relevance and confidence when available
  - Metadata display section in expanded view
- Added CSS styles for new components: `.kv-grid`, `.kv-row`, `.nice-list`, `.raw-json-section`, `.expand-toggle` in `evidence-cards.css`.

## 2025-11-27 – Thinking trace & evidence refinements (log runs)

- Suppressed raw JSON streaming to the chat bubble for log-analysis runs; thinking trace now summarizes JSON (log runs show “Analyzing logs” or a short summary) instead of raw blobs (`app/agents/streaming/handler.py`, `frontend/src/features/ag-ui/sidebar/ThinkingTrace.tsx`, `ChatContainer.tsx`).
- Header shows resolved model/task metadata from backend state (`AgentContext.tsx`, `ChatContainer.tsx`, `ChatHeader.tsx`), so log runs display the Pro model when selected.
- Tool evidence sidebar renders backend cards when present and falls back to any evidence payload even if timeline ops don’t match (`ToolEvidenceSidebar.tsx`, `services/ag-ui/validators.ts`).
- Backend evidence normalizer now parses string outputs more leniently (handles `content=/data=` prefixes, single-quoted JSON) and shortens snippets; if parsing fails, it emits a friendly summary card instead of raw JSON (`app/agents/streaming/normalizers.py`).

## 2025-11-29 – OpenRouter integration and model wiring

- Added OpenRouter provider support with Grok 4.1 Fast (free) and MiniMax M2 models to the registry, provider factory, subagents, and API model config. Fallback chain set to Grok free → MiniMax. (`app/core/config/model_registry.py`, `app/agents/unified/provider_factory.py`, `app/agents/unified/subagents.py`, `app/api/v1/endpoints/models_endpoints.py`, `.env`).
- Enabled OpenRouter selection in frontend header: provider selector now shows OpenRouter; model selector surfaces Grok free and MiniMax with defaults/fallbacks. (`frontend/src/services/api/endpoints/models.ts`, `ProviderSelector.tsx`, `AgUiChatClient.tsx`, `ChatContainer.tsx`).
- Confirmed OpenRouter tool-calls work for both Grok free and MiniMax with bound tools; registry/subagent model selection resolves correctly for `provider="openrouter"`. Tools validated via direct LangChain calls.
- Resolved `openai` dependency conflict by relaxing pin to `>=1.109.1,<3.0.0` and reinstalling deps; restarted backend/frontend/celery with new config.
