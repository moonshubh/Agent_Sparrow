"""
FeedMe Security Module
Production-ready security utilities for input validation, sanitization, and protection

Features:
- Input validation with comprehensive checks
- SQL injection prevention
- XSS protection
- Path traversal prevention
- Rate limiting
- File upload security
- CSRF protection
- Security headers
"""

import re
import html
import hashlib
import secrets
import mimetypes
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timezone, timedelta
from pathlib import Path
import unicodedata
from urllib.parse import urlparse
import ipaddress
import logging

from pydantic import BaseModel, Field, field_validator
from fastapi import HTTPException, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import bleach
from slowapi import Limiter
from slowapi.util import get_remote_address

# Configure logging
logger = logging.getLogger(__name__)

# Security constants
SECURITY_CONFIG = {
    "MAX_TEXT_LENGTH": 1000000,  # 1 million characters
    "MIN_TEXT_LENGTH": 1,
    "MAX_TITLE_LENGTH": 255,
    "MAX_DESCRIPTION_LENGTH": 1000,
    "MAX_FILE_SIZE": 10 * 1024 * 1024,  # 10MB
    "MAX_FOLDER_NAME_LENGTH": 100,
    "MAX_TAG_LENGTH": 50,
    "MAX_TAGS": 20,
    "ALLOWED_FILE_EXTENSIONS": [".txt", ".pdf", ".doc", ".docx"],
    "ALLOWED_MIME_TYPES": [
        "text/plain",
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ],
    "RATE_LIMIT_WINDOW": 60,  # seconds
    "RATE_LIMIT_REQUESTS": 100,
    "MAX_PATH_DEPTH": 5,
    "BLOCKED_PATTERNS": [
        r"<script[^>]*>.*?</script>",
        r"<iframe[^>]*>.*?</iframe>",
        r"javascript:",
        r"on\w+\s*=",
        r"<object[^>]*>.*?</object>",
        r"<embed[^>]*>",
        r"data:text/html",
        r"vbscript:"
    ],
    "SQL_PATTERNS": [
        r"\b(union|select|insert|update|delete|drop|create|alter|exec|execute)\b",
        r"(--|/\*|\*/)",
        r"(;|'|\"|`|\\x00|\\n|\\r|\\x1a)"
    ],
    "PATH_TRAVERSAL_PATTERNS": [
        r"\.\./",
        r"\.\.\\",
        r"%2e%2e",
        r"%252e%252e"
    ]
}

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)


