"""
Circuit breaker implementation for rate limiting system.

Provides protection against cascading failures by temporarily blocking
requests when failure rates exceed thresholds.
"""

import asyncio
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional, Dict

from app.core.logging_config import get_logger
from .exceptions import CircuitBreakerOpenException
from .schemas import CircuitState, CircuitBreakerStatus


class CircuitBreaker:
    """
    Circuit breaker implementation with three states:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failure threshold exceeded, requests blocked
    - HALF_OPEN: Testing if service recovered, limited requests allowed
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        success_threshold: int = 3,
        name: str = "circuit_breaker"
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout_seconds: Time to wait before attempting recovery
            success_threshold: Successes needed to close circuit in HALF_OPEN
            name: Name for logging and identification
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.success_threshold = success_threshold
        self.name = name
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.next_attempt_time: Optional[datetime] = None
        
        self._lock = asyncio.Lock()
        self.logger = get_logger(f"circuit_breaker_{name}")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function call with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenException: If circuit is open
        """
        async with self._lock:
            await self._update_state()
            
            if self.state == CircuitState.OPEN:
                self.logger.warning(f"Circuit breaker {self.name} is OPEN, blocking request")
                raise CircuitBreakerOpenException(
                    f"Circuit breaker {self.name} is open",
                    estimated_recovery=self.next_attempt_time,
                    failure_count=self.failure_count
                )
        
        try:
            # Execute the function
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            await self._on_success()
            return result
            
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _update_state(self) -> None:
        """Update circuit breaker state based on current conditions."""
        now = datetime.utcnow()
        
        if self.state == CircuitState.OPEN:
            if self.next_attempt_time and now >= self.next_attempt_time:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                self.logger.info(f"Circuit breaker {self.name} transitioning to HALF_OPEN")
    
    async def _on_success(self) -> None:
        """Handle successful function execution."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                self.logger.debug(f"Circuit breaker {self.name} success count: {self.success_count}")
                
                if self.success_count >= self.success_threshold:
                    self._close_circuit()
            elif self.state == CircuitState.CLOSED:
                # Reset failure count on successful request
                self.failure_count = 0
    
    async def _on_failure(self) -> None:
        """Handle failed function execution."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.utcnow()
            
            self.logger.warning(f"Circuit breaker {self.name} failure count: {self.failure_count}")
            
            if self.state == CircuitState.HALF_OPEN:
                # Any failure in HALF_OPEN state opens the circuit again
                self._open_circuit()
            elif self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
                # Failure threshold exceeded, open the circuit
                self._open_circuit()
    
    def _open_circuit(self) -> None:
        """Open the circuit breaker."""
        self.state = CircuitState.OPEN
        self.next_attempt_time = datetime.utcnow() + timedelta(seconds=self.timeout_seconds)
        self.logger.error(
            f"Circuit breaker {self.name} OPENED after {self.failure_count} failures. "
            f"Next attempt at {self.next_attempt_time}"
        )
    
    def _close_circuit(self) -> None:
        """Close the circuit breaker."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.next_attempt_time = None
        self.logger.info(f"Circuit breaker {self.name} CLOSED - service recovered")
    
    async def get_status(self) -> CircuitBreakerStatus:
        """
        Get current circuit breaker status.
        
        Returns:
            CircuitBreakerStatus with current state information
        """
        async with self._lock:
            await self._update_state()
            
            return CircuitBreakerStatus(
                state=self.state,
                failure_count=self.failure_count,
                success_count=self.success_count,
                last_failure_time=self.last_failure_time,
                next_attempt_time=self.next_attempt_time
            )
    
    async def force_open(self) -> None:
        """Force the circuit breaker open (for testing/emergency)."""
        async with self._lock:
            self._open_circuit()
            self.logger.warning(f"Circuit breaker {self.name} forced OPEN")
    
    async def force_close(self) -> None:
        """Force the circuit breaker closed (for testing/recovery)."""
        async with self._lock:
            self._close_circuit()
            self.logger.info(f"Circuit breaker {self.name} forced CLOSED")
    
    async def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        async with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
            self.next_attempt_time = None
            self.logger.info(f"Circuit breaker {self.name} reset to CLOSED state")
    
    def __str__(self) -> str:
        """String representation of circuit breaker."""
        return (
            f"CircuitBreaker({self.name}, state={self.state}, "
            f"failures={self.failure_count}/{self.failure_threshold})"
        )