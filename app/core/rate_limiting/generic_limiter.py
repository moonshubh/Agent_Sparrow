"""
Generic rate limiter for non-Gemini models.

This module provides a generic rate limiting wrapper that can be applied
to any LangChain-compatible model, including OpenRouter models like Kimi K2.
"""

import asyncio
import time
from typing import Any, Dict, Optional
from collections import defaultdict
from datetime import datetime, timedelta

from app.core.logging_config import get_logger
from .exceptions import RateLimitExceededException

logger = get_logger(__name__)


class GenericRateLimiter:
    """
    Generic rate limiter that can be applied to any model.
    
    Features:
    - Token bucket algorithm for rate limiting
    - Configurable requests per minute and tokens per minute
    - Thread-safe implementation
    - Graceful degradation on failures
    """
    
    def __init__(
        self,
        model_name: str,
        requests_per_minute: int = 60,
        tokens_per_minute: int = 60000,
        burst_size: int = 10
    ):
        """
        Initialize the generic rate limiter.
        
        Args:
            model_name: Name of the model for logging
            requests_per_minute: Maximum requests per minute
            tokens_per_minute: Maximum tokens per minute
            burst_size: Maximum burst size for requests
        """
        self.model_name = model_name
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute
        self.burst_size = burst_size
        
        # Token buckets for rate limiting
        self._request_bucket = TokenBucket(
            capacity=burst_size,
            refill_rate=requests_per_minute / 60.0
        )
        self._token_bucket = TokenBucket(
            capacity=tokens_per_minute // 10,  # Allow 10% burst
            refill_rate=tokens_per_minute / 60.0
        )
        
        # Usage tracking
        self._request_count = 0
        self._token_count = 0
        self._last_reset = datetime.now()
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
    
    async def check_rate_limit(self, estimated_tokens: int = 1000) -> bool:
        """
        Check if a request can proceed under rate limits.
        
        Args:
            estimated_tokens: Estimated number of tokens for the request
            
        Returns:
            True if request can proceed, False otherwise
        """
        async with self._lock:
            # Check request rate limit
            if not await self._request_bucket.consume(1):
                logger.warning(f"Request rate limit exceeded for {self.model_name}")
                return False
            
            # Check token rate limit
            if not await self._token_bucket.consume(estimated_tokens):
                logger.warning(f"Token rate limit exceeded for {self.model_name}")
                # Return the request token since we're not proceeding
                await self._request_bucket.add(1)
                return False
            
            # Track usage
            self._request_count += 1
            self._token_count += estimated_tokens
            
            return True
    
    def get_retry_after(self) -> float:
        """
        Get the recommended retry after time in seconds.
        
        Returns:
            Number of seconds to wait before retrying
        """
        # Simple implementation: wait for bucket to refill
        return max(
            self._request_bucket.time_until_tokens(1),
            self._token_bucket.time_until_tokens(1000)
        )
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get current usage statistics.
        
        Returns:
            Dictionary with usage stats
        """
        now = datetime.now()
        elapsed = (now - self._last_reset).total_seconds()
        
        return {
            "model": self.model_name,
            "requests": {
                "count": self._request_count,
                "rate": self._request_count / elapsed * 60 if elapsed > 0 else 0,
                "limit": self.requests_per_minute,
                "available": self._request_bucket.available_tokens()
            },
            "tokens": {
                "count": self._token_count,
                "rate": self._token_count / elapsed * 60 if elapsed > 0 else 0,
                "limit": self.tokens_per_minute,
                "available": self._token_bucket.available_tokens()
            },
            "uptime_seconds": elapsed
        }


class TokenBucket:
    """
    Token bucket implementation for rate limiting.
    
    Thread-safe token bucket that refills at a constant rate.
    """
    
    def __init__(self, capacity: float, refill_rate: float):
        """
        Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._tokens = capacity
        self._last_refill = time.monotonic()
    
    async def consume(self, tokens: float) -> bool:
        """
        Try to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        self._refill()
        
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False
    
    async def add(self, tokens: float):
        """
        Add tokens back to the bucket (e.g., for returned requests).
        
        Args:
            tokens: Number of tokens to add
        """
        self._tokens = min(self._tokens + tokens, self.capacity)
    
    def available_tokens(self) -> float:
        """Get the number of available tokens."""
        self._refill()
        return self._tokens
    
    def time_until_tokens(self, tokens: float) -> float:
        """
        Calculate time until enough tokens are available.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Seconds until tokens are available
        """
        self._refill()
        
        if self._tokens >= tokens:
            return 0.0
        
        needed = tokens - self._tokens
        return needed / self.refill_rate
    
    def _refill(self):
        """Refill the bucket based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        
        if elapsed > 0:
            new_tokens = elapsed * self.refill_rate
            self._tokens = min(self._tokens + new_tokens, self.capacity)
            self._last_refill = now


