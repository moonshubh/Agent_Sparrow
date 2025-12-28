"""Stream event handler for processing agent events and emitting AG-UI events.

Extracted from agent_sparrow.py to provide a clean, modular interface for
handling LangGraph streaming events.
"""

from __future__ import annotations

import hashlib
import re
import time
from contextlib import nullcontext
from typing import Any, TYPE_CHECKING

from langchain_core.messages import BaseMessage
from loguru import logger
import json

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

from .emitter import StreamEventEmitter
from .normalizers import (
    build_tool_evidence_cards,
    extract_grounding_results,
    extract_snippet_texts,
)
from .utils import (
    ToolResultEvictionManager,
    parse_tool_calls_safely,
    InvalidToolCall,
    retry_with_backoff,
    RetryConfig,
)
from app.core.settings import settings

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.config import RunnableConfig
    from app.agents.orchestration.orchestration.state import GraphState
    from app.agents.helpers.gemma_helper import GemmaHelper


# Timeout for Gemma helper calls
HELPER_TIMEOUT_SECONDS = 8.0

# Pattern for detecting thinking blocks
THINKING_TOKEN_PATTERN = r"(?:thinking|think|analysis|reasoning|thought)"
THINKING_BLOCK_PATTERN = re.compile(
    rf":::\s*{THINKING_TOKEN_PATTERN}\s*([\s\S]*?)\s*:::",
    re.IGNORECASE,
)
THINK_TAG_PATTERN = re.compile(
    rf"<\s*{THINKING_TOKEN_PATTERN}\s*>\s*([\s\S]*?)\s*<\s*/\s*{THINKING_TOKEN_PATTERN}\s*>",
    re.IGNORECASE,
)
THINK_FENCE_PATTERN = re.compile(
    rf"```\s*{THINKING_TOKEN_PATTERN}\s*([\s\S]*?)\s*```",
    re.IGNORECASE,
)
THINKING_BLOCK_START_RE = re.compile(
    rf":::\s*{THINKING_TOKEN_PATTERN}\b",
    re.IGNORECASE,
)
THINKING_TAG_START_RE = re.compile(
    rf"<\s*({THINKING_TOKEN_PATTERN})\s*>",
    re.IGNORECASE,
)
THINKING_FENCE_START_RE = re.compile(
    rf"```\s*({THINKING_TOKEN_PATTERN})\b",
    re.IGNORECASE,
)

# Pattern for detecting markdown images with data URIs (base64-encoded images)
# Matches: ![alt text](data:image/...) where the base64 data can be very long.
# This catches the model outputting embedded images as markdown which should be filtered.
MARKDOWN_DATA_URI_PATTERN = re.compile(
    r"!\[[^\]]*\]\(data:image/[^)]+\)",
    re.IGNORECASE,
)


class ThinkingBlockTracker:
    """Tracks thinking block state across streaming chunks.

    Uses a buffer-based approach to reliably detect :::thinking blocks
    even when markers span multiple chunks. Provides both real-time
    filtering during streaming and final sanitization.
    """

    def __init__(self):
        self.buffer = ""
        self.in_thinking = False
        self.emitted_content = ""
        self._end_marker: str | None = None
        self._search_start = 0

    def _find_start_marker(self, lower_buffer: str) -> tuple[int, str, int] | None:
        """Find the earliest thinking block start marker."""
        candidates: list[tuple[int, str, int]] = []

        block_match = THINKING_BLOCK_START_RE.search(lower_buffer)
        if block_match:
            candidates.append((block_match.start(), ":::", block_match.end()))

        fence_match = THINKING_FENCE_START_RE.search(lower_buffer)
        if fence_match:
            candidates.append((fence_match.start(), "```", fence_match.end()))

        tag_match = THINKING_TAG_START_RE.search(lower_buffer)
        if tag_match:
            token = tag_match.group(1)
            candidates.append((tag_match.start(), f"</{token}>", tag_match.end()))

        if not candidates:
            return None

        return min(candidates, key=lambda item: item[0])

    def process_chunk(self, chunk: str) -> tuple[str, bool]:
        """Process a chunk and return (user_visible_content, is_thinking).

        Args:
            chunk: The raw text chunk from the model.

        Returns:
            Tuple of (content_to_emit, is_thinking_content) where:
            - content_to_emit: Text safe to show to user (empty if in thinking block)
            - is_thinking_content: True if this chunk is part of a thinking block
        """
        self.buffer += chunk
        lower_buffer = self.buffer.lower()

        # Check if we're starting a thinking block
        if not self.in_thinking:
            start_info = self._find_start_marker(lower_buffer)
            start_idx = start_info[0] if start_info else -1

            if start_idx >= 0:
                # Found start of thinking block
                # Emit anything before the block as user content
                if start_info is not None:
                    _, end_marker, search_start = start_info
                    self._end_marker = end_marker
                    self._search_start = max(0, search_start - start_idx)
                pre_thinking = self.buffer[:start_idx].strip()
                self.in_thinking = True
                self.buffer = self.buffer[start_idx:]

                if pre_thinking:
                    self.emitted_content += pre_thinking
                    return (pre_thinking, False)
                return ("", True)
            else:
                # Not in thinking block, safe to emit
                # But keep a small tail in case we're about to hit a marker
                if len(self.buffer) > 64:
                    safe_content = self.buffer[:-64]
                    self.buffer = self.buffer[-64:]
                    self.emitted_content += safe_content
                    return (safe_content, False)
                return ("", False)
        else:
            # We're inside a thinking block - look for end marker
            end_marker = self._end_marker or ":::"
            search_start = self._search_start
            end_idx = lower_buffer.find(end_marker, search_start)
            if end_idx >= 0:
                end_idx += len(end_marker)

            if end_idx >= 0:
                # Found end of thinking block
                self.in_thinking = False
                self._end_marker = None
                self._search_start = 0
                # Everything after the closing ::: is user content
                post_thinking = self.buffer[end_idx:].strip()
                self.buffer = ""

                if post_thinking:
                    self.emitted_content += post_thinking
                    return (post_thinking, False)
                return ("", True)
            else:
                # Still in thinking block
                return ("", True)

    def flush(self) -> str:
        """Flush any remaining buffered content.

        Called at end of stream to emit any remaining safe content.
        """
        if self.in_thinking:
            # We're stuck in a thinking block - don't emit anything
            return ""
        content = self.buffer.strip()
        self.buffer = ""
        if content:
            self.emitted_content += content
        return content

    @staticmethod
    def sanitize_final_content(content: str) -> str:
        """Strip any remaining thinking blocks and markdown data URIs from final content.

        This is a safety net for any thinking content or embedded images that
        slipped through during streaming. Should be called on the final message content.

        Args:
            content: The final message content.

        Returns:
            Content with all :::thinking blocks and markdown data URIs removed.
        """
        if not content:
            return content

        # Remove complete thinking blocks
        sanitized = THINKING_BLOCK_PATTERN.sub("", content)
        sanitized = THINK_TAG_PATTERN.sub("", sanitized)
        sanitized = THINK_FENCE_PATTERN.sub("", sanitized)

        # Also handle malformed/partial blocks
        # Remove any orphaned :::thinking markers
        sanitized = re.sub(
            rf":::\s*{THINKING_TOKEN_PATTERN}\s*",
            "",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            rf"</?\s*{THINKING_TOKEN_PATTERN}\s*>",
            "",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            rf"```\s*{THINKING_TOKEN_PATTERN}\s*",
            "",
            sanitized,
            flags=re.IGNORECASE,
        )

        # Remove any orphaned closing ::: that might be left
        # But be careful not to remove ::: in other contexts (like code blocks)
        # Only remove ::: at the start of a line or after whitespace
        sanitized = re.sub(r"(?:^|\n)\s*:::\s*(?=\n|$)", "\n", sanitized)

        # Remove markdown images with data URIs: ![alt](data:image/...)
        # These are generated when the model tries to embed base64 images in text
        # The images are already displayed as artifacts, so this is just garbage
        sanitized = MARKDOWN_DATA_URI_PATTERN.sub("", sanitized)

        # Clean up excess whitespace
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()

        return sanitized


