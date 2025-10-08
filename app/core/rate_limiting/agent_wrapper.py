"""
Agent wrapper for integrating rate limiting with existing Gemini agents.

Provides decorators and wrapper classes to seamlessly add rate limiting
to existing agent implementations without major code changes.
"""

import asyncio
import functools
from typing import Any, Callable, Optional, Union, TypeVar, Dict
from langchain_core.messages import BaseMessage

from app.core.logging_config import get_logger
from .gemini_limiter import GeminiRateLimiter
from .config import RateLimitConfig
from .exceptions import (
    RateLimitExceededException,
    CircuitBreakerOpenException,
    GeminiServiceUnavailableException
)

# Type variable for decorated functions
F = TypeVar('F', bound=Callable[..., Any])

# Global rate limiter instance
_global_rate_limiter: Optional[GeminiRateLimiter] = None


def get_rate_limiter() -> GeminiRateLimiter:
    """Get or create the global rate limiter instance."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        config = RateLimitConfig.from_environment()
        _global_rate_limiter = GeminiRateLimiter(config)
    return _global_rate_limiter


def rate_limited(model: str, fail_gracefully: bool = False):
    """
    Decorator to add rate limiting to agent functions.
    
    Args:
        model: Gemini model name ("gemini-2.5-flash" or "gemini-2.5-pro")
        fail_gracefully: If True, return None on rate limit instead of raising
        
    Usage:
        @rate_limited("gemini-2.5-flash")
        async def my_agent_function(messages):
            # Agent logic here
            return response
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            limiter = get_rate_limiter()
            logger = get_logger(f"rate_limited_{func.__name__}")
            
            try:
                return await limiter.execute_with_protection(
                    model, func, *args, **kwargs
                )
            except RateLimitExceededException as e:
                logger.warning(f"Rate limit exceeded for {model}: {e.message}")
                if fail_gracefully:
                    return None
                raise
            except CircuitBreakerOpenException as e:
                logger.error(f"Circuit breaker open for {model}: {e.message}")
                if fail_gracefully:
                    return None
                raise
            except Exception as e:
                logger.error(f"Rate limiter error for {model}: {e}")
                if fail_gracefully:
                    return None
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For synchronous functions, handle event loop safely
            try:
                # Check if there is a running event loop
                loop = asyncio.get_running_loop()
                # If running loop exists, we can't use run_until_complete
                import threading
                import concurrent.futures
                
                # Run in thread pool to avoid blocking running event loop
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        lambda: asyncio.run(async_wrapper(*args, **kwargs))
                    )
                    return future.result()
                    
            except RuntimeError:
                # No running event loop, create a new one
                try:
                    loop = asyncio.get_event_loop()
                    return loop.run_until_complete(async_wrapper(*args, **kwargs))
                except RuntimeError:
                    # No event loop in this thread, create new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(async_wrapper(*args, **kwargs))
                    finally:
                        loop.close()
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


