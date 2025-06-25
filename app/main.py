from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, List
import os
from langchain_core.messages import HumanMessage

from app.agents_v2.orchestration.graph import app as agent_graph
from app.agents_v2.orchestration.state import GraphState # Corrected import location
from app.api.v1.endpoints import auth as auth_endpoints # Added for JWT auth
from app.api.v1.endpoints import search_tools_endpoints # Added for search tools endpoints
from app.api.v1.endpoints import agent_endpoints  # Agent interaction endpoints
from app.api.v1.endpoints import feedme_endpoints  # FeedMe transcript ingestion

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

# FastAPI instance
app = FastAPI(
    title="MB-Sparrow Agent Server",
    version="1.0",
    description="API server for the MB-Sparrow multi-agent system."
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Include the authentication router
app.include_router(auth_endpoints.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(search_tools_endpoints.router, prefix="/api/v1/tools", tags=["Search Tools"])
app.include_router(agent_endpoints.router, prefix="/api/v1", tags=["Agent Interaction"])
# Register FeedMe routes
app.include_router(feedme_endpoints.router, prefix="/api/v1/feedme", tags=["FeedMe"])


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
            span.set_attribute("input.query", request.query)
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