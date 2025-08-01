"""
Generic rate limiter for non-Gemini models.

This module provides a generic rate limiting wrapper that can be applied
to any LangChain-compatible model, including OpenRouter models like Kimi K2.
"""

import asyncio
import concurrent.futures
import time
from typing import Any, Dict, Optional
from collections import defaultdict
from datetime import datetime, timedelta

from app.core.logging_config import get_logger
from .exceptions import RateLimitExceededException
from .token_estimation import estimate_tokens

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
        fail_gracefully: bool = True,
        rate_check_timeout: float = 3.0,
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
        # Configurable timeout for rate-limit checks executed via executor
        self._rate_check_timeout = rate_check_timeout
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
        
        # Run async check in sync context using improved loop handling
        try:
            # Try to get existing event loop
            try:
                loop = asyncio.get_running_loop()
                # If we have a running loop, we need to use run_in_executor
                import concurrent.futures
                # Use a shared thread pool executor to prevent resource leaks
                if not hasattr(self, '_executor'):
                    self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                
                future = self._executor.submit(
                    asyncio.run,
                    self.rate_limiter.check_rate_limit(estimated_tokens)
                )
                can_proceed = future.result(timeout=self._rate_check_timeout)
            except RuntimeError:
                # No running event loop, we can use asyncio.run
                can_proceed = asyncio.run(
                    self.rate_limiter.check_rate_limit(estimated_tokens)
                )
        except (asyncio.TimeoutError, concurrent.futures.TimeoutError) as e:
            logger.warning(f"Timeout during rate-limit check: {e}")
            can_proceed = False
        except Exception as e:  # pragma: no cover
            logger.exception("Unexpected error during rate-limit check")
            can_proceed = False
        
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
        Estimate the number of tokens for a request using advanced estimation service.
        
        Uses model-specific tokenization with configurable parameters and caching.
        """
        try:
            # Get model name from various sources
            model_name = self._extract_model_name(args, kwargs)
            
            # Use advanced token estimation
            return estimate_tokens(
                args=args,
                kwargs=kwargs, 
                model_name=model_name,
                include_context=True
            )
            
        except Exception as e:
            logger.warning(f"Advanced token estimation failed, using fallback: {e}")
            return self._fallback_token_estimation(args, kwargs)
    
    def _extract_model_name(self, args: tuple, kwargs: dict) -> Optional[str]:
        """Enhanced model name extraction from request arguments."""
        # Check common parameter names with improved extraction
        for param_name in ['model', 'model_name', 'model_id', 'engine']:
            if param_name in kwargs:
                model_name = str(kwargs[param_name])
                # Clean and normalize model name
                return self._normalize_model_name(model_name)
        
        # Check if model is embedded in the wrapped model object
        if hasattr(self, 'model_name'):
            return self._normalize_model_name(self.model_name)
        
        # Check model attribute on the wrapped model
        if hasattr(self, 'model') and hasattr(self.model, 'model_name'):
            return self._normalize_model_name(self.model.model_name)
        
        # Check for model info in args (first argument might be model config)
        if args and isinstance(args[0], dict) and 'model' in args[0]:
            return self._normalize_model_name(str(args[0]['model']))
            
        return None
    
    def _normalize_model_name(self, model_name: str) -> str:
        """Normalize model name for consistent processing."""
        if not model_name:
            return model_name
        
        # Remove common prefixes/suffixes and normalize
        normalized = model_name.lower().strip()
        
        # Handle common model name variations
        if 'gemini' in normalized:
            if '2.5' in normalized and 'pro' in normalized:
                return 'gemini-2.5-pro'
            elif '2.5' in normalized and 'flash' in normalized:
                return 'gemini-2.5-flash'
        elif 'kimi' in normalized:
            return 'kimi-k2'
        elif 'gpt' in normalized:
            if '4' in normalized:
                return 'gpt-4'
            elif '3.5' in normalized:
                return 'gpt-3.5-turbo'
        
        return normalized
    
    def _fallback_token_estimation(self, args: tuple, kwargs: dict) -> int:
        """Fallback token estimation using simple heuristics."""
        # Extract messages if available (with type safety)
        messages = None
        if args and len(args) > 0 and hasattr(args[0], '__iter__') and not isinstance(args[0], str):
            try:
                messages = list(args[0])  # Convert to list for safety
            except (TypeError, ValueError):
                messages = None
        elif 'messages' in kwargs and isinstance(kwargs['messages'], (list, tuple)):
            messages = kwargs['messages']
        
        if not messages:
            return 1200  # Conservative default estimate
        
        # Simple estimation: ~4 characters per token with overhead (with error handling)
        total_chars = 0
        for msg in messages:
            try:
                if hasattr(msg, 'content') and msg.content is not None:
                    total_chars += len(str(msg.content))
                else:
                    total_chars += len(str(msg)) if msg is not None else 0
            except (AttributeError, TypeError, ValueError):
                # Skip problematic messages and add conservative estimate
                total_chars += 100
        
        # More conservative calculation
        estimated_input = int(total_chars / 3.5)  # Slightly more tokens per char
        estimated_output = 1200  # Higher response estimate
        overhead = 150  # System prompt and formatting overhead
        
        return estimated_input + estimated_output + overhead
    
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
    
    # --------------------------------------------------------------------- #
    # Context manager support for safe executor cleanup                      #
    # --------------------------------------------------------------------- #
    def __enter__(self):
        """Enter the context manager and return self."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure the thread-pool executor is shut down gracefully."""
        if hasattr(self, "_executor") and self._executor:
            try:
                # Wait for running tasks to finish before shutting down
                self._executor.shutdown(wait=True)
            except Exception as e:  # pragma: no cover
                logger.warning("Failed shutting down executor: %s", e)
        # Do not suppress exceptions
        return False


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

    Note:
        The returned object implements the context-manager protocol, so it is
        recommended to use it via `with` for deterministic resource cleanup:

        ```python
        with create_rate_limited_model(model, "my-model") as limited:
            limited.invoke(...)
        ```
    
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