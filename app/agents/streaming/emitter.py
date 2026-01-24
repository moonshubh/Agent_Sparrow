"""Centralized AG-UI event emission with state tracking.

Extracted from agent_sparrow.py to provide a clean interface for
emitting custom events to the AG-UI frontend.

Implements patterns from DeepAgents, LangChain, and LangGraph:
- Content block separation (reasoning vs text)
- Windowed trace with progressive summarization (not truncation)
- Deduplication tracking for streaming events
- Lazy emission (only emit on actual changes)
"""

from __future__ import annotations

import hashlib
import itertools
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from loguru import logger

from .event_types import (
    AgentThinkingTraceEvent,
    AgentTimelineUpdateEvent,
    AgentTodosUpdateEvent,
    TimelineOperation,
    TodoItem,
    ToolEvidenceUpdateEvent,
    TraceStep,
)
from .normalizers import normalize_todos
from .utils import count_tokens_approximately, BackpressureQueue, safe_json_value


# =============================================================================
# CONFIGURATION - Based on DeepAgents/LangGraph patterns
# =============================================================================

# Throttle delay between consecutive image artifact emissions (in seconds)
# Prevents frontend memory overflow when multiple large images are generated in parallel
IMAGE_EMISSION_THROTTLE_MS = 500  # 500ms between images

# Thinking trace windowing configuration (from DeepAgents pattern)
# Instead of truncating content, we use windowing + summarization
TRACE_WINDOW_SIZE = 15  # Keep last N steps in full detail
TRACE_SUMMARY_THRESHOLD = 30  # Start summarizing when trace exceeds this
MAX_STEP_CONTENT_FULL = 15000  # Full content limit per step (~15KB)
MAX_STEP_CONTENT_SUMMARY = 500  # Summary length for older steps
DEDUP_EMISSION_WINDOW_MS = 100  # Deduplicate emissions within this window

# Streaming backpressure configuration (LangChain pattern)
# Controls buffering when events are generated faster than they can be consumed
BACKPRESSURE_QUEUE_SIZE = 100  # Max pending events before blocking
TEXT_BUFFER_FLUSH_INTERVAL_MS = 50  # Flush text buffer every N ms

# Thinking stream buffering (Phase 2)
THINKING_BUFFER_FLUSH_MS = 150  # Flush buffered thinking every 150ms
THINKING_BUFFER_MIN_CHARS = 50  # Minimum chars before flushing
THINKING_BUFFER_MAX_CHARS = 2000  # Hard cap to prevent runaway buffers

# Subagent thinking buffering (Phase 2)
SUBAGENT_THINKING_BUFFER_FLUSH_MS = 150
SUBAGENT_THINKING_BUFFER_MIN_CHARS = 50
SUBAGENT_THINKING_BUFFER_MAX_CHARS = 2000


