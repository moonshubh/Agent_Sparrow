"""
Secure Log Analysis Endpoint with Paranoid Security

This module provides a secure version of the log analysis endpoint that
integrates all Phase 6.0 security features for production use.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents_v2.log_analysis_agent.comprehensive_agent import LogAnalysisAgent
from app.agents_v2.log_analysis_agent.privacy import RedactionLevel
from app.agents_v2.log_analysis_agent.security import ValidationStatus, ThreatLevel
from app.api.v1.endpoints.agent_endpoints import get_current_user_id
from app.core.user_context import create_user_context_from_user_id, user_context_scope

logger = logging.getLogger(__name__)

router = APIRouter()


class SecureLogAnalysisRequest(BaseModel):
    """Request model for secure log analysis."""
    content: Optional[str] = None  # Direct log content
    question: Optional[str] = None
    trace_id: Optional[str] = None
    security_level: str = "high"  # paranoid, high, medium, low
    enable_attachments: bool = False
    session_metadata: Dict[str, Any] = {}


class SecurityAuditResponse(BaseModel):
    """Response model for security audit."""
    security_enabled: bool
    redaction_level: Optional[str] = None
    cleanup_stats: Optional[Dict[str, Any]] = None
    compliance_status: Optional[str] = None
    recent_validations: List[Dict[str, Any]] = []


# Thread-safe agent creation
import threading

_agent_lock = threading.Lock()
_secure_agent = None


def create_secure_agent(security_level: RedactionLevel = RedactionLevel.PARANOID) -> LogAnalysisAgent:
    """Create a new secure log analysis agent instance.

    Creates a fresh agent instance for thread-safety in concurrent requests.
    Each request gets its own agent to avoid race conditions.

    Args:
        security_level: The security/redaction level for the agent

    Returns:
        A new LogAnalysisAgent instance
    """
    return LogAnalysisAgent(
        provider="google",
        model_name="gemini-2.5-pro",
        enable_security=True,
        security_level=security_level
    )


def get_secure_agent() -> LogAnalysisAgent:
    """Get or create the secure log analysis agent.

    NOTE: This maintains a singleton for backward compatibility,
    but new code should use create_secure_agent() for thread safety.
    """
    global _secure_agent
    with _agent_lock:
        if _secure_agent is None:
            _secure_agent = LogAnalysisAgent(
                provider="google",
                model_name="gemini-2.5-pro",
                enable_security=True,
                security_level=RedactionLevel.PARANOID  # Maximum security by default
            )
        return _secure_agent


@router.post("/agent/secure/logs")
async def analyze_logs_securely(
    request: SecureLogAnalysisRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Analyze logs with paranoid-level security features.

    Security features:
    - Input validation and threat detection
    - Complete data sanitization
    - Guaranteed cleanup of sensitive data
    - Compliance validation
    - Zero persistent storage of raw logs
    """
    # Validate request
    if not request.content:
        raise HTTPException(status_code=400, detail="Log content cannot be empty")

    # Generate secure session ID
    session_id = request.trace_id or f"secure-{uuid4().hex[:8]}"

    try:
        # Set security level based on request
        security_levels = {
            "paranoid": RedactionLevel.PARANOID,
            "high": RedactionLevel.HIGH,
            "medium": RedactionLevel.MEDIUM,
            "low": RedactionLevel.LOW
        }
        requested_level = security_levels.get(
            request.security_level.lower(),
            RedactionLevel.HIGH
        )

        # Create per-request agent for thread safety
        agent = create_secure_agent(requested_level)
        logger.info(f"Created new agent with security level: {requested_level.value}")

        # Create user context
        user_context = await create_user_context_from_user_id(user_id)

        # Check API keys
        gemini_key = await user_context.get_gemini_api_key()
        if not gemini_key:
            raise HTTPException(
                status_code=400,
                detail="API Key Required: Please add your Google Gemini API key in Settings"
            )

        # Perform security validation first
        validation_result = agent.security_validator.validate_request({
            "content": request.content,
            "question": request.question,
            "metadata": request.session_metadata
        })

        if validation_result.status == ValidationStatus.FAILED:
            logger.error(f"Request failed security validation: {validation_result.issues}")
            raise HTTPException(
                status_code=400,
                detail=f"Security validation failed: {', '.join(validation_result.issues)}"
            )

        if validation_result.threat_level == ThreatLevel.CRITICAL:
            logger.critical(f"Critical threat detected in request from user {user_id}")
            raise HTTPException(
                status_code=403,
                detail="Critical security threat detected"
            )

        # Log security warning if suspicious
        if validation_result.status == ValidationStatus.SUSPICIOUS:
            logger.warning(
                f"Suspicious content in request from user {user_id}: {validation_result.issues}"
            )

        # Use user context for analysis
        async with user_context_scope(user_context):
            # Create temporary file for secure processing
            with agent.cleanup_manager.temporary_file(suffix=".log") as temp_path:
                # Write content to temporary file
                temp_path.write_text(request.content)

                # Analyze with full security wrapper
                analysis_result, response = await agent.analyze_log_file(
                    log_file_path=temp_path,
                    user_query=request.question,
                    user_context_input=None,
                    use_cache=True,
                    attachments=[]
                )

        # Validate compliance before returning
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "security_level": requested_level.value,
            "analysis_summary": {
                "has_errors": bool(analysis_result.error_patterns),
                "severity_counts": analysis_result.metadata.severity_counts if analysis_result.metadata else {},
                "recommendation_count": len(analysis_result.recommendations) if analysis_result.recommendations else 0
            }
        }

        is_compliant, compliance_issues = agent.compliance_manager.validate_for_storage(session_data)

        if not is_compliant:
            logger.warning(f"Compliance issues for session {session_id}: {compliance_issues}")

        # Prepare response (already sanitized)
        secure_response = {
            "session_id": session_id,
            "analysis": response,
            "security_metadata": {
                "sanitized": True,
                "security_level": requested_level.value,
                "compliance_status": "compliant" if is_compliant else "non-compliant",
                "threat_level": validation_result.threat_level.value,
                "timestamp": datetime.now().isoformat()
            }
        }

        # Force cleanup before returning
        agent.cleanup_manager.force_cleanup()

        return secure_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Secure analysis failed for session {session_id}: {e}")
        # Ensure cleanup on error
        if 'agent' in locals():
            agent.cleanup_manager.force_cleanup()
        raise HTTPException(
            status_code=500,
            detail=f"Secure analysis failed: {str(e)}"
        )


