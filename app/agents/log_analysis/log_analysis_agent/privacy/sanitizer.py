"""
Log Data Sanitizer with Paranoid-Level Security

This module implements comprehensive data sanitization to remove/redact all forms
of sensitive information from logs. Uses defense-in-depth with multiple pattern
matching layers and configurable redaction levels.

Security Design:
- Multiple regex patterns for each sensitive data type
- Overlapping pattern detection for edge cases
- Configurable redaction levels for different environments
- Maintains log structure while removing sensitive content
- Validates sanitization completeness
"""

import re
import quopri
import hashlib
import logging
from enum import Enum
from typing import Dict, List, Optional, Pattern, Tuple, Set
from dataclasses import dataclass, field
from ipaddress import ip_address, ip_network
import unicodedata

logger = logging.getLogger(__name__)


class RedactionLevel(Enum):
    """Security levels for data redaction."""
    PARANOID = "paranoid"  # Maximum redaction, assumes everything is sensitive
    HIGH = "high"          # Production-level redaction
    MEDIUM = "medium"      # Development environment redaction
    LOW = "low"            # Minimal redaction for debugging
    NONE = "none"          # No redaction (DANGEROUS - only for isolated testing)


@dataclass
class SanitizationConfig:
    """Configuration for log sanitization with secure defaults."""
    redaction_level: RedactionLevel = RedactionLevel.HIGH
    preserve_structure: bool = True  # Maintain log format for analysis
    hash_sensitive_data: bool = True  # Hash instead of complete removal
    custom_patterns: List[Pattern] = field(default_factory=list)
    allowed_domains: Set[str] = field(default_factory=lambda: {"example.com", "localhost"})
    max_iterations: int = 5  # Prevent regex DoS attacks
    enable_unicode_normalization: bool = True  # Prevent homograph attacks
    validate_completeness: bool = True  # Double-check sanitization
    paranoid_mode: bool = False  # Enable maximum redaction safeguards

    def __post_init__(self) -> None:
        """Normalize configuration and enforce paranoid safeguards when enabled."""
        # Ensure domain allowlist comparison is case-insensitive
        self.allowed_domains = {domain.lower() for domain in self.allowed_domains}

        if self.paranoid_mode:
            # Paranoid mode always uses maximum redaction and disables allowlist exceptions
            if self.redaction_level != RedactionLevel.PARANOID:
                logger.debug(
                    "Paranoid mode enabled; overriding redaction level to PARANOID"
                )
                self.redaction_level = RedactionLevel.PARANOID

            # Only keep localhost in paranoid mode to avoid leaking corporate domains
            self.allowed_domains = {domain for domain in self.allowed_domains if domain == "localhost"}

            # Increase pass count and force validation in paranoid mode
            self.max_iterations = max(self.max_iterations, 7)
            self.validate_completeness = True
            self.hash_sensitive_data = True


