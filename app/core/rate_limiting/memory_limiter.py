"""
Simplified in-memory rate limiter for small-scale deployments.

This module provides a thread-safe rate limiting solution that
eliminates the need for Redis in small deployments (10 users).
"""

import asyncio
import time
from collections import defaultdict, deque
from threading import RLock
from typing import Any, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """
    Thread-safe in-memory rate limiter using sliding window algorithm.

    Designed for small-scale deployments where Redis overhead is not justified.
    Tracks requests per user/API key with configurable time windows.
    """

    def __init__(self):
        """Initialize the in-memory rate limiter."""
        self._windows: Dict[str, deque] = defaultdict(deque)
        self._lock = RLock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = 60  # Cleanup every minute

    async def start(self):
        """Start the background cleanup task."""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Rate limiter cleanup task started")

    async def stop(self):
        """Stop the background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Rate limiter cleanup task stopped")

    async def check_rate_limit(
        self, key: str, limit: int, window_seconds: int = 60, safety_margin: float = 0.2
    ) -> Tuple[bool, Optional[int], Optional[int]]:
        """
        Check if a request is within rate limits.

        Args:
            key: Unique identifier (e.g., user_id, api_key)
            limit: Maximum requests allowed in the window
            window_seconds: Time window in seconds
            safety_margin: Reserve percentage of limit (0.0 to 1.0)

        Returns:
            Tuple of (allowed, remaining_requests, reset_time_seconds)
        """
        current_time = time.time()
        window_start = current_time - window_seconds
        effective_limit = int(limit * (1 - safety_margin))

        with self._lock:
            # Get or create window for this key
            window = self._windows[key]

            # Remove expired entries
            while window and window[0] < window_start:
                window.popleft()

            # Check if under limit
            current_count = len(window)
            if current_count >= effective_limit:
                # Calculate when the oldest request will expire
                if window:
                    reset_time = int(window[0] + window_seconds - current_time) + 1
                else:
                    reset_time = 0
                return False, 0, reset_time

            # Add current request
            window.append(current_time)
            remaining = effective_limit - current_count - 1

            # Calculate reset time (when current window expires)
            reset_time = window_seconds

            return True, remaining, reset_time

    async def get_usage(self, key: str, window_seconds: int = 60) -> Dict[str, int]:
        """
        Get current usage statistics for a key.

        Args:
            key: Unique identifier
            window_seconds: Time window to check

        Returns:
            Dictionary with usage statistics
        """
        current_time = time.time()
        window_start = current_time - window_seconds

        with self._lock:
            window = self._windows.get(key, deque())

            # Count requests in current window
            count = sum(1 for ts in window if ts >= window_start)

            stats: Dict[str, Any] = {
                "current_requests": count,
                "window_seconds": window_seconds,
                "oldest_request_age": int(current_time - window[0]) if window else None,
            }
            return stats

    async def reset(self, key: str):
        """Reset rate limit for a specific key."""
        with self._lock:
            if key in self._windows:
                del self._windows[key]
                logger.debug(f"Reset rate limit for key: {key}")

    async def reset_all(self):
        """Reset all rate limits."""
        with self._lock:
            self._windows.clear()
            logger.info("Reset all rate limits")

    async def _cleanup_loop(self):
        """Background task to clean up old entries."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_old_entries()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in rate limiter cleanup: {e}")

    async def _cleanup_old_entries(self):
        """Remove entries older than 1 hour to prevent memory growth."""
        current_time = time.time()
        cutoff_time = current_time - 3600  # 1 hour
        cleaned = 0

        with self._lock:
            for key in list(self._windows.keys()):
                window = self._windows[key]

                # Remove old entries
                initial_len = len(window)
                while window and window[0] < cutoff_time:
                    window.popleft()

                # Remove empty windows
                if not window:
                    del self._windows[key]
                    cleaned += 1
                elif initial_len > len(window):
                    cleaned += 1

        if cleaned > 0:
            logger.debug(f"Cleaned up {cleaned} rate limiter entries")

    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        with self._lock:
            total_keys = len(self._windows)
            total_requests = sum(len(window) for window in self._windows.values())

            return {
                "total_keys": total_keys,
                "total_requests": total_requests,
                "average_requests_per_key": total_requests / max(1, total_keys),
            }


class GeminiRateLimiter:
    """
    Specialized rate limiter for Gemini API calls.

    Tracks both per-minute (RPM) and per-day (RPD) limits.
    """

    def __init__(self):
        """Initialize the Gemini rate limiter."""
        self._rpm_limiter = InMemoryRateLimiter()
        self._rpd_limiter = InMemoryRateLimiter()

    async def start(self):
        """Start the rate limiters."""
        await self._rpm_limiter.start()
        await self._rpd_limiter.start()

    async def stop(self):
        """Stop the rate limiters."""
        await self._rpm_limiter.stop()
        await self._rpd_limiter.stop()

    async def check_limits(
        self,
        user_id: str,
        model: str,
        rpm_limit: int,
        rpd_limit: int,
        safety_margin: float = 0.2,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check both RPM and RPD limits for a Gemini API call.

        Args:
            user_id: User identifier
            model: Model name (e.g., "gemini-flash", "gemini-pro")
            rpm_limit: Requests per minute limit
            rpd_limit: Requests per day limit
            safety_margin: Reserve percentage

        Returns:
            Tuple of (allowed, limit_info)
        """
        # Check per-minute limit
        rpm_key = f"{user_id}:{model}:rpm"
        (
            rpm_allowed,
            rpm_remaining,
            rpm_reset,
        ) = await self._rpm_limiter.check_rate_limit(
            rpm_key, rpm_limit, 60, safety_margin
        )

        # Check per-day limit
        rpd_key = f"{user_id}:{model}:rpd"
        (
            rpd_allowed,
            rpd_remaining,
            rpd_reset,
        ) = await self._rpd_limiter.check_rate_limit(
            rpd_key, rpd_limit, 86400, safety_margin
        )

        # Both limits must pass
        allowed = rpm_allowed and rpd_allowed

        limit_info = {
            "allowed": allowed,
            "rpm": {
                "limit": rpm_limit,
                "remaining": rpm_remaining if rpm_allowed else 0,
                "reset_seconds": rpm_reset,
            },
            "rpd": {
                "limit": rpd_limit,
                "remaining": rpd_remaining if rpd_allowed else 0,
                "reset_seconds": rpd_reset,
            },
            "limiting_factor": (
                "rpm" if not rpm_allowed else ("rpd" if not rpd_allowed else None)
            ),
        }

        return allowed, limit_info

    async def get_usage(self, user_id: str, model: str) -> Dict[str, Any]:
        """Get usage statistics for a user and model."""
        rpm_key = f"{user_id}:{model}:rpm"
        rpd_key = f"{user_id}:{model}:rpd"

        rpm_usage = await self._rpm_limiter.get_usage(rpm_key, 60)
        rpd_usage = await self._rpd_limiter.get_usage(rpd_key, 86400)

        return {"model": model, "rpm_usage": rpm_usage, "rpd_usage": rpd_usage}


# Global singleton instances
_rate_limiter: Optional[InMemoryRateLimiter] = None
_gemini_limiter: Optional[GeminiRateLimiter] = None


def get_rate_limiter() -> InMemoryRateLimiter:
    """Get or create the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = InMemoryRateLimiter()
    return _rate_limiter


def get_gemini_limiter() -> GeminiRateLimiter:
    """Get or create the global Gemini rate limiter instance."""
    global _gemini_limiter
    if _gemini_limiter is None:
        _gemini_limiter = GeminiRateLimiter()
    return _gemini_limiter
