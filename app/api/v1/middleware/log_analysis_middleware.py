"""
Middleware for Log Analysis Agent Backend Integration

This module provides middleware for:
- Request validation for log analysis
- Rate limiting for log analysis requests
- Session management for log analysis conversations
- Attachment insights persistence (metadata only)
"""

import asyncio
import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from fastapi import HTTPException, Request

from app.core.constants import AGENT_SESSION_LIMITS
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Rate limiting configuration for log analysis
LOG_ANALYSIS_RATE_LIMITS = {
    "requests_per_minute": 10,
    "requests_per_hour": 100,
    "requests_per_day": 500,
    "max_file_size_mb": 50,  # Maximum log file size in MB
    "max_concurrent_analyses": 3,  # Max concurrent analyses per user
}

TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
UTC_MIN = datetime.min.replace(tzinfo=timezone.utc)


class LogAnalysisRateLimiter:
    """Rate limiter specifically for log analysis requests."""

    def __init__(self):
        self._user_requests: Dict[str, List[datetime]] = {}
        self._concurrent_analyses: Dict[str, int] = {}
        self._user_locks: Dict[str, asyncio.Lock] = {}
        self._locks_lock: Optional[asyncio.Lock] = None

    async def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        if self._locks_lock is None:
            self._locks_lock = asyncio.Lock()
        async with self._locks_lock:
            lock = self._user_locks.get(user_id)
            if lock is None:
                lock = asyncio.Lock()
                self._user_locks[user_id] = lock
        return lock

    async def check_rate_limit(self, user_id: str) -> Dict[str, Any]:
        """
        Check if user has exceeded rate limits for log analysis.

        Args:
            user_id: User identifier

        Returns:
            Dict with allowed status and metadata

        Raises:
            HTTPException: If rate limit exceeded
        """
        user_lock = await self._get_user_lock(user_id)
        async with user_lock:
            now = datetime.now(timezone.utc)

            if user_id not in self._user_requests:
                self._user_requests[user_id] = []
                self._concurrent_analyses[user_id] = 0

            def _aware(ts: datetime) -> datetime:
                return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)

            self._user_requests[user_id] = [
                req_time
                for req_time in self._user_requests[user_id]
                if now - _aware(req_time) < timedelta(days=1)
            ]

            recent_minute = [
                req
                for req in self._user_requests[user_id]
                if now - _aware(req) < timedelta(minutes=1)
            ]
            if len(recent_minute) >= LOG_ANALYSIS_RATE_LIMITS["requests_per_minute"]:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Exceeded {LOG_ANALYSIS_RATE_LIMITS['requests_per_minute']} requests per minute for log analysis",
                        "retry_after": 60,
                    },
                )

            recent_hour = [
                req
                for req in self._user_requests[user_id]
                if now - _aware(req) < timedelta(hours=1)
            ]
            if len(recent_hour) >= LOG_ANALYSIS_RATE_LIMITS["requests_per_hour"]:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Exceeded {LOG_ANALYSIS_RATE_LIMITS['requests_per_hour']} requests per hour for log analysis",
                        "retry_after": 3600,
                    },
                )

            if (
                len(self._user_requests[user_id])
                >= LOG_ANALYSIS_RATE_LIMITS["requests_per_day"]
            ):
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Exceeded {LOG_ANALYSIS_RATE_LIMITS['requests_per_day']} requests per day for log analysis",
                        "retry_after": 86400,
                    },
                )

            if (
                self._concurrent_analyses[user_id]
                >= LOG_ANALYSIS_RATE_LIMITS["max_concurrent_analyses"]
            ):
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "concurrent_limit_exceeded",
                        "message": f"Maximum {LOG_ANALYSIS_RATE_LIMITS['max_concurrent_analyses']} concurrent log analyses allowed",
                        "retry_after": 30,
                    },
                )

            self._user_requests[user_id].append(now)
            self._concurrent_analyses[user_id] += 1

            return {
                "allowed": True,
                "requests_today": len(self._user_requests[user_id]),
                "concurrent_analyses": self._concurrent_analyses[user_id],
                "limits": LOG_ANALYSIS_RATE_LIMITS,
            }

    async def release_concurrent_slot(self, user_id: str):
        """Release a concurrent analysis slot when analysis completes."""
        user_lock = await self._get_user_lock(user_id)
        async with user_lock:
            if user_id in self._concurrent_analyses:
                self._concurrent_analyses[user_id] = max(
                    0, self._concurrent_analyses[user_id] - 1
                )

    async def get_user_usage(self, user_id: str) -> Dict[str, Any]:
        """Return a snapshot of rate limit usage for a user."""
        user_lock = await self._get_user_lock(user_id)
        async with user_lock:
            request_history = list(self._user_requests.get(user_id, []))
            concurrent = self._concurrent_analyses.get(user_id, 0)
        return {
            "requests": request_history,
            "concurrent": concurrent,
        }


