"""
Privacy and Data Protection Module for Log Analysis Agent

This module implements comprehensive privacy controls with paranoid-level
security for handling potentially sensitive log data. All components follow
the principle of least privilege and defense-in-depth.

Security Principles:
- Zero persistence of sensitive data
- Complete data sanitization
- Guaranteed cleanup on all code paths
- Multi-layer validation and protection
"""

from .sanitizer import LogSanitizer, RedactionLevel, SanitizationConfig
from .cleanup import LogCleanupManager, CleanupConfig
from .attachment_sanitizer import AttachmentSanitizer

__all__ = [
    'LogSanitizer',
    'RedactionLevel',
    'SanitizationConfig',
    'LogCleanupManager',
    'CleanupConfig',
    'AttachmentSanitizer',
]