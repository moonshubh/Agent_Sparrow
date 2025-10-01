from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Annotated, AsyncIterable, Dict, List, Pattern, Any, Optional
from datetime import datetime

from app.agents_v2.primary_agent.agent import run_primary_agent
from app.agents_v2.primary_agent.schemas import PrimaryAgentState # Import PrimaryAgentState
from app.agents_v2.log_analysis_agent.simplified_schemas import SimplifiedLogAnalysisOutput, SimplifiedAgentState
from langchain_core.messages import HumanMessage, AIMessage
import json
import re
from app.api.v1.middleware.log_analysis_middleware import (
    log_analysis_request_middleware,
    log_analysis_rate_limiter,
    log_analysis_session_manager
)

from app.agents_v2.log_analysis_agent.agent import run_log_analysis_agent
from app.agents_v2.research_agent.research_agent import get_research_graph, ResearchState
from app.agents_v2.orchestration.graph import app as agent_graph
from app.agents_v2.orchestration.state import GraphState
# Conditional import for authentication
try:
    from app.api.v1.endpoints.auth import get_current_user_id
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    # Fallback function when auth is not available
    async def get_current_user_id() -> str:
        from app.core.settings import settings
        return getattr(settings, 'development_user_id', 'dev-user-12345')
from app.core.user_context import user_context_scope, create_user_context_from_user_id
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Precompiled regex patterns for performance
SELF_CRITIQUE_RE = re.compile(r'<self_critique>.*?</self_critique>', flags=re.DOTALL)

SYSTEM_PATTERNS: list[Pattern[str]] = [
    re.compile(r"<system>.*?</system>", flags=re.DOTALL | re.IGNORECASE),
    re.compile(r"<internal>.*?</internal>", flags=re.DOTALL | re.IGNORECASE),
    re.compile(r"<self_critique>.*?</self_critique>", flags=re.DOTALL | re.IGNORECASE),
    re.compile(r".*loyalty relationship.*", flags=re.IGNORECASE),
]


def _filter_system_text(text: str | None) -> str:
    """Strip internal/system markers before they reach the UI stream."""
    if not text:
        return ""

    filtered = text
    # Handle legacy critique pattern as well as the consolidated regexes above.
    filtered = SELF_CRITIQUE_RE.sub("", filtered)

    for pattern in SYSTEM_PATTERNS:
        filtered = pattern.sub("", filtered)

    return filtered

# --- Formatting helpers ---

def _format_log_analysis_content(analysis: dict | Any, question: str | None) -> str:
    """
    Build a single, cohesive markdown answer for log analysis that:
    1) Acknowledges the user's question (empathy)
    2) Summarizes the problem clearly
    3) Provides step-by-step solutions
    """
    try:
        if not isinstance(analysis, dict):
            # Best-effort conversion for pydantic models or objects
            if hasattr(analysis, 'model_dump'):
                analysis = analysis.model_dump()  # type: ignore
            elif hasattr(analysis, 'dict'):
                analysis = analysis.dict()  # type: ignore
            else:
                analysis = {"overall_summary": str(analysis)}

        overall_summary = analysis.get("overall_summary") or analysis.get("summary") or "Log analysis complete."
        issues = analysis.get("identified_issues") or analysis.get("issues") or []
        solutions = analysis.get("proposed_solutions") or analysis.get("solutions") or analysis.get("actions") or []

        parts: list[str] = []

        # 1) Empathetic opening
        if question:
            parts.append(
                f"Thanks for sharing the log file. I reviewed it in the context of your question: \"{question}\". Here's what I found and how to fix it."
            )
        else:
            parts.append(
                "Thanks for sharing the log file. I’ve completed the analysis — here’s what’s going on and how to fix it."
            )

        # 2) Problem analysis
        parts.append("## Problem analysis\n" + str(overall_summary))

        if isinstance(issues, list) and len(issues) > 0:
            findings: list[str] = []
            for issue in issues[:3]:
                title = issue.get("title") if isinstance(issue, dict) else None
                details = issue.get("details") if isinstance(issue, dict) else None
                severity = issue.get("severity") if isinstance(issue, dict) else None
                bullet = "- "
                if severity:
                    bullet += f"[{severity}] "
                if title:
                    bullet += f"{title}"
                if details:
                    bullet += f": {details}"
                findings.append(bullet)
            if findings:
                parts.append("### Critical findings\n" + "\n".join(findings))

        # 3) Step-by-step solutions
        step_sections: list[str] = []
        if isinstance(solutions, list) and len(solutions) > 0:
            for idx, sol in enumerate(solutions[:3], start=1):
                if not isinstance(sol, dict):
                    continue
                title = sol.get("title") or f"Solution {idx}"
                steps = sol.get("steps") or []
                expected = sol.get("expected_outcome") or sol.get("outcome")
                section_lines: list[str] = [f"### Solution {idx}: {title}"]
                if isinstance(steps, list) and steps:
                    section_lines.append("**Steps to resolve:**")
                    for j, step in enumerate(steps, start=1):
                        section_lines.append(f"{j}. {step}")
                step_sections.append("\n".join(section_lines))

        if step_sections:
            parts.append("## Step-by-step solution\n" + "\n\n".join(step_sections))

        return "\n\n".join(parts)
    except Exception:
        # Fallback: keep current short content on unexpected errors
        summary = analysis.get("overall_summary") if isinstance(analysis, dict) else None
        return f"Log analysis complete! {summary or ''}".strip()

