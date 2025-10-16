"""
Pattern Analyzer for Error Detection

This module implements sophisticated pattern recognition for identifying
error patterns, anomalies, and recurring issues in Mailbird logs.
"""

import re
import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
import hashlib

from ..schemas.log_schemas import (
    LogEntry,
    ErrorPattern,
    ErrorCategory,
    Severity,
    EvidenceReference,
    SignatureInfo,
)

logger = logging.getLogger(__name__)


@dataclass
class PatternSignature:
    """Represents a unique pattern signature for clustering similar errors."""

    signature_hash: str
    template: str
    variables: List[str] = field(default_factory=list)
    category: ErrorCategory = ErrorCategory.UNKNOWN
    exception: Optional[str] = None
    top_frames: List[str] = field(default_factory=list)

    @classmethod
    def from_message(cls, message: str, category: ErrorCategory = ErrorCategory.UNKNOWN) -> "PatternSignature":
        """Create a pattern signature from an error message."""
        # Normalize the message to create a template
        template, variables = cls._extract_template(message)
        exception, top_frames = cls._extract_exception_and_frames(message)
        signature_hash = hashlib.md5(template.encode()).hexdigest()[:8]

        return cls(
            signature_hash=signature_hash,
            template=template,
            variables=variables,
            category=category,
            exception=exception,
            top_frames=top_frames,
        )

    @staticmethod
    def _extract_template(message: str) -> Tuple[str, List[str]]:
        """Extract a normalized template and variable parts from a message."""
        variables = []

        # Replace common variable patterns with placeholders
        patterns = [
            (r"\b[A-Fa-f0-9]{8,}\b", "<HEX>"),  # Hex values
            (r"\b\d{4,}\b", "<NUM>"),  # Large numbers
            (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}", "<EMAIL>"),  # Emails
            (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "<IP>"),  # IP addresses
            (r"[\\/][^\\\/\s]+[\\/][^\\\/\s]+", "<PATH>"),  # File paths
            (r"\b[A-Z][a-z]+Exception\b", "<EXCEPTION>"),  # Exception types
            (r'"[^"]*"', "<STRING>"),  # Quoted strings
            (r"'[^']*'", "<STRING>"),  # Single quoted strings
        ]

        template = message
        for pattern, placeholder in patterns:
            matches = re.findall(pattern, template)
            variables.extend(matches)
            template = re.sub(pattern, placeholder, template)

        return template, variables

    @staticmethod
    def _extract_exception_and_frames(message: str) -> Tuple[Optional[str], List[str]]:
        """Extract probable exception name and top stack frames from a message block."""
        exception_match = re.search(r"([A-Za-z0-9_.]+Exception)", message)
        exception = exception_match.group(1) if exception_match else None

        frames: List[str] = []
        for line in message.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if lowered.startswith("at "):
                frame = stripped[3:].strip()
            elif " at " in lowered:
                # Handle "Exception: ... at Method" inline formats
                parts = stripped.split(" at ", 1)
                frame = parts[1].strip()
            else:
                continue

            frame = re.sub(r":\d+(?=\b|$)", "", frame)
            frame = re.sub(r"\s+in\s+<[^>]+>", "", frame)
            if frame and frame not in frames:
                frames.append(frame)
            if len(frames) >= 3:
                break

        return exception, frames