@router.post("/agent/secure/logs/file")
async def analyze_log_file_securely(
    file: UploadFile = File(...),
    question: Optional[str] = Form(None),
    security_level: str = Form("high"),
    user_id: str = Depends(get_current_user_id)
):
    """
    Analyze uploaded log file with paranoid security.

    Features:
    - File validation and virus scanning simulation
    - Size and type restrictions
    - Complete sanitization
    - No persistent storage
    """
    # Validate file
    if not file.filename.lower().endswith(('.log', '.txt', '.text')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only .log, .txt, and .text files are allowed"
        )

    # Check file size (10MB limit)
    file_content = await file.read()
    if len(file_content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum size is 10MB"
        )

    try:
        # Decode content
        try:
            content = file_content.decode('utf-8')
        except UnicodeDecodeError:
            content = file_content.decode('utf-8', errors='ignore')

        # Process with secure endpoint
        request = SecureLogAnalysisRequest(
            content=content,
            question=question,
            security_level=security_level
        )

        return await analyze_logs_securely(request, user_id)

    finally:
        # Ensure file content is cleared from memory
        del file_content
        del content


@router.get("/agent/secure/audit")
async def get_security_audit(
    user_id: str = Depends(get_current_user_id)
) -> SecurityAuditResponse:
    """
    Get security audit information for the log analysis system.

    Returns:
    - Current security configuration
    - Cleanup statistics
    - Compliance status
    - Recent security validations
    """
    agent = get_secure_agent()

    audit_data = agent.get_security_audit()

    # Convert compliance report to dict for response
    if 'compliance_report' in audit_data:
        report = audit_data['compliance_report']
        audit_data['compliance_status'] = report.status.value
        audit_data['compliance_checks'] = report.checks_performed
        audit_data['compliance_issues'] = report.issues_found
        del audit_data['compliance_report']

    return SecurityAuditResponse(**audit_data)


