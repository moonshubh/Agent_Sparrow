"""
Root Cause Classifier for Log Analysis

This module implements intelligent root cause analysis by correlating
error patterns, metadata, and contextual information to identify
the underlying causes of issues in Mailbird logs.
"""

import logging
from typing import List, Dict, Optional, Tuple, Set, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import Counter

from ..schemas.log_schemas import (
    RootCause,
    ErrorPattern,
    ErrorCategory,
    IssueImpact,
    LogMetadata,
    UserContext,
)

logger = logging.getLogger(__name__)


@dataclass
class RootCauseHypothesis:
    """Represents a hypothesis for a root cause."""

    title: str
    category: ErrorCategory
    confidence: float
    evidence: List[str]
    resolution_steps: List[str]
    impact: IssueImpact = IssueImpact.MEDIUM
    affected_features: List[str] = None
    preventive_measures: List[str] = None

    def __post_init__(self):
        """Initialize default values for mutable attributes."""
        if self.affected_features is None:
            self.affected_features = []
        if self.preventive_measures is None:
            self.preventive_measures = []


class RootCauseClassifier:
    """
    Classifies and identifies root causes from error patterns and metadata.

    This class implements a rule-based system with heuristics to determine
    the most likely root causes of issues observed in Mailbird logs.
    """

    # Known root cause patterns for Mailbird
    KNOWN_ROOT_CAUSES = {
        "oauth_token_expired": {
            "indicators": ["401", "unauthorized", "token", "expired", "oauth"],
            "category": ErrorCategory.AUTHENTICATION,
            "impact": IssueImpact.HIGH,
            "resolution": [
                "Re-authenticate the affected email account",
                "Go to Settings → Accounts → Select account → Re-enter credentials",
                "Complete the OAuth flow in your browser",
                "Verify the account syncs successfully",
            ],
            "prevention": [
                "Enable automatic token refresh if available",
                "Check account settings regularly",
                "Update to latest Mailbird version for improved OAuth handling",
            ],
        },
        "imap_connection_blocked": {
            "indicators": ["imap", "connection", "refused", "timeout", "port"],
            "category": ErrorCategory.NETWORK,
            "impact": IssueImpact.HIGH,
            "resolution": [
                "Check firewall settings for IMAP ports (993 for SSL, 143 for non-SSL)",
                "Temporarily disable antivirus email scanning",
                "Verify IMAP server settings are correct",
                "Test connection with telnet to IMAP server",
            ],
            "prevention": [
                "Add Mailbird to firewall exceptions",
                "Configure antivirus to allow Mailbird",
                "Use recommended server settings from email provider",
            ],
        },
        "database_corruption": {
            "indicators": ["database", "corrupt", "locked", "sqlite", "integrity"],
            "category": ErrorCategory.DATABASE,
            "impact": IssueImpact.CRITICAL,
            "resolution": [
                "Close Mailbird completely",
                "Navigate to %APPDATA%/Mailbird/Store",
                "Rename mailbird.db to mailbird.db.backup",
                "Restart Mailbird to rebuild database",
                "Re-sync email accounts",
            ],
            "prevention": [
                "Regular database optimization",
                "Avoid force-closing Mailbird",
                "Ensure adequate disk space",
                "Regular backups of Mailbird data",
            ],
        },
        "memory_leak": {
            "indicators": ["memory", "heap", "allocation", "exhausted", "oom"],
            "category": ErrorCategory.MEMORY,
            "impact": IssueImpact.HIGH,
            "resolution": [
                "Restart Mailbird to free memory",
                "Reduce number of simultaneous accounts",
                "Clear email cache in Settings",
                "Disable memory-intensive features temporarily",
            ],
            "prevention": [
                "Limit attachment preview sizes",
                "Regular application restarts",
                "Monitor memory usage patterns",
                "Update to latest version with memory fixes",
            ],
        },
        "sync_conflict": {
            "indicators": ["sync", "conflict", "duplicate", "mismatch", "version"],
            "category": ErrorCategory.SYNCHRONIZATION,
            "impact": IssueImpact.MEDIUM,
            "resolution": [
                "Force full re-sync of affected folders",
                "Clear local cache for the account",
                "Check for duplicate messages",
                "Verify server-side folder structure",
            ],
            "prevention": [
                "Avoid using multiple email clients simultaneously",
                "Regular sync interval adjustments",
                "Keep Mailbird as primary email client",
            ],
        },
        "ssl_certificate_issue": {
            "indicators": ["ssl", "certificate", "tls", "handshake", "verification"],
            "category": ErrorCategory.NETWORK,
            "impact": IssueImpact.HIGH,
            "resolution": [
                "Update system date and time",
                "Clear SSL certificate cache",
                "Import server certificate if self-signed",
                "Update Windows root certificates",
            ],
            "prevention": [
                "Keep system time synchronized",
                "Regular Windows updates",
                "Use recommended SSL/TLS settings",
            ],
        },
        "disk_space_low": {
            "indicators": ["disk", "space", "full", "storage", "write failed"],
            "category": ErrorCategory.FILE_SYSTEM,
            "impact": IssueImpact.CRITICAL,
            "resolution": [
                "Free up disk space immediately",
                "Clear Mailbird cache and temp files",
                "Move Mailbird data to another drive",
                "Clean up old email attachments",
            ],
            "prevention": [
                "Monitor disk space regularly",
                "Set up automatic cleanup rules",
                "Archive old emails",
                "Configure attachment storage limits",
            ],
        },
    }

    def __init__(self):
        """Initialize the root cause classifier."""
        self._hypothesis_cache: Dict[str, RootCauseHypothesis] = {}

    def classify(
        self,
        patterns: List[ErrorPattern],
        metadata: LogMetadata,
        user_context: Optional[UserContext] = None,
    ) -> List[RootCause]:
        """
        Classify root causes from error patterns and metadata.

        Args:
            patterns: Detected error patterns
            metadata: Log metadata
            user_context: Optional user-provided context

        Returns:
            List of identified root causes sorted by confidence
        """
        root_causes = []

        # Generate hypotheses from patterns
        hypotheses = self._generate_hypotheses(patterns, metadata, user_context)

        # Correlate and validate hypotheses
        validated_hypotheses = self._validate_hypotheses(hypotheses, patterns, metadata)

        # Convert to RootCause objects
        for i, hypothesis in enumerate(validated_hypotheses, 1):
            root_cause = self._hypothesis_to_root_cause(
                hypothesis,
                cause_id=f"RC-{i:03d}",
                patterns=patterns,
            )
            root_causes.append(root_cause)

        # Apply user context if available
        if user_context:
            root_causes = self._apply_user_context(root_causes, user_context)

        # Sort by confidence and impact
        root_causes.sort(
            key=lambda rc: (rc.impact.numeric_score, rc.confidence_score),
            reverse=True,
        )

        return root_causes

    def _generate_hypotheses(
        self,
        patterns: List[ErrorPattern],
        metadata: LogMetadata,
        user_context: Optional[UserContext],
    ) -> List[RootCauseHypothesis]:
        """Generate root cause hypotheses from available data."""
        hypotheses = []

        # Check against known root causes
        for cause_key, cause_data in self.KNOWN_ROOT_CAUSES.items():
            confidence = self._calculate_hypothesis_confidence(
                cause_data["indicators"],
                patterns,
                metadata,
            )

            if confidence > 0.3:  # Minimum threshold
                hypothesis = RootCauseHypothesis(
                    title=self._humanize_cause_title(cause_key),
                    category=cause_data["category"],
                    confidence=confidence,
                    evidence=self._gather_evidence(
                        cause_data["indicators"],
                        patterns,
                    ),
                    resolution_steps=cause_data["resolution"],
                    impact=cause_data["impact"],
                    preventive_measures=cause_data["prevention"],
                    affected_features=self._identify_affected_features(
                        patterns, cause_data["indicators"]
                    ),
                )
                hypotheses.append(hypothesis)

        # Generate additional hypotheses from pattern analysis
        pattern_hypotheses = self._generate_pattern_hypotheses(patterns)
        hypotheses.extend(pattern_hypotheses)

        # Generate metadata-based hypotheses
        metadata_hypotheses = self._generate_metadata_hypotheses(metadata)
        hypotheses.extend(metadata_hypotheses)

        return hypotheses

    def _calculate_hypothesis_confidence(
        self,
        indicators: List[str],
        patterns: List[ErrorPattern],
        metadata: LogMetadata,
    ) -> float:
        """Calculate confidence score for a hypothesis."""
        confidence = 0.0
        indicator_matches = 0

        # Check pattern matches
        for pattern in patterns:
            pattern_text = (
                pattern.description.lower() +
                " ".join(pattern.indicators).lower() +
                " ".join(e.message.lower() for e in pattern.sample_entries)
            )

            for indicator in indicators:
                if indicator.lower() in pattern_text:
                    indicator_matches += 1
                    confidence += 0.1 * pattern.confidence

        # Boost confidence based on match ratio
        if indicators:
            match_ratio = indicator_matches / len(indicators)
            confidence += match_ratio * 0.3

        # Consider pattern frequency
        total_errors = sum(p.occurrences for p in patterns)
        if total_errors > 50:
            confidence += 0.1
        elif total_errors > 20:
            confidence += 0.05

        # Consider metadata factors
        if metadata.error_rate > 10:
            confidence += 0.1
        if metadata.database_size_mb and metadata.database_size_mb > 1000:
            confidence += 0.05

        return min(confidence, 1.0)

    def _gather_evidence(
        self,
        indicators: List[str],
        patterns: List[ErrorPattern],
    ) -> List[str]:
        """Gather evidence supporting a hypothesis."""
        evidence = []

        for pattern in patterns:
            # Check if pattern matches indicators
            pattern_text = pattern.description.lower() + " ".join(pattern.indicators).lower()

            matching_indicators = [
                ind for ind in indicators
                if ind.lower() in pattern_text
            ]

            if matching_indicators:
                evidence.append(
                    f"Pattern '{pattern.pattern_id}' shows {pattern.occurrences} "
                    f"occurrences of {', '.join(matching_indicators)}"
                )

                # Add sample error message
                if pattern.sample_entries:
                    sample = pattern.sample_entries[0]
                    evidence.append(
                        f"Sample error: {sample.message[:100]}..."
                        if len(sample.message) > 100
                        else f"Sample error: {sample.message}"
                    )

        return evidence[:5]  # Limit to 5 pieces of evidence

    def _humanize_cause_title(self, cause_key: str) -> str:
        """Convert cause key to human-readable title."""
        title_map = {
            "oauth_token_expired": "OAuth Authentication Token Expired",
            "imap_connection_blocked": "IMAP Connection Blocked by Firewall/Antivirus",
            "database_corruption": "Local Database Corruption Detected",
            "memory_leak": "Memory Leak Causing Performance Issues",
            "sync_conflict": "Email Synchronization Conflict",
            "ssl_certificate_issue": "SSL/TLS Certificate Problem",
            "disk_space_low": "Insufficient Disk Space",
        }
        return title_map.get(cause_key, cause_key.replace("_", " ").title())

    def _identify_affected_features(
        self, patterns: List[ErrorPattern], indicators: Optional[List[str]] = None
    ) -> List[str]:
        """Identify Mailbird features affected by patterns matching indicators."""
        affected = set()

        for pattern in patterns:
            # If indicators are provided, only process patterns matching them
            if indicators:
                pattern_text = (
                    pattern.description.lower() +
                    " ".join(pattern.indicators).lower()
                )
                # Check if pattern matches any of the indicators
                if not any(ind.lower() in pattern_text for ind in indicators):
                    continue

            components = pattern.affected_components

            # Map components to features
            for component in components:
                component_lower = component.lower()

                if "sync" in component_lower:
                    affected.add("Email Synchronization")
                if "ui" in component_lower or "window" in component_lower:
                    affected.add("User Interface")
                if "auth" in component_lower:
                    affected.add("Account Authentication")
                if "smtp" in component_lower:
                    affected.add("Email Sending")
                if "imap" in component_lower:
                    affected.add("Email Receiving")
                if "database" in component_lower or "db" in component_lower:
                    affected.add("Local Storage")
                if "calendar" in component_lower:
                    affected.add("Calendar Integration")
                if "contact" in component_lower:
                    affected.add("Contacts Management")

        return list(affected)

    def _generate_pattern_hypotheses(
        self,
        patterns: List[ErrorPattern],
    ) -> List[RootCauseHypothesis]:
        """Generate hypotheses directly from error patterns."""
        hypotheses = []

        # Group patterns by category
        category_groups = {}
        for pattern in patterns:
            if pattern.category not in category_groups:
                category_groups[pattern.category] = []
            category_groups[pattern.category].append(pattern)

        # Generate hypothesis for each significant category
        for category, category_patterns in category_groups.items():
            total_occurrences = sum(p.occurrences for p in category_patterns)

            if total_occurrences >= 5:  # Significant threshold
                hypothesis = self._create_category_hypothesis(
                    category,
                    category_patterns,
                )
                hypotheses.append(hypothesis)

        return hypotheses

    def _create_category_hypothesis(
        self,
        category: ErrorCategory,
        patterns: List[ErrorPattern],
    ) -> RootCauseHypothesis:
        """Create a hypothesis based on error category patterns."""
        total_occurrences = sum(p.occurrences for p in patterns)

        # Category-specific analysis
        if category == ErrorCategory.AUTHENTICATION:
            return RootCauseHypothesis(
                title="Authentication System Failure",
                category=category,
                confidence=min(0.6 + (total_occurrences / 100), 0.9),
                evidence=[f"{total_occurrences} authentication errors detected"],
                resolution_steps=[
                    "Check email account credentials",
                    "Verify OAuth tokens are valid",
                    "Re-authenticate affected accounts",
                ],
                impact=IssueImpact.HIGH,
            )
        elif category == ErrorCategory.NETWORK:
            return RootCauseHypothesis(
                title="Network Connectivity Issues",
                category=category,
                confidence=min(0.5 + (total_occurrences / 100), 0.85),
                evidence=[f"{total_occurrences} network errors detected"],
                resolution_steps=[
                    "Check internet connection",
                    "Verify firewall settings",
                    "Test email server connectivity",
                ],
                impact=IssueImpact.HIGH,
            )
        elif category == ErrorCategory.DATABASE:
            return RootCauseHypothesis(
                title="Database Performance Problems",
                category=category,
                confidence=min(0.7 + (total_occurrences / 50), 0.95),
                evidence=[f"{total_occurrences} database errors detected"],
                resolution_steps=[
                    "Optimize Mailbird database",
                    "Clear cache and temporary files",
                    "Check disk space availability",
                ],
                impact=IssueImpact.CRITICAL if total_occurrences > 20 else IssueImpact.MEDIUM,
            )
        else:
            return RootCauseHypothesis(
                title=f"{category.name.replace('_', ' ').title()} Issues",
                category=category,
                confidence=0.5,
                evidence=[f"{total_occurrences} errors in category"],
                resolution_steps=["Review detailed error logs", "Contact support if persistent"],
                impact=IssueImpact.MEDIUM,
            )

    def _generate_metadata_hypotheses(
        self,
        metadata: LogMetadata,
    ) -> List[RootCauseHypothesis]:
        """Generate hypotheses from metadata analysis."""
        hypotheses = []

        # Check for database size issues
        if metadata.database_size_mb and metadata.database_size_mb > 2000:
            hypothesis = RootCauseHypothesis(
                title="Database Size Exceeding Optimal Limits",
                category=ErrorCategory.DATABASE,
                confidence=0.7,
                evidence=[f"Database size: {metadata.database_size_mb:.0f} MB"],
                resolution_steps=[
                    "Archive old emails",
                    "Compact database in Settings",
                    "Delete unnecessary attachments",
                ],
                impact=IssueImpact.MEDIUM,
                preventive_measures=["Regular database maintenance", "Set up auto-archive rules"],
            )
            hypotheses.append(hypothesis)

        # Check for high error rate
        if metadata.error_rate > 15:
            hypothesis = RootCauseHypothesis(
                title="Systemic Instability Detected",
                category=ErrorCategory.UNKNOWN,
                confidence=0.6,
                evidence=[f"Error rate: {metadata.error_rate:.1f}%"],
                resolution_steps=[
                    "Update Mailbird to latest version",
                    "Check for Windows updates",
                    "Run system file checker (sfc /scannow)",
                ],
                impact=IssueImpact.HIGH,
            )
            hypotheses.append(hypothesis)

        # Check for multiple accounts
        if metadata.account_count > 5:
            hypothesis = RootCauseHypothesis(
                title="Performance Impact from Multiple Accounts",
                category=ErrorCategory.PERFORMANCE,
                confidence=0.5,
                evidence=[f"Managing {metadata.account_count} email accounts"],
                resolution_steps=[
                    "Reduce sync frequency for less important accounts",
                    "Disable unused accounts temporarily",
                    "Increase memory allocation for Mailbird",
                ],
                impact=IssueImpact.LOW,
            )
            hypotheses.append(hypothesis)

        return hypotheses

    def _validate_hypotheses(
        self,
        hypotheses: List[RootCauseHypothesis],
        patterns: List[ErrorPattern],
        metadata: LogMetadata,
    ) -> List[RootCauseHypothesis]:
        """Validate and filter hypotheses based on evidence strength."""
        validated = []

        for hypothesis in hypotheses:
            # Skip low confidence hypotheses
            if hypothesis.confidence < 0.4:
                continue

            # Boost confidence if multiple supporting patterns
            supporting_patterns = [
                p for p in patterns
                if p.category == hypothesis.category
            ]

            if len(supporting_patterns) >= 3:
                hypothesis.confidence = min(hypothesis.confidence + 0.1, 1.0)

            # Adjust based on metadata correlation
            if self._correlates_with_metadata(hypothesis, metadata):
                hypothesis.confidence = min(hypothesis.confidence + 0.05, 1.0)

            validated.append(hypothesis)

        # Remove duplicates and merge similar
        validated = self._merge_similar_hypotheses(validated)

        return validated

    def _correlates_with_metadata(
        self,
        hypothesis: RootCauseHypothesis,
        metadata: LogMetadata,
    ) -> bool:
        """Check if hypothesis correlates with metadata."""
        if hypothesis.category == ErrorCategory.MEMORY:
            return (
                metadata.memory_usage_mb is not None
                and metadata.memory_usage_mb > 500
            )

        if hypothesis.category == ErrorCategory.DATABASE:
            return (
                metadata.database_size_mb is not None
                and metadata.database_size_mb > 1000
            )

        if hypothesis.category == ErrorCategory.NETWORK:
            state = (metadata.network_state or "").lower()
            return state in {"offline", "disconnected"}

        return False

    def _merge_similar_hypotheses(
        self,
        hypotheses: List[RootCauseHypothesis],
    ) -> List[RootCauseHypothesis]:
        """Merge similar hypotheses to avoid duplicates."""
        merged = []
        seen_categories = set()

        for hypothesis in sorted(hypotheses, key=lambda h: h.confidence, reverse=True):
            # Simple deduplication by category for now
            key = (hypothesis.category, hypothesis.title[:20])
            if key not in seen_categories:
                seen_categories.add(key)
                merged.append(hypothesis)

        return merged

    def _hypothesis_to_root_cause(
        self,
        hypothesis: RootCauseHypothesis,
        cause_id: str,
        patterns: List[ErrorPattern],
    ) -> RootCause:
        """Convert a hypothesis to a RootCause object."""
        # Find related pattern IDs
        related_pattern_ids = [
            p.pattern_id for p in patterns
            if p.category == hypothesis.category
        ]

        # Estimate resolution time based on impact
        resolution_time_map = {
            IssueImpact.MINIMAL: 5,
            IssueImpact.LOW: 10,
            IssueImpact.MEDIUM: 20,
            IssueImpact.HIGH: 30,
            IssueImpact.CRITICAL: 45,
        }

        return RootCause(
            cause_id=cause_id,
            category=hypothesis.category,
            title=hypothesis.title,
            description=self._generate_cause_description(hypothesis),
            confidence_score=hypothesis.confidence,
            evidence=hypothesis.evidence,
            impact=hypothesis.impact,
            affected_features=hypothesis.affected_features,
            resolution_steps=hypothesis.resolution_steps,
            preventive_measures=hypothesis.preventive_measures,
            estimated_resolution_time=resolution_time_map.get(hypothesis.impact, 20),
            requires_user_action=True,
            requires_support=hypothesis.impact == IssueImpact.CRITICAL,
            related_patterns=related_pattern_ids,
        )

    def _generate_cause_description(self, hypothesis: RootCauseHypothesis) -> str:
        """Generate a detailed description of the root cause."""
        descriptions = {
            ErrorCategory.AUTHENTICATION: (
                "The authentication system is experiencing failures, preventing "
                "proper email account access. This typically occurs when credentials "
                "expire or authentication protocols change."
            ),
            ErrorCategory.NETWORK: (
                "Network connectivity issues are preventing Mailbird from "
                "communicating with email servers. This could be due to firewall "
                "settings, network configuration, or server availability."
            ),
            ErrorCategory.DATABASE: (
                "The local Mailbird database is experiencing performance issues "
                "or corruption. This affects email storage, search, and synchronization."
            ),
            ErrorCategory.SYNCHRONIZATION: (
                "Email synchronization between Mailbird and email servers is "
                "failing. This prevents new emails from appearing and changes "
                "from being saved."
            ),
            ErrorCategory.PERFORMANCE: (
                "System performance degradation is affecting Mailbird's responsiveness. "
                "This could be due to resource constraints or inefficient operations."
            ),
        }

        return descriptions.get(
            hypothesis.category,
            f"Issues detected in {hypothesis.category.name.lower()} operations "
            f"that require attention to restore normal functionality."
        )

    def _apply_user_context(
        self,
        root_causes: List[RootCause],
        user_context: UserContext,
    ) -> List[RootCause]:
        """Apply user context to refine root causes."""
        # Boost confidence if user report matches root cause
        for cause in root_causes:
            if self._matches_user_report(cause, user_context):
                cause.confidence_score = min(cause.confidence_score + 0.1, 1.0)
                summary = f"User reported: {user_context.reported_issue[:100]}"
                if not cause.evidence or cause.evidence[0] != summary:
                    cause.evidence.insert(0, summary)

            # Adjust impact based on business impact
            if user_context.business_impact and "critical" in user_context.business_impact.lower():
                if cause.impact != IssueImpact.CRITICAL:
                    cause.impact = IssueImpact.HIGH

            # Add attempted solutions to evidence
            if user_context.attempted_solutions:
                attempted = f"User already tried: {', '.join(user_context.attempted_solutions[:2])}"
                if attempted not in cause.evidence:
                    cause.evidence.append(attempted)

        root_causes.sort(
            key=lambda rc: (rc.impact.numeric_score, rc.confidence_score),
            reverse=True,
        )

        return root_causes

    def _matches_user_report(
        self,
        cause: RootCause,
        user_context: UserContext,
    ) -> bool:
        """Check if root cause matches user's reported issue."""
        if not user_context.reported_issue:
            return False

        report_lower = user_context.reported_issue.lower()

        # Check category-specific keywords
        keyword_map = {
            ErrorCategory.AUTHENTICATION: ["login", "password", "credential", "auth"],
            ErrorCategory.SYNCHRONIZATION: ["sync", "update", "refresh", "new email"],
            ErrorCategory.NETWORK: ["connection", "offline", "internet", "server"],
            ErrorCategory.DATABASE: ["slow", "frozen", "crash", "corrupt"],
            ErrorCategory.PERFORMANCE: ["slow", "lag", "freeze", "unresponsive"],
        }

        keywords = keyword_map.get(cause.category, [])
        return any(keyword in report_lower for keyword in keywords)
