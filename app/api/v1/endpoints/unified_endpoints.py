from __future__ import annotations
import logging
import uuid
from typing import Any, AsyncIterable, Dict, Optional

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
from app.core.transport.sse import format_sse_data
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
    # Manual web search flags (from frontend pill)
    force_websearch: bool | None = None
    websearch_max_results: int | None = None
    websearch_profile: str | None = None


LOG_AGENT_ALIASES = {"log_analyst", "log_analysis"}


async def unified_agent_stream_generator(request: UnifiedAgentRequest, user_id: Optional[str] = None) -> AsyncIterable[str]:
    try:
        yield format_sse_data({"role": "system", "content": f"🤖 Analyzing your request...", "agent_type": "router", "trace_id": request.trace_id})
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
        yield format_sse_data({"role": "system", "content": f"🎯 Routing to {agent_name} Agent", "agent_type": agent_type, "trace_id": request.trace_id})

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
                yield format_sse_data({"role": "error", "content": f"Unable to start log analysis: {message}", "agent_type": "log_analysis", "trace_id": request.trace_id})
                return
            except Exception as middleware_error:
                logger.error(f"Middleware failure for log analysis: {middleware_error}", exc_info=True)
                yield format_sse_data({"role": "error", "content": "Unexpected error while preparing log analysis. Please try again shortly.", "agent_type": "log_analysis", "trace_id": request.trace_id})
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
                    yield format_sse_data({"role": "error", "content": "🔑 **API Key Required**: To analyze logs, please add your Google Gemini API key in Settings.", "agent_type": "log_analysis", "trace_id": request.trace_id})
                    return

                result: Optional[Dict[str, Any]] = None
                try:
                    async with user_context_scope(user_context):
                        try:
                            yield format_sse_data({'type': 'step', 'data': {'type': 'Starting Analysis', 'description': 'Initializing log analysis...', 'status': 'in-progress'}})
                            yield format_sse_data({'type': 'step', 'data': {'type': 'Parsing', 'description': 'Parsing log entries...', 'status': 'in-progress'}})
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
                        result = await run_log_analysis_agent(initial_state)
                        try:
                            yield format_sse_data({'type': 'step', 'data': {'type': 'Analyzing', 'description': 'Analyzing patterns and issues...', 'status': 'complete'}})
                            yield format_sse_data({'type': 'step', 'data': {'type': 'Synthesizing', 'description': 'Generating final summary and recommendations...', 'status': 'in-progress'}})
                        except Exception:
                            pass
                except Exception as agent_error:
                    logger.error("Log analysis agent failed: %s", agent_error, exc_info=True)
                    yield format_sse_data({"role": "error", "content": "Log analysis failed while processing the file. Please try again after a short break.", "agent_type": "log_analysis", "trace_id": request.trace_id})
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
                            yield format_sse_data({'type': 'step', 'data': {'type': 'Synthesizing', 'description': 'Finalizing the response...', 'status': 'complete'}})
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
                        yield format_sse_data({"role": "assistant", "content": content_md, "agent_type": "log_analysis", "trace_id": request.trace_id, "analysis_results": analysis_results, "session_id": session_id})
                    except Exception as json_error:
                        logger.error(f"JSON serialization error: {json_error}")
                        yield format_sse_data({"role": "assistant", "content": f"Log analysis complete! {summary}", "agent_type": "log_analysis", "trace_id": request.trace_id, "analysis_results": {"overall_summary": summary, "error": f"Serialization failed: {str(json_error)}", "system_metadata": {}, "identified_issues": [], "proposed_solutions": []}, "session_id": session_id})
                else:
                    yield format_sse_data({"role": "error", "content": "Log analysis completed without producing a final report.", "agent_type": "log_analysis", "trace_id": request.trace_id})
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
            yield format_sse_data({"role": "assistant", "content": answer, "agent_type": agent_type, "trace_id": request.trace_id, "citations": citations})
        else:
            from app.core.settings import get_settings
            settings = get_settings()
            user_id = get_user_id_for_dev_mode(settings)
            if user_id != "anonymous":
                logger.info("Using development user ID for testing")
            user_context = await create_user_context_from_user_id(user_id)
            gemini_key = await user_context.get_gemini_api_key()
            if not gemini_key:
                yield format_sse_data({"role": "error", "content": "🔑 **API Key Required**: To use the AI assistant, please add your Google Gemini API key in Settings.\n\n**How to configure:**\n1. Click the ⚙️ Settings button in the top-right corner\n2. Navigate to the 'API Keys' section\n3. Add your Google Gemini API key (starts with 'AIza')\n4. Get your free API key at: https://makersuite.google.com/app/apikey", "trace_id": request.trace_id})
                return
            async with user_context_scope(user_context):
                messages = []
                if request.messages:
                    for msg in request.messages:
                        if msg.get("type") == "user" or msg.get("role") == "user":
                            messages.append(HumanMessage(content=msg.get("content", "")))
                        elif msg.get("type") in ("assistant", "agent") or msg.get("role") == "assistant":
                            messages.append(AIMessage(content=msg.get("content", "")))
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
                async for chunk in run_primary_agent(initial_state):
                    if hasattr(chunk, 'content') and chunk.content is not None:
                        cleaned_content = filter_system_text(chunk.content)
                        if cleaned_content.strip():
                            role = getattr(chunk, 'role', 'assistant') or 'assistant'
                            yield format_sse_data({"role": role, "content": cleaned_content, "agent_type": agent_type, "trace_id": request.trace_id})
                    elif hasattr(chunk, 'additional_kwargs') and chunk.additional_kwargs.get('metadata'):
                        metadata = chunk.additional_kwargs['metadata']
                        yield format_sse_data({"role": "metadata", "metadata": metadata, "agent_type": agent_type, "trace_id": request.trace_id})

        yield format_sse_data({'role': 'system', 'content': '[DONE]'})
    except Exception as e:
        logger.error(f"Error in unified_agent_stream_generator: {e}", exc_info=True)
        yield format_sse_data({"role": "error", "content": f"An error occurred: {str(e)}", "trace_id": request.trace_id})


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
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
else:
    @router.post("/agent/unified/stream")
    async def unified_agent_stream(request: UnifiedAgentRequest):
        if not request.message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        return StreamingResponse(
            unified_agent_stream_generator(request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