class StreamEventEmitter:
    """Centralized AG-UI event emission with state tracking.

    This class manages all state related to the agent timeline, thinking trace,
    and todos, and provides methods for emitting properly typed events to the
    AG-UI frontend via the LangGraph stream writer.

    Usage:
        emitter = StreamEventEmitter(writer, root_id="trace-123")
        emitter.start_root_operation(provider="google", model="gemini-2.5-flash")

        # Tool execution
        emitter.start_tool(tool_call_id, tool_name)
        emitter.end_tool(tool_call_id, output)

        # Thinking
        emitter.start_thought(run_id, model="gemini-2.5-flash")
        emitter.end_thought(run_id, content="...")

        # Todos
        emitter.update_todos(raw_todos)
    """

    def __init__(
        self,
        writer: Optional[Callable[[Dict[str, Any]], None]],
        root_id: Optional[str] = None,
    ):
        """Initialize the emitter.

        Args:
            writer: LangGraph stream writer function, or None for no-op mode.
            root_id: Root operation ID (defaults to timestamp-based ID).
        """
        self.writer = writer
        self.root_id = root_id or f"run-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        # State tracking
        self.operations: Dict[str, TimelineOperation] = {}
        self.thinking_trace: List[TraceStep] = []
        self.trace_step_aliases: Dict[str, TraceStep] = {}
        self.todo_items: List[TodoItem] = []
        self.todo_operation_ids: Set[str] = set()

        # Counters
        self._trace_step_counter = itertools.count(1)

        # Image emission throttling
        self._last_image_emission_time: float = 0.0

        # =====================================================================
        # NEW: Deduplication & windowing state (LangGraph/DeepAgents patterns)
        # =====================================================================
        # Track emitted content hashes for deduplication
        self._emitted_trace_hashes: Set[str] = set()
        self._last_trace_emission_time: float = 0.0
        self._last_emitted_trace_version: int = 0
        self._last_emitted_trace_fingerprint: Optional[str] = None

        # Summarized older steps (progressive summarization)
        self._summarized_steps: List[Dict[str, Any]] = []

        # Content block buffers (LangChain pattern - separate reasoning from text)
        self._pending_text_buffer: str = ""
        self._reasoning_blocks: List[Dict[str, Any]] = []

        # Backpressure queue for high-volume event streams (LangChain pattern)
        # Used for batching and rate-limiting event emissions
        self._event_queue: Optional[BackpressureQueue] = None
        self._last_text_flush_time: float = 0.0

        # Thinking buffers (hybrid buffering)
        self._thinking_buffer: Dict[str, str] = {}
        self._thinking_buffer_last_flush: Dict[str, float] = {}

        # Subagent thinking buffers (keyed by tool_call_id)
        self._subagent_thinking_buffer: Dict[str, str] = {}
        self._subagent_thinking_last_flush: Dict[str, float] = {}
        self._subagent_thinking_type: Dict[str, Optional[str]] = {}

    # -------------------------------------------------------------------------
    # Low-level emission
    # -------------------------------------------------------------------------

    def emit_custom_event(self, name: str, payload: Dict[str, Any]) -> None:
        """Emit a custom AG-UI event."""
        if self.writer is None:
            return
        self.writer({
            "event": "on_custom_event",
            "name": name,
            "data": payload,
        })

    def emit_tool_call_start(self, tool_call_id: str, tool_name: str) -> None:
        """Emit TOOL_CALL_START event."""
        if self.writer is None:
            return
        self.writer({
            "type": "TOOL_CALL_START",
            "toolCallId": tool_call_id,
            "toolCallName": tool_name,
        })

    def emit_tool_call_end(
        self,
        tool_call_id: str,
        tool_name: str,
        result: Optional[str] = None,
    ) -> None:
        """Emit TOOL_CALL_END event."""
        if self.writer is None:
            return
        self.writer({
            "type": "TOOL_CALL_END",
            "toolCallId": tool_call_id,
            "toolCallName": tool_name,
            "result": result,
        })

    def emit_genui_state(self, data: Dict[str, Any]) -> None:
        """Emit GenUI state update via CUSTOM event."""
        if self.writer is None or not data:
            return
        self.writer({
            "type": "CUSTOM",
            "name": "genui_state_update",
            "value": data,
        })

    def emit_image_artifact(
        self,
        *,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        mime_type: str = "image/png",
        title: str = "Generated Image",
        prompt: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        resolution: Optional[str] = None,
        page_url: Optional[str] = None,
    ) -> None:
        """Emit image artifact via CUSTOM event for frontend display.

        Includes throttling to prevent multiple large images from overwhelming
        the frontend when generated in parallel (e.g., Grok generating 8 images).

        Args:
            image_url: Retrievable URL to the image (preferred; Phase V)
            image_base64: Base64-encoded image data (legacy fallback)
            mime_type: MIME type of the image (e.g., 'image/png')
            title: Display title for the artifact
            prompt: Original prompt used to generate the image
            aspect_ratio: Aspect ratio of the image
            resolution: Resolution of the image
            page_url: Optional source page URL for web-sourced images
        """
        if self.writer is None:
            return
        if image_url is None and image_base64 is None:
            return

        # Throttle: wait if last emission was too recent
        # Prevents frontend memory overflow from rapid large payload bursts
        now = time.time()
        elapsed_ms = (now - self._last_image_emission_time) * 1000
        if elapsed_ms < IMAGE_EMISSION_THROTTLE_MS and self._last_image_emission_time > 0:
            wait_time = (IMAGE_EMISSION_THROTTLE_MS - elapsed_ms) / 1000
            logger.debug(
                "emit_image_artifact: throttling, waiting {:.2f}s",
                wait_time,
            )
            time.sleep(wait_time)

        import uuid
        artifact_id = f"img-{uuid.uuid4().hex[:8]}"
        message_id = getattr(self, "_current_message_id", None) or f"msg-{self.root_id}"

        # Use emit_custom_event for consistent event format with other custom events
        payload: Dict[str, Any] = {
            "id": artifact_id,
            "type": "image",
            "title": title,
            "content": prompt or "",
            "messageId": message_id,
            "mimeType": mime_type,
            "altText": prompt or title,
            "aspectRatio": aspect_ratio,
            "resolution": resolution,
        }
        if image_url is not None:
            payload["imageUrl"] = image_url
        if image_base64 is not None:
            payload["imageData"] = image_base64
        if page_url is not None:
            payload["pageUrl"] = page_url

        self.emit_custom_event("image_artifact", payload)

        # Update last emission time after successful emit
        self._last_image_emission_time = time.time()
        logger.info(
            "emit_image_artifact: id={}, mime={}, title={}",
            artifact_id,
            mime_type,
            title,
        )

    def emit_article_artifact(
        self,
        content: str,
        title: str = "Article",
        images: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        """Emit article artifact via CUSTOM event for frontend display.

        Creates an editable article artifact with markdown content and optional images.

        Args:
            content: Markdown content of the article
            title: Display title for the artifact
            images: Optional list of image dicts with 'url' and 'alt' keys to embed
        """
        if self.writer is None:
            return

        # Warn if content is empty but images exist
        if not content.strip() and images:
            logger.warning(
                "emit_article_artifact: empty content with images present. "
                "Article will contain only embedded images."
            )

        # Early return only if BOTH content AND images are empty
        if not content.strip() and not images:
            logger.warning("emit_article_artifact: no content or images")
            return

        import uuid
        artifact_id = f"article-{uuid.uuid4().hex[:8]}"
        message_id = getattr(self, "_current_message_id", None) or f"msg-{self.root_id}"

        # If images provided, append them to the content as markdown
        if images:
            # Only add separator if there's existing content
            if content.strip():
                image_section = "\n\n---\n\n## Images\n\n"
            else:
                # For image-only articles, start with a header
                image_section = "# Generated Images\n\n"

            for img in images:
                alt = img.get("alt", "Image")
                url = img.get("url", "")
                if url:
                    image_section += f"![{alt}]({url})\n\n"
            content = content + image_section if content else image_section

        self.emit_custom_event("article_artifact", {
            "id": artifact_id,
            "type": "article",
            "title": title,
            "content": content,
            "messageId": message_id,
        })
        logger.info(
            "emit_article_artifact: id={}, title={}, content_length={}",
            artifact_id,
            title,
            len(content),
        )

    # -------------------------------------------------------------------------
    # Text message emission (AG-UI protocol)
    # -------------------------------------------------------------------------

    def start_text_message(self, message_id: Optional[str] = None) -> str:
        """Emit TEXT_MESSAGE_START event.

        Returns:
            The message_id used for the message.
        """
        if message_id is None:
            message_id = f"msg-{self.root_id}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"

        self._current_message_id = message_id
        self._message_started = True

        if self.writer is not None:
            self.writer({
                "type": "TEXT_MESSAGE_START",
                "messageId": message_id,
                "role": "assistant",
            })
        return message_id

    def emit_text_content(self, delta: str) -> None:
        """Emit TEXT_MESSAGE_CONTENT event with streaming text delta.

        Args:
            delta: The text chunk to emit.
        """
        # Hot path: avoid per-chunk logging (can easily exceed provider log limits).
        if self.writer is None or not delta:
            return

        # Ensure message is started
        if not getattr(self, '_message_started', False):
            logger.debug("emit_text_content: Starting new text message")
            self.start_text_message()

        event = {
            "type": "TEXT_MESSAGE_CONTENT",
            "messageId": getattr(self, '_current_message_id', self.root_id),
            "delta": delta,
        }
        self.writer(event)

    def end_text_message(self) -> None:
        """Emit TEXT_MESSAGE_END event."""
        if self.writer is None:
            return

        message_id = getattr(self, '_current_message_id', self.root_id)
        self._message_started = False

        self.writer({
            "type": "TEXT_MESSAGE_END",
            "messageId": message_id,
        })

    # -------------------------------------------------------------------------
    # Timeline operations
    # -------------------------------------------------------------------------

    def start_root_operation(
        self,
        name: str = "Unified Agent",
        **metadata: Any,
    ) -> TimelineOperation:
        """Initialize the root agent operation."""
        root_op = TimelineOperation.create_root(
            root_id=self.root_id,
            name=name,
            **metadata,
        )
        self.operations[self.root_id] = root_op
        self._emit_timeline_update(self.root_id)
        return root_op

    def start_tool(
        self,
        tool_call_id: str,
        tool_name: str,
        input_data: Optional[Any] = None,
        goal: Optional[str] = None,
    ) -> TimelineOperation:
        """Record a tool operation starting."""
        tool_op = self.operations.get(tool_call_id)
        if tool_op is None:
            tool_op = TimelineOperation.create_tool(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                parent_id=self.root_id,
            )
            self.operations[tool_call_id] = tool_op
            self._add_to_parent(tool_call_id)
        if goal:
            tool_op.metadata["goal"] = goal

        # Emit events
        self._emit_timeline_update(tool_call_id)
        self.emit_tool_call_start(tool_call_id, tool_name)

        # Add trace step (skip internal housekeeping tools; those have dedicated UI)
        if tool_name not in {"write_todos", "trace_update"}:
            trace_meta: Dict[str, Any] = {
                "toolCallId": tool_call_id,
                "toolName": tool_name,
            }
            if input_data is not None:
                trace_meta["input"] = safe_json_value(input_data)
            if goal:
                trace_meta["goal"] = goal

            self.add_trace_step(
                step_type="action",
                content=f"Executing {tool_name}",
                metadata=trace_meta,
            )

        return tool_op

    def end_tool(
        self,
        tool_call_id: str,
        tool_name: str,
        output: Any,
        summary: Optional[str] = None,
        cards: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Record a tool operation completing."""
        tool_op = self.operations.get(tool_call_id)
        if tool_op is None:
            # Create if missing
            tool_op = TimelineOperation.create_tool(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                parent_id=self.root_id,
            )
            self.operations[tool_call_id] = tool_op

        # Complete the operation
        tool_op.complete(success=True)

        # Add output preview to metadata
        safe_output = safe_json_value(output) if output is not None else None
        if safe_output is not None:
            tool_op.metadata["rawOutputPreview"] = str(safe_output)[:1000]

        # Emit events
        self._emit_timeline_update(tool_call_id)
        # Use explicit None check to preserve falsy but valid outputs (0, False, "")
        self.emit_tool_call_end(
            tool_call_id, tool_name, str(output) if output is not None else None
        )

        # Emit tool evidence with cards
        self.emit_custom_event(
            "tool_evidence_update",
            ToolEvidenceUpdateEvent(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                output=safe_output,
                summary=summary,
                cards=cards or [],
            ).to_dict(),
        )

        # Add trace step (skip internal housekeeping tools; those have dedicated UI)
        if tool_name not in {"write_todos", "trace_update"}:
            result_meta: Dict[str, Any] = {
                "toolCallId": tool_call_id,
                "toolName": tool_name,
            }
            goal = tool_op.metadata.get("goal") if tool_op else None
            if isinstance(goal, str) and goal.strip():
                result_meta["goal"] = goal.strip()
            if safe_output is not None:
                # Avoid retaining large tool outputs in memory via thinking trace metadata.
                if isinstance(safe_output, str) and len(safe_output) <= 2000:
                    result_meta["output"] = safe_output
                else:
                    preview = tool_op.metadata.get("rawOutputPreview") if tool_op else None
                    if isinstance(preview, str) and preview.strip():
                        result_meta["outputPreview"] = preview
            if tool_op.duration is not None:
                result_meta["durationMs"] = tool_op.duration

            self.add_trace_step(
                step_type="result",
                content=f"{tool_name} completed",
                metadata=result_meta,
            )

    def error_tool(
        self,
        tool_call_id: str,
        tool_name: str,
        error: Any,
    ) -> None:
        """Record a tool operation failing."""
        tool_op = self.operations.get(tool_call_id)
        if tool_op:
            tool_op.complete(success=False)
            tool_op.metadata["error"] = str(error)

        self._emit_timeline_update(tool_call_id)

        # Emit error event
        self.emit_custom_event(
            "tool_error",
            {
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "error": str(error),
            },
        )

        # Add trace step
        self.add_trace_step(
            step_type="result",
            content=f"{tool_name} failed",
            metadata={"toolCallId": tool_call_id, "error": str(error)},
        )

        logger.error(
            "Tool error tool_name={} tool_call_id={} error={}",
            tool_name,
            tool_call_id,
            error,
        )

    def start_thought(
        self,
        run_id: str,
        model: Optional[str] = None,
        prompt_preview: Optional[str] = None,
    ) -> TimelineOperation:
        """Record a thought/reasoning operation starting."""
        thought_op = TimelineOperation.create_thought(
            run_id=run_id,
            parent_id=self.root_id,
            model=model,
        )
        self.operations[run_id] = thought_op
        self._add_to_parent(run_id)

        self._emit_timeline_update(run_id)

        # Add trace step
        thinking_meta: Dict[str, Any] = {}
        if model:
            thinking_meta["model"] = model
        if prompt_preview:
            thinking_meta["promptPreview"] = prompt_preview[:600]

        self.add_trace_step(
            step_type="thought",
            content="",
            metadata=thinking_meta,
            alias=str(run_id),
        )

        return thought_op

    def end_thought(
        self,
        run_id: str,
        content: Optional[str] = None,
    ) -> None:
        """Record a thought/reasoning operation completing."""
        run_id_str = str(run_id)

        # Flush any buffered thinking before finalizing.
        self._flush_thinking_buffer(run_id_str)
        self._thinking_buffer.pop(run_id_str, None)
        self._thinking_buffer_last_flush.pop(run_id_str, None)

        thought_op = self.operations.get(run_id)
        duration_ms: Optional[int] = None
        status: Optional[str] = None
        if thought_op:
            thought_op.complete(success=True)
            duration_ms = thought_op.duration
            status = thought_op.status
            if content:
                thought_op.metadata["content"] = str(content)

        self._emit_timeline_update(run_id)

        trace_meta: Dict[str, Any] = {}
        if duration_ms is not None:
            trace_meta["durationMs"] = duration_ms
        if status is not None:
            trace_meta["status"] = status

        # Update trace step (never attach final user-visible answer here).
        self.update_trace_step(
            alias=str(run_id),
            metadata=trace_meta or None,
            finalize=True,
        )

    def _flush_thinking_buffer(self, run_id: str) -> None:
        buffer = self._thinking_buffer.get(run_id, "")
        if not buffer:
            return

        updated = self.update_trace_step(run_id, append_content=buffer)
        if updated is None:
            self.add_trace_step(
                step_type="thought",
                content=buffer,
                alias=run_id,
            )

        self._thinking_buffer[run_id] = ""
        self._thinking_buffer_last_flush[run_id] = time.time() * 1000

    def stream_thought_chunk(self, run_id: str, chunk_text: str) -> None:
        """Append streaming content to a thought trace step with buffering."""
        if not chunk_text:
            return

        # Allow reasonable chunk sizes - windowed emission handles summarization
        # Only cap extremely large chunks that might indicate malformed data
        max_chunk_size = 5000  # Increased from 2000 - let windowing handle rest
        if len(chunk_text) > max_chunk_size:
            chunk_text = (
                f"[...{len(chunk_text) - max_chunk_size} chars...]"
                f"{chunk_text[-max_chunk_size:]}"
            )

        run_id_str = str(run_id)
        now_ms = time.time() * 1000

        if run_id_str not in self._thinking_buffer:
            self._thinking_buffer[run_id_str] = ""
            self._thinking_buffer_last_flush[run_id_str] = now_ms

        self._thinking_buffer[run_id_str] += chunk_text
        buffer = self._thinking_buffer[run_id_str]
        last_flush = self._thinking_buffer_last_flush.get(run_id_str, now_ms)

        should_flush = (
            len(buffer) >= THINKING_BUFFER_MAX_CHARS
            or (
                (now_ms - last_flush) >= THINKING_BUFFER_FLUSH_MS
                and len(buffer) >= THINKING_BUFFER_MIN_CHARS
            )
        )

        if should_flush:
            self._flush_thinking_buffer(run_id_str)

    def _flush_subagent_thinking_buffer(self, tool_call_id: str) -> None:
        buffer = self._subagent_thinking_buffer.get(tool_call_id, "")
        if not buffer:
            return

        payload = {
            "toolCallId": tool_call_id,
            "delta": buffer,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        subagent_type = self._subagent_thinking_type.get(tool_call_id)
        if subagent_type:
            payload["subagentType"] = subagent_type

        self.emit_custom_event("subagent_thinking_delta", payload)

        self._subagent_thinking_buffer[tool_call_id] = ""
        self._subagent_thinking_last_flush[tool_call_id] = time.time() * 1000

    def stream_subagent_thinking_delta(
        self,
        tool_call_id: str,
        delta: str,
        subagent_type: Optional[str] = None,
    ) -> None:
        """Buffer and emit subagent thinking deltas for the UI."""
        if not delta:
            return

        key = str(tool_call_id)
        now_ms = time.time() * 1000

        if key not in self._subagent_thinking_buffer:
            self._subagent_thinking_buffer[key] = ""
            self._subagent_thinking_last_flush[key] = now_ms

        if subagent_type:
            self._subagent_thinking_type[key] = subagent_type

        self._subagent_thinking_buffer[key] += delta
        buffer = self._subagent_thinking_buffer[key]
        last_flush = self._subagent_thinking_last_flush.get(key, now_ms)

        should_flush = (
            len(buffer) >= SUBAGENT_THINKING_BUFFER_MAX_CHARS
            or (
                (now_ms - last_flush) >= SUBAGENT_THINKING_BUFFER_FLUSH_MS
                and len(buffer) >= SUBAGENT_THINKING_BUFFER_MIN_CHARS
            )
        )

        if should_flush:
            self._flush_subagent_thinking_buffer(key)

    def flush_subagent_thinking(self, tool_call_id: str) -> None:
        """Flush and clear any pending subagent thinking buffer."""
        key = str(tool_call_id)
        self._flush_subagent_thinking_buffer(key)
        self._subagent_thinking_buffer.pop(key, None)
        self._subagent_thinking_last_flush.pop(key, None)
        self._subagent_thinking_type.pop(key, None)

    def complete_root(self) -> None:
        """Mark the root operation as completed."""
        root_op = self.operations.get(self.root_id)
        if root_op and root_op.end_time is None:
            root_op.complete(success=True)
            self._emit_timeline_update(self.root_id)

    # -------------------------------------------------------------------------
    # Thinking trace
    # -------------------------------------------------------------------------

    def add_trace_step(
        self,
        step_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        alias: Optional[str] = None,
    ) -> TraceStep:
        """Add a new step to the thinking trace."""
        step = TraceStep.create(
            step_id=f"{self.root_id}-trace-{next(self._trace_step_counter)}",
            step_type=step_type,  # type: ignore
            content=content,
            metadata=metadata,
        )
        self.thinking_trace.append(step)

        if alias:
            self.trace_step_aliases[alias] = step

        self._emit_thinking_trace(step)
        return step

    def update_trace_step(
        self,
        alias: str,
        append_content: Optional[str] = None,
        replace_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        step_type: Optional[str] = None,
        finalize: bool = False,
    ) -> Optional[TraceStep]:
        """Update an existing trace step by alias.

        Content is allowed to grow up to MAX_STEP_CONTENT_FULL during accumulation.
        The emission step handles summarization for older steps, preserving quality.
        """
        step = self.trace_step_aliases.get(alias)
        if step is None:
            return None

        # Allow content to grow during accumulation
        # Summarization happens at emission time (windowed approach)
        if append_content:
            new_content = f"{step.content}{append_content}"
            # Only cap at the FULL limit (15KB) - emission will handle summarization
            if len(new_content) > MAX_STEP_CONTENT_FULL:
                # Keep the most recent content, summarize the beginning
                overflow = len(new_content) - MAX_STEP_CONTENT_FULL
                step.content = f"[...{overflow} chars earlier...]\n{new_content[-MAX_STEP_CONTENT_FULL:]}"
                step.metadata["_content_overflow"] = overflow
            else:
                step.content = new_content

        if replace_content is not None:
            if len(replace_content) > MAX_STEP_CONTENT_FULL:
                overflow = len(replace_content) - MAX_STEP_CONTENT_FULL
                step.content = f"[...{overflow} chars earlier...]\n{replace_content[-MAX_STEP_CONTENT_FULL:]}"
                step.metadata["_content_overflow"] = overflow
            else:
                step.content = replace_content

        if metadata:
            step.metadata.update(metadata)
        if step_type:
            step.type = step_type  # type: ignore

        step.timestamp = datetime.now(timezone.utc).isoformat()

        # Emit with deduplication check (won't spam if called rapidly)
        self._emit_thinking_trace(step)

        if finalize:
            self.trace_step_aliases.pop(alias, None)
            # Force final emission to ensure UI gets the complete state
            self._emit_thinking_trace(step, force=True)

        return step

    # -------------------------------------------------------------------------
    # Todos
    # -------------------------------------------------------------------------

    def update_todos(self, raw_todos: Any) -> List[TodoItem]:
        """Update the todo list from raw tool output."""
        # Debug logging to understand the raw_todos structure
        raw_type = type(raw_todos).__name__
        logger.debug("write_todos_debug: type=%s", raw_type)

        normalized = normalize_todos(raw_todos, self.root_id)
        if not normalized:
            logger.info(
                "write_todos_no_new_items: prior_count={}, raw_type={}",
                len(self.todo_items),
                raw_type,
            )
            # Emit current state even if no changes
            self._sync_todo_operations()
            self._emit_todos()
            return self.todo_items

        # Preserve progress across imperfect todo rewrites:
        # - If the model re-emits the same todos with new IDs, keep the existing IDs.
        # - Never regress status (pending < in_progress < done).
        status_rank = {"pending": 0, "in_progress": 1, "done": 2}

        existing_by_id = {todo.id: todo for todo in self.todo_items if todo.id}
        existing_by_title: Dict[str, TodoItem] = {}
        duplicate_titles: Set[str] = set()
        matched_existing_ids: Set[str] = set()
        for todo in self.todo_items:
            title_key = " ".join((todo.title or "").split()).lower()
            if not title_key:
                continue
            if title_key in existing_by_title:
                duplicate_titles.add(title_key)
            else:
                existing_by_title[title_key] = todo
        for key in duplicate_titles:
            existing_by_title.pop(key, None)

        for todo_dict in normalized:
            title_key = " ".join(str(todo_dict.get("title") or "").split()).lower()
            incoming_id = str(todo_dict.get("id") or "")
            match: Optional[TodoItem] = None
            if incoming_id and incoming_id in existing_by_id:
                candidate = existing_by_id[incoming_id]
                if candidate.id and candidate.id not in matched_existing_ids:
                    match = candidate
            elif title_key and title_key in existing_by_title:
                candidate = existing_by_title[title_key]
                if candidate.id and candidate.id not in matched_existing_ids:
                    match = candidate

            if match is None:
                continue

            if match.id:
                matched_existing_ids.add(match.id)

            # Keep a stable ID when the same title reappears with a new/random ID.
            if title_key and incoming_id and incoming_id != match.id:
                todo_dict["id"] = match.id

            # Never regress status.
            incoming_status = str(todo_dict.get("status") or "pending").lower()
            existing_status = str(match.status or "pending").lower()  # type: ignore[attr-defined]
            if status_rank.get(existing_status, 0) > status_rank.get(incoming_status, 0):
                todo_dict["status"] = existing_status

            # Merge metadata (new fields win).
            incoming_meta = todo_dict.get("metadata")
            if not isinstance(incoming_meta, dict):
                incoming_meta = {}
            merged_meta = {**(match.metadata or {}), **incoming_meta}
            todo_dict["metadata"] = merged_meta

        # Ensure IDs are unique (model output can contain duplicates).
        seen_ids: Set[str] = set()
        for idx, todo_dict in enumerate(normalized, start=1):
            base_id = str(todo_dict.get("id") or "").strip() or f"{self.root_id}-todo-{idx}"
            unique_id = base_id
            suffix = 2
            while unique_id in seen_ids:
                unique_id = f"{base_id}-{suffix}"
                suffix += 1
            todo_dict["id"] = unique_id
            seen_ids.add(unique_id)

        logger.info("write_todos_normalized normalized_count=%s", len(normalized))

        # Convert to TodoItem objects
        self.todo_items.clear()
        for todo_dict in normalized:
            self.todo_items.append(TodoItem(
                id=todo_dict["id"],
                title=todo_dict["title"],
                status=todo_dict["status"],  # type: ignore
                metadata=todo_dict.get("metadata", {}),
            ))

        # Update timeline and emit events
        self._sync_todo_operations()
        self._emit_todos()

        return self.todo_items

    def get_todos_as_dicts(self) -> List[Dict[str, Any]]:
        """Get todos as list of dicts for state storage."""
        return [todo.to_dict() for todo in self.todo_items]

    def start_next_todo(self) -> bool:
        """Mark the next pending todo as in_progress."""
        for todo in self.todo_items:
            status = (todo.status or "pending").lower()  # type: ignore[attr-defined]
            if status == "pending":
                todo.status = "in_progress"  # type: ignore[attr-defined]
                self._sync_todo_operations()
                self._emit_todos()
                return True
        return False

    def complete_active_todo(self) -> bool:
        """Mark the first in-progress todo as done."""
        for todo in self.todo_items:
            status = (todo.status or "pending").lower()  # type: ignore[attr-defined]
            if status == "in_progress":
                todo.status = "done"  # type: ignore[attr-defined]
                self._sync_todo_operations()
                self._emit_todos()
                return True
        return False

    def mark_all_todos_done(self) -> None:
        """Mark all todos as done and emit updates."""
        if not self.todo_items:
            return

        changed = False
        for todo in self.todo_items:
            if (todo.status or "pending").lower() != "done":  # type: ignore[attr-defined]
                todo.status = "done"  # type: ignore[attr-defined]
                changed = True

        if changed:
            self._sync_todo_operations()
            self._emit_todos()

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _add_to_parent(self, child_id: str) -> None:
        """Add a child operation to the root parent."""
        parent_op = self.operations.get(self.root_id)
        if parent_op is not None and child_id not in parent_op.children:
            parent_op.children.append(child_id)

    def _emit_timeline_update(self, current_op_id: Optional[str] = None) -> None:
        """Emit a timeline update event."""
        self.emit_custom_event(
            "agent_timeline_update",
            AgentTimelineUpdateEvent(
                operations=list(self.operations.values()),
                current_operation_id=current_op_id,
            ).to_dict(),
        )

    def _emit_thinking_trace(
        self,
        step: Optional[TraceStep] = None,
        force: bool = False,
    ) -> None:
        """Emit a thinking trace update with windowing, summarization, and deduplication.

        Implements patterns from DeepAgents/LangGraph:
        - Windowed trace: Recent steps in full detail, older steps summarized
        - Deduplication: Skip emission if content hash unchanged within window
        - Lazy emission: Only emit when there's meaningful change

        Args:
            step: The current/latest trace step (optional)
            force: Force emission even if deduplication would skip it
        """
        current_time = time.time() * 1000  # ms

        # Compute a fingerprint that changes when step content changes.
        # This prevents "stale" trace panels where the step count stays the same
        # but the active step content is streaming in.
        changed_step = step or (self.thinking_trace[-1] if self.thinking_trace else None)
        if changed_step is not None:
            tail = changed_step.content[-512:] if changed_step.content else ""
            tail_hash = hashlib.md5(tail.encode("utf-8", errors="ignore")).hexdigest()[:8]
            fingerprint = (
                f"{len(self.thinking_trace)}|{changed_step.id}|{changed_step.timestamp}|"
                f"{changed_step.type}|{len(changed_step.content)}|{tail_hash}"
            )
        else:
            fingerprint = f"{len(self.thinking_trace)}|none"

        # =====================================================================
        # DEDUPLICATION CHECK (LangGraph pattern)
        # Skip if we just emitted and content hasn't meaningfully changed
        # =====================================================================
        if not force:
            time_since_last = current_time - self._last_trace_emission_time
            if (
                time_since_last < DEDUP_EMISSION_WINDOW_MS
                and fingerprint == self._last_emitted_trace_fingerprint
            ):
                return  # No meaningful change within dedup window

        # =====================================================================
        # WINDOWED TRACE WITH PROGRESSIVE SUMMARIZATION (DeepAgents pattern)
        # Instead of truncating content, we summarize older steps
        # =====================================================================
        windowed_trace = []
        total_steps = len(self.thinking_trace)

        if total_steps <= TRACE_WINDOW_SIZE:
            # Few enough steps - send all in full detail
            for trace_step in self.thinking_trace:
                windowed_trace.append(self._prepare_step_for_emission(trace_step, full=True))
        else:
            # Summarize older steps, keep recent steps in full detail
            summary_count = total_steps - TRACE_WINDOW_SIZE

            # Older steps: Create summaries
            for i, trace_step in enumerate(self.thinking_trace[:summary_count]):
                should_keep_full = (
                    trace_step.type == "thought"
                    or str(trace_step.metadata.get("kind", "")).lower() in {"narration", "phase", "provider_reasoning"}
                )
                windowed_trace.append(
                    self._prepare_step_for_emission(trace_step, full=should_keep_full)
                )

            # Recent steps: Full detail
            for trace_step in self.thinking_trace[summary_count:]:
                windowed_trace.append(self._prepare_step_for_emission(trace_step, full=True))

        # =====================================================================
        # APPROXIMATE TOKEN COUNT (LangChain pattern)
        # Fast estimation for observability without actual tokenization
        # =====================================================================
        total_content = "".join(
            str(s.content) if hasattr(s, "content") else str(s.get("content", ""))
            for s in windowed_trace
        )
        approx_tokens = count_tokens_approximately(total_content, include_overhead=False)

        # Build payload
        payload = AgentThinkingTraceEvent(
            total_steps=total_steps,
            thinking_trace=windowed_trace,
            latest_step=step,
            active_step_id=step.id if step else (
                self.thinking_trace[-1].id if self.thinking_trace else None
            ),
        )

        # Add token metrics to payload
        payload_dict = payload.to_dict()
        payload_dict["_metrics"] = {
            "approx_tokens": approx_tokens,
            "windowed_steps": len(windowed_trace),
            "total_steps": total_steps,
            "summarized_steps": max(0, total_steps - TRACE_WINDOW_SIZE),
        }

        # Emit the event
        self.emit_custom_event("agent_thinking_trace", payload_dict)

        # Update deduplication state
        self._last_trace_emission_time = current_time
        self._last_emitted_trace_version = total_steps
        self._last_emitted_trace_fingerprint = fingerprint

    def _prepare_step_for_emission(self, trace_step: TraceStep, full: bool = True) -> TraceStep:
        """Prepare a trace step for emission with optional summarization.

        Args:
            trace_step: The original trace step
            full: If True, include full content (up to MAX_STEP_CONTENT_FULL)
                  If False, summarize to MAX_STEP_CONTENT_SUMMARY

        Returns:
            TraceStep ready for emission (may be a modified copy)
        """
        content = trace_step.content
        max_len = MAX_STEP_CONTENT_FULL if full else MAX_STEP_CONTENT_SUMMARY

        if len(content) <= max_len:
            return trace_step

        # Content exceeds limit - need to create a summarized version
        if full:
            # For full mode, truncate at a reasonable boundary with indicator
            truncated = content[:max_len]
            # Try to truncate at a sentence boundary
            last_period = truncated.rfind('. ')
            if last_period > max_len * 0.7:  # Only if we keep >70% of content
                truncated = truncated[:last_period + 1]
            summary = truncated + f"\n\n[...{len(content) - len(truncated)} more characters]"
        else:
            # For summary mode, create a brief summary
            # Take first paragraph or first N chars
            first_para_end = content.find('\n\n')
            if first_para_end > 0 and first_para_end < max_len:
                summary = content[:first_para_end] + "..."
            else:
                summary = content[:max_len] + "..."

        return TraceStep(
            id=trace_step.id,
            type=trace_step.type,
            content=summary,
            timestamp=trace_step.timestamp,
            metadata={
                **trace_step.metadata,
                "_summarized": True,
                "_original_length": len(content),
            },
        )

    def _emit_todos(self) -> None:
        """Emit a todos update event."""
        self.emit_custom_event(
            "agent_todos_update",
            AgentTodosUpdateEvent(todos=self.todo_items).to_dict(),
        )
        logger.info(
            "agent_todos_update_emit",
            todo_count=len(self.todo_items),
        )

    def _sync_todo_operations(self) -> None:
        """Sync todo items to timeline operations."""
        # Remove old todo operations
        for tid in list(self.todo_operation_ids):
            self.operations.pop(tid, None)

        # Remove from parent children
        parent_op = self.operations.get(self.root_id)
        if parent_op is not None:
            parent_op.children = [c for c in parent_op.children if c not in self.todo_operation_ids]

        self.todo_operation_ids.clear()

        # Create new todo operations
        for idx, todo in enumerate(self.todo_items):
            op_id = f"{self.root_id}-todo-{idx + 1}"
            status = (todo.status or "pending").lower()  # type: ignore[attr-defined]
            op = TimelineOperation.create_todo(
                todo_id=op_id,
                title=todo.title,
                parent_id=self.root_id,
                status=status,
                todo_data=todo.to_dict(),
            )
            self.operations[op_id] = op
            self.todo_operation_ids.add(op_id)

            if parent_op is not None and op_id not in parent_op.children:
                parent_op.children.append(op_id)

        self._emit_timeline_update()
