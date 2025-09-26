"""
Advanced Agent Endpoints for exposing reasoning and troubleshooting features.

This module provides REST endpoints for accessing the advanced capabilities
of the Primary Agent, including the 6-phase reasoning pipeline and
structured troubleshooting workflows.

Simplified version without Redis dependency - uses in-memory session store
suitable for small-scale deployments (10 users).
"""

from fastapi import APIRouter, HTTPException, Depends, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Literal, AsyncGenerator
from datetime import datetime, timedelta
import logging
import json
import uuid
import re
import asyncio
import os

# Use the new in-memory session store instead of Redis
from app.core.session_store import store_session, get_session, delete_session, get_session_store
from app.agents_v2.primary_agent.reasoning.reasoning_engine import ReasoningEngine, ReasoningConfig
from app.agents_v2.primary_agent.troubleshooting.troubleshooting_engine import (
    TroubleshootingEngine, 
    TroubleshootingConfig
)
from app.agents_v2.primary_agent.troubleshooting.troubleshooting_schemas import (
    TroubleshootingState,
    DiagnosticStep,
    TroubleshootingPhase
)
from app.agents_v2.primary_agent.reasoning.schemas import (
    ReasoningState,
    QueryAnalysis,
    EmotionalState,
    ToolDecisionType,
    ProblemCategory
)
from app.api.v1.endpoints.auth import get_current_user_id
from app.core.user_context import user_context_scope, create_user_context_from_user_id
from app.core.settings import get_settings
from app.core.security import sanitize_input
from app.core.quality_manager import (
    AdaptiveQualityManager,
    QualityLevel,
    get_quality_manager
)

logger = logging.getLogger(__name__)

# Quality timeout multipliers for different quality levels
QUALITY_MULTIPLIERS = {
    "fast": 0.5,
    "balanced": 1.0,
    "thorough": 1.5
}
router = APIRouter(prefix="/agent/advanced", tags=["advanced-agent"])
settings = get_settings()

# Get the global quality manager instance
quality_manager = get_quality_manager()

# ============= Input Validation Helpers =============
def validate_session_id(v: Optional[str]) -> Optional[str]:
    """Validate session ID format."""
    if v is None:
        return None
    if not re.match(r'^[a-zA-Z0-9-_]{8,64}$', v):
        raise ValueError('Invalid session ID format')
    return v

def validate_query_length(v: str) -> str:
    """Validate query length."""
    if len(v) < 1:
        raise ValueError('Query cannot be empty')
    if len(v) > 10000:
        raise ValueError('Query too long (max 10000 characters)')
    # Basic XSS prevention
    if '<script' in v.lower() or 'javascript:' in v.lower():
        raise ValueError('Invalid characters in query')
    return v

def get_timeout_for_operation(operation: str, quality_level: str = "balanced") -> int:
    """Calculate timeout for an operation based on quality level."""
    # Convert string to QualityLevel enum
    quality_enum = QualityLevel(quality_level)
    return quality_manager.get_timeout(operation, quality_enum)

# ============= Request/Response Models =============
class ReasoningRequest(BaseModel):
    """Request model for reasoning analysis with validation."""
    query: str = Field(..., description="The user query to analyze", min_length=1, max_length=10000)
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context")
    # Optional provider/model selection (Phase 2)
    provider: Optional[Literal["google", "openai"]] = Field(None, description="LLM provider override for this request")
    model: Optional[str] = Field(None, description="Model ID override for this request")
    enable_chain_of_thought: bool = Field(default=True, description="Enable chain-of-thought reasoning")
    enable_problem_solving: bool = Field(default=True, description="Enable problem-solving framework")
    enable_tool_intelligence: bool = Field(default=True, description="Enable intelligent tool selection")
    enable_quality_assessment: bool = Field(default=True, description="Enable quality assessment")
    thinking_budget: Optional[int] = Field(None, ge=1, le=100, description="Maximum thinking steps (1-100)")
    session_id: Optional[str] = Field(None, description="Session ID for context")
    quality_level: Optional[str] = Field(default="balanced", description="Quality level for processing")
    stream_response: bool = Field(default=False, description="Stream partial results as they become available")
    
    @validator('query')
    def validate_query(cls, v):
        return validate_query_length(v)
    
    @validator('session_id')
    def validate_session(cls, v):
        return validate_session_id(v)
    
    @validator('quality_level')
    def validate_quality_level(cls, v):
        if v not in ["fast", "balanced", "thorough"]:
            raise ValueError('Invalid quality level')
        return v

