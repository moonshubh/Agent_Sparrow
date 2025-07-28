"""
Exception hierarchy for MB-Sparrow Primary Agent.

This module provides a comprehensive exception system for handling various error
scenarios in the primary agent, with user-friendly messages and recovery suggestions.

Design Principles:
- All exceptions inherit from AgentException base class
- Each exception provides a user-friendly message via user_message() method
- Technical details are preserved for logging
- Recovery suggestions are included where applicable
- Exceptions are serializable for API responses

Author: MB-Sparrow Team
Version: 1.0.0
"""

import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from enum import Enum
from urllib.parse import urlparse


class ErrorSeverity(Enum):
    """Severity levels for exceptions."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentException(Exception):
    """
    Base exception class for all primary agent exceptions.
    
    Provides a consistent interface for error handling with user-friendly
    messages and recovery suggestions.
    
    Attributes:
        message: Technical error message for logging
        user_facing_message: User-friendly error message
        recovery_suggestions: List of suggested actions for recovery
        severity: Error severity level
        error_code: Unique error code for tracking
        metadata: Additional error context
    """
    
    def __init__(
        self,
        message: str,
        user_facing_message: Optional[str] = None,
        recovery_suggestions: Optional[List[str]] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        error_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the AgentException.
        
        Args:
            message: Technical error message
            user_facing_message: User-friendly message (defaults to message)
            recovery_suggestions: List of recovery actions
            severity: Error severity level
            error_code: Unique error identifier
            metadata: Additional context information
        """
        super().__init__(message)
        self.message = message
        self.user_facing_message = user_facing_message or message
        self.recovery_suggestions = recovery_suggestions or []
        self.severity = severity
        self.error_code = error_code or self.__class__.__name__
        self.metadata = metadata or {}
        self.timestamp = datetime.now(timezone.utc)
        
    def user_message(self) -> str:
        """
        Get the user-friendly error message.
        
        Returns:
            User-friendly error message suitable for display
        """
        return self.user_facing_message
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert exception to dictionary for API responses.
        
        Returns:
            Dictionary representation of the exception
        """
        return {
            "error": self.error_code,
            "message": self.user_facing_message,
            "technical_message": self.message,
            "severity": self.severity.value,
            "recovery_suggestions": self.recovery_suggestions,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }
    
    def __str__(self) -> str:
        """String representation for logging."""
        return f"{self.error_code}: {self.message}"


class RateLimitException(AgentException):
    """
    Raised when rate limits are exceeded.
    
    Includes retry information and current usage statistics.
    """
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        limit_type: Optional[str] = None,
        current_usage: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Initialize RateLimitException.
        
        Args:
            message: Technical error message
            retry_after: Seconds until retry is allowed
            limit_type: Type of limit exceeded (e.g., 'api_calls', 'tokens')
            current_usage: Current usage statistics
            **kwargs: Additional arguments for AgentException
        """
        self.retry_after = retry_after
        self.limit_type = limit_type or "requests"
        self.current_usage = current_usage or {}
        
        user_message = (
            f"I've reached my {limit_type} limit for now. "
            f"Please try again in {retry_after or 60} seconds."
        )
        
        recovery = [
            f"Wait {retry_after or 60} seconds before retrying",
            "Consider breaking your request into smaller parts",
            "Try again during off-peak hours for better availability"
        ]
        
        metadata = {
            "retry_after": retry_after,
            "limit_type": limit_type,
            "usage": current_usage
        }
        
        super().__init__(
            message=message,
            user_facing_message=user_message,
            recovery_suggestions=recovery,
            severity=ErrorSeverity.MEDIUM,
            error_code="RATE_LIMIT_EXCEEDED",
            metadata=metadata,
            **kwargs
        )


