"""Streaming utilities implementing patterns from DeepAgents, LangChain, and LangGraph.

This module provides production-grade utilities for:
- Large tool result eviction (DeepAgents pattern)
- Approximate token counting for hot paths (LangChain pattern)
- Invalid tool call handling (LangChain pattern)
- Checkpoint deduplication (LangGraph pattern)
- Retry with exponential backoff + jitter (LangGraph pattern)
- Streaming backpressure (LangChain pattern)
- Safe JSON conversion helpers shared across streaming modules
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, TypedDict

from loguru import logger
from app.agents.log_analysis.log_analysis_agent.utils import extract_json_payload


# =============================================================================
# CONFIGURATION CONSTANTS (DeepAgents-style)
# =============================================================================

# Tool result eviction thresholds
TOOL_TOKEN_LIMIT = 20000  # ~80KB of text (4 chars/token)
TOOL_EVICTION_THRESHOLD = 4 * TOOL_TOKEN_LIMIT  # 80KB triggers eviction
MAX_LINE_LENGTH = 10000  # Individual line limit for formatting

# Token counting (LangChain-style)
CHARS_PER_TOKEN = 4.0  # Configurable ratio
EXTRA_TOKENS_PER_MESSAGE = 3.0  # Special token overhead

# Retry configuration (LangGraph-style)
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_INITIAL_INTERVAL = 1.0  # seconds
DEFAULT_MAX_INTERVAL = 60.0  # seconds
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_JITTER = 1.0  # seconds


# =============================================================================
# 1. LARGE TOOL RESULT EVICTION (DeepAgents pattern)
# =============================================================================

@dataclass
class EvictedToolResult:
    """Reference to a tool result that was evicted to storage."""
    original_length: int
    evicted_path: str
    sample_content: str
    evicted_at: str


class ToolResultEvictionManager:
    """Manages eviction of large tool results to prevent memory overflow.

    Based on DeepAgents pattern: Large results are written to a reference path
    and replaced with a summary + path reference.
    """

    def __init__(
        self,
        token_limit: int = TOOL_TOKEN_LIMIT,
        storage_callback: Optional[Callable[[str, str], bool]] = None,
    ):
        """Initialize the eviction manager.

        Args:
            token_limit: Token threshold before eviction (~4 chars/token)
            storage_callback: Optional callback to persist evicted content
                              Signature: (path, content) -> success
        """
        self.token_limit = token_limit
        self.eviction_threshold = 4 * token_limit  # Character threshold
        self.storage_callback = storage_callback
        self._evicted_results: Dict[str, EvictedToolResult] = {}

    def should_evict(self, content: str) -> bool:
        """Check if content exceeds eviction threshold."""
        return len(content) > self.eviction_threshold

    def evict_if_needed(
        self,
        tool_call_id: str,
        tool_name: str,
        content: str,
    ) -> Tuple[str, bool]:
        """Evict large tool result if it exceeds threshold.

        Args:
            tool_call_id: Unique identifier for the tool call
            tool_name: Name of the tool
            content: The tool result content

        Returns:
            Tuple of (processed_content, was_evicted)
        """
        if not self.should_evict(content):
            return content, False

        # Sanitize tool call ID for path
        sanitized_id = re.sub(r'[^a-zA-Z0-9_-]', '_', tool_call_id)[:50]
        evicted_path = f"/large_tool_results/{tool_name}/{sanitized_id}"

        # Get sample content (first 10 lines or 500 chars)
        lines = content.split('\n')[:10]
        sample = '\n'.join(lines)
        if len(sample) > 500:
            sample = sample[:500] + "..."

        # Store if callback provided
        if self.storage_callback:
            try:
                self.storage_callback(evicted_path, content)
            except Exception as e:
                logger.warning(f"tool_result_eviction_storage_failed: {e}")

        # Track eviction
        from datetime import datetime, timezone
        evicted = EvictedToolResult(
            original_length=len(content),
            evicted_path=evicted_path,
            sample_content=sample,
            evicted_at=datetime.now(timezone.utc).isoformat(),
        )
        self._evicted_results[tool_call_id] = evicted

        # Create reference message
        reference_msg = f"""Tool result too large ({len(content):,} chars, ~{len(content)//4:,} tokens).
Full result saved at: {evicted_path}

To access the full result, use read_file with offset/limit parameters.

Preview (first 10 lines):
{sample}"""

        logger.info(
            "tool_result_evicted",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            original_length=len(content),
            evicted_path=evicted_path,
        )

        return reference_msg, True

    def get_evicted_result(self, tool_call_id: str) -> Optional[EvictedToolResult]:
        """Retrieve metadata about an evicted result."""
        return self._evicted_results.get(tool_call_id)


# =============================================================================
# Shared safe JSON helpers
# =============================================================================

def safe_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure metadata values are JSON-serializable."""
    import json

    safe: Dict[str, Any] = {}
    for key, value in metadata.items():
        try:
            json.dumps(value)
            safe[key] = value
        except TypeError:
            safe[key] = str(value)
    return safe


def safe_json_value(value: Any) -> Any:
    """Convert a value to JSON-safe form, parsing JSON strings when possible."""
    import json

    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        if isinstance(value, str):
            trimmed = value.strip()
            if (trimmed.startswith("{") and trimmed.endswith("}")) or (
                trimmed.startswith("[") and trimmed.endswith("]")
            ):
                parsed = extract_json_payload(trimmed) or trimmed
                try:
                    json.dumps(parsed, ensure_ascii=False)
                    return parsed
                except Exception:
                    return trimmed
            return trimmed
        return str(value)


# =============================================================================
# 2. APPROXIMATE TOKEN COUNTING (LangChain pattern)
# =============================================================================

def count_tokens_approximately(
    content: str | List[Any],
    *,
    chars_per_token: float = CHARS_PER_TOKEN,
    extra_tokens_per_message: float = EXTRA_TOKENS_PER_MESSAGE,
    include_overhead: bool = True,
) -> int:
    """Fast approximate token counting for hot paths.

    Based on LangChain's count_tokens_approximately pattern.
    Uses character ratio instead of actual tokenization for speed.

    Args:
        content: String or list of content blocks
        chars_per_token: Character-to-token ratio (default 4.0)
        extra_tokens_per_message: Overhead for special tokens
        include_overhead: Whether to add message overhead

    Returns:
        Approximate token count (rounded up)
    """
    if isinstance(content, str):
        char_count = len(content)
    elif isinstance(content, list):
        # Sum content of list items
        char_count = sum(
            len(str(item.get("text", item))) if isinstance(item, dict) else len(str(item))
            for item in content
        )
    else:
        char_count = len(str(content))

    token_count = math.ceil(char_count / chars_per_token)

    if include_overhead:
        token_count += int(extra_tokens_per_message)

    return token_count


def count_message_tokens_approximately(
    messages: Sequence[Dict[str, Any]],
    *,
    chars_per_token: float = CHARS_PER_TOKEN,
) -> int:
    """Count tokens across multiple messages approximately.

    Args:
        messages: List of message dicts with 'content' and optionally 'role'
        chars_per_token: Character-to-token ratio

    Returns:
        Total approximate token count
    """
    total = 0

    for msg in messages:
        content = msg.get("content", "")
        role = msg.get("role", "user")

        # Content tokens
        total += count_tokens_approximately(
            content,
            chars_per_token=chars_per_token,
            include_overhead=False,
        )

        # Role overhead
        total += math.ceil(len(role) / chars_per_token)

        # Tool calls (if present)
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            total += count_tokens_approximately(
                json.dumps(tool_calls, default=str),
                chars_per_token=chars_per_token,
                include_overhead=False,
            )

        # Per-message overhead
        total += int(EXTRA_TOKENS_PER_MESSAGE)

    return total


# =============================================================================
# 3. INVALID TOOL CALL HANDLING (LangChain pattern)
# =============================================================================

class InvalidToolCall(TypedDict):
    """Structured capture of invalid tool calls."""
    type: str  # "invalid_tool_call"
    id: Optional[str]
    name: Optional[str]
    args: Optional[str]  # Raw args string (not parsed)
    error: Optional[str]
    index: Optional[int]


def parse_tool_calls_safely(
    raw_tool_calls: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[InvalidToolCall]]:
    """Parse tool calls with graceful error handling.

    Based on LangChain's default_tool_parser pattern.
    Invalid tool calls are captured rather than raising exceptions.

    Args:
        raw_tool_calls: List of raw tool call dicts from LLM response

    Returns:
        Tuple of (valid_calls, invalid_calls)
    """
    valid_calls: List[Dict[str, Any]] = []
    invalid_calls: List[InvalidToolCall] = []

    for idx, raw_call in enumerate(raw_tool_calls):
        try:
            # Extract function info
            function = raw_call.get("function", raw_call)
            name = function.get("name") or raw_call.get("name")
            args_raw = function.get("arguments") or raw_call.get("args", "{}")
            call_id = raw_call.get("id") or f"call_{idx}"

            # Try to parse arguments as JSON
            if isinstance(args_raw, str):
                try:
                    args = json.loads(args_raw)
                except json.JSONDecodeError as e:
                    # Capture as invalid call
                    invalid_calls.append(InvalidToolCall(
                        type="invalid_tool_call",
                        id=call_id,
                        name=name,
                        args=args_raw,
                        error=f"JSON parse error: {str(e)}",
                        index=idx,
                    ))
                    continue
            else:
                args = args_raw

            # Valid call
            valid_calls.append({
                "id": call_id,
                "name": name,
                "args": args,
            })

        except Exception as e:
            # Catch any other parsing errors
            invalid_calls.append(InvalidToolCall(
                type="invalid_tool_call",
                id=raw_call.get("id"),
                name=raw_call.get("name") or raw_call.get("function", {}).get("name"),
                args=str(raw_call.get("args") or raw_call.get("function", {}).get("arguments")),
                error=f"Parse error: {str(e)}",
                index=idx,
            ))

    return valid_calls, invalid_calls


# =============================================================================
# 4. CHECKPOINT DEDUPLICATION (LangGraph pattern)
# =============================================================================

class WriteDeduplicator:
    """Deduplicates checkpoint writes by keeping last write per channel.

    Based on LangGraph pattern: {w[0]: w for w in writes}.values()
    """

    def __init__(self):
        self._pending_writes: Dict[str, Tuple[str, str, Any]] = {}
        self._write_order: List[str] = []

    def add_write(self, task_id: str, channel: str, value: Any) -> None:
        """Add a write, replacing any previous write to same channel."""
        key = f"{task_id}:{channel}"

        if key not in self._pending_writes:
            self._write_order.append(key)

        self._pending_writes[key] = (task_id, channel, value)

    def get_deduplicated_writes(self) -> List[Tuple[str, str, Any]]:
        """Get deduplicated writes in submission order."""
        return [self._pending_writes[key] for key in self._write_order if key in self._pending_writes]

    def clear(self) -> None:
        """Clear all pending writes."""
        self._pending_writes.clear()
        self._write_order.clear()

    def remove_task_writes(self, task_id: str) -> None:
        """Remove all writes for a specific task."""
        keys_to_remove = [k for k in self._pending_writes if k.startswith(f"{task_id}:")]
        for key in keys_to_remove:
            del self._pending_writes[key]
            if key in self._write_order:
                self._write_order.remove(key)


# =============================================================================
# 5. RETRY WITH EXPONENTIAL BACKOFF + JITTER (LangGraph pattern)
# =============================================================================

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    initial_interval: float = DEFAULT_INITIAL_INTERVAL
    max_interval: float = DEFAULT_MAX_INTERVAL
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR
    jitter: float = DEFAULT_JITTER
    retry_exceptions: Tuple[type, ...] = (Exception,)


def calculate_retry_delay(
    attempt: int,
    config: RetryConfig,
) -> float:
    """Calculate delay before next retry with exponential backoff + jitter.

    Based on LangGraph pattern:
    delay = min(max_interval, initial * backoff_factor^(attempt-1) + random(0, jitter))

    Args:
        attempt: Current attempt number (1-indexed)
        config: Retry configuration

    Returns:
        Delay in seconds before next attempt
    """
    # Exponential backoff
    base_delay = config.initial_interval * (config.backoff_factor ** (attempt - 1))

    # Cap at max interval
    base_delay = min(base_delay, config.max_interval)

    # Add jitter to prevent thundering herd
    jitter = random.uniform(0, config.jitter)

    return base_delay + jitter


async def retry_with_backoff(
    func: Callable,
    *args,
    config: Optional[RetryConfig] = None,
    **kwargs,
) -> Any:
    """Execute function with retry and exponential backoff.

    Args:
        func: Async or sync function to execute
        *args: Positional arguments for func
        config: Retry configuration
        **kwargs: Keyword arguments for func

    Returns:
        Result of successful function execution

    Raises:
        Last exception if all retries fail
    """
    config = config or RetryConfig()
    last_exception: Optional[Exception] = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            # Execute function
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        except config.retry_exceptions as e:
            last_exception = e

            if attempt < config.max_attempts:
                delay = calculate_retry_delay(attempt, config)
                logger.warning(
                    "retry_attempt",
                    attempt=attempt,
                    max_attempts=config.max_attempts,
                    delay=delay,
                    error=str(e),
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "retry_exhausted",
                    attempts=attempt,
                    error=str(e),
                )

    if last_exception:
        raise last_exception

    raise RuntimeError("Retry failed without exception")


# =============================================================================
# 6. STREAMING BACKPRESSURE (LangChain pattern)
# =============================================================================

class BackpressureQueue:
    """Async queue with backpressure handling for streaming.

    Based on LangChain's AsyncIteratorCallbackHandler pattern.
    Uses event coordination to handle slow consumers.
    """

    def __init__(self, maxsize: int = 0):
        """Initialize the backpressure queue.

        Args:
            maxsize: Maximum queue size (0 = unbounded)
        """
        self.queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=maxsize)
        self.done: asyncio.Event = asyncio.Event()
        self._error: Optional[Exception] = None

    async def put(self, item: Any) -> None:
        """Add item to queue (blocks if full for bounded queue)."""
        if self.done.is_set():
            return
        await self.queue.put(item)

    def put_nowait(self, item: Any) -> None:
        """Add item without blocking (may raise QueueFull)."""
        if self.done.is_set():
            return
        self.queue.put_nowait(item)

    def signal_done(self, error: Optional[Exception] = None) -> None:
        """Signal that no more items will be added."""
        self._error = error
        self.done.set()

    async def __aiter__(self):
        """Iterate over queue items with backpressure handling."""
        while not (self.queue.empty() and self.done.is_set()):
            # Wait for either item or done signal
            get_task = asyncio.create_task(self.queue.get())
            done_task = asyncio.create_task(self.done.wait())

            done, pending = await asyncio.wait(
                [get_task, done_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Check if we got an item
            if get_task in done:
                try:
                    item = get_task.result()
                    yield item
                except asyncio.CancelledError:
                    pass

            # Check if done
            if done_task in done and self.queue.empty():
                break

        # Raise error if one was set
        if self._error:
            raise self._error


# =============================================================================
# 7. CONTENT TRUNCATION WITH GUIDANCE (DeepAgents pattern)
# =============================================================================

TRUNCATION_GUIDANCE = "... [results truncated, try being more specific with your parameters]"


def truncate_if_too_long(
    result: str | List[str],
    token_limit: int = TOOL_TOKEN_LIMIT,
) -> str | List[str]:
    """Truncate result if it exceeds token limit with helpful guidance.

    Based on DeepAgents pattern: Rough estimate of 4 chars/token.

    Args:
        result: String or list of strings to truncate
        token_limit: Maximum tokens allowed

    Returns:
        Truncated result with guidance message if truncated
    """
    char_limit = token_limit * 4  # ~4 chars per token

    if isinstance(result, list):
        total_chars = sum(len(item) for item in result)
        if total_chars > char_limit:
            # Calculate how many items to keep
            truncated_ratio = char_limit / total_chars
            truncated_count = max(1, int(len(result) * truncated_ratio))
            return result[:truncated_count] + [TRUNCATION_GUIDANCE]
        return result

    # String
    if len(result) > char_limit:
        return result[:char_limit] + "\n" + TRUNCATION_GUIDANCE

    return result


def format_content_with_line_numbers(
    content: str | List[str],
    start_line: int = 1,
    max_line_length: int = MAX_LINE_LENGTH,
) -> str:
    """Format content with line numbers, chunking long lines.

    Based on DeepAgents pattern with continuation markers.

    Args:
        content: String or list of lines
        start_line: Starting line number
        max_line_length: Maximum characters per line before chunking

    Returns:
        Formatted string with line numbers
    """
    if isinstance(content, str):
        lines = content.split('\n')
    else:
        lines = content

    result_lines = []
    line_number_width = 6

    for i, line in enumerate(lines):
        line_num = i + start_line

        if len(line) <= max_line_length:
            result_lines.append(f"{line_num:{line_number_width}d}\t{line}")
        else:
            # Split long line into chunks with continuation markers
            num_chunks = (len(line) + max_line_length - 1) // max_line_length
            for chunk_idx in range(num_chunks):
                start = chunk_idx * max_line_length
                end = min(start + max_line_length, len(line))
                chunk = line[start:end]

                if chunk_idx == 0:
                    result_lines.append(f"{line_num:{line_number_width}d}\t{chunk}")
                else:
                    # Continuation: use decimal notation (5.1, 5.2, etc.)
                    continuation_marker = f"{line_num}.{chunk_idx}"
                    result_lines.append(f"{continuation_marker:>{line_number_width}}\t{chunk}")

    return '\n'.join(result_lines)


# =============================================================================
# 8. EMISSION DEDUPLICATION HASH (LangGraph-inspired)
# =============================================================================

def compute_content_hash(content: Any, max_sample: int = 1000) -> str:
    """Compute a fast hash of content for deduplication.

    Args:
        content: Content to hash
        max_sample: Maximum chars to include in hash computation

    Returns:
        Short hash string
    """
    if content is None:
        return "none"

    # Convert to string representation
    if isinstance(content, str):
        sample = content[:max_sample]
    elif isinstance(content, (list, dict)):
        try:
            sample = json.dumps(content, default=str, sort_keys=True)[:max_sample]
        except:
            sample = str(content)[:max_sample]
    else:
        sample = str(content)[:max_sample]

    # Include length for full content awareness
    full_repr = f"{len(str(content))}:{sample}"

    return hashlib.md5(full_repr.encode()).hexdigest()[:12]
