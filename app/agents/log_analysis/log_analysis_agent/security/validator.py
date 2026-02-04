"""
Security Validator with Paranoid-Level Checks

This module implements comprehensive security validation for all inputs,
detecting malicious content, enforcing limits, and maintaining audit logs.

Security Design:
- Multi-layer validation for defense in depth
- Detection of injection attacks (SQL, XSS, Command, LDAP, etc.)
- File type and size validation
- Rate limiting and resource consumption checks
- Detailed security audit logging
- Fail-safe defaults (deny by default)
"""

import hashlib
import logging
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
import mimetypes
import chardet
from threading import Lock

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    """Security threat levels with comparison support."""

    CRITICAL = "critical"  # Immediate threat, block and alert
    HIGH = "high"  # Serious threat, block
    MEDIUM = "medium"  # Potential threat, sanitize
    LOW = "low"  # Minor concern, log
    NONE = "none"  # No threat detected

    @property
    def severity(self) -> int:
        """Return numeric severity for comparison."""
        severity_map = {
            ThreatLevel.NONE: 0,
            ThreatLevel.LOW: 1,
            ThreatLevel.MEDIUM: 2,
            ThreatLevel.HIGH: 3,
            ThreatLevel.CRITICAL: 4,
        }
        return severity_map.get(self, 0)

    def __lt__(self, other: "ThreatLevel") -> bool:
        """Compare threat levels by severity."""
        if not isinstance(other, ThreatLevel):
            return NotImplemented
        return self.severity < other.severity

    def __le__(self, other: "ThreatLevel") -> bool:
        """Compare threat levels by severity."""
        if not isinstance(other, ThreatLevel):
            return NotImplemented
        return self.severity <= other.severity

    def __gt__(self, other: "ThreatLevel") -> bool:
        """Compare threat levels by severity."""
        if not isinstance(other, ThreatLevel):
            return NotImplemented
        return self.severity > other.severity

    def __ge__(self, other: "ThreatLevel") -> bool:
        """Compare threat levels by severity."""
        if not isinstance(other, ThreatLevel):
            return NotImplemented
        return self.severity >= other.severity


class ValidationStatus(Enum):
    """Validation result status."""

    PASSED = "passed"
    FAILED = "failed"
    SUSPICIOUS = "suspicious"
    RATE_LIMITED = "rate_limited"


@dataclass
class ValidationConfig:
    """Configuration for security validator with paranoid defaults."""

    max_file_size: int = 10 * 1024 * 1024  # 10MB
    max_line_length: int = 10000  # Max characters per line
    max_lines: int = 100000  # Max lines per file
    allowed_extensions: Set[str] = field(
        default_factory=lambda: {".log", ".txt", ".text", ".logs"}
    )
    allowed_mime_types: Set[str] = field(
        default_factory=lambda: {"text/plain", "text/log", "application/octet-stream"}
    )
    enable_content_validation: bool = True
    enable_injection_detection: bool = True
    enable_rate_limiting: bool = True
    rate_limit_requests: int = 100  # Max requests per window
    rate_limit_window: int = 60  # Window in seconds
    enable_audit_logging: bool = True
    block_binary_content: bool = True
    max_nested_depth: int = 10  # Max nesting depth for structures
    paranoid_mode: bool = True  # Maximum security checks


