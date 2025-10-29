from __future__ import annotations
import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterable, Dict, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.primary import run_primary_agent, PrimaryAgentState
from app.agents.research import get_research_graph
from app.agents.log_analysis import run_log_analysis_agent, LogSanitizer
from app.api.v1.endpoints.agent_common import (
    filter_system_text,
    get_user_id_for_dev_mode,
    serialize_analysis_results,
    augment_analysis_metadata,
    _format_log_analysis_content,
)
from app.api.v1.middleware.log_analysis_middleware import (
    log_analysis_request_middleware,
    log_analysis_rate_limiter,
    log_analysis_session_manager,
)
from app.core.transport.sse import (
    DEFAULT_SSE_HEARTBEAT_COMMENT,
    build_sse_prelude,
    format_sse_comment,
    format_sse_data,
)
from app.core.user_context import create_user_context_from_user_id, user_context_scope
from langchain_core.messages import AIMessage, HumanMessage

logger = logging.getLogger(__name__)

router = APIRouter()

# Single module-level sanitizer instance for SSE content (defense-in-depth).
# Uses secure defaults; no external dependencies added.
_SSE_SANITIZER = LogSanitizer()


class UnifiedAgentRequest(BaseModel):
    message: str
    agent_type: str | None = None
    log_content: str | None = None
    log_metadata: Optional[Dict[str, Any]] = None
    trace_id: str | None = None
    messages: list[dict] | None = None
    session_id: str | None = None
    provider: str | None = None
    model: str | None = None
    # Optional image/file attachments (data URLs) to support multimodal
    attachments: list[Dict[str, Any]] | None = None
    # Manual web search flags (from frontend pill)
    force_websearch: bool | None = None
    websearch_max_results: int | None = None
    websearch_profile: str | None = None


LOG_AGENT_ALIASES = {"log_analyst", "log_analysis"}


def _emit_followups_if_present(
    message_metadata: Dict[str, Any],
    emit,
    agent_type: Optional[str],
    request: UnifiedAgentRequest,
    stream_id: str,
    preface_metadata: Optional[Dict[str, Any]],
):
    followups = message_metadata.get("followUpQuestions")
    if not followups:
        return
    yield emit({
        "type": "data-followups",
        "data": followups,
        "agent_type": agent_type,
        "trace_id": request.trace_id,
        "stream_id": stream_id,
    })


def _emit_structured_if_present(
    message_metadata: Dict[str, Any],
    emit,
    agent_type: Optional[str],
    request: UnifiedAgentRequest,
    stream_id: str,
    preface_metadata: Optional[Dict[str, Any]],
):
    structured_payload = message_metadata.get("structured")
    if not structured_payload:
        return
    yield emit({
        "type": "assistant-structured",
        "data": structured_payload,
        "agent_type": agent_type,
        "trace_id": request.trace_id,
        "stream_id": stream_id,
    })


def _extract_latest_thought_from_trace(thinking_trace: Any) -> Optional[str]:
    try:
        if isinstance(thinking_trace, dict):
            steps = thinking_trace.get("thinking_steps")
            if isinstance(steps, list) and steps:
                last_step = steps[-1]
                if isinstance(last_step, dict):
                    thought = last_step.get("thought") or last_step.get("text")
                    if isinstance(thought, str):
                        return thought
        if isinstance(thinking_trace, str):
            return thinking_trace
    except Exception:
        return None
    return None


def _emit_thinking_trace_if_present(
    message_metadata: Dict[str, Any],
    emit,
    agent_type: Optional[str],
    request: UnifiedAgentRequest,
    stream_id: str,
    preface_metadata: Optional[Dict[str, Any]],
):
    reasoning_started = False

    def _generator():
        nonlocal reasoning_started
        thinking_trace = message_metadata.get("thinking_trace")
        if not thinking_trace:
            return
        reasoning_started = True
        yield emit({
            "type": "reasoning-start",
            "agent_type": agent_type,
            "trace_id": request.trace_id,
            "stream_id": stream_id,
        })
        latest_thought = _extract_latest_thought_from_trace(thinking_trace)
        if latest_thought:
            yield emit({
                "type": "reasoning-delta",
                "text": latest_thought,
                "agent_type": agent_type,
                "trace_id": request.trace_id,
                "stream_id": stream_id,
            })
        yield emit({
            "type": "data-thinking",
            "data": thinking_trace,
            "agent_type": agent_type,
            "trace_id": request.trace_id,
            "stream_id": stream_id,
        })

    gen = _generator()
    setattr(gen, "reasoning_started_flag", lambda: reasoning_started)
    return gen