class ReasoningResponse(BaseModel):
    """Response model for reasoning analysis."""
    query_analysis: Dict[str, Any]
    context_recognition: Dict[str, Any]
    solution_mapping: Dict[str, Any]
    tool_reasoning: Dict[str, Any]
    response_strategy: Dict[str, Any]
    quality_assessment: Dict[str, Any]
    confidence_score: float
    thinking_steps: List[Dict[str, Any]]
    emotional_intelligence: Dict[str, Any]
    session_id: Optional[str] = None
    quality_level: str = "balanced"
    processing_time_ms: Optional[int] = None

class TroubleshootingRequest(BaseModel):
    """Request model for starting troubleshooting with validation."""
    problem_description: str = Field(..., min_length=1, max_length=5000, description="Description of the problem")
    problem_category: Optional[str] = Field(None, description="Problem category")
    customer_technical_level: Optional[int] = Field(
        3,  # 1-5 scale, 3 is intermediate
        description="Customer's technical level (1-5 scale)",
        ge=1,
        le=5
    )
    previous_attempts: Optional[List[str]] = Field(default_factory=list, description="Previous attempts")
    session_id: Optional[str] = Field(None, description="Session ID for persistence")
    quality_level: Optional[str] = Field(default="balanced", description="Quality level for processing")
    
    @validator('problem_description')
    def validate_problem(cls, v):
        return validate_query_length(v)
    
    @validator('session_id')
    def validate_session(cls, v):
        return validate_session_id(v)
    
    @validator('previous_attempts')
    def validate_attempts(cls, v):
        if v and len(v) > 10:
            raise ValueError('Too many previous attempts (max 10)')
        # Sanitize each attempt
        return [sanitize_input(attempt) for attempt in v] if v else []
    
    @validator('quality_level')
    def validate_quality_level(cls, v):
        if v not in ["fast", "balanced", "thorough"]:
            raise ValueError('Invalid quality level')
        return v

class TroubleshootingResponse(BaseModel):
    """Response model for troubleshooting operations."""
    session_id: str
    current_phase: TroubleshootingPhase
    current_step: Optional[DiagnosticStep] = None
    next_steps: List[DiagnosticStep]
    progress_percentage: float
    verification_status: Optional[Dict[str, Any]] = None
    escalation_recommended: bool = False
    escalation_reason: Optional[str] = None
    workflow_complete: bool = False
    resolution_summary: Optional[str] = None
    quality_level: str = "balanced"
    processing_time_ms: Optional[int] = None

class DiagnosticStepRequest(BaseModel):
    """Request model for executing a diagnostic step with validation."""
    session_id: str = Field(..., description="Troubleshooting session ID")
    step_id: str = Field(..., min_length=1, max_length=100, description="Step ID to execute")
    step_result: Literal["success", "failure", "partial", "skip"] = Field(..., description="Step result")
    customer_feedback: Optional[str] = Field(None, max_length=1000, description="Customer feedback (max 1000 chars)")
    additional_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional data")
    quality_level: Optional[str] = Field(default="balanced", description="Quality level for processing")
    
    @validator('session_id')
    def validate_session(cls, v):
        return validate_session_id(v)
    
    @validator('customer_feedback')
    def validate_feedback(cls, v):
        if v:
            # Sanitize customer feedback to prevent XSS
            return sanitize_input(v)
        return v
    
    @validator('quality_level')
    def validate_quality_level(cls, v):
        if v not in ["fast", "balanced", "thorough"]:
            raise ValueError('Invalid quality level')
        return v

# ============= Security Helpers =============
async def validate_user_permissions(user_id: str, action: str) -> bool:
    """Validate user has permission for the requested action."""
    # For 10-user deployment, all authenticated users have basic permissions
    return bool(user_id)

