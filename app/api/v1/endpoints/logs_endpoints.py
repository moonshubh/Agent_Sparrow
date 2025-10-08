from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncIterable, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents_v2.log_analysis_agent.agent import run_log_analysis_agent
from app.agents_v2.log_analysis_agent.simplified_schemas import SimplifiedLogAnalysisOutput
from app.api.v1.endpoints.agent_common import serialize_analysis_results
from app.api.v1.middleware.log_analysis_middleware import (
    LOG_ANALYSIS_RATE_LIMITS,
    log_analysis_rate_limiter,
    log_analysis_request_middleware,
    log_analysis_session_manager,
)
from app.core.transport.sse import format_sse_data
from app.core.user_context import create_user_context_from_user_id, user_context_scope

logger = logging.getLogger(__name__)

router = APIRouter()


class LogAnalysisV2Response(SimplifiedLogAnalysisOutput):
    trace_id: str | None = None


class LogAnalysisRequest(BaseModel):
    log_text: str | None = None
    content: str | None = None
    question: str | None = None
    trace_id: str | None = None
    settings_content: str | None = None
    settings_path: str | None = None


try:
    from app.api.v1.endpoints.auth import get_current_user_id
except ImportError:  # pragma: no cover
    async def get_current_user_id() -> str:  # type: ignore
        from app.core.settings import settings
        return getattr(settings, 'development_user_id', 'dev-user-12345')


@router.post("/agent/logs", response_model=LogAnalysisV2Response)
async def analyze_logs(request: LogAnalysisRequest, user_id: str = Depends(get_current_user_id)):
    log_body = request.content or request.log_text
    if not log_body:
        raise HTTPException(status_code=400, detail="Log text cannot be empty")

    session_id = request.trace_id or f"log-session-{uuid.uuid4().hex[:8]}"
    concurrent_slot_acquired = False
    try:
        try:
            fake_request = type('Request', (), {'headers': {}})()
            await log_analysis_request_middleware(fake_request, user_id, log_body, file_name="analysis.log")
            concurrent_slot_acquired = True
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Middleware error in analyze_logs: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to prepare log analysis request")

        user_context = await create_user_context_from_user_id(user_id)
        gemini_key = await user_context.get_gemini_api_key()
        if not gemini_key:
            raise HTTPException(status_code=400, detail="API Key Required: Please add your Google Gemini API key in Settings")

        async with user_context_scope(user_context):
            initial_state = {"raw_log_content": log_body, "question": request.question, "trace_id": request.trace_id, "session_id": session_id}
            result = await run_log_analysis_agent(initial_state)

        final_report = result.get('final_report') if isinstance(result, dict) else None
        if not final_report:
            raise HTTPException(status_code=500, detail="Log analysis agent did not return a final report.")

        response_dict = serialize_analysis_results(final_report)
        response_dict["trace_id"] = result.get('trace_id') or request.trace_id
        try:
            return LogAnalysisV2Response(**response_dict)
        except Exception as validation_error:
            logger.warning(f"LogAnalysisV2Response validation error: {validation_error}")
            fallback = {
                "overall_summary": response_dict.get("overall_summary", "Analysis completed"),
                "health_status": response_dict.get("health_status", "Unknown"),
                "priority_concerns": response_dict.get("priority_concerns", []),
                "system_metadata": response_dict.get("system_metadata", {}),
                "environmental_context": response_dict.get("environmental_context", {}),
                "identified_issues": response_dict.get("identified_issues", []),
                "issue_summary_by_severity": response_dict.get("issue_summary_by_severity", {}),
                "correlation_analysis": response_dict.get("correlation_analysis", {}),
                "dependency_analysis": response_dict.get("dependency_analysis", {}),
                "predictive_insights": response_dict.get("predictive_insights", []),
                "ml_pattern_discovery": response_dict.get("ml_pattern_discovery", {}),
                "proposed_solutions": response_dict.get("proposed_solutions", []),
                "supplemental_research": response_dict.get("supplemental_research"),
                "analysis_metrics": response_dict.get("analysis_metrics", {}),
                "validation_summary": response_dict.get("validation_summary", {}),
                "immediate_actions": response_dict.get("immediate_actions", []),
                "preventive_measures": response_dict.get("preventive_measures", []),
                "monitoring_recommendations": response_dict.get("monitoring_recommendations", []),
                "automated_remediation_available": response_dict.get("automated_remediation_available", False),
                "trace_id": result.get('trace_id') or request.trace_id,
            }
            return LogAnalysisV2Response(**fallback)
    except Exception as e:
        logger.error(f"Error in Log Analysis Agent endpoint: {e}", exc_info=True)
        raise
    finally:
        if concurrent_slot_acquired:
            await log_analysis_rate_limiter.release_concurrent_slot(user_id)