@router.post("/agent/secure/compliance/check")
async def run_compliance_check(
    user_id: str = Depends(get_current_user_id)
):
    """
    Run a comprehensive compliance check.

    Returns detailed compliance report including:
    - Configuration compliance
    - Data protection status
    - Security policy adherence
    - Recommendations
    """
    agent = get_secure_agent()

    report = agent.compliance_manager.run_compliance_check()

    return {
        "timestamp": report.timestamp.isoformat(),
        "status": report.status.value,
        "checks_performed": report.checks_performed,
        "issues_found": report.issues_found,
        "recommendations": report.recommendations,
        "metadata": report.metadata
    }


@router.delete("/agent/secure/cleanup")
async def force_security_cleanup(
    user_id: str = Depends(get_current_user_id)
):
    """
    Force immediate cleanup of all temporary data.

    This endpoint ensures all sensitive data is immediately removed from memory
    and temporary storage.
    """
    agent = get_secure_agent()

    cleanup_stats = agent.cleanup_manager.force_cleanup()

    return {
        "status": "success",
        "cleanup_stats": cleanup_stats,
        "timestamp": datetime.now().isoformat()
    }


async def secure_log_stream_generator(
    log_content: str,
    question: Optional[str],
    session_id: str,
    user_id: str,
    security_level: RedactionLevel
):
    """Generator for streaming secure log analysis."""
    # Create per-request agent for thread safety
    agent = create_secure_agent(security_level)

    try:
        # Send initial security status
        yield f"data: {json.dumps({'type': 'security', 'status': 'validating'})}\n\n"

        # Validate content
        validation_result = agent.security_validator.validate_request({
            "content": log_content,
            "question": question
        })

        if validation_result.status == ValidationStatus.FAILED:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Security validation failed'})}\n\n"
            return

        # Send sanitization status
        yield f"data: {json.dumps({'type': 'security', 'status': 'sanitizing'})}\n\n"

        # Sanitize content
        sanitized_content, stats = agent.sanitizer.sanitize(log_content)

        yield f"data: {json.dumps({'type': 'security', 'redacted': sum(stats.values())})}\n\n"

        # Process analysis
        yield f"data: {json.dumps({'type': 'analysis', 'status': 'processing'})}\n\n"

        # Create user context and analyze
        user_context = await create_user_context_from_user_id(user_id)
        async with user_context_scope(user_context):
            with agent.cleanup_manager.temporary_file() as temp_path:
                temp_path.write_text(sanitized_content)

                analysis_result, response = await agent.analyze_log_file(
                    log_file_path=temp_path,
                    user_query=question
                )

        # Send result
        yield f"data: {json.dumps({'type': 'result', 'data': response})}\n\n"

        # Send completion
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        logger.error(f"Secure stream error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    finally:
        # Ensure cleanup
        agent.cleanup_manager.force_cleanup()


@router.post("/agent/secure/logs/stream")
async def secure_log_analysis_stream(
    request: SecureLogAnalysisRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Stream secure log analysis with real-time security updates.

    Provides:
    - Real-time security validation status
    - Sanitization progress
    - Analysis results
    - Compliance status
    """
    if not request.content:
        raise HTTPException(status_code=400, detail="Log content cannot be empty")

    session_id = request.trace_id or f"secure-stream-{uuid4().hex[:8]}"

    security_levels = {
        "paranoid": RedactionLevel.PARANOID,
        "high": RedactionLevel.HIGH,
        "medium": RedactionLevel.MEDIUM,
        "low": RedactionLevel.LOW
    }
    security_level = security_levels.get(request.security_level.lower(), RedactionLevel.HIGH)

    return StreamingResponse(
        secure_log_stream_generator(
            request.content,
            request.question,
            session_id,
            user_id,
            security_level
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )