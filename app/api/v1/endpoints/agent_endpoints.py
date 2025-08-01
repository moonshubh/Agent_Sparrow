from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import AsyncIterable, List, Annotated, Optional, Dict, Any
from datetime import datetime
import asyncio
import logging

from app.agents_v2.primary_agent.agent import run_primary_agent
from app.agents_v2.primary_agent.schemas import PrimaryAgentState # Import PrimaryAgentState
from app.agents_v2.primary_agent.reasoning.unified_deep_reasoning_engine import (
    UnifiedDeepReasoningEngine, UnifiedReasoningConfig, UnifiedReasoningOutput
)
from app.agents_v2.primary_agent.reasoning.safety_redactor import redact_reasoning_ui
from app.agents_v2.primary_agent.llm_registry import SupportedModel, validate_model_id, DEFAULT_MODEL
from app.agents_v2.log_analysis_agent.schemas import LogAnalysisAgentState, StructuredLogAnalysisOutput
from app.agents_v2.log_analysis_agent.enhanced_schemas import ComprehensiveLogAnalysisOutput
from app.core.rate_limiting.budget_manager import BudgetManager
from langchain_core.messages import HumanMessage
import json
import re

from app.agents_v2.log_analysis_agent.agent import run_log_analysis_agent
from app.agents_v2.research_agent.research_agent import get_research_graph, ResearchState
from app.agents_v2.orchestration.graph import app as agent_graph
from app.agents_v2.orchestration.state import GraphState
# Conditional import for authentication
try:
    from app.api.v1.endpoints.auth import get_current_user_id
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    # Fallback function when auth is not available
    async def get_current_user_id() -> str:
        from app.core.settings import settings
        return getattr(settings, 'development_user_id', 'dev-user-12345')
from app.core.user_context import user_context_scope, create_user_context_from_user_id

router = APIRouter()

# Initialize logger
logger = logging.getLogger(__name__)

# Configuration constants for streaming behavior
STREAMING_BATCH_SIZE = 3  # Number of words per batch in simulated streaming
STREAMING_DELAY = 0.05    # Delay between batches in seconds
DEBUG_VERBOSE = False     # Enable verbose debug messages (set to True for debugging)

# --- Helper Functions ---

