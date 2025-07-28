import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, List
import os
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

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

from app.agents_v2.orchestration.graph import app as agent_graph
from app.agents_v2.orchestration.state import GraphState # Corrected import location
from app.api.v1.endpoints import search_tools_endpoints # Added for search tools endpoints
from app.api.v1.endpoints import agent_endpoints  # Agent interaction endpoints
from app.api.v1.endpoints import feedme_endpoints  # FeedMe transcript ingestion
from app.api.v1.endpoints import chat_session_endpoints  # Chat session persistence
from app.api.v1.endpoints import rate_limit_endpoints  # Rate limiting monitoring
from app.api.v1.websocket import feedme_websocket  # FeedMe WebSocket endpoints
from app.core.settings import settings

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

# Add SlowAPI middleware for rate limiting
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Conditionally include authentication router
if auth_endpoints and settings.should_enable_auth_endpoints():
    app.include_router(auth_endpoints.router, prefix="/api/v1/auth", tags=["Authentication"])
    logging.info("Authentication router registered")
else:
    logging.warning("Authentication router not registered - endpoints disabled or import failed")

# Always include core application routers
app.include_router(search_tools_endpoints.router, prefix="/api/v1/tools", tags=["Search Tools"])
app.include_router(agent_endpoints.router, prefix="/api/v1", tags=["Agent Interaction"])
# Register FeedMe routes
app.include_router(feedme_endpoints.router, prefix="/api/v1/feedme", tags=["FeedMe"])
# Register Chat Session routes
app.include_router(chat_session_endpoints.router, prefix="/api/v1", tags=["Chat Sessions"])
# Register Rate Limiting routes
app.include_router(rate_limit_endpoints.router, prefix="/api/v1", tags=["Rate Limiting"])

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
    
    logging.info("=== MB-Sparrow Security Configuration ===")
    logging.info(f"Production Mode: {is_production}")
    logging.info(f"Authentication Endpoints: {'ENABLED' if auth_enabled else 'DISABLED'}")
    logging.info(f"API Key Endpoints: {'ENABLED' if api_key_enabled else 'DISABLED'}")
    logging.info(f"Skip Auth: {settings.skip_auth}")
    
    if not is_production:
        logging.warning("Running in development mode - some security features may be disabled")
    
    if not auth_enabled or not api_key_enabled:
        logging.warning("Some security endpoints are disabled - ensure this is intentional")
    
    logging.info("==========================================")

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
    session_id: int | None = None  # Optional session ID for memory retention

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


# Rate limiting test endpoint removed - functionality verified
# The global exception handlers are working properly for all rate-limited endpoints

@app.get("/security-status", tags=["General"])
async def security_status():
    """
    Security configuration status endpoint for debugging and validation.
    Shows current security feature states.
    """
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
            "internal_api_token_configured": bool(settings.internal_api_token)
        }
    }

@app.post("/agent", response_model=AgentResponse, tags=["Agent"])
async def agent_invoke_endpoint(request: AgentQueryRequest):
    """
    Main endpoint to interact with the MB-Sparrow agent.
    It takes a user query and returns the agent's response.
    Integrates session history for memory retention.
    """
    if not request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    # Load session history if session_id is provided
    messages = []
    
    # Use direct attribute access with validation
    if request.session_id:
        # Validate session_id is a positive integer
        if not isinstance(request.session_id, int) or request.session_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid session_id")
        
        try:
            # Import the chat session client
            from app.db.supabase_client import get_supabase_client
            client = get_supabase_client()
            
            # Get messages for this session ordered by creation time
            messages_response = client.client.table('chat_messages')\
                .select('*')\
                .eq('session_id', request.session_id)\
                .order('created_at', asc=True)\
                .execute()
            
            if messages_response.data:
                # Convert to LangChain message format with error handling
                for msg in messages_response.data:
                    try:
                        if msg.get('message_type') == 'user':
                            messages.append(HumanMessage(content=msg.get('content', '')))
                        elif msg.get('message_type') == 'assistant':
                            messages.append(AIMessage(content=msg.get('content', '')))
                    except Exception as msg_error:
                        logging.warning(f"Failed to convert message {msg.get('id')}: {msg_error}")
                        continue
            
            logging.info(f"Loaded {len(messages)} historical messages for session {request.session_id}")
        except HTTPException:
            raise
        except Exception as e:
            logging.warning(f"Failed to load session history: {e}")
            # Continue without history rather than failing the request
    
    # Add current query to messages
    messages.append(HumanMessage(content=request.query))

    # Initial state for the graph with history
    initial_input = {
        "messages": messages,
        "raw_log_content": request.log_content,
        "session_id": request.session_id  # Direct attribute access
    }

    try:
        # Create the configuration for the checkpointer
        # Use session_id as thread_id for memory persistence, fallback to a default if not provided
        thread_id = str(request.session_id) if request.session_id else "default_session"
        config = RunnableConfig(configurable={"thread_id": thread_id})
        
        # Invoke the LangGraph agent
        # Note: stream() or astream() would be used for streaming responses.
        # For a single response after full execution, invoke() or ainvoke() is used.
        # Wrap the agent graph invocation in a span
        with tracer.start_as_current_span("agent_graph_invocation") as span:
            span.set_attribute("input.query", request.query)
            span.set_attribute("input.thread_id", thread_id)
            if request.log_content:
                span.set_attribute("input.log_content_length", len(request.log_content))
            
            final_state = await agent_graph.ainvoke(initial_input, config=config)
            
            # You could add attributes from final_state to the span if useful
            # For example, if final_state contains a 'destination'
            if isinstance(final_state, dict) and final_state.get('destination'):
                span.set_attribute("output.destination", str(final_state['destination']))
            
        return {"final_state": final_state}
    except Exception as e:
        # Log the exception details for debugging
        logging.error(f"Error invoking agent graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing agent request: {str(e)}")

# To run this app (from the project root directory):
# uvicorn app.main:app --reload