async def log_analysis_stream_generator(
    log_content: str,
    question: str | None = None,
    trace_id: str | None = None,
    user_id: str | None = None,
) -> AsyncIterable[str]:
    concurrent_slot_acquired = False
    try:
        if user_id:
            fake_request = type('Request', (), {'headers': {}})()
            try:
                await log_analysis_request_middleware(fake_request, user_id, log_content, file_name="analysis.log")
                concurrent_slot_acquired = True
            except HTTPException as rate_limit_error:
                detail = rate_limit_error.detail
                message = detail.get('message', str(detail)) if isinstance(detail, dict) else str(detail)
                yield format_sse_data({'type': 'error', 'data': {'message': f'Rate limit exceeded: {message}', 'trace_id': trace_id}})
                return

        if user_id:
            user_context = await create_user_context_from_user_id(user_id)
            gemini_key = await user_context.get_gemini_api_key()
            if not gemini_key:
                yield format_sse_data({'type': 'error', 'data': {'message': 'API Key Required: Please add your Google Gemini API key in Settings.', 'trace_id': trace_id}})
                return
        else:
            from app.core.settings import get_settings
            settings = get_settings()
            user_id = user_id or settings.development_user_id
            user_context = await create_user_context_from_user_id(user_id)

        yield format_sse_data({'type': 'step', 'data': {'type': 'Starting Analysis', 'description': 'Initializing log analysis...', 'status': 'in-progress'}})
        async with user_context_scope(user_context):
            initial_state = {"raw_log_content": log_content, "question": question, "trace_id": trace_id}
            yield format_sse_data({'type': 'step', 'data': {'type': 'Parsing', 'description': 'Parsing log entries...', 'status': 'in-progress'}})
            result = await run_log_analysis_agent(initial_state)
            yield format_sse_data({'type': 'step', 'data': {'type': 'Analyzing', 'description': 'Analyzing patterns and issues...', 'status': 'complete'}})

            final_report = result.get('final_report')
            returned_trace_id = result.get('trace_id')
            if final_report:
                analysis_results = serialize_analysis_results(final_report)
                yield format_sse_data({'type': 'result', 'data': {'analysis': analysis_results, 'trace_id': returned_trace_id or trace_id}})
            else:
                yield format_sse_data({'type': 'error', 'data': {'message': 'Log analysis did not produce a report', 'trace_id': trace_id}})

        yield format_sse_data({'type': 'done'})
    except Exception as e:
        logger.error(f"Error in log_analysis_stream_generator: {e}", exc_info=True)
        yield format_sse_data({'type': 'error', 'data': {'message': f'Error during log analysis: {str(e)}', 'trace_id': trace_id}})
    finally:
        if concurrent_slot_acquired and user_id:
            await log_analysis_rate_limiter.release_concurrent_slot(user_id)


@router.post("/agent/logs/stream")
async def log_analysis_stream(request: LogAnalysisRequest, user_id: str = Depends(get_current_user_id)):
    log_body = request.content or request.log_text
    if not log_body:
        raise HTTPException(status_code=400, detail="Log text cannot be empty")
    return StreamingResponse(
        log_analysis_stream_generator(log_content=log_body, question=request.question, trace_id=request.trace_id, user_id=user_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


class LogAnalysisSessionResponse(BaseModel):
    session_id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    metadata: dict
    insights: list
    conversation: list


@router.get("/agent/logs/sessions")
async def list_log_analysis_sessions(user_id: str = Depends(get_current_user_id)):
    sessions = await log_analysis_session_manager.list_sessions(user_id)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/agent/logs/sessions/{session_id}")
async def get_log_analysis_session(session_id: str, user_id: str = Depends(get_current_user_id)):
    session = await log_analysis_session_manager.get_session(user_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/agent/logs/sessions/{session_id}/insights")
async def add_session_insight(session_id: str, insight: dict, user_id: str = Depends(get_current_user_id)):
    success = await log_analysis_session_manager.add_insight(user_id, session_id, insight)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success", "message": "Insight added"}


@router.get("/agent/logs/rate-limits")
async def get_log_analysis_rate_limits(user_id: str = Depends(get_current_user_id)):
    usage_snapshot = await log_analysis_rate_limiter.get_user_usage(user_id)
    user_requests = usage_snapshot.get("requests", [])
    concurrent = usage_snapshot.get("concurrent", 0)

    now = datetime.utcnow()
    requests_last_minute = len([r for r in user_requests if now - r < timedelta(minutes=1)])
    requests_last_hour = len([r for r in user_requests if now - r < timedelta(hours=1)])
    requests_today = len(user_requests)

    return {
        "limits": LOG_ANALYSIS_RATE_LIMITS,
        "usage": {
            "requests_last_minute": requests_last_minute,
            "requests_last_hour": requests_last_hour,
            "requests_today": requests_today,
            "concurrent_analyses": concurrent,
        },
        "remaining": {
            "per_minute": max(0, LOG_ANALYSIS_RATE_LIMITS["requests_per_minute"] - requests_last_minute),
            "per_hour": max(0, LOG_ANALYSIS_RATE_LIMITS["requests_per_hour"] - requests_last_hour),
            "per_day": max(0, LOG_ANALYSIS_RATE_LIMITS["requests_per_day"] - requests_today),
            "concurrent": max(0, LOG_ANALYSIS_RATE_LIMITS["max_concurrent_analyses"] - concurrent),
        },
    }