def safe_json_serializer(obj):
    """
    Custom JSON serializer that handles complex objects like datetime, Pydantic models, etc.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, 'model_dump'):
        # Handle Pydantic v2 models
        return obj.model_dump()
    elif hasattr(obj, 'dict'):
        # Handle Pydantic v1 models
        return obj.dict()
    elif isinstance(obj, (list, tuple)):
        return [safe_json_serializer(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: safe_json_serializer(value) for key, value in obj.items()}
    else:
        # For other objects, try to convert to string as fallback
        try:
            # Check if it's already JSON serializable
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

def serialize_analysis_results(final_report):
    """
    Safely serialize analysis results for JSON streaming response.
    """
    try:
        if hasattr(final_report, 'model_dump'):
            # Pydantic v2 model
            serialized = final_report.model_dump()
        elif hasattr(final_report, 'dict'):
            # Pydantic v1 model
            serialized = final_report.dict()
        elif isinstance(final_report, dict):
            # Already a dictionary
            serialized = final_report
        else:
            # Fallback for other object types
            serialized = {"summary": str(final_report)}
        
        # Recursively serialize any complex nested objects
        return safe_json_serializer(serialized)
    except Exception as e:
        print(f"Error serializing analysis results: {e}")
        # Return minimal fallback
        return {
            "overall_summary": "Analysis completed but serialization failed",
            "error": str(e),
            "system_metadata": {},
            "identified_issues": [],
            "proposed_solutions": []
        }

# --- Pydantic Models for Log Analysis Agent ---

class LogAnalysisV2Response(ComprehensiveLogAnalysisOutput):
    trace_id: str | None = None
class Issue(BaseModel):
    id: str
    description: str
    severity: str # Consider using Literal["low", "medium", "high", "critical"]
    recommendation: str | None = None
    line_numbers: tuple[int, int] | None = None
    error_type: str | None = None

class LogAnalysisRequest(BaseModel):
    """Accepts raw log content from the frontend.
    For backward-compatibility we allow both the legacy `log_text` key and the newer
    `content` key used by the v2 UI. Exactly one of them must be provided.
    """
    log_text: str | None = None
    content: str | None = None  # Preferred new field name
    trace_id: str | None = None




# --- Pydantic Models for Research Agent ---
class ResearchItem(BaseModel):
    id: str
    url: str
    title: str
    snippet: str | None = None
    source_name: str | None = None # e.g., "Web Search", "Internal KB"
    score: float | None = None # Relevance score

class ResearchRequest(BaseModel):
    query: str
    top_k: int | None = None
    trace_id: str | None = None

class ResearchResponse(BaseModel):
    results: List[ResearchItem]
    trace_id: str | None = None


class ChatRequest(BaseModel):
    message: str
    model: str | None = None  # Optional model selection for primary agent
    # trace_id: str | None = None # Optional, if you plan to propagate trace IDs

async def primary_agent_stream_generator(query: str, user_id: str, model: str | None = None) -> AsyncIterable[str]:
    """Wraps the primary agent's streaming output with user-specific API configuration."""
    try:
        # Create user context
        user_context = await create_user_context_from_user_id(user_id)
        
        # Check if user has required API keys based on selected model
        from app.agents_v2.primary_agent.llm_registry import SupportedModel, validate_model_id, DEFAULT_MODEL
        
        # Determine which model is being used
        try:
            selected_model = validate_model_id(model) if model else DEFAULT_MODEL
        except ValueError:
            selected_model = DEFAULT_MODEL
        
        # Check appropriate API key based on model
        if selected_model == SupportedModel.KIMI_K2:
            # For Kimi K2, check for OpenRouter key (or use Gemini key as fallback)
            import os
            openrouter_key = os.getenv("OPENROUTER_API_KEY")
            gemini_key = await user_context.get_gemini_api_key()
            
            if not openrouter_key and not gemini_key:
                error_payload = json.dumps({
                    "role": "error", 
                    "content": "🔑 **API Key Required**: To use Kimi K2, please configure an API key.\n\n**Options:**\n1. Set OPENROUTER_API_KEY environment variable\n2. Or add your Google Gemini API key in Settings (will be used for OpenRouter)\n\n**Get API keys:**\n- OpenRouter: https://openrouter.ai/keys\n- Google Gemini: https://makersuite.google.com/app/apikey"
                }, ensure_ascii=False)
                yield f"data: {error_payload}\n\n"
                return
        else:
            # For Gemini models, check Gemini key
            gemini_key = await user_context.get_gemini_api_key()
            if not gemini_key:
                error_payload = json.dumps({
                    "role": "error", 
                    "content": "🔑 **API Key Required**: To use the AI assistant, please add your Google Gemini API key in Settings.\n\n**How to configure:**\n1. Click the ⚙️ Settings button in the top-right corner\n2. Navigate to the 'API Keys' section\n3. Add your Google Gemini API key (starts with 'AIza')\n4. Get your free API key at: https://makersuite.google.com/app/apikey"
                }, ensure_ascii=False)
                yield f"data: {error_payload}\n\n"
                return
        
        # Use user-specific context
        async with user_context_scope(user_context):
            initial_state = PrimaryAgentState(
                messages=[HumanMessage(content=query)],
                model=model  # Pass the selected model to the agent
            )
            
            # Call the primary agent (returns a dict, not async generator)
            result = await run_primary_agent(initial_state)
            
            # Extract messages from result
            if result and 'messages' in result:
                for message in result['messages']:
                    if hasattr(message, 'content') and message.content:
                        # Stream the message content word by word for natural feel
                        words = message.content.split()
                        for i in range(0, len(words), STREAMING_BATCH_SIZE):
                            batch = words[i:i+STREAMING_BATCH_SIZE]
                            json_payload = json.dumps({
                                "role": "assistant", 
                                "content": " ".join(batch) + " "
                            }, ensure_ascii=False)
                            yield f"data: {json_payload}\n\n"
                            await asyncio.sleep(STREAMING_DELAY)  # Configurable delay for streaming effect
                    
    except Exception as e:
        # Use logger for consistency if available, otherwise print
        # logger.error(f"Error in primary_agent_stream_generator calling run_primary_agent: {e}", exc_info=True)
        print(f"Error in primary_agent_stream_generator calling run_primary_agent: {e}")
        error_payload = json.dumps({"role": "error", "content": f"An error occurred in the agent: {str(e)}"}, ensure_ascii=False)
        yield f"data: {error_payload}\n\n"

