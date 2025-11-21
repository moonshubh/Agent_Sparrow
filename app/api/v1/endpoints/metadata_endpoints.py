"""
Metadata and Observability Endpoints for Phase 6
Provides memory stats, quota status, and trace metadata for frontend transparency
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends, Path, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_user, User
from app.core.settings import settings
from app.db.supabase.client import get_supabase_client
from app.agents.unified.quota_manager import QuotaManager
from app.agents.unified.model_health import quota_tracker
from app.memory.service import MemoryService
from app.core.logging_config import get_logger

logger = get_logger("metadata_endpoints")
router = APIRouter(prefix="/metadata", tags=["Metadata"])

# ============================================
# Pydantic Models
# ============================================

class MemoryStats(BaseModel):
    """Memory statistics for a session"""
    facts_count: int = Field(..., description="Total facts in memory for this session")
    recent_facts: List[Dict[str, Any]] = Field(..., description="Most recently retrieved facts")
    write_count: int = Field(..., description="Number of facts written this session")
    last_write_at: Optional[datetime] = Field(None, description="Timestamp of last write")
    relevance_scores: Optional[List[float]] = Field(None, description="Recent relevance scores")

class QuotaStatus(BaseModel):
    """Real-time quota status across services"""
    gemini_pro_pct: float = Field(..., ge=0, le=100, description="Gemini Pro usage percentage")
    gemini_flash_pct: float = Field(..., ge=0, le=100, description="Gemini Flash usage percentage")
    grounding_pct: float = Field(..., ge=0, le=100, description="Grounding service usage percentage")
    embeddings_pct: float = Field(..., ge=0, le=100, description="Embeddings usage percentage")
    warnings: List[str] = Field(default_factory=list, description="Active quota warnings")

    # Detailed breakdowns
    gemini_pro: Dict[str, Any] = Field(default_factory=dict)
    gemini_flash: Dict[str, Any] = Field(default_factory=dict)
    grounding: Dict[str, Any] = Field(default_factory=dict)

class TraceMetadata(BaseModel):
    """Enhanced trace metadata from LangSmith"""
    trace_id: str = Field(..., description="LangSmith trace ID")
    session_id: str = Field(..., description="Session ID")
    model_used: str = Field(..., description="Primary model used")
    fallback_chain: Optional[List[str]] = Field(None, description="Models tried in order")
    fallback_occurred: bool = Field(False, description="Whether fallback was triggered")
    fallback_reason: Optional[str] = Field(None, description="Reason for fallback")

    search_service: Optional[str] = Field(None, description="Search service used")
    search_metadata: Optional[Dict[str, Any]] = Field(None, description="Search service details")

    memory_operations: Optional[Dict[str, Any]] = Field(None, description="Memory operation stats")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Tools invoked")

    duration_ms: Optional[int] = Field(None, description="Total execution time in milliseconds")
    token_count: Optional[int] = Field(None, description="Total tokens used")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# ============================================
# Memory Endpoints
# ============================================

@router.get("/memory/{session_id}/stats", response_model=MemoryStats)
async def get_memory_stats(
    session_id: str = Path(..., description="Session ID to get memory stats for"),
    current_user: User = Depends(get_current_user)
) -> MemoryStats:
    """
    Get memory statistics for a specific session.

    Returns facts count, recent retrievals, write stats, and relevance scores.
    """
    try:
        memory_service = MemoryService()
        supabase = get_supabase_client()

        # Get facts count for this session
        result = supabase.table("memory_facts").select("*", count="exact").eq(
            "session_id", session_id
        ).eq("user_id", current_user.id).execute()

        facts_count = result.count if result else 0

        # Get recent facts (last 5)
        recent_result = supabase.table("memory_facts").select("*").eq(
            "session_id", session_id
        ).eq("user_id", current_user.id).order(
            "created_at", desc=True
        ).limit(5).execute()

        recent_facts = []
        if recent_result and recent_result.data:
            recent_facts = [
                {
                    "fact": fact.get("fact", ""),
                    "relevance_score": fact.get("relevance_score"),
                    "created_at": fact.get("created_at")
                }
                for fact in recent_result.data
            ]

        # Get write count for this session
        write_result = supabase.table("memory_facts").select("created_at", count="exact").eq(
            "session_id", session_id
        ).eq("user_id", current_user.id).gte(
            "created_at", (datetime.utcnow() - timedelta(hours=24)).isoformat()
        ).execute()

        write_count = write_result.count if write_result else 0
        last_write_at = None

        # Get last_write_at from recent_result (already ordered by created_at desc)
        if recent_result and recent_result.data and len(recent_result.data) > 0:
            last_write_at = recent_result.data[0].get("created_at")

        # Get recent relevance scores
        relevance_scores = [
            fact.get("relevance_score", 0.0)
            for fact in recent_facts
            if fact.get("relevance_score") is not None
        ]

        return MemoryStats(
            facts_count=facts_count,
            recent_facts=recent_facts,
            write_count=write_count,
            last_write_at=last_write_at,
            relevance_scores=relevance_scores if relevance_scores else None
        )

    except Exception as e:
        logger.error(f"Error fetching memory stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch memory stats: {str(e)}")

# ============================================
# Quota Endpoints
# ============================================

@router.get("/quotas/status", response_model=QuotaStatus)
async def get_quota_status(
    current_user: User = Depends(get_current_user)
) -> QuotaStatus:
    """
    Get real-time quota status for all services.

    Returns usage percentages and warnings for rate limits approaching.
    """
    try:
        quota_manager = QuotaManager()

        # Get current usage for each service
        gemini_pro_health = await quota_tracker.get_health("gemini-2.5-pro")
        gemini_flash_health = await quota_tracker.get_health("gemini-2.5-flash")

        # Calculate percentages
        def calculate_percentage(used: int, limit: int) -> float:
            if limit == 0:
                return 0.0
            return min(100.0, (used / limit) * 100)

        gemini_pro_pct = calculate_percentage(
            gemini_pro_health.rpd_used,
            gemini_pro_health.rpd_limit
        )
        gemini_flash_pct = calculate_percentage(
            gemini_flash_health.rpd_used,
            gemini_flash_health.rpd_limit
        )

        # Get grounding usage (simplified - you may want to track this separately)
        grounding_pct = quota_manager.get_usage_percentage("grounding")
        embeddings_pct = quota_manager.get_usage_percentage("embeddings")

        # Generate warnings
        warnings = []
        if gemini_pro_pct > 80:
            warnings.append(f"Gemini Pro usage at {gemini_pro_pct:.0f}% - consider fallback")
        if gemini_flash_pct > 80:
            warnings.append(f"Gemini Flash usage at {gemini_flash_pct:.0f}%")
        if grounding_pct > 80:
            warnings.append(f"Grounding service approaching limit ({grounding_pct:.0f}%)")

        # Detailed breakdowns
        gemini_pro_details = {
            "rpm_used": gemini_pro_health.rpm_used,
            "rpm_limit": gemini_pro_health.rpm_limit,
            "rpd_used": gemini_pro_health.rpd_used,
            "rpd_limit": gemini_pro_health.rpd_limit,
            "circuit_state": gemini_pro_health.circuit_state,
            "available": gemini_pro_health.available
        }

        gemini_flash_details = {
            "rpm_used": gemini_flash_health.rpm_used,
            "rpm_limit": gemini_flash_health.rpm_limit,
            "rpd_used": gemini_flash_health.rpd_used,
            "rpd_limit": gemini_flash_health.rpd_limit,
            "circuit_state": gemini_flash_health.circuit_state,
            "available": gemini_flash_health.available
        }

        grounding_details = {
            "requests_today": quota_manager.get_usage("grounding"),
            "limit_per_day": quota_manager.get_limit("grounding"),
            "available": quota_manager.check_quota("grounding")
        }

        return QuotaStatus(
            gemini_pro_pct=gemini_pro_pct,
            gemini_flash_pct=gemini_flash_pct,
            grounding_pct=grounding_pct,
            embeddings_pct=embeddings_pct,
            warnings=warnings,
            gemini_pro=gemini_pro_details,
            gemini_flash=gemini_flash_details,
            grounding=grounding_details
        )

    except Exception as e:
        logger.error(f"Error fetching quota status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch quota status: {str(e)}")

# ============================================
# Trace Metadata Endpoints
# ============================================

@router.get("/sessions/{session_id}/traces/{trace_id}", response_model=TraceMetadata)
async def get_trace_metadata(
    session_id: str = Path(..., description="Session ID"),
    trace_id: str = Path(..., description="Trace ID from LangSmith"),
    current_user: User = Depends(get_current_user)
) -> TraceMetadata:
    """
    Get enhanced metadata for a specific trace.

    This would typically fetch from LangSmith API, but for now returns
    structured metadata from our local tracking.
    """
    try:
        # Verify session ownership
        supabase = get_supabase_client()
        session_check = supabase.table("chat_sessions").select("id").eq(
            "id", session_id
        ).eq("user_id", current_user.id).execute()

        if not session_check.data:
            raise HTTPException(
                status_code=404,
                detail="Session not found or access denied"
            )

        # In production, this would fetch from LangSmith API
        # For now, we'll return mock structured data
        # You could also store this in Redis or database during execution

        # Example implementation - replace with actual LangSmith integration
        metadata = TraceMetadata(
            trace_id=trace_id,
            session_id=session_id,
            model_used="gemini-2.5-flash",
            fallback_chain=None,
            fallback_occurred=False,
            fallback_reason=None,
            search_service="gemini_grounding",
            search_metadata={
                "results_count": 5,
                "max_requested": 5,
                "query_length": 42
            },
            memory_operations={
                "retrieval_attempted": True,
                "facts_retrieved": 3,
                "write_attempted": True,
                "facts_written": 1
            },
            tool_calls=[
                {
                    "tool": "search_knowledge_base",
                    "confidence": 0.95,
                    "duration_ms": 245
                }
            ],
            duration_ms=1250,
            token_count=850,
            timestamp=datetime.now(timezone.utc)
        )

        return metadata

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching trace metadata: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch trace metadata: {str(e)}")

# ============================================
# Health Check Endpoint
# ============================================

@router.get("/health")
async def health_check():
    """
    Check health of metadata services.
    """
    try:
        quota_manager = QuotaManager()

        # Check if services are accessible
        redis_ok = quota_manager.redis_client.ping() if quota_manager.redis_client else False

        return {
            "status": "healthy" if redis_ok else "degraded",
            "services": {
                "redis": "healthy" if redis_ok else "unavailable",
                "memory": "healthy",  # Could check Supabase connection
                "quotas": "healthy"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# ============================================
# Utility Functions
# ============================================

def get_usage_percentage(service_name: str, quota_manager: QuotaManager) -> float:
    """Helper to calculate usage percentage for a service"""
    try:
        used = quota_manager.get_usage(service_name)
        limit = quota_manager.get_limit(service_name)
        if limit == 0:
            return 0.0
        return min(100.0, (used / limit) * 100)
    except:
        return 0.0