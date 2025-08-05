import logging
import os
import anyio
import re
from dotenv import load_dotenv
from typing import AsyncIterator, Dict, Optional
from functools import lru_cache

from langchain_core.messages import AIMessageChunk
from langchain_google_genai import ChatGoogleGenerativeAI, HarmCategory, HarmBlockThreshold
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.core.rate_limiting.agent_wrapper import wrap_gemini_agent
from app.agents_v2.primary_agent.schemas import PrimaryAgentState
from app.agents_v2.primary_agent.tools import mailbird_kb_search, tavily_web_search
from app.agents_v2.primary_agent.reasoning import ReasoningEngine, ReasoningConfig
from app.agents_v2.primary_agent.prompts import AgentSparrowV9Prompts

# Standard logger setup
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Get a tracer instance for OpenTelemetry
tracer = trace.get_tracer(__name__)

# Load environment variables from .env file
load_dotenv()

# Model cache for reusing user-specific models
_model_cache: Dict[str, ChatGoogleGenerativeAI] = {}

def _validate_api_key(api_key: str) -> bool:
    """Validate API key format for Google Generative AI."""
    if not api_key or not isinstance(api_key, str):
        return False
    # Google API keys typically start with 'AIza' and are 39 characters long
    if not api_key.startswith('AIza') or len(api_key) != 39:
        logger.warning(f"API key format validation failed: expected format 'AIza...' with 39 characters, got {len(api_key)} characters")
        return False
    # Additional validation for valid characters (alphanumeric, underscore, hyphen)
    if not re.match(r'^[A-Za-z0-9_-]+$', api_key):
        logger.warning("API key contains invalid characters")
        return False
    return True

@lru_cache(maxsize=128)
def _get_model_config() -> str:
    """Get the configured model name from settings with caching."""
    from app.core.settings import settings
    return settings.primary_agent_model

def create_user_specific_model(api_key: str) -> ChatGoogleGenerativeAI:
    """Create a user-specific Gemini model with their API key.
    
    Features:
    - API key format validation
    - Configurable model name from settings
    - Caching mechanism to reuse models
    - Comprehensive error handling
    """
    if not _validate_api_key(api_key):
        raise ValueError("Invalid API key format. Expected Google API key starting with 'AIza' and 39 characters long.")
    
    # Check cache first (using a hash of the API key for security)
    cache_key = f"{hash(api_key)}_{_get_model_config()}"
    if cache_key in _model_cache:
        logger.debug("Returning cached model for user")
        return _model_cache[cache_key]
    
    try:
        model_name = _get_model_config()
        logger.info(f"Creating new user-specific model with {model_name}")
        
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }
        
        model_base = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0,
            google_api_key=api_key,
            safety_settings=safety_settings,
            convert_system_message_to_human=True
        )
        
        # Bind tools and then wrap for rate limiting
        model_with_tools_base = model_base.bind_tools([mailbird_kb_search, tavily_web_search])
        wrapped_model = wrap_gemini_agent(model_with_tools_base, model_name)
        
        # Cache the model (limit cache size to prevent memory issues)
        if len(_model_cache) >= 100:  # Simple cache eviction
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(_model_cache))
            del _model_cache[oldest_key]
            logger.debug("Evicted oldest model from cache")
        
        _model_cache[cache_key] = wrapped_model
        logger.debug(f"Cached new model for user (cache size: {len(_model_cache)})")
        
        return wrapped_model
        
    except Exception as e:
        logger.error(f"Error creating user-specific model with {_get_model_config()}: {e}")
        # Clear any partial cache entry
        _model_cache.pop(cache_key, None)
        raise ValueError(f"Failed to create AI model: {str(e)}")