# Global rate limiter instance
log_analysis_rate_limiter = LogAnalysisRateLimiter()


class LogAnalysisSessionManager:
    """
    Session manager for log analysis conversations.
    Stores only metadata and insights, not raw log files.
    """

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._session_limit = AGENT_SESSION_LIMITS.get("log_analysis", 10)
        self._lock: Optional[asyncio.Lock] = None

    async def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def create_session(
        self, user_id: str, session_id: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new log analysis session.

        Args:
            user_id: User identifier
            session_id: Session identifier
            metadata: Session metadata (file info, not content)

        Returns:
            Created session info
        """
        lock = await self._get_lock()
        async with lock:
            user_key = f"{user_id}:log_analysis"

            if user_key not in self._sessions:
                self._sessions[user_key] = {}

            user_sessions = self._sessions[user_key]
            if len(user_sessions) >= self._session_limit:
                oldest_session_id = min(
                    user_sessions.keys(),
                    key=lambda k: user_sessions[k].get("created_at", UTC_MIN),
                )
                del user_sessions[oldest_session_id]
                logger.info(
                    f"Evicted oldest log analysis session {oldest_session_id} for user {user_id}"
                )

            now = datetime.now(timezone.utc)
            session_data = {
                "session_id": session_id,
                "user_id": user_id,
                "created_at": now,
                "updated_at": now,
                "metadata": {
                    "file_name": metadata.get("file_name", "unknown.log"),
                    "file_size": metadata.get("file_size", 0),
                    "file_hash": metadata.get("file_hash", ""),
                    "log_format": metadata.get("log_format", "unknown"),
                    "line_count": metadata.get("line_count", 0),
                    "time_range": metadata.get("time_range", {}),
                    "analysis_type": metadata.get("analysis_type", "general"),
                },
                "insights": [],
                "conversation": [],
            }

            self._sessions[user_key][session_id] = session_data
            logger.info(f"Created log analysis session {session_id} for user {user_id}")

            return session_data

    async def add_insight(
        self, user_id: str, session_id: str, insight: Dict[str, Any]
    ) -> bool:
        """
        Add an analysis insight to a session.

        Args:
            user_id: User identifier
            session_id: Session identifier
            insight: Analysis insight (text only, no raw logs)

        Returns:
            Success status
        """
        lock = await self._get_lock()
        async with lock:
            user_key = f"{user_id}:log_analysis"

            if (
                user_key not in self._sessions
                or session_id not in self._sessions[user_key]
            ):
                logger.warning(f"Session {session_id} not found for user {user_id}")
                return False

            clean_insight = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": insight.get("type", "analysis"),
                "severity": insight.get("severity", "info"),
                "summary": insight.get("summary", ""),
                "details": insight.get("details", ""),
                "recommendations": insight.get("recommendations", []),
                "affected_components": insight.get("affected_components", []),
                "pattern_detected": insight.get("pattern_detected", False),
            }

            session = self._sessions[user_key][session_id]
            session["insights"].append(clean_insight)
            session["updated_at"] = datetime.now(timezone.utc)

            if len(session["insights"]) > 100:
                session["insights"] = session["insights"][-100:]

            return True

    async def get_session(
        self, user_id: str, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a session by ID."""
        lock = await self._get_lock()
        async with lock:
            user_key = f"{user_id}:log_analysis"
            if user_key in self._sessions and session_id in self._sessions[user_key]:
                return self._sessions[user_key][session_id]
            return None

    async def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """List all sessions for a user."""
        lock = await self._get_lock()
        async with lock:
            user_key = f"{user_id}:log_analysis"
            if user_key in self._sessions:
                return list(self._sessions[user_key].values())
            return []

    async def cleanup_old_sessions(self, max_age_days: int = 7):
        """Remove sessions older than specified days."""
        lock = await self._get_lock()
        async with lock:
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=max_age_days)

            def _aware(ts: datetime) -> datetime:
                return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)

            for user_key in list(self._sessions.keys()):
                sessions = self._sessions[user_key]
                for session_id in list(sessions.keys()):
                    updated_at = sessions[session_id].get("updated_at", UTC_MIN)
                    if _aware(updated_at) < cutoff_time:
                        del sessions[session_id]
                        logger.info(f"Cleaned up old log analysis session {session_id}")

                if not sessions:
                    del self._sessions[user_key]


