"""
Compliance Manager for Data Protection

This module ensures compliance with data protection requirements, preventing
storage of sensitive log data and maintaining audit trails for compliance verification.

Security Design:
- Ensures zero raw log storage in database
- Validates all data before persistence
- Automated compliance testing
- Comprehensive audit trails
- Data retention policy enforcement
- Regular compliance verification
"""

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from pathlib import Path
import asyncio
from collections import deque
import re

from app.agents.log_analysis.log_analysis_agent.utils import extract_json_payload

logger = logging.getLogger(__name__)


class ComplianceStatus(Enum):
    """Compliance check status with severity ordering."""
    COMPLIANT = "compliant"
    WARNING = "warning"
    NON_COMPLIANT = "non_compliant"
    UNKNOWN = "unknown"

    def severity_level(self) -> int:
        """Return numeric severity level for comparison."""
        severity_map = {
            ComplianceStatus.COMPLIANT: 0,
            ComplianceStatus.WARNING: 1,
            ComplianceStatus.NON_COMPLIANT: 2,
            ComplianceStatus.UNKNOWN: 3
        }
        return severity_map.get(self, 3)


class DataClassification(Enum):
    """Data classification levels."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


@dataclass
class ComplianceConfig:
    """Configuration for compliance manager."""
    enforce_zero_log_storage: bool = True  # Never store raw logs
    max_metadata_retention_days: int = 90  # Metadata retention period
    require_encryption_at_rest: bool = True
    require_audit_trail: bool = True
    enable_automated_checks: bool = True
    check_interval_seconds: int = 3600  # How often to run checks
    max_session_data_size: int = 1024 * 1024  # 1MB max for session data
    prohibited_fields: Set[str] = field(default_factory=lambda: {
        'password', 'secret', 'token', 'api_key', 'credit_card',
        'ssn', 'email', 'ip_address', 'raw_log', 'log_content'
    })
    paranoid_mode: bool = True


@dataclass
class ComplianceReport:
    """Compliance check report."""
    timestamp: datetime
    status: ComplianceStatus
    checks_performed: List[str]
    issues_found: List[str]
    recommendations: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class ComplianceManager:
    """
    Manages compliance with data protection requirements.

    Ensures that no sensitive log data is persisted while maintaining
    necessary metadata for system operation.
    """

    def __init__(self, config: Optional[ComplianceConfig] = None):
        """
        Initialize compliance manager.

        Args:
            config: Optional configuration
        """
        self.config = config or ComplianceConfig()
        self._audit_trail = deque(maxlen=10000)
        self._compliance_cache = {}
        self._automated_check_task = None
        self._violation_count = 0
        self._background_loop: Optional[asyncio.AbstractEventLoop] = None
        self._background_thread: Optional[threading.Thread] = None

        if self.config.enable_automated_checks:
            self._start_automated_checks()

        logger.info("ComplianceManager initialized with paranoid settings")

    def _start_automated_checks(self):
        """Start automated compliance monitoring."""
        async def run_checks():
            while True:
                try:
                    await asyncio.sleep(self.config.check_interval_seconds)
                    report = self.run_compliance_check()
                    if report.status == ComplianceStatus.NON_COMPLIANT:
                        logger.error(f"Compliance violation detected: {report.issues_found}")
                        self._violation_count += 1
                except asyncio.CancelledError:
                    logger.info("Automated compliance checks cancelled")
                    break
                except Exception as e:
                    logger.error(f"Automated compliance check failed: {e}")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            self._automated_check_task = loop.create_task(run_checks())
        else:
            self._background_loop = asyncio.new_event_loop()
            self._background_thread = threading.Thread(
                target=self._run_background_loop,
                args=(self._background_loop,),
                daemon=True,
            )
            self._background_thread.start()
            self._automated_check_task = asyncio.run_coroutine_threadsafe(
                run_checks(), self._background_loop
            )

    def _run_background_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def validate_for_storage(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate data before storage to ensure compliance.

        Args:
            data: Data to validate

        Returns:
            Tuple of (is_compliant, list of issues)
        """
        issues = []

        # Normalize input to a dict, attempting JSON extraction for string payloads.
        normalized_data: Dict[str, Any]
        if isinstance(data, str):
            parsed = extract_json_payload(data, logger_instance=logger)
            normalized_data = parsed if isinstance(parsed, dict) else {"raw_input": data}
        elif isinstance(data, dict):
            normalized_data = data
        else:
            normalized_data = {"raw_input": data}
        data = normalized_data

        # Check for prohibited fields
        prohibited_found = self._check_prohibited_fields(data)
        if prohibited_found:
            issues.append(f"Prohibited fields found: {prohibited_found}")

        # Check for raw log content
        if self.config.enforce_zero_log_storage:
            if self._contains_raw_logs(data):
                issues.append("Raw log content detected in data")

        # Check data size
        data_size = len(json.dumps(data, default=str))
        if data_size > self.config.max_session_data_size:
            issues.append(f"Data size exceeds limit: {data_size} bytes")

        # Check for sensitive patterns
        sensitive_patterns = self._detect_sensitive_patterns(data)
        if sensitive_patterns:
            issues.append(f"Sensitive patterns detected: {sensitive_patterns}")

        # Audit the validation
        self._audit_validation(data, issues)

        return len(issues) == 0, issues

    def _check_prohibited_fields(self, data: Dict, path: str = "") -> List[str]:
        """Recursively check for prohibited fields."""
        prohibited_found = []

        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key

            # Check if field name contains prohibited terms
            key_lower = key.lower()
            for prohibited in self.config.prohibited_fields:
                if prohibited in key_lower:
                    prohibited_found.append(current_path)
                    break

            # Recursively check nested structures
            if isinstance(value, dict):
                prohibited_found.extend(self._check_prohibited_fields(value, current_path))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        prohibited_found.extend(
                            self._check_prohibited_fields(item, f"{current_path}[{i}]")
                        )

        return prohibited_found

    def _contains_raw_logs(self, data: Any) -> bool:
        """Check if data contains raw log content."""
        if isinstance(data, str):
            # Check for log-like patterns
            log_patterns = [
                r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}',  # Timestamps
                r'(?:ERROR|WARN|INFO|DEBUG|TRACE)\s*:',  # Log levels
                r'at\s+\w+\.\w+\(',  # Stack traces
                r'Exception|Error|Traceback',  # Error indicators
            ]

            # If multiple log patterns match, likely raw log
            matches = sum(1 for pattern in log_patterns if re.search(pattern, data))
            if matches >= 2 and len(data) > 500:
                return True

        elif isinstance(data, dict):
            for value in data.values():
                if self._contains_raw_logs(value):
                    return True
        elif isinstance(data, list):
            for item in data:
                if self._contains_raw_logs(item):
                    return True

        return False

    def _detect_sensitive_patterns(self, data: Any) -> List[str]:
        """Detect sensitive data patterns."""
        sensitive_found = []

        def check_string(s: str, location: str):
            patterns = {
                'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                'api_key': r'(?i)(?:api[_-]?key|token)\s*[:=]\s*["\']?[A-Za-z0-9+/=_-]{20,}',
                'credit_card': r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
                'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
                'ip_address': r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
            }

            for pattern_name, pattern in patterns.items():
                if re.search(pattern, s):
                    sensitive_found.append(f"{pattern_name} at {location}")

        def traverse(obj, path="root"):
            if isinstance(obj, str):
                check_string(obj, path)
            elif isinstance(obj, dict):
                for key, value in obj.items():
                    traverse(value, f"{path}.{key}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    traverse(item, f"{path}[{i}]")

        traverse(data)
        return sensitive_found

    def sanitize_session_data(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize session data for compliant storage.

        Args:
            session_data: Raw session data

        Returns:
            Sanitized session data
        """
        sanitized = {}

        # Whitelist of safe fields
        safe_fields = {
            'session_id', 'user_id', 'timestamp', 'status',
            'error_count', 'warning_count', 'info_count',
            'analysis_complete', 'quality_score', 'response_format'
        }

        # Copy only safe fields
        for field in safe_fields:
            if field in session_data:
                sanitized[field] = session_data[field]

        # Add metadata hash instead of raw content
        if 'log_content' in session_data:
            serialized_content = self._serialize_log_content(session_data['log_content'])
            sanitized['content_hash'] = hashlib.sha256(serialized_content).hexdigest()[:16]
            sanitized['content_size'] = len(serialized_content)

        # Add sanitized summary
        if 'analysis_result' in session_data:
            sanitized['analysis_summary'] = self._create_safe_summary(
                session_data['analysis_result']
            )

        return sanitized

    def _create_safe_summary(self, analysis_result: Any) -> Dict[str, Any]:
        """Create a safe summary of analysis results."""
        summary = {
            'timestamp': datetime.now().isoformat(),
            'has_errors': False,
            'has_warnings': False,
            'issue_categories': [],
            'recommendation_count': 0
        }

        if isinstance(analysis_result, dict):
            # Extract safe metadata
            if 'errors' in analysis_result:
                summary['has_errors'] = len(analysis_result['errors']) > 0
                summary['error_count'] = len(analysis_result['errors'])

            if 'warnings' in analysis_result:
                summary['has_warnings'] = len(analysis_result['warnings']) > 0
                summary['warning_count'] = len(analysis_result['warnings'])

            if 'categories' in analysis_result:
                # Store only category names, not content
                summary['issue_categories'] = list(analysis_result['categories'])

            if 'recommendations' in analysis_result:
                summary['recommendation_count'] = len(analysis_result['recommendations'])

        return summary

    def validate_attachment_handling(self, attachment_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate attachment handling for compliance.

        Args:
            attachment_data: Attachment metadata

        Returns:
            Tuple of (is_compliant, issues)
        """
        issues = []

        # Ensure no raw attachment data
        if 'raw_data' in attachment_data or 'file_content' in attachment_data:
            issues.append("Raw attachment data found")

        # Ensure no full file paths (privacy concern)
        if 'file_path' in attachment_data:
            path = str(attachment_data['file_path'])
            lowered = path.lower()
            risky_segments = (
                '/home/',
                '/users/',
                '\\users\\',
                ':\\users\\',
            )
            if (
                any(segment in lowered for segment in risky_segments)
                or path.startswith('\\\\')
            ):
                issues.append("Full file path with user information detected")

        # Check for base64 encoded content
        for value in attachment_data.values():
            # Only check string values
            if isinstance(value, str):
                if len(value) > 1000 and re.search(r'[A-Za-z0-9+/]+=*', value):
                    issues.append("Possible base64 encoded content detected")
                    break

        return len(issues) == 0, issues

    def stop_automated_checks(self) -> None:
        """Cancel automated compliance checks and stop background loop."""
        task = self._automated_check_task
        self._automated_check_task = None

        if task is not None:
            try:
                if isinstance(task, asyncio.Task):
                    loop = task.get_loop()
                    loop.call_soon_threadsafe(task.cancel)
                else:
                    task.cancel()
            except Exception:
                logger.debug("Failed to cancel automated compliance task", exc_info=True)

            if hasattr(task, "result"):
                try:
                    task.result(timeout=1)
                except Exception:
                    pass

        if self._background_loop:
            loop = self._background_loop
            loop.call_soon_threadsafe(loop.stop)
            if self._background_thread and self._background_thread.is_alive():
                self._background_thread.join(timeout=1)
            self._background_loop = None
            self._background_thread = None

    def __del__(self):  # pragma: no cover - defensive cleanup
        try:
            self.stop_automated_checks()
        except Exception:
            pass

    def _escalate_status(self, current: ComplianceStatus, new: ComplianceStatus) -> ComplianceStatus:
        """
        Escalate compliance status monotonically.

        Args:
            current: Current status
            new: New status to consider

        Returns:
            The more severe status
        """
        if new.severity_level() > current.severity_level():
            return new
        return current

    def enforce_retention_policy(self, data_age_days: int) -> bool:
        """
        Check if data should be retained based on policy.

        Args:
            data_age_days: Age of data in days

        Returns:
            True if data should be deleted
        """
        return data_age_days > self.config.max_metadata_retention_days

    def run_compliance_check(self) -> ComplianceReport:
        """
        Run comprehensive compliance check.

        Returns:
            Compliance report
        """
        checks_performed = []
        issues_found = []
        recommendations = []
        status = ComplianceStatus.COMPLIANT

        # Check 1: Zero log storage enforcement
        checks_performed.append("Zero log storage enforcement")
        # This would check actual database in production
        # For now, we check configuration
        if not self.config.enforce_zero_log_storage:
            issues_found.append("Zero log storage not enforced")
            status = self._escalate_status(status, ComplianceStatus.NON_COMPLIANT)

        # Check 2: Encryption at rest
        checks_performed.append("Encryption at rest requirement")
        if not self.config.require_encryption_at_rest:
            issues_found.append("Encryption at rest not required")
            recommendations.append("Enable encryption at rest for all stored data")
            status = self._escalate_status(status, ComplianceStatus.WARNING)

        # Check 3: Audit trail
        checks_performed.append("Audit trail requirement")
        if not self.config.require_audit_trail:
            issues_found.append("Audit trail not required")
            recommendations.append("Enable comprehensive audit logging")
            status = self._escalate_status(status, ComplianceStatus.WARNING)

        # Check 4: Retention policy
        checks_performed.append("Data retention policy")
        if self.config.max_metadata_retention_days > 365:
            issues_found.append(f"Retention period too long: {self.config.max_metadata_retention_days} days")
            recommendations.append("Reduce retention period to minimize data exposure")
            status = self._escalate_status(status, ComplianceStatus.WARNING)

        # Check 5: Prohibited fields configuration
        checks_performed.append("Prohibited fields configuration")
        if len(self.config.prohibited_fields) < 5:
            recommendations.append("Consider expanding prohibited fields list")

        # Check 6: Paranoid mode
        checks_performed.append("Security mode check")
        if not self.config.paranoid_mode:
            issues_found.append("Not running in paranoid mode")
            recommendations.append("Enable paranoid mode for maximum security")
            status = self._escalate_status(status, ComplianceStatus.NON_COMPLIANT)

        # Create report
        report = ComplianceReport(
            timestamp=datetime.now(),
            status=status,
            checks_performed=checks_performed,
            issues_found=issues_found,
            recommendations=recommendations,
            metadata={
                'violation_count': self._violation_count,
                'config_hash': self._get_config_hash()
            }
        )

        # Audit the compliance check
        self._audit_compliance_check(report)

        return report

    def _get_config_hash(self) -> str:
        """Get hash of current configuration for verification."""
        config_dict = asdict(self.config)
        config_str = json.dumps(config_dict, sort_keys=True, default=str)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]

    def _audit_validation(self, data: Dict[str, Any], issues: List[str]):
        """Audit data validation event."""
        audit_entry = {
            'timestamp': datetime.now().isoformat(),
            'event': 'data_validation',
            'data_hash': hashlib.sha256(str(data).encode()).hexdigest()[:16],
            'compliant': len(issues) == 0,
            'issues': issues
        }
        self._audit_trail.append(audit_entry)

        if issues and self.config.paranoid_mode:
            logger.warning(f"Compliance validation failed: {issues}")

    def _audit_compliance_check(self, report: ComplianceReport):
        """Audit compliance check event."""
        audit_entry = {
            'timestamp': report.timestamp.isoformat(),
            'event': 'compliance_check',
            'status': report.status.value,
            'issues_found': len(report.issues_found),
            'recommendations': len(report.recommendations)
        }
        self._audit_trail.append(audit_entry)

    def get_audit_trail(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent audit trail entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of audit entries
        """
        return list(self._audit_trail)[-limit:]

    def export_compliance_report(self, filepath: Optional[Path] = None) -> str:
        """
        Export comprehensive compliance report.

        Args:
            filepath: Optional path to save report

        Returns:
            Report as JSON string
        """
        report = self.run_compliance_check()

        full_report = {
            'generated_at': datetime.now().isoformat(),
            'compliance_status': report.status.value,
            'configuration': {
                'enforce_zero_log_storage': self.config.enforce_zero_log_storage,
                'max_metadata_retention_days': self.config.max_metadata_retention_days,
                'require_encryption_at_rest': self.config.require_encryption_at_rest,
                'paranoid_mode': self.config.paranoid_mode
            },
            'current_report': asdict(report),
            'recent_audit_trail': self.get_audit_trail(50),
            'statistics': {
                'total_validations': len([e for e in self._audit_trail if e.get('event') == 'data_validation']),
                'failed_validations': len([e for e in self._audit_trail if e.get('event') == 'data_validation' and not e.get('compliant')]),
                'compliance_checks': len([e for e in self._audit_trail if e.get('event') == 'compliance_check']),
                'violation_count': self._violation_count
            }
        }

        report_json = json.dumps(full_report, indent=2, default=str)

        if filepath:
            filepath.write_text(report_json)
            logger.info(f"Compliance report exported to {filepath}")

        return report_json
