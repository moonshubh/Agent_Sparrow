"""
Metadata Formatter

Formats system information, session details, and diagnostic metadata
into clear, structured sections for log analysis responses.
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from dataclasses import dataclass

try:
    from ..schemas.log_schemas import LogMetadata, PerformanceMetrics
except ImportError:
    try:
        from schemas.log_schemas import LogMetadata, PerformanceMetrics
    except ImportError:
        from app.agents_v2.log_analysis_agent.schemas.log_schemas import LogMetadata, PerformanceMetrics


@dataclass
class MetadataSection:
    """Represents a formatted metadata section"""
    title: str
    items: Dict[str, str]
    icon: str = "ℹ️"
    priority: int = 0  # Lower number = higher priority


class MetadataFormatter:
    """
    Formats metadata and system information into structured markdown sections.

    Provides specialized formatting for:
    - System information boxes
    - Session statistics
    - Performance metrics
    - Account configurations
    - Environment details
    """

    # Icons for different metadata categories
    CATEGORY_ICONS = {
        "system": "💻",
        "performance": "⚡",
        "database": "🗄️",
        "network": "🌐",
        "memory": "🧠",
        "accounts": "📧",
        "session": "⏱️",
        "plugins": "🔌",
        "errors": "❌",
        "warnings": "⚠️"
    }

    # Status indicators
    STATUS_INDICATORS = {
        "healthy": "🟢",
        "warning": "🟡",
        "error": "🔴",
        "unknown": "⚫"
    }

    def __init__(self):
        """Initialize the metadata formatter"""
        self.show_empty_values = False
        self.compact_mode = False

    def format_metadata_overview(self, metadata: LogMetadata) -> str:
        """
        Format complete metadata overview.

        Args:
            metadata: Log metadata to format

        Returns:
            Formatted markdown metadata section
        """
        sections = []

        # Always show system info first
        system_section = self._format_system_info(metadata)
        sections.append(system_section)

        # Session information
        session_section = self._format_session_info(metadata)
        if session_section:
            sections.append(session_section)

        # Account information
        if metadata.account_count > 0:
            account_section = self._format_account_info(metadata)
            sections.append(account_section)

        # Performance indicators
        if metadata.error_count > 0 or metadata.warning_count > 0:
            health_section = self._format_health_indicators(metadata)
            sections.append(health_section)

        # System resources
        resource_section = self._format_resource_usage(metadata)
        if resource_section:
            sections.append(resource_section)

        # Combine all sections
        return "\n\n".join(sections)

    def format_compact_metadata(self, metadata: LogMetadata) -> str:
        """
        Format metadata in compact single-box format.

        Args:
            metadata: Log metadata to format

        Returns:
            Compact formatted metadata
        """
        lines = []
        lines.append("```yaml")
        lines.append("# System Information")
        lines.append(f"Mailbird Version: {metadata.mailbird_version}")

        if metadata.build_number:
            lines.append(f"Build: {metadata.build_number}")

        lines.append(f"OS: {metadata.os_version} ({metadata.os_architecture})")
        lines.append(f"Accounts: {metadata.account_count}")

        if metadata.account_providers:
            providers = ", ".join(metadata.account_providers)
            lines.append(f"Providers: {providers}")

        lines.append(f"Total Log Entries: {metadata.total_entries:,}")
        lines.append(f"Errors: {metadata.error_count:,}")
        lines.append(f"Warnings: {metadata.warning_count:,}")

        if metadata.session_duration_hours:
            lines.append(f"Session Duration: {self._format_duration(metadata.session_duration_hours)}")

        lines.append("```")
        return "\n".join(lines)

    def format_performance_metrics(self, metrics: PerformanceMetrics) -> str:
        """
        Format performance metrics section.

        Args:
            metrics: Performance metrics to format

        Returns:
            Formatted performance metrics
        """
        lines = []
        lines.append("### ⚡ Performance Metrics")
        lines.append("")

        # Response times
        if metrics.avg_response_time_ms is not None:
            status = self._get_response_time_status(metrics.avg_response_time_ms)
            max_time_str = (
                f"{metrics.max_response_time_ms:.1f}ms"
                if metrics.max_response_time_ms is not None
                else "N/A"
            )
            lines.append(
                f"- **Response Time**: {status} {metrics.avg_response_time_ms:.1f}ms avg "
                f"(max: {max_time_str})"
            )

        # Database performance
        if metrics.slow_queries > 0:
            status = self.STATUS_INDICATORS["warning" if metrics.slow_queries > 10 else "healthy"]
            lines.append(f"- **Slow Queries**: {status} {metrics.slow_queries} detected")

        # Sync performance
        if metrics.sync_duration_seconds is not None:
            status = self._get_sync_duration_status(metrics.sync_duration_seconds)
            lines.append(f"- **Sync Duration**: {status} {metrics.sync_duration_seconds:.1f}s average")

        # Network latency
        if metrics.network_latency_ms is not None:
            status = self._get_latency_status(metrics.network_latency_ms)
            lines.append(f"- **Network Latency**: {status} {metrics.network_latency_ms:.1f}ms")

        # Critical issues
        if metrics.ui_freezes > 0:
            lines.append(f"- **UI Freezes**: {self.STATUS_INDICATORS['error']} {metrics.ui_freezes} occurrences")

        if metrics.crash_events > 0:
            lines.append(f"- **Crashes**: {self.STATUS_INDICATORS['error']} {metrics.crash_events} events")

        # Memory peaks
        if metrics.memory_peaks:
            max_memory = max(peak[1] for peak in metrics.memory_peaks)
            lines.append(f"- **Peak Memory**: {max_memory:.1f} MB")

        # CPU peaks
        if metrics.cpu_peaks:
            max_cpu = max(peak[1] for peak in metrics.cpu_peaks)
            lines.append(f"- **Peak CPU**: {max_cpu:.1f}%")

        return "\n".join(lines) if lines[2:] else ""  # Return empty if no metrics

    def _format_system_info(self, metadata: LogMetadata) -> str:
        """Format system information section"""
        lines = []
        icon = self.CATEGORY_ICONS["system"]

        lines.append(f"### {icon} System Information")
        lines.append("")
        lines.append("```yaml")
        lines.append(f"Application: Mailbird {metadata.mailbird_version}")

        if metadata.build_number:
            lines.append(f"Build: {metadata.build_number}")

        lines.append(f"Operating System: {metadata.os_version}")
        lines.append(f"Architecture: {metadata.os_architecture}")

        if metadata.database_size_mb:
            lines.append(f"Database Size: {metadata.database_size_mb:.1f} MB")

        lines.append("```")
        return "\n".join(lines)

    def _format_session_info(self, metadata: LogMetadata) -> Optional[str]:
        """Format session information section"""
        if not metadata.session_start:
            return None

        lines = []
        icon = self.CATEGORY_ICONS["session"]

        lines.append(f"### {icon} Session Information")
        lines.append("")

        start_time = metadata.session_start.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"- **Started**: {start_time}")

        if metadata.session_end:
            end_time = metadata.session_end.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"- **Ended**: {end_time}")

        if metadata.session_duration_hours:
            duration = self._format_duration(metadata.session_duration_hours)
            lines.append(f"- **Duration**: {duration}")

        lines.append(f"- **Total Entries**: {metadata.total_entries:,}")
        lines.append(f"- **Error Rate**: {metadata.error_rate:.1f}%")

        return "\n".join(lines)

    def _format_account_info(self, metadata: LogMetadata) -> str:
        """Format account information section"""
        lines = []
        icon = self.CATEGORY_ICONS["accounts"]

        lines.append(f"### {icon} Email Accounts")
        lines.append("")
        lines.append(f"- **Total Accounts**: {metadata.account_count}")

        if metadata.account_providers:
            lines.append(f"- **Providers**: {', '.join(metadata.account_providers)}")

        if metadata.proxy_configured:
            lines.append(f"- **Proxy**: {self.STATUS_INDICATORS['healthy']} Configured")

        lines.append(f"- **Network State**: {metadata.network_state}")

        return "\n".join(lines)

    def _format_health_indicators(self, metadata: LogMetadata) -> str:
        """Format health status indicators"""
        lines = []

        # Determine overall health
        if metadata.error_rate > 10:
            health_status = "error"
            health_text = "Critical Issues Detected"
        elif metadata.error_rate > 5:
            health_status = "warning"
            health_text = "Some Issues Detected"
        else:
            health_status = "healthy"
            health_text = "Normal Operation"

        icon = self.STATUS_INDICATORS[health_status]
        lines.append(f"### {icon} Health Status: {health_text}")
        lines.append("")

        # Error breakdown
        if metadata.error_count > 0:
            lines.append(f"- **Errors**: {self.CATEGORY_ICONS['errors']} {metadata.error_count:,} "
                        f"({metadata.error_rate:.1f}% of entries)")

        if metadata.warning_count > 0:
            lines.append(f"- **Warnings**: {self.CATEGORY_ICONS['warnings']} {metadata.warning_count:,}")

        return "\n".join(lines)

    def _format_resource_usage(self, metadata: LogMetadata) -> Optional[str]:
        """Format resource usage section"""
        if not metadata.memory_usage_mb and not metadata.cpu_usage_percent:
            return None

        lines = []
        lines.append("### 🖥️ Resource Usage")
        lines.append("")

        if metadata.memory_usage_mb:
            memory_status = self._get_memory_status(metadata.memory_usage_mb)
            lines.append(f"- **Memory**: {memory_status} {metadata.memory_usage_mb:.1f} MB average")

        if metadata.cpu_usage_percent:
            cpu_status = self._get_cpu_status(metadata.cpu_usage_percent)
            lines.append(f"- **CPU**: {cpu_status} {metadata.cpu_usage_percent:.1f}% average")

        if metadata.database_size_mb:
            db_status = self._get_database_status(metadata.database_size_mb)
            lines.append(f"- **Database**: {db_status} {metadata.database_size_mb:.1f} MB")

        return "\n".join(lines)

    def _format_duration(self, hours: float) -> str:
        """Format duration in human-readable format"""
        if hours < 1:
            return f"{int(hours * 60)} minutes"
        elif hours < 24:
            return f"{hours:.1f} hours"
        else:
            days = int(hours / 24)
            remaining_hours = hours % 24
            return f"{days} days, {remaining_hours:.1f} hours"

    def _get_response_time_status(self, ms: float) -> str:
        """Get status indicator for response time"""
        if ms < 100:
            return self.STATUS_INDICATORS["healthy"]
        elif ms < 500:
            return self.STATUS_INDICATORS["warning"]
        else:
            return self.STATUS_INDICATORS["error"]

    def _get_sync_duration_status(self, seconds: float) -> str:
        """Get status indicator for sync duration"""
        if seconds < 5:
            return self.STATUS_INDICATORS["healthy"]
        elif seconds < 30:
            return self.STATUS_INDICATORS["warning"]
        else:
            return self.STATUS_INDICATORS["error"]

    def _get_latency_status(self, ms: float) -> str:
        """Get status indicator for network latency"""
        if ms < 50:
            return self.STATUS_INDICATORS["healthy"]
        elif ms < 200:
            return self.STATUS_INDICATORS["warning"]
        else:
            return self.STATUS_INDICATORS["error"]

    def _get_memory_status(self, mb: float) -> str:
        """Get status indicator for memory usage"""
        if mb < 500:
            return self.STATUS_INDICATORS["healthy"]
        elif mb < 1000:
            return self.STATUS_INDICATORS["warning"]
        else:
            return self.STATUS_INDICATORS["error"]

    def _get_cpu_status(self, percent: float) -> str:
        """Get status indicator for CPU usage"""
        if percent < 30:
            return self.STATUS_INDICATORS["healthy"]
        elif percent < 70:
            return self.STATUS_INDICATORS["warning"]
        else:
            return self.STATUS_INDICATORS["error"]

    def _get_database_status(self, mb: float) -> str:
        """Get status indicator for database size"""
        if mb < 500:
            return self.STATUS_INDICATORS["healthy"]
        elif mb < 2000:
            return self.STATUS_INDICATORS["warning"]
        else:
            return self.STATUS_INDICATORS["error"]

    def format_attachment_info(self, attachment_data: Dict[str, Any]) -> str:
        """
        Format attachment information if present.

        Args:
            attachment_data: Dictionary containing attachment metadata

        Returns:
            Formatted attachment section
        """
        if not attachment_data:
            return ""

        lines = []
        lines.append("### 📎 Attachment Analysis")
        lines.append("")

        if "screenshot_count" in attachment_data:
            lines.append(f"- **Screenshots**: {attachment_data['screenshot_count']}")

        if "ocr_summary" in attachment_data:
            lines.append(f"- **OCR Summary**: {attachment_data['ocr_summary']}")

        if "error_visible" in attachment_data:
            if attachment_data["error_visible"]:
                lines.append("- **Error Dialog**: " + self.STATUS_INDICATORS["error"] + " Detected in screenshot")

        return "\n".join(lines) if lines[2:] else ""