# Global session manager instance
log_analysis_session_manager = LogAnalysisSessionManager()


class LogAnalysisRequestValidator:
    """Validator for log analysis requests."""

    @staticmethod
    async def validate_log_content(
        log_content: str, file_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate log content before analysis.

        Args:
            log_content: Raw log content
            file_name: Optional file name

        Returns:
            Validation results with metadata

        Raises:
            HTTPException: If validation fails
        """
        # Check content size
        content_size_mb = len(log_content.encode("utf-8")) / (1024 * 1024)
        if content_size_mb > LOG_ANALYSIS_RATE_LIMITS["max_file_size_mb"]:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "file_too_large",
                    "message": f"Log file exceeds {LOG_ANALYSIS_RATE_LIMITS['max_file_size_mb']}MB limit",
                    "actual_size_mb": round(content_size_mb, 2),
                },
            )

        # Check if content is empty
        if not log_content or not log_content.strip():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "empty_content",
                    "message": "Log content cannot be empty",
                },
            )

        # Detect log format
        log_format = LogAnalysisRequestValidator._detect_log_format(log_content)

        # Count lines
        lines = log_content.strip().split("\n")
        line_count = len(lines)

        # Calculate content hash for deduplication
        content_hash = hashlib.sha256(log_content.encode("utf-8")).hexdigest()

        # Extract time range if possible
        time_range = LogAnalysisRequestValidator._extract_time_range(lines, log_format)

        return {
            "valid": True,
            "file_name": file_name or "uploaded.log",
            "file_size": len(log_content),
            "file_size_mb": round(content_size_mb, 2),
            "file_hash": content_hash,
            "log_format": log_format,
            "line_count": line_count,
            "time_range": time_range,
        }

    @staticmethod
    def _detect_log_format(content: str) -> str:
        """Detect the format of log content."""
        # Simple format detection based on patterns
        sample = content[:1000]  # Check first 1000 chars

        if '"timestamp"' in sample and "{" in sample:
            return "json"
        elif any(pattern in sample for pattern in ["ERROR", "WARN", "INFO", "DEBUG"]):
            return "structured"
        elif any(char in sample for char in ["[", "]"]) and ":" in sample:
            return "syslog"
        else:
            return "plain"

    @staticmethod
    def _extract_time_range(
        lines: List[str], log_format: str
    ) -> Dict[str, Optional[str]]:
        """Extract time range from log lines."""
        # This is a simplified implementation
        # In production, you'd want more sophisticated timestamp parsing

        first_timestamp = None
        last_timestamp = None

        for line in lines[:10]:
            match = TIMESTAMP_PATTERN.search(line)
            if match:
                first_timestamp = match.group()
                break

        for line in reversed(lines[-10:]):
            match = TIMESTAMP_PATTERN.search(line)
            if match:
                last_timestamp = match.group()
                break

        return {"start": first_timestamp, "end": last_timestamp}


async def log_analysis_request_middleware(
    request: Request, user_id: str, log_content: str, file_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Middleware to validate and prepare log analysis requests.

    Args:
        request: FastAPI request object
        user_id: User identifier
        log_content: Raw log content
        file_name: Optional file name

    Returns:
        Validated request metadata

    Raises:
        HTTPException: If validation or rate limiting fails
    """
    try:
        # Validate log content
        validation_result = await LogAnalysisRequestValidator.validate_log_content(
            log_content, file_name
        )

        # Check rate limits
        rate_limit_result = await log_analysis_rate_limiter.check_rate_limit(user_id)

        # Combine results
        return {
            **validation_result,
            **rate_limit_result,
            "user_id": user_id,
            "request_id": request.headers.get("X-Request-ID", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in log analysis middleware: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "middleware_error",
                "message": "Failed to process log analysis request",
            },
        )