# Legacy v1 endpoint - DEPRECATED but maintained for backward compatibility
@router.post("/agent/chat/stream")
async def chat_stream_v1_legacy(
    request: ChatRequest
):
    """
    DEPRECATED: Legacy streaming chat endpoint without authentication.
    
    This endpoint is maintained for backward compatibility but is deprecated.
    New applications should use /v2/agent/chat/stream with proper authentication.
    
    Deprecation Notice:
    - This endpoint will be removed in v3.0
    - Please migrate to the authenticated v2 endpoint
    - See migration guide: /docs/api-migration
    """
    if not request.message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    # Use default configuration for unauthenticated requests
    return StreamingResponse(
        primary_agent_stream_generator(request.message, user_id="anonymous", model=request.model),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-API-Version": "1.0",
            "X-Deprecation-Warning": "This endpoint is deprecated. Use /v2/agent/chat/stream"
        }
    )

# v2 endpoint with authentication - RECOMMENDED
@router.post("/v2/agent/chat/stream")
async def chat_stream_v2_authenticated(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Authenticated streaming chat endpoint with the Primary Support Agent.
    
    This endpoint requires Supabase authentication and provides:
    - User-specific API key configuration
    - Personalized agent behavior
    - Enhanced security and rate limiting
    - Access to premium features
    """
    if not request.message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    return StreamingResponse(
        primary_agent_stream_generator(request.message, user_id, request.model),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-API-Version": "2.0"
        }
    )

# --- Log Analysis Agent Endpoint ---
@router.post("/agent/logs", response_model=LogAnalysisV2Response)
async def analyze_logs(
    request: LogAnalysisRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Endpoint for analyzing logs with the Log Analysis Agent."""
    # Determine which field contains the log content (new `content` or legacy `log_text`)
    log_body = request.content or request.log_text
    if not log_body:
        raise HTTPException(status_code=400, detail="Log text cannot be empty")

    try:
        # Create user context
        user_context = await create_user_context_from_user_id(user_id)
        
        # Check if user has required API keys
        gemini_key = await user_context.get_gemini_api_key()
        if not gemini_key:
            raise HTTPException(
                status_code=400, 
                detail="API Key Required: To use log analysis, please add your Google Gemini API key in Settings. Steps: (1) Click Settings ⚙️ in the top-right (2) Go to 'API Keys' section (3) Add your Gemini API key (starts with 'AIza') (4) Get a free key at: https://makersuite.google.com/app/apikey"
            )
        
        # Use user-specific context
        async with user_context_scope(user_context):
            initial_state = LogAnalysisAgentState(
                messages=[HumanMessage(content=log_body)],
                raw_log_content=log_body,
                # trace_id is handled within run_log_analysis_agent if passed as kwarg, but not part of state dict
            )

            # Pass trace_id as a keyword argument if the agent function supports it for logging/tracing
            # The run_log_analysis_agent in agent.py is designed to pick up trace_id from the state dict if present,
            # or generate one. For explicit passing for the endpoint, let's ensure it's part of the initial call.
            # However, the agent.py run_log_analysis_agent expects trace_id in the state dictionary.
            if request.trace_id:
                initial_state['trace_id'] = request.trace_id

            raw_agent_output = await run_log_analysis_agent(initial_state)

        final_report: ComprehensiveLogAnalysisOutput = raw_agent_output.get('final_report')
        returned_trace_id = raw_agent_output.get('trace_id')

        if not final_report:
            raise HTTPException(status_code=500, detail="Log analysis agent did not return a final report.")

        # Return the structured report directly along with the trace_id
        # Use safe serialization for consistent handling
        response_dict = serialize_analysis_results(final_report)
        response_dict["trace_id"] = returned_trace_id or request.trace_id
        
        try:
            return LogAnalysisV2Response(**response_dict)
        except Exception as validation_error:
            print(f"LogAnalysisV2Response validation error: {validation_error}")
            # Create a minimal response that will validate
            fallback_response = {
                "overall_summary": response_dict.get("overall_summary", "Analysis completed"),
                "health_status": response_dict.get("health_status", "Unknown"),
                "priority_concerns": response_dict.get("priority_concerns", []),
                "system_metadata": response_dict.get("system_metadata", {}),
                "environmental_context": response_dict.get("environmental_context", {}),
                "identified_issues": response_dict.get("identified_issues", []),
                "issue_summary_by_severity": response_dict.get("issue_summary_by_severity", {}),
                "correlation_analysis": response_dict.get("correlation_analysis", {}),
                "dependency_analysis": response_dict.get("dependency_analysis", {}),
                "predictive_insights": response_dict.get("predictive_insights", []),
                "ml_pattern_discovery": response_dict.get("ml_pattern_discovery", {}),
                "proposed_solutions": response_dict.get("proposed_solutions", []),
                "supplemental_research": response_dict.get("supplemental_research"),
                "analysis_metrics": response_dict.get("analysis_metrics", {}),
                "validation_summary": response_dict.get("validation_summary", {}),
                "immediate_actions": response_dict.get("immediate_actions", []),
                "preventive_measures": response_dict.get("preventive_measures", []),
                "monitoring_recommendations": response_dict.get("monitoring_recommendations", []),
                "automated_remediation_available": response_dict.get("automated_remediation_available", False),
                "trace_id": returned_trace_id or request.trace_id
            }
            return LogAnalysisV2Response(**fallback_response)
    except Exception as e:
        # Log the exception details for debugging
        print(f"Error in Log Analysis Agent endpoint: {e}")
        # Consider how to propagate trace_id in error responses if needed
        raise HTTPException(status_code=500, detail=f"Error processing log analysis request: {str(e)}")

# --- Research Agent Endpoint ---
@router.post("/agent/research", response_model=ResearchResponse)
async def research_query(
    request: ResearchRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Endpoint for performing research with the Research Agent."""
    if not request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        # Create user context
        user_context = await create_user_context_from_user_id(user_id)
        
        # Check if user has API key for research (Tavily is needed for research)
        tavily_key = await user_context.get_tavily_api_key()
        if not tavily_key:
            raise HTTPException(
                status_code=400, 
                detail="Please configure your Tavily API key in Settings to use web research functionality."
            )
        
        # Use user-specific context
        async with user_context_scope(user_context):
            research_graph = get_research_graph()
            initial_graph_state: ResearchState = {
                "query": request.query,
                "urls": [],
                "documents": [],
                "answer": None,
                "citations": None,
                # top_k is not directly used by the graph state but influences search_node's max_results implicitly
                # The Tavily search tool used by search_node has a max_results parameter.
                # If request.top_k is intended to control this, it needs to be passed to search_node or the tool config.
                # For now, the graph uses a default of 5 in search_node.
            }

            # LangGraph's invoke is synchronous, ainvoke for async
            # Assuming the graph nodes (search, scrape, synthesize) are async, we should use ainvoke.
            # However, the current research_agent.py uses synchronous .invoke() in its CLI test.
            # For an async FastAPI endpoint, we should ideally use graph.ainvoke if graph nodes support it.
            # If nodes are synchronous, graph.invoke() would block. Let's assume ainvoke is preferred.
            # For simplicity and matching the agent's own test harness, let's use invoke for now,
            # but acknowledge this might need to change to ainvoke and run in a threadpool for a truly async endpoint.
            # For now, we will call it directly. If it blocks, it needs to be run in a threadpool.
            # result_state = await asyncio.to_thread(research_graph.invoke, initial_graph_state)
            # The research_graph nodes (search_node, scrape_node, synthesize_node) are synchronous.
            # To avoid blocking the event loop, we should run the graph.invoke in a thread pool.
            # However, for now, let's make a direct call and note this as a point for future improvement.

            import asyncio # Make sure to import asyncio if not already
            # To run synchronous graph.invoke in an async endpoint without blocking:
            loop = asyncio.get_event_loop()
            result_state = await loop.run_in_executor(None, research_graph.invoke, initial_graph_state)

        answer = result_state.get("answer", "No answer provided.")
        citations = result_state.get("citations", [])

        transformed_results: List[ResearchItem] = []
        if citations:
            for citation in citations:
                # The citation format from research_agent is {'id': int, 'url': str}
                # The ResearchItem for the frontend expects more fields.
                transformed_results.append(
                    ResearchItem(
                        id=str(citation.get('id', '')),
                        url=citation.get('url', '#'),
                        title=f"Source [{citation.get('id', '')}]: {citation.get('url', 'N/A')}", # Placeholder title
                        snippet=answer, # Using the main answer as a snippet for all cited sources for now
                        source_name="Web Research",
                        score=None # Score is not provided by the current research agent
                    )
                )
        
        # If there's an answer but no citations, we can create a single result item for the answer itself.
        if not transformed_results and answer != "No answer provided." and answer != "I'm sorry, I couldn't find relevant information to answer your question.":
            transformed_results.append(
                 ResearchItem(
                    id="answer_summary",
                    url="#", # No specific URL for the summary itself
                    title="Synthesized Answer",
                    snippet=answer,
                    source_name="Synthesized by Agent",
                    score=None
                )
            )

        response_data = {
            "results": [item.model_dump() for item in transformed_results],
            "trace_id": request.trace_id # Propagate trace_id from request for now
        }
        return ResearchResponse(**response_data)
    except Exception as e:
        print(f"Error in Research Agent endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing research request: {str(e)}")

# --- Unified Agent Endpoint with LangGraph Orchestration ---
class UnifiedAgentRequest(BaseModel):
    message: str
    agent_type: str | None = None  # Optional: "primary", "log_analyst", "researcher", or None for auto-routing
    log_content: str | None = None  # For log analysis
    trace_id: str | None = None

async def unified_agent_stream_generator(request: UnifiedAgentRequest) -> AsyncIterable[str]:
    """Unified agent endpoint with intelligent routing and fallback."""
    try:
        # Send routing notification
        routing_payload = json.dumps({
            "role": "system", 
            "content": f"🤖 Analyzing your request...",
            "agent_type": "router",
            "trace_id": request.trace_id
        }, ensure_ascii=False)
        yield f"data: {routing_payload}\n\n"
        
        # Simple intelligent routing based on message content
        message_lower = request.message.lower()
        
        # Determine agent type
        if request.agent_type:
            agent_type = request.agent_type
        elif any(keyword in message_lower for keyword in ['analyze this log', 'parse log file', 'debug this log', 'log analysis', 'examine log entries', 'review log output', 'check log errors']):
            agent_type = "log_analyst"
        elif any(keyword in message_lower for keyword in ['research', 'find information about', 'latest news', 'compare products', 'what is new in', 'investigate', 'gather sources', 'comprehensive overview', 'detailed research']):
            agent_type = "researcher"  
        else:
            agent_type = "primary_agent"
        
        # Send agent selection notification
        agent_name = {
            "primary_agent": "Primary Support",
            "log_analyst": "Log Analysis", 
            "researcher": "Research"
        }.get(agent_type, "Primary Support")
        
        agent_payload = json.dumps({
            "role": "system", 
            "content": f"🎯 Routing to {agent_name} Agent",
            "agent_type": agent_type,
            "trace_id": request.trace_id
        }, ensure_ascii=False)
        yield f"data: {agent_payload}\n\n"
        
        # Route to appropriate agent endpoint
        if agent_type == "log_analyst" and request.log_content:
            # Handle log analysis
            from app.agents_v2.log_analysis_agent.agent import run_log_analysis_agent
            from app.agents_v2.log_analysis_agent.schemas import LogAnalysisAgentState
            
            initial_state = LogAnalysisAgentState(
                messages=[HumanMessage(content=request.message)],
                raw_log_content=request.log_content
            )
            
            result = await run_log_analysis_agent(initial_state)
            final_report = result.get('final_report')
            
            if final_report:
                # Handle both Pydantic models and dictionaries for overall_summary
                if hasattr(final_report, 'overall_summary'):
                    summary = final_report.overall_summary
                elif isinstance(final_report, dict):
                    summary = final_report.get('overall_summary', 'Analysis complete')
                else:
                    summary = str(final_report)
                
                content = f"Log analysis complete! {summary}"
                
                # Use safe serialization for analysis_results
                analysis_results = serialize_analysis_results(final_report)
                
                # Additional debug logging
                print(f"Serialized analysis results keys: {list(analysis_results.keys()) if isinstance(analysis_results, dict) else 'not a dict'}")
                
                try:
                    json_payload = json.dumps({
                        "role": "assistant", 
                        "content": content,
                        "agent_type": agent_type,
                        "trace_id": request.trace_id,
                        "analysis_results": analysis_results
                    }, ensure_ascii=False)
                    yield f"data: {json_payload}\n\n"
                except Exception as json_error:
                    print(f"JSON serialization error: {json_error}")
                    # Send a fallback response
                    fallback_payload = json.dumps({
                        "role": "assistant", 
                        "content": f"Log analysis complete! {summary}",
                        "agent_type": agent_type,
                        "trace_id": request.trace_id,
                        "analysis_results": {
                            "overall_summary": summary,
                            "error": f"Serialization failed: {str(json_error)}",
                            "system_metadata": {},
                            "identified_issues": [],
                            "proposed_solutions": []
                        }
                    }, ensure_ascii=False)
                    yield f"data: {fallback_payload}\n\n"
            
        elif agent_type == "researcher":
            # Handle research queries
            from app.agents_v2.research_agent.research_agent import get_research_graph
            
            research_graph = get_research_graph()
            initial_state = {
                "query": request.message,
                "urls": [],
                "documents": [],
                "answer": None,
                "citations": None,
            }
            
            import asyncio
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, research_graph.invoke, initial_state)
            
            answer = result.get("answer", "No answer provided.")
            citations = result.get("citations", [])
            
            json_payload = json.dumps({
                "role": "assistant", 
                "content": answer,
                "agent_type": agent_type,
                "trace_id": request.trace_id,
                "citations": citations
            }, ensure_ascii=False)
            yield f"data: {json_payload}\n\n"
            
        else:
            # Handle primary agent queries
            from app.agents_v2.primary_agent.agent import run_primary_agent
            from app.agents_v2.primary_agent.schemas import PrimaryAgentState
            
            initial_state = PrimaryAgentState(
                messages=[HumanMessage(content=request.message)]
            )
            
            # Stream the primary agent's response
            routing_message = f"🎯 Routing to {agent_type.replace('_', ' ').title()}"
            yield f'data: {json.dumps({"role": "system", "content": routing_message, "agent_type": agent_type, "trace_id": request.trace_id})}\n\n'
            
            # Stream each chunk after cleaning
            async for chunk in run_primary_agent(initial_state):
                if hasattr(chunk, 'content') and chunk.content is not None:
                    # Clean self-critique blocks from each chunk
                    cleaned_content = re.sub(r'<self_critique>.*?</self_critique>', '', chunk.content, flags=re.DOTALL)
                    
                    if cleaned_content.strip():  # Only send non-empty content
                        role = getattr(chunk, 'role', 'assistant') or 'assistant'
                        json_payload = json.dumps({
                            "role": role,
                            "content": cleaned_content,
                            "agent_type": agent_type,
                            "trace_id": request.trace_id
                        }, ensure_ascii=False)
                        yield f"data: {json_payload}\n\n"
                
        # Send completion signal
        yield f"data: {json.dumps({'role': 'system', 'content': '[DONE]'})}\n\n"
        
    except Exception as e:
        print(f"Error in unified_agent_stream_generator: {e}")
        import traceback
        traceback.print_exc()
        error_payload = json.dumps({
            "role": "error", 
            "content": f"An error occurred: {str(e)}",
            "trace_id": request.trace_id
        }, ensure_ascii=False)
        yield f"data: {error_payload}\n\n"


@router.post("/agent/stream")
async def agent_stream_with_reasoning(
    request: ChatRequest,
    user_id: Annotated[str, Depends(get_current_user_id)]
):
    """
    Stream agent responses with deep reasoning UI metadata.
    
    This endpoint implements Server-Sent Events (SSE) streaming with:
    - Token-by-token streaming for real-time response
    - Final event with reasoning_ui metadata
    - Budget-aware model selection
    - Safety redaction of reasoning content
    """
    async def stream_generator() -> AsyncIterable[str]:
        try:
            # Send debug message (only if debug mode enabled)
            if DEBUG_VERBOSE:
                debug_msg = json.dumps({
                    "event": "debug",
                    "data": {"message": "Starting stream generator"}
                })
                yield f"data: {debug_msg}\n\n"
            
            # Initialize budget manager
            budget_manager = BudgetManager()
            await budget_manager.initialize()
            
            if DEBUG_VERBOSE:
                debug_msg = json.dumps({
                    "event": "debug", 
                    "data": {"message": "Budget manager initialized"}
                })
                yield f"data: {debug_msg}\n\n"
            
            # Validate and select model
            requested_model = validate_model_id(request.model) if request.model else DEFAULT_MODEL
            
            if DEBUG_VERBOSE:
                debug_msg = json.dumps({
                    "event": "debug",
                    "data": {"message": f"Requested model: {requested_model.value}"}
                })
                yield f"data: {debug_msg}\n\n"
            
            # Check budget and potentially downgrade
            allowed_model_str = await budget_manager.pick_allowed(requested_model.value)
            
            if DEBUG_VERBOSE:
                debug_msg = json.dumps({
                    "event": "debug",
                    "data": {"message": f"Budget manager returned: {allowed_model_str}"}
                })
                yield f"data: {debug_msg}\n\n"
            
            # Map budget manager model names back to SupportedModel enum values
            MODEL_NAME_MAPPING = {
                "gemini-2.5-flash": SupportedModel.GEMINI_FLASH,
                "gemini-2.5-pro": SupportedModel.GEMINI_PRO,
                "kimi-k2": SupportedModel.KIMI_K2
            }
            
            effective_model = MODEL_NAME_MAPPING.get(allowed_model_str, requested_model)
            
            # Get user API key
            user_context = await create_user_context_from_user_id(user_id)
            if "gemini" in effective_model.value:
                api_key = await user_context.get_gemini_api_key()
            else:
                api_key = await user_context.get_openrouter_api_key()
            
            if not api_key:
                error_msg = json.dumps({
                    "event": "error",
                    "data": {
                        "error": f"No API key configured for {effective_model.value}"
                    }
                })
                yield f"data: {error_msg}\n\n"
                return
            
            # Initialize reasoning engine
            reasoning_config = UnifiedReasoningConfig(
                enable_caching=True,
                enable_polish_pass=True,
                polish_threshold=0.75
            )
            reasoning_engine = UnifiedDeepReasoningEngine(
                effective_model,
                reasoning_config
            )
            await reasoning_engine.initialize()
            
            # Stream initial thinking message
            thinking_msg = json.dumps({
                "event": "thinking",
                "data": {
                    "content": "Analyzing your request...",
                    "model": effective_model.value
                }
            })
            yield f"data: {thinking_msg}\n\n"
            
            # Extract context from request with error handling
            context_messages = []
            try:
                if hasattr(request, 'messages') and request.messages is not None:
                    if isinstance(request.messages, list):
                        for msg in request.messages[-5:]:  # Last 5 messages
                            if isinstance(msg, dict):
                                context_messages.append({
                                    "role": "user" if msg.get("role") == "user" else "assistant",
                                    "content": msg.get("content", "")
                                })
                            else:
                                logger.warning(f"Invalid message format in request: {type(msg)}")
                    else:
                        logger.warning(f"request.messages is not a list: {type(request.messages)}")
            except Exception as e:
                logger.error(f"Error extracting context messages: {e}")
                # Continue with empty context_messages
            
            # Get router metadata if available (from state)
            # TODO: Replace these placeholder values with dynamic data from actual router
            # These values should be obtained from the router's analysis of the query
            router_metadata = {
                "query_complexity": 0.5,  # PLACEHOLDER: Should come from router analysis
                "routing_confidence": 0.8  # PLACEHOLDER: Should come from router confidence scoring
            }
            
            # Perform reasoning
            reasoning_output = await reasoning_engine.reason_about_query(
                query=request.message,
                context_messages=context_messages,
                api_key=api_key,
                router_metadata=router_metadata
            )
            
            # Stream the response tokens
            response_text = reasoning_output.final_response_markdown
            words = response_text.split()
            
            # Stream words in small batches for natural feel
            for i in range(0, len(words), STREAMING_BATCH_SIZE):
                batch = words[i:i+STREAMING_BATCH_SIZE]
                token_msg = json.dumps({
                    "event": "token",
                    "data": {
                        "content": " ".join(batch) + " "
                    }
                })
                yield f"data: {token_msg}\n\n"
                await asyncio.sleep(STREAMING_DELAY)  # Configurable delay for natural streaming
            
            # Redact reasoning UI for safety
            safe_reasoning_ui = redact_reasoning_ui(reasoning_output.reasoning_ui.dict())
            
            # Get budget headroom
            headroom = await budget_manager.headroom(effective_model.value)
            
            # Send final event with reasoning UI
            final_msg = json.dumps({
                "event": "completion.final",
                "data": {
                    "final_response_markdown": reasoning_output.final_response_markdown,
                    "reasoning_ui": safe_reasoning_ui,
                    "model_effective": effective_model.value,
                    "budget": {
                        "rpd_used": headroom.get("rpd_used", 0),
                        "headroom": headroom.get("status", "OK")
                    }
                }
            })
            yield f"data: {final_msg}\n\n"
            
            # Record usage
            await budget_manager.record(effective_model.value)
            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            error_msg = json.dumps({
                "event": "error",
                "data": {
                    "error": str(e)
                }
            })
            yield f"data: {error_msg}\n\n"
    
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.post("/agent/unified/stream")
async def unified_agent_stream(request: UnifiedAgentRequest):
    """Unified streaming endpoint that routes to appropriate agents using LangGraph."""
    if not request.message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    return StreamingResponse(
        unified_agent_stream_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

# --- Research Agent Streaming Endpoint ---
async def research_agent_stream_generator(query: str, trace_id: str | None = None) -> AsyncIterable[str]:
    """Streaming research agent that sends steps and final results."""
    try:
        research_graph = get_research_graph()
        
        # Send initial status
        yield f"data: {json.dumps({'type': 'step', 'data': {'type': 'Starting Research', 'description': 'Initializing research query...', 'status': 'in-progress'}})}\n\n"
        
        initial_state: ResearchState = {
            "query": query,
            "urls": [],
            "documents": [],
            "answer": None,
            "citations": None,
        }
        
        # Execute research (this should be made async in the future)
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, research_graph.invoke, initial_state)
        
        # Send research completion step
        yield f"data: {json.dumps({'type': 'step', 'data': {'type': 'Research Complete', 'description': 'Research analysis finished', 'status': 'completed'}})}\n\n"
        
        # Send final answer
        answer = result.get("answer", "No answer provided.")
        citations = result.get("citations", [])
        
        final_message = {
            "id": "research_result",
            "type": "agent",
            "content": answer,
            "timestamp": "now",
            "agentType": "research",
            "citations": citations,
            "feedback": None,
            "trace_id": trace_id
        }
        
        yield f"data: {json.dumps({'type': 'message', 'data': final_message})}\n\n"
        
    except Exception as e:
        print(f"Error in research_agent_stream_generator: {e}")
        error_step = {
            "type": "Error", 
            "description": f"Research failed: {str(e)}", 
            "status": "error"
        }
        yield f"data: {json.dumps({'type': 'step', 'data': error_step})}\n\n"

@router.post("/agent/research/stream")
async def research_agent_stream(request: ResearchRequest):
    """Streaming research endpoint that matches frontend expectations."""
    if not request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    return StreamingResponse(
        research_agent_stream_generator(request.query, request.trace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
