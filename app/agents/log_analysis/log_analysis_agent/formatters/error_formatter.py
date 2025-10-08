"""
Error Block Formatter

Specializes in formatting error messages, stack traces, and log excerpts
with syntax highlighting, line numbers, and contextual information.
"""

from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import re

# Import with fallbacks to support both package and top-level test imports
try:
    from ..schemas.log_schemas import LogEntry, ErrorPattern, Severity
except ImportError:
    try:
        from schemas.log_schemas import LogEntry, ErrorPattern, Severity
    except ImportError:
        from app.agents.log_analysis.log_analysis_agent.schemas.log_schemas import LogEntry, ErrorPattern, Severity


@dataclass
class ErrorContext:
    """Context information for an error"""
    before_lines: List[str]
    error_lines: List[str]
    after_lines: List[str]
    start_line_number: int
    component: str
    timestamp: datetime
    severity: Severity


class ErrorBlockFormatter:
    """
    Formats error messages and log excerpts with enhanced readability.

    Features:
    - Syntax highlighting for different log levels
    - Line number annotations
    - Context lines before/after errors
    - Stack trace formatting
    - Error pattern highlighting
    """

    # Color codes for different severity levels (ANSI-like in markdown)
    SEVERITY_MARKERS = {
        Severity.TRACE: "🔍",
        Severity.DEBUG: "🐛",
        Severity.INFO: "ℹ️",
        Severity.WARNING: "⚠️",
        Severity.ERROR: "❌",
        Severity.CRITICAL: "🚨",
        Severity.FATAL: "💀"
    }

    # Patterns for common error types
    ERROR_PATTERNS = {
        "null_reference": re.compile(r"null reference|NullPointerException|undefined"),
        "timeout": re.compile(r"timeout|timed out|deadline exceeded", re.IGNORECASE),
        "connection": re.compile(r"connection (refused|reset|closed|failed)", re.IGNORECASE),
        "authentication": re.compile(r"auth(entication|orization) (failed|denied)", re.IGNORECASE),
        "memory": re.compile(r"out of memory|memory exhausted|heap space", re.IGNORECASE),
        "permission": re.compile(r"permission denied|access denied|forbidden", re.IGNORECASE),
        "file_not_found": re.compile(r"file not found|no such file|cannot find", re.IGNORECASE),
        "database": re.compile(r"database|sql|query (failed|error)", re.IGNORECASE)
    }

    def __init__(self):
        """Initialize the error formatter"""
        self.context_lines_before = 3
        self.context_lines_after = 3
        self.max_line_length = 120
        self.highlight_errors = True

    def format_error_block(self, error: ErrorContext) -> str:
        """
        Format a complete error block with context.

        Args:
            error: Error context information

        Returns:
            Formatted markdown error block
        """
        lines = []

        # Add header with metadata
        header = self._format_error_header(error)
        lines.append(header)
        lines.append("")

        # Start code block
        lines.append("```log")

        # Add context lines before error
        if error.before_lines:
            # Before lines come before the error, so they start at start_line_number - len(before_lines)
            before_start = error.start_line_number - len(error.before_lines)
            for i, line in enumerate(error.before_lines):
                line_num = before_start + i
                formatted_line = self._format_context_line(line, line_num)
                lines.append(formatted_line)

        # Add error lines with highlighting
        for i, line in enumerate(error.error_lines):
            line_num = error.start_line_number + i
            formatted_line = self._format_error_line(line, line_num, error.severity)
            lines.append(formatted_line)

        # Add context lines after error
        if error.after_lines:
            after_start = error.start_line_number + len(error.error_lines)
            for i, line in enumerate(error.after_lines):
                line_num = after_start + i
                formatted_line = self._format_context_line(line, line_num)
                lines.append(formatted_line)

        # End code block
        lines.append("```")

        # Add copy instruction
        lines.append("")
        lines.append("*💡 Tip: Click the copy button above to share this error with support*")

        return "\n".join(lines)

    def format_error_pattern(self, pattern: ErrorPattern) -> str:
        """
        Format an error pattern with sample entries.

        Args:
            pattern: Error pattern to format

        Returns:
            Formatted markdown representation
        """
        lines = []

        # Pattern header
        severity_marker = self.SEVERITY_MARKERS.get(Severity.ERROR, "❌")
        lines.append(f"### {severity_marker} {pattern.description}")
        lines.append("")

        # Pattern metadata
        lines.append(f"- **Category**: {pattern.category.name.replace('_', ' ').title()}")
        lines.append(f"- **Occurrences**: {pattern.occurrences} times")
        lines.append(f"- **Confidence**: {pattern.confidence:.0%}")
        lines.append(f"- **Duration**: {self._format_duration(pattern.duration)}")

        if pattern.affected_components:
            components = ", ".join(f"`{comp}`" for comp in pattern.affected_components)
            lines.append(f"- **Affected Components**: {components}")

        lines.append("")

        # Sample entries
        if pattern.sample_entries:
            lines.append("#### Sample Occurrences:")
            lines.append("")
            lines.append("```log")

            for entry in pattern.sample_entries[:3]:  # Show max 3 samples
                formatted_entry = self._format_log_entry(entry)
                lines.append(formatted_entry)
                lines.append("")

            lines.append("```")

        # Indicators
        if pattern.indicators:
            lines.append("")
            lines.append("**Key Indicators:**")
            for indicator in pattern.indicators:
                lines.append(f"- {indicator}")

        return "\n".join(lines)

    def format_stack_trace(self, stack_trace: str, language: str = "java") -> str:
        """
        Format a stack trace with proper highlighting.

        Args:
            stack_trace: Raw stack trace text
            language: Programming language for syntax highlighting

        Returns:
            Formatted markdown stack trace
        """
        lines = []
        lines.append(f"```{language}")

        trace_lines = stack_trace.split("\n")
        for line in trace_lines:
            # Highlight important parts
            if "Exception" in line or "Error" in line:
                line = f">>> {line} <<<"
            elif "at " in line:  # Stack frame
                # Indent stack frames
                line = "    " + line

            # Truncate very long lines
            if len(line) > self.max_line_length:
                line = line[:self.max_line_length] + "..."

            lines.append(line)

        lines.append("```")
        return "\n".join(lines)

    def format_log_excerpt(self, entries: List[LogEntry],
                           highlight_errors: bool = True,
                           max_entries: int = 20) -> str:
        """
        Format a sequence of log entries.

        Args:
            entries: Log entries to format
            highlight_errors: Whether to highlight error entries
            max_entries: Maximum number of entries to show

        Returns:
            Formatted markdown log excerpt
        """
        if not entries:
            return "*No log entries available*"

        lines = []
        lines.append("```log")

        # Truncate if needed
        if len(entries) > max_entries:
            entries = entries[:max_entries]
            truncated = True
        else:
            truncated = False

        for entry in entries:
            formatted_entry = self._format_log_entry(entry, highlight_errors)
            lines.append(formatted_entry)

        if truncated:
            lines.append("... [truncated]")

        lines.append("```")
        return "\n".join(lines)

    def _format_error_header(self, error: ErrorContext) -> str:
        """Format error block header with metadata"""
        severity_marker = self.SEVERITY_MARKERS.get(error.severity, "❌")
        timestamp = error.timestamp.strftime("%Y-%m-%d %H:%M:%S")

        header = (
            f"#### {severity_marker} Error in `{error.component}` "
            f"at {timestamp} (Line {error.start_line_number})"
        )
        return header

    def _format_context_line(self, line: str, line_num: int) -> str:
        """Format a context line (before/after error)"""
        # Dim context lines
        line = self._truncate_line(line)
        return f"{line_num:5d} |  {line}"

    def _format_error_line(self, line: str, line_num: int, severity: Severity) -> str:
        """Format an error line with highlighting"""
        line = self._truncate_line(line)
        severity_marker = self.SEVERITY_MARKERS.get(severity, "❌")

        # Highlight the error line
        return f"{line_num:5d} | {severity_marker} {line} <<<--- ERROR"

    def _format_log_entry(self, entry: LogEntry,
                         highlight_errors: bool = True) -> str:
        """Format a single log entry"""
        # Format timestamp
        timestamp = entry.timestamp.strftime("%H:%M:%S.%f")[:-3]

        # Get severity marker
        severity_marker = self.SEVERITY_MARKERS.get(entry.severity, "")

        # Format component
        component = f"[{entry.component}]" if entry.component else ""

        # Truncate message if needed
        message = self._truncate_line(entry.message)

        # Build the formatted line
        if entry.line_number:
            line_prefix = f"{entry.line_number:5d} | "
        else:
            line_prefix = ""

        formatted = f"{line_prefix}{timestamp} {severity_marker} {component} {message}"

        # Highlight errors if requested
        if highlight_errors and entry.is_error:
            formatted = f">>> {formatted} <<<"

        return formatted

    def _truncate_line(self, line: str) -> str:
        """Truncate long lines"""
        if len(line) > self.max_line_length:
            return line[:self.max_line_length] + "..."
        return line

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            return f"{seconds / 60:.1f} minutes"
        else:
            return f"{seconds / 3600:.1f} hours"

    def identify_error_type(self, message: str) -> Optional[str]:
        """
        Identify the type of error from the message.

        Args:
            message: Error message text

        Returns:
            Error type identifier or None
        """
        for error_type, pattern in self.ERROR_PATTERNS.items():
            if pattern.search(message):
                return error_type
        return None

    def suggest_copy_command(self, error_text: str) -> str:
        """
        Generate a copy-to-clipboard suggestion for an error.

        Args:
            error_text: Error text to copy

        Returns:
            Markdown with copy suggestion
        """
        # Escape backticks in error text
        escaped = error_text.replace("`", "\\`")

        return (
            f"**Quick Copy for Support:**\n"
            f"```\n"
            f"{escaped}\n"
            f"```\n"
            f"*Click the copy button and paste this in your support ticket*"
        )