class PatternAnalyzer:
    """
    Analyzes log entries to identify and categorize error patterns.

    This class implements clustering algorithms and heuristics to group
    similar errors and detect recurring patterns in Mailbird logs.
    """

    # Known error patterns for Mailbird
    KNOWN_PATTERNS = {
        ErrorCategory.AUTHENTICATION: [
            r"401\s+Unauthorized",
            r"403\s+Forbidden",
            r"Authentication failed",
            r"Invalid credentials",
            r"OAuth.*expired",
            r"Token.*invalid",
            r"Password.*incorrect",
            r"Login failed",
            r"Access denied",
        ],
        ErrorCategory.SYNCHRONIZATION: [
            r"Sync.*failed",
            r"Unable to sync",
            r"Synchronization error",
            r"IMAP.*timeout",
            r"SMTP.*failed",
            r"Connection.*lost",
            r"Folder.*not.*found",
            r"Message.*not.*found",
            r"Conflict.*detected",
        ],
        ErrorCategory.NETWORK: [
            r"Connection.*refused",
            r"Network.*unreachable",
            r"Timeout.*exceeded",
            r"Socket.*error",
            r"DNS.*resolution.*failed",
            r"SSL.*handshake.*failed",
            r"Certificate.*invalid",
            r"Proxy.*error",
            r"No.*internet.*connection",
        ],
        ErrorCategory.DATABASE: [
            r"Database.*locked",
            r"SQL.*error",
            r"Constraint.*violation",
            r"Corruption.*detected",
            r"Transaction.*failed",
            r"Deadlock.*detected",
            r"Index.*corrupt",
            r"Table.*not.*found",
            r"Database.*full",
        ],
        ErrorCategory.PERFORMANCE: [
            r"Out of memory",
            r"Memory.*exhausted",
            r"Stack overflow",
            r"CPU.*usage.*high",
            r"Response.*slow",
            r"Timeout.*occurred",
            r"Thread.*blocked",
            r"Deadlock",
            r"Performance.*degraded",
        ],
        ErrorCategory.UI_INTERACTION: [
            r"UI.*frozen",
            r"Window.*not.*responding",
            r"Click.*failed",
            r"Render.*error",
            r"Display.*issue",
            r"Control.*not.*found",
            r"Focus.*lost",
            r"Input.*blocked",
        ],
        ErrorCategory.FILE_SYSTEM: [
            r"File.*not.*found",
            r"Access.*denied",
            r"Disk.*full",
            r"Path.*invalid",
            r"Permission.*denied",
            r"Write.*failed",
            r"Read.*error",
            r"Directory.*not.*exist",
        ],
    }

    def __init__(self, min_occurrences: int = 2, time_window_minutes: int = 60):
        """
        Initialize the pattern analyzer.

        Args:
            min_occurrences: Minimum occurrences to consider a pattern
            time_window_minutes: Time window for clustering related errors
        """
        self.min_occurrences = min_occurrences
        self.time_window = timedelta(minutes=time_window_minutes)
        self._compiled_patterns = self._compile_patterns()
        self.reset()

    def _compile_patterns(self) -> Dict[ErrorCategory, List[re.Pattern]]:
        """Pre-compile regex patterns for efficiency."""
        compiled = {}
        for category, patterns in self.KNOWN_PATTERNS.items():
            compiled[category] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]
        return compiled

    def reset(self):
        """Reset internal state for new analysis."""
        self._pattern_clusters: Dict[str, Dict[str, Any]] = {}
        self._category_counts: Counter = Counter()
        self._temporal_clusters: List[List[LogEntry]] = []

    def analyze_entries(self, entries: List[LogEntry]) -> List[ErrorPattern]:
        """
        Analyze log entries to identify error patterns.

        Args:
            entries: List of log entries to analyze

        Returns:
            List of identified error patterns
        """
        self.reset()

        # Filter to error/warning entries
        relevant_entries = [
            e for e in entries
            if e.severity.numeric_value >= Severity.WARNING.numeric_value
        ]

        if not relevant_entries:
            return []

        # Categorize entries
        categorized_entries = self._categorize_entries(relevant_entries)

        # Cluster similar errors
        self._cluster_by_signature(categorized_entries)

        # Perform temporal clustering
        self._temporal_clustering(relevant_entries)

        # Build error patterns
        patterns = self._build_patterns()

        # Sort by severity and frequency
        patterns.sort(
            key=lambda p: (p.occurrences, p.confidence),
            reverse=True
        )

        return patterns

    def _categorize_entries(
        self, entries: List[LogEntry]
    ) -> List[Tuple[LogEntry, ErrorCategory]]:
        """Categorize each entry based on known patterns."""
        categorized = []

        for entry in entries:
            category = self._categorize_entry(entry)
            categorized.append((entry, category))
            self._category_counts[category] += 1

        return categorized

    def _categorize_entry(self, entry: LogEntry) -> ErrorCategory:
        """Determine the category of a single log entry."""
        message = entry.message.lower()

        # Check against known patterns
        for category, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(message):
                    return category

        # Heuristic categorization based on keywords
        if any(word in message for word in ["auth", "login", "password", "credential"]):
            return ErrorCategory.AUTHENTICATION
        elif any(word in message for word in ["sync", "imap", "smtp", "email"]):
            return ErrorCategory.SYNCHRONIZATION
        elif any(word in message for word in ["network", "connection", "socket", "timeout"]):
            return ErrorCategory.NETWORK
        elif any(word in message for word in ["database", "sql", "query", "table"]):
            return ErrorCategory.DATABASE
        elif any(word in message for word in ["memory", "cpu", "performance", "slow"]):
            return ErrorCategory.PERFORMANCE
        elif any(word in message for word in ["ui", "window", "display", "render"]):
            return ErrorCategory.UI_INTERACTION
        elif any(word in message for word in ["file", "disk", "path", "directory"]):
            return ErrorCategory.FILE_SYSTEM

        return ErrorCategory.UNKNOWN

    def _cluster_by_signature(
        self, categorized_entries: List[Tuple[LogEntry, ErrorCategory]]
    ):
        """Cluster entries by their pattern signature."""
        for entry, category in categorized_entries:
            signature = PatternSignature.from_message(entry.message, category)
            cluster = self._pattern_clusters.setdefault(
                signature.signature_hash,
                {"signature": signature, "entries": []}
            )
            cluster["entries"].append(entry)

    def _temporal_clustering(self, entries: List[LogEntry]):
        """Cluster errors that occur close together in time."""
        if not entries:
            return

        # Filter out entries without timestamps
        entries_with_time = [e for e in entries if e.timestamp is not None]
        if not entries_with_time:
            return

        # Sort by timestamp
        sorted_entries = sorted(entries_with_time, key=lambda e: e.timestamp)

        current_cluster = [sorted_entries[0]]

        for entry in sorted_entries[1:]:
            # Check if entry is within time window of last cluster entry
            time_diff = entry.timestamp - current_cluster[-1].timestamp
            if time_diff <= self.time_window:
                current_cluster.append(entry)
            else:
                # Start new cluster if current has minimum entries
                if len(current_cluster) >= self.min_occurrences:
                    self._temporal_clusters.append(current_cluster)
                current_cluster = [entry]

        # Don't forget the last cluster
        if len(current_cluster) >= self.min_occurrences:
            self._temporal_clusters.append(current_cluster)

    def _build_patterns(self) -> List[ErrorPattern]:
        """Build ErrorPattern objects from clustered data."""
        patterns = []
        pattern_id = 0

        # Build patterns from signature clusters
        for signature_hash, payload in self._pattern_clusters.items():
            entries = payload["entries"]
            signature: PatternSignature = payload["signature"]

            if len(entries) < self.min_occurrences:
                continue

            pattern_id += 1
            first_entry = entries[0]
            category = signature.category or self._categorize_entry(first_entry)

            # Extract pattern details
            components = set(e.component for e in entries)
            timestamps = [e.timestamp for e in entries]

            evidence_refs: List[Dict[str, Any]] = []
            for example in entries[:3]:
                evidence_refs.append(
                    asdict(
                        EvidenceReference(
                            source_file=example.source_file or "log_file.log",
                            line_start=example.line_number,
                            line_end=example.line_number,
                            signature_id=signature_hash,
                        )
                    )
                )

            signature_info = SignatureInfo(
                exception=signature.exception,
                message_fingerprint=signature.template,
                top_frames=signature.top_frames,
            )

            pattern = ErrorPattern(
                pattern_id=f"PAT-{pattern_id:04d}",
                category=category,
                description=self._generate_pattern_description(signature, entries),
                occurrences=len(entries),
                first_seen=min(timestamps),
                last_seen=max(timestamps),
                affected_components=components,
                sample_entries=entries[:3],  # Keep first 3 as samples
                confidence=self._calculate_confidence(entries),
                indicators=self._extract_indicators(entries),
                signature_id=signature_hash,
                signature=signature_info.__dict__,
                evidence_refs=evidence_refs,
            )
            patterns.append(pattern)

        # Build patterns from temporal clusters
        for cluster in self._temporal_clusters:
            pattern_id += 1
            categories = Counter(self._categorize_entry(e) for e in cluster)
            dominant_category = categories.most_common(1)[0][0]

            pattern = ErrorPattern(
                pattern_id=f"TEMP-{pattern_id:04d}",
                category=dominant_category,
                description=f"Cascade of {len(cluster)} errors within {self.time_window.total_seconds()/60:.0f} minutes",
                occurrences=len(cluster),
                first_seen=cluster[0].timestamp,
                last_seen=cluster[-1].timestamp,
                affected_components=set(e.component for e in cluster),
                sample_entries=cluster[:3],
                confidence=0.8,  # Temporal patterns have good confidence
                indicators=["temporal_correlation", f"burst_size:{len(cluster)}"],
            )
            patterns.append(pattern)

        return patterns

    def _generate_pattern_description(
        self, signature: PatternSignature, entries: List[LogEntry]
    ) -> str:
        """Generate a human-readable description of the pattern."""
        # Extract common elements
        components = Counter(e.component for e in entries)
        most_common_component = components.most_common(1)[0][0] if components else "system"

        # Build description based on category
        category_descriptions = {
            ErrorCategory.AUTHENTICATION: f"Authentication failures in {most_common_component}",
            ErrorCategory.SYNCHRONIZATION: f"Synchronization issues with {most_common_component}",
            ErrorCategory.NETWORK: f"Network connectivity problems affecting {most_common_component}",
            ErrorCategory.DATABASE: f"Database errors in {most_common_component}",
            ErrorCategory.PERFORMANCE: f"Performance degradation in {most_common_component}",
            ErrorCategory.UI_INTERACTION: f"UI responsiveness issues in {most_common_component}",
            ErrorCategory.FILE_SYSTEM: f"File system errors affecting {most_common_component}",
            ErrorCategory.UNKNOWN: f"Recurring errors in {most_common_component}",
        }

        base_description = category_descriptions.get(
            signature.category,
            f"Error pattern in {most_common_component}"
        )

        # Add frequency information
        if len(entries) > 10:
            base_description += f" (high frequency: {len(entries)} occurrences)"
        elif len(entries) > 5:
            base_description += f" (moderate frequency: {len(entries)} occurrences)"

        return base_description

    def _calculate_confidence(self, entries: List[LogEntry]) -> float:
        """Calculate confidence score for a pattern."""
        base_confidence = 0.5

        # Increase confidence based on occurrence count
        if len(entries) >= 10:
            base_confidence += 0.3
        elif len(entries) >= 5:
            base_confidence += 0.2
        elif len(entries) >= 3:
            base_confidence += 0.1

        # Increase confidence if errors are consistent
        messages = [e.message for e in entries]
        unique_messages = set(messages)
        consistency_ratio = 1.0 - (len(unique_messages) / len(messages))
        base_confidence += consistency_ratio * 0.2

        return min(base_confidence, 1.0)

    def _extract_indicators(self, entries: List[LogEntry]) -> List[str]:
        """Extract indicator keywords from entries."""
        indicators = []

        # Extract common words from error messages
        all_words = []
        for entry in entries:
            words = re.findall(r'\b\w+\b', entry.message.lower())
            all_words.extend(words)

        # Find most common significant words
        word_counts = Counter(all_words)
        # Filter out common words
        stop_words = {
            'the', 'is', 'at', 'to', 'from', 'and', 'or', 'but',
            'in', 'on', 'with', 'for', 'of', 'a', 'an', 'error',
            'warning', 'failed', 'unable', 'could', 'not'
        }

        significant_words = [
            word for word, count in word_counts.most_common(10)
            if word not in stop_words and len(word) > 3 and count >= 2
        ]

        indicators.extend(significant_words[:5])

        # Add special indicators
        if any("timeout" in e.message.lower() for e in entries):
            indicators.append("timeout_detected")
        if any("retry" in e.message.lower() for e in entries):
            indicators.append("retry_pattern")
        if any("exception" in e.message.lower() for e in entries):
            indicators.append("exception_thrown")

        return indicators

    def detect_cascading_failures(
        self, entries: List[LogEntry]
    ) -> List[Tuple[LogEntry, List[LogEntry]]]:
        """
        Detect cascading failures where one error triggers others.

        Args:
            entries: List of log entries

        Returns:
            List of tuples (root_error, consequent_errors)
        """
        cascades = []

        # Filter out entries without timestamps
        entries_with_time = [e for e in entries if e.timestamp is not None]
        if not entries_with_time:
            return cascades

        # Sort entries by timestamp
        sorted_entries = sorted(entries_with_time, key=lambda e: e.timestamp)

        for i, entry in enumerate(sorted_entries):
            if not entry.is_error:
                continue

            # Look for errors in the next 30 seconds
            cascade_window = timedelta(seconds=30)
            consequent_errors = []

            for j in range(i + 1, len(sorted_entries)):
                if sorted_entries[j].timestamp - entry.timestamp > cascade_window:
                    break

                if sorted_entries[j].is_error:
                    # Check if potentially related
                    if self._are_related(entry, sorted_entries[j]):
                        consequent_errors.append(sorted_entries[j])

            if consequent_errors:
                cascades.append((entry, consequent_errors))

        return cascades

    def _are_related(self, entry1: LogEntry, entry2: LogEntry) -> bool:
        """Check if two log entries are potentially related."""
        # Same component is a strong indicator
        if entry1.component == entry2.component:
            return True

        # Check for correlation IDs
        if entry1.correlation_id and entry1.correlation_id == entry2.correlation_id:
            return True

        # Check for common keywords
        words1 = set(entry1.message.lower().split())
        words2 = set(entry2.message.lower().split())
        common_words = words1 & words2

        # If significant overlap, consider related
        if len(common_words) >= 3:
            return True

        return False