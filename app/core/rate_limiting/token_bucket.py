"""
Token bucket algorithm implementation for rate limiting.

The token bucket algorithm allows for burst requests while maintaining
an average rate limit over time.
"""

import time
import asyncio
from typing import Optional


class TokenBucket:
    """
    Token bucket rate limiter implementation.

    The token bucket algorithm:
    1. Maintains a bucket with a fixed capacity
    2. Tokens are added to the bucket at a fixed rate
    3. Each request consumes one or more tokens
    4. Requests are allowed if enough tokens are available
    5. Allows bursts up to the bucket capacity
    """

    def __init__(
        self, capacity: int, refill_rate: float, burst_capacity: Optional[int] = None
    ):
        """
        Initialize the token bucket.

        Args:
            capacity: Maximum number of tokens the bucket can hold
            refill_rate: Rate at which tokens are added (tokens per second)
            burst_capacity: Optional burst capacity (defaults to capacity)

        Raises:
            ValueError: If capacity <= 0 or refill_rate <= 0
        """
        if capacity <= 0:
            raise ValueError("Capacity must be positive")
        if refill_rate <= 0:
            raise ValueError("Refill rate must be positive")

        self.capacity = capacity
        self.refill_rate = refill_rate
        self.burst_capacity = burst_capacity or capacity

        # Start with full capacity (or burst capacity)
        self.tokens = float(self.burst_capacity)
        self.last_refill = time.time()

        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if not enough tokens available
        """
        async with self._lock:
            await self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    async def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill

        if elapsed > 0:
            # Add tokens based on elapsed time
            tokens_to_add = elapsed * self.refill_rate
            self.tokens = min(self.burst_capacity, self.tokens + tokens_to_add)

            self.last_refill = now

    async def get_current_tokens(self) -> float:
        """
        Get the current number of tokens available.

        Returns:
            Current token count after refill
        """
        async with self._lock:
            await self._refill()
            return self.tokens

    async def time_until_tokens_available(self, required_tokens: int) -> float:
        """
        Calculate time until required tokens are available.

        Args:
            required_tokens: Number of tokens needed

        Returns:
            Time in seconds until tokens are available (0 if already available)
        """
        async with self._lock:
            await self._refill()

            if self.tokens >= required_tokens:
                return 0.0

            tokens_needed = required_tokens - self.tokens
            return tokens_needed / self.refill_rate

    async def get_metadata(self) -> dict:
        """
        Get metadata about the current bucket state.

        Returns:
            Dictionary with bucket state information
        """
        async with self._lock:
            await self._refill()

            return {
                "capacity": self.capacity,
                "burst_capacity": self.burst_capacity,
                "current_tokens": self.tokens,
                "refill_rate": self.refill_rate,
                "utilization": 1.0 - (self.tokens / self.burst_capacity),
                "last_refill": self.last_refill,
            }

    def __str__(self) -> str:
        """String representation of the bucket."""
        return (
            f"TokenBucket({self.tokens:.1f}/{self.capacity}, "
            f"{self.refill_rate} tokens/sec)"
        )