class RateLimitedAgent:
    """
    Wrapper class for existing agent implementations.
    
    Provides rate limiting functionality without modifying the original agent.
    """
    
    def __init__(
        self,
        agent: Any,
        model: str,
        fail_gracefully: bool = False,
        rate_limiter: Optional[GeminiRateLimiter] = None
    ):
        """
        Initialize rate limited agent wrapper.
        
        Args:
            agent: Original agent instance
            model: Gemini model name
            fail_gracefully: If True, return errors instead of raising
            rate_limiter: Optional rate limiter instance
        """
        self.agent = agent
        self.model = model
        self.fail_gracefully = fail_gracefully
        self.rate_limiter = rate_limiter or get_rate_limiter()
        self.logger = get_logger(f"rate_limited_agent_{model}")
        
        # Preserve original agent attributes
        for attr in dir(agent):
            if not attr.startswith('_') and not hasattr(self, attr):
                setattr(self, attr, getattr(agent, attr))
    
    async def invoke(self, *args, **kwargs) -> Any:
        """
        Rate-limited invoke method.
        
        This method wraps the original agent's invoke method with rate limiting.
        """
        try:
            # Check if original agent has invoke method
            if hasattr(self.agent, 'invoke'):
                return await self.rate_limiter.execute_with_protection(
                    self.model, self.agent.invoke, *args, **kwargs
                )
            else:
                raise AttributeError(f"Agent {self.agent} does not have invoke method")
                
        except RateLimitExceededException as e:
            self.logger.warning(f"Rate limit exceeded: {e.message}")
            if self.fail_gracefully:
                return self._create_error_response(e)
            raise
        except CircuitBreakerOpenException as e:
            self.logger.error(f"Circuit breaker open: {e.message}")
            if self.fail_gracefully:
                return self._create_error_response(e)
            raise
        except Exception as e:
            self.logger.error(f"Agent execution failed: {e}")
            raise
    
    async def ainvoke(self, *args, **kwargs) -> Any:
        """Alias for invoke method (LangChain compatibility)."""
        return await self.invoke(*args, **kwargs)
    
    def stream(self, *args, **kwargs) -> Any:
        """
        Rate-limited streaming method (synchronous).
        
        For sync streaming, we check rate limits synchronously before streaming.
        """
        self.logger.info(f"rate_limit_wrapper_stream_called model={self.model}")
        
        try:
            # Check rate limits synchronously before streaming
            import asyncio
            try:
                # First try to get the current running event loop
                loop = asyncio.get_running_loop()
                # If we have a running loop, we need to handle this differently
                # For now, we'll skip rate limiting check in stream to avoid blocking
                self.logger.warning("Running event loop detected, skipping sync rate limit check")
                
            except RuntimeError:
                # No running event loop, safe to get or create one
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            
            # Check rate limits before streaming
            # Only run rate check if we have a usable loop (not running)
            if 'loop' in locals():
                rate_check = loop.run_until_complete(self.rate_limiter.check_and_consume(self.model))
            else:
                rate_check = None
            if rate_check is not None and not rate_check.allowed:
                self.logger.warning(f"Rate limit exceeded for {self.model}")
                if self.fail_gracefully:
                    return self._create_error_stream_sync(
                        RateLimitExceededException(
                            message=f"Rate limit exceeded for {self.model}",
                            retry_after=rate_check.retry_after,
                            limits=rate_check.metadata.dict(),
                            model=self.model
                        )
                    )
                raise RateLimitExceededException(
                    message=f"Rate limit exceeded for {self.model}",
                    retry_after=rate_check.retry_after,
                    limits=rate_check.metadata.dict(),
                    model=self.model
                )
            
            self.logger.info("rate_limit_check_passed proceeding_with_stream")
            
        except Exception as e:
            self.logger.error(f"Rate limiting error in stream: {e}")
            # Continue without rate limiting on error to maintain functionality
        
        # Stream with circuit breaker protection
        if hasattr(self.agent, 'stream'):
            try:
                circuit_breaker = self.rate_limiter.circuit_breakers[self.model]
                return circuit_breaker.call_sync(self.agent.stream, *args, **kwargs)
            except Exception as e:
                self.logger.error(f"Circuit breaker error in stream: {e}")
                # Fallback to direct stream call
                return self.agent.stream(*args, **kwargs)
        else:
            raise AttributeError(f"Agent {self.agent} does not have stream method")

    async def astream(self, *args, **kwargs) -> Any:
        """
        Rate-limited async streaming method.
        
        For streaming responses, we check rate limits before starting the stream.
        """
        try:
            # Check rate limits first
            rate_check = await self.rate_limiter.check_and_consume(self.model)
            if rate_check is not None and not rate_check.allowed:
                raise RateLimitExceededException(
                    message=f"Rate limit exceeded for {self.model}",
                    retry_after=rate_check.retry_after,
                    limits=rate_check.metadata.dict(),
                    model=self.model
                )
            
            # Stream with circuit breaker protection
            if hasattr(self.agent, 'astream'):
                circuit_breaker = self.rate_limiter.circuit_breakers[self.model]
                return await circuit_breaker.call(self.agent.astream, *args, **kwargs)
            elif hasattr(self.agent, 'stream'):
                # Fallback to sync stream
                circuit_breaker = self.rate_limiter.circuit_breakers[self.model]
                return await circuit_breaker.call_sync(self.agent.stream, *args, **kwargs)
            else:
                raise AttributeError(f"Agent {self.agent} does not have stream method")
                
        except RateLimitExceededException as e:
            self.logger.warning(f"Async streaming rate limit exceeded: {e.message}")
            if self.fail_gracefully:
                return self._create_error_stream(e)
            raise
        except CircuitBreakerOpenException as e:
            self.logger.error(f"Async streaming circuit breaker open: {e.message}")
            if self.fail_gracefully:
                return self._create_error_stream(e)
            raise
    
    def _create_error_response(self, error: Exception) -> Dict[str, Any]:
        """Create error response for graceful failure mode."""
        return {
            "error": True,
            "error_type": type(error).__name__,
            "message": str(error),
            "model": self.model
        }
    
    async def _create_error_stream(self, error: Exception):
        """Create error stream for graceful failure mode."""
        error_response = self._create_error_response(error)
        yield error_response
    
    def _create_error_stream_sync(self, error: Exception):
        """Create error stream for graceful failure mode (synchronous)."""
        error_response = self._create_error_response(error)
        yield error_response
    
    async def get_usage_stats(self) -> Dict[str, Any]:
        """Get rate limiting usage statistics."""
        stats = await self.rate_limiter.get_usage_stats()
        return stats.dict()
    
    async def health_check(self) -> Dict[str, Any]:
        """Check agent and rate limiter health."""
        health = await self.rate_limiter.health_check()
        health["agent_model"] = self.model
        health["fail_gracefully"] = self.fail_gracefully
        return health