class RateLimitedModelWrapper:
    """
    Wrapper that adds rate limiting to any LangChain model.
    
    This wrapper intercepts calls to the model and applies rate limiting
    before allowing the request to proceed.
    """
    
    def __init__(
        self,
        model: Any,
        rate_limiter: GenericRateLimiter,
        fail_gracefully: bool = True
    ):
        """
        Initialize the rate-limited model wrapper.
        
        Args:
            model: The underlying model to wrap
            rate_limiter: The rate limiter to use
            fail_gracefully: Whether to return errors instead of raising
        """
        self.model = model
        self.rate_limiter = rate_limiter
        self.fail_gracefully = fail_gracefully
        self.logger = get_logger(f"rate_limited_{rate_limiter.model_name}")
        
        # Preserve model attributes
        for attr in dir(model):
            if not attr.startswith('_') and not hasattr(self, attr):
                setattr(self, attr, getattr(model, attr))
    
    async def invoke(self, *args, **kwargs) -> Any:
        """Rate-limited invoke method."""
        # Estimate tokens (simple heuristic)
        estimated_tokens = self._estimate_tokens(args, kwargs)
        
        if not await self.rate_limiter.check_rate_limit(estimated_tokens):
            retry_after = self.rate_limiter.get_retry_after()
            
            if self.fail_gracefully:
                return self._create_error_response(
                    f"Rate limit exceeded. Please retry after {retry_after:.1f} seconds."
                )
            
            raise RateLimitExceededException(
                message=f"Rate limit exceeded for {self.rate_limiter.model_name}",
                retry_after=retry_after,
                limits=self.rate_limiter.get_usage_stats(),
                model=self.rate_limiter.model_name
            )
        
        # Proceed with the actual call
        return await self.model.invoke(*args, **kwargs)
    
    def stream(self, *args, **kwargs) -> Any:
        """Rate-limited streaming method."""
        # For sync streaming, we do a simple check
        estimated_tokens = self._estimate_tokens(args, kwargs)
        
        # Run async check in sync context
        loop = asyncio.new_event_loop()
        try:
            can_proceed = loop.run_until_complete(
                self.rate_limiter.check_rate_limit(estimated_tokens)
            )
        finally:
            loop.close()
        
        if not can_proceed:
            retry_after = self.rate_limiter.get_retry_after()
            
            if self.fail_gracefully:
                yield self._create_error_response(
                    f"Rate limit exceeded. Please retry after {retry_after:.1f} seconds."
                )
                return
            
            raise RateLimitExceededException(
                message=f"Rate limit exceeded for {self.rate_limiter.model_name}",
                retry_after=retry_after,
                limits=self.rate_limiter.get_usage_stats(),
                model=self.rate_limiter.model_name
            )
        
        # Proceed with streaming
        yield from self.model.stream(*args, **kwargs)
    
    async def astream(self, *args, **kwargs) -> Any:
        """Rate-limited async streaming method."""
        estimated_tokens = self._estimate_tokens(args, kwargs)
        
        if not await self.rate_limiter.check_rate_limit(estimated_tokens):
            retry_after = self.rate_limiter.get_retry_after()
            
            if self.fail_gracefully:
                yield self._create_error_response(
                    f"Rate limit exceeded. Please retry after {retry_after:.1f} seconds."
                )
                return
            
            raise RateLimitExceededException(
                message=f"Rate limit exceeded for {self.rate_limiter.model_name}",
                retry_after=retry_after,
                limits=self.rate_limiter.get_usage_stats(),
                model=self.rate_limiter.model_name
            )
        
        # Proceed with async streaming
        async for chunk in self.model.astream(*args, **kwargs):
            yield chunk
    
    def _estimate_tokens(self, args: tuple, kwargs: dict) -> int:
        """
        Estimate the number of tokens for a request.
        
        This is a simple heuristic based on message length.
        """
        # Extract messages if available
        messages = None
        if args and hasattr(args[0], '__iter__'):
            messages = args[0]
        elif 'messages' in kwargs:
            messages = kwargs['messages']
        
        if not messages:
            return 1000  # Default estimate
        
        # Simple estimation: ~4 characters per token
        total_chars = sum(
            len(str(msg.content)) if hasattr(msg, 'content') else len(str(msg))
            for msg in messages
        )
        
        # Add some buffer for response tokens
        estimated_input = total_chars // 4
        estimated_output = 1000  # Assume 1000 tokens for response
        
        return estimated_input + estimated_output
    
    def _create_error_response(self, message: str) -> Dict[str, Any]:
        """Create an error response for graceful failure."""
        return {
            "error": True,
            "message": message,
            "model": self.rate_limiter.model_name,
            "usage_stats": self.rate_limiter.get_usage_stats()
        }
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get rate limiter usage statistics."""
        return self.rate_limiter.get_usage_stats()


# Factory function to create rate-limited models
def create_rate_limited_model(
    model: Any,
    model_name: str,
    requests_per_minute: int = 60,
    tokens_per_minute: int = 60000,
    fail_gracefully: bool = True
) -> RateLimitedModelWrapper:
    """
    Create a rate-limited wrapper for any model.
    
    Args:
        model: The model to wrap
        model_name: Name of the model for logging
        requests_per_minute: Request rate limit
        tokens_per_minute: Token rate limit
        fail_gracefully: Whether to return errors instead of raising
        
    Returns:
        Rate-limited model wrapper
    """
    rate_limiter = GenericRateLimiter(
        model_name=model_name,
        requests_per_minute=requests_per_minute,
        tokens_per_minute=tokens_per_minute
    )
    
    return RateLimitedModelWrapper(
        model=model,
        rate_limiter=rate_limiter,
        fail_gracefully=fail_gracefully
    )