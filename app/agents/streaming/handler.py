"""Stream event handler for processing agent events and emitting AG-UI events.

Extracted from agent_sparrow.py to provide a clean, modular interface for
handling LangGraph streaming events.
"""

from __future__ import annotations

import hashlib
import time
from contextlib import nullcontext
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from langchain_core.messages import AIMessage, BaseMessage
from loguru import logger

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

from .emitter import StreamEventEmitter
from .event_types import _safe_json_value
from .normalizers import (
    build_tool_evidence_cards,
    extract_grounding_results,
    extract_snippet_texts,
)
from .utils import (
    ToolResultEvictionManager,
    count_tokens_approximately,
    truncate_if_too_long,
    parse_tool_calls_safely,
    InvalidToolCall,
    retry_with_backoff,
    RetryConfig,
    TOOL_TOKEN_LIMIT,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.config import RunnableConfig
    from app.agents.orchestration.orchestration.state import GraphState
    from app.agents.helpers.gemma_helper import GemmaHelper


# Timeout for Gemma helper calls
HELPER_TIMEOUT_SECONDS = 8.0

# Pattern for detecting thinking blocks
import re
THINKING_BLOCK_PATTERN = re.compile(
    r":::(?:thinking|think)\s*([\s\S]*?)\s*:::",
    re.IGNORECASE
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
            # Look for start marker
            start_idx = lower_buffer.find(":::thinking")
            if start_idx == -1:
                start_idx = lower_buffer.find(":::think\n")
            if start_idx == -1 and lower_buffer.startswith(":::"):
                # Treat as start only when the marker is followed by a thinking token
                remainder = lower_buffer[3:].lstrip()
                if remainder.startswith("thinking") or remainder.startswith("think"):
                    start_idx = 0

            if start_idx >= 0:
                # Found start of thinking block
                # Emit anything before the block as user content
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
                if len(self.buffer) > 20:
                    safe_content = self.buffer[:-20]
                    self.buffer = self.buffer[-20:]
                    self.emitted_content += safe_content
                    return (safe_content, False)
                return ("", False)
        else:
            # We're inside a thinking block - look for end marker
            # Find closing ::: that's not the opening marker
            end_idx = -1
            search_start = 12 if lower_buffer.startswith(":::thinking") else 10

            # Look for standalone ::: on its own or followed by newline
            remaining = lower_buffer[search_start:]
            close_match = remaining.find(":::")
            if close_match >= 0:
                end_idx = search_start + close_match + 3

            if end_idx >= 0:
                # Found end of thinking block
                self.in_thinking = False
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
        """Strip any remaining thinking blocks from final content.

        This is a safety net for any thinking content that slipped through
        during streaming. Should be called on the final message content.

        Args:
            content: The final message content.

        Returns:
            Content with all :::thinking blocks removed.
        """
        if not content:
            return content

        # Remove complete thinking blocks
        sanitized = THINKING_BLOCK_PATTERN.sub("", content)

        # Also handle malformed/partial blocks
        # Remove any orphaned :::thinking markers
        sanitized = re.sub(r":::(?:thinking|think)\s*", "", sanitized, flags=re.IGNORECASE)

        # Remove any orphaned closing ::: that might be left
        # But be careful not to remove ::: in other contexts (like code blocks)
        # Only remove ::: at the start of a line or after whitespace
        sanitized = re.sub(r"(?:^|\n)\s*:::\s*(?=\n|$)", "\n", sanitized)

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
        messages: List[BaseMessage],
        *,
        helper: Optional["GemmaHelper"] = None,
        session_cache: Optional[Dict[str, Dict[str, Any]]] = None,
        last_user_query: Optional[str] = None,
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

        self.final_output: Optional[Dict[str, Any]] = None

        # Get tracer if available
        self._tracer = trace.get_tracer(__name__) if OTEL_AVAILABLE else None

        # Tool result eviction manager (DeepAgents pattern)
        # Evicts large tool results to prevent memory overflow
        self._eviction_manager = ToolResultEvictionManager(
            storage_callback=self._store_evicted_result,
        )

    async def stream_and_process(self) -> Optional[Dict[str, Any]]:
        """Main streaming loop with event processing.

        Returns:
            The final agent output, or None if streaming failed.
        """
        try:
            async for event in self._event_generator():
                await self._handle_event(event)
        except Exception as e:
            logger.error(f"Error during agent streaming: {e}")

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
                self.final_output = await retry_with_backoff(
                    self.agent.ainvoke,
                    self._agent_inputs(),
                    config=retry_config,
                    # Pass original config as keyword arg
                    **{"config": self.config},
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
                logger.error(f"Fallback invoke failed after retries: {fallback_error}")
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
                    logger.debug(f"Stream event: {event.get('event')} name={event.get('name')}")
                    yield event

                if run_span is not None:
                    run_span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                if run_span is not None:
                    run_span.record_exception(exc)
                    run_span.set_status(Status(StatusCode.ERROR, "agent_run_failed"))
                logger.error(f"Agent run failed: {str(exc)}", exc_info=True)
                raise

    def _agent_inputs(self) -> Dict[str, Any]:
        """Build agent input dict."""
        return {
            "messages": list(self.messages),
            "attachments": self.state.attachments,
            "scratchpad": self.state.scratchpad,
        }

    async def _handle_event(self, event: Dict[str, Any]) -> None:
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

    async def _on_tool_start(self, event: Dict[str, Any]) -> None:
        """Handle tool start event."""
        tool_data = event.get("data", {})
        tool_call_id = str(tool_data.get("tool_call_id", "unknown"))
        tool_name = self._extract_tool_name(event.get("name"), tool_call_id)
        event["name"] = tool_name

        tool_input = tool_data.get("input") or tool_data.get("tool_input")

        self.emitter.start_tool(tool_call_id, tool_name, tool_input)
        # Drive todo status progression when tools start (skip write_todos itself)
        if tool_name != "write_todos" and hasattr(self.emitter, "start_next_todo"):
            if self.emitter.start_next_todo():
                todos_dicts = self.emitter.get_todos_as_dicts()
                self.state.scratchpad["_todos"] = todos_dicts
                try:
                    self.state.todos = todos_dicts  # type: ignore[attr-defined]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("todo_state_set_failed_on_start", error=str(exc))

    async def _on_tool_end(self, event: Dict[str, Any]) -> None:
        """Handle tool end event."""
        tool_data = event.get("data", {})
        output = tool_data.get("output")
        tool_call_id = str(tool_data.get("tool_call_id", "unknown"))
        tool_name = self._extract_tool_name(event.get("name"), tool_call_id)
        event["name"] = tool_name

        # =====================================================================
        # SPECIAL TOOL HANDLING (BEFORE EVICTION)
        # Handle tools that need the full output (images, articles) before eviction
        # =====================================================================

        # Handle special tools that need full output
        if tool_name == "grounding_search":
            output = await self._rerank_grounding_results(output)

        if tool_name == "write_todos":
            await self._handle_write_todos(output)

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
        if tool_name != "write_todos" and hasattr(self.emitter, "complete_active_todo"):
            if self.emitter.complete_active_todo():
                todos_dicts = self.emitter.get_todos_as_dicts()
                self.state.scratchpad["_todos"] = todos_dicts
                try:
                    self.state.todos = todos_dicts  # type: ignore[attr-defined]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("todo_state_set_failed_on_end", error=str(exc))

    async def _on_tool_error(self, event: Dict[str, Any]) -> None:
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

    async def _on_model_start(self, event: Dict[str, Any]) -> None:
        """Handle chat model start event."""
        data = event.get("data", {})
        run_id = event.get("run_id")

        if not run_id:
            return

        # Extract prompt preview
        prompt_messages = data.get("messages") or data.get("inputs") or []
        prompt_preview = self._extract_prompt_preview(prompt_messages)

        self.emitter.start_thought(
            run_id=run_id,
            model=data.get("model"),
            prompt_preview=prompt_preview,
        )

    async def _on_model_end(self, event: Dict[str, Any]) -> None:
        """Handle chat model end event."""
        data = event.get("data", {})
        run_id = event.get("run_id")
        run_id_str = str(run_id) if run_id is not None else None

        if run_id and run_id in self.emitter.operations:
            output = data.get("output")
            content = ""
            if output:
                # Extract reasoning content from xAI/Grok responses (additional_kwargs.reasoning_content)
                reasoning_content = self._extract_reasoning_content(output)
                main_content = self._stringify_message_content(
                    getattr(output, "content", output)
                )

                # Sanitize main_content to remove any leaked thinking blocks
                # This is a safety net for Gemini models that may include :::thinking in output
                main_content = ThinkingBlockTracker.sanitize_final_content(main_content)

                # Combine reasoning and main content
                if reasoning_content:
                    content = f":::thinking\n{reasoning_content}\n:::\n{main_content}"
                else:
                    content = main_content

            self.emitter.end_thought(run_id, content)

        # Track final output
        final_output = data.get("output")
        if final_output:
            self.final_output = {"output": final_output}

            # End any open text message stream
            # Check if this is a final text response (not a tool call)
            # Uses safe parsing to capture invalid tool calls (LangChain pattern)
            has_tool_calls = False
            invalid_tool_calls: List[InvalidToolCall] = []

            raw_tool_calls = None
            if hasattr(final_output, "tool_calls") and final_output.tool_calls:
                raw_tool_calls = final_output.tool_calls
            elif isinstance(final_output, dict) and final_output.get("tool_calls"):
                raw_tool_calls = final_output.get("tool_calls")

            if raw_tool_calls:
                # Safe parse to capture any malformed tool calls
                valid_calls, invalid_calls = parse_tool_calls_safely(raw_tool_calls)
                has_tool_calls = len(valid_calls) > 0

                # Log and track invalid calls for observability
                if invalid_calls:
                    invalid_tool_calls = invalid_calls
                    for inv in invalid_calls:
                        logger.warning(
                            "invalid_tool_call_captured",
                            tool_name=inv.get("name"),
                            tool_id=inv.get("id"),
                            error=inv.get("error"),
                        )
                    # Emit trace step for visibility
                    self.emitter.add_trace_step(
                        step_type="warning",
                        content=f"Captured {len(invalid_calls)} invalid tool call(s)",
                        metadata={"invalid_calls": [dict(c) for c in invalid_calls]},
                    )

            if not has_tool_calls and getattr(self.emitter, '_message_started', False):
                self.emitter.end_text_message()

            # Mark todos complete when the final response is produced
            if hasattr(self.emitter, "mark_all_todos_done"):
                self.emitter.mark_all_todos_done()
                try:
                    todos_dicts = self.emitter.get_todos_as_dicts()
                    self.state.scratchpad["_todos"] = todos_dicts
                    self.state.todos = todos_dicts  # type: ignore[attr-defined]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("todo_state_update_failed", error=str(exc))

        # Fallback: ensure we close any open text stream even if output is missing
        if getattr(self.emitter, '_message_started', False) and not final_output:
            self.emitter.end_text_message()

        # Clean up thinking tracker for this run
        if run_id_str and hasattr(self, "_thinking_trackers"):
            self._thinking_trackers.pop(run_id_str, None)

    async def _on_model_stream(self, event: Dict[str, Any]) -> None:
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
        if thinking_text:
            self.emitter.stream_thought_chunk(run_id, thinking_text)

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
                self._thinking_trackers: Dict[str, ThinkingBlockTracker] = {}
            run_id_str = str(run_id)
            if run_id_str not in self._thinking_trackers:
                self._thinking_trackers[run_id_str] = ThinkingBlockTracker()
            tracker = self._thinking_trackers[run_id_str]

            visible_content, is_thinking_chunk = tracker.process_chunk(chunk_text)

            # Always emit to thinking trace
            self.emitter.stream_thought_chunk(run_id, chunk_text)

            looks_like_json = normalized.startswith(("{", "[")) and normalized.endswith(("}", "]"))

            # Emit as TEXT_MESSAGE_CONTENT for the main chat display
            # Only emit text content when not streaming tool call arguments,
            # not JSON payloads, and not inside a dedicated thinking block.
            if not has_tool_calls and not looks_like_json and visible_content and not is_thinking_chunk:
                logger.info(f"Emitting TEXT_MESSAGE_CONTENT: {visible_content[:50]!r}...")
                self.emitter.emit_text_content(visible_content)
        else:
            # Empty chunk (no text, no tool calls) — log for diagnostics (common with some providers)
            logger.debug(
                "empty_stream_chunk",
                provider=getattr(self.state, "provider", None),
                model=getattr(self.state, "model", None),
                has_tool_calls=has_tool_calls,
            )

    async def _on_genui_state(self, event: Dict[str, Any]) -> None:
        """Handle GenUI state update event."""
        data = event.get("data", {})
        if data:
            self.emitter.emit_genui_state(data)

    async def _on_chain_end(self, event: Dict[str, Any]) -> None:
        """Handle chain/graph end event."""
        data = event.get("data", {})
        self.emitter.complete_root()

        output = data.get("output")
        if output:
            # Add final result trace step
            summarized = self._stringify_message_content(output)
            if summarized:
                self.emitter.add_trace_step(
                    step_type="result",
                    content=summarized,
                    metadata={"source": event.get("event")},
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
            block_type = content.get("type", "")

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
                if k not in ("extras", "signature", "thought_signature", "thoughtSignature", "thinking")
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
            block_type = content.get("type", "")

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
                if isinstance(text, str):
                    visible_parts.append(text)
                else:
                    # Fallback to stringify (filters out thinking types)
                    visible_str = self._stringify_message_content(content)
                    if visible_str:
                        visible_parts.append(visible_str)

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

    def _extract_reasoning_content(self, message: Any) -> Optional[str]:
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

        # xAI/Grok reasoning content
        reasoning = additional_kwargs.get("reasoning_content")
        if reasoning:
            logger.debug("extracted_xai_reasoning", length=len(str(reasoning)))
            return str(reasoning)

        # Claude extended thinking
        thinking = additional_kwargs.get("thinking")
        if thinking:
            logger.debug("extracted_claude_thinking", length=len(str(thinking)))
            return str(thinking)

        # OpenAI-style reasoning field (some models)
        reasoning_field = additional_kwargs.get("reasoning")
        if reasoning_field:
            logger.debug("extracted_openai_reasoning", length=len(str(reasoning_field)))
            return str(reasoning_field)

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
        results: List[Dict[str, Any]],
        reranked_texts: List[str],
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

    async def _handle_write_todos(self, output: Any) -> None:
        """Handle write_todos tool output."""
        from langchain_core.messages import ToolMessage

        # Debug: Log the actual type and value being passed
        output_type = type(output).__name__
        output_repr_str = repr(output)[:500] if output else "None"
        logger.info(f"write_todos_handler_input: type={output_type}, repr={output_repr_str}")

        # Extract content from ToolMessage if needed
        raw_output = output
        if isinstance(output, ToolMessage):
            raw_output = output.content
            content_type = type(raw_output).__name__
            content_repr_str = repr(raw_output)[:500] if raw_output else "None"
            logger.info(f"write_todos_extracted_from_toolmessage: type={content_type}, repr={content_repr_str}")

        todos = self.emitter.update_todos(raw_output)

        # Update state
        todos_dicts = self.emitter.get_todos_as_dicts()
        self.state.scratchpad["_todos"] = todos_dicts
        try:
            self.state.todos = todos_dicts  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("state_todos_set_failed", error=str(exc))

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
        content = raw_output.get("content")
        images = raw_output.get("images")

        if content:
            self.emitter.emit_article_artifact(
                content=content,
                title=title,
                images=images,
            )
            logger.info("article_artifact_emitted: title=%s, content_length=%d",
                       title, len(content))

    def _summarize_structured_content(self, content: Any) -> Optional[str]:
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

    def _extract_structured_entries(self, data: Any) -> List[Dict[str, Any]]:
        """Extract entries from structured data."""
        entries: List[Dict[str, Any]] = []

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
            logger.warning(f"evicted_result_storage_failed: {e}")
            return False