async def run_primary_agent(state: PrimaryAgentState) -> AsyncIterator[AIMessageChunk]:
    """
    Asynchronously processes a user query using the primary agent system, yielding AI message chunks as a streaming response.

    This function orchestrates the reasoning engine to generate a comprehensive, self-critiqued answer.
    It handles input validation, calls the reasoning engine, logs telemetry, and streams the final response.

    Parameters:
        state (PrimaryAgentState): The current agent state, including user messages and session context.

    Yields:
        AIMessageChunk: Streamed chunks of the AI assistant's response.
    """
    with tracer.start_as_current_span("primary_agent.run") as parent_span:
        try:
            logger.debug("Running primary agent")
            user_query = state.messages[-1].content if state.messages else ""

            # Input Validation: Query length
            MAX_QUERY_LENGTH = 4000
            if len(user_query) > MAX_QUERY_LENGTH:
                parent_span.set_attribute("input.query.error", "Query too long")
                parent_span.set_status(Status(StatusCode.ERROR, "Query too long"))
                yield AIMessageChunk(content="Your query is too long. Please shorten it and try again.", role="assistant")
                return

            # Get user-specific API key
            from app.core.user_context import get_user_gemini_key
            gemini_api_key = await get_user_gemini_key()
            
            if not gemini_api_key:
                error_msg = "No Gemini API key available for user"
                logger.warning(f"{error_msg} - user_query: {user_query[:100]}...")
                parent_span.set_attribute("error", error_msg)
                parent_span.set_status(Status(StatusCode.ERROR, "No API key"))
                
                detailed_guidance = (
                    "To use Agent Sparrow, please configure your Gemini API key:\n\n"
                    "1. Go to Settings in the application\n"
                    "2. Navigate to the API Keys section\n"
                    "3. Enter your Google Gemini API key (get one at https://makersuite.google.com/app/apikey)\n"
                    "4. Save your settings and try again\n\n"
                    "Your API key should start with 'AIza' and be 39 characters long."
                )
                yield AIMessageChunk(content=detailed_guidance, role="error")
                return
            
            # Create user-specific model
            model_with_tools = create_user_specific_model(gemini_api_key)

            parent_span.set_attribute("input.query", user_query)
            parent_span.set_attribute("state.message_count", len(state.messages))

            # Initialize reasoning engine with self-critique enabled
            from app.core.settings import settings
            reasoning_config = ReasoningConfig(
                enable_self_critique=True,
                enable_chain_of_thought=settings.reasoning_enable_chain_of_thought,
                enable_problem_solving_framework=settings.reasoning_enable_problem_solving,
                enable_tool_intelligence=settings.reasoning_enable_tool_intelligence,
                enable_quality_assessment=settings.reasoning_enable_quality_assessment,
                enable_reasoning_transparency=settings.reasoning_enable_reasoning_transparency,
                debug_mode=settings.reasoning_debug_mode
            )
            reasoning_engine = ReasoningEngine(model=model_with_tools, config=reasoning_config)

            # Perform comprehensive reasoning with optimized LLM calls
            reasoning_state = await reasoning_engine.reason_about_query(
                query=user_query,
                context={"messages": state.messages},
                session_id=getattr(state, 'session_id', 'default')
            )
            
            # Generate enhanced response with thinking budget (2nd LLM call)
            if reasoning_state and reasoning_state.query_analysis:
                await reasoning_engine.generate_enhanced_response(reasoning_state)
                
                # Optional: Refine response if confidence is low (3rd LLM call)
                await reasoning_engine.refine_response_if_needed(reasoning_state)

            # Log key reasoning results for observability
            parent_span.set_attribute("reasoning.confidence", reasoning_state.overall_confidence)
            if reasoning_state.query_analysis:
                parent_span.set_attribute("reasoning.emotion", reasoning_state.query_analysis.emotional_state.value)
                parent_span.set_attribute("reasoning.category", reasoning_state.query_analysis.problem_category.value)
            if reasoning_state.self_critique_result:
                parent_span.set_attribute("reasoning.critique_score", reasoning_state.self_critique_result.critique_score)
                parent_span.set_attribute("reasoning.critique_passed", reasoning_state.self_critique_result.passed_critique)

            # The final, critiqued response is now ready to be streamed.
            if not reasoning_state.response_orchestration:
                logger.error("Response orchestration is None in reasoning state")
                logger.error(f"Reasoning state attributes: {vars(reasoning_state)}")
                yield AIMessageChunk(content="I'm sorry, I was unable to generate a response. Please try again.", role="assistant")
                return
                
            final_response = reasoning_state.response_orchestration.final_response_preview

            if not final_response:
                logger.warning("Reasoning completed but no final response was generated.")
                yield AIMessageChunk(content="I'm sorry, I was unable to generate a response. Please try again.", role="assistant")
                return

            # Stream the final, cleaned response chunk by chunk to the client.
            chunk_size = 200  # Increased for better performance
            for i in range(0, len(final_response), chunk_size):
                chunk_content = final_response[i:i+chunk_size]
                yield AIMessageChunk(content=chunk_content, role="assistant")
                await anyio.sleep(0.005)  # Reduced delay for smoother streaming

            parent_span.set_status(Status(StatusCode.OK))

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.exception("Error in run_primary_agent: %s", e)
            logger.error(f"Detailed error trace:\n{error_details}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error args: {e.args}")
            if 'parent_span' in locals() and parent_span.is_recording():
                parent_span.record_exception(e)
                parent_span.set_status(Status(StatusCode.ERROR, str(e)))
            # Include more specific error info in development
            error_msg = f"I'm sorry, an unexpected error occurred: {type(e).__name__}: {str(e)}"
            yield AIMessageChunk(content=error_msg, role="assistant") 