class SecurityValidator:
    """Central security validation class"""
    
    @staticmethod
    def validate_text_length(text: str, min_length: int = None, max_length: int = None) -> bool:
        """Validate text length"""
        min_len = min_length or SECURITY_CONFIG["MIN_TEXT_LENGTH"]
        max_len = max_length or SECURITY_CONFIG["MAX_TEXT_LENGTH"]
        return min_len <= len(text) <= max_len
    
    @staticmethod
    def detect_xss_patterns(text: str) -> List[str]:
        """Detect potential XSS patterns in text"""
        detected_patterns = []
        for pattern in SECURITY_CONFIG["BLOCKED_PATTERNS"]:
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                detected_patterns.append(pattern)
        return detected_patterns
    
    @staticmethod
    def detect_sql_injection(text: str) -> List[str]:
        """Detect potential SQL injection patterns"""
        detected_patterns = []
        for pattern in SECURITY_CONFIG["SQL_PATTERNS"]:
            if re.search(pattern, text, re.IGNORECASE):
                detected_patterns.append(pattern)
        return detected_patterns
    
    @staticmethod
    def detect_path_traversal(path: str) -> bool:
        """Detect path traversal attempts"""
        for pattern in SECURITY_CONFIG["PATH_TRAVERSAL_PATTERNS"]:
            if re.search(pattern, path, re.IGNORECASE):
                return True
        return False
    
    @staticmethod
    def validate_file_extension(filename: str) -> bool:
        """Validate file extension"""
        ext = Path(filename).suffix.lower()
        return ext in SECURITY_CONFIG["ALLOWED_FILE_EXTENSIONS"]
    
    @staticmethod
    def validate_mime_type(mime_type: str) -> bool:
        """Validate MIME type"""
        return mime_type in SECURITY_CONFIG["ALLOWED_MIME_TYPES"]
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename for safe storage"""
        # Remove path components
        filename = Path(filename).name
        
        # Remove unicode control characters
        filename = "".join(ch for ch in filename if unicodedata.category(ch)[0] != "C")
        
        # Replace dangerous characters
        filename = re.sub(r'[^\w\s.-]', '_', filename)
        
        # Remove multiple dots
        filename = re.sub(r'\.{2,}', '.', filename)
        
        # Limit length
        max_length = 255
        if len(filename) > max_length:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            filename = f"{name[:max_length-len(ext)-10]}_truncated.{ext}" if ext else name[:max_length]
        
        return filename or "unnamed_file"
    
    @staticmethod
    def sanitize_text(text: str, strip_html: bool = True) -> str:
        """Sanitize text content"""
        if strip_html:
            # Use bleach to strip all HTML
            text = bleach.clean(text, tags=[], strip=True)
        else:
            # Allow only safe HTML tags
            text = bleach.clean(
                text,
                tags=['b', 'i', 'em', 'strong', 'a', 'br', 'p'],
                attributes={'a': ['href']},
                strip=True
            )
        
        # Remove null bytes and control characters
        text = text.replace('\x00', '')
        text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in '\n\r\t')
        
        return text.strip()
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL for safety"""
        try:
            parsed = urlparse(url)
            
            # Check protocol
            if parsed.scheme not in ['http', 'https']:
                return False
            
            # Check for local addresses
            hostname = parsed.hostname
            if not hostname:
                return False
            
            # Block localhost and private IPs
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback:
                    return False
            except ValueError:
                # Not an IP address, check hostname
                if hostname.lower() in ['localhost', '127.0.0.1', '::1']:
                    return False
            
            return True
        except Exception:
            return False
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email address"""
        email_regex = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
        return bool(email_regex.match(email)) and len(email) <= 254


class SecureTextModel(BaseModel):
    """Pydantic model for secure text validation"""
    text: str = Field(..., min_length=1, max_length=SECURITY_CONFIG["MAX_TEXT_LENGTH"])
    
    @field_validator('text')
    def validate_text_security(cls, v):
        # Check for XSS patterns
        xss_patterns = SecurityValidator.detect_xss_patterns(v)
        if xss_patterns:
            raise ValueError(f"Text contains potentially harmful content: {xss_patterns[0]}")
        
        # Sanitize text
        return SecurityValidator.sanitize_text(v)


class SecureTitleModel(BaseModel):
    """Pydantic model for secure title validation"""
    title: str = Field(..., min_length=1, max_length=SECURITY_CONFIG["MAX_TITLE_LENGTH"])
    
    @field_validator('title')
    def validate_title_security(cls, v):
        # Check for XSS patterns
        xss_patterns = SecurityValidator.detect_xss_patterns(v)
        if xss_patterns:
            raise ValueError("Title contains potentially harmful content")
        
        # Sanitize title
        return SecurityValidator.sanitize_text(v, strip_html=True)


class SecureFolderNameModel(BaseModel):
    """Pydantic model for secure folder name validation"""
    name: str = Field(..., min_length=1, max_length=SECURITY_CONFIG["MAX_FOLDER_NAME_LENGTH"])
    
    @field_validator('name')
    def validate_folder_name(cls, v):
        # Check for path traversal
        if SecurityValidator.detect_path_traversal(v):
            raise ValueError("Folder name contains invalid characters")
        
        # Allow only alphanumeric, spaces, hyphens, underscores, parentheses
        if not re.match(r'^[a-zA-Z0-9\s\-_()]+$', v):
            raise ValueError("Folder name contains invalid characters")
        
        return v.strip()


class SecureSearchModel(BaseModel):
    """Pydantic model for secure search query validation"""
    query: str = Field(..., max_length=200)
    
    @field_validator('query')
    def validate_search_query(cls, v):
        # Check for SQL injection
        sql_patterns = SecurityValidator.detect_sql_injection(v)
        if sql_patterns:
            raise ValueError("Search query contains invalid characters")
        
        # Sanitize query
        return SecurityValidator.sanitize_text(v, strip_html=True)


def generate_csrf_token() -> str:
    """Generate a secure CSRF token"""
    return secrets.token_urlsafe(32)


def verify_csrf_token(token: str, session_token: str) -> bool:
    """Verify CSRF token"""
    return secrets.compare_digest(token, session_token)


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Hash password with salt"""
    if not salt:
        salt = secrets.token_hex(32)
    
    # Use PBKDF2 with SHA256
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # iterations
    )
    
    return key.hex(), salt


def verify_password(password: str, hashed: str, salt: str) -> bool:
    """Verify password against hash"""
    key, _ = hash_password(password, salt)
    return secrets.compare_digest(key, hashed)


def create_secure_session(user_id: str, ip_address: str) -> Dict[str, Any]:
    """Create a secure session"""
    session_id = secrets.token_urlsafe(32)
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(hours=24)
    
    return {
        "session_id": session_id,
        "user_id": user_id,
        "ip_address": ip_address,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "csrf_token": generate_csrf_token()
    }


def add_security_headers(response: Response) -> Response:
    """Add security headers to response"""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' wss: https:; "
        "media-src 'self'; "
        "object-src 'none'; "
        "frame-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "upgrade-insecure-requests"
    )
    return response


