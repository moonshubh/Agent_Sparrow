"""Standardized tool contracts for consistent error handling.

This module provides:
- ToolResult dataclass for standardized tool output
- @tool_error_handler decorator for automatic error wrapping
- Error classification utilities

All tools should return ToolResult and use @tool_error_handler to ensure:
1. Tools never raise exceptions (they return error results)
2. Errors are consistently formatted
3. Retry hints are provided when appropriate
4. LangSmith gets proper observability data
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union
from enum import Enum

from loguru import logger


class ErrorCategory(Enum):
    """Categories of tool errors for handling hints."""

    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    VALIDATION = "validation"
    PERMISSION = "permission"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


@dataclass
class ToolResult:
    """Standard result type for all tools.

    All tools should return this type to ensure consistent:
    - Error handling across the agent
    - Observability in LangSmith
    - Frontend error display

    Usage:
        @tool
        @tool_error_handler
        async def my_tool(query: str) -> ToolResult:
            results = await do_search(query)
            return ToolResult.success(data=results)

    Attributes:
        success: Whether the operation succeeded.
        data: Result data on success.
        error: Error message on failure.
        error_category: Classification of the error.
        metadata: Additional context (retry hints, partial results, etc.)
    """

    success: bool
    data: Any = None
    error: Optional[str] = None
    error_category: Optional[ErrorCategory] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        data: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ToolResult":
        """Create a successful result.

        Args:
            data: Result data.
            metadata: Optional metadata.

        Returns:
            ToolResult with success=True.
        """
        return cls(
            success=True,
            data=data,
            metadata=metadata or {},
        )

    @classmethod
    def failure(
        cls,
        error: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ToolResult":
        """Create a failure result.

        Args:
            error: Error message.
            category: Error classification.
            metadata: Optional metadata (retry hints, etc.)

        Returns:
            ToolResult with success=False.
        """
        return cls(
            success=False,
            error=error,
            error_category=category,
            metadata=metadata or {},
        )

    @classmethod
    def rate_limited(
        cls,
        error: str,
        retry_after: Optional[int] = None,
    ) -> "ToolResult":
        """Create a rate-limited result.

        Args:
            error: Error message.
            retry_after: Seconds to wait before retry.

        Returns:
            ToolResult indicating rate limit.
        """
        metadata = {}
        if retry_after is not None:
            metadata["retry_after"] = retry_after
        return cls.failure(
            error=error,
            category=ErrorCategory.RATE_LIMIT,
            metadata=metadata,
        )

    @classmethod
    def timeout(cls, operation: str) -> "ToolResult":
        """Create a timeout result.

        Args:
            operation: Name of the timed-out operation.

        Returns:
            ToolResult indicating timeout.
        """
        return cls.failure(
            error=f"Operation '{operation}' timed out",
            category=ErrorCategory.TIMEOUT,
            metadata={"operation": operation},
        )

    @classmethod
    def not_found(cls, resource: str) -> "ToolResult":
        """Create a not-found result.

        Args:
            resource: Description of the missing resource.

        Returns:
            ToolResult indicating resource not found.
        """
        return cls.failure(
            error=f"Resource not found: {resource}",
            category=ErrorCategory.NOT_FOUND,
            metadata={"resource": resource},
        )

    def to_message(self) -> str:
        """Convert to message string for tool response.

        Returns:
            Formatted string for LangChain ToolMessage content.
        """
        if self.error:
            msg = f"Error: {self.error}"
            if self.error_category:
                msg = f"[{self.error_category.value}] {msg}"
            if self.metadata.get("retry_after"):
                msg += f" (retry after {self.metadata['retry_after']}s)"
            return msg

        if isinstance(self.data, (dict, list)):
            try:
                return json.dumps(self.data, indent=2, default=str)
            except (TypeError, ValueError):
                return str(self.data)

        return str(self.data) if self.data is not None else ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization.

        Returns:
            Dict representation.
        """
        result = {
            "success": self.success,
            "data": self.data,
        }
        if self.error:
            result["error"] = self.error
        if self.error_category:
            result["error_category"] = self.error_category.value
        if self.metadata:
            result["metadata"] = self.metadata
        return result


# Type variable for decorated functions
F = TypeVar("F", bound=Callable[..., Any])