@dataclass
class ValidationResult:
    """Result of security validation."""

    status: ValidationStatus
    threat_level: ThreatLevel
    issues: List[str] = field(default_factory=list)
    sanitized_content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class SecurityValidator:
    """
    Comprehensive security validator with paranoid-level checks.

    Implements multiple validation layers to detect and prevent various
    attack vectors while maintaining detailed audit logs.
    """

    # Injection attack patterns
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|FROM|WHERE|JOIN|ORDER\s+BY|GROUP\s+BY|HAVING)\b)",
        r"(--|\#|\/\*|\*\/)",  # SQL comments
        r"(\bOR\b\s*\d+\s*=\s*\d+)",  # OR 1=1
        r"(\bAND\b\s*\d+\s*=\s*\d+)",  # AND 1=1
        r"(;|--|\/\*|xp_|sp_|0x)",  # Common injection markers
        r"(CAST|CONVERT|CHAR|NCHAR|VARCHAR|NVARCHAR)",  # Type conversion
        r"(@@version|@@servername|db_name|user_name|system_user)",  # System functions
    ]

    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",  # Script tags
        r"javascript:",  # JavaScript protocol
        r"on\w+\s*=",  # Event handlers
        r"<iframe[^>]*>",  # Iframes
        r"<embed[^>]*>",  # Embed tags
        r"<object[^>]*>",  # Object tags
        r"<img[^>]*onerror[^>]*>",  # Image with error handler
        r"<svg[^>]*onload[^>]*>",  # SVG with load handler
        r"eval\s*\(",  # Eval function
        r"expression\s*\(",  # CSS expression
        r"vbscript:",  # VBScript protocol
        r"<link[^>]*href[^>]*>",  # Link tags
    ]

    COMMAND_INJECTION_PATTERNS = [
        r"(\||;|&|`|\$\(|\))",  # Command separators
        r"(>|>>|<|<<)",  # Redirections
        r"\b(cat|ls|dir|pwd|whoami|id|uname|ifconfig|netstat|ps|kill|rm|mv|cp|chmod|chown)\b",  # Common commands
        r"(\.\.\/|\.\.\\)",  # Directory traversal
        r"(/etc/passwd|/etc/shadow|C:\\Windows\\System32)",  # System files
        r"(curl|wget|nc|netcat|telnet|ssh|ftp)",  # Network commands
        r"(bash|sh|cmd|powershell|python|perl|ruby|php)",  # Interpreters
    ]

    LDAP_INJECTION_PATTERNS = [
        r"[()&|!*]",  # LDAP special characters
        r"(\(|\))\s*\(",  # Nested parentheses
        r"(cn=|ou=|dc=|uid=|mail=)",  # LDAP attributes
    ]

    XXE_PATTERNS = [
        r"<!DOCTYPE[^>]*>",  # DOCTYPE declarations
        r"<!ENTITY[^>]*>",  # Entity declarations
        r"<\?xml[^>]*>",  # XML declarations
        r"SYSTEM\s+[\"']",  # System entities
        r"PUBLIC\s+[\"']",  # Public entities
        r"file:\/\/",  # File protocol
        r"php:\/\/",  # PHP protocol
        r"data:\/\/",  # Data protocol
    ]

    PATH_TRAVERSAL_PATTERNS = [
        r"\.\.\/|\.\.\\",  # Parent directory
        r"\/\.\.\/|\\\.\.\\",  # Directory traversal
        r"%2e%2e%2f|%2e%2e%5c",  # URL encoded
        r"..%252f|..%255c",  # Double URL encoded
        r"\.\./|\.\./",  # Unicode variants
    ]

    def __init__(self, config: Optional[ValidationConfig] = None):
        """
        Initialize security validator with paranoid defaults.

        Args:
            config: Optional configuration
        """
        self.config = config or ValidationConfig()
        self._rate_limiter = (
            RateLimiter(self.config.rate_limit_requests, self.config.rate_limit_window)
            if self.config.enable_rate_limiting
            else None
        )
        self._audit_log = (
            SecurityAuditLog() if self.config.enable_audit_logging else None
        )
        self._compiled_patterns = self._compile_patterns()

        logger.info("SecurityValidator initialized with paranoid settings")

    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Compile all security patterns for efficiency."""
        patterns = {}

        if self.config.enable_injection_detection:
            patterns["sql"] = [
                re.compile(p, re.IGNORECASE) for p in self.SQL_INJECTION_PATTERNS
            ]
            patterns["xss"] = [
                re.compile(p, re.IGNORECASE | re.DOTALL) for p in self.XSS_PATTERNS
            ]
            patterns["command"] = [
                re.compile(p, re.IGNORECASE) for p in self.COMMAND_INJECTION_PATTERNS
            ]
            patterns["ldap"] = [re.compile(p) for p in self.LDAP_INJECTION_PATTERNS]
            patterns["xxe"] = [re.compile(p, re.IGNORECASE) for p in self.XXE_PATTERNS]
            patterns["path"] = [
                re.compile(p, re.IGNORECASE) for p in self.PATH_TRAVERSAL_PATTERNS
            ]

        return patterns

    def validate_file(
        self, file_path: Path, content: Optional[bytes] = None
    ) -> ValidationResult:
        """
        Comprehensive file validation with paranoid checks.

        Args:
            file_path: Path to file
            content: Optional file content (if already read)

        Returns:
            Validation result with detailed findings
        """
        issues = []
        threat_level = ThreatLevel.NONE

        try:
            # Rate limiting check
            if self._rate_limiter and not self._rate_limiter.check_request(
                str(file_path)
            ):
                return ValidationResult(
                    status=ValidationStatus.RATE_LIMITED,
                    threat_level=ThreatLevel.MEDIUM,
                    issues=["Rate limit exceeded"],
                )

            # File extension validation
            if not self._validate_extension(file_path):
                issues.append(f"Invalid file extension: {file_path.suffix}")
                threat_level = ThreatLevel.HIGH

            # File size validation
            file_size = (
                file_path.stat().st_size if file_path.exists() else len(content or b"")
            )
            if file_size > self.config.max_file_size:
                issues.append(f"File too large: {file_size} bytes")
                threat_level = ThreatLevel.HIGH

            if file_size == 0:
                issues.append("Empty file")
                threat_level = ThreatLevel.LOW

            # Read content if not provided
            if content is None and file_path.exists():
                content = file_path.read_bytes()

            # MIME type validation
            mime_issues, mime_threat = self._validate_mime_type(file_path, content)
            issues.extend(mime_issues)
            threat_level = max(threat_level, mime_threat, key=lambda t: t.severity)

            # Content validation
            if self.config.enable_content_validation and content:
                content_issues, content_threat = self._validate_content(content)
                issues.extend(content_issues)
                threat_level = max(
                    threat_level, content_threat, key=lambda t: t.severity
                )

            # Determine final status
            if threat_level in [ThreatLevel.CRITICAL, ThreatLevel.HIGH]:
                status = ValidationStatus.FAILED
            elif threat_level == ThreatLevel.MEDIUM or issues:
                status = ValidationStatus.SUSPICIOUS
            else:
                status = ValidationStatus.PASSED

            # Log audit event
            if self._audit_log:
                self._audit_log.log_validation(file_path, status, threat_level, issues)

            return ValidationResult(
                status=status,
                threat_level=threat_level,
                issues=issues,
                metadata={
                    "file_size": file_size,
                    "file_path": str(file_path),
                    "extension": file_path.suffix,
                },
            )

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return ValidationResult(
                status=ValidationStatus.FAILED,
                threat_level=ThreatLevel.HIGH,
                issues=[f"Validation error: {str(e)}"],
            )

    def _validate_extension(self, file_path: Path) -> bool:
        """Validate file extension."""
        return file_path.suffix.lower() in self.config.allowed_extensions

    def _validate_mime_type(
        self, file_path: Path, content: Optional[bytes]
    ) -> Tuple[List[str], ThreatLevel]:
        """Validate MIME type of file."""
        issues = []
        threat_level = ThreatLevel.NONE

        try:
            # Guess MIME type from filename
            mime_type, _ = mimetypes.guess_type(str(file_path))

            # If we have content, verify with magic bytes
            if content:
                import magic  # type: ignore[import-not-found]

                detected_mime = magic.from_buffer(content[:8192], mime=True)

                # Check for mismatch
                if mime_type and detected_mime and mime_type != detected_mime:
                    issues.append(f"MIME type mismatch: {mime_type} vs {detected_mime}")
                    threat_level = ThreatLevel.HIGH

                mime_type = detected_mime or mime_type

            # Validate against allowed types
            if mime_type and mime_type not in self.config.allowed_mime_types:
                # Check if it's a text file that's mislabeled
                if content:
                    try:
                        content.decode("utf-8")
                        # It's valid UTF-8, might be acceptable
                        threat_level = ThreatLevel.LOW
                    except UnicodeDecodeError:
                        issues.append(f"Disallowed MIME type: {mime_type}")
                        threat_level = ThreatLevel.HIGH

        except Exception as e:
            logger.warning(f"MIME validation error: {e}")
            issues.append("Could not validate MIME type")
            threat_level = ThreatLevel.MEDIUM

        return issues, threat_level

    def _validate_content(self, content: bytes) -> Tuple[List[str], ThreatLevel]:
        """Validate file content for malicious patterns."""
        issues = []
        threat_level = ThreatLevel.NONE

        try:
            # Detect encoding
            detected = chardet.detect(content[:10000])
            encoding = detected.get("encoding") or "utf-8"

            # Try to decode as text
            try:
                text_content = content.decode(encoding, errors="ignore")
            except Exception:
                text_content = content.decode("utf-8", errors="ignore")

            # Check for binary content
            if self.config.block_binary_content:
                if self._contains_binary(content):
                    issues.append("Binary content detected")
                    threat_level = ThreatLevel.HIGH

            # Line length validation
            lines = text_content.split("\n")
            if len(lines) > self.config.max_lines:
                issues.append(f"Too many lines: {len(lines)}")
                threat_level = ThreatLevel.MEDIUM

            for line_num, line in enumerate(lines[:1000], 1):  # Check first 1000 lines
                if len(line) > self.config.max_line_length:
                    issues.append(f"Line {line_num} too long: {len(line)} chars")
                    threat_level = max(
                        threat_level, ThreatLevel.LOW, key=lambda t: t.severity
                    )

            # Injection detection
            if self.config.enable_injection_detection:
                injection_issues, injection_threat = self._detect_injections(
                    text_content
                )
                issues.extend(injection_issues)
                threat_level = max(
                    threat_level, injection_threat, key=lambda t: t.severity
                )

            # Check for suspicious patterns
            suspicious_issues, suspicious_threat = self._detect_suspicious_patterns(
                text_content
            )
            issues.extend(suspicious_issues)
            threat_level = max(
                threat_level, suspicious_threat, key=lambda t: t.severity
            )

        except Exception as e:
            logger.error(f"Content validation error: {e}")
            issues.append(f"Content validation error: {str(e)}")
            threat_level = ThreatLevel.HIGH

        return issues, threat_level

    def _contains_binary(self, content: bytes) -> bool:
        """Check if content contains binary data."""
        # Check for null bytes
        if b"\x00" in content[:1000]:
            return True

        # Check for high ratio of non-printable characters
        sample = content[:1000]
        non_printable = sum(1 for b in sample if b < 32 or b > 126)
        if len(sample) > 0 and non_printable / len(sample) > 0.3:
            return True

        return False

    def _detect_injections(self, text: str) -> Tuple[List[str], ThreatLevel]:
        """Detect various injection attacks."""
        issues = []
        threat_level = ThreatLevel.NONE

        # Sample for performance (check first 100KB)
        sample = text[:100000]

        for pattern_type, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                matches = pattern.findall(sample)
                if matches:
                    # Determine threat level based on pattern type
                    if pattern_type in ["sql", "command", "xxe"]:
                        threat = ThreatLevel.CRITICAL
                    elif pattern_type in ["xss", "ldap"]:
                        threat = ThreatLevel.HIGH
                    else:
                        threat = ThreatLevel.MEDIUM

                    issues.append(
                        f"Potential {pattern_type.upper()} injection detected"
                    )
                    threat_level = max(threat_level, threat, key=lambda t: t.severity)
                    break  # One detection per type is enough

        return issues, threat_level

    def _detect_suspicious_patterns(self, text: str) -> Tuple[List[str], ThreatLevel]:
        """Detect other suspicious patterns."""
        issues = []
        threat_level = ThreatLevel.NONE

        # Check for excessive repetition (potential DoS)
        if self._has_excessive_repetition(text):
            issues.append("Excessive repetition detected")
            threat_level = ThreatLevel.MEDIUM

        # Check for encoded payloads
        if self._has_encoded_payloads(text):
            issues.append("Encoded payloads detected")
            threat_level = ThreatLevel.HIGH

        # Check for suspicious URLs
        if self._has_suspicious_urls(text):
            issues.append("Suspicious URLs detected")
            threat_level = ThreatLevel.MEDIUM

        # Check for potential buffer overflow attempts
        if self._has_buffer_overflow_patterns(text):
            issues.append("Potential buffer overflow pattern")
            threat_level = ThreatLevel.CRITICAL

        return issues, threat_level

    def _has_excessive_repetition(self, text: str) -> bool:
        """Check for excessive character repetition."""
        # Check for long sequences of same character
        import re

        pattern = re.compile(r"(.)\1{100,}")
        return bool(pattern.search(text[:10000]))

    def _has_encoded_payloads(self, text: str) -> bool:
        """Check for base64 or hex encoded payloads."""
        import re

        # Base64 pattern (long sequences)
        base64_pattern = re.compile(r"[A-Za-z0-9+/]{100,}={0,2}")
        # Hex pattern (long sequences)
        hex_pattern = re.compile(r"(?:[0-9a-fA-F]{2}){50,}")

        sample = text[:10000]
        return bool(base64_pattern.search(sample) or hex_pattern.search(sample))

    def _has_suspicious_urls(self, text: str) -> bool:
        """Check for suspicious URLs."""
        import re

        # Look for URLs with suspicious patterns
        suspicious_url_patterns = [
            r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",  # IP addresses
            r"https?://[^/]*\.(tk|ml|ga|cf)",  # Suspicious TLDs
            r"https?://[^/]*[0-9]{5,}",  # URLs with many numbers
            r"file://",  # File URLs
            r"gopher://",  # Gopher protocol
        ]

        sample = text[:10000]
        for pattern in suspicious_url_patterns:
            if re.search(pattern, sample, re.IGNORECASE):
                return True
        return False

    def _has_buffer_overflow_patterns(self, text: str) -> bool:
        """Check for buffer overflow patterns."""
        # Check for NOP sleds
        if "\x90" * 50 in text:
            return True
        # Check for shellcode patterns
        if "\\x" in text and text.count("\\x") > 100:
            return True
        return False

    def validate_request(self, request_data: Dict[str, Any]) -> ValidationResult:
        """
        Validate an API request for security issues.

        Args:
            request_data: Request data to validate

        Returns:
            Validation result
        """
        issues = []
        threat_level = ThreatLevel.NONE

        # Check request size
        request_str = str(request_data)
        if len(request_str) > 1000000:  # 1MB limit for requests
            issues.append("Request too large")
            threat_level = ThreatLevel.HIGH

        # Check for nested structures (potential DoS)
        if self._check_nesting_depth(request_data) > self.config.max_nested_depth:
            issues.append("Excessive nesting depth")
            threat_level = ThreatLevel.HIGH

        # Check all string values for injection
        for key, value in self._flatten_dict(request_data).items():
            if isinstance(value, str):
                inj_issues, inj_threat = self._detect_injections(value)
                if inj_issues:
                    issues.extend([f"{key}: {issue}" for issue in inj_issues])
                    threat_level = max(
                        threat_level, inj_threat, key=lambda t: t.severity
                    )

        status = ValidationStatus.PASSED if not issues else ValidationStatus.FAILED

        return ValidationResult(status=status, threat_level=threat_level, issues=issues)

    def _check_nesting_depth(self, obj: Any, depth: int = 0) -> int:
        """Check maximum nesting depth of object."""
        if depth > self.config.max_nested_depth:
            return depth

        if isinstance(obj, dict):
            return max(
                [self._check_nesting_depth(v, depth + 1) for v in obj.values()]
                + [depth]
            )
        elif isinstance(obj, (list, tuple)):
            return max([self._check_nesting_depth(v, depth + 1) for v in obj] + [depth])
        else:
            return depth

    def _flatten_dict(
        self, d: Dict[str, Any], parent_key: str = "", sep: str = "."
    ) -> Dict[str, Any]:
        """Flatten nested dictionary for validation."""
        items: list[tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)


class RateLimiter:
    """Rate limiter for security validation."""

    def __init__(self, max_requests: int, window_seconds: int):
        """Initialize rate limiter."""
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: defaultdict[str, deque[float]] = defaultdict(deque)
        self.lock = Lock()

    def check_request(self, identifier: str) -> bool:
        """Check if request is within rate limit."""
        with self.lock:
            now = time.time()
            window_start = now - self.window_seconds

            # Remove old requests outside window
            while (
                self.requests[identifier]
                and self.requests[identifier][0] < window_start
            ):
                self.requests[identifier].popleft()

            # Check rate limit
            if len(self.requests[identifier]) >= self.max_requests:
                return False

            # Add current request
            self.requests[identifier].append(now)
            return True


class SecurityAuditLog:
    """Security audit logger for compliance."""

    def __init__(self, max_entries: int = 10000):
        """Initialize audit log."""
        self.entries: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self.lock = Lock()

    def log_validation(
        self,
        file_path: Path,
        status: ValidationStatus,
        threat_level: ThreatLevel,
        issues: List[str],
    ):
        """Log validation event."""
        with self.lock:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "file_path": str(file_path),
                "status": status.value,
                "threat_level": threat_level.value,
                "issues": issues,
                "hash": hashlib.sha256(str(file_path).encode()).hexdigest()[:16],
            }
            self.entries.append(entry)

            # Log critical threats immediately
            if threat_level == ThreatLevel.CRITICAL:
                logger.critical(f"SECURITY ALERT: {file_path} - {issues}")

    def get_recent_entries(self, count: int = 100) -> List[Dict]:
        """Get recent audit entries."""
        with self.lock:
            return list(self.entries)[-count:]