class ChatGoogleGenerativeAIWrapper(RateLimitedAgent):
    """
    Specific wrapper for ChatGoogleGenerativeAI instances.
    
    Provides compatibility with LangChain's ChatGoogleGenerativeAI interface.
    """
    
    def __init__(
        self,
        chat_model: Any,
        model_name: str,
        fail_gracefully: bool = False
    ):
        """
        Initialize ChatGoogleGenerativeAI wrapper.
        
        Args:
            chat_model: Original ChatGoogleGenerativeAI instance
            model_name: Model name for rate limiting
            fail_gracefully: Graceful failure mode
        """
        super().__init__(chat_model, model_name, fail_gracefully)
        
        # Preserve LangChain-specific attributes
        self.model_name = model_name
        self.temperature = getattr(chat_model, 'temperature', 0)
        self.max_tokens = getattr(chat_model, 'max_tokens', None)
    
    async def _call(self, messages: list, **kwargs) -> str:
        """LangChain _call method compatibility."""
        response = await self.invoke(messages, **kwargs)
        if isinstance(response, dict) and response.get("error"):
            # Return error message if in graceful mode
            return f"Error: {response['message']}"
        return response.content if hasattr(response, 'content') else str(response)
    
    async def _acall(self, messages: list, **kwargs) -> str:
        """LangChain async _call method compatibility."""
        return await self._call(messages, **kwargs)


def wrap_gemini_agent(agent: Any, model: str, **kwargs) -> RateLimitedAgent:
    """
    Factory function to wrap any Gemini agent with rate limiting.
    
    Args:
        agent: Agent instance to wrap
        model: Gemini model name
        **kwargs: Additional arguments for RateLimitedAgent
        
    Returns:
        Rate-limited agent wrapper
    """
    # Detect agent type and use appropriate wrapper
    agent_class_name = agent.__class__.__name__
    
    if agent_class_name == "ChatGoogleGenerativeAI":
        return ChatGoogleGenerativeAIWrapper(agent, model, **kwargs)
    else:
        return RateLimitedAgent(agent, model, **kwargs)


async def cleanup_rate_limiter():
    """Cleanup global rate limiter resources."""
    global _global_rate_limiter
    if _global_rate_limiter:
        await _global_rate_limiter.close()
        _global_rate_limiter = None