def _emit_tool_results_if_present(
    message_metadata: Dict[str, Any],
    emit,
    agent_type: Optional[str],
    request: UnifiedAgentRequest,
    stream_id: str,
    preface_metadata: Optional[Dict[str, Any]],
):
    tool_results = message_metadata.get("toolResults")
    if not tool_results:
        return
    yield emit({
        "type": "data-tool-result",
        "data": tool_results,
        "agent_type": agent_type,
        "trace_id": request.trace_id,
        "stream_id": stream_id,
    })


def _emit_leftover_metadata_if_present(
    message_metadata: Dict[str, Any],
    emit,
    agent_type: Optional[str],
    request: UnifiedAgentRequest,
    stream_id: str,
    preface_metadata: Optional[Dict[str, Any]],
    reserved_keys: set[str],
):
    leftover = {key: value for key, value in message_metadata.items() if key not in reserved_keys}
    if preface_metadata:
        leftover.setdefault("preface", preface_metadata)
    if not leftover:
        return
    yield emit({
        "type": "message-metadata",
        "messageMetadata": leftover,
        "agent_type": agent_type,
        "trace_id": request.trace_id,
    })


async def stream_text_by_characters(
    text: str,
    stream_id: str,
    *,
    emit_start: bool = False,
    emit_end: bool = False,
    chunk_size: int = 1,
    delay: float = 0.0,
    metrics: Optional[Dict[str, int]] = None,
) -> AsyncIterable[str]:
    """Stream text content character by character with standardized SSE payloads."""
    if emit_start:
        if metrics is not None:
            metrics["events"] = metrics.get("events", 0) + 1
        yield format_sse_data({"type": "text-start", "id": stream_id})

    for i in range(0, len(text), chunk_size):
        chunk = text[i : i + chunk_size]
        if not chunk:
            continue
        if metrics is not None:
            metrics["events"] = metrics.get("events", 0) + 1
            metrics["text_chars"] = metrics.get("text_chars", 0) + len(chunk)
        yield format_sse_data({"type": "text-delta", "id": stream_id, "delta": chunk})
        if delay > 0:
            await asyncio.sleep(delay)

    if emit_end:
        if metrics is not None:
            metrics["events"] = metrics.get("events", 0) + 1
        yield format_sse_data({"type": "text-end", "id": stream_id})


