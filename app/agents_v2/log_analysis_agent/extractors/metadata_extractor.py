"""
Metadata Extractor for Log Analysis

This module extracts structured metadata from Mailbird log files,
identifying version information, system details, and operational metrics.
"""

import re
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from ..schemas.log_schemas import LogMetadata, LogEntry, Severity

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """
    Extracts and aggregates metadata from log entries.

    This class implements efficient pattern matching to identify
    and extract key metadata from Mailbird logs including version info,
    system configuration, and performance metrics.
    """

    # Version patterns
    VERSION_PATTERNS = [
        r"Mailbird[\/\s]+(?:v|version)?[\s]*([\d.]+(?:\.\d+)?)",
        r"Version:\s*([\d.]+)",
        r"Build:\s*([\d.]+)",
        r"Application Version:\s*([\d.]+)",
    ]

    # OS patterns
    OS_PATTERNS = [
        r"Windows\s+([\d.]+)",
        r"macOS\s+([\d.]+)",
        r"Mac OS X\s+([\d.]+)",
        r"Operating System:\s*([^,\n]+)",
        r"OS:\s*([^,\n]+)",
    ]

    # Memory patterns
    MEMORY_PATTERNS = [
        r"Memory Usage:\s*([\d.]+)\s*MB",
        r"RAM:\s*([\d.]+)\s*MB",
        r"Memory:\s*([\d.]+)MB",
        r"Working Set:\s*([\d.]+)",
    ]

    # Database patterns
    DATABASE_PATTERNS = [
        r"Database Size:\s*([\d.]+)\s*MB",
        r"DB Size:\s*([\d.]+)",
        r"mailbird\.db.*size:\s*([\d.]+)",
        r"Storage Used:\s*([\d.]+)\s*MB",
    ]

    # Account patterns
    ACCOUNT_PATTERNS = [
        r"Account\[(\d+)\]:\s*([^@]+@[^@\s]+)",
        r"Email Account:\s*([^@]+@[^@\s]+)",
        r"Provider:\s*(Gmail|Outlook|Yahoo|IMAP|Exchange)",
        r"Account Type:\s*(\w+)",
    ]

    # Network patterns
    NETWORK_PATTERNS = [
        r"Network Status:\s*(\w+)",
        r"Proxy:\s*(Enabled|Disabled|True|False)",
        r"Connection:\s*(Online|Offline|Connected|Disconnected)",
    ]

    def __init__(self):
        """Initialize the metadata extractor."""
        self._compiled_patterns = self._compile_patterns()
        self.reset()

    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Pre-compile regex patterns for efficiency."""
        return {
            "version": [re.compile(p, re.IGNORECASE) for p in self.VERSION_PATTERNS],
            "os": [re.compile(p, re.IGNORECASE) for p in self.OS_PATTERNS],
            "memory": [re.compile(p, re.IGNORECASE) for p in self.MEMORY_PATTERNS],
            "database": [re.compile(p, re.IGNORECASE) for p in self.DATABASE_PATTERNS],
            "account": [re.compile(p, re.IGNORECASE) for p in self.ACCOUNT_PATTERNS],
            "network": [re.compile(p, re.IGNORECASE) for p in self.NETWORK_PATTERNS],
        }

    def reset(self):
        """Reset internal state for new analysis."""
        self._metadata = LogMetadata(mailbird_version="Unknown")
        self._memory_samples: List[float] = []
        self._cpu_samples: List[float] = []
        self._accounts: Dict[str, str] = {}
        self._first_timestamp: Optional[datetime] = None
        self._last_timestamp: Optional[datetime] = None

    def extract_from_entries(self, entries: List[LogEntry]) -> LogMetadata:
        """
        Extract metadata from a list of log entries.

        Args:
            entries: List of parsed log entries

        Returns:
            Aggregated metadata from all entries
        """
        self.reset()

        if not entries:
            return self._metadata

        # Process timestamps
        self._process_timestamps(entries)

        # Count entries by severity
        self._count_severities(entries)

        # Extract metadata from each entry
        for entry in entries:
            self._extract_from_entry(entry)

        # Finalize aggregated values
        self._finalize_metadata()

        return self._metadata

    def extract_from_text(self, log_text: str) -> LogMetadata:
        """
        Extract metadata directly from raw log text.

        Args:
            log_text: Raw log file content

        Returns:
            Extracted metadata
        """
        self.reset()

        # Extract version information
        self._extract_version(log_text)

        # Extract OS information
        self._extract_os(log_text)

        # Extract memory statistics
        self._extract_memory_stats(log_text)

        # Extract database information
        self._extract_database_info(log_text)

        # Extract account information
        self._extract_accounts(log_text)

        # Extract network state
        self._extract_network_state(log_text)

        # Finalize aggregated values
        self._finalize_metadata()

        return self._metadata

    def _extract_from_entry(self, entry: LogEntry):
        """Extract metadata from a single log entry."""
        text = entry.raw_text if entry.raw_text else entry.message

        # Version extraction
        if not self._metadata.mailbird_version or self._metadata.mailbird_version == "Unknown":
            self._extract_version(text)

        # Memory samples
        self._extract_memory_sample(text)

        # Account detection
        self._extract_account_from_text(text)

    def _extract_version(self, text: str):
        """Extract version information from text."""
        for pattern in self._compiled_patterns["version"]:
            match = pattern.search(text)
            if match:
                version = match.group(1)
                if self._is_valid_version(version):
                    self._metadata.mailbird_version = version
                    logger.debug(f"Extracted version: {version}")
                    break

        # Extract build number separately
        build_match = re.search(r"Build[:\s#]*([\d.]+)", text, re.IGNORECASE)
        if build_match:
            self._metadata.build_number = build_match.group(1)

    def _extract_os(self, text: str):
        """Extract operating system information."""
        for pattern in self._compiled_patterns["os"]:
            match = pattern.search(text)
            if match:
                os_info = match.group(0)
                self._metadata.os_version = self._clean_os_string(os_info)

                # Detect architecture
                if "64-bit" in text or "x64" in text:
                    self._metadata.os_architecture = "x64"
                elif "32-bit" in text or "x86" in text:
                    self._metadata.os_architecture = "x86"
                elif "ARM" in text:
                    self._metadata.os_architecture = "ARM"
                break

    def _extract_memory_stats(self, text: str):
        """Extract memory usage statistics."""
        for pattern in self._compiled_patterns["memory"]:
            matches = pattern.findall(text)
            for match in matches:
                try:
                    memory_mb = float(match)
                    if 0 < memory_mb < 100000:  # Sanity check
                        self._memory_samples.append(memory_mb)
                except (ValueError, TypeError):
                    continue

    def _extract_memory_sample(self, text: str):
        """Extract a single memory sample from text."""
        for pattern in self._compiled_patterns["memory"]:
            match = pattern.search(text)
            if match:
                try:
                    memory_mb = float(match.group(1))
                    if 0 < memory_mb < 100000:  # Sanity check
                        self._memory_samples.append(memory_mb)
                        return
                except (ValueError, TypeError):
                    continue

    def _extract_database_info(self, text: str):
        """Extract database size information."""
        for pattern in self._compiled_patterns["database"]:
            match = pattern.search(text)
            if match:
                try:
                    size_mb = float(match.group(1))
                    if 0 < size_mb < 100000:  # Sanity check
                        self._metadata.database_size_mb = size_mb
                        logger.debug(f"Extracted database size: {size_mb} MB")
                        break
                except (ValueError, TypeError):
                    continue

    def _extract_accounts(self, text: str):
        """Extract email account information."""
        # Look for email addresses
        email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
        emails = email_pattern.findall(text)

        for email in emails:
            if not self._is_system_email(email):
                provider = self._identify_provider(email)
                self._accounts[email] = provider

        # Look for explicit provider mentions
        provider_pattern = re.compile(
            r"(Gmail|Outlook|Yahoo|Exchange|IMAP|Hotmail|Office\s*365)",
            re.IGNORECASE
        )
        providers = provider_pattern.findall(text)
        for provider in providers:
            normalized = self._normalize_provider(provider)
            if normalized not in self._metadata.account_providers:
                self._metadata.account_providers.append(normalized)

    def _extract_account_from_text(self, text: str):
        """Extract account information from a single text snippet."""
        email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
        match = email_pattern.search(text)
        if match:
            email = match.group(0)
            if not self._is_system_email(email):
                provider = self._identify_provider(email)
                self._accounts[email] = provider

    def _extract_network_state(self, text: str):
        """Extract network state information."""
        for pattern in self._compiled_patterns["network"]:
            match = pattern.search(text)
            if match:
                state = match.group(1) if match.lastindex else match.group(0)
                self._metadata.network_state = state

                # Check for proxy
                if "proxy" in text.lower():
                    if any(word in text.lower() for word in ["enabled", "true", "configured"]):
                        self._metadata.proxy_configured = True
                break

    def _process_timestamps(self, entries: List[LogEntry]):
        """Process entry timestamps to determine session bounds."""
        if not entries:
            return

        timestamps = [e.timestamp for e in entries if e.timestamp]
        if timestamps:
            self._first_timestamp = min(timestamps)
            self._last_timestamp = max(timestamps)
            self._metadata.session_start = self._first_timestamp
            self._metadata.session_end = self._last_timestamp

    def _count_severities(self, entries: List[LogEntry]):
        """Count entries by severity level."""
        self._metadata.total_entries = len(entries)
        self._metadata.error_count = sum(
            1 for e in entries
            if e.severity.numeric_value >= Severity.ERROR.numeric_value
        )
        self._metadata.warning_count = sum(
            1 for e in entries
            if e.severity == Severity.WARNING
        )

    def _finalize_metadata(self):
        """Finalize aggregated metadata values."""
        # Calculate average memory usage
        if self._memory_samples:
            self._metadata.memory_usage_mb = sum(self._memory_samples) / len(
                self._memory_samples
            )

        # Set account information
        self._metadata.account_count = len(self._accounts)
        if not self._metadata.account_providers and self._accounts:
            providers = list(set(self._accounts.values()))
            self._metadata.account_providers = [p for p in providers if p != "Other"]

    def _is_valid_version(self, version: str) -> bool:
        """Check if a version string is valid."""
        # Basic validation for version format
        parts = version.split(".")
        if not parts:
            return False

        try:
            # At least the first part should be a number
            int(parts[0])
            return True
        except ValueError:
            return False

    def _clean_os_string(self, os_string: str) -> str:
        """Clean and normalize OS string."""
        # Remove extra whitespace and standardize format
        cleaned = " ".join(os_string.split())
        # Capitalize properly
        if "windows" in cleaned.lower():
            cleaned = cleaned.replace("windows", "Windows")
        elif "macos" in cleaned.lower() or "mac os" in cleaned.lower():
            cleaned = cleaned.replace("macos", "macOS").replace("Mac OS", "macOS")
        return cleaned

    def _is_system_email(self, email: str) -> bool:
        """Check if an email is a system/example email."""
        system_domains = [
            "example.com",
            "test.com",
            "localhost",
            "mailbird.com",
            "noreply",
        ]
        return any(domain in email.lower() for domain in system_domains)

    def _identify_provider(self, email: str) -> str:
        """Identify email provider from email address."""
        email_lower = email.lower()
        providers = {
            "gmail.com": "Gmail",
            "googlemail.com": "Gmail",
            "outlook.com": "Outlook",
            "hotmail.com": "Outlook",
            "live.com": "Outlook",
            "yahoo.com": "Yahoo",
            "yahoo.co": "Yahoo",
            "icloud.com": "iCloud",
            "me.com": "iCloud",
            "mac.com": "iCloud",
        }

        for domain, provider in providers.items():
            if domain in email_lower:
                return provider

        # Check for corporate/exchange
        if "@" in email and not any(d in email_lower for d in providers.keys()):
            # Likely corporate email
            return "Exchange/IMAP"

        return "Other"

    def _normalize_provider(self, provider: str) -> str:
        """Normalize provider name to standard format."""
        normalized = {
            "office365": "Office 365",
            "office 365": "Office 365",
            "exchange": "Exchange",
            "gmail": "Gmail",
            "outlook": "Outlook",
            "yahoo": "Yahoo",
            "imap": "IMAP",
            "hotmail": "Outlook",
        }

        provider_lower = provider.lower().strip()
        return normalized.get(provider_lower, provider.title())