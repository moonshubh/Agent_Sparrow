"""
Core Constants Module

Central location for application-wide constants and configuration values.
This module helps avoid hardcoded values scattered throughout the codebase.
"""

from typing import Dict

# Agent Session Limits
# Default maximum active sessions per agent type
AGENT_SESSION_LIMITS: Dict[str, int] = {
    "primary": 5,
    "log_analysis": 3,
    "research": 5,
    "router": 10,
}

# Agent Configuration Defaults
AGENT_MESSAGE_LENGTH_LIMITS: Dict[str, int] = {
    "primary": 10000,
    "log_analysis": 50000,
    "research": 15000,
    "router": 5000,
}

AGENT_SESSION_TIMEOUT_HOURS: Dict[str, int] = {
    "primary": 24,
    "log_analysis": 12,
    "research": 24,
    "router": 6,
}

# Database Configuration
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Response Configuration
MAX_FOLLOW_UP_QUESTIONS = 5
MIN_FOLLOW_UP_QUESTIONS = 3

# Logging Configuration
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Security Configuration
MAX_LOGIN_ATTEMPTS = 5
LOGIN_TIMEOUT_MINUTES = 15
SESSION_EXPIRY_HOURS = 24

# Rate Limiting
DEFAULT_RATE_LIMIT = "100/hour"
STRICT_RATE_LIMIT = "20/minute"

# Cache Configuration
CACHE_TTL_SECONDS = 3600  # 1 hour
CACHE_TTL_LONG_SECONDS = 86400  # 24 hours

# File Upload Configuration
MAX_FILE_SIZE_MB = 10
ALLOWED_FILE_EXTENSIONS = {".txt", ".log", ".json", ".csv", ".md"}

# Email Configuration
EMAIL_PROVIDERS = {
    "gmail": {"imap": "imap.gmail.com", "smtp": "smtp.gmail.com", "port": 993},
    "outlook": {
        "imap": "outlook.office365.com",
        "smtp": "smtp.office365.com",
        "port": 993,
    },
    "yahoo": {
        "imap": "imap.mail.yahoo.com",
        "smtp": "smtp.mail.yahoo.com",
        "port": 993,
    },
}

# Error Messages
ERROR_MESSAGES = {
    "session_limit_exceeded": "Maximum number of active sessions reached for this agent type",
    "invalid_credentials": "Invalid username or password",
    "session_expired": "Your session has expired. Please log in again",
    "rate_limit_exceeded": "Too many requests. Please try again later",
    "file_too_large": f"File size exceeds the maximum limit of {MAX_FILE_SIZE_MB}MB",
    "invalid_file_type": f"Invalid file type. Allowed types: {', '.join(ALLOWED_FILE_EXTENSIONS)}",
    "database_error": "A database error occurred. Please try again later",
    "internal_error": "An internal error occurred. Please contact support if the issue persists",
}

# Success Messages
SUCCESS_MESSAGES = {
    "session_created": "Chat session created successfully",
    "session_updated": "Chat session updated successfully",
    "session_deleted": "Chat session deleted successfully",
    "message_sent": "Message sent successfully",
    "file_uploaded": "File uploaded successfully",
    "settings_updated": "Settings updated successfully",
}

# API Response Codes
API_RESPONSE_CODES = {
    "SUCCESS": 200,
    "CREATED": 201,
    "BAD_REQUEST": 400,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "RATE_LIMITED": 429,
    "SERVER_ERROR": 500,
}