async def unified_agent_stream_generator(request: UnifiedAgentRequest, user_id: Optional[str] = None) -> AsyncIterable[str]:
    stream_closed = False
    stream_metrics: Dict[str, int] = {"events": 0, "text_chars": 0, "heartbeats": 0}
    started_at = datetime.utcnow()
    from app.core.settings import get_settings

    settings = get_settings()
    heartbeat_interval = getattr(settings, "sse_heartbeat_interval", 5.0)
    heartbeat_comment = getattr(settings, "sse_heartbeat_comment", DEFAULT_SSE_HEARTBEAT_COMMENT)
    prelude_size = getattr(settings, "sse_prelude_size", 2048)

    def emit(payload: Dict[str, Any]) -> str:
        stream_metrics["events"] += 1
        return format_sse_data(payload)

    def emit_comment(comment: str = heartbeat_comment) -> str:
        stream_metrics["events"] += 1
        stream_metrics["heartbeats"] += 1
        return format_sse_comment(comment)

    try:
        prelude = build_sse_prelude(prelude_size)
        stream_metrics["events"] += 1
        stream_metrics["heartbeats"] += 1
        yield prelude if prelude else format_sse_comment(heartbeat_comment)
        yield emit({"type": "step", "data": {"type": "Router", "description": "Analyzing your request…", "status": "in_progress"}})
        message_lower = request.message.lower()
        if request.agent_type:
            agent_type = request.agent_type
        elif any(k in message_lower for k in ['analyze this log', 'parse log file', 'debug this log', 'log analysis', 'examine log entries', 'review log output', 'check log errors']):
            agent_type = "log_analyst"
        elif any(k in message_lower for k in ['research', 'find information about', 'latest news', 'compare products', 'what is new in', 'investigate', 'gather sources', 'comprehensive overview', 'detailed research']):
            agent_type = "researcher"
        else:
            agent_type = "primary"
        if agent_type in LOG_AGENT_ALIASES:
            agent_type = "log_analysis"
        agent_name = {"primary": "Primary Support", "primary_agent": "Primary Support", "log_analyst": "Log Analysis", "log_analysis": "Log Analysis", "researcher": "Research"}.get(agent_type, "Primary Support")
        yield emit({"type": "step", "data": {"type": "Router", "description": f"Routing to {agent_name}", "status": "completed"}})

        if agent_type == "log_analysis" and request.log_content:
            from app.core.settings import get_settings
            settings = get_settings()
            resolved_user_id = user_id or get_user_id_for_dev_mode(settings)
            file_metadata = request.log_metadata or {}
            file_name = str(file_metadata.get("filename") or "analysis.log")
            concurrent_slot_acquired = False
            session_id = request.session_id or request.trace_id or f"log-session-{uuid.uuid4().hex[:8]}"
            try:
                fake_request = type('Request', (), {'headers': {}})()
                middleware_metadata = await log_analysis_request_middleware(fake_request, resolved_user_id, request.log_content, file_name=file_name)
                concurrent_slot_acquired = True
            except HTTPException as exc:
                detail = exc.detail
                message = detail.get('message') if isinstance(detail, dict) else str(detail or exc)
                yield emit({"type": "error", "errorText": f"Unable to start log analysis: {message}", "agent_type": "log_analysis", "trace_id": request.trace_id})
                return
            except Exception as middleware_error:
                logger.error(f"Middleware failure for log analysis: {middleware_error}", exc_info=True)
                yield emit({"type": "error", "errorText": "Unexpected error while preparing log analysis. Please try again shortly.", "agent_type": "log_analysis", "trace_id": request.trace_id})
                return

            try:
                session_metadata = {**middleware_metadata}
                if file_metadata:
                    session_metadata["uploaded_file"] = file_metadata
                try:
                    await log_analysis_session_manager.create_session(user_id=resolved_user_id, session_id=session_id, metadata=session_metadata)
                except Exception as session_error:
                    logger.warning("Failed to persist log analysis session %s for user %s: %s", session_id, resolved_user_id, session_error)

                user_context = await create_user_context_from_user_id(resolved_user_id)
                gemini_key = await user_context.get_gemini_api_key()
                if not gemini_key:
                    yield emit({"type": "error", "errorText": "🔑 **API Key Required**: To analyze logs, please add your Google Gemini API key in Settings.", "agent_type": "log_analysis", "trace_id": request.trace_id})
                    return

                result: Optional[Dict[str, Any]] = None
                try:
                    async with user_context_scope(user_context):
                        try:
                            yield emit({'type': 'step', 'data': {'type': 'Starting Analysis', 'description': 'Initializing log analysis...', 'status': 'in_progress'}})
                            yield emit({'type': 'step', 'data': {'type': 'Parsing', 'description': 'Parsing log entries...', 'status': 'in_progress'}})
                            yield emit({'type': 'step', 'data': {'type': 'Analyzing', 'description': 'Analyzing patterns and issues...', 'status': 'in_progress'}})
                        except Exception:
                            pass
                        initial_state = {
                            "raw_log_content": request.log_content,
                            "question": request.message or None,
                            "trace_id": request.trace_id,
                            "session_id": session_id,
                            # Pass through web search flags to agent
                            "force_websearch": bool(request.force_websearch) if request.force_websearch is not None else None,
                            "websearch_max_results": request.websearch_max_results,
                            "websearch_profile": request.websearch_profile,
                        }
                        yield emit_comment(heartbeat_comment)
                        result = await run_log_analysis_agent(initial_state)
                        yield emit_comment(heartbeat_comment)
                        try:
                            yield emit({'type': 'step', 'data': {'type': 'Parsing', 'description': 'Parsing log entries...', 'status': 'completed'}})
                            yield emit({'type': 'step', 'data': {'type': 'Analyzing', 'description': 'Analyzing patterns and issues...', 'status': 'completed'}})
                            yield emit({'type': 'step', 'data': {'type': 'Synthesizing', 'description': 'Generating final summary and recommendations...', 'status': 'in_progress'}})
                        except Exception:
                            pass
                except Exception as agent_error:
                    logger.error("Log analysis agent failed: %s", agent_error, exc_info=True)
                    yield emit({"type": "error", "errorText": "Log analysis failed while processing the file. Please try again after a short break.", "agent_type": "log_analysis", "trace_id": request.trace_id})
                    return

                final_report = result.get('final_report') if isinstance(result, dict) else None
                if final_report:
                    if hasattr(final_report, 'overall_summary'):
                        summary = final_report.overall_summary
                    elif isinstance(final_report, dict):
                        summary = final_report.get('overall_summary', 'Analysis complete')
                    else:
                        summary = str(final_report)

                    analysis_results = serialize_analysis_results(final_report)
                    if isinstance(analysis_results, dict):
                        if middleware_metadata is not None:
                            analysis_results['ingestion_metadata'] = middleware_metadata
                        if session_id is not None:
                            analysis_results['session_id'] = session_id
                        issues_list = analysis_results.get('identified_issues') or analysis_results.get('issues') or []
                        analysis_results = augment_analysis_metadata(analysis_results, request.log_content, issues_list, middleware_metadata)

                    # Helper to recursively sanitize any string fields in payloads before SSE
                    def _sanitize_payload(obj: Any) -> Any:
                        try:
                            if isinstance(obj, str):
                                # Remove internal/system tags first, then sanitize for display
                                cleaned = filter_system_text(obj)
                                return _SSE_SANITIZER.sanitize_for_display(cleaned)
                            if isinstance(obj, list):
                                return [_sanitize_payload(x) for x in obj]
                            if isinstance(obj, dict):
                                return {k: _sanitize_payload(v) for k, v in obj.items()}
                            return obj
                        except Exception:
                            return obj

                    try:
                        try:
                            yield emit({'type': 'step', 'data': {'type': 'Synthesizing', 'description': 'Finalizing the response...', 'status': 'completed'}})
                        except Exception:
                            pass
                        # Prefer agent-formatted conversational response when available
                        formatted_response = None
                        try:
                            if isinstance(result, dict):
                                fr = result.get('formatted_response')
                                if isinstance(fr, str):
                                    # Strip internal tags then sanitize for display
                                    fr = filter_system_text(fr)
                                    fr = _SSE_SANITIZER.sanitize_for_display(fr)
                                formatted_response = fr if isinstance(fr, str) and fr.strip() else None
                        except Exception:
                            formatted_response = None

                        content_md = formatted_response or (summary if not isinstance(analysis_results, dict) else None)
                        if not content_md:
                            content_md = _format_log_analysis_content(analysis_results, request.message)
                        # Always sanitize outgoing assistant content and metadata for SSE
                        try:
                            content_md = _SSE_SANITIZER.sanitize_for_display(filter_system_text(content_md))
                        except Exception:
                            pass
                        try:
                            analysis_results = _sanitize_payload(analysis_results)
                        except Exception:
                            pass
                        # Stream the content character by character
                        stream_id = f"assistant-{uuid.uuid4().hex}"
                        try:
                            light_log_meta = None
                            try:
                                if isinstance(analysis_results, dict):
                                    light_log_meta = analysis_results.get("ingestion_metadata") or analysis_results.get("system_metadata")
                            except Exception:
                                light_log_meta = None
                            yield emit({
                                "type": "message-metadata",
                                "messageMetadata": {
                                    "logMetadata": light_log_meta,
                                },
                                "agent_type": "log_analysis",
                                "trace_id": request.trace_id,
                                "session_id": session_id,
                            })
                        except Exception:
                            pass
                        # If attachments are present (images), emit a timeline step for visibility
                        try:
                            if isinstance(request.attachments, list) and any(att.get('media_type','').startswith('image/') for att in request.attachments if isinstance(att, dict)):
                                yield emit({'type': 'step', 'data': {'type': 'Attachments', 'description': 'Processing attached images…', 'status': 'in_progress'}})
                        except Exception:
                            pass
                        async for chunk in stream_text_by_characters(
                            content_md,
                            stream_id,
                            emit_start=True,
                            chunk_size=64,
                            metrics=stream_metrics,
                        ):
                            yield chunk
                        async for closing in stream_text_by_characters(
                            "",
                            stream_id,
                            emit_end=True,
                            metrics=stream_metrics,
                        ):
                            yield closing
                        # Finalize the last in-progress timeline step for UI compaction
                        try:
                            yield emit({'type': 'data', 'data': {'type': 'finish-step'}, 'agent_type': 'log_analysis', 'trace_id': request.trace_id, 'session_id': session_id})
                        except Exception:
                            pass
                        yield emit({"type": "result", "data": {"analysis": analysis_results}, "agent_type": "log_analysis", "trace_id": request.trace_id, "session_id": session_id})
                    except Exception as json_error:
                        logger.error(f"JSON serialization error: {json_error}")
                        yield emit({"type": "error", "errorText": f"Log analysis serialization failed: {str(json_error)}", "agent_type": "log_analysis", "trace_id": request.trace_id, "session_id": session_id})
                else:
                    yield emit({"type": "error", "errorText": "Log analysis completed without producing a final report.", "agent_type": "log_analysis", "trace_id": request.trace_id})
                return
            finally:
                if concurrent_slot_acquired and resolved_user_id:
                    await log_analysis_rate_limiter.release_concurrent_slot(resolved_user_id)

        elif agent_type == "researcher":
            research_graph = get_research_graph()
            initial_state = {"query": request.message, "urls": [], "documents": [], "answer": None, "citations": None}
            result = await research_graph.ainvoke(initial_state)
            answer = result.get("answer", "No answer provided.")
            citations = result.get("citations", [])
            if citations:
                yield emit({
                    "type": "message-metadata",
                    "messageMetadata": {"citations": citations},
                    "agent_type": agent_type,
                    "trace_id": request.trace_id,
                })
            # Ensure a stream id exists for character streaming in this branch
            stream_id = f"assistant-{uuid.uuid4().hex}"
            async for chunk in stream_text_by_characters(
                answer,
                stream_id,
                emit_start=True,
                chunk_size=64,
                metrics=stream_metrics,
            ):
                yield chunk
            async for closing in stream_text_by_characters("", stream_id, emit_end=True, metrics=stream_metrics):
                yield closing
            yield emit({
                "type": "result",
                "data": {"answer": answer, "citations": citations},
                "agent_type": agent_type,
                "trace_id": request.trace_id,
            })
        else:
            from app.core.settings import get_settings
            settings = get_settings()
            resolved_user_id = user_id or get_user_id_for_dev_mode(settings)
            if user_id is None and resolved_user_id != "anonymous":
                logger.info("Using development user ID for testing")
            user_context = await create_user_context_from_user_id(resolved_user_id)
            gemini_key = await user_context.get_gemini_api_key()
            if not gemini_key:
                yield emit({"type": "error", "errorText": "🔑 **API Key Required**: To use the AI assistant, please add your Google Gemini API key in Settings.\n\n**How to configure:**\n1. Click the ⚙️ Settings button in the top-right corner\n2. Navigate to the 'API Keys' section\n3. Add your Google Gemini API key (starts with 'AIza')\n4. Get your free API key at: https://makersuite.google.com/app/apikey", "trace_id": request.trace_id})
                return
            async with user_context_scope(user_context):
                messages = []
                if request.messages:
                    for msg in request.messages:
                        if msg.get("type") == "user" or msg.get("role") == "user":
                            messages.append(HumanMessage(content=msg.get("content", "")))
                        elif msg.get("type") in ("assistant", "agent") or msg.get("role") == "assistant":
                            messages.append(AIMessage(content=msg.get("content", "")))
                # Multimodal: package images with the user's question when present
                image_parts = []
                try:
                    attachments = request.attachments or []
                    MAX_ATTACHMENTS = 4
                    for att in attachments[:MAX_ATTACHMENTS]:
                        if not isinstance(att, dict):
                            continue
                        mt = str(att.get('media_type') or '').lower()
                        if not mt.startswith('image/'):
                            continue
                        data_url = str(att.get('data_url') or '')
                        if not data_url.startswith('data:'):
                            continue
                        image_parts.append({"type": "image_url", "image_url": {"url": data_url}})
                except Exception:
                    image_parts = []

                if image_parts:
                    messages.append(HumanMessage(content=[{"type": "text", "text": request.message}, *image_parts]))
                else:
                    messages.append(HumanMessage(content=request.message))
                initial_state = PrimaryAgentState(
                    messages=messages,
                    session_id=request.session_id,
                    provider=request.provider,
                    model=request.model,
                    force_websearch=request.force_websearch,
                    websearch_max_results=request.websearch_max_results,
                    websearch_profile=request.websearch_profile,
                )
                stream_id = f"assistant-{uuid.uuid4().hex}"
                text_started = False
                try:
                    agent_task = asyncio.create_task(run_primary_agent(initial_state))
                    result = None
                    while True:
                        try:
                            result = await asyncio.wait_for(agent_task, heartbeat_interval)
                            break
                        except asyncio.TimeoutError:
                            yield emit_comment(heartbeat_comment)
                    if result is None:
                        raise RuntimeError("Primary agent returned no result")
                finally:
                    if 'agent_task' in locals() and not agent_task.done():
                        agent_task.cancel()
                        try:
                            await agent_task
                        except asyncio.CancelledError:
                            pass

                result_messages = list((result or {}).get("messages") or [])
                final_msg: Optional[AIMessage] = None
                for candidate in reversed(result_messages):
                    if isinstance(candidate, AIMessage):
                        final_msg = candidate
                        break

                metadata_kwargs = {}
                if final_msg and isinstance(final_msg.additional_kwargs, dict):
                    metadata_kwargs = dict(final_msg.additional_kwargs)
                message_metadata = metadata_kwargs.get("messageMetadata") or {}
                if not isinstance(message_metadata, dict):
                    message_metadata = {}
                else:
                    message_metadata = dict(message_metadata)
                preface_metadata = metadata_kwargs.get("preface")
                if preface_metadata is not None and not isinstance(preface_metadata, dict):
                    preface_metadata = None

                content_piece = ""
                if final_msg and getattr(final_msg, "content", None):
                    content_piece = final_msg.content
                    if not isinstance(content_piece, str):
                        try:
                            content_piece = json.dumps(content_piece, ensure_ascii=False)
                        except TypeError:
                            content_piece = str(content_piece)
                content_piece = filter_system_text(content_piece or "")

                if content_piece:
                    async for char_chunk in stream_text_by_characters(
                        content_piece,
                        stream_id,
                        emit_start=True,
                        emit_end=True,
                        chunk_size=48,
                        metrics=stream_metrics,
                    ):
                        yield char_chunk
                    text_started = True
                else:
                    fallback_text = (
                        "I'm sorry, I wasn't able to generate a response right now. "
                        "Please verify API connectivity and keys in Settings, then try again."
                    )
                    async for fb in stream_text_by_characters(
                        fallback_text,
                        stream_id,
                        emit_start=True,
                        emit_end=True,
                        chunk_size=48,
                        metrics=stream_metrics,
                    ):
                        yield fb
                    text_started = True

                if message_metadata:
                    for event in _emit_followups_if_present(message_metadata, emit, agent_type, request, stream_id, preface_metadata):
                        yield event

                    for event in _emit_structured_if_present(message_metadata, emit, agent_type, request, stream_id, preface_metadata):
                        yield event

                    thinking_generator = _emit_thinking_trace_if_present(
                        message_metadata,
                        emit,
                        agent_type,
                        request,
                        stream_id,
                        preface_metadata,
                    )
                    for event in thinking_generator:
                        yield event
                    thinking_flag = getattr(thinking_generator, "reasoning_started_flag", None)

                    for event in _emit_tool_results_if_present(message_metadata, emit, agent_type, request, stream_id, preface_metadata):
                        yield event

                    reserved_keys = {"followUpQuestions", "thinking_trace", "toolResults", "structured"}
                    for event in _emit_leftover_metadata_if_present(
                        message_metadata,
                        emit,
                        agent_type,
                        request,
                        stream_id,
                        preface_metadata,
                        reserved_keys,
                    ):
                        yield event

                    if callable(thinking_flag) and thinking_flag():
                        yield emit({
                            "type": "reasoning-end",
                            "agent_type": agent_type,
                            "trace_id": request.trace_id,
                            "stream_id": stream_id,
                        })

                if text_started:
                    async for closing in stream_text_by_characters("", stream_id, emit_end=True, metrics=stream_metrics):
                        yield closing

        yield emit({'type': 'finish', 'trace_id': request.trace_id, 'stream_id': locals().get('stream_id')})
        stream_closed = True
    except Exception as e:
        logger.error(f"Error in unified_agent_stream_generator: {e}", exc_info=True)
        yield emit({
            "type": "error",
            "errorText": f"An error occurred: {str(e)}",
            "trace_id": request.trace_id,
        })
    finally:
        if not stream_closed:
            yield emit({'type': 'finish', 'trace_id': request.trace_id, 'stream_id': locals().get('stream_id')})
        elapsed_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        logger.info(
            "[unified_stream] stream complete agent=%s trace_id=%s stream_id=%s events=%d text_chars=%d heartbeats=%d elapsed_ms=%d",
            request.agent_type or "auto",
            request.trace_id,
            locals().get('stream_id'),
            stream_metrics.get("events", 0),
            stream_metrics.get("text_chars", 0),
            stream_metrics.get("heartbeats", 0),
            elapsed_ms,
        )


