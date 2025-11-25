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
from .normalizers import extract_grounding_results, extract_snippet_texts

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.config import RunnableConfig
    from app.agents.orchestration.orchestration.state import GraphState
    from app.agents.helpers.gemma_helper import GemmaHelper


# Timeout for Gemma helper calls
HELPER_TIMEOUT_SECONDS = 8.0


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

            # Try fallback invoke with error handling
            try:
                self.final_output = await self.agent.ainvoke(
                    self._agent_inputs(),
                    config=self.config,
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
                            "content": "Fallback invoke completed successfully",
                            "metadata": {"fallback": True},
                        },
                    },
                )

            except Exception as fallback_error:
                # Emit error event if fallback also fails
                logger.error(f"Fallback invoke also failed: {fallback_error}")
                self.emitter.emit_custom_event(
                    "agent_thinking_trace",
                    {
                        "totalSteps": 2,
                        "latestStep": {
                            "id": f"fallback-error-{int(time.time() * 1000)}",
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "type": "result",
                            "content": f"Fallback invoke failed: {type(fallback_error).__name__}",
                            "metadata": {
                                "error": str(fallback_error),
                                "fallback": True,
                                "failed": True,
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

    async def _on_tool_end(self, event: Dict[str, Any]) -> None:
        """Handle tool end event."""
        tool_data = event.get("data", {})
        output = tool_data.get("output")
        tool_call_id = str(tool_data.get("tool_call_id", "unknown"))
        tool_name = self._extract_tool_name(event.get("name"), tool_call_id)
        event["name"] = tool_name

        # Handle special tools
        if tool_name == "grounding_search":
            output = await self._rerank_grounding_results(output)

        if tool_name == "write_todos":
            await self._handle_write_todos(output)

        # Create summary for tool evidence
        summary = self._summarize_structured_content(output)

        self.emitter.end_tool(tool_call_id, tool_name, output, summary)

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

        if run_id and run_id in self.emitter.operations:
            output = data.get("output")
            content = ""
            if output:
                content = self._stringify_message_content(
                    getattr(output, "content", output)
                )

            self.emitter.end_thought(run_id, content)

        # Track final output
        final_output = data.get("output")
        if final_output:
            self.final_output = {"output": final_output}

    async def _on_model_stream(self, event: Dict[str, Any]) -> None:
        """Handle chat model streaming event."""
        run_id = event.get("run_id")
        if not run_id:
            return

        stream_data = event.get("data", {})
        chunk = stream_data.get("chunk") or stream_data.get("output")
        chunk_text = self._stringify_message_content(
            getattr(chunk, "content", chunk)
        )

        if chunk_text:
            self.emitter.stream_thought_chunk(run_id, chunk_text)

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
        """Convert message content to string."""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, (int, float, bool)):
            return str(content)
        if isinstance(content, BaseMessage):
            return self._stringify_message_content(content.content)
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str):
                return text
            import json
            return json.dumps(content, default=str)
        if isinstance(content, list):
            return " ".join(self._stringify_message_content(part) for part in content)
        return str(content)

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

    def _summarize_structured_content(self, content: Any) -> Optional[str]:
        """Create a summary of structured tool output."""
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

        summary_lines = ["Here are the most relevant matches:"]
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
            line = f"{idx}. **{title}**"
            if snippet_text:
                line += f" - {snippet_text}"
            if isinstance(url, str) and url.strip():
                line += f" ({url.strip()})"
            summary_lines.append(line)

        return "\n".join(summary_lines)

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