class InvalidAPIKeyException(AgentException):
    """
    Raised when API key is invalid or malformed.
    
    Provides guidance on proper API key format and setup.
    """
    
    def __init__(
        self,
        message: str = "Invalid API key",
        key_type: str = "Google API",
        expected_format: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize InvalidAPIKeyException.
        
        Args:
            message: Technical error message
            key_type: Type of API key (e.g., 'Google API', 'OpenAI')
            expected_format: Expected format description
            **kwargs: Additional arguments for AgentException
        """
        self.key_type = key_type
        self.expected_format = expected_format
        
        user_message = (
            f"The {key_type} key appears to be invalid. "
            "Please check your API key configuration."
        )
        
        recovery = [
            f"Verify your {key_type} key is correct",
            "Check that the key hasn't expired",
            "Ensure the key has proper permissions enabled"
        ]
        
        if expected_format:
            recovery.append(f"Expected format: {expected_format}")
        
        metadata = {
            "key_type": key_type,
            "expected_format": expected_format
        }
        
        super().__init__(
            message=message,
            user_facing_message=user_message,
            recovery_suggestions=recovery,
            severity=ErrorSeverity.HIGH,
            error_code="INVALID_API_KEY",
            metadata=metadata,
            **kwargs
        )


class TimeoutException(AgentException):
    """
    Raised when operations exceed time limits.
    
    Includes information about the operation that timed out.
    """
    
    def __init__(
        self,
        message: str = "Operation timed out",
        operation: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        **kwargs
    ):
        """
        Initialize TimeoutException.
        
        Args:
            message: Technical error message
            operation: Name of the operation that timed out
            timeout_seconds: Timeout duration in seconds
            **kwargs: Additional arguments for AgentException
        """
        self.operation = operation or "operation"
        self.timeout_seconds = timeout_seconds
        
        user_message = (
            f"The {self.operation} is taking longer than expected. "
            "This might be due to high system load."
        )
        
        recovery = [
            "Try again in a few moments",
            "Simplify your request if possible",
            "Check your internet connection"
        ]
        
        metadata = {
            "operation": operation,
            "timeout_seconds": timeout_seconds
        }
        
        super().__init__(
            message=message,
            user_facing_message=user_message,
            recovery_suggestions=recovery,
            severity=ErrorSeverity.MEDIUM,
            error_code="TIMEOUT",
            metadata=metadata,
            **kwargs
        )


class NetworkException(AgentException):
    """
    Raised when network-related errors occur.
    
    Covers connectivity issues, DNS failures, and API unreachability.
    """
    
    def __init__(
        self,
        message: str = "Network error occurred",
        service: Optional[str] = None,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize NetworkException.
        
        Args:
            message: Technical error message
            service: Service that failed (e.g., 'Google AI', 'Knowledge Base')
            url: URL that failed (sanitized for security)
            status_code: HTTP status code if applicable
            **kwargs: Additional arguments for AgentException
        """
        self.service = service or "external service"
        self.url = url
        self.status_code = status_code
        
        user_message = (
            f"I'm having trouble connecting to {self.service}. "
            "This is usually temporary."
        )
        
        recovery = [
            "Check your internet connection",
            "Try again in a few moments",
            f"The {service} might be experiencing issues"
        ]
        
        metadata = {
            "service": service,
            "status_code": status_code
        }
        
        # Don't include URL in metadata for security - use urllib.parse for safer handling
        if url:
            try:
                parsed_url = urlparse(url)
                # Only include URL if it doesn't contain sensitive parameters
                if not any(sensitive in parsed_url.query.lower() for sensitive in ['key', 'token', 'secret', 'password']):
                    # Sanitize URL by removing query parameters
                    sanitized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                    metadata["url"] = sanitized_url
            except Exception:
                # If URL parsing fails, don't include it
                pass
        
        super().__init__(
            message=message,
            user_facing_message=user_message,
            recovery_suggestions=recovery,
            severity=ErrorSeverity.MEDIUM,
            error_code="NETWORK_ERROR",
            metadata=metadata,
            **kwargs
        )


class ConfigurationException(AgentException):
    """
    Raised when system configuration is invalid or missing.
    
    Helps identify misconfigurations and missing settings.
    """
    
    def __init__(
        self,
        message: str = "Configuration error",
        config_key: Optional[str] = None,
        expected_value: Optional[str] = None,
        actual_value: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize ConfigurationException.
        
        Args:
            message: Technical error message
            config_key: Configuration key that failed
            expected_value: Expected configuration value/format
            actual_value: Actual configuration value (sanitized)
            **kwargs: Additional arguments for AgentException
        """
        self.config_key = config_key
        self.expected_value = expected_value
        self.actual_value = actual_value
        
        user_message = (
            "There's a configuration issue preventing me from completing your request. "
            "An administrator has been notified."
        )
        
        recovery = [
            "This requires administrator attention",
            "Try using a different feature in the meantime",
            "Report this issue with the error code"
        ]
        
        metadata = {
            "config_key": config_key,
            "expected": expected_value
        }
        
        # Sanitize actual value for security
        if actual_value and not any(sensitive in str(config_key or '').lower() 
                                   for sensitive in ['key', 'token', 'secret', 'password']):
            metadata["actual"] = actual_value
        
        super().__init__(
            message=message,
            user_facing_message=user_message,
            recovery_suggestions=recovery,
            severity=ErrorSeverity.HIGH,
            error_code="CONFIG_ERROR",
            metadata=metadata,
            **kwargs
        )


class KnowledgeBaseException(AgentException):
    """
    Raised when knowledge base operations fail.
    
    Covers search failures, connection issues, and data problems.
    """
    
    def __init__(
        self,
        message: str = "Knowledge base error",
        operation: Optional[str] = None,
        query: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize KnowledgeBaseException.
        
        Args:
            message: Technical error message
            operation: KB operation that failed (e.g., 'search', 'retrieve')
            query: Query that caused the error (sanitized)
            **kwargs: Additional arguments for AgentException
        """
        self.operation = operation or "access"
        self.query = query
        
        user_message = (
            f"I'm having trouble accessing my knowledge base to {self.operation} information. "
            "I'll try to help with what I know."
        )
        
        recovery = [
            "I'll use my general knowledge to help",
            "Try rephrasing your question",
            "The knowledge base will be available again soon"
        ]
        
        metadata = {
            "operation": operation,
            "query_length": len(query) if query else 0
        }
        
        super().__init__(
            message=message,
            user_facing_message=user_message,
            recovery_suggestions=recovery,
            severity=ErrorSeverity.MEDIUM,
            error_code="KB_ERROR",
            metadata=metadata,
            **kwargs
        )


class ToolExecutionException(AgentException):
    """
    Raised when tool execution fails.
    
    Provides information about which tool failed and why.
    """
    
    def __init__(
        self,
        message: str = "Tool execution failed",
        tool_name: Optional[str] = None,
        tool_error: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize ToolExecutionException.
        
        Args:
            message: Technical error message
            tool_name: Name of the tool that failed
            tool_error: Specific error from the tool
            **kwargs: Additional arguments for AgentException
        """
        self.tool_name = tool_name or "tool"
        self.tool_error = tool_error
        
        user_message = (
            f"I encountered an issue while using the {self.tool_name}. "
            "Let me try a different approach."
        )
        
        recovery = [
            "I'll attempt an alternative method",
            "Try simplifying your request",
            "Some features may be temporarily limited"
        ]
        
        metadata = {
            "tool_name": tool_name,
            "tool_error": tool_error
        }
        
        super().__init__(
            message=message,
            user_facing_message=user_message,
            recovery_suggestions=recovery,
            severity=ErrorSeverity.MEDIUM,
            error_code="TOOL_ERROR",
            metadata=metadata,
            **kwargs
        )


class ReasoningException(AgentException):
    """
    Raised when reasoning engine encounters errors.
    
    Indicates problems with query analysis or decision making.
    """
    
    def __init__(
        self,
        message: str = "Reasoning error",
        reasoning_phase: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Initialize ReasoningException.
        
        Args:
            message: Technical error message
            reasoning_phase: Phase where error occurred
            context: Reasoning context when error occurred
            **kwargs: Additional arguments for AgentException
        """
        self.reasoning_phase = reasoning_phase
        self.context = context or {}
        
        user_message = (
            "I'm having difficulty understanding your request fully. "
            "Let me try a simpler approach to help you."
        )
        
        recovery = [
            "Try rephrasing your question",
            "Break down complex requests into simpler parts",
            "Provide more specific details"
        ]
        
        metadata = {
            "reasoning_phase": reasoning_phase,
            "context_keys": list(context.keys()) if context else []
        }
        
        super().__init__(
            message=message,
            user_facing_message=user_message,
            recovery_suggestions=recovery,
            severity=ErrorSeverity.MEDIUM,
            error_code="REASONING_ERROR",
            metadata=metadata,
            **kwargs
        )


class ModelOverloadException(AgentException):
    """
    Raised when AI model is overloaded or unavailable.
    
    Provides fallback options and estimated recovery time.
    """
    
    def __init__(
        self,
        message: str = "Model overloaded",
        model_name: Optional[str] = None,
        fallback_available: bool = False,
        estimated_wait: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize ModelOverloadException.
        
        Args:
            message: Technical error message
            model_name: Name of the overloaded model
            fallback_available: Whether a fallback model is available
            estimated_wait: Estimated wait time in seconds
            **kwargs: Additional arguments for AgentException
        """
        self.model_name = model_name or "AI model"
        self.fallback_available = fallback_available
        self.estimated_wait = estimated_wait
        
        user_message = (
            f"The {self.model_name} is currently experiencing high demand. "
        )
        
        if fallback_available:
            user_message += "I'm switching to an alternative model to help you."
        else:
            user_message += f"Please try again in {estimated_wait or 30} seconds."
        
        recovery = []
        if fallback_available:
            recovery.append("Using alternative model with similar capabilities")
        else:
            recovery.extend([
                f"Wait {estimated_wait or 30} seconds before retrying",
                "Try during off-peak hours for faster response",
                "Consider simplifying complex requests"
            ])
        
        metadata = {
            "model_name": model_name,
            "fallback_available": fallback_available,
            "estimated_wait": estimated_wait
        }
        
        super().__init__(
            message=message,
            user_facing_message=user_message,
            recovery_suggestions=recovery,
            severity=ErrorSeverity.HIGH if not fallback_available else ErrorSeverity.MEDIUM,
            error_code="MODEL_OVERLOAD",
            metadata=metadata,
            **kwargs
        )


# Exception factory function for common scenarios
def create_exception_from_error(
    error: Exception,
    context: Optional[Dict[str, Any]] = None
) -> AgentException:
    """
    Factory function to create appropriate AgentException from generic errors.
    
    Args:
        error: The original exception
        context: Additional context about where the error occurred
        
    Returns:
        Appropriate AgentException subclass
    """
    error_str = str(error).lower()
    error_type = type(error).__name__
    
    # Check for rate limit patterns (combine string check with type check)
    if (any(pattern in error_str for pattern in ['rate limit', 'quota', 'too many requests']) or
        error_type in ['RateLimitError', 'QuotaExceeded', 'TooManyRequestsError']):
        retry_after = None
        if 'retry after' in error_str:
            # Try to extract retry time
            match = re.search(r'retry after (\d+)', error_str)
            if match:
                retry_after = int(match.group(1))
        return RateLimitException(
            message=str(error),
            retry_after=retry_after
        )
    
    # Check for API key issues (combine string check with type check)
    if (any(pattern in error_str for pattern in ['api key', 'api_key', 'unauthorized', 'authentication']) or
        error_type in ['AuthenticationError', 'UnauthorizedError', 'InvalidAPIKeyError']):
        return InvalidAPIKeyException(message=str(error))
    
    # Check for timeout issues (combine string check with type check)
    if (any(pattern in error_str for pattern in ['timeout', 'timed out', 'deadline exceeded']) or
        error_type in ['TimeoutError', 'DeadlineExceeded', 'RequestTimeout']):
        return TimeoutException(message=str(error))
    
    # Check for network issues (combine string check with type check)
    if (any(pattern in error_str for pattern in ['connection', 'network', 'dns', 'unreachable']) or
        error_type in ['ConnectionError', 'NetworkError', 'DNSError', 'UnreachableError']):
        return NetworkException(message=str(error))
    
    # Check for configuration issues (combine string check with type check)
    if (any(pattern in error_str for pattern in ['config', 'missing required', 'not found']) or
        error_type in ['ConfigurationError', 'MissingRequiredField', 'NotFoundError']):
        return ConfigurationException(message=str(error))
    
    # Default to generic AgentException
    return AgentException(
        message=str(error),
        user_facing_message="An unexpected error occurred. I'm working on resolving it.",
        recovery_suggestions=[
            "Try your request again",
            "If the problem persists, please report it with the error code"
        ],
        severity=ErrorSeverity.MEDIUM,
        metadata={
            "original_error_type": error_type,
            "context": context or {}
        }
    )