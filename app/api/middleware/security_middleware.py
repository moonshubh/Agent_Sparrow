"""
Security Middleware for FastAPI
Adds security headers and performs request validation
"""

from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import time
import logging
from typing import Callable

from app.feedme.security import add_security_headers, IPAddressValidator, SecurityAuditLogger

logger = logging.getLogger(__name__)
audit_logger = SecurityAuditLogger()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Process the request
        response = await call_next(request)
        
        # Add security headers
        response = add_security_headers(response)
        
        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Validate requests for security concerns"""
    
    def __init__(self, app, max_body_size: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_body_size = max_body_size
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check content length
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_body_size:
            audit_logger.log_validation_failure(
                "request_size",
                f"Size: {content_length}",
                f"Exceeds max size: {self.max_body_size}",
                request.client.host
            )
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"}
            )
        
        # Log request timing
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Log successful request
            process_time = time.time() - start_time
            logger.info(
                f"{request.method} {request.url.path} "
                f"completed in {process_time:.3f}s "
                f"with status {response.status_code}"
            )
            
            # Add processing time header
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"{request.method} {request.url.path} "
                f"failed after {process_time:.3f}s: {str(e)}"
            )
            
            # Log suspicious activity if appropriate
            if "script" in str(e).lower() or "sql" in str(e).lower():
                audit_logger.log_suspicious_activity(
                    "potential_attack",
                    {
                        "method": request.method,
                        "path": request.url.path,
                        "error": str(e)
                    },
                    request.client.host
                )
            
            raise


class IPFilterMiddleware(BaseHTTPMiddleware):
    """Filter requests by IP address"""
    
    def __init__(self, app, blocked_ips: list = None, allowed_ips: list = None):
        super().__init__(app)
        self.blocked_ips = set(blocked_ips or [])
        self.allowed_ips = set(allowed_ips or [])
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host
        
        # Check if IP is blocked
        if client_ip in self.blocked_ips:
            audit_logger.log_suspicious_activity(
                "blocked_ip_access",
                {"ip": client_ip, "path": request.url.path},
                client_ip
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Access denied"}
            )
        
        # Check if IP allowlist is enabled
        if self.allowed_ips and client_ip not in self.allowed_ips:
            # Check if it's a private IP (for development)
            if not IPAddressValidator.is_private_ip(client_ip):
                audit_logger.log_suspicious_activity(
                    "unauthorized_ip_access",
                    {"ip": client_ip, "path": request.url.path},
                    client_ip
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Access denied"}
                )
        
        return await call_next(request)


def setup_security_middleware(app):
    """Setup all security middleware for the application"""
    
    # CORS middleware (configure as needed)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure with specific origins in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Process-Time"],
    )
    
    # Security headers middleware
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Request validation middleware
    app.add_middleware(
        RequestValidationMiddleware,
        max_body_size=10 * 1024 * 1024  # 10MB
    )
    
    # IP filter middleware (optional - configure as needed)
    # app.add_middleware(
    #     IPFilterMiddleware,
    #     blocked_ips=["192.168.1.100"],  # Example blocked IPs
    #     allowed_ips=[]  # Leave empty to allow all
    # )
    
    logger.info("Security middleware configured successfully")