class StreamEventHandler:
    """Processes agent stream events and emits AG-UI events.

    This class encapsulates the event processing loop that was previously
    embedded in run_unified_agent. It handles:
    - Tool start/end/error events
    - Chat model start/end/stream events
    - GenUI state updates
    - Todo normalization and reranking

    Usage:
        handler = StreamEventHandler(
            agent=compiled_agent,
            emitter=emitter,
            config=run_config,
            state=state,
        )
        final_output = await handler.stream_and_process()
    """

    def __init__(
        self,
        agent: "CompiledStateGraph",
        emitter: StreamEventEmitter,
        config: "RunnableConfig",
        state: "GraphState",
        messages: list[BaseMessage],
        *,
        helper: GemmaHelper | None = None,
        session_cache: dict[str, dict[str, Any]] | None = None,
        last_user_query: str | None = None,
    ):
        """Initialize the handler.

        Args:
            agent: Compiled LangGraph agent.
            emitter: StreamEventEmitter for emitting AG-UI events.
            config: LangGraph runnable config.
            state: Current graph state.
            messages: Prepared messages to send to the agent.
            helper: Optional GemmaHelper for reranking.
            session_cache: Optional session cache for caching reranks.
            last_user_query: Optional user query for reranking context.
        """
        self.agent = agent
        self.emitter = emitter
        self.config = config
        self.state = state
        self.messages = messages
        self.helper = helper
        self.session_cache = session_cache or {}
        self.last_user_query = last_user_query

        self.final_output: dict[str, Any] | None = None
        # Buffer user-visible text for Gemini thinking models so chain-of-thought
        # stays in the reasoning pane while the main chat only receives the
        # final, sanitized answer.
        self._gemini_buffer_runs: dict[str, list[str]] = {}

        # Get tracer if available
        self._tracer = trace.get_tracer(__name__) if OTEL_AVAILABLE else None

        # Tool result eviction manager (DeepAgents pattern)
        # Evicts large tool results to prevent memory overflow
        self._eviction_manager = ToolResultEvictionManager(
            storage_callback=self._store_evicted_result,
        )
        # Phase emission guards (deterministic trace fallbacks)
        self._phase_emitted: set[str] = set()

    async def stream_and_process(self) -> dict[str, Any] | None:
        """Main streaming loop with event processing.

        Returns:
            The final agent output, or None if streaming failed.
        """
        try:
            if settings.trace_mode != "off":
                planning_detail = self._build_planning_phase_detail()
                planning_content = "**Planning**"
                if planning_detail:
                    planning_content = f"{planning_content}\n\n{planning_detail}"
                self.emitter.add_trace_step(
                    step_type="thought",
                    content=planning_content,
                    metadata={"kind": "phase", "source": "system_phase"},
                )
            async for event in self._event_generator():
                await self._handle_event(event)
        except Exception as e:
            logger.opt(exception=True).error("Error during agent streaming: {}", e)

            # Emit warning event to notify UI that streaming failed
            self.emitter.emit_custom_event(
                "agent_thinking_trace",
                {
                    "totalSteps": 1,
                    "latestStep": {
                        "id": f"fallback-{int(time.time() * 1000)}",
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "type": "thought",
                        "content": f"Streaming failed ({type(e).__name__}), attempting fallback invoke...",
                        "metadata": {"error": str(e), "fallback": True},
                    },
                },
            )

            # Try fallback invoke with retry and exponential backoff (LangGraph pattern)
            # Retry transient errors up to 3 times with jitter to avoid thundering herd
            retry_config = RetryConfig(
                max_attempts=3,
                initial_interval=1.0,
                max_interval=10.0,
                backoff_factor=2.0,
                jitter=0.5,
                retry_exceptions=(ConnectionError, TimeoutError, OSError),
            )

            try:
                fallback_inputs = self._agent_inputs()

                async def _fallback_invoke() -> Any:
                    return await self.agent.ainvoke(
                        fallback_inputs,
                        config=self.config,
                    )

                self.final_output = await retry_with_backoff(
                    _fallback_invoke,
                    config=retry_config,
                )

                # Emit success event after fallback completes
                self.emitter.emit_custom_event(
                    "agent_thinking_trace",
                    {
                        "totalSteps": 2,
                        "latestStep": {
                            "id": f"fallback-complete-{int(time.time() * 1000)}",
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "type": "result",
                            "content": "Fallback invoke completed successfully (with retry)",
                            "metadata": {"fallback": True, "retry_enabled": True},
                        },
                    },
                )

            except Exception as fallback_error:
                # Emit error event if fallback also fails after all retries
                logger.opt(exception=True).error(
                    "Fallback invoke failed after retries: {}",
                    fallback_error,
                )
                self.emitter.emit_custom_event(
                    "agent_thinking_trace",
                    {
                        "totalSteps": 2,
                        "latestStep": {
                            "id": f"fallback-error-{int(time.time() * 1000)}",
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "type": "result",
                            "content": f"Fallback invoke failed after {retry_config.max_attempts} attempts: {type(fallback_error).__name__}",
                            "metadata": {
                                "error": str(fallback_error),
                                "fallback": True,
                                "failed": True,
                                "max_attempts": retry_config.max_attempts,
                            },
                        },
                    },
                )
                # Don't re-raise, return None to indicate failure
                self.final_output = None

        return self.final_output

    async def _event_generator(self):
        """Async generator that yields events from the agent stream."""
        span_cm = (
            self._tracer.start_as_current_span("agui.stream.run")
            if self._tracer
            else nullcontext()
        )

        with span_cm as run_span:
            cfg = (self.config or {}).get("configurable", {})
            if run_span is not None:
                run_span.set_attribute("agui.session_id", str(cfg.get("session_id") or ""))
                run_span.set_attribute("agui.trace_id", str(cfg.get("trace_id") or ""))
                run_span.set_attribute("agui.provider", str(cfg.get("provider") or ""))
                run_span.set_attribute("agui.model", str(cfg.get("model") or ""))

            try:
                async for event in self.agent.astream_events(
                    self._agent_inputs(),
                    config=self.config,
                    version="v2",
                ):
                    logger.debug(
                        "Stream event: {} name={}",
                        event.get("event"),
                        event.get("name"),
                    )
                    yield event

                if run_span is not None:
                    run_span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                if run_span is not None:
                    run_span.record_exception(exc)
                    run_span.set_status(Status(StatusCode.ERROR, "agent_run_failed"))
                logger.opt(exception=True).error("Agent run failed: {}", exc)
                raise

    def _agent_inputs(self) -> dict[str, Any]:
        """Build agent input dict."""
        return {
            "messages": list(self.messages),
            "attachments": self.state.attachments,
            "scratchpad": self.state.scratchpad,
        }

    async def _handle_event(self, event: dict[str, Any]) -> None:
        """Route event to appropriate handler."""
        event_type = event.get("event")
        handlers = {
            "on_tool_start": self._on_tool_start,
            "on_tool_end": self._on_tool_end,
            "on_tool_error": self._on_tool_error,
            "on_chat_model_start": self._on_model_start,
            "on_chat_model_end": self._on_model_end,
            "on_chat_model_stream": self._on_model_stream,
            "on_llm_stream": self._on_model_stream,
            "manually_emit_state": self._on_genui_state,
            "on_chain_end": self._on_chain_end,
            "on_graph_end": self._on_chain_end,
        }

        handler = handlers.get(event_type)
        if handler:
            await handler(event)

    async def _on_tool_start(self, event: dict[str, Any]) -> None:
        """Handle tool start event."""
        tool_data = event.get("data", {})
        tool_call_id = str(tool_data.get("tool_call_id", "unknown"))
        tool_name = self._extract_tool_name(event.get("name"), tool_call_id)
        event["name"] = tool_name

        tool_input = tool_data.get("input") or tool_data.get("tool_input")

        if tool_name == "trace_update":
            # Narration-only tool: emit a thought step from the tool INPUT (not output),
            # and store an optional goal to annotate the next real tool call.
            if settings.trace_mode == "off":
                return

            payload: dict[str, Any] = {}
            if isinstance(tool_input, dict):
                payload = dict(tool_input)
            elif isinstance(tool_input, str):
                try:
                    parsed = json.loads(tool_input)
                    if isinstance(parsed, dict):
                        payload = parsed
                except Exception:
                    payload = {}

            title = payload.get("title") if isinstance(payload.get("title"), str) else ""
            detail = payload.get("detail") if isinstance(payload.get("detail"), str) else ""
            kind = payload.get("kind") if isinstance(payload.get("kind"), str) else "thought"
            kind = kind.lower().strip() if kind else "thought"
            if kind not in {"thought", "phase"}:
                kind = "thought"

            goal = payload.get("goal_for_next_tool") or payload.get("goalForNextTool")
            if isinstance(goal, str) and goal.strip() and isinstance(self.state.scratchpad, dict):
                self.state.scratchpad["_next_tool_goal"] = goal.strip()

            heading = title.strip() or "Thought"
            body = detail.strip()
            content = f"**{heading}**\n\n{body}" if body else f"**{heading}**"
            self.emitter.add_trace_step(
                step_type="thought",
                content=content,
                metadata={"source": "narration", "kind": kind},
            )
            return

        tool_goal: str | None = None
        if (
            tool_name not in {"write_todos", "trace_update"}
            and isinstance(self.state.scratchpad, dict)
        ):
            raw_goal = self.state.scratchpad.pop("_next_tool_goal", None)
            if isinstance(raw_goal, str) and raw_goal.strip():
                tool_goal = raw_goal.strip()

        # Deterministic phase fallback on first real tool start
        if settings.trace_mode != "off" and tool_name not in {"write_todos"}:
            if "work" not in self._phase_emitted:
                lower = tool_name.lower()
                label = "Working"
                if any(key in lower for key in ("search", "tavily", "firecrawl", "grounding")):
                    label = "Searching"
                elif any(key in lower for key in ("read", "fetch", "scrape", "crawl", "map")):
                    label = "Exploring"

                phase_detail = self._build_tool_phase_detail(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_goal=tool_goal,
                )
                phase_content = f"**{label}**"
                if phase_detail:
                    phase_content = f"{phase_content}\n\n{phase_detail}"
                self.emitter.add_trace_step(
                    step_type="thought",
                    content=phase_content,
                    metadata={"kind": "phase", "source": "system_phase"},
                )
                self._phase_emitted.add("work")

        self.emitter.start_tool(tool_call_id, tool_name, tool_input, goal=tool_goal)
        # Drive todo status progression when tools start (skip write_todos itself)
        if tool_name not in {"write_todos", "trace_update"} and hasattr(self.emitter, "start_next_todo"):
            if self.emitter.start_next_todo():
                todos_dicts = self.emitter.get_todos_as_dicts()
                self.state.scratchpad["_todos"] = todos_dicts
                try:
                    self.state.todos = todos_dicts  # type: ignore[attr-defined]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("todo_state_set_failed_on_start", error=str(exc))

    async def _on_tool_end(self, event: dict[str, Any]) -> None:
        """Handle tool end event."""
        tool_data = event.get("data", {})
        output = tool_data.get("output")
        tool_call_id = str(tool_data.get("tool_call_id", "unknown"))
        tool_name = self._extract_tool_name(event.get("name"), tool_call_id)
        event["name"] = tool_name
        if tool_name == "trace_update":
            return

        # =====================================================================
        # SPECIAL TOOL HANDLING (BEFORE EVICTION)
        # Handle tools that need the full output (images, articles) before eviction
        # =====================================================================

        # Handle special tools that need full output
        if tool_name == "grounding_search":
            output = await self._rerank_grounding_results(output)

        if tool_name == "write_todos":
            todos_dicts = await self._handle_write_todos(output)
            output = {"todos": todos_dicts}

        # Handle image generation - emit as artifact for frontend display FIRST
        # Then strip base64 from output to prevent context overflow
        if tool_name == "generate_image":
            await self._handle_image_generation(output)
            # Strip large base64 data from output after emitting to frontend
            # This prevents 1-3MB per image from accumulating in conversation history
            output = self._compact_image_output(output)

        # Handle article creation - emit as artifact for frontend display
        if tool_name == "write_article":
            await self._handle_article_generation(output)

        # =====================================================================
        # TOOL RESULT EVICTION (DeepAgents pattern) - AFTER special handling
        # Evict large results to prevent memory overflow and context explosion
        # Skip eviction for tools that already compact their output (generate_image)
        # =====================================================================
        if output is not None and tool_name not in ("generate_image",):
            output_str = self._stringify_tool_output(output)
            evicted_output, was_evicted = self._eviction_manager.evict_if_needed(
                tool_call_id, tool_name, output_str
            )
            if was_evicted:
                # Replace output with eviction reference
                output = evicted_output
                logger.info(
                    "tool_result_evicted_in_handler",
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    original_length=len(output_str),
                )

        # Create summary for tool evidence
        summary = self._summarize_structured_content(output)

        # Build structured cards for UI display
        cards = build_tool_evidence_cards(
            output, tool_name, user_query=self.last_user_query, max_items=3
        )

        self.emitter.end_tool(tool_call_id, tool_name, output, summary, cards=cards)

        # Mark active todo as done when a tool finishes (skip write_todos)
        if tool_name not in {"write_todos", "trace_update"} and hasattr(self.emitter, "complete_active_todo"):
            if self.emitter.complete_active_todo():
                todos_dicts = self.emitter.get_todos_as_dicts()
                self.state.scratchpad["_todos"] = todos_dicts
                try:
                    self.state.todos = todos_dicts  # type: ignore[attr-defined]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("todo_state_set_failed_on_end", error=str(exc))

    async def _on_tool_error(self, event: dict[str, Any]) -> None:
        """Handle tool error event."""
        tool_data = event.get("data", {}) or {}
        tool_call_id = str(tool_data.get("tool_call_id", "unknown"))
        raw_error = (
            tool_data.get("error")
            or tool_data.get("error_message")
            or event.get("error")
        )
        tool_name = event.get("name") or tool_call_id or "tool"

        self.emitter.error_tool(tool_call_id, tool_name, raw_error)

    async def _on_model_start(self, event: dict[str, Any]) -> None:
        """Handle chat model start event."""
        data = event.get("data", {})
        run_id = event.get("run_id")

        if not run_id:
            return

        # Extract prompt preview
        prompt_messages = data.get("messages") or data.get("inputs") or []
        prompt_preview = self._extract_prompt_preview(prompt_messages)

        # Gemini 3 streams chain-of-thought as plain text. Buffer visible chunks
        # so only the final sanitized answer goes to the main chat.
        model_name = data.get("model")
        if isinstance(model_name, str) and "gemini-3" in model_name.lower():
            self._gemini_buffer_runs[str(run_id)] = []

        if settings.trace_mode != "off":
            self.emitter.start_thought(
                run_id=run_id,
                model=data.get("model"),
                prompt_preview=prompt_preview,
            )

    async def _on_model_end(self, event: dict[str, Any]) -> None:
        """Handle chat model end event.

        Also monitors Gemini implicit cache hits for cost optimization tracking.
        Gemini 2.5 models cache repeated context prefixes at 75% cost savings.
        """
        data = event.get("data", {})
        run_id = event.get("run_id")
        run_id_str = str(run_id) if run_id is not None else None

        # =====================================================================
        # GEMINI CACHE HIT MONITORING (Phase 2.2)
        # Log cache hit metrics for LangSmith observability
        # Gemini 2.5 returns cached_content_token_count in usage_metadata
        # =====================================================================
        self._log_cache_metrics(data)

        final_output = data.get("output")
        has_tool_calls, invalid_tool_calls = self._detect_tool_calls(final_output)

        if run_id and run_id in self.emitter.operations:
            content = ""
            if final_output:
                reasoning_content = self._extract_reasoning_content(final_output)

                # Only treat content as user-visible when this model call produced
                # a final text response (tool-call turns must never reach the main chat).
                if not has_tool_calls:
                    content = self._extract_user_visible_text(final_output)
                    content = ThinkingBlockTracker.sanitize_final_content(content)

                # If we have extracted reasoning, emit it to the thinking trace as a final summary
                # This ensures the trace panel gets the full reasoning without polluting the message
                if reasoning_content and run_id and settings.trace_mode in {"hybrid", "provider_reasoning"}:
                    cleaned_reasoning = reasoning_content.strip()
                    updated = self.emitter.update_trace_step(
                        alias=str(run_id),
                        replace_content=cleaned_reasoning or reasoning_content,
                        metadata={"source": "model_reasoning", "final": True},
                    )
                    if updated is None:
                        self.emitter.add_trace_step(
                            step_type="thought",
                            content=f"Model reasoning:\n{cleaned_reasoning or reasoning_content}",
                            metadata={"source": "model_reasoning", "final": True},
                        )

            # If we buffered Gemini 3 text, emit a single sanitized message now
            # IMPORTANT: never flush the buffer for tool-call turns.
            if run_id_str and run_id_str in self._gemini_buffer_runs:
                buffered_text = " ".join(self._gemini_buffer_runs.pop(run_id_str) or [])
                buffered_text = ThinkingBlockTracker.sanitize_final_content(buffered_text)

                if not has_tool_calls:
                    final_visible = content or buffered_text
                    if final_visible:
                        self.emitter.start_text_message()
                        self.emitter.emit_text_content(final_visible)
                        self.emitter.end_text_message()

            # Never attach the final user-visible answer to the thought trace step.
            # Thought steps must represent reasoning/narration only.
            self.emitter.end_thought(run_id, None)

        # Track final output
        if final_output:
            self.final_output = {"output": final_output}

            # Log and track invalid calls for observability
            if invalid_tool_calls:
                for inv in invalid_tool_calls:
                    logger.warning(
                        "invalid_tool_call_captured",
                        tool_name=inv.get("name"),
                        tool_id=inv.get("id"),
                        error=inv.get("error"),
                    )
                self.emitter.add_trace_step(
                    step_type="warning",
                    content=f"Captured {len(invalid_tool_calls)} invalid tool call(s)",
                    metadata={"invalid_calls": [dict(c) for c in invalid_tool_calls]},
                )

            # End any open text message stream (final text response only)
            if not has_tool_calls and getattr(self.emitter, "_message_started", False):
                self.emitter.end_text_message()

            # Mark todos complete only when the final response is produced (not tool-call turns)
            if not has_tool_calls and hasattr(self.emitter, "mark_all_todos_done"):
                self.emitter.mark_all_todos_done()
                try:
                    todos_dicts = self.emitter.get_todos_as_dicts()
                    self.state.scratchpad["_todos"] = todos_dicts
                    self.state.todos = todos_dicts  # type: ignore[attr-defined]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("todo_state_update_failed", error=str(exc))

        # Fallback: ensure we close any open text stream even if output is missing
        if getattr(self.emitter, "_message_started", False) and not final_output:
            self.emitter.end_text_message()

        # Clean up thinking tracker for this run
        if run_id_str and hasattr(self, "_thinking_trackers"):
            self._thinking_trackers.pop(run_id_str, None)

    async def _on_model_stream(self, event: dict[str, Any]) -> None:
        """Handle chat model streaming event.

        This method processes streaming text from the model and emits both:
        1. Thinking trace updates (for the sidebar)
        2. TEXT_MESSAGE_CONTENT events (for the main chat display)

        For Gemini 3 models, content may come as a list of content blocks:
        - [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "..."}]
        We extract thinking to the trace and only emit text to the main display.
        """
        run_id = event.get("run_id")
        if not run_id:
            return

        stream_data = event.get("data", {})
        chunk = stream_data.get("chunk") or stream_data.get("output")

        # Check if this chunk contains tool calls
        # If so, we don't emit text content for tool call arguments
        has_tool_calls = False
        if hasattr(chunk, "tool_calls") and chunk.tool_calls:
            has_tool_calls = True
        elif hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
            has_tool_calls = True

        # Extract and separate thinking from content (Gemini 3 format)
        raw_content = getattr(chunk, "content", chunk)
        thinking_text, visible_text = self._extract_thinking_and_text(raw_content)

        # Route thinking content to trace (not to main display)
        if thinking_text and settings.trace_mode in {"hybrid", "provider_reasoning"}:
            self.emitter.stream_thought_chunk(run_id, thinking_text)

        # Capture provider-specific streamed reasoning (xAI/OpenRouter/etc.)
        additional_kwargs = getattr(chunk, "additional_kwargs", None)
        if additional_kwargs is None and isinstance(chunk, dict):
            additional_kwargs = chunk.get("additional_kwargs")
        # Some providers surface tool calls via additional_kwargs.function_call
        if isinstance(additional_kwargs, dict) and (
            additional_kwargs.get("function_call")
            or additional_kwargs.get("tool_calls")
            or additional_kwargs.get("toolCalls")
        ):
            has_tool_calls = True
        kwargs_reasoning = self._extract_reasoning_from_kwargs(additional_kwargs)
        if kwargs_reasoning and settings.trace_mode in {"hybrid", "provider_reasoning"}:
            self.emitter.stream_thought_chunk(run_id, kwargs_reasoning)

        chunk_text = visible_text

        # Debug logging
        logger.debug(
            f"_on_model_stream: chunk_text={chunk_text[:100] if chunk_text else 'empty'!r}, "
            f"has_tool_calls={has_tool_calls}, chunk_type={type(chunk).__name__}"
        )

        if chunk_text:
            normalized = chunk_text.strip()
            if not normalized:
                logger.debug(
                    "empty_stream_chunk",
                    provider=getattr(self.state, "provider", None),
                    model=getattr(self.state, "model", None),
                    has_tool_calls=has_tool_calls,
                )
                return

            if normalized.lower() == "empty":
                logger.debug(
                    "empty_stream_placeholder_chunk",
                    provider=getattr(self.state, "provider", None),
                    model=getattr(self.state, "model", None),
                    has_tool_calls=has_tool_calls,
                )
                return

            # Use a per-run tracker to filter thinking blocks for all providers.
            if not hasattr(self, "_thinking_trackers"):
                self._thinking_trackers: dict[str, ThinkingBlockTracker] = {}
            run_id_str = str(run_id)
            if run_id_str not in self._thinking_trackers:
                self._thinking_trackers[run_id_str] = ThinkingBlockTracker()
            tracker = self._thinking_trackers[run_id_str]

            visible_content, is_thinking_chunk = tracker.process_chunk(chunk_text)

            # Filter markdown data-URI images before any early returns (including Gemini buffering).
            if visible_content and MARKDOWN_DATA_URI_PATTERN.search(visible_content):
                cleaned = MARKDOWN_DATA_URI_PATTERN.sub("", visible_content).strip()
                logger.debug(
                    "stripped_markdown_data_uri_early",
                    original_length=len(visible_content),
                    cleaned_length=len(cleaned),
                )
                if not cleaned:
                    return
                visible_content = cleaned

            # Skip base64-like blobs that sometimes leak into visible content.
            if visible_content and len(visible_content) > 500:
                sample = visible_content.replace("\n", "").replace(" ", "")[:500]
                stripped = sample.rstrip("=")
                if stripped and re.match(r"^[A-Za-z0-9+/]+$", stripped):
                    logger.debug(
                        "skipping_base64_like_visible_chunk",
                        length=len(visible_content),
                    )
                    return

            # CRITICAL: Filter markdown images with data URIs BEFORE any early returns
            # (including the Gemini 3 buffer path). The model sometimes outputs
            # ![alt](data:image/...) despite prompt instructions not to.
            if visible_content and MARKDOWN_DATA_URI_PATTERN.search(visible_content):
                cleaned = MARKDOWN_DATA_URI_PATTERN.sub("", visible_content).strip()
                logger.debug(
                    "stripped_markdown_data_uri_early",
                    original_length=len(visible_content),
                    cleaned_length=len(cleaned),
                )
                if not cleaned:
                    return  # Skip if entire chunk was just a markdown image
                visible_content = cleaned

            # Buffer Gemini 3 visible text so chain-of-thought never hits the
            # main chat stream; we'll emit a single sanitized answer at model_end.
            # IMPORTANT: never buffer tool-call turns or JSON-y payloads.
            if run_id_str in self._gemini_buffer_runs:
                looks_like_tool_payload = (
                    has_tool_calls
                    or "function_call" in normalized.lower()
                    or "tool_calls" in normalized.lower()
                )
                if visible_content and not looks_like_tool_payload:
                    self._gemini_buffer_runs[run_id_str].append(visible_content)
                return

            # Skip large content that looks like base64 or binary data
            # Filter visible_content since that's what gets emitted to the chat
            # Base64 images are typically 50KB-3MB; normal text chunks are < 8KB
            if visible_content and len(visible_content) > 8000:
                logger.debug("skipping_large_visible_chunk", length=len(visible_content))
                return

            # Also detect base64-like patterns (long strings of alphanumeric + /+=)
            # Real text has spaces, punctuation, varied patterns - base64 doesn't
            if visible_content and len(visible_content) > 500:
                sample = visible_content.replace('\n', '').replace(' ', '')[:500]
                stripped = sample.rstrip('=')
                # Check for valid base64 alphabet (no spaces, punctuation, or varied case patterns)
                if stripped and re.match(r'^[A-Za-z0-9+/]+$', stripped):
                    logger.debug("skipping_base64_like_visible_chunk", length=len(visible_content))
                    return

            # Filter markdown images with data URIs: ![alt](data:image/...)
            # These are generated when the model tries to "embed" images it generated
            # via the generate_image tool. The image is already displayed as an artifact,
            # so this markdown just creates garbage in the chat display.
            if visible_content and MARKDOWN_DATA_URI_PATTERN.search(visible_content):
                # Strip the markdown data URI from the content
                cleaned = MARKDOWN_DATA_URI_PATTERN.sub("", visible_content).strip()
                logger.debug(
                    "stripped_markdown_data_uri",
                    original_length=len(visible_content),
                    cleaned_length=len(cleaned),
                )
                if not cleaned:
                    # If the entire chunk was just a markdown image, skip it
                    return
                visible_content = cleaned

            looks_like_json = normalized.startswith(("{", "[")) and normalized.endswith(("}", "]"))

            # Emit as TEXT_MESSAGE_CONTENT for the main chat display
            # Only emit text content when not streaming tool call arguments,
            # not JSON payloads, and not inside a dedicated thinking block.
            if not has_tool_calls and not looks_like_json and visible_content and not is_thinking_chunk:
                logger.info(
                    "Emitting TEXT_MESSAGE_CONTENT: {!r}...",
                    visible_content[:50],
                )
                self.emitter.emit_text_content(visible_content)
        else:
            # Empty chunk (no text, no tool calls) — log for diagnostics (common with some providers)
            logger.debug(
                "empty_stream_chunk",
                provider=getattr(self.state, "provider", None),
                model=getattr(self.state, "model", None),
                has_tool_calls=has_tool_calls,
            )

    async def _on_genui_state(self, event: dict[str, Any]) -> None:
        """Handle GenUI state update event."""
        data = event.get("data", {})
        if data:
            self.emitter.emit_genui_state(data)

    async def _on_chain_end(self, event: dict[str, Any]) -> None:
        """Handle chain/graph end event."""
        # Only emit a final "result" trace step at the end of the compiled graph.
        # on_chain_end fires for many nested runnables and will otherwise spam the UI
        # with internal objects (Overwrite(...), additional_kwargs, tool calls, etc.).
        event_type = event.get("event")
        if event_type != "on_graph_end":
            return

        data = event.get("data", {})
        self.emitter.complete_root()

        if settings.trace_mode == "off":
            output = data.get("output")
            if isinstance(output, dict):
                self.final_output = output
            return

        output = data.get("output")
        if output:
            # Deterministic phase fallback before emitting the final result.
            writing_detail = self._build_writing_phase_detail()
            writing_content = "**Writing answer**"
            if writing_detail:
                writing_content = f"{writing_content}\n\n{writing_detail}"
            self.emitter.add_trace_step(
                step_type="thought",
                content=writing_content,
                metadata={"kind": "phase", "source": "system_phase"},
            )
            final_text = self._extract_final_assistant_text(output)
            if final_text:
                # Safety net: strip any stray thinking markers before UI display.
                final_text = ThinkingBlockTracker.sanitize_final_content(final_text)
                self.emitter.add_trace_step(
                    step_type="result",
                    content=final_text,
                    metadata={"source": event_type, "final": True},
                )

            if isinstance(output, dict):
                self.final_output = output

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _extract_tool_name(self, raw_name: Any, tool_call_id: str) -> str:
        """Extract tool name from event, with fallbacks."""
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name
        if tool_call_id and tool_call_id != "unknown":
            return tool_call_id
        return "tool"

    def _build_planning_phase_detail(self) -> str:
        """Build a lightweight planning detail string for the phase step."""
        user_query = (self.last_user_query or "").strip()
        if not user_query:
            return ""
        user_query = user_query.replace("\n", " ").strip()
        if len(user_query) > 280:
            user_query = user_query[:277] + "..."
        return f"- Task: {user_query}"

    def _build_writing_phase_detail(self) -> str:
        """Build a lightweight writing detail string for the phase step."""
        return "- Synthesizing results into a final response."

    def _build_tool_phase_detail(
        self,
        *,
        tool_name: str,
        tool_input: Any,
        tool_goal: str | None,
    ) -> str:
        """Describe the upcoming tool execution in a user-readable way."""
        query = self._extract_tool_query_preview(tool_input)
        lines: list[str] = []
        if tool_goal and tool_goal.strip():
            lines.append(f"Goal: {tool_goal.strip()}")
        if query:
            lines.append(f'Query: "{query}"')
        if not lines:
            return ""
        return "\n".join(f"- {line}" for line in lines)

    def _extract_tool_query_preview(self, tool_input: Any) -> str:
        """Extract a short, human-readable query from a tool input payload."""
        if tool_input is None:
            return ""

        payload: Any = tool_input
        if isinstance(tool_input, str):
            text = tool_input.strip()
            if not text:
                return ""
            try:
                parsed = json.loads(text)
                payload = parsed
            except Exception:
                payload = tool_input

        if isinstance(payload, dict):
            for key in ("query", "q", "prompt", "url", "path", "file", "id", "name", "title"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return self._truncate_trace_value(value.strip())
            return ""

        if isinstance(payload, str):
            return self._truncate_trace_value(payload.strip())

        return ""

    def _truncate_trace_value(self, value: str, max_len: int = 160) -> str:
        value = value.replace("\n", " ").strip()
        if len(value) <= max_len:
            return value
        return value[: max_len - 3] + "..."

    def _extract_prompt_preview(self, prompt_messages: Any) -> str:
        """Extract a preview of the prompt messages."""
        if not isinstance(prompt_messages, list):
            return ""

        preview_chunks = []
        for message in prompt_messages[-2:]:
            if isinstance(message, dict):
                preview_chunks.append(self._stringify_message_content(message.get("content")))
            else:
                preview_chunks.append(self._stringify_message_content(message))

        return " ".join(part for part in preview_chunks if part).strip()

    def _detect_tool_calls(self, output: Any) -> tuple[bool, list[InvalidToolCall]]:
        """Detect tool calls on a model output message.

        Tool-call turns must never emit user-visible text into the main chat stream.
        We treat both valid and invalid tool-call payloads as tool-call turns.
        """
        if output is None:
            return False, []

        # Some LangChain message types expose tool call chunks rather than tool_calls.
        if hasattr(output, "tool_call_chunks") and getattr(output, "tool_call_chunks"):
            return True, []

        raw_tool_calls: Any = None

        if hasattr(output, "tool_calls") and getattr(output, "tool_calls"):
            raw_tool_calls = getattr(output, "tool_calls")
        elif isinstance(output, dict) and output.get("tool_calls"):
            raw_tool_calls = output.get("tool_calls")
        else:
            additional_kwargs = getattr(output, "additional_kwargs", None)
            if additional_kwargs is None and isinstance(output, dict):
                additional_kwargs = output.get("additional_kwargs")
            if isinstance(additional_kwargs, dict):
                raw_tool_calls = (
                    additional_kwargs.get("tool_calls")
                    or additional_kwargs.get("toolCalls")
                    or additional_kwargs.get("function_call")
                )

        if not raw_tool_calls:
            return False, []

        if not isinstance(raw_tool_calls, list):
            raw_tool_calls = [raw_tool_calls]

        valid_calls, invalid_calls = parse_tool_calls_safely(raw_tool_calls)
        has_tool_calls = bool(valid_calls) or bool(invalid_calls)
        return has_tool_calls, invalid_calls

    def _extract_user_visible_text(self, output: Any) -> str:
        """Extract user-visible assistant text from a model output.

        This removes provider-specific thinking blocks and avoids rendering
        tool-call payloads, signatures, or other metadata-like structures.
        """
        if output is None:
            return ""

        # Prefer message.content when available.
        if isinstance(output, BaseMessage):
            raw_content: Any = output.content
        elif isinstance(output, dict):
            raw_content = output.get("content", "")
        else:
            raw_content = getattr(output, "content", output)

        _, visible_text = self._extract_thinking_and_text(raw_content)
        if visible_text:
            return str(visible_text)

        # Fallback to conservative stringification (filters tool calls/signatures).
        return self._stringify_message_content(raw_content).strip()

    def _extract_final_assistant_text(self, output: Any) -> str:
        """Extract the final assistant response text from a chain/graph output.

        LangGraph outputs frequently include dict-shaped state with message lists.
        We never want to stringify the whole state (it becomes JSON-ish dumps).
        """
        if output is None:
            return ""
        if isinstance(output, str):
            return output.strip()

        # If the output itself is a message, prefer it (but skip tool-call turns).
        if isinstance(output, BaseMessage):
            has_tool_calls, _ = self._detect_tool_calls(output)
            if has_tool_calls:
                return ""
            return self._extract_user_visible_text(output).strip()

        # Dict-shaped outputs (common LangGraph pattern)
        if isinstance(output, dict):
            # Prefer an explicit output field.
            direct_output = output.get("output")
            if direct_output is not None:
                return self._extract_final_assistant_text(direct_output)

            messages = output.get("messages")
            if isinstance(messages, list) and messages:
                for message in reversed(messages):
                    # Messages may already be BaseMessage objects or dicts.
                    if isinstance(message, BaseMessage):
                        has_tool_calls, _ = self._detect_tool_calls(message)
                        if has_tool_calls:
                            continue
                        text = self._extract_user_visible_text(message).strip()
                        if text:
                            return text
                    elif isinstance(message, dict):
                        role = str(message.get("role") or message.get("type") or "").lower()
                        if role not in ("assistant", "ai"):
                            continue
                        has_tool_calls, _ = self._detect_tool_calls(message)
                        if has_tool_calls:
                            continue
                        text = self._extract_user_visible_text(message).strip()
                        if text:
                            return text

        # List-shaped outputs (rare, but handle defensively)
        if isinstance(output, list):
            for item in reversed(output):
                text = self._extract_final_assistant_text(item)
                if text:
                    return text

        return ""

    def _stringify_message_content(self, content: Any) -> str:
        """Convert message content to string, filtering out thought signatures.

        Implements LangChain's content block pattern:
        - Separates reasoning/thinking blocks (handled by _extract_reasoning_content)
        - Filters out thought_signatures and extras with signatures
        - Preserves text content while avoiding serialization of metadata

        Handles Gemini 3 Pro content blocks which may include:
        - {"type": "text", "text": "...", "extras": {"signature": "..."}}
        - {"type": "thinking", "thinking": "...", "signature": "..."}
        - Large thought_signature data that should not be serialized
        """
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, (int, float, bool)):
            return str(content)
        if isinstance(content, BaseMessage):
            return self._stringify_message_content(content.content)
        if isinstance(content, dict):
            raw_type = content.get("type", "")
            block_type = raw_type.lower() if isinstance(raw_type, str) else ""

            # Skip tool-call payloads and non-user-visible blocks.
            if block_type in (
                "tool",
                "tool_call",
                "tool_calls",
                "tool_use",
                "function_call",
                "function",
                "call",
            ):
                return ""
            if any(
                key in content
                for key in (
                    "function_call",
                    "tool_calls",
                    "toolCalls",
                    "tool_call",
                    "toolCall",
                    "arguments",
                )
            ):
                return ""

            # =================================================================
            # REASONING BLOCKS - Skip in main content (handled separately)
            # LangChain pattern: reasoning blocks go to thinking trace only
            # =================================================================
            if block_type in ("thinking", "reasoning", "thought", "signature", "thought_signature"):
                return ""

            # Extract text from Gemini 3 content blocks
            text = content.get("text")
            if isinstance(text, str):
                return text

            # Check for "type": "text" blocks (Gemini 3 format)
            if block_type == "text" and "text" in content:
                return str(content["text"])

            # For other dicts, only include safe fields (avoid signature/extras)
            safe_content = {
                k: v for k, v in content.items()
                if k
                not in (
                    "extras",
                    "signature",
                    "thought_signature",
                    "thoughtSignature",
                    "thinking",
                    "function_call",
                    "tool_calls",
                    "toolCalls",
                    "tool_call",
                    "toolCall",
                    "arguments",
                )
                and not (isinstance(v, str) and len(v) > 10000)  # Skip large base64 blobs
            }
            if safe_content:
                import json
                return json.dumps(safe_content, default=str)
            return ""

        if isinstance(content, list):
            parts = []
            for part in content:
                part_str = self._stringify_message_content(part)
                if part_str:
                    parts.append(part_str)
            return " ".join(parts)
        return str(content)

    def _extract_thinking_and_text(self, content: Any) -> tuple[str, str]:
        """Extract thinking content and visible text from Gemini 3 content blocks.

        Gemini 3 models return content as a list of typed blocks:
        - [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "..."}]

        This method separates thinking (which goes to trace) from text (which
        goes to user display).

        Args:
            content: The raw content from the model (may be string, list, or dict).

        Returns:
            Tuple of (thinking_text, visible_text) where either may be empty.
        """
        thinking_parts: list[str] = []
        visible_parts: list[str] = []

        # Handle None or empty
        if content is None:
            return "", ""

        # Handle string content - check for :::thinking markers
        if isinstance(content, str):
            # Use ThinkingBlockTracker for marker-based content
            return "", content  # Return as visible text (tracker handles markers later)

        # Handle BaseMessage
        if isinstance(content, BaseMessage):
            return self._extract_thinking_and_text(content.content)

        # Handle single dict block
        if isinstance(content, dict):
            raw_type = content.get("type", "")
            block_type = raw_type.lower() if isinstance(raw_type, str) else ""

            # Tool call blocks should never be treated as visible text.
            if block_type in ("tool", "tool_use", "tool_call", "tool_calls", "function_call", "function"):
                return "", ""
            if any(
                key in content
                for key in (
                    "function_call",
                    "tool_calls",
                    "toolCalls",
                    "tool_call",
                    "toolCall",
                    "arguments",
                )
            ):
                return "", ""

            # Thinking block types (Gemini 3 format)
            if block_type in ("thinking", "reasoning", "thought"):
                thinking_text = (
                    content.get("thinking")
                    or content.get("reasoning")
                    or content.get("thought")
                    or content.get("content")
                    or ""
                )
                if thinking_text:
                    thinking_parts.append(str(thinking_text))
            # Text block type
            elif block_type == "text":
                text = content.get("text", "")
                if text:
                    visible_parts.append(str(text))
            # Skip signature blocks (thought_signature, signature)
            elif block_type in ("signature", "thought_signature"):
                pass  # Ignore signatures
            # Other dict content
            else:
                # Check for direct text field
                text = content.get("text")
                if isinstance(text, str) and text:
                    visible_parts.append(text)
                else:
                    # Avoid stringifying unknown dict blocks into JSON dumps.
                    raw_content = content.get("content")
                    if isinstance(raw_content, str) and raw_content:
                        visible_parts.append(raw_content)

        # Handle list of content blocks (Gemini 3 format)
        elif isinstance(content, list):
            for block in content:
                block_thinking, block_visible = self._extract_thinking_and_text(block)
                if block_thinking:
                    thinking_parts.append(block_thinking)
                if block_visible:
                    visible_parts.append(block_visible)

        # Fallback for other types
        else:
            visible_str = str(content)
            if visible_str:
                visible_parts.append(visible_str)

        return " ".join(thinking_parts), " ".join(visible_parts)

    def _extract_reasoning_from_kwargs(self, additional_kwargs: Any) -> str | None:
        """Extract reasoning text from additional_kwargs payloads."""
        if not isinstance(additional_kwargs, dict) or not additional_kwargs:
            return None

        def _coerce_reasoning(value: Any) -> str | None:
            if value is None:
                return None
            if isinstance(value, str):
                text = value.strip()
                return text or None
            if isinstance(value, list):
                parts = [str(part).strip() for part in value if part]
                combined = " ".join(part for part in parts if part)
                return combined or None
            if isinstance(value, dict):
                for key in ("content", "text", "reasoning", "thinking"):
                    sub = value.get(key)
                    if isinstance(sub, str) and sub.strip():
                        return sub.strip()
            return None

        for key in ("reasoning_content", "reasoning", "thinking"):
            extracted = _coerce_reasoning(additional_kwargs.get(key))
            if extracted:
                return extracted
        return None

    def _extract_reasoning_content(self, message: Any) -> str | None:
        """Extract reasoning/thinking content from model-specific response formats.

        Implements LangChain's multi-provider reasoning extraction pattern:
        - Gemini 3: content_blocks with type="thinking" or type="reasoning"
        - xAI/Grok: additional_kwargs.reasoning_content
        - Claude: additional_kwargs.thinking (extended thinking)
        - Anthropic-style: <think>...</think> tags in content
        - OpenAI-style: reasoning field in response

        The extracted reasoning is kept separate from main content to:
        1. Prevent UI overflow with large thinking traces
        2. Allow proper display in thinking trace panel
        3. Filter out thought_signatures that shouldn't be serialized

        Args:
            message: The LLM response message object.

        Returns:
            The reasoning content as a string, or None if not present.
        """
        if message is None:
            return None

        # Get additional_kwargs from message
        additional_kwargs = getattr(message, "additional_kwargs", {}) or {}

        # =================================================================
        # GEMINI 3 THINKING BLOCKS (LangChain pattern)
        # Content blocks may contain type="thinking" or type="reasoning"
        # =================================================================
        content = getattr(message, "content", None)
        if isinstance(content, list):
            reasoning_parts = []
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type", "")
                    # Gemini 3 uses "thinking" type
                    if block_type == "thinking":
                        thinking_text = block.get("thinking", "")
                        if thinking_text:
                            reasoning_parts.append(thinking_text)
                    # LangChain standardizes to "reasoning" type
                    elif block_type == "reasoning":
                        reasoning_text = block.get("reasoning", "")
                        if reasoning_text:
                            reasoning_parts.append(reasoning_text)
            if reasoning_parts:
                combined = "\n\n".join(reasoning_parts)
                logger.debug("extracted_gemini3_thinking", length=len(combined), blocks=len(reasoning_parts))
                return combined

        # Additional kwargs (xAI/OpenRouter/Claude/OpenAI-compatible)
        kwargs_reasoning = self._extract_reasoning_from_kwargs(additional_kwargs)
        if kwargs_reasoning:
            logger.debug("extracted_reasoning_kwargs", length=len(kwargs_reasoning))
            return kwargs_reasoning

        # Check for <think>...</think> tags in content (Anthropic XML style)
        content_str = self._stringify_message_content(content)
        if "<think>" in content_str and "</think>" in content_str:
            think_match = re.search(r"<think>([\s\S]*?)</think>", content_str)
            if think_match:
                logger.debug("extracted_think_tags", length=len(think_match.group(1)))
                return think_match.group(1).strip()

        return None

    async def _rerank_grounding_results(self, output: Any) -> Any:
        """Rerank grounding search results using Gemma helper."""
        if not self.helper or not self.last_user_query:
            return output

        results = extract_grounding_results(output)
        if not results:
            return output

        snippet_texts = extract_snippet_texts(results)
        if not snippet_texts:
            return output

        # Check cache
        rerank_key = None
        if self.session_cache:
            hasher = hashlib.md5()
            for s in snippet_texts:
                hasher.update(s.encode("utf-8", errors="ignore"))
            rerank_key = f"rerank:{self.last_user_query.lower().strip()}:{hasher.hexdigest()}"
            cached = self.session_cache.get(rerank_key, {}).get("value")
            if cached:
                return self._apply_reranked_results(output, results, cached)

        # Call helper with timeout
        try:
            import asyncio
            reranked = await asyncio.wait_for(
                self.helper.rerank(
                    snippet_texts,
                    self.last_user_query,
                    top_k=min(3, len(snippet_texts)),
                ),
                timeout=HELPER_TIMEOUT_SECONDS,
            )

            if reranked:
                # Cache the result
                if rerank_key and self.session_cache is not None:
                    self.session_cache[rerank_key] = {"value": reranked, "ts": time.time()}

                return self._apply_reranked_results(output, results, reranked)

        except asyncio.TimeoutError:
            logger.warning("gemma_rerank_grounding_timeout")
        except Exception as exc:
            logger.warning("gemma_rerank_grounding_failed", error=str(exc))

        return output

    def _apply_reranked_results(
        self,
        output: Any,
        results: list[dict[str, Any]],
        reranked_texts: list[str],
    ) -> Any:
        """Apply reranked order to results."""
        snippet_texts = extract_snippet_texts(results)

        # Preserve original items order based on reranked texts
        ordered = []
        seen = set()
        for text in reranked_texts:
            for item, raw in zip(results, snippet_texts):
                if raw == text and id(item) not in seen:
                    ordered.append(item)
                    seen.add(id(item))
                    break

        if ordered and isinstance(output, dict):
            output = dict(output)
            output["results"] = ordered

        return output

    async def _handle_write_todos(self, output: Any) -> list[dict[str, Any]]:
        """Handle write_todos tool output and return normalized todos."""
        from langchain_core.messages import ToolMessage

        # Debug: Log the actual type and value being passed
        output_type = type(output).__name__
        output_repr_str = repr(output)[:500] if output else "None"
        logger.info(
            "write_todos_handler_input: type={}, repr={!r}",
            output_type,
            output_repr_str,
        )

        # Extract content from ToolMessage if needed
        raw_output = output
        if isinstance(output, ToolMessage):
            raw_output = output.content
            content_type = type(raw_output).__name__
            content_repr_str = repr(raw_output)[:500] if raw_output else "None"
            logger.info(
                "write_todos_extracted_from_toolmessage: type={}, repr={!r}",
                content_type,
                content_repr_str,
            )

        self.emitter.update_todos(raw_output)

        # Update state
        todos_dicts = self.emitter.get_todos_as_dicts()
        self.state.scratchpad["_todos"] = todos_dicts
        try:
            self.state.todos = todos_dicts  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("state_todos_set_failed", error=str(exc))
        return todos_dicts

    async def _handle_image_generation(self, output: Any) -> None:
        """Handle generate_image tool output - emit as artifact for frontend display."""
        from langchain_core.messages import ToolMessage
        import json

        # Extract content from ToolMessage if needed
        raw_output = output
        if isinstance(output, ToolMessage):
            raw_output = output.content

        # Parse JSON string if needed
        if isinstance(raw_output, str):
            try:
                raw_output = json.loads(raw_output)
            except (json.JSONDecodeError, TypeError):
                pass

        # Check if image generation was successful
        if not isinstance(raw_output, dict):
            logger.debug("image_generation_output_not_dict: %s", type(raw_output).__name__)
            return

        if not raw_output.get("success"):
            logger.debug("image_generation_not_successful: %s", raw_output.get("error"))
            return

        image_base64 = raw_output.get("image_base64")
        if not image_base64:
            logger.debug("image_generation_no_image_data")
            return

        # Emit image artifact for frontend display
        self.emitter.emit_image_artifact(
            image_base64=image_base64,
            mime_type=raw_output.get("mime_type", "image/png"),
            title="Generated Image",
            prompt=raw_output.get("description"),
            aspect_ratio=raw_output.get("aspect_ratio"),
            resolution=raw_output.get("resolution"),
        )
        logger.info("image_artifact_emitted: aspect=%s, resolution=%s",
                   raw_output.get("aspect_ratio"), raw_output.get("resolution"))

    def _compact_image_output(self, output: Any) -> Any:
        """Strip large base64 image data from output to prevent context overflow.

        After emitting the image to frontend, we don't need the full base64
        in conversation history. Each 2K image is ~1-3MB, and multiple images
        can overflow the 2M token limit.

        Returns a compact version with just metadata, suitable for the model
        to understand the image was generated without storing megabytes of data.
        """
        from langchain_core.messages import ToolMessage
        import json

        # Handle ToolMessage wrapper
        raw_output = output
        is_tool_message = isinstance(output, ToolMessage)
        if is_tool_message:
            raw_output = output.content
            if isinstance(raw_output, str):
                try:
                    raw_output = json.loads(raw_output)
                except (json.JSONDecodeError, TypeError):
                    return output  # Can't parse, return as-is

        # Check if this is an image result with base64 data
        if not isinstance(raw_output, dict):
            return output
        if not raw_output.get("success") or not raw_output.get("image_base64"):
            return output

        # Create compact version without base64
        compact = {
            "success": True,
            "image_generated": True,  # Flag that image was created
            "description": raw_output.get("description"),
            "aspect_ratio": raw_output.get("aspect_ratio"),
            "resolution": raw_output.get("resolution"),
            "mime_type": raw_output.get("mime_type"),
            # Note for model: image was sent to user's display
            "status": "Image generated and displayed to user",
        }

        logger.debug("image_output_compacted: stripped %d bytes of base64",
                    len(raw_output.get("image_base64", "")))

        # Return appropriate type
        if is_tool_message:
            return ToolMessage(
                content=json.dumps(compact),
                tool_call_id=output.tool_call_id,
                name=output.name if hasattr(output, 'name') else "generate_image",
            )
        return compact

    async def _handle_article_generation(self, output: Any) -> None:
        """Handle write_article tool output - emit as artifact for frontend display."""
        from langchain_core.messages import ToolMessage
        import json

        # Extract content from ToolMessage if needed
        raw_output = output
        if isinstance(output, ToolMessage):
            raw_output = output.content

        # Parse JSON string if needed
        if isinstance(raw_output, str):
            try:
                raw_output = json.loads(raw_output)
            except (json.JSONDecodeError, TypeError):
                pass

        # Check if article creation was successful
        if not isinstance(raw_output, dict):
            logger.debug("article_generation_output_not_dict: %s", type(raw_output).__name__)
            return

        if not raw_output.get("success"):
            logger.debug("article_generation_not_successful: %s", raw_output.get("error"))
            return

        # The tool already calls emit_article_artifact via runtime
        # This handler is for cases where the artifact wasn't emitted during tool execution
        # Check if we have the raw content to emit
        title = raw_output.get("title", "Article")
        content = raw_output.get("content", "")
        images = raw_output.get("images")

        # Emit if we have content OR images (not just content)
        # This ensures image-only articles are properly displayed
        if content or images:
            self.emitter.emit_article_artifact(
                content=content or "",
                title=title,
                images=images,
            )
            logger.info(
                "article_artifact_emitted: title=%s, content_length=%d, images=%d",
                title, len(content or ""), len(images or [])
            )
        else:
            logger.warning("article_artifact_skipped: no content or images")

    def _summarize_structured_content(self, content: Any) -> str | None:
        """Create a plain-text summary of structured tool output."""
        import json
        import textwrap

        parsed: Any = None

        if isinstance(content, str):
            trimmed = content.strip()
            if not (trimmed.startswith(("{", "[")) and trimmed.endswith(("}", "]"))):
                return None
            try:
                parsed = json.loads(trimmed)
            except Exception:
                return None
        elif isinstance(content, (dict, list)):
            parsed = content
        else:
            return None

        entries = self._extract_structured_entries(parsed)
        if not entries:
            return None

        lines = ["Top matches:"]
        for idx, entry in enumerate(entries[:3], start=1):
            title = str(
                entry.get("title")
                or entry.get("name")
                or entry.get("id")
                or f"Result {idx}"
            ).strip()
            snippet = entry.get("snippet") or entry.get("summary") or entry.get("content") or ""
            snippet_text = (
                textwrap.shorten(str(snippet).strip(), width=220, placeholder="...")
                if snippet
                else ""
            )
            url = entry.get("url") or entry.get("link")
            line = f"{idx}. {title}"
            if snippet_text:
                line += f" — {snippet_text}"
            if isinstance(url, str) and url.strip():
                line += f" ({url.strip()})"
            lines.append(line)

        return "\n".join(lines)

    def _extract_structured_entries(self, data: Any) -> list[dict[str, Any]]:
        """Extract entries from structured data."""
        entries: list[dict[str, Any]] = []

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    entries.append(item)
                elif isinstance(item, list):
                    entries.extend([sub for sub in item if isinstance(sub, dict)])
        elif isinstance(data, dict):
            for key in ("results", "items", "data", "entries", "documents"):
                value = data.get(key)
                if isinstance(value, list):
                    entries.extend([item for item in value if isinstance(item, dict)])
            if not entries:
                # Check if any values are dicts
                dict_values = [v for v in data.values() if isinstance(v, dict)]
                if dict_values:
                    entries.extend(dict_values)
                elif all(isinstance(v, (str, int, float, bool, type(None))) for v in data.values()):
                    # Treat as single entry if it looks flat
                    entries.append(data)

        return entries

    # -------------------------------------------------------------------------
    # Tool Result Eviction Helpers (DeepAgents pattern)
    # -------------------------------------------------------------------------

    def _stringify_tool_output(self, output: Any) -> str:
        """Convert tool output to string for size checking.

        Handles ToolMessage, dict, list, and primitive types.
        Filters out known large binary fields (images, signatures).
        """
        from langchain_core.messages import ToolMessage
        import json

        # Handle ToolMessage wrapper
        if isinstance(output, ToolMessage):
            output = output.content

        # Handle string output
        if isinstance(output, str):
            return output

        # Handle dict - filter large binary fields
        if isinstance(output, dict):
            filtered = {
                k: v for k, v in output.items()
                if k not in (
                    "image_base64", "base64", "binary", "data",
                    "thought_signature", "signature", "extras"
                )
                and not (isinstance(v, str) and len(v) > 50000)  # Skip large strings
            }
            try:
                return json.dumps(filtered, default=str)
            except Exception:
                return str(output)

        # Handle list
        if isinstance(output, list):
            try:
                return json.dumps(output, default=str)
            except Exception:
                return str(output)

        return str(output)

    def _store_evicted_result(self, path: str, content: str) -> bool:
        """Store evicted tool result to scratchpad for later retrieval.

        This callback is used by ToolResultEvictionManager to persist
        large tool results that were evicted from the main context.

        Args:
            path: Virtual path for the evicted result (e.g., /large_tool_results/tool/id)
            content: The full tool result content

        Returns:
            True if storage succeeded
        """
        try:
            # Store in state scratchpad under special key
            evicted_results = self.state.scratchpad.setdefault("_evicted_tool_results", {})
            evicted_results[path] = {
                "content": content,
                "stored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "size": len(content),
            }
            logger.debug(
                "evicted_result_stored",
                path=path,
                size=len(content),
            )
            return True
        except Exception as e:
            logger.warning("evicted_result_storage_failed: {}", e)
            return False

    def _log_cache_metrics(self, data: dict[str, Any]) -> None:
        """Log Gemini implicit cache hit metrics for observability.

        Gemini 2.5 models support implicit context caching:
        - First request with a unique prefix pays full price
        - Subsequent requests with same prefix get ~75% cost savings
        - Cache is automatic - no explicit configuration needed

        Metrics are logged for LangSmith dashboard monitoring.

        Args:
            data: The model end event data containing output and usage info.
        """
        try:
            output = data.get("output")
            if not output:
                return

            # Extract usage_metadata from response
            # LangChain wraps this in different locations depending on the provider
            usage_metadata = None

            # Try response_metadata.usage_metadata (LangChain standard)
            response_metadata = getattr(output, "response_metadata", None) or {}
            if isinstance(response_metadata, dict):
                usage_metadata = response_metadata.get("usage_metadata")

            # Try additional_kwargs.usage_metadata (some providers)
            if not usage_metadata:
                additional_kwargs = getattr(output, "additional_kwargs", None) or {}
                if isinstance(additional_kwargs, dict):
                    usage_metadata = additional_kwargs.get("usage_metadata")

            # Try llm_output.usage_metadata (older pattern)
            if not usage_metadata and isinstance(data, dict):
                llm_output = data.get("llm_output") or {}
                if isinstance(llm_output, dict):
                    usage_metadata = llm_output.get("usage_metadata")

            if not usage_metadata or not isinstance(usage_metadata, dict):
                return

            # Extract cache metrics (Gemini 2.5 format)
            cached_tokens = usage_metadata.get("cached_content_token_count", 0)
            prompt_tokens = usage_metadata.get("prompt_token_count", 0)
            total_tokens = usage_metadata.get("total_token_count", 0)
            candidates_tokens = usage_metadata.get("candidates_token_count", 0)

            # Only log if we have meaningful cache data
            if cached_tokens > 0 and prompt_tokens > 0:
                cache_ratio = cached_tokens / prompt_tokens
                estimated_savings = cached_tokens * 0.75  # 75% savings on cached tokens

                logger.info(
                    "gemini_cache_metrics",
                    cache_hit_ratio=f"{cache_ratio:.1%}",
                    cached_tokens=cached_tokens,
                    prompt_tokens=prompt_tokens,
                    total_tokens=total_tokens,
                    candidates_tokens=candidates_tokens,
                    estimated_token_savings=int(estimated_savings),
                    model=getattr(self.state, "model", "unknown"),
                    provider=getattr(self.state, "provider", "unknown"),
                )

                # Store in scratchpad for LangSmith metadata
                if hasattr(self.state, "scratchpad") and isinstance(self.state.scratchpad, dict):
                    system_bucket = self.state.scratchpad.setdefault("_system", {})
                    system_bucket["cache_metrics"] = {
                        "cache_hit_ratio": round(cache_ratio, 3),
                        "cached_tokens": cached_tokens,
                        "prompt_tokens": prompt_tokens,
                        "total_tokens": total_tokens,
                        "estimated_savings_pct": round(cache_ratio * 75, 1),
                    }

            elif prompt_tokens > 0:
                # No cache hit - log for comparison
                logger.debug(
                    "gemini_cache_miss",
                    prompt_tokens=prompt_tokens,
                    total_tokens=total_tokens,
                    model=getattr(self.state, "model", "unknown"),
                )

        except Exception as e:
            # Cache metrics are optional - don't fail on errors
            logger.debug("cache_metrics_extraction_failed: {}", e)
