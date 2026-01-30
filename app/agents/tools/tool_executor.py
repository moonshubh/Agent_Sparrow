"""
Claude-style tool execution with reliability patterns.

Key patterns adopted from Claude Agent SDK:
1. Errors become context for reasoning (not crashes)
2. Structured retry with exponential backoff
3. Per-tool configuration
4. Rich execution results for observability
"""

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

from app.core.logging_config import get_logger

logger = get_logger(__name__)


MAX_TOOL_MESSAGE_CHARS = 50_000


def _serialize_tool_content(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        return str(payload)


def _truncate_text(text: str, *, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return (
        text[: max(0, max_chars - 1)].rstrip()
        + "\n\n[TRUNCATED: tool output exceeded "
        + str(max_chars)
        + " chars]"
    )


@dataclass
class ToolExecutionConfig:
    """Per-tool execution configuration.

    Allows fine-grained control over how each tool executes:
    - Timeout: How long to wait before giving up
    - Retries: How many times to retry transient failures
    - Backoff: Exponential backoff factor between retries
    - Retryable errors: Which exceptions should trigger retries
    """

    timeout: float = 45.0
    max_retries: int = 2
    retry_backoff: float = 1.0
    retryable_errors: tuple[type, ...] = (
        TimeoutError,
        asyncio.TimeoutError,
        ConnectionError,
        ConnectionRefusedError,
        ConnectionResetError,
    )
    # Tool-specific hints for error messages
    error_recovery_hint: str = "Consider alternative approaches."


@dataclass
class ToolExecutionResult:
    """Structured result from tool execution.

    This is the key Claude pattern: every tool execution produces a structured
    result that can be converted to context for the model to reason about.

    Even failures become useful context, not just error strings.
    """

    tool_name: str
    tool_call_id: str
    success: bool
    result: Any | None
    error: str | None
    error_type: str | None
    duration_ms: int
    retries_used: int
    is_retryable_error: bool = False
    args_summary: str | None = None
    status: str | None = None
    artifact: Any | None = None

    def to_tool_message(self) -> ToolMessage:
        """Convert to LangChain ToolMessage with proper error handling.

        Claude pattern: errors become context for reasoning, not just error strings.
        The model can see what failed and why, and can try alternative approaches.
        """
        status = self.status or ("success" if self.success else "error")

        if self.success:
            content = _truncate_text(
                _serialize_tool_content(self.result),
                max_chars=MAX_TOOL_MESSAGE_CHARS,
            )
            return ToolMessage(
                content=content,
                tool_call_id=self.tool_call_id,
                name=self.tool_name,
                additional_kwargs={
                    "status": status,
                    "artifact": self.artifact,
                    "args_summary": self.args_summary,
                },
            )
        else:
            # Claude pattern: errors become context for reasoning
            error_content = self._format_error_content()
            return ToolMessage(
                content=error_content,
                tool_call_id=self.tool_call_id,
                name=self.tool_name,
                additional_kwargs={
                    "is_error": True,
                    "error_type": self.error_type,
                    "retries_used": self.retries_used,
                    "is_retryable": self.is_retryable_error,
                    "status": status,
                    "artifact": self.artifact,
                    "args_summary": self.args_summary,
                },
            )

    def _format_error_content(self) -> str:
        """Create consistent error context for the model."""
        parts = [
            f"Tool '{self.tool_name}' failed after {self.retries_used} retries.",
            f"Error: {self.error}",
            f"Duration: {self.duration_ms}ms",
        ]
        if self.args_summary:
            parts.append(f"Args: {self.args_summary}")
        parts.append("Consider alternative approaches or different parameters.")
        return "\n".join(parts)

    def to_metadata(self) -> dict[str, Any]:
        """Convert to metadata dict for LangSmith observability."""
        return {
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "retries_used": self.retries_used,
            "error_type": self.error_type,
            "is_retryable_error": self.is_retryable_error,
            "status": self.status,
        }


# Default configurations for known tools
# Tools that are more likely to have transient failures get more retries
DEFAULT_TOOL_CONFIGS: dict[str, ToolExecutionConfig] = {
    # Web-based tools are more prone to transient failures
    "web_search": ToolExecutionConfig(
        timeout=60.0,
        max_retries=3,
        retry_backoff=2.0,
        error_recovery_hint="Try a different search query or use alternative sources.",
    ),
    "tavily_extract": ToolExecutionConfig(
        timeout=90.0,
        max_retries=2,
        retry_backoff=2.0,
        error_recovery_hint="Try fewer URLs or a smaller set of pages.",
    ),
    "grounding_search": ToolExecutionConfig(
        timeout=60.0,
        max_retries=3,
        retry_backoff=2.0,
        error_recovery_hint="Try rephrasing the query or using web_search instead.",
    ),
    "minimax_web_search": ToolExecutionConfig(
        timeout=60.0,
        max_retries=2,
        retry_backoff=2.0,
        error_recovery_hint="Try simplifying the query or fallback to web_search.",
    ),
    "minimax_understand_image": ToolExecutionConfig(
        timeout=90.0,
        max_retries=2,
        retry_backoff=2.0,
        error_recovery_hint="Try a smaller image or a clearer prompt.",
    ),
    "firecrawl_fetch": ToolExecutionConfig(
        timeout=90.0,
        max_retries=2,
        retry_backoff=2.0,
        error_recovery_hint="Try reducing formats or actions, or fetch a simpler URL first.",
    ),
    "firecrawl_search": ToolExecutionConfig(
        timeout=60.0,
        max_retries=2,
        retry_backoff=2.0,
        error_recovery_hint="Try narrowing the query or switching sources.",
    ),
    "firecrawl_map": ToolExecutionConfig(
        timeout=60.0,
        max_retries=2,
        retry_backoff=2.0,
        error_recovery_hint="Try a simpler base URL or reduce the limit.",
    ),
    "firecrawl_crawl": ToolExecutionConfig(
        timeout=180.0,
        max_retries=1,
        retry_backoff=3.0,
        error_recovery_hint="Try reducing limit/max_depth or crawl a smaller section.",
    ),
    "firecrawl_agent": ToolExecutionConfig(
        timeout=180.0,
        max_retries=1,
        retry_backoff=3.0,
        error_recovery_hint="Try a narrower prompt or provide seed URLs.",
    ),
    "firecrawl_extract": ToolExecutionConfig(
        timeout=90.0,
        max_retries=2,
        retry_backoff=3.0,
        error_recovery_hint="The URL may be inaccessible. Try a different source.",
    ),
    # Database tools should be fast but may have connection issues
    "supabase_query": ToolExecutionConfig(
        timeout=30.0,
        max_retries=2,
        retry_backoff=1.0,
        error_recovery_hint="Check the query syntax or try a simpler query.",
    ),
    # Knowledge base search is usually reliable
    "kb_search": ToolExecutionConfig(
        timeout=30.0,
        max_retries=1,
        retry_backoff=1.0,
        error_recovery_hint="Try different search terms or check available knowledge bases.",
    ),
    # Log analysis can take longer for large files
    "log_diagnoser": ToolExecutionConfig(
        timeout=120.0,
        max_retries=1,
        retry_backoff=2.0,
        error_recovery_hint="The log file may be too large. Try analyzing a smaller portion.",
    ),
}


class ToolExecutor:
    """Reliable tool execution with Claude-style patterns.

    Key features:
    1. Structured retry with exponential backoff
    2. Per-tool configuration (timeout, retries, etc.)
    3. Errors become context for reasoning
    4. Rich execution results for observability
    5. Concurrent execution with semaphore-based limits

    Example:
        executor = ToolExecutor(configs=DEFAULT_TOOL_CONFIGS)
        result = await executor.execute(tool, tool_call, state)
        message = result.to_tool_message()  # Even errors become useful context
    """

    def __init__(
        self,
        configs: dict[str, ToolExecutionConfig] | None = None,
        default_config: ToolExecutionConfig | None = None,
        max_concurrency: int = 8,
        on_result: Callable[[ToolExecutionResult], None] | None = None,
    ):
        """Initialize the executor.

        Args:
            configs: Per-tool configuration overrides
            default_config: Default config for tools without specific config
            max_concurrency: Max parallel tool executions
            on_result: Optional callback fired after each execution (success/fail)
        """
        self.configs = configs or {}
        self.default_config = default_config or ToolExecutionConfig()
        bounded_concurrency = max(1, min(max_concurrency, 64))
        if bounded_concurrency != max_concurrency:
            logger.warning(
                "tool_executor_concurrency_adjusted",
                requested=max_concurrency,
                applied=bounded_concurrency,
            )
        self._max_concurrency = bounded_concurrency
        self._sem: asyncio.Semaphore | None = None
        self._sem_loop: asyncio.AbstractEventLoop | None = None
        self._on_result = on_result

        # Execution stats for observability
        self._stats_lock = threading.Lock()
        self._total_executions = 0
        self._total_failures = 0
        self._total_retries = 0

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Lazily create a semaphore bound to the current event loop."""
        loop = asyncio.get_running_loop()
        if self._sem is None or self._sem_loop is None or self._sem_loop is not loop:
            self._sem = asyncio.Semaphore(self._max_concurrency)
            self._sem_loop = loop
        return self._sem

    def get_config(self, tool_name: str) -> ToolExecutionConfig:
        """Get configuration for a specific tool."""
        return self.configs.get(tool_name, self.default_config)

    async def execute(
        self,
        tool: BaseTool,
        tool_call_id: str,
        args: Mapping[str, Any],
        config: dict | None = None,
    ) -> ToolExecutionResult:
        """Execute a tool with retry, timeout, and error conversion.

        Args:
            tool: The LangChain tool to execute
            tool_call_id: Unique ID for this tool call
            args: Arguments to pass to the tool
            config: Optional runtime config (for RunnableConfig)

        Returns:
            ToolExecutionResult with success/failure info that can be
            converted to a ToolMessage for the model to reason about.
        """
        tool_config = self.get_config(tool.name)
        start_time = time.monotonic()
        retries_used = 0
        last_error: Exception | None = None
        is_retryable = False
        tool_args = dict(args)
        args_summary = _summarize_args(tool_args)
        artifact = None

        with self._stats_lock:
            self._total_executions += 1

        async with self._get_semaphore():
            for attempt in range(tool_config.max_retries + 1):
                try:
                    async with asyncio.timeout(tool_config.timeout):
                        result = await tool.ainvoke(tool_args, config=config)

                        duration_ms = int((time.monotonic() - start_time) * 1000)

                        logger.debug(
                            "tool_execution_success",
                            tool=tool.name,
                            tool_call_id=tool_call_id,
                            duration_ms=duration_ms,
                            retries_used=retries_used,
                        )

                        artifact = _extract_artifact(result)
                        result_obj = ToolExecutionResult(
                            tool_name=tool.name,
                            tool_call_id=tool_call_id,
                            success=True,
                            result=result,
                            error=None,
                            error_type=None,
                            duration_ms=duration_ms,
                            retries_used=retries_used,
                            artifact=artifact,
                            args_summary=args_summary,
                            status="success",
                        )
                        self._emit_result(result_obj)
                        return result_obj

                except tool_config.retryable_errors as exc:
                    last_error = exc
                    is_retryable = True
                    retries_used += 1
                    with self._stats_lock:
                        self._total_retries += 1

                    if attempt < tool_config.max_retries:
                        delay = tool_config.retry_backoff * (2 ** attempt)
                        logger.warning(
                            "tool_execution_retry",
                            tool=tool.name,
                            tool_call_id=tool_call_id,
                            attempt=attempt + 1,
                            max_attempts=tool_config.max_retries + 1,
                            delay=delay,
                            error=str(exc),
                            exc_info=exc,
                        )
                        await asyncio.sleep(delay)
                        continue

                    # Final retry failed
                    break

                except asyncio.CancelledError:
                    # Don't catch cancellation - let it propagate
                    raise

                except Exception as exc:
                    # Non-retryable error
                    last_error = exc
                    is_retryable = False
                    break

        # If we get here, execution failed
        duration_ms = int((time.monotonic() - start_time) * 1000)
        with self._stats_lock:
            self._total_failures += 1

        error_msg = str(last_error) if last_error else "Unknown error"
        error_type = type(last_error).__name__ if last_error else "Unknown"

        logger.warning(
            "tool_execution_failed",
            tool=tool.name,
            tool_call_id=tool_call_id,
            duration_ms=duration_ms,
            retries_used=retries_used,
            error_type=error_type,
            error=error_msg,
            is_retryable=is_retryable,
            exc_info=last_error,
        )

        # Add recovery hint if available
        if tool_config.error_recovery_hint:
            error_msg = f"{error_msg}\n{tool_config.error_recovery_hint}"

        result_obj = ToolExecutionResult(
            tool_name=tool.name,
            tool_call_id=tool_call_id,
            success=False,
            result=None,
            error=error_msg,
            error_type=error_type,
            duration_ms=duration_ms,
            retries_used=retries_used,
            is_retryable_error=is_retryable,
            artifact=artifact,
            args_summary=args_summary,
            status="error",
        )
        self._emit_result(result_obj)
        return result_obj

    async def execute_batch(
        self,
        executions: list[tuple[BaseTool, str, Mapping[str, Any]]],
        config: dict | None = None,
    ) -> list[ToolExecutionResult]:
        """Execute multiple tools concurrently.

        Args:
            executions: List of (tool, tool_call_id, args) tuples
            config: Optional runtime config

        Returns:
            List of ToolExecutionResult in the same order as input
        """
        tasks = [
            self.execute(tool, tool_call_id, args, config)
            for tool, tool_call_id, args in executions
        ]
        return await asyncio.gather(*tasks)

    def get_stats(self) -> dict:
        """Get execution statistics for observability."""
        with self._stats_lock:
            total_executions = self._total_executions
            total_failures = self._total_failures
            total_retries = self._total_retries
        return {
            "total_executions": total_executions,
            "total_failures": total_failures,
            "total_retries": total_retries,
            "failure_rate": (
                total_failures / total_executions
                if total_executions > 0
                else 0.0
            ),
        }

    def reset_stats(self) -> None:
        """Reset execution statistics."""
        with self._stats_lock:
            self._total_executions = 0
            self._total_failures = 0
            self._total_retries = 0

    def _emit_result(self, result: ToolExecutionResult) -> None:
        """Invoke result callback safely."""
        if self._on_result is None:
            return
        try:
            self._on_result(result)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("tool_executor_callback_failed", error=str(exc))


def _summarize_args(args: Mapping[str, Any]) -> str:
    """Lightweight, non-sensitive args summary for logs/context."""
    if not args:
        return "no args"
    parts = []
    for index, (key, value) in enumerate(args.items()):
        if index >= 5:
            parts.append("...")
            break
        parts.append(f"{key}={type(value).__name__}")
    return ", ".join(parts)


def _extract_artifact(result: Any) -> Any | None:
    """Pull out an artifact payload from a structured result, if present."""
    if isinstance(result, Mapping):
        if "artifact" in result:
            return result.get("artifact")
        if "artifacts" in result:
            return result.get("artifacts")
    if hasattr(result, "artifact"):
        return getattr(result, "artifact")
    return None