def tool_error_handler(func: F) -> F:
    """Decorator ensuring tools never raise, always return ToolResult.

    This decorator wraps tool functions to:
    1. Catch all exceptions
    2. Classify errors appropriately
    3. Return ToolResult objects
    4. Log errors for observability

    Usage:
        @tool
        @tool_error_handler
        async def web_search(query: str) -> ToolResult:
            results = await search_api.search(query)
            return results  # Automatically wrapped in ToolResult

    Note: The decorator handles both sync and async functions.
    """

    @wraps(func)
    async def async_wrapper(*args, **kwargs) -> ToolResult:
        try:
            result = await func(*args, **kwargs)

            # If already a ToolResult, return as-is
            if isinstance(result, ToolResult):
                return result

            # Wrap raw result in ToolResult
            return ToolResult.success(data=result)

        except QuotaExceededError as e:
            retry_after = getattr(e, "retry_after", None)
            logger.warning(
                "tool_quota_exceeded",
                tool=func.__name__,
                retry_after=retry_after,
            )
            return ToolResult.rate_limited(
                error=str(e),
                retry_after=retry_after,
            )

        except TimeoutError:
            logger.warning("tool_timeout", tool=func.__name__)
            return ToolResult.timeout(operation=func.__name__)

        except NotFoundException as e:
            logger.info("tool_not_found", tool=func.__name__, resource=str(e))
            return ToolResult.not_found(resource=str(e))

        except ValidationError as e:
            logger.warning("tool_validation_error", tool=func.__name__, error=str(e))
            return ToolResult.failure(
                error=str(e),
                category=ErrorCategory.VALIDATION,
            )

        except Exception as e:
            logger.exception(f"Tool {func.__name__} failed unexpectedly")
            return ToolResult.failure(
                error=str(e),
                category=_classify_error(e),
                metadata={"exception_type": type(e).__name__},
            )

    @wraps(func)
    def sync_wrapper(*args, **kwargs) -> ToolResult:
        try:
            result = func(*args, **kwargs)

            if isinstance(result, ToolResult):
                return result

            return ToolResult.success(data=result)

        except QuotaExceededError as e:
            retry_after = getattr(e, "retry_after", None)
            logger.warning(
                "tool_quota_exceeded",
                tool=func.__name__,
                retry_after=retry_after,
            )
            return ToolResult.rate_limited(
                error=str(e),
                retry_after=retry_after,
            )

        except TimeoutError:
            logger.warning("tool_timeout", tool=func.__name__)
            return ToolResult.timeout(operation=func.__name__)

        except NotFoundException as e:
            logger.info("tool_not_found", tool=func.__name__, resource=str(e))
            return ToolResult.not_found(resource=str(e))

        except ValidationError as e:
            logger.warning("tool_validation_error", tool=func.__name__, error=str(e))
            return ToolResult.failure(
                error=str(e),
                category=ErrorCategory.VALIDATION,
            )

        except Exception as e:
            logger.exception(f"Tool {func.__name__} failed unexpectedly")
            return ToolResult.failure(
                error=str(e),
                category=_classify_error(e),
                metadata={"exception_type": type(e).__name__},
            )

    # Return appropriate wrapper based on function type
    import asyncio

    if asyncio.iscoroutinefunction(func):
        return async_wrapper  # type: ignore
    return sync_wrapper  # type: ignore


def _classify_error(exc: Exception) -> ErrorCategory:
    """Classify an exception into an error category.

    Args:
        exc: The exception to classify.

    Returns:
        Appropriate ErrorCategory.
    """
    exc_type = type(exc).__name__.lower()
    exc_str = str(exc).lower()

    # Check for common error patterns
    if "rate" in exc_type or "quota" in exc_str or "429" in exc_str:
        return ErrorCategory.RATE_LIMIT

    if "timeout" in exc_type or "timeout" in exc_str:
        return ErrorCategory.TIMEOUT

    if "notfound" in exc_type or "404" in exc_str or "not found" in exc_str:
        return ErrorCategory.NOT_FOUND

    if "validation" in exc_type or "invalid" in exc_str:
        return ErrorCategory.VALIDATION

    if "permission" in exc_type or "403" in exc_str or "unauthorized" in exc_str:
        return ErrorCategory.PERMISSION

    if "unavailable" in exc_str or "503" in exc_str or "502" in exc_str:
        return ErrorCategory.SERVICE_UNAVAILABLE

    return ErrorCategory.UNKNOWN


# Custom exception types for explicit error handling
class QuotaExceededError(Exception):
    """Raised when API quota is exceeded."""

    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class NotFoundException(Exception):
    """Raised when a resource is not found."""

    pass


class ValidationError(Exception):
    """Raised when input validation fails."""

    pass


# Utility functions for tool implementations
def validate_required_param(
    value: Any,
    param_name: str,
    expected_type: Optional[type] = None,
) -> None:
    """Validate a required parameter.

    Args:
        value: Parameter value.
        param_name: Parameter name for error message.
        expected_type: Optional expected type.

    Raises:
        ValidationError: If validation fails.
    """
    if value is None:
        raise ValidationError(f"Required parameter '{param_name}' is missing")

    if expected_type is not None and not isinstance(value, expected_type):
        raise ValidationError(
            f"Parameter '{param_name}' must be {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )


def truncate_result(
    data: Union[str, Dict, List],
    max_chars: int = 50000,
) -> Union[str, Dict, List]:
    """Truncate tool result to prevent context overflow.

    Args:
        data: Result data.
        max_chars: Maximum characters.

    Returns:
        Truncated data.
    """
    if isinstance(data, str):
        if len(data) > max_chars:
            return data[: max_chars - 100] + f"\n... (truncated, {len(data)} total chars)"
        return data

    if isinstance(data, list):
        serialized = json.dumps(data, default=str)
        if len(serialized) > max_chars:
            # Truncate list items
            truncated = []
            current_len = 2  # for []
            for item in data:
                item_str = json.dumps(item, default=str)
                if current_len + len(item_str) + 2 > max_chars:
                    truncated.append({"_truncated": True, "_total_items": len(data)})
                    break
                truncated.append(item)
                current_len += len(item_str) + 2
            return truncated
        return data

    if isinstance(data, dict):
        serialized = json.dumps(data, default=str)
        if len(serialized) > max_chars:
            # Keep metadata, truncate content
            result = {}
            for key, value in data.items():
                if key in ("metadata", "error", "status", "count", "total"):
                    result[key] = value
                elif isinstance(value, str) and len(value) > 1000:
                    result[key] = value[:1000] + "..."
                else:
                    result[key] = value
            result["_truncated"] = True
            return result
        return data

    return data