def _augment_analysis_metadata(
    analysis_results: dict,
    raw_log: str | None,
    issues: list | None,
    ingestion_metadata: dict | None,
) -> dict:
    """Best-effort enrichment of analysis metadata for the overview card.

    - database_size: parsed from log (e.g., "Store.db 485.0 MB" or "Database size: 2.4 GB")
    - account_count: rough unique email count (not exposed as list to avoid PII)
    - accounts_with_errors: unique accounts referenced in issue details
    - error_count / warning_count / total_entries: derived when available
    - time_range: preserved from ingestion_metadata
    """
    try:
        if not isinstance(analysis_results, dict):
            return analysis_results

        # Ensure dicts for metadata containers
        if not isinstance(analysis_results.get("system_metadata"), dict):
            analysis_results["system_metadata"] = {}
        if not isinstance(analysis_results.get("ingestion_metadata"), dict):
            analysis_results["ingestion_metadata"] = {}

        system_meta = analysis_results["system_metadata"]
        ingest_meta = analysis_results["ingestion_metadata"]

        # Preserve time_range if middleware provided it
        if ingestion_metadata and isinstance(ingestion_metadata, dict):
            if ingestion_metadata.get("time_range") and not ingest_meta.get("time_range"):
                ingest_meta["time_range"] = ingestion_metadata.get("time_range")
            if ingestion_metadata.get("line_count") and not ingest_meta.get("line_count"):
                ingest_meta["line_count"] = ingestion_metadata.get("line_count")

        # Derive counts from raw log
        if isinstance(raw_log, str) and raw_log:
            lines = raw_log.splitlines()
            # Only populate when missing
            if ingest_meta.get("line_count") is None:
                ingest_meta["line_count"] = len(lines)

            if system_meta.get("error_count") is None:
                system_meta["error_count"] = sum(1 for ln in lines if "|ERROR|" in ln or " ERROR " in ln)
            if system_meta.get("warning_count") is None:
                system_meta["warning_count"] = sum(1 for ln in lines if "|WARN|" in ln or " WARNING " in ln)

            # Database size
            if system_meta.get("database_size") is None:
                import re as _re
                m = _re.search(r"(?:Store\.db\s+|Database size:\s*)([\d,.]+\s*[KMGTP]B)", raw_log, _re.IGNORECASE)
                if m:
                    system_meta["database_size"] = m.group(1).replace(",", "")

            # Account count (unique emails) — number only (no PII exposure)
            if system_meta.get("account_count") is None:
                import re as _re
                emails = set(_re.findall(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}", raw_log))
                system_meta["account_count"] = len(emails) if emails else None

        # Accounts with errors from issues
        if system_meta.get("accounts_with_errors") is None and isinstance(issues, list) and issues:
            import re as _re
            accs: set[str] = set()
            for it in issues:
                if not isinstance(it, dict):
                    continue
                text = " ".join(str(it.get(k, "")) for k in ("details", "description", "title"))
                for m in _re.findall(r"Account[:\s]+([^\s|]+@[^\s|]+)", text):
                    accs.add(m)
            if accs:
                system_meta["accounts_with_errors"] = len(accs)

        return analysis_results
    except Exception:
        return analysis_results

# --- Helper Functions ---

def _get_user_id_for_dev_mode(settings) -> str:
    """
    Get user ID for development mode.
    
    Returns development_user_id if SKIP_AUTH is true and development_user_id is set,
    otherwise returns 'anonymous'.
    
    Args:
        settings: Application settings object
        
    Returns:
        str: User ID to use
    """
    if settings.skip_auth and hasattr(settings, 'development_user_id') and settings.development_user_id:
        return settings.development_user_id
    return "anonymous"

def safe_json_serializer(obj):
    """
    Custom JSON serializer that handles complex objects like datetime, Pydantic models, etc.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, 'model_dump'):
        # Handle Pydantic v2 models
        return obj.model_dump()
    elif hasattr(obj, 'dict'):
        # Handle Pydantic v1 models
        return obj.dict()
    elif isinstance(obj, (list, tuple)):
        return [safe_json_serializer(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: safe_json_serializer(value) for key, value in obj.items()}
    else:
        # For other objects, try to convert to string as fallback
        try:
            # Check if it's already JSON serializable
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

def serialize_analysis_results(final_report):
    """
    Safely serialize analysis results for JSON streaming response.
    """
    try:
        if hasattr(final_report, 'model_dump'):
            # Pydantic v2 model
            serialized = final_report.model_dump()
        elif hasattr(final_report, 'dict'):
            # Pydantic v1 model
            serialized = final_report.dict()
        elif isinstance(final_report, dict):
            # Already a dictionary
            serialized = final_report
        else:
            # Fallback for other object types
            serialized = {"summary": str(final_report)}
        
        # Recursively serialize any complex nested objects
        return safe_json_serializer(serialized)
    except Exception as e:
        logger.error(f"Error serializing analysis results: {e}")
        # Return minimal fallback
        return {
            "overall_summary": "Analysis completed but serialization failed",
            "error": str(e),
            "system_metadata": {},
            "identified_issues": [],
            "proposed_solutions": []
        }

# --- Pydantic Models for Log Analysis Agent ---

class LogAnalysisV2Response(SimplifiedLogAnalysisOutput):
    trace_id: str | None = None
class Issue(BaseModel):
    id: str
    description: str
    severity: str # Consider using Literal["low", "medium", "high", "critical"]
    recommendation: str | None = None
    line_numbers: tuple[int, int] | None = None
    error_type: str | None = None

class LogAnalysisRequest(BaseModel):
    """Accepts raw log content from the frontend.
    For backward-compatibility we allow both the legacy `log_text` key and the newer
    `content` key used by the v2 UI. Exactly one of them must be provided.
    """
    log_text: str | None = None
    content: str | None = None  # Preferred new field name
    question: str | None = None  # Optional question for focused analysis
    trace_id: str | None = None
    # Optional Mailbird settings (Windows): provide either content or a path
    settings_content: str | None = None
    settings_path: str | None = None




# --- Pydantic Models for Research Agent ---
class ResearchItem(BaseModel):
    id: str
    url: str
    title: str
    snippet: str | None = None
    source_name: str | None = None # e.g., "Web Search", "Internal KB"
    score: float | None = None # Relevance score

class ResearchRequest(BaseModel):
    query: str
    top_k: int | None = None
    trace_id: str | None = None

class ResearchResponse(BaseModel):
    results: List[ResearchItem]
    trace_id: str | None = None


class ChatRequest(BaseModel):
    message: str
    messages: list[dict] | None = None  # Full conversation history
    session_id: str | None = None  # Session identifier for context
    provider: str | None = None  # "google" or "openai"
    model: str | None = None     # model id like "gemini-2.5-flash" or "gpt5-mini"
    # trace_id: str | None = None # Optional, if you plan to propagate trace IDs

import uuid


async def primary_agent_stream_generator(
    query: str,
    user_id: str,
    message_history: list[dict] | None = None,
    session_id: str | None = None,
    provider: str | None = None,
    model: str | None = None
) -> AsyncIterable[str]:
    """Wraps the primary agent's streaming output with user-specific API configuration."""
    try:
        # Create user context
        user_context = await create_user_context_from_user_id(user_id)
        
        # Determine provider/model, default to google if not provided
        try:
            from app.providers.registry import default_provider, default_model_for_provider
            req_provider = (provider or default_provider()).lower()
            req_model = (model or default_model_for_provider(req_provider)).lower()
        except Exception:
            req_provider = (provider or "google").lower()
            req_model = (model or "gemini-2.5-flash").lower()
        logger.info(f"[chat_stream] request provider={provider}, model={model} -> resolved provider={req_provider}, model={req_model}")

        # Check required API key for selected provider
        if req_provider == "google":
            gemini_key = await user_context.get_gemini_api_key()
            if not gemini_key:
                error_payload = json.dumps({
                    "type": "error",
                    "errorText": "API Key Required: Please add your Google Gemini API key in Settings."
                }, ensure_ascii=False)
                yield f"data: {error_payload}\n\n"
                return
        elif req_provider == "openai":
            openai_key = None
            if hasattr(user_context, "get_openai_api_key"):
                try:
                    openai_key = await user_context.get_openai_api_key()
                except Exception:
                    openai_key = None
            import os
            openai_key = openai_key or os.getenv("OPENAI_API_KEY")
            if not openai_key:
                error_payload = json.dumps({
                    "type": "error",
                    "errorText": "OpenAI API key missing. Add it in Settings or set OPENAI_API_KEY."
                }, ensure_ascii=False)
                yield f"data: {error_payload}\n\n"
                return
        else:
            error_payload = json.dumps({
                "type": "error",
                "errorText": f"Unsupported provider: {req_provider}"
            }, ensure_ascii=False)
            yield f"data: {error_payload}\n\n"
            return
        
        # Use user-specific context
        async with user_context_scope(user_context):
            # Build message history
            messages = []
            
            # Add conversation history if provided
            if message_history:
                for msg in message_history:
                    if msg.get("type") == "user" or msg.get("role") == "user":
                        messages.append(HumanMessage(content=msg.get("content", "")))
                    elif msg.get("type") == "assistant" or msg.get("role") == "assistant":
                        messages.append(AIMessage(content=msg.get("content", "")))
            
            # Add current query
            messages.append(HumanMessage(content=query))
            
            initial_state = PrimaryAgentState(
                messages=messages,
                session_id=session_id,
                # pass provider/model through to the agent
                provider=req_provider,
                model=req_model
            )
            logger.info(f"[chat_stream] initial_state provider={initial_state.provider}, model={initial_state.model}")
            
            stream_id = f"assistant-{uuid.uuid4().hex}"
            text_started = False

            async for chunk in run_primary_agent(initial_state):
                payloads: list[dict] = []

                if hasattr(chunk, 'content') and chunk.content is not None:
                    content_piece = chunk.content
                    if not isinstance(content_piece, str):
                        try:
                            content_piece = json.dumps(content_piece, ensure_ascii=False)
                        except TypeError:
                            content_piece = str(content_piece)

                    content_piece = _filter_system_text(content_piece)

                    if content_piece:
                        if not text_started:
                            payloads.append({
                                "type": "text-start",
                                "id": stream_id,
                            })
                            text_started = True

                        payloads.append({
                            "type": "text-delta",
                            "id": stream_id,
                            "delta": content_piece,
                        })

                metadata = getattr(chunk, "additional_kwargs", {}).get("metadata") if hasattr(chunk, "additional_kwargs") else None
                if metadata:
                    # Follow-up questions
                    followups = metadata.get("followUpQuestions")
                    if followups:
                        payloads.append({
                            "type": "data-followups",
                            "data": followups,
                            "transient": True,
                        })

                    # Thinking trace
                    thinking_trace = metadata.get("thinking_trace")
                    if thinking_trace:
                        payloads.append({
                            "type": "data-thinking",
                            "data": thinking_trace,
                        })

                    tool_results = metadata.get("toolResults")
                    if tool_results:
                        payloads.append({
                            "type": "data-tool-result",
                            "data": tool_results,
                        })

                    # Any remaining metadata keys that haven't been emitted yet
                    leftover = {
                        key: value for key, value in metadata.items()
                        if key not in {"followUpQuestions", "thinking_trace", "toolResults"}
                    }
                    if leftover:
                        payloads.append({
                            "type": "message-metadata",
                            "messageMetadata": leftover,
                        })

                for payload in payloads:
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            if text_started:
                finish_payloads = [
                    {"type": "text-end", "id": stream_id},
                    {"type": "finish"},
                ]
                for payload in finish_payloads:
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    except Exception as e:
        # Use logger for consistency if available, otherwise print
        # logger.error(f"Error in primary_agent_stream_generator calling run_primary_agent: {e}", exc_info=True)
        logger.error(f"Error in primary_agent_stream_generator calling run_primary_agent: {e}", exc_info=True)
        error_payload = json.dumps({"type": "error", "errorText": f"An error occurred in the agent: {str(e)}"}, ensure_ascii=False)
        yield f"data: {error_payload}\n\n"

# Legacy v1 endpoint - DEPRECATED but maintained for backward compatibility
@router.post("/agent/chat/stream")
async def chat_stream_v1_legacy(
    request: ChatRequest
):
    """
    DEPRECATED: Legacy streaming chat endpoint without authentication.
    
    This endpoint is maintained for backward compatibility but is deprecated.
    New applications should use /v2/agent/chat/stream with proper authentication.
    
    Deprecation Notice:
    - This endpoint will be removed in v3.0
    - Please migrate to the authenticated v2 endpoint
    - See migration guide: /docs/api-migration
    """
    if not request.message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    # In development mode with SKIP_AUTH=true, use the development user ID
    from app.core.settings import get_settings
    settings = get_settings()
    
    # Determine user ID based on environment
    user_id = _get_user_id_for_dev_mode(settings)
    if user_id != "anonymous":
        logger.info("Using development user ID for testing")
    
    # Use appropriate user configuration
    return StreamingResponse(
        primary_agent_stream_generator(
            request.message, 
            user_id=user_id,
            message_history=request.messages,
            session_id=request.session_id,
            provider=request.provider,
            model=request.model
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-API-Version": "1.0",
            "X-Deprecation-Warning": "This endpoint is deprecated. Use /v2/agent/chat/stream"
        }
    )

# v2 endpoint with authentication - RECOMMENDED
@router.post("/v2/agent/chat/stream")
async def chat_stream_v2_authenticated(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Authenticated streaming chat endpoint with the Primary Support Agent.
    
    This endpoint requires Supabase authentication and provides:
    - User-specific API key configuration
    - Personalized agent behavior
    - Enhanced security and rate limiting
    - Access to premium features
    """
    if not request.message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    return StreamingResponse(
        primary_agent_stream_generator(
            request.message, 
            user_id,
            message_history=request.messages,
            session_id=request.session_id,
            provider=request.provider,
            model=request.model
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-API-Version": "2.0"
        }
    )

# --- Log Analysis Agent Endpoint with Session Management ---
@router.post("/agent/logs", response_model=LogAnalysisV2Response)
async def analyze_logs(
    request: LogAnalysisRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Endpoint for analyzing logs with the Log Analysis Agent (with session management)."""
    # Determine which field contains the log content (new `content` or legacy `log_text`)
    log_body = request.content or request.log_text
    if not log_body:
        raise HTTPException(status_code=400, detail="Log text cannot be empty")

    # Generate session ID if not provided
    session_id = request.trace_id or f"log-session-{uuid.uuid4().hex[:8]}"

    # Track whether we've acquired a concurrent slot
    concurrent_slot_acquired = False

    try:
        # Apply middleware for validation and rate limiting
        from fastapi import Request as FastAPIRequest
        fake_request = type('Request', (), {'headers': {}})()  # Create minimal request object
        middleware_result = await log_analysis_request_middleware(
            fake_request,
            user_id,
            log_body,
            file_name="analysis.log"
        )

        # Mark that we've acquired a concurrent slot (middleware increments the counter)
        concurrent_slot_acquired = True

        # Create session for this analysis
        session_data = await log_analysis_session_manager.create_session(
            user_id=user_id,
            session_id=session_id,
            metadata=middleware_result
        )

        # Create user context
        user_context = await create_user_context_from_user_id(user_id)

        # Check if user has required API keys
        gemini_key = await user_context.get_gemini_api_key()
        if not gemini_key:
            raise HTTPException(
                status_code=400,
                detail="API Key Required: To use log analysis, please add your Google Gemini API key in Settings. Steps: (1) Click Settings ⚙️ in the top-right (2) Go to 'API Keys' section (3) Add your Gemini API key (starts with 'AIza') (4) Get a free key at: https://makersuite.google.com/app/apikey"
            )

        # Use user-specific context
        async with user_context_scope(user_context):
            initial_state = {
                "raw_log_content": log_body,
                "question": None,
                "trace_id": None,
                "settings_content": request.settings_content,
                "settings_path": request.settings_path,
            }

            # Add question if provided (for simplified agent)
            if hasattr(request, 'question') and request.question:
                initial_state['question'] = request.question

            # Pass trace_id as a keyword argument if the agent function supports it for logging/tracing
            # The run_log_analysis_agent in agent.py is designed to pick up trace_id from the state dict if present,
            # or generate one. For explicit passing for the endpoint, let's ensure it's part of the initial call.
            # However, the agent.py run_log_analysis_agent expects trace_id in the state dictionary.
            if request.trace_id:
                initial_state['trace_id'] = request.trace_id

            raw_agent_output = await run_log_analysis_agent(initial_state)

        final_report: SimplifiedLogAnalysisOutput = raw_agent_output.get('final_report')
        returned_trace_id = raw_agent_output.get('trace_id')

        if not final_report:
            raise HTTPException(status_code=500, detail="Log analysis agent did not return a final report.")

        # Return the structured report directly along with the trace_id
        # Use safe serialization for consistent handling
        response_dict = serialize_analysis_results(final_report)
        response_dict["trace_id"] = returned_trace_id or request.trace_id

        try:
            return LogAnalysisV2Response(**response_dict)
        except Exception as validation_error:
            logger.warning(f"LogAnalysisV2Response validation error: {validation_error}")
            # Create a minimal response that will validate
            fallback_response = {
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
                "trace_id": returned_trace_id or request.trace_id
            }
            return LogAnalysisV2Response(**fallback_response)
    except Exception as e:
        # Log the exception details for debugging
        logger.error(f"Error in Log Analysis Agent endpoint: {e}", exc_info=True)
        # Consider how to propagate trace_id in error responses if needed
        raise HTTPException(status_code=500, detail=f"Error processing log analysis request: {str(e)}")
    finally:
        # Always release the concurrent slot if we acquired one
        if concurrent_slot_acquired:
            await log_analysis_rate_limiter.release_concurrent_slot(user_id)

# --- Research Agent Endpoint ---
@router.post("/agent/research", response_model=ResearchResponse)
async def research_query(
    request: ResearchRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Endpoint for performing research with the Research Agent."""
    if not request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        # Create user context
        user_context = await create_user_context_from_user_id(user_id)
        
        # Check if user has API key for research (Tavily is needed for research)
        tavily_key = await user_context.get_tavily_api_key()
        if not tavily_key:
            raise HTTPException(
                status_code=400, 
                detail="Please configure your Tavily API key in Settings to use web research functionality."
            )
        
        # Use user-specific context
        async with user_context_scope(user_context):
            research_graph = get_research_graph()
            initial_graph_state: ResearchState = {
                "query": request.query,
                "urls": [],
                "documents": [],
                "answer": None,
                "citations": None,
                # top_k is not directly used by the graph state but influences search_node's max_results implicitly
                # The Tavily search tool used by search_node has a max_results parameter.
                # If request.top_k is intended to control this, it needs to be passed to search_node or the tool config.
                # For now, the graph uses a default of 5 in search_node.
            }

            # LangGraph's invoke is synchronous, ainvoke for async
            # Assuming the graph nodes (search, scrape, synthesize) are async, we should use ainvoke.
            # However, the current research_agent.py uses synchronous .invoke() in its CLI test.
            # For an async FastAPI endpoint, we should ideally use graph.ainvoke if graph nodes support it.
            # If nodes are synchronous, graph.invoke() would block. Let's assume ainvoke is preferred.
            # For simplicity and matching the agent's own test harness, let's use invoke for now,
            # but acknowledge this might need to change to ainvoke and run in a threadpool for a truly async endpoint.
            # For now, we will call it directly. If it blocks, it needs to be run in a threadpool.
            # result_state = await asyncio.to_thread(research_graph.invoke, initial_graph_state)
            # The research_graph nodes (search_node, scrape_node, synthesize_node) are synchronous.
            # To avoid blocking the event loop, we should run the graph.invoke in a thread pool.
            # However, for now, let's make a direct call and note this as a point for future improvement.

            # Use async graph invocation (synthesize_node is async)
            result_state = await research_graph.ainvoke(initial_graph_state)

        answer = result_state.get("answer", "No answer provided.")
        citations = result_state.get("citations", [])

        transformed_results: List[ResearchItem] = []
        if citations:
            for citation in citations:
                # The citation format from research_agent is {'id': int, 'url': str}
                # The ResearchItem for the frontend expects more fields.
                transformed_results.append(
                    ResearchItem(
                        id=str(citation.get('id', '')),
                        url=citation.get('url', '#'),
                        title=f"Source [{citation.get('id', '')}]: {citation.get('url', 'N/A')}", # Placeholder title
                        snippet=answer, # Using the main answer as a snippet for all cited sources for now
                        source_name="Web Research",
                        score=None # Score is not provided by the current research agent
                    )
                )
        
        # If there's an answer but no citations, we can create a single result item for the answer itself.
        if not transformed_results and answer != "No answer provided." and answer != "I'm sorry, I couldn't find relevant information to answer your question.":
            transformed_results.append(
                 ResearchItem(
                    id="answer_summary",
                    url="#", # No specific URL for the summary itself
                    title="Synthesized Answer",
                    snippet=answer,
                    source_name="Synthesized by Agent",
                    score=None
                )
            )

        response_data = {
            "results": [item.model_dump() for item in transformed_results],
            "trace_id": request.trace_id # Propagate trace_id from request for now
        }
        return ResearchResponse(**response_data)
    except Exception as e:
        logger.error(f"Error in Research Agent endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing research request: {str(e)}")

# --- Unified Agent Endpoint with LangGraph Orchestration ---
class UnifiedAgentRequest(BaseModel):
    message: str
    agent_type: str | None = None  # Optional: "primary", "log_analyst", "log_analysis", "researcher", or None for auto-routing
    log_content: str | None = None  # For log analysis
    log_metadata: Optional[Dict[str, Any]] = None  # Optional metadata about uploaded log file
    trace_id: str | None = None
    messages: list[dict] | None = None  # Full conversation history
    session_id: str | None = None  # Session identifier for context

LOG_AGENT_ALIASES = {"log_analyst", "log_analysis"}


async def unified_agent_stream_generator(
    request: UnifiedAgentRequest,
    user_id: Optional[str] = None,
) -> AsyncIterable[str]:
    """Unified agent endpoint with intelligent routing and fallback."""
    try:
        # Send routing notification
        routing_payload = json.dumps({
            "role": "system", 
            "content": f"🤖 Analyzing your request...",
            "agent_type": "router",
            "trace_id": request.trace_id
        }, ensure_ascii=False)
        yield f"data: {routing_payload}\n\n"
        
        # Simple intelligent routing based on message content
        message_lower = request.message.lower()
        
        # Determine agent type
        if request.agent_type:
            agent_type = request.agent_type
        elif any(keyword in message_lower for keyword in ['analyze this log', 'parse log file', 'debug this log', 'log analysis', 'examine log entries', 'review log output', 'check log errors']):
            agent_type = "log_analyst"
        elif any(keyword in message_lower for keyword in ['research', 'find information about', 'latest news', 'compare products', 'what is new in', 'investigate', 'gather sources', 'comprehensive overview', 'detailed research']):
            agent_type = "researcher"  
        else:
            agent_type = "primary"
        
        if agent_type in LOG_AGENT_ALIASES:
            agent_type = "log_analysis"

        # Send agent selection notification
        agent_name = {
            "primary": "Primary Support",
            "primary_agent": "Primary Support",
            "log_analyst": "Log Analysis",
            "log_analysis": "Log Analysis",
            "researcher": "Research"
        }.get(agent_type, "Primary Support")
        
        agent_payload = json.dumps({
            "role": "system", 
            "content": f"🎯 Routing to {agent_name} Agent",
            "agent_type": agent_type,
            "trace_id": request.trace_id
        }, ensure_ascii=False)
        yield f"data: {agent_payload}\n\n"
        
        # Route to appropriate agent endpoint
        if agent_type in LOG_AGENT_ALIASES and request.log_content:
            from app.agents_v2.log_analysis_agent.agent import run_log_analysis_agent
            from app.core.settings import get_settings

            settings = get_settings()
            resolved_user_id = user_id or _get_user_id_for_dev_mode(settings)
            file_metadata = request.log_metadata or {}
            file_name = str(file_metadata.get("filename") or "analysis.log")
            concurrent_slot_acquired = False
            session_id = request.session_id or request.trace_id or f"log-session-{uuid.uuid4().hex[:8]}"

            try:
                fake_request = type('Request', (), {'headers': {}})()
                middleware_metadata = await log_analysis_request_middleware(
                    fake_request,
                    resolved_user_id,
                    request.log_content,
                    file_name=file_name
                )
                concurrent_slot_acquired = True
            except HTTPException as exc:
                detail = exc.detail
                message = detail.get('message') if isinstance(detail, dict) else str(detail or exc)
                error_payload = json.dumps({
                    "role": "error",
                    "content": f"Unable to start log analysis: {message}",
                    "agent_type": "log_analysis",
                    "trace_id": request.trace_id
                }, ensure_ascii=False)
                yield f"data: {error_payload}\n\n"
                return
            except Exception as middleware_error:
                logger.error(f"Middleware failure for log analysis: {middleware_error}", exc_info=True)
                error_payload = json.dumps({
                    "role": "error",
                    "content": "Unexpected error while preparing log analysis. Please try again shortly.",
                    "agent_type": "log_analysis",
                    "trace_id": request.trace_id
                }, ensure_ascii=False)
                yield f"data: {error_payload}\n\n"
                return

            try:
                session_metadata = {**middleware_metadata}
                if file_metadata:
                    session_metadata["uploaded_file"] = file_metadata

                try:
                    await log_analysis_session_manager.create_session(
                        user_id=resolved_user_id,
                        session_id=session_id,
                        metadata=session_metadata
                    )
                except Exception as session_error:
                    logger.warning(
                        "Failed to persist log analysis session %s for user %s: %s",
                        session_id,
                        resolved_user_id,
                        session_error,
                    )

                user_context = await create_user_context_from_user_id(resolved_user_id)
                gemini_key = await user_context.get_gemini_api_key()
                if not gemini_key:
                    error_payload = json.dumps({
                        "role": "error",
                        "content": "🔑 **API Key Required**: To analyze logs, please add your Google Gemini API key in Settings.",
                        "agent_type": "log_analysis",
                        "trace_id": request.trace_id
                    }, ensure_ascii=False)
                    yield f"data: {error_payload}\n\n"
                    return

                result: Optional[Dict[str, Any]] = None
                try:
                    async with user_context_scope(user_context):
                        initial_state = {
                            "raw_log_content": request.log_content,
                            "question": request.message or None,
                            "trace_id": request.trace_id,
                            "session_id": session_id
                        }
                        result = await run_log_analysis_agent(initial_state)
                except Exception as agent_error:
                    logger.error("Log analysis agent failed: %s", agent_error, exc_info=True)
                    error_payload = json.dumps({
                        "role": "error",
                        "content": "Log analysis failed while processing the file. Please try again after a short break.",
                        "agent_type": "log_analysis",
                        "trace_id": request.trace_id
                    }, ensure_ascii=False)
                    yield f"data: {error_payload}\n\n"
                    return

                final_report = result.get('final_report') if isinstance(result, dict) else None

                if final_report:
                    if hasattr(final_report, 'overall_summary'):
                        summary = final_report.overall_summary
                    elif isinstance(final_report, dict):
                        summary = final_report.get('overall_summary', 'Analysis complete')
                    else:
                        summary = str(final_report)

                    # Build cohesive markdown content instead of a fragment
                    analysis_results = serialize_analysis_results(final_report)
                    if isinstance(analysis_results, dict):
                        if middleware_metadata is not None:
                            analysis_results['ingestion_metadata'] = middleware_metadata
                        if session_id is not None:
                            analysis_results['session_id'] = session_id
                        # Enrich overview metadata for the UI card
                        issues_list = analysis_results.get('identified_issues') or analysis_results.get('issues') or []
                        analysis_results = _augment_analysis_metadata(
                            analysis_results,
                            request.log_content,
                            issues_list,
                            middleware_metadata,
                        )

                    logger.debug(
                        "Serialized analysis results keys: %s",
                        list(analysis_results.keys()) if isinstance(analysis_results, dict) else 'not a dict'
                    )

                    try:
                        content_md = _format_log_analysis_content(analysis_results, request.message)
                        json_payload = json.dumps({
                            "role": "assistant",
                            "content": content_md,
                            "agent_type": "log_analysis",
                            "trace_id": request.trace_id,
                            "analysis_results": analysis_results,
                            "session_id": session_id
                        }, ensure_ascii=False)
                        yield f"data: {json_payload}\n\n"
                    except Exception as json_error:
                        logger.error(f"JSON serialization error: {json_error}")
                        fallback_payload = json.dumps({
                            "role": "assistant",
                            "content": f"Log analysis complete! {summary}",
                            "agent_type": "log_analysis",
                            "trace_id": request.trace_id,
                            "analysis_results": {
                                "overall_summary": summary,
                                "error": f"Serialization failed: {str(json_error)}",
                                "system_metadata": {},
                                "identified_issues": [],
                                "proposed_solutions": []
                            },
                            "session_id": session_id
                        }, ensure_ascii=False)
                        yield f"data: {fallback_payload}\n\n"
                else:
                    error_payload = json.dumps({
                        "role": "error",
                        "content": "Log analysis completed without producing a final report.",
                        "agent_type": "log_analysis",
                        "trace_id": request.trace_id
                    }, ensure_ascii=False)
                    yield f"data: {error_payload}\n\n"

                return
            finally:
                if concurrent_slot_acquired and resolved_user_id:
                    await log_analysis_rate_limiter.release_concurrent_slot(resolved_user_id)
        elif agent_type == "researcher":
            # Handle research queries
            from app.agents_v2.research_agent.research_agent import get_research_graph
            
            research_graph = get_research_graph()
            initial_state = {
                "query": request.message,
                "urls": [],
                "documents": [],
                "answer": None,
                "citations": None,
            }
            
            # Use async graph invocation (synthesize_node is async)
            result = await research_graph.ainvoke(initial_state)
            
            answer = result.get("answer", "No answer provided.")
            citations = result.get("citations", [])
            
            json_payload = json.dumps({
                "role": "assistant", 
                "content": answer,
                "agent_type": agent_type,
                "trace_id": request.trace_id,
                "citations": citations
            }, ensure_ascii=False)
            yield f"data: {json_payload}\n\n"
            
        else:
            # Handle primary agent queries with user context
            from app.agents_v2.primary_agent.agent import run_primary_agent
            from app.agents_v2.primary_agent.schemas import PrimaryAgentState
            from app.core.settings import get_settings
            
            settings = get_settings()
            
            # Determine user ID based on environment
            user_id = _get_user_id_for_dev_mode(settings)
            if user_id != "anonymous":
                logger.info("Using development user ID for testing")
            
            # Create user context
            user_context = await create_user_context_from_user_id(user_id)
            
            # Check if user has required API keys
            gemini_key = await user_context.get_gemini_api_key()
            if not gemini_key:
                error_payload = json.dumps({
                    "role": "error", 
                    "content": "🔑 **API Key Required**: To use the AI assistant, please add your Google Gemini API key in Settings.\n\n**How to configure:**\n1. Click the ⚙️ Settings button in the top-right corner\n2. Navigate to the 'API Keys' section\n3. Add your Google Gemini API key (starts with 'AIza')\n4. Get your free API key at: https://makersuite.google.com/app/apikey",
                    "trace_id": request.trace_id
                }, ensure_ascii=False)
                yield f"data: {error_payload}\n\n"
                return
            
            # Use user-specific context
            async with user_context_scope(user_context):
                # Build message history
                messages = []
                
                # Add conversation history if provided
                if request.messages:
                    for msg in request.messages:
                        if msg.get("type") == "user" or msg.get("role") == "user":
                            messages.append(HumanMessage(content=msg.get("content", "")))
                        elif msg.get("type") == "assistant" or msg.get("role") == "assistant" or msg.get("type") == "agent":
                            messages.append(AIMessage(content=msg.get("content", "")))
                
                # Add current query
                messages.append(HumanMessage(content=request.message))
                
                initial_state = PrimaryAgentState(
                    messages=messages,
                    session_id=request.session_id,
                    provider=request.provider,
                    model=request.model
                )
                
                # Note: Routing message already sent earlier (lines 521-527)
                # Stream each chunk after cleaning
                async for chunk in run_primary_agent(initial_state):
                    json_payload = ""
                    
                    if hasattr(chunk, 'content') and chunk.content is not None:
                        # Clean self-critique blocks from each chunk using precompiled regex
                        cleaned_content = SELF_CRITIQUE_RE.sub('', chunk.content)
                        
                        if cleaned_content.strip():  # Only send non-empty content
                            role = getattr(chunk, 'role', 'assistant') or 'assistant'
                            json_payload = json.dumps({
                                "role": role,
                                "content": cleaned_content,
                                "agent_type": agent_type,
                                "trace_id": request.trace_id
                            }, ensure_ascii=False)
                    elif hasattr(chunk, 'additional_kwargs') and chunk.additional_kwargs.get('metadata'):
                        # Handle metadata events (including follow-up questions)
                        metadata = chunk.additional_kwargs['metadata']
                        json_payload = json.dumps({
                            "role": "metadata",
                            "metadata": metadata,
                            "agent_type": agent_type,
                            "trace_id": request.trace_id
                        }, ensure_ascii=False)
                    
                    if json_payload:
                        yield f"data: {json_payload}\n\n"
                
        # Send completion signal
        yield f"data: {json.dumps({'role': 'system', 'content': '[DONE]'})}\n\n"
        
    except Exception as e:
        logger.error(f"Error in unified_agent_stream_generator: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        error_payload = json.dumps({
            "role": "error", 
            "content": f"An error occurred: {str(e)}",
            "trace_id": request.trace_id
        }, ensure_ascii=False)
        yield f"data: {error_payload}\n\n"

if AUTH_AVAILABLE:
    @router.post("/agent/unified/stream")
    async def unified_agent_stream(
        request: UnifiedAgentRequest,
        user_id: str = Depends(get_current_user_id),
    ):
        """Unified streaming endpoint that routes to appropriate agents using LangGraph."""
        if not request.message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        return StreamingResponse(
            unified_agent_stream_generator(request, user_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
else:
    @router.post("/agent/unified/stream")
    async def unified_agent_stream(request: UnifiedAgentRequest):
        """Unified streaming endpoint that routes to appropriate agents using LangGraph."""
        if not request.message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        return StreamingResponse(
            unified_agent_stream_generator(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )

# --- Log Analysis Agent Streaming Endpoint ---
async def log_analysis_stream_generator(
    log_content: str,
    question: str | None = None,
    trace_id: str | None = None,
    user_id: str | None = None
) -> AsyncIterable[str]:
    """Streaming log analysis that sends progress updates and final results."""
    concurrent_slot_acquired = False

    try:
        # Apply rate limiting and validation first if user_id is provided
        if user_id:
            # Apply middleware for validation and rate limiting
            from fastapi import Request as FastAPIRequest
            fake_request = type('Request', (), {'headers': {}})()  # Create minimal request object
            try:
                await log_analysis_request_middleware(
                    fake_request,
                    user_id,
                    log_content,
                    file_name="analysis.log"
                )
                concurrent_slot_acquired = True
            except HTTPException as rate_limit_error:
                # Convert HTTPException detail to proper format
                detail = rate_limit_error.detail
                if isinstance(detail, dict):
                    message = detail.get('message', str(detail))
                else:
                    message = str(detail)
                error_payload = json.dumps({
                    'type': 'error',
                    'data': {
                        'message': f'Rate limit exceeded: {message}',
                        'trace_id': trace_id
                    }
                })
                yield f"data: {error_payload}\n\n"
                return

        # Continue with original logic
        # Create user context if user_id is provided
        if user_id:
            user_context = await create_user_context_from_user_id(user_id)

            # Check if user has required API keys
            gemini_key = await user_context.get_gemini_api_key()
            if not gemini_key:
                error_payload = json.dumps({
                    'type': 'error',
                    'data': {
                        'message': 'API Key Required: Please add your Google Gemini API key in Settings.',
                        'trace_id': trace_id
                    }
                })
                yield f"data: {error_payload}\n\n"
                return
        else:
            # Use default settings for anonymous users
            from app.core.settings import get_settings
            settings = get_settings()
            user_id = _get_user_id_for_dev_mode(settings)
            user_context = await create_user_context_from_user_id(user_id)

        # Send initial status
        yield f"data: {json.dumps({'type': 'step', 'data': {'type': 'Starting Analysis', 'description': 'Initializing log analysis...', 'status': 'in-progress'}})}\n\n"

        # Use user-specific context
        async with user_context_scope(user_context):
            initial_state = {
                "raw_log_content": log_content,
                "question": question,
                "trace_id": trace_id
            }

            # Send parsing status
            yield f"data: {json.dumps({'type': 'step', 'data': {'type': 'Parsing', 'description': 'Parsing log entries...', 'status': 'in-progress'}})}\n\n"

            # Run the log analysis agent
            result = await run_log_analysis_agent(initial_state)

            # Send analysis status
            yield f"data: {json.dumps({'type': 'step', 'data': {'type': 'Analyzing', 'description': 'Analyzing patterns and issues...', 'status': 'complete'}})}\n\n"

            final_report = result.get('final_report')
            returned_trace_id = result.get('trace_id')

            if final_report:
                # Serialize the analysis results
                analysis_results = serialize_analysis_results(final_report)

                # Send final result
                final_payload = {
                    'type': 'result',
                    'data': {
                        'analysis': analysis_results,
                        'trace_id': returned_trace_id or trace_id
                    }
                }
                yield f"data: {json.dumps(final_payload)}\n\n"
            else:
                # Send error if no report
                error_payload = {
                    'type': 'error',
                    'data': {
                        'message': 'Log analysis did not produce a report',
                        'trace_id': trace_id
                    }
                }
                yield f"data: {json.dumps(error_payload)}\n\n"

        # Completion sentinel
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        logger.error(f"Error in log_analysis_stream_generator: {e}", exc_info=True)
        err_payload = {
            'type': 'error',
            'data': {
                'message': f'Error during log analysis: {str(e)}',
                'trace_id': trace_id
            }
        }
        yield f"data: {json.dumps(err_payload)}\n\n"
    finally:
        # Always release the concurrent slot if we acquired one
        if concurrent_slot_acquired and user_id:
            await log_analysis_rate_limiter.release_concurrent_slot(user_id)

@router.post("/agent/logs/stream")
async def log_analysis_stream(
    request: LogAnalysisRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Streaming log analysis endpoint for real-time feedback."""
    # Determine which field contains the log content
    log_body = request.content or request.log_text
    if not log_body:
        raise HTTPException(status_code=400, detail="Log text cannot be empty")

    return StreamingResponse(
        log_analysis_stream_generator(
            log_content=log_body,
            question=request.question,
            trace_id=request.trace_id,
            user_id=user_id
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

# --- Research Agent Streaming Endpoint ---
async def research_agent_stream_generator(query: str, trace_id: str | None = None) -> AsyncIterable[str]:
    """Streaming research agent that sends steps and final results."""
    try:
        research_graph = get_research_graph()
        
        # Send initial status
        yield f"data: {json.dumps({'type': 'step', 'data': {'type': 'Starting Research', 'description': 'Initializing research query...', 'status': 'in-progress'}})}\n\n"
        
        initial_state: ResearchState = {
            "query": query,
            "urls": [],
            "documents": [],
            "answer": None,
            "citations": None,
        }
        
        # Execute research via async graph invocation (synthesize_node is async)
        result = await research_graph.ainvoke(initial_state)

        # Stream a progress update after synthesize
        yield f"data: {json.dumps({'type': 'step', 'data': {'type': 'Synthesize', 'description': 'Synthesizing answer from sources...', 'status': 'complete'}})}\n\n"

        # Emit final result
        final_payload = {
            'type': 'result',
            'data': {
                'answer': result.get('answer', 'No answer provided.'),
                'citations': result.get('citations', []),
                'trace_id': trace_id
            }
        }
        yield f"data: {json.dumps(final_payload)}\n\n"

        # Completion sentinel
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        logger.error(f"Error in research_agent_stream_generator: {e}", exc_info=True)
        err_payload = {
            'type': 'error',
            'data': {
                'message': f'Error running research: {str(e)}',
                'trace_id': trace_id
            }
        }
        yield f"data: {json.dumps(err_payload)}\n\n"
        
        # Send research completion step
        yield f"data: {json.dumps({'type': 'step', 'data': {'type': 'Research Complete', 'description': 'Research analysis finished', 'status': 'completed'}})}\n\n"
        
        # Send final answer
        answer = result.get("answer", "No answer provided.")
        citations = result.get("citations", [])
        
        final_message = {
            "id": "research_result",
            "type": "agent",
            "content": answer,
            "timestamp": "now",
            "agentType": "research",
            "citations": citations,
            "feedback": None,
            "trace_id": trace_id
        }
        
        yield f"data: {json.dumps({'type': 'message', 'data': final_message})}\n\n"
        
    except Exception as e:
        logger.error(f"Error in research_agent_stream_generator: {e}", exc_info=True)
        error_step = {
            "type": "Error", 
            "description": f"Research failed: {str(e)}", 
            "status": "error"
        }
        yield f"data: {json.dumps({'type': 'step', 'data': error_step})}\n\n"

@router.post("/agent/research/stream")
async def research_agent_stream(request: ResearchRequest):
    """Streaming research endpoint that matches frontend expectations."""
    if not request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    return StreamingResponse(
        research_agent_stream_generator(request.query, request.trace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# --- Log Analysis Session Management Endpoints ---

class LogAnalysisSessionResponse(BaseModel):
    """Response model for log analysis sessions."""
    session_id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    metadata: dict
    insights: list
    conversation: list

@router.get("/agent/logs/sessions")
async def list_log_analysis_sessions(
    user_id: str = Depends(get_current_user_id)
):
    """List all log analysis sessions for the current user."""
    sessions = await log_analysis_session_manager.list_sessions(user_id)
    return {"sessions": sessions, "count": len(sessions)}

@router.get("/agent/logs/sessions/{session_id}")
async def get_log_analysis_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Retrieve a specific log analysis session."""
    session = await log_analysis_session_manager.get_session(user_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

@router.post("/agent/logs/sessions/{session_id}/insights")
async def add_session_insight(
    session_id: str,
    insight: dict,
    user_id: str = Depends(get_current_user_id)
):
    """Add an insight to a log analysis session."""
    success = await log_analysis_session_manager.add_insight(user_id, session_id, insight)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success", "message": "Insight added"}

@router.get("/agent/logs/rate-limits")
async def get_log_analysis_rate_limits(
    user_id: str = Depends(get_current_user_id)
):
    """Get current rate limit status for log analysis."""
    from app.api.v1.middleware.log_analysis_middleware import LOG_ANALYSIS_RATE_LIMITS

    # Get user's current usage
    user_requests = log_analysis_rate_limiter._user_requests.get(user_id, [])
    concurrent = log_analysis_rate_limiter._concurrent_analyses.get(user_id, 0)

    now = datetime.utcnow()
    from datetime import timedelta

    # Count requests in different time windows
    requests_last_minute = len([r for r in user_requests if now - r < timedelta(minutes=1)])
    requests_last_hour = len([r for r in user_requests if now - r < timedelta(hours=1)])
    requests_today = len(user_requests)

    return {
        "limits": LOG_ANALYSIS_RATE_LIMITS,
        "usage": {
            "requests_last_minute": requests_last_minute,
            "requests_last_hour": requests_last_hour,
            "requests_today": requests_today,
            "concurrent_analyses": concurrent
        },
        "remaining": {
            "per_minute": max(0, LOG_ANALYSIS_RATE_LIMITS["requests_per_minute"] - requests_last_minute),
            "per_hour": max(0, LOG_ANALYSIS_RATE_LIMITS["requests_per_hour"] - requests_last_hour),
            "per_day": max(0, LOG_ANALYSIS_RATE_LIMITS["requests_per_day"] - requests_today),
            "concurrent": max(0, LOG_ANALYSIS_RATE_LIMITS["max_concurrent_analyses"] - concurrent)
        }
    }
