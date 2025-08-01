"""
Safety Redactor for reasoning UI content.

Ensures no sensitive information, system prompts, or internal details
leak through the reasoning UI shown to users.
"""

import re
import copy
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RedactionLevel(Enum):
    """Redaction strictness levels."""
    MINIMAL = "minimal"      # Basic PII and keys
    STANDARD = "standard"    # Standard security redaction
    STRICT = "strict"        # Maximum redaction for production


@dataclass
class RedactionPattern:
    """Pattern for redacting sensitive content."""
    name: str
    pattern: str
    replacement: str
    flags: int = 0


class SafetyRedactor:
    """
    Redacts sensitive information from reasoning UI content.
    
    Features:
    - API key and token redaction
    - File path sanitization
    - System prompt marker removal
    - PII detection and redaction
    - Content length limiting
    - Whitespace normalization
    """
    
    # Common redaction patterns
    REDACTION_PATTERNS = [
        # API Keys and Tokens
        RedactionPattern(
            name="api_key",
            pattern=r'\b(sk-|api_key=|key=|token=|bearer\s+)[A-Za-z0-9_\-]{20,}',
            replacement="[REDACTED_KEY]",
            flags=re.IGNORECASE
        ),
        RedactionPattern(
            name="google_api_key",
            pattern=r'AIza[0-9A-Za-z\-_]{35}',
            replacement="[REDACTED_GOOGLE_KEY]"
        ),
        RedactionPattern(
            name="email_password",
            pattern=r'(password|pwd|pass)\s*[:=]\s*[^\s]+',
            replacement="[REDACTED_PASSWORD]",
            flags=re.IGNORECASE
        ),
        
        # File Paths
        RedactionPattern(
            name="windows_path",
            pattern=r'[A-Z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*',
            replacement="[LOCAL_PATH]",
            flags=re.IGNORECASE
        ),
        RedactionPattern(
            name="unix_path",
            pattern=r'\/(?:home|usr|var|etc|opt)\/[^\s]*',
            replacement="[LOCAL_PATH]"
        ),
        
        # System Prompt Markers
        RedactionPattern(
            name="chain_of_thought",
            pattern=r'(chain[- ]of[- ]thought|thinking\s+process|internal\s+reasoning)',
            replacement="analysis",
            flags=re.IGNORECASE
        ),
        RedactionPattern(
            name="system_prompt",
            pattern=r'(system\s+prompt|hidden\s+prompt|secret\s+instructions)',
            replacement="instructions",
            flags=re.IGNORECASE
        ),
        RedactionPattern(
            name="tool_details",
            pattern=r'(tool\s+call:|function\s+name:|api\s+endpoint:)[^\n]+',
            replacement="[TOOL_USAGE]",
            flags=re.IGNORECASE
        ),
        
        # PII Patterns
        RedactionPattern(
            name="email",
            pattern=r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            replacement="[EMAIL]"
        ),
        RedactionPattern(
            name="ip_address",
            pattern=r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
            replacement="[IP_ADDRESS]"
        ),
        RedactionPattern(
            name="credit_card",
            pattern=r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3[0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b',
            replacement="[CREDIT_CARD]"
        ),
        
        # Internal References
        RedactionPattern(
            name="memory_ref",
            pattern=r'MEMORY\[[a-f0-9\-]+\]',
            replacement="[REFERENCE]"
        ),
        RedactionPattern(
            name="trace_id",
            pattern=r'(trace_id|request_id|session_id)\s*[:=]\s*[a-f0-9\-]+',
            replacement="[ID]",
            flags=re.IGNORECASE
        )
    ]
    
    def __init__(self, level: RedactionLevel = RedactionLevel.STANDARD):
        """Initialize redactor with specified level."""
        self.level = level
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for efficiency."""
        self.compiled_patterns = []
        
        # Select patterns based on level
        if self.level == RedactionLevel.MINIMAL:
            pattern_names = ["api_key", "google_api_key", "email_password", "credit_card"]
        elif self.level == RedactionLevel.STANDARD:
            pattern_names = [
                "api_key", "google_api_key", "email_password",
                "windows_path", "unix_path",
                "chain_of_thought", "system_prompt", "tool_details",
                "email", "credit_card"
            ]
        else:  # STRICT
            pattern_names = [p.name for p in self.REDACTION_PATTERNS]
        
        for pattern in self.REDACTION_PATTERNS:
            if pattern.name in pattern_names:
                self.compiled_patterns.append({
                    "name": pattern.name,
                    "regex": re.compile(pattern.pattern, pattern.flags),
                    "replacement": pattern.replacement
                })
    
    def redact_text(self, text: str, max_length: Optional[int] = None) -> str:
        """
        Redact sensitive information from text.
        
        Args:
            text: Text to redact
            max_length: Maximum allowed length (truncates if exceeded)
            
        Returns:
            Redacted text
        """
        if not text:
            return ""
        
        redacted = text
        
        # Apply all redaction patterns
        for pattern_info in self.compiled_patterns:
            try:
                redacted = pattern_info["regex"].sub(
                    pattern_info["replacement"], 
                    redacted
                )
            except (re.error, TypeError, AttributeError) as e:
                logger.error(f"Redaction pattern {pattern_info['name']} failed: {e}")
        
        # Normalize whitespace
        redacted = self._normalize_whitespace(redacted)
        
        # Truncate if needed (preserve word boundaries)
        if max_length and len(redacted) > max_length:
            if max_length <= 3:
                redacted = "..."
            else:
                # Find the last space before max_length-3
                truncate_pos = max_length - 3
                last_space = redacted.rfind(' ', 0, truncate_pos)
                if last_space > 0 and last_space > truncate_pos - 20:  # Don't go too far back
                    redacted = redacted[:last_space] + "..."
                else:
                    redacted = redacted[:truncate_pos] + "..."
        
        return redacted
    
    def redact_reasoning_ui(self, reasoning_ui: Dict[str, Any]) -> Dict[str, Any]:
        """
        Redact a complete reasoning UI structure.
        
        Args:
            reasoning_ui: UIReasoning dictionary
            
        Returns:
            Redacted reasoning UI
        """
        redacted = copy.deepcopy(reasoning_ui)
        
        # Redact summary
        if "summary" in redacted:
            redacted["summary"] = self.redact_text(
                redacted["summary"], 
                max_length=600
            )
        
        # Redact decision path
        if "decision_path" in redacted and isinstance(redacted["decision_path"], list):
            for step in redacted["decision_path"]:
                if isinstance(step, dict):
                    if "label" in step:
                        step["label"] = self.redact_text(step["label"], max_length=64)
                    if "action" in step:
                        step["action"] = self.redact_text(step["action"], max_length=180)
                    if "evidence" in step:
                        step["evidence"] = self.redact_text(step["evidence"], max_length=140)
        
        # Redact assumptions
        if "assumptions" in redacted and isinstance(redacted["assumptions"], list):
            redacted["assumptions"] = [
                self.redact_text(assumption, max_length=200)
                for assumption in redacted["assumptions"][:3]  # Limit to 3
            ]
        
        # Validate flags (no redaction needed, just ensure they're safe)
        if "flags" in redacted and isinstance(redacted["flags"], list):
            allowed_flags = {
                "downgraded_model", "missing_info", "tool_used", 
                "kb_consulted", "limited_budget", "processing_error",
                "parsing_error", "quality_check_failed"
            }
            redacted["flags"] = [
                flag for flag in redacted["flags"] 
                if flag in allowed_flags
            ]
        
        return redacted
    
    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace in text."""
        # Replace multiple spaces with single space
        text = re.sub(r'\s+', ' ', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        # Normalize line breaks
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        return text
    
    def validate_safe_content(self, content: Dict[str, Any]) -> bool:
        """
        Validate that content is safe to display.
        
        Args:
            content: Content dictionary to validate
            
        Returns:
            True if content appears safe
        """
        # Check for any remaining sensitive patterns using compiled patterns
        suspicious_pattern_names = [
            "api_key", "google_api_key", "email_password", 
            "unix_path", "windows_path"
        ]
        
        # Get patterns that should always be flagged as suspicious
        suspicious_patterns = []
        for pattern in self.REDACTION_PATTERNS:
            if pattern.name in suspicious_pattern_names:
                suspicious_patterns.append(pattern.pattern)
        
        content_str = str(content)
        
        for i, pattern in enumerate(suspicious_patterns):
            try:
                if re.search(pattern, content_str, re.IGNORECASE):
                    pattern_name = suspicious_pattern_names[i] if i < len(suspicious_pattern_names) else "unknown"
                    logger.warning(f"Suspicious pattern found: {pattern_name}")
                    return False
            except (re.error, TypeError) as e:
                logger.error(f"Error checking suspicious pattern {suspicious_pattern_names[i] if i < len(suspicious_pattern_names) else 'unknown'}: {e}")
                continue
        
        return True


# Convenience functions
_default_redactor = SafetyRedactor(RedactionLevel.STANDARD)


def redact_reasoning_ui(reasoning_ui: Dict[str, Any]) -> Dict[str, Any]:
    """Redact reasoning UI with default settings."""
    return _default_redactor.redact_reasoning_ui(reasoning_ui)


def redact_text(text: str, max_length: Optional[int] = None) -> str:
    """Redact text with default settings."""
    return _default_redactor.redact_text(text, max_length)