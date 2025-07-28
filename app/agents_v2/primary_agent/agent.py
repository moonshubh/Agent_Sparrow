import logging
import os
import anyio
import re
from dotenv import load_dotenv
from typing import AsyncIterator, Dict, Optional, Any
import asyncio
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
from app.agents_v2.primary_agent.exceptions import (
    RateLimitException,
    InvalidAPIKeyException,
    TimeoutException,
    NetworkException,
    ConfigurationException,
    ReasoningException,
    create_exception_from_error
)

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
from collections import OrderedDict
_model_cache: OrderedDict[str, ChatGoogleGenerativeAI] = OrderedDict()
MAX_CACHE_SIZE = 100

def _validate_api_key(api_key: str) -> bool:
    """Basic API key validation - just check it's not empty.
    
    Let the actual API tell us if the key is invalid rather than
    hardcoding format assumptions that may change.
    """
    return bool(api_key and isinstance(api_key, str) and api_key.strip())

@lru_cache(maxsize=128)
def _get_model_config() -> str:
    """Get the configured model name from settings with caching."""
    from app.core.settings import settings
    return settings.primary_agent_model

def create_user_specific_model(api_key: str) -> ChatGoogleGenerativeAI:
    """Create a user-specific Gemini model with their API key.
    
    Features:
    - Basic API key validation
    - Configurable model name from settings
    - Caching mechanism to reuse models
    - Comprehensive error handling
    """
    if not _validate_api_key(api_key):
        raise InvalidAPIKeyException(
            "API key is missing or empty",
            technical_details="API key validation failed: empty or None"
        )
    
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
        if len(_model_cache) >= MAX_CACHE_SIZE:
            # Remove oldest entry (FIFO with OrderedDict)
            _model_cache.popitem(last=False)  # Remove first (oldest) item
            logger.debug("Evicted oldest model from cache")
        
        _model_cache[cache_key] = wrapped_model
        logger.debug(f"Cached new model for user (cache size: {len(_model_cache)})")
        
        return wrapped_model
        
    except Exception as e:
        logger.error(f"Error creating user-specific model with {_get_model_config()}: {e}")
        # Clear any partial cache entry
        _model_cache.pop(cache_key, None)
        raise ValueError(f"Failed to create AI model: {str(e)}")

async def run_primary_agent(state: PrimaryAgentState) -> Dict[str, Any]:
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
                from langchain_core.messages import AIMessage
                return {"messages": [AIMessage(content="Your query is too long. Please shorten it and try again.")], "qa_retry_count": 0}

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
                from langchain_core.messages import AIMessage
                return {"messages": [AIMessage(content=detailed_guidance)], "qa_retry_count": 0}
            
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

            # Perform comprehensive reasoning. This is a single, blocking call that includes self-critique.
            reasoning_state = await reasoning_engine.reason_about_query(
                query=user_query,
                context={"messages": state.messages},
                session_id=getattr(state, 'session_id', 'default')
            )

            # Log key reasoning results for observability
            parent_span.set_attribute("reasoning.confidence", reasoning_state.overall_confidence)
            if reasoning_state.query_analysis:
                parent_span.set_attribute("reasoning.emotion", reasoning_state.query_analysis.emotional_state.value)
                parent_span.set_attribute("reasoning.category", reasoning_state.query_analysis.problem_category.value)
            if reasoning_state.self_critique_result:
                parent_span.set_attribute("reasoning.critique_score", reasoning_state.self_critique_result.critique_score)
                parent_span.set_attribute("reasoning.critique_passed", reasoning_state.self_critique_result.passed_critique)

            # The final, critiqued response is now ready to be streamed.
            final_response = reasoning_state.response_orchestration.final_response_preview

            if not final_response:
                logger.warning("Reasoning completed but no final response was generated.")
                from langchain_core.messages import AIMessage
                return {"messages": [AIMessage(content="I'm sorry, I was unable to generate a response. Please try again.")], "qa_retry_count": 0}

            # Create assistant message and return state diff
            from langchain_core.messages import AIMessage
            assistant_msg = AIMessage(content=final_response)
            
            # Extract thought steps for frontend display
            thought_steps = []
            if reasoning_state.reasoning_steps:
                for step in reasoning_state.reasoning_steps:
                    thought_steps.append({
                        "step": step.phase.value.replace("_", " ").title(),
                        "content": step.reasoning,
                        "confidence": step.confidence
                    })
            
            parent_span.set_status(Status(StatusCode.OK))
            return {
                "messages": [assistant_msg],
                "qa_retry_count": 0,
                "thought_steps": thought_steps
            }

            # Save the interaction to memory for context retention
            session_id = getattr(state, 'session_id', None)
            if session_id:
                try:
                    from app.services.qdrant_memory import QdrantMemory
                    memory = QdrantMemory()
                    memory.add_interaction(
                        session_id=str(session_id),
                        user_query=user_query,
                        agent_response=final_response
                    )
                    logger.debug(f"Saved interaction to memory for session {session_id}")
                except Exception as e:
                    logger.warning(f"Failed to save interaction to memory: {e}")

            parent_span.set_status(Status(StatusCode.OK))



        except RateLimitException as e:
            logger.warning(f"Rate limit hit: {e}")
            if 'parent_span' in locals() and parent_span.is_recording():
                parent_span.record_exception(e)
                parent_span.set_status(Status(StatusCode.ERROR, "Rate limit exceeded"))
            from langchain_core.messages import AIMessage
            assistant_msg = AIMessage(content=e.user_message())
            return {
                "messages": [assistant_msg],
                "qa_retry_count": 0
            }
            
        except InvalidAPIKeyException as e:
            logger.error(f"Invalid API key: {e}")
            if 'parent_span' in locals() and parent_span.is_recording():
                parent_span.record_exception(e)
                parent_span.set_status(Status(StatusCode.ERROR, "Invalid API key"))
            from langchain_core.messages import AIMessage
            assistant_msg = AIMessage(content=e.user_message())
            return {
                "messages": [assistant_msg],
                "qa_retry_count": 0
            }
            
        except TimeoutException as e:
            logger.warning(f"Request timeout: {e}")
            if 'parent_span' in locals() and parent_span.is_recording():
                parent_span.record_exception(e)
                parent_span.set_status(Status(StatusCode.ERROR, "Request timeout"))
            from langchain_core.messages import AIMessage
            assistant_msg = AIMessage(content=e.user_message())
            return {
                "messages": [assistant_msg],
                "qa_retry_count": 0
            }
            
        except (NetworkException, ConfigurationException, ReasoningException) as e:
            logger.error(f"{type(e).__name__}: {e}")
            if 'parent_span' in locals() and parent_span.is_recording():
                parent_span.record_exception(e)
                parent_span.set_status(Status(StatusCode.ERROR, str(e)))
            from langchain_core.messages import AIMessage
            assistant_msg = AIMessage(content=e.user_message())
            return {
                "messages": [assistant_msg],
                "qa_retry_count": 0
            }
            
        except Exception as e:
            # Convert unknown exceptions using factory
            agent_exception = create_exception_from_error(e)
            logger.exception(f"Unexpected error in primary agent: {agent_exception}")
            
            if 'parent_span' in locals() and parent_span.is_recording():
                parent_span.record_exception(e)
                parent_span.set_status(Status(StatusCode.ERROR, str(e)))
                
            from langchain_core.messages import AIMessage
            assistant_msg = AIMessage(content=agent_exception.user_message())
            return {
                "messages": [assistant_msg],
                "qa_retry_count": 0
            } 