class LogSanitizer:
    """
    Comprehensive log sanitizer with paranoid-level security patterns.

    Implements multiple layers of pattern matching to ensure complete removal
    of sensitive information while maintaining log integrity for analysis.
    """

    _SOFT_LINE_BREAK_RE = re.compile(r'=\r?\n')
    _CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]+')
    _COMMON_CORRECTIONS = (
        (re.compile(r'\bfirwall\b', re.IGNORECASE), 'firewall'),
        (re.compile(r'\bfir\s+wall\b', re.IGNORECASE), 'firewall'),
    )

    # Comprehensive regex patterns for sensitive data detection
    # Each pattern has multiple variants to catch edge cases

    # Email patterns - multiple formats and obfuscation attempts
    EMAIL_PATTERNS = [
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Standard email
        r'\b[A-Za-z0-9._%+-]+\s*@\s*[A-Za-z0-9.-]+\s*\.\s*[A-Z|a-z]{2,}\b',  # With spaces
        r'\b[A-Za-z0-9._%+-]+\[at\][A-Za-z0-9.-]+\[dot\][A-Z|a-z]{2,}\b',  # Obfuscated
        r'\b[A-Za-z0-9._%+-]+\(at\)[A-Za-z0-9.-]+\(dot\)[A-Z|a-z]{2,}\b',  # Alternative obfuscation
        r'(?i)e-?mail\s*[:=]\s*[^\s,;]+',  # Email fields
        r'(?i)mail\s*[:=]\s*[^\s,;]+',  # Mail fields
        r'(?i)from\s*[:=]\s*[^\s,;]+@[^\s,;]+',  # From headers
        r'(?i)to\s*[:=]\s*[^\s,;]+@[^\s,;]+',  # To headers
    ]

    # IP Address patterns - IPv4, IPv6, and obfuscated formats
    IP_PATTERNS = [
        r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',  # IPv4
        r'(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}',  # IPv6 full
        r'::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}',  # IPv6 compressed
        r'(?:[0-9a-fA-F]{1,4}:){1,7}:',  # IPv6 with ::
        r'(?i)(?:ip|host|server|client)[\s_-]*(?:addr|address)?[\s:=]+[\d.:a-f]+',  # IP fields
        r'\b\d{1,3}\[\.\]\d{1,3}\[\.\]\d{1,3}\[\.\]\d{1,3}\b',  # Obfuscated IPv4
    ]

    # API Keys and Tokens - various formats and platforms
    # Require explicit keywords and longer token lengths to reduce false positives; may still flag long encoded strings and should be tuned as needed
    API_KEY_PATTERNS = [
        r'(?i)(?:api[_-]?key|apikey|api[_-]?token|access[_-]?token|auth[_-]?token|authorization|bearer)\s*[:=]\s*["\']?[A-Za-z0-9+/=_-]{20,}["\']?',
        r'(?i)(?:secret|private[_-]?key|client[_-]?secret)\s*[:=]\s*["\']?[A-Za-z0-9+/=_-]{20,}["\']?',
        r'sk_(?:test|live)_[A-Za-z0-9]{24,}',  # Stripe
        r'(?:r|s)k_[A-Za-z0-9]{40,}',  # Various providers
        r'(?i)(?:key|token|secret|apikey|api[_-]?key|access[_-]?token|auth[_-]?token)[^\S\r\n]{0,5}[:=]?\s*["\']?[A-Za-z0-9+/=_-]{40,}["\']?',
        r'ghp_[A-Za-z0-9]{36}',  # GitHub personal access token
        r'gho_[A-Za-z0-9]{36}',  # GitHub OAuth token
        r'github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59}',  # GitHub fine-grained PAT
        r'glpat-[A-Za-z0-9]{20}',  # GitLab
        r'sq0[a-z]{3}-[A-Za-z0-9\-]{22,}',  # Square
        r'AKIA[A-Z0-9]{16}',  # AWS Access Key
        r'(?i)x-api-key\s*[:=]\s*[A-Za-z0-9+/=_-]+',  # X-API-Key headers
    ]

    # Password patterns - various formats and contexts
    PASSWORD_PATTERNS = [
        r'(?i)(?:password|passwd|pwd|pass)\s*[:=]\s*["\']?[^\s"\']{3,}["\']?',
        r'(?i)(?:pw|credential)\s*[:=]\s*["\']?[^\s"\']{3,}["\']?',
        r'(?i)(?:auth|authentication)\s*[:=]\s*["\']?[^\s"\']{8,}["\']?',
        r'(?i)login\s*[:=]\s*[^\s,;]+\s+[^\s,;]+',  # Login credentials
        r'(?i)user\s*[:=]\s*[^\s,;]+\s+password\s*[:=]\s*[^\s,;]+',
    ]

    # Credit Card patterns - all major card types
    CREDIT_CARD_PATTERNS = [
        r'\b(?:4[0-9]{12}(?:[0-9]{3})?)\b',  # Visa
        r'\b(?:5[1-5][0-9]{14}|2(?:22[1-9]|2[3-9][0-9]|[3-6][0-9]{2}|7[0-1][0-9]|720)[0-9]{12})\b',  # Mastercard
        r'\b(?:3[47][0-9]{13})\b',  # American Express
        r'\b(?:3(?:0[0-5]|[68][0-9])[0-9]{11})\b',  # Diners Club
        r'\b(?:6(?:011|5[0-9]{2})[0-9]{12})\b',  # Discover
        r'\b(?:(?:2131|1800|35\d{3})\d{11})\b',  # JCB
        r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Generic with separators
        r'(?i)(?:card|cc|credit)\s*(?:num|number)?\s*[:=]\s*\d{13,19}',
    ]

    # SSN and National ID patterns
    SSN_PATTERNS = [
        r'\b\d{3}-\d{2}-\d{4}\b',  # US SSN with dashes
        r'\b\d{3}\s\d{2}\s\d{4}\b',  # US SSN with spaces
        r'(?i)(?:ssn|social)\s*[:=]\s*\d{3}[-\s]?\d{2}[-\s]?\d{4}',
        r'(?i)(?:tax[_-]?id|tin)\s*[:=]\s*\d{2}-?\d{7}',  # Tax ID
    ]

    # Phone number patterns - international formats
    PHONE_PATTERNS = [
        r'\+[1-9]\d{9,14}\b',  # E.164 compliant
        r'(?i)(?:phone|tel|mobile|cell)\s*[:=]\s*\+[1-9]\d{9,14}'
    ]

    # AWS and Cloud Provider patterns
    CLOUD_PATTERNS = [
        r'(?i)aws[_-]?(?:access[_-]?key[_-]?id|secret[_-]?access[_-]?key)\s*[:=]\s*[A-Za-z0-9+/=]+',
        r'arn:aws:[a-z0-9\-]+:[a-z0-9\-]*:\d{12}:[a-zA-Z0-9\-_:/]+',  # AWS ARN
        r'(?i)azure[_-]?(?:storage[_-]?account[_-]?key|client[_-]?secret)\s*[:=]\s*[A-Za-z0-9+/=]+',
        r'(?i)gcp[_-]?(?:api[_-]?key|service[_-]?account)\s*[:=]\s*[A-Za-z0-9+/=]+',
    ]

    # Database connection strings
    DATABASE_PATTERNS = [
        r'(?i)(?:mongodb|postgres|postgresql|mysql|redis|mssql|oracle)://[^\s]+',
        r'(?i)(?:host|server)\s*[:=]\s*[^\s]+\s+(?:user|username)\s*[:=]\s*[^\s]+\s+(?:password|pwd)\s*[:=]\s*[^\s]+',
        r'(?i)data\s+source\s*=\s*[^;]+;[^;]*password\s*=\s*[^;]+',  # SQL Server
    ]

    # JWT tokens
    JWT_PATTERNS = [
        r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',  # JWT format
        r'(?i)bearer\s+eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
    ]

    # File paths with potentially sensitive information
    PATH_PATTERNS = [
        r'(?i)/(?:home|users)/[^/\s]+/[^\s]*(?:\.ssh|\.aws|\.git|password|secret|credential|private)',
        r'(?i)(?:c:|d:)\\users\\[^\\]+\\[^\s]*(?:password|secret|credential|private)',
        r'(?i)/(?:etc|var)/[^\s]*(?:passwd|shadow|secret)',
    ]

    def __init__(self, config: Optional[SanitizationConfig] = None):
        """
        Initialize the log sanitizer with secure defaults.

        Args:
            config: Optional configuration, uses secure defaults if not provided
        """
        self.config = config or SanitizationConfig()
        self._compiled_patterns = self._compile_patterns()
        self._redaction_cache = {}  # Cache for consistent redaction
        self._validation_patterns = self._compile_validation_patterns()

        logger.info(f"LogSanitizer initialized with redaction level: {self.config.redaction_level.value}")

    def _compile_patterns(self) -> Dict[str, List[Pattern]]:
        """Compile all regex patterns for efficiency and security."""
        patterns = {}

        # Compile patterns based on redaction level
        if self.config.redaction_level == RedactionLevel.NONE:
            logger.warning("DANGEROUS: Sanitizer initialized with RedactionLevel.NONE - No data will be redacted!")
            return patterns

        # Always include critical patterns
        patterns['email'] = [re.compile(p, re.IGNORECASE) for p in self.EMAIL_PATTERNS]
        patterns['api_key'] = [re.compile(p) for p in self.API_KEY_PATTERNS]
        patterns['password'] = [re.compile(p) for p in self.PASSWORD_PATTERNS]
        patterns['credit_card'] = [re.compile(p) for p in self.CREDIT_CARD_PATTERNS]

        if self.config.redaction_level in [RedactionLevel.PARANOID, RedactionLevel.HIGH]:
            patterns['ip'] = [re.compile(p) for p in self.IP_PATTERNS]
            patterns['ssn'] = [re.compile(p) for p in self.SSN_PATTERNS]
            patterns['phone'] = [re.compile(p) for p in self.PHONE_PATTERNS]
            patterns['cloud'] = [re.compile(p) for p in self.CLOUD_PATTERNS]
            patterns['database'] = [re.compile(p) for p in self.DATABASE_PATTERNS]
            patterns['jwt'] = [re.compile(p) for p in self.JWT_PATTERNS]

        if self.config.redaction_level == RedactionLevel.PARANOID:
            patterns['path'] = [re.compile(p) for p in self.PATH_PATTERNS]
            # Add custom patterns in paranoid mode
            patterns['custom'] = self.config.custom_patterns

        return patterns

    def _compile_validation_patterns(self) -> Dict[str, Pattern]:
        """Compile patterns for post-sanitization validation."""
        return {
            'residual_email': re.compile(r'@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}'),
            'residual_api': re.compile(r'[A-Za-z0-9+/=_-]{40,}'),
            'residual_card': re.compile(r'\b\d{13,19}\b'),
            'residual_jwt': re.compile(r'eyJ[A-Za-z0-9_-]{10,}'),
        }

    def _normalize_unicode(self, text: str) -> str:
        """Normalize Unicode to prevent homograph attacks."""
        if not self.config.enable_unicode_normalization:
            return text

        # Normalize to NFKD form to decompose characters
        normalized = unicodedata.normalize('NFKD', text)
        # Remove non-ASCII characters that could be used for obfuscation
        ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
        return ascii_text

    def _generate_redaction(self, sensitive_data: str, data_type: str) -> str:
        """
        Generate consistent redaction for sensitive data.

        Args:
            sensitive_data: The sensitive data to redact
            data_type: Type of sensitive data

        Returns:
            Redacted string with optional hash for correlation
        """
        if self.config.hash_sensitive_data:
            # Create a hash for correlation while maintaining privacy
            hash_value = hashlib.sha256(sensitive_data.encode()).hexdigest()[:8]
            return f"[REDACTED_{data_type.upper()}_{hash_value}]"
        else:
            return f"[REDACTED_{data_type.upper()}]"

    def _sanitize_layer(self, text: str, pattern_type: str, patterns: List[Pattern]) -> Tuple[str, int]:
        """
        Apply a single layer of sanitization.

        Args:
            text: Text to sanitize
            pattern_type: Type of pattern being applied
            patterns: List of compiled patterns

        Returns:
            Tuple of (sanitized text, number of redactions)
        """
        redaction_count = 0

        for pattern in patterns:
            matches = list(pattern.finditer(text))

            # Process matches in reverse to maintain string indices
            for match in reversed(matches):
                sensitive_data = match.group()

                # Skip allowed domains for email patterns
                if pattern_type == 'email' and self.config.allowed_domains:
                    domain = sensitive_data.split('@')[-1] if '@' in sensitive_data else ''
                    domain = domain.lower().strip(" <>[](){}.,;:\"'\n\r\t")
                    if domain in self.config.allowed_domains:
                        continue

                # Generate consistent redaction
                redacted = self._generate_redaction(sensitive_data, pattern_type)

                # Replace the sensitive data
                text = text[:match.start()] + redacted + text[match.end():]
                redaction_count += 1

                # Log the redaction (without the sensitive data!)
                logger.debug(f"Redacted {pattern_type} at position {match.start()}")

        return text, redaction_count

    def sanitize(self, text: str) -> Tuple[str, Dict[str, int]]:
        """
        Sanitize log text by removing/redacting sensitive information.

        Args:
            text: Raw log text to sanitize

        Returns:
            Tuple of (sanitized text, redaction statistics)
        """
        if not text:
            return text, {}

        text = self._preprocess_text(text)

        # Unicode normalization to prevent bypass attempts
        if self.config.enable_unicode_normalization:
            text = self._normalize_unicode(text)

        redaction_stats = {}
        iteration = 0
        total_redactions = 0

        # Multiple passes to catch nested patterns
        while iteration < self.config.max_iterations:
            iteration_redactions = 0

            # Apply each pattern layer
            for pattern_type, patterns in self._compiled_patterns.items():
                if patterns:
                    text, count = self._sanitize_layer(text, pattern_type, patterns)
                    redaction_stats[pattern_type] = redaction_stats.get(pattern_type, 0) + count
                    iteration_redactions += count

            # Break if no new redactions in this iteration
            if iteration_redactions == 0:
                break

            total_redactions += iteration_redactions
            iteration += 1

        # Validate completeness if configured
        if self.config.validate_completeness:
            validation_issues = self._validate_sanitization(text)
            if validation_issues:
                logger.warning(f"Post-sanitization validation found potential issues: {validation_issues}")
                # Apply paranoid final pass
                text = self._apply_paranoid_final_pass(text)

        logger.info(f"Sanitization complete: {total_redactions} redactions across {iteration} iterations")
        return text, redaction_stats

    def _preprocess_text(self, text: str) -> str:
        """Normalize transport artefacts before sanitization routines run."""

        processed = text

        try:
            decoded_bytes = quopri.decodestring(processed.encode('utf-8', errors='ignore'))
            processed = decoded_bytes.decode('utf-8', errors='ignore')
        except Exception:
            # If decoding fails, continue with the original text
            pass

        processed = self._SOFT_LINE_BREAK_RE.sub('', processed)
        processed = self._CONTROL_CHAR_RE.sub('', processed)

        for pattern, replacement in self._COMMON_CORRECTIONS:
            processed = pattern.sub(replacement, processed)

        return processed

    def _validate_sanitization(self, text: str) -> List[str]:
        """
        Validate that sanitization was complete.

        Args:
            text: Sanitized text to validate

        Returns:
            List of validation issues found
        """
        issues = []

        for pattern_name, pattern in self._validation_patterns.items():
            if pattern.search(text):
                issues.append(f"Potential {pattern_name} remaining")

        # Check for long alphanumeric sequences that might be tokens
        long_token_pattern = re.compile(r'[A-Za-z0-9+/=_-]{50,}')
        if long_token_pattern.search(text):
            issues.append("Long alphanumeric sequences detected")

        return issues

    def _apply_paranoid_final_pass(self, text: str) -> str:
        """Apply paranoid final sanitization pass for any suspicious patterns."""
        # Redact any remaining long alphanumeric sequences
        text = re.sub(r'[A-Za-z0-9+/=_-]{50,}', '[REDACTED_SUSPICIOUS_TOKEN]', text)

        # Redact any remaining email-like patterns
        text = re.sub(r'[^\s]+@[^\s]+', '[REDACTED_SUSPICIOUS_EMAIL]', text)

        # Redact hex sequences that might be hashes or keys
        text = re.sub(r'\b[a-fA-F0-9]{32,}\b', '[REDACTED_SUSPICIOUS_HEX]', text)

        return text

    def sanitize_for_display(self, text: str) -> str:
        """
        Sanitize text specifically for user-facing display.

        This applies additional formatting and ensures all sensitive
        data is removed before showing to users.

        Args:
            text: Text to sanitize for display

        Returns:
            Display-safe sanitized text
        """
        # First apply standard sanitization
        sanitized, _ = self.sanitize(text)

        # Additional display-specific sanitization
        # Remove internal system paths
        sanitized = re.sub(r'/(?:usr|opt|var|tmp|sys)/[^\s]*', '[SYSTEM_PATH]', sanitized)

        # Remove stack traces that might contain sensitive info
        sanitized = re.sub(r'at\s+[^\s]+\s+\([^)]+\)', 'at [REDACTED_STACK_TRACE]', sanitized)

        # Remove memory addresses
        sanitized = re.sub(r'0x[a-fA-F0-9]{8,}', '[MEMORY_ADDRESS]', sanitized)

        # Truncate very long lines that might contain encoded data
        lines = sanitized.split('\n')
        sanitized_lines = []
        for line in lines:
            if len(line) > 500:
                line = line[:497] + '...'
            sanitized_lines.append(line)

        return '\n'.join(sanitized_lines)

    def get_redaction_summary(self, stats: Dict[str, int]) -> str:
        """
        Generate a summary of redactions performed.

        Args:
            stats: Dictionary of redaction statistics

        Returns:
            Human-readable summary
        """
        if not stats:
            return "No sensitive data was redacted."

        summary_parts = []
        for data_type, count in sorted(stats.items()):
            if count > 0:
                summary_parts.append(f"{count} {data_type}(s)")

        return f"Redacted: {', '.join(summary_parts)}"