try:
    from app.api.v1.endpoints.auth import get_current_user_id
    AUTH_AVAILABLE = True
except ImportError:  # pragma: no cover
    AUTH_AVAILABLE = False
    async def get_current_user_id() -> str:  # type: ignore
        from app.core.settings import settings
        return getattr(settings, 'development_user_id', 'dev-user-12345')


if AUTH_AVAILABLE:
    @router.post("/agent/unified/stream")
    async def unified_agent_stream(request: UnifiedAgentRequest, user_id: str = Depends(get_current_user_id)):
        if not request.message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        return StreamingResponse(
            unified_agent_stream_generator(request, user_id),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream; charset=utf-8",
                "Content-Encoding": "identity",
                "Pragma": "no-cache",
                "Vary": "Authorization, Accept-Encoding",
                "X-Accel-Buffering": "no",
                "X-Content-Type-Options": "nosniff",
            },
        )
else:
    @router.post("/agent/unified/stream")
    async def unified_agent_stream(request: UnifiedAgentRequest):
        if not request.message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        return StreamingResponse(
            unified_agent_stream_generator(request),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream; charset=utf-8",
                "Pragma": "no-cache",
                "Vary": "Authorization, Accept-Encoding",
                "X-Accel-Buffering": "no",
            },
        )