class FileUploadValidator:
    """Validate file uploads for security"""
    
    @staticmethod
    def validate_file(
        filename: str,
        file_size: int,
        mime_type: Optional[str] = None,
        content: Optional[bytes] = None
    ) -> Tuple[bool, Optional[str]]:
        """Comprehensive file validation"""
        
        # Validate filename
        if not filename:
            return False, "Filename is required"
        
        sanitized_filename = SecurityValidator.sanitize_filename(filename)
        if not SecurityValidator.validate_file_extension(sanitized_filename):
            return False, f"File type not allowed. Allowed types: {', '.join(SECURITY_CONFIG['ALLOWED_FILE_EXTENSIONS'])}"
        
        # Validate file size
        if file_size > SECURITY_CONFIG["MAX_FILE_SIZE"]:
            return False, f"File size exceeds maximum allowed size of {SECURITY_CONFIG['MAX_FILE_SIZE'] // (1024*1024)}MB"
        
        # Validate MIME type if provided
        if mime_type and not SecurityValidator.validate_mime_type(mime_type):
            return False, "File type not allowed based on MIME type"
        
        # If content is provided, perform additional checks
        if content:
            # Check file signature (magic numbers)
            if not FileUploadValidator._validate_file_signature(content, sanitized_filename):
                return False, "File content does not match file extension"
            
            # Scan for malicious content
            if FileUploadValidator._detect_malicious_content(content):
                return False, "File contains potentially malicious content"
        
        return True, None
    
    @staticmethod
    def _validate_file_signature(content: bytes, filename: str) -> bool:
        """Validate file signature matches extension"""
        ext = Path(filename).suffix.lower()
        
        # File signatures (magic numbers)
        signatures = {
            '.pdf': b'%PDF',
            '.txt': None,  # Text files don't have a signature
            '.doc': b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1',
            '.docx': b'PK\x03\x04'
        }
        
        expected_sig = signatures.get(ext)
        if expected_sig is None:
            return True  # No signature to check
        
        return content.startswith(expected_sig)
    
    @staticmethod
    def _detect_malicious_content(content: bytes) -> bool:
        """Detect potentially malicious content in file"""
        # Convert to string for pattern matching
        try:
            text_content = content.decode('utf-8', errors='ignore')
        except:
            return False  # Binary file, skip text-based checks
        
        # Check for suspicious patterns
        suspicious_patterns = [
            r'<script[^>]*>.*?</script>',
            r'eval\s*\(',
            r'exec\s*\(',
            r'__import__\s*\(',
            r'subprocess\.',
            r'os\.system\s*\('
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, text_content, re.IGNORECASE | re.DOTALL):
                return True
        
        return False


class IPAddressValidator:
    """Validate and check IP addresses"""
    
    @staticmethod
    def is_valid_ip(ip: str) -> bool:
        """Check if string is valid IP address"""
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def is_private_ip(ip: str) -> bool:
        """Check if IP is private"""
        try:
            ip_obj = ipaddress.ip_address(ip)
            return ip_obj.is_private or ip_obj.is_loopback
        except ValueError:
            return False
    
    @staticmethod
    def is_trusted_ip(ip: str, trusted_ranges: List[str]) -> bool:
        """Check if IP is in trusted ranges"""
        try:
            ip_obj = ipaddress.ip_address(ip)
            for range_str in trusted_ranges:
                if ip_obj in ipaddress.ip_network(range_str):
                    return True
            return False
        except ValueError:
            return False


# Security middleware functions
async def validate_request_size(request: Request, max_size: int = 10 * 1024 * 1024):
    """Validate request body size"""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"Request body too large. Maximum size: {max_size} bytes"
        )


async def validate_content_type(request: Request, allowed_types: List[str]):
    """Validate request content type"""
    content_type = request.headers.get("content-type", "").split(";")[0].strip()
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content type. Allowed types: {', '.join(allowed_types)}"
        )


# Audit logging
class SecurityAuditLogger:
    """Log security-related events"""
    
    @staticmethod
    def log_access(user_id: str, resource: str, action: str, ip_address: str, success: bool):
        """Log access attempt"""
        logger.info(
            "Security Access Log",
            extra={
                "user_id": user_id,
                "resource": resource,
                "action": action,
                "ip_address": ip_address,
                "success": success,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
    
    @staticmethod
    def log_validation_failure(
        validation_type: str,
        input_data: str,
        reason: str,
        ip_address: str
    ):
        """Log validation failure"""
        logger.warning(
            "Security Validation Failure",
            extra={
                "validation_type": validation_type,
                "input_preview": input_data[:100] if input_data else None,
                "reason": reason,
                "ip_address": ip_address,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
    
    @staticmethod
    def log_suspicious_activity(
        activity_type: str,
        details: Dict[str, Any],
        ip_address: str
    ):
        """Log suspicious activity"""
        logger.warning(
            "Suspicious Activity Detected",
            extra={
                "activity_type": activity_type,
                "details": details,
                "ip_address": ip_address,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )