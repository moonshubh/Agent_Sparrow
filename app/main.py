import logging
from datetime import datetime, timezone
from uuid import uuid4
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import os
import asyncio
from langchain_core.messages import HumanMessage

# Ensure AG-UI LangGraph custom events propagate even if site-packages are overwritten
from app.patches.agui_custom_events import apply_patch as _apply_agui_patch
_apply_agui_patch()

# Fix circular reference issue in AG-UI state serialization
from app.patches.agui_json_safe import apply_patch as _apply_json_safe_patch
_apply_json_safe_patch()

# Rate limiting imports
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Custom rate limiting exceptions
from app.core.rate_limiting.exceptions import (
    RateLimitExceededException,
    CircuitBreakerOpenException,
    GeminiServiceUnavailableException
)

from app.agents import agent_graph
from app.agents import GraphState # Corrected import location
from app.api.v1.endpoints import search_tools_endpoints # Added for search tools endpoints
from app.api.v1.endpoints import (
    logs_endpoints,  # Log analysis (JSON + SSE + sessions)
    research_endpoints,  # Research (JSON + SSE)
    agui_endpoints,  # AG-UI streaming endpoint (primary streaming path)
    models_endpoints,  # Models listing for frontend selector
    metadata_endpoints,  # Phase 6: Memory stats, quota status, trace metadata
)
from app.api.v1.endpoints import agents_endpoints  # Agent metadata discovery
from app.api.v1.endpoints import tavily_selftest  # Dev-only Tavily diagnostics
from app.api.v1.endpoints import feedme  # FeedMe transcript ingestion (modular package)
from app.api.v1.endpoints import text_approval_endpoints  # Text approval workflow for FeedMe
from app.api.v1.endpoints import chat_session_endpoints  # Chat session persistence
from app.api.v1.endpoints import rate_limit_endpoints  # Rate limiting monitoring
from app.api.v1.endpoints import feedme_intelligence  # FeedMe AI intelligence endpoints
from app.api.v1.endpoints import agent_interrupt_endpoints  # HITL interrupt controls
# from app.api.v1.endpoints import secure_log_analysis  # Secure Log Analysis endpoints - Disabled due to reasoning engine removal
from app.api.v1.endpoints import (
    global_knowledge_observability,  # Global knowledge observability APIs
    global_knowledge_feedback,  # Global knowledge submission APIs
    message_feedback_endpoints,  # Message thumbs up/down feedback
)
from app.api.v1.websocket import feedme_websocket  # FeedMe WebSocket endpoints
from app.core.settings import settings
from app.db.embedding_config import EXPECTED_DIM
from app.integrations.zendesk import router as zendesk_router
from app.integrations.zendesk.admin_endpoints import router as zendesk_admin_router
from app.integrations.zendesk.scheduler import start_background_scheduler

# Conditional imports based on security configuration
auth_endpoints = None
api_key_endpoints = None

if settings.should_enable_auth_endpoints():
    try:
        from app.api.v1.endpoints import auth as auth_endpoints
        logging.info("Authentication endpoints enabled")
    except ImportError as e:
        logging.warning(f"Failed to import auth endpoints: {e}")
        auth_endpoints = None

if settings.should_enable_api_key_endpoints():
    try:
        from app.api.v1.endpoints import api_key_endpoints
        logging.info("API key endpoints enabled")
    except ImportError as e:
        logging.warning(f"Failed to import API key endpoints: {e}")
        api_key_endpoints = None

# OpenTelemetry Setup
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import hashlib

# Configure the resource for your application
resource = Resource(attributes={
    "service.name": "mb-sparrow-agent-server"
})

# Determine if OpenTelemetry exporter should be enabled (e.g., in production)
ENABLE_OTEL: bool = os.getenv("ENABLE_OTEL", "false").lower() in {"1", "true", "yes"}

# Set up a TracerProvider
trace.set_tracer_provider(TracerProvider(resource=resource))

if ENABLE_OTEL:
    try:
        # Configure an OTLP exporter
        # Ensure your OTLP collector is running and accessible (e.g., http://localhost:4318/v1/traces)
        otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")  # Adjust endpoint as needed

        # Use a BatchSpanProcessor for better performance in production
        span_processor = BatchSpanProcessor(otlp_exporter)

        # Add the span processor to the tracer provider
        trace.get_tracer_provider().add_span_processor(span_processor)
    except Exception as e:  # pragma: no cover -- best-effort safeguard
        # Fallback: disable exporter if configuration fails (e.g., collector not running)
        print(f"[OTel] Warning: failed to configure OTLP exporter -> {e}. Telemetry disabled.")

# Get a tracer instance
tracer = trace.get_tracer(__name__)

# Initialize global rate limiter
limiter = Limiter(key_func=get_remote_address)

# FastAPI instance
app = FastAPI(
    title="MB-Sparrow Agent Server",
    version="1.0",
    description="API server for the MB-Sparrow multi-agent system."
)

# Configure LangSmith tracing during startup (if enabled)
from app.core.tracing import configure_langsmith
configure_langsmith()

# Enable FastAPI auto-instrumentation for OpenTelemetry when enabled
if ENABLE_OTEL:
    try:  # pragma: no cover - best-effort, do not fail app startup on instrumentation issues
        FastAPIInstrumentor().instrument_app(app)
    except Exception as _otel_exc:
        print(f"[OTel] Warning: failed to instrument FastAPI -> {_otel_exc}. Continuing without instrumentation.")

@app.middleware("http")
async def _debug_log_agui_requests(request: Request, call_next):
    if request.url.path.startswith("/api/v1/agui"):
        body_bytes = await request.body()
        try:
            body_preview = body_bytes.decode("utf-8")
        except Exception:
            body_preview = repr(body_bytes)
        logging.info("agui_request path=%s method=%s body=%s", request.url.path, request.method, body_preview)
    response = await call_next(request)
    return response

# AG-UI streaming endpoint
# LangGraph stream endpoint via router: /api/v1/agui/stream
# GraphQL shim removed - use stream endpoint for all chat interactions

# Add SlowAPI middleware for rate limiting
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Add CORS middleware (explicit origins when credentials are allowed)
cors_env = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
if cors_env:
    allowed_origins = [o.strip() for o in cors_env.split(",") if o.strip()]
else:
    # Safe defaults for local dev
    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",  # Added port 3001 support
        "http://127.0.0.1:3001",  # Added port 3001 support
        "http://localhost:3010",  # Playwright / dev override
        "http://127.0.0.1:3010",
    ]

is_production_mode = settings.is_production_mode()
# Stricter octet pattern (0-255) to avoid accepting invalid IPs like 999.999.999.999.
octet = r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)"
allow_origin_regex = rf"^http:\/\/192\.168\.{octet}\.{octet}:3000$"
if not is_production_mode:
    allow_origin_regex = (
        r"^http:\/\/(localhost|127\.0\.0\.1)(:[0-9]{1,5})?$|" + allow_origin_regex
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conditionally include authentication router
if auth_endpoints and settings.should_enable_auth_endpoints():
    app.include_router(auth_endpoints.router, prefix="/api/v1/auth", tags=["Authentication"])
    logging.info("Authentication router registered")
else:
    logging.warning("Authentication router not registered - endpoints disabled or import failed")

# Include local auth bypass router for development
if os.getenv("ENABLE_LOCAL_AUTH_BYPASS", "false").lower() == "true":
    try:
        from app.api.v1.endpoints import local_auth
        app.include_router(local_auth.router, prefix="/api/v1/auth", tags=["Local Auth"])
        logging.warning("⚠️  LOCAL AUTH BYPASS ENABLED - DO NOT USE IN PRODUCTION")
    except ImportError as e:
        logging.error(f"Failed to import local auth endpoints: {e}")

# Always include core application routers
app.include_router(search_tools_endpoints.router, prefix="/api/v1/tools", tags=["Search Tools"])
app.include_router(tavily_selftest.router, prefix="/api/v1", tags=["Search Tools"])  # GET /api/v1/tools/tavily/self-test
# Register Agent Interaction routers (modularized)
app.include_router(logs_endpoints.router, prefix="/api/v1", tags=["Agent Interaction"]) 
app.include_router(research_endpoints.router, prefix="/api/v1", tags=["Agent Interaction"]) 
app.include_router(agui_endpoints.router, prefix="/api/v1", tags=["AG-UI"])  # /api/v1/agui/stream
app.include_router(models_endpoints.router, prefix="/api/v1", tags=["Models"])  # /api/v1/models
app.include_router(agents_endpoints.router, prefix="/api/v1", tags=["Agents"])  # /api/v1/agents
app.include_router(metadata_endpoints.router, prefix="/api/v1", tags=["Metadata"])  # /api/v1/metadata - Phase 6
app.include_router(global_knowledge_observability.router, prefix="/api/v1", tags=["Global Knowledge"])
app.include_router(global_knowledge_feedback.router, prefix="/api/v1", tags=["Global Knowledge"])
app.include_router(message_feedback_endpoints.router, prefix="/api/v1", tags=["Message Feedback"])  # /api/v1/feedback/message
# Register FeedMe routes (modular package)
app.include_router(feedme.router, prefix="/api/v1", tags=["FeedMe"])
# Register FeedMe Text Approval routes  
app.include_router(text_approval_endpoints.router, tags=["FeedMe Text Approval"])
# Register FeedMe Intelligence routes
app.include_router(feedme_intelligence.router, prefix="/api/v1", tags=["FeedMe Intelligence"])
# Register Chat Session routes
app.include_router(chat_session_endpoints.router, prefix="/api/v1", tags=["Chat Sessions"])
# Register Rate Limiting routes
app.include_router(rate_limit_endpoints.router, prefix="/api/v1", tags=["Rate Limiting"])
# Register Agent Interrupt control routes
app.include_router(agent_interrupt_endpoints.router, prefix="/api/v1", tags=["Agent Interrupts"])
# Register Secure Log Analysis routes
# app.include_router(secure_log_analysis.router, prefix="/api/v1", tags=["Secure Log Analysis"])  # Disabled due to reasoning engine removal
# Register Zendesk integration routes
app.include_router(zendesk_router, prefix="/api/v1", tags=["Zendesk"])
app.include_router(zendesk_admin_router, prefix="/api/v1", tags=["Zendesk Admin"])

# Conditionally include API Key Management router
if api_key_endpoints and settings.should_enable_api_key_endpoints():
    app.include_router(api_key_endpoints.router, prefix="/api/v1", tags=["API Key Management"])
    logging.info("API Key Management router registered")
else:
    logging.warning("API Key Management router not registered - endpoints disabled or import failed")

# Register FeedMe WebSocket routes
app.include_router(feedme_websocket.router, prefix="/ws", tags=["FeedMe WebSocket"])

@app.on_event("startup")
async def startup_event():
    """Log security configuration on application startup."""
    is_production = settings.is_production_mode()
    auth_enabled = settings.should_enable_auth_endpoints()
    api_key_enabled = settings.should_enable_api_key_endpoints()
    
    # Debug environment variable loading
    import os
    skip_auth_env = os.getenv("SKIP_AUTH", "not_set")
    
    logging.info("=== MB-Sparrow Security Configuration ===")
    logging.info(f"Production Mode: {is_production}")
    logging.info(f"Authentication Endpoints: {'ENABLED' if auth_enabled else 'DISABLED'}")
    logging.info(f"API Key Endpoints: {'ENABLED' if api_key_enabled else 'DISABLED'}")
    logging.info(f"Skip Auth (settings): {settings.skip_auth}")
    logging.info(f"Skip Auth (env raw): {skip_auth_env}")
    logging.info(f"Development User ID: {settings.development_user_id}")
    # Reflect real JWT secret configuration (prefer explicit env var; treat default placeholder as not configured)
    jwt_env = os.getenv("JWT_SECRET_KEY")
    jwt_val = jwt_env if jwt_env is not None else getattr(settings, "jwt_secret_key", None)
    jwt_configured = bool(jwt_val) and str(jwt_val) != "change-this-in-production"
    logging.info(f"JWT Secret Configured: {jwt_configured}")

    logging.info("=== Global Knowledge Configuration ===")
    logging.info(
        "Global Knowledge Flags: inject=%s, store_adapter=%s, store_writes=%s, retrieval_primary=%s",
        settings.enable_global_knowledge_injection,
        settings.enable_store_adapter,
        settings.enable_store_writes,
        settings.get_retrieval_primary(),
    )
    logging.info(
        "Global Knowledge Effective: should_enable=%s, should_use_store_adapter=%s, should_enable_store_writes=%s, store_configured=%s",
        settings.should_enable_global_knowledge(),
        settings.should_use_store_adapter(),
        settings.should_enable_store_writes(),
        settings.has_global_store_configuration(),
    )
    logging.info("=======================================")
    
    if not is_production:
        logging.warning("Running in development mode - some security features may be disabled")
    
    if not auth_enabled or not api_key_enabled:
        logging.warning("Some security endpoints are disabled - ensure this is intentional")
    
    logging.info("==========================================")

    # Start Zendesk background scheduler (feature guarded internally)
    try:
        asyncio.get_event_loop().create_task(start_background_scheduler())
        logging.info("Zendesk scheduler task started")
    except Exception as e:  # pragma: no cover
        logging.error("Failed to start Zendesk scheduler: %s", e)


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on application shutdown to prevent memory leaks."""
    logging.info("=== MB-Sparrow Shutdown Initiated ===")

    # Clear rate limiters and stop cleanup tasks
    try:
        from app.core.rate_limiting.memory_limiter import get_rate_limiter, get_gemini_limiter
        rate_limiter = get_rate_limiter()
        if hasattr(rate_limiter, 'stop'):
            await rate_limiter.stop()
        gemini_limiter = get_gemini_limiter()
        if hasattr(gemini_limiter, 'stop'):
            await gemini_limiter.stop()
        logging.info("Rate limiters stopped")
    except Exception as e:
        logging.warning(f"Rate limiter cleanup failed: {e}")

    # Clear Supabase client singleton (thread-safe)
    try:
        from app.db.supabase.client import clear_supabase_client
        clear_supabase_client()
        logging.info("Supabase client cleared")
    except Exception as e:
        logging.warning(f"Supabase cleanup failed: {e}")

    # Clear Redis cache client
    try:
        from app.cache import redis_cache
        if hasattr(redis_cache, '_redis_client') and redis_cache._redis_client:
            redis_cache._redis_client = None
        logging.info("Redis cache client cleared")
    except Exception as e:
        logging.warning(f"Redis cache cleanup failed: {e}")

    # Force garbage collection
    import gc
    gc.collect()
    logging.info("=== MB-Sparrow Shutdown Complete ===")


# Global exception handlers for rate limiting

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """
    Global handler for SlowAPI rate limit exceeded errors.
    Provides user-friendly feedback with proper HTTP status.
    """
    logging.warning(f"Rate limit exceeded for {request.client.host}: {exc.detail}")
    
    response = JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
            "detail": str(exc.detail),
            "type": "rate_limit"
        },
    )
    response.headers["Retry-After"] = "60"  # Suggest retry after 60 seconds
    return response


@app.exception_handler(RateLimitExceededException)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceededException):
    """
    Global handler for custom rate limiting exceptions from Gemini rate limiter.
    Provides detailed rate limiting information and retry guidance.
    """
    logging.warning(
        f"Custom rate limit exceeded for {request.client.host if request.client else 'unknown'}: "
        f"{exc.message} (model: {exc.model})"
    )
    
    response = JSONResponse(
        status_code=429,
        content=exc.to_dict(),
    )
    
    # Add retry-after header if available
    if exc.retry_after:
        response.headers["Retry-After"] = str(exc.retry_after)
    else:
        response.headers["Retry-After"] = "60"  # Default to 60 seconds
    
    return response


@app.exception_handler(CircuitBreakerOpenException)
async def circuit_breaker_handler(request: Request, exc: CircuitBreakerOpenException):
    """
    Global handler for circuit breaker open exceptions.
    Indicates service is temporarily unavailable due to repeated failures.
    """
    logging.error(
        f"Circuit breaker open for {request.client.host if request.client else 'unknown'}: "
        f"{exc.message} (failures: {exc.failure_count})"
    )
    
    response = JSONResponse(
        status_code=503,
        content=exc.to_dict(),
    )
    
    # Add retry-after header based on estimated recovery time
    if exc.estimated_recovery:
        retry_seconds = max(60, int((exc.estimated_recovery - datetime.now()).total_seconds()))
        response.headers["Retry-After"] = str(retry_seconds)
    else:
        response.headers["Retry-After"] = "300"  # Default to 5 minutes
        
    return response


@app.exception_handler(GeminiServiceUnavailableException)
async def gemini_service_unavailable_handler(request: Request, exc: GeminiServiceUnavailableException):
    """
    Global handler for Gemini service unavailable exceptions.
    Indicates the Gemini API is temporarily down or unreachable.
    """
    logging.error(
        f"Gemini service unavailable for {request.client.host if request.client else 'unknown'}: "
        f"{exc.message} (status: {exc.service_status})"
    )
    
    response = JSONResponse(
        status_code=503,
        content=exc.to_dict(),
    )
    
    # Add retry-after header
    if exc.retry_after:
        response.headers["Retry-After"] = str(exc.retry_after)
    else:
        response.headers["Retry-After"] = "120"  # Default to 2 minutes
        
    return response


# Global exception handler for sanitizing error messages
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches any unhandled exceptions and returns a generic 500 error response.
    This prevents sensitive application details from leaking in production.
    """
    # Log the full error for internal debugging
    logging.error(f"Unhandled exception for request {request.url}: {exc}", exc_info=True)
    
    # Return a generic, sanitized error response to the client
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected internal server error occurred. Please try again later."
        },
    )


class AgentQueryRequest(BaseModel):
    query: str
    log_content: str | None = None

class AgentResponse(BaseModel):
    # Define what a typical response should look like
    # For now, returning the full final state for inspection
    final_state: dict

@app.get("/", tags=["General"])
async def read_root():
    """Root endpoint, returns a welcome message."""
    return {"message": "Welcome to MB-Sparrow Agent API"}

@app.get("/health", tags=["General"])
async def health_check():
    """Health check endpoint for monitoring and connectivity testing."""
    try:
        # Basic health check - can be expanded with database checks, etc.
        return {
            "status": "healthy",
            "service": "mb-sparrow-agent-server",
            "version": "1.0"
        }
    except Exception as e:
        logging.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "mb-sparrow-agent-server",
                "error": "Service unavailable"
            }
        )


@app.get("/health/global-knowledge", tags=["General"])
async def global_knowledge_health_check():
    """Health probe reporting global knowledge feature readiness."""
    flags = {
        "enable_global_knowledge_injection": bool(settings.enable_global_knowledge_injection),
        "enable_store_adapter": bool(settings.enable_store_adapter),
        "enable_store_writes": bool(settings.enable_store_writes),
        "retrieval_primary": settings.get_retrieval_primary(),
    }
    try:
        store_configured = settings.has_global_store_configuration()
        default_state = (
            not flags["enable_global_knowledge_injection"]
            and not flags["enable_store_adapter"]
            and not flags["enable_store_writes"]
            and flags["retrieval_primary"] == "rpc"
        )
        store_required = settings.should_use_store_adapter() or settings.should_enable_store_writes()

        if default_state:
            ready = True
        elif store_required:
            ready = store_configured
        else:
            ready = True
        status = "ready" if ready else "degraded"

        return {
            "status": status,
            "flags": flags,
            "store_configured": store_configured,
            "embedding_expected_dim": EXPECTED_DIM,
        }
    except Exception as exc:  # pragma: no cover - defensive safeguard
        logging.error("Global knowledge health probe failed: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "flags": flags,
                "store_configured": settings.has_global_store_configuration(),
                "embedding_expected_dim": EXPECTED_DIM,
                "error": "probe_failed",
            },
        )


# Rate limiting test endpoint removed - functionality verified
# The global exception handlers are working properly for all rate-limited endpoints

@app.get("/security-status", tags=["General"])
async def security_status():
    """
    Security configuration status endpoint for debugging and validation.
    Shows current security feature states.
    """
    # Get list of all registered routes
    routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            routes.append({
                "path": route.path,
                "methods": list(route.methods) if route.methods else []
            })
    
    return {
        "production_mode": settings.is_production_mode(),
        "authentication_endpoints": {
            "should_enable": settings.should_enable_auth_endpoints(),
            "actually_enabled": auth_endpoints is not None,
            "config_value": settings.enable_auth_endpoints
        },
        "api_key_endpoints": {
            "should_enable": settings.should_enable_api_key_endpoints(),
            "actually_enabled": api_key_endpoints is not None,
            "config_value": settings.enable_api_key_endpoints
        },
        "auth_configuration": {
            "skip_auth": settings.skip_auth,
            "development_user_id": settings.development_user_id,
            "force_production_security": settings.force_production_security
        },
        "environment_indicators": {
            "supabase_configured": bool(settings.supabase_url),
            "internal_api_token_configured": bool(settings.internal_api_token),
            "encryption_secret_configured": bool(getattr(settings, 'api_key_encryption_secret', None))
        },
        "registered_routes": routes,
        "api_key_routes_registered": any("/api-keys" in r["path"] for r in routes),
        "rate_limit_routes_registered": any("/rate-limits" in r["path"] for r in routes)
    }

@app.post("/agent", response_model=AgentResponse, tags=["Agent"])
async def agent_invoke_endpoint(request: AgentQueryRequest):
    """
    Main endpoint to interact with the MB-Sparrow agent.
    It takes a user query and returns the agent's response.
    """
    if not request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Initial state for the graph
    # The graph expects messages in a specific format, often List[BaseMessage]
    # For simplicity, we'll wrap the query. Adjust if your graph expects richer messages.
    initial_input = {
        "messages": [HumanMessage(content=request.query)],
        "raw_log_content": request.log_content
    }

    try:
        # Invoke the LangGraph agent
        # Note: stream() or astream() would be used for streaming responses.
        # For a single response after full execution, invoke() or ainvoke() is used.
        # Wrap the agent graph invocation in a span
        with tracer.start_as_current_span("agent_graph_invocation") as span:
            try:
                qh = hashlib.sha256(request.query.encode("utf-8")).hexdigest()
                span.set_attribute("input.query_hash", qh)
                span.set_attribute("input.query_present", True)
            except Exception:
                span.set_attribute("input.query_present", bool(request.query))
            if request.log_content:
                span.set_attribute("input.log_content_length", len(request.log_content))
            
            final_state = await agent_graph.ainvoke(initial_input)
            
            # You could add attributes from final_state to the span if useful
            # For example, if final_state contains a 'destination'
            if isinstance(final_state, dict) and final_state.get('destination'):
                span.set_attribute("output.destination", str(final_state['destination']))
            
        return {"final_state": final_state}
    except Exception as e:
        # Log the exception details for debugging
        print(f"Error invoking agent graph: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing agent request: {str(e)}")

# To run this app (from the project root directory):
# uvicorn app.main:app --reload