async def get_safe_config(user_id: str, request_config: Optional[Dict] = None) -> Dict:
    """Get safe configuration based on user permissions."""
    # Simplified for 10-user deployment
    return {
        'enable_adaptive_workflows': True,
        'enable_progressive_complexity': True,
        'enable_verification_checkpoints': True,
        'enable_automatic_escalation': False,  # Manual escalation for small deployments
        'max_diagnostic_steps': 20,
        'thinking_budget': min(request_config.get('thinking_budget', 30) if request_config else 30, 50)
    }

# ============= Progressive Result Streaming =============
async def stream_reasoning_results(
    reasoning_engine: ReasoningEngine,
    query: str,
    context: Dict[str, Any],
    session_id: str
) -> AsyncGenerator[str, None]:
    """Stream reasoning results progressively as they become available."""
    try:
        # Start reasoning
        start_time = datetime.utcnow()
        
        # Yield initial status
        yield json.dumps({
            "type": "status",
            "phase": "starting",
            "message": "Initializing reasoning analysis..."
        }) + "\n"
        
        # Perform reasoning with progress updates
        reasoning_state = await reasoning_engine.reason_about_query(
            query=query,
            context=context,
            session_id=session_id
        )
        
        # Yield completed phases as they're available
        phases = [
            ("query_analysis", reasoning_state.query_analysis),
            ("context_recognition", reasoning_state.context_recognition),
            ("solution_mapping", reasoning_state.solution_mapping),
            ("tool_reasoning", reasoning_state.tool_reasoning),
            ("response_strategy", reasoning_state.response_strategy),
            ("quality_assessment", reasoning_state.quality_assessment)
        ]
        
        for phase_name, phase_data in phases:
            if phase_data:
                yield json.dumps({
                    "type": "phase_complete",
                    "phase": phase_name,
                    "data": phase_data.dict() if hasattr(phase_data, 'dict') else phase_data
                }) + "\n"
                await asyncio.sleep(0.01)  # Small delay for streaming effect
        
        # Calculate processing time
        processing_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        # Yield final result
        yield json.dumps({
            "type": "complete",
            "session_id": session_id,
            "processing_time_ms": processing_time_ms,
            "confidence_score": reasoning_state.overall_confidence
        }) + "\n"
        
    except Exception as e:
        logger.error(f"Error in streaming reasoning: {e}")
        yield json.dumps({
            "type": "error",
            "message": str(e)
        }) + "\n"

# ============= Endpoints =============

@router.post("/reasoning", response_model=ReasoningResponse)
async def analyze_with_reasoning(
    request: ReasoningRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Perform advanced reasoning analysis on a user query.
    
    This endpoint exposes the 6-phase reasoning pipeline:
    1. Query Analysis - Understand intent and emotional state
    2. Context Recognition - Identify patterns and context
    3. Solution Mapping - Generate solution candidates
    4. Tool Assessment - Decide on tool usage
    5. Response Strategy - Plan the response approach
    6. Quality Assessment - Evaluate the response quality
    
    Supports streaming for progressive result delivery.
    """
    try:
        start_time = datetime.utcnow()
        
        # Create user context
        user_context = await create_user_context_from_user_id(user_id)
        
        # Determine provider/model (per-request override or defaults)
        from app.agents_v2.primary_agent.adapter_bridge import get_primary_agent_model
        from app.providers.registry import default_provider, default_model_for_provider
        provider = (request.provider or default_provider()).lower()
        model_id = (request.model or default_model_for_provider(provider)).lower()

        # Resolve API key and basic access validation
        # Note: For Phase 2, Google uses user key; OpenAI uses env or user key if available.
        openai_key: Optional[str] = None
        gemini_key: Optional[str] = None

        if provider == "google":
            gemini_key = await user_context.get_gemini_api_key()
            if not gemini_key:
                raise HTTPException(
                    status_code=400,
                    detail="API Key Required: Please configure your Gemini API key in settings."
                )
        elif provider == "openai":
            # Try user-specific OpenAI key via Supabase API key service
            # Fallback to environment variable OPENAI_API_KEY
            openai_key = None
            if hasattr(user_context, "get_openai_api_key"):
                openai_key = await user_context.get_openai_api_key()

            openai_key = openai_key or os.getenv("OPENAI_API_KEY")
            if not openai_key:
                raise HTTPException(
                    status_code=400,
                    detail="OpenAI API key missing. Please configure your OpenAI key in settings or set OPENAI_API_KEY."
                )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

        async with user_context_scope(user_context):
            # Calculate timeout based on quality level
            timeout = get_timeout_for_operation(
                "reasoning",
                request.quality_level
            )
            
            # Initialize reasoning engine config
            config = ReasoningConfig(
                enable_chain_of_thought=request.enable_chain_of_thought,
                enable_problem_solving_framework=request.enable_problem_solving,
                enable_tool_intelligence=request.enable_tool_intelligence,
                enable_quality_assessment=request.enable_quality_assessment,
                enable_reasoning_transparency=True,
                thinking_budget_override=request.thinking_budget,
                quality_level=request.quality_level
            )

            # Load model via provider registry
            api_key = gemini_key if provider == "google" else openai_key
            model = await get_primary_agent_model(api_key=api_key, provider=provider, model=model_id)

            # Instantiate reasoning engine with model (fix incorrect ctor)
            reasoning_engine = ReasoningEngine(
                model=model,
                config=config,
                provider=provider,
                model_name=model_id,
            )
            reasoning_engine._api_key = api_key
            
            # Generate session ID if not provided
            session_id = request.session_id or str(uuid.uuid4())
            
            # Stream results if requested
            if request.stream_response:
                return StreamingResponse(
                    stream_reasoning_results(
                        reasoning_engine,
                        request.query,
                        request.context or {},
                        session_id
                    ),
                    media_type="application/x-ndjson"
                )
            
            # Perform reasoning analysis with timeout
            try:
                reasoning_state = await asyncio.wait_for(
                    reasoning_engine.reason_about_query(
                        query=request.query,
                        context=request.context or {},
                        session_id=session_id
                    ),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=408,
                    detail=f"Reasoning analysis timed out after {timeout} seconds. Try using 'fast' quality level."
                )
            
            # Store session in memory store
            await store_session(session_id, 'reasoning', reasoning_state, ttl=3600)
            
            # Calculate processing time
            processing_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Convert to response format
            return ReasoningResponse(
                query_analysis={
                    "original_query": reasoning_state.query_analysis.original_query,
                    "intent": reasoning_state.query_analysis.intent,
                    "problem_category": reasoning_state.query_analysis.problem_category.value if reasoning_state.query_analysis.problem_category else None,
                    "emotional_state": reasoning_state.query_analysis.emotional_state.value if reasoning_state.query_analysis.emotional_state else "neutral",
                    "urgency_level": reasoning_state.query_analysis.urgency_level,
                    "technical_complexity": reasoning_state.query_analysis.technical_complexity
                },
                context_recognition={
                    "previous_interactions": reasoning_state.context_recognition.previous_interactions,
                    "user_expertise_level": reasoning_state.context_recognition.user_expertise_level,
                    "environmental_factors": reasoning_state.context_recognition.environmental_factors,
                    "related_issues": reasoning_state.context_recognition.related_issues
                },
                solution_mapping={
                    "potential_solutions": [
                        {
                            "solution": sol.solution,
                            "confidence": sol.confidence,
                            "time_estimate": sol.time_estimate,
                            "prerequisites": sol.prerequisites
                        } for sol in reasoning_state.solution_mapping.potential_solutions
                    ],
                    "recommended_approach": reasoning_state.solution_mapping.recommended_approach,
                    "alternative_paths": reasoning_state.solution_mapping.alternative_paths,
                    "knowledge_gaps": reasoning_state.solution_mapping.knowledge_gaps
                },
                tool_reasoning={
                    "decision_type": reasoning_state.tool_reasoning.decision_type.value,
                    "confidence": reasoning_state.tool_reasoning.confidence.value,
                    "reasoning": reasoning_state.tool_reasoning.reasoning,
                    "recommended_tools": reasoning_state.tool_reasoning.recommended_tools,
                    "tool_sequence": reasoning_state.tool_reasoning.tool_sequence
                },
                response_strategy={
                    "approach": reasoning_state.response_strategy.approach,
                    "tone": reasoning_state.response_strategy.tone,
                    "structure": reasoning_state.response_strategy.structure,
                    "key_points": reasoning_state.response_strategy.key_points,
                    "examples_needed": reasoning_state.response_strategy.examples_needed
                },
                quality_assessment={
                    "clarity_score": reasoning_state.quality_assessment.clarity_score,
                    "completeness_score": reasoning_state.quality_assessment.completeness_score,
                    "accuracy_confidence": reasoning_state.quality_assessment.accuracy_confidence,
                    "improvement_suggestions": reasoning_state.quality_assessment.improvement_suggestions,
                    "potential_misunderstandings": reasoning_state.quality_assessment.potential_misunderstandings
                },
                confidence_score=reasoning_state.overall_confidence,
                thinking_steps=[
                    {
                        "phase": step.phase,
                        "thought": step.thought,
                        "confidence": step.confidence,
                        "evidence": step.evidence,
                        "alternatives_considered": step.alternatives_considered
                    } for step in reasoning_state.thinking_steps
                ],
                emotional_intelligence={
                    "detected_emotion": reasoning_state.query_analysis.emotional_state.value if reasoning_state.query_analysis.emotional_state else "neutral",
                    "empathy_response": reasoning_state.response_strategy.empathy_statements[0] if reasoning_state.response_strategy.empathy_statements else None,
                    "emotional_validation": reasoning_state.query_analysis.emotional_confidence
                },
                session_id=session_id,
                quality_level=request.quality_level,
                processing_time_ms=processing_time_ms
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reasoning analysis failed for user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred during reasoning analysis. Please try again."
        )

@router.post("/troubleshooting/start", response_model=TroubleshootingResponse)
async def start_troubleshooting(
    request: TroubleshootingRequest,
    user_id: str = Depends(get_current_user_id)
) -> TroubleshootingResponse:
    """
    Start a structured troubleshooting session.
    
    This initiates a 7-phase troubleshooting workflow:
    1. Initial Assessment
    2. Basic Diagnostics
    3. Intermediate Diagnostics
    4. Advanced Diagnostics
    5. Specialized Testing
    6. Escalation Preparation
    7. Resolution Verification
    """
    try:
        start_time = datetime.utcnow()
        
        # Create user context
        user_context = await create_user_context_from_user_id(user_id)
        
        # Check for API key
        gemini_key = await user_context.get_gemini_api_key()
        if not gemini_key:
            raise HTTPException(
                status_code=400,
                detail="API Key Required: Please configure your Gemini API key in settings."
            )
        
        async with user_context_scope(user_context):
            # Get safe configuration
            safe_config = await get_safe_config(user_id)
            
            # Calculate timeout based on quality level
            timeout = get_timeout_for_operation(
                "troubleshooting",
                request.quality_level
            )
            
            # Initialize troubleshooting engine with safe config
            config = TroubleshootingConfig(
                enable_adaptive_workflows=safe_config['enable_adaptive_workflows'],
                enable_progressive_complexity=safe_config['enable_progressive_complexity'],
                enable_verification_checkpoints=safe_config['enable_verification_checkpoints'],
                enable_automatic_escalation=safe_config['enable_automatic_escalation'],
                max_diagnostic_steps=safe_config['max_diagnostic_steps']
            )
            
            troubleshooting_engine = TroubleshootingEngine(config)
            
            # Generate session ID if not provided
            session_id = request.session_id or str(uuid.uuid4())
            
            # Initialize troubleshooting state with timeout
            try:
                initial_state = await asyncio.wait_for(
                    troubleshooting_engine.initiate_troubleshooting(
                        query_text=request.problem_description,
                        problem_category=request.problem_category,
                        customer_technical_level=request.customer_technical_level,
                        previous_attempts=request.previous_attempts
                    ),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=408,
                    detail=f"Troubleshooting initialization timed out after {timeout} seconds. Try using 'fast' quality level."
                )
            
            # Start the session
            session = await troubleshooting_engine.start_troubleshooting_session(
                troubleshooting_state=initial_state,
                session_id=session_id
            )
            
            # Store session in memory store
            await store_session(session_id, 'troubleshooting', session.state, ttl=7200)  # 2 hour TTL
            
            # Get next steps
            next_steps = session.state.workflow.get_next_steps(3)
            
            # Calculate processing time
            processing_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return TroubleshootingResponse(
                session_id=session_id,
                current_phase=session.state.current_phase,
                current_step=session.state.current_step,
                next_steps=next_steps,
                progress_percentage=session.state.progress_percentage,
                verification_status=None,
                escalation_recommended=False,
                workflow_complete=False,
                quality_level=request.quality_level,
                processing_time_ms=processing_time_ms
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Troubleshooting start failed for user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to start troubleshooting session. Please try again."
        )

@router.post("/troubleshooting/step", response_model=TroubleshootingResponse)
async def execute_diagnostic_step(
    request: DiagnosticStepRequest = Body(...),
    user_id: str = Depends(get_current_user_id)
) -> TroubleshootingResponse:
    """
    Execute a diagnostic step in an active troubleshooting session.
    
    This endpoint handles:
    - Step execution and result recording
    - Workflow progression
    - Verification checkpoints
    - Escalation decisions
    """
    try:
        start_time = datetime.utcnow()
        
        # Retrieve session from memory store
        session_data = await get_session(request.session_id, 'troubleshooting')
        if not session_data:
            raise HTTPException(status_code=404, detail="Troubleshooting session not found or expired")
        
        # Reconstruct session state
        session_state = TroubleshootingState(**session_data)
        
        # Create user context
        user_context = await create_user_context_from_user_id(user_id)
        
        async with user_context_scope(user_context):
            # Calculate timeout based on quality level
            timeout = get_timeout_for_operation(
                "diagnostic",
                request.quality_level
            )
            
            # Re-initialize engine with config
            config = TroubleshootingConfig(
                enable_adaptive_workflows=True,
                enable_verification_checkpoints=True,
                enable_automatic_escalation=False  # Manual escalation for small deployments
            )
            
            troubleshooting_engine = TroubleshootingEngine(config)
            
            # Execute the step with timeout
            try:
                updated_state = await asyncio.wait_for(
                    troubleshooting_engine.execute_diagnostic_step(
                        state=session_state,
                        step_id=request.step_id,
                        result=request.step_result,
                        customer_feedback=request.customer_feedback,
                        additional_data=request.additional_data
                    ),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=408,
                    detail=f"Diagnostic step execution timed out after {timeout} seconds. Try using 'fast' quality level."
                )
            
            # Update session in memory store
            await store_session(request.session_id, 'troubleshooting', updated_state, ttl=7200)
            
            # Check for escalation
            escalation_info = await troubleshooting_engine.check_escalation_criteria(updated_state)
            
            # Get next steps
            next_steps = updated_state.workflow.get_next_steps(3) if updated_state.workflow else []
            
            # Check if workflow is complete
            workflow_complete = (
                updated_state.current_phase == TroubleshootingPhase.RESOLUTION_VERIFICATION and
                updated_state.resolution_achieved
            )
            
            # Calculate processing time
            processing_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return TroubleshootingResponse(
                session_id=request.session_id,
                current_phase=updated_state.current_phase,
                current_step=updated_state.current_step,
                next_steps=next_steps,
                progress_percentage=updated_state.progress_percentage,
                verification_status={
                    "checkpoints_passed": updated_state.verification_checkpoints,
                    "current_verification": updated_state.current_step.verification if updated_state.current_step else None
                },
                escalation_recommended=escalation_info.get("should_escalate", False),
                escalation_reason=escalation_info.get("reason"),
                workflow_complete=workflow_complete,
                resolution_summary=updated_state.resolution_summary if workflow_complete else None,
                quality_level=request.quality_level,
                processing_time_ms=processing_time_ms
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing diagnostic step: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/troubleshooting/session/{session_id}", response_model=TroubleshootingResponse)
async def get_troubleshooting_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id)
) -> TroubleshootingResponse:
    """
    Retrieve the current state of a troubleshooting session.
    """
    try:
        # Retrieve session from memory store
        session_data = await get_session(session_id, 'troubleshooting')
        if not session_data:
            raise HTTPException(status_code=404, detail="Troubleshooting session not found or expired")
        
        # Reconstruct session state
        session_state = TroubleshootingState(**session_data)
        
        # Get next steps
        next_steps = session_state.workflow.get_next_steps(3) if session_state.workflow else []
        
        # Check if workflow is complete
        workflow_complete = (
            session_state.current_phase == TroubleshootingPhase.RESOLUTION_VERIFICATION and
            session_state.resolution_achieved
        )
        
        return TroubleshootingResponse(
            session_id=session_id,
            current_phase=session_state.current_phase,
            current_step=session_state.current_step,
            next_steps=next_steps,
            progress_percentage=session_state.progress_percentage,
            verification_status={
                "checkpoints_passed": session_state.verification_checkpoints,
                "current_verification": session_state.current_step.verification if session_state.current_step else None
            },
            escalation_recommended=False,
            workflow_complete=workflow_complete,
            resolution_summary=session_state.resolution_summary if workflow_complete else None,
            quality_level="balanced"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving troubleshooting session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/troubleshooting/session/{session_id}")
async def end_troubleshooting_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id)
) -> Dict[str, str]:
    """
    End and cleanup a troubleshooting session.
    """
    try:
        # Delete session from memory store
        deleted = await delete_session(session_id, 'troubleshooting')
        if not deleted:
            raise HTTPException(status_code=404, detail="Troubleshooting session not found or already ended")
        
        return {"message": "Troubleshooting session ended successfully", "session_id": session_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ending troubleshooting session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============= Session Management Endpoints =============

@router.get("/sessions/stats")
async def get_session_stats(
    user_id: str = Depends(get_current_user_id)
) -> Dict[str, Any]:
    """
    Get statistics about active sessions.
    """
    try:
        store = get_session_store()
        stats = store.get_stats()
        return {
            "status": "healthy",
            "session_storage": "in-memory",
            "stats": stats,
            "limits": {
                "max_sessions": stats['max_sessions'],
                "current_usage": f"{stats['total_sessions']}/{stats['max_sessions']}",
                "usage_percentage": (stats['total_sessions'] / stats['max_sessions']) * 100
            }
        }
    except Exception as e:
        logger.error(f"Error getting session stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve session statistics")

@router.post("/sessions/cleanup")
async def cleanup_expired_sessions(
    user_id: str = Depends(get_current_user_id)
) -> Dict[str, Any]:
    """
    Manually trigger cleanup of expired sessions.
    """
    try:
        store = get_session_store()
        await store._cleanup_expired()
        stats = store.get_stats()
        return {
            "message": "Cleanup completed successfully",
            "sessions_after_cleanup": stats['total_sessions'],
            "total_expirations": stats['expirations']
        }
    except Exception as e:
        logger.error(f"Error during session cleanup: {e}")
        raise HTTPException(status_code=500, detail="Failed to cleanup sessions")

# ============= Health Check =============

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Check the health of advanced agent endpoints.
    """
    store = get_session_store()
    stats = await store.get_stats()
    
    return {
        "status": "healthy",
        "session_storage": "in-memory",
        "storage_healthy": True,
        "active_sessions": stats['total_sessions'],
        "session_capacity": f"{stats['total_sessions']}/{stats['max_sessions']}",
        "features": {
            "reasoning_pipeline": True,
            "troubleshooting_workflows": True,
            "emotional_intelligence": True,
            "adaptive_complexity": True,
            "quality_levels": True,
            "streaming_support": True
        },
        "quality_levels": {
            "available": ["fast", "balanced", "thorough"],
            "timeout_multipliers": QUALITY_MULTIPLIERS
        }
    }

# ============= Startup/Shutdown Hooks =============

@router.on_event("startup")
async def startup_event():
    """Initialize the session store on startup."""
    store = get_session_store()
    await store.start()
    logger.info("In-memory session store initialized and cleanup task started")

@router.on_event("shutdown")
async def shutdown_event():
    """Cleanup the session store on shutdown."""
    store = get_session_store()
    await store.stop()
    logger.info("In-memory session store cleanup task stopped")
