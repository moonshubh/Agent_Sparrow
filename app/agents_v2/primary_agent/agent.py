import logging
import os
import anyio
import re
from dotenv import load_dotenv
from typing import AsyncIterator, Dict, Optional, Any
import asyncio
from functools import lru_cache
import hashlib
from datetime import datetime

from langchain_core.messages import AIMessageChunk
from langchain_google_genai import ChatGoogleGenerativeAI, HarmCategory, HarmBlockThreshold
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.core.rate_limiting.agent_wrapper import wrap_gemini_agent
from app.agents_v2.primary_agent.schemas import PrimaryAgentState
from app.agents_v2.primary_agent.tools import mailbird_kb_search, tavily_web_search
from app.agents_v2.primary_agent.reasoning.unified_deep_reasoning_engine import (
    UnifiedDeepReasoningEngine, UnifiedReasoningConfig
)
from app.agents_v2.primary_agent.reasoning.schemas import ReasoningConfig
# AgentSparrowV9Prompts now integrated via model-specific factory
from app.agents_v2.primary_agent.llm_registry import SupportedModel, DEFAULT_MODEL, validate_model_id
from app.agents_v2.primary_agent.llm_factory import build_llm
from app.agents_v2.primary_agent.model_adapter import ModelAdapter
from app.agents_v2.primary_agent.exceptions import (
    RateLimitException,
    InvalidAPIKeyException,
    TimeoutException,
    NetworkException,
    ConfigurationException,
    ReasoningException,
    create_exception_from_error
)
from app.agents_v2.primary_agent.prompts.model_specific_factory import (
    ModelSpecificPromptFactory, PromptOptimizationLevel
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
_model_cache: OrderedDict[str, Any] = OrderedDict()  # Changed to Any to support different model types
MAX_CACHE_SIZE = 100

def clear_model_cache():
    """Clear the model cache. Useful for testing or when cache becomes stale."""
    global _model_cache
    _model_cache.clear()
    logger.info("Model cache cleared")

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

def _generate_secure_cache_key(api_key: str, model_value: str) -> str:
    """Generate a secure cache key using SHA256 hash.
    
    Args:
        api_key: The API key to hash
        model_value: The model identifier
        
    Returns:
        A secure cache key truncated to reasonable length
    """
    # Create a SHA256 hash of the API key for security
    hash_object = hashlib.sha256(api_key.encode('utf-8'))
    hash_hex = hash_object.hexdigest()
    # Truncate to first 16 characters for reasonable cache key length
    return f"{hash_hex[:16]}_{model_value}"

def create_user_specific_model(api_key: str, model_id: Optional[str] = None) -> Any:
    """Create a user-specific model with their API key.
    
    Features:
    - Basic API key validation
    - Support for multiple models (Gemini Flash, Pro, Kimi K2)
    - Caching mechanism to reuse models
    - Comprehensive error handling
    - Model adapter for consistent behavior
    - Thread-safe API key handling
    """
    if not _validate_api_key(api_key):
        raise InvalidAPIKeyException(
            "API key is missing or empty",
            technical_details="API key validation failed: empty or None"
        )
    
    # Validate and get model
    try:
        model_enum = validate_model_id(model_id) if model_id else DEFAULT_MODEL
    except ValueError as e:
        logger.warning(f"Invalid model ID '{model_id}', using default: {e}")
        model_enum = DEFAULT_MODEL
    
    # Check cache first using secure hash
    cache_key = _generate_secure_cache_key(api_key, model_enum.value)
    if cache_key in _model_cache:
        logger.debug(f"Returning cached {model_enum.value} model for user")
        return _model_cache[cache_key]
    
    try:
        logger.info(f"Creating new user-specific model: {model_enum.value} (requested: {model_id})")
        
        # Get model-specific configuration from the prompt factory
        prompt_factory = ModelSpecificPromptFactory()
        optimization_level = PromptOptimizationLevel.BALANCED  # Default optimization
        model_config = prompt_factory.get_model_configuration(model_enum, 
            prompt_factory.get_recommended_config(model_enum, optimization_level))
        
        logger.info(f"Using model-specific config for {model_enum.value}: temperature={model_config.get('temperature', 0.3)}")
        
        # Build the base model using the factory with model-specific configuration
        # This ensures thread-safety by not modifying os.environ
        api_key_param = api_key
        if model_enum == SupportedModel.KIMI_K2:
            # For Kimi K2, we pass the API key directly to the model
            # instead of setting it in the environment
            base_llm = build_llm(
                model_enum, 
                temperature=model_config.get('temperature', 0.6),  # Kimi K2 optimal
                max_tokens=model_config.get('max_tokens', 2048),
                api_key=api_key_param,
                **{k: v for k, v in model_config.items() if k not in ['temperature', 'max_tokens']}
            )
        else:
            # For Gemini models, pass the API key directly with model-optimized config
            base_llm = build_llm(
                model_enum, 
                temperature=model_config.get('temperature', 0.3),
                max_tokens=model_config.get('max_tokens', 2048),
                api_key=api_key_param,
                **{k: v for k, v in model_config.items() if k not in ['temperature', 'max_tokens']}
            )
        
        # Create model adapter for consistent behavior
        model_adapter = ModelAdapter(base_llm, model_enum)
        
        # Bind tools to the model
        model_with_tools = model_adapter.bind_tools([mailbird_kb_search, tavily_web_search])
        
        # Wrap for rate limiting
        if model_enum in (SupportedModel.GEMINI_FLASH, SupportedModel.GEMINI_PRO):
            model_name = model_enum.value.split("/")[-1]  # Extract just the model name
            wrapped_model = wrap_gemini_agent(model_with_tools, model_name)
        elif model_enum == SupportedModel.KIMI_K2:
            # Create a generic rate limiter for Kimi K2
            from app.core.rate_limiting.generic_limiter import create_rate_limited_model
            wrapped_model = create_rate_limited_model(model_with_tools, "kimi-k2")
        else:
            wrapped_model = model_with_tools
        
        # Cache the model (limit cache size to prevent memory issues)
        if len(_model_cache) >= MAX_CACHE_SIZE:
            # Remove oldest entry (FIFO with OrderedDict)
            _model_cache.popitem(last=False)  # Remove first (oldest) item
            logger.debug("Evicted oldest model from cache")
        
        _model_cache[cache_key] = wrapped_model
        logger.debug(f"Cached new model for user (cache size: {len(_model_cache)})")
        
        return wrapped_model
        
    except Exception as e:
        logger.error(f"Error creating user-specific model {model_enum.value}: {e}")
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

            # Create user-specific model with optional model selection
            selected_model = state.model  # Use the correct field name from PrimaryAgentState
            logger.info(f"Primary agent received selected_model: {selected_model}")
            
            # Determine model type to get appropriate API key
            try:
                model_enum = validate_model_id(selected_model) if selected_model else DEFAULT_MODEL
            except ValueError as e:
                logger.warning(f"Invalid model ID '{selected_model}', using default: {e}")
                model_enum = DEFAULT_MODEL
            
            # Get the appropriate API key based on model type
            if model_enum == SupportedModel.KIMI_K2:
                # For Kimi K2, try OpenRouter API key first, fall back to Gemini
                from app.core.user_context import get_user_openrouter_key, get_user_gemini_key
                api_key = await get_user_openrouter_key()
                if not api_key:
                    api_key = await get_user_gemini_key()  # Fallback to Gemini key
                    logger.info("Using Gemini API key for Kimi K2 model (OpenRouter key not available)")
                
                if not api_key:
                    error_msg = "No API key available for Kimi K2 model"
                    logger.warning(f"{error_msg} - user_query: {user_query[:100]}...")
                    parent_span.set_attribute("error", error_msg)
                    parent_span.set_status(Status(StatusCode.ERROR, "No API key"))
                    
                    detailed_guidance = (
                        "To use Kimi K2, please configure an API key:\n\n"
                        "**Option 1 - OpenRouter (Recommended):**\n"
                        "1. Go to Settings in the application\n"
                        "2. Navigate to the API Keys section\n"
                        "3. Enter your OpenRouter API key (get one at https://openrouter.ai/keys)\n\n"
                        "**Option 2 - Use Gemini API key:**\n"
                        "1. Enter your Google Gemini API key (get one at https://makersuite.google.com/app/apikey)\n"
                        "2. It will be used to access Kimi K2 via OpenRouter\n\n"
                        "4. Save your settings and try again"
                    )
                    from langchain_core.messages import AIMessage
                    return {"messages": [AIMessage(content=detailed_guidance)], "qa_retry_count": 0}
            else:
                # For Gemini models, use Gemini API key
                from app.core.user_context import get_user_gemini_key
                api_key = await get_user_gemini_key()
                
                if not api_key:
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
            
            model_with_tools = create_user_specific_model(api_key, selected_model)

            parent_span.set_attribute("input.query", user_query)
            parent_span.set_attribute("state.message_count", len(state.messages))

            # Initialize unified deep reasoning engine for single-pass reasoning
            from app.core.settings import settings
            from app.core.user_context import get_user_gemini_key
            
            # Get API key for the reasoning engine
            reasoning_api_key = await get_user_gemini_key()
            if not reasoning_api_key:
                logger.error("No API key available for reasoning engine")
                from langchain_core.messages import AIMessage
                return {"messages": [AIMessage(content="API key required for reasoning engine")], "qa_retry_count": 0}
            
            # Use unified deep reasoning engine for single-pass reasoning with safety
            reasoning_config = UnifiedReasoningConfig(
                enable_caching=True,
                enable_polish_pass=True,
                polish_threshold=0.75
            )
            
            # Convert selected_model string to SupportedModel enum
            try:
                model_enum = validate_model_id(selected_model) if selected_model else DEFAULT_MODEL
            except ValueError:
                model_enum = DEFAULT_MODEL
                
            reasoning_engine = UnifiedDeepReasoningEngine(
                model_enum,  # Pass the validated model enum
                reasoning_config
            )
            await reasoning_engine.initialize()
            logger.info(f"Using UnifiedDeepReasoningEngine for single-pass reasoning with query: {user_query[:50]}...")

            # Create progress callback for Pro model progress updates
            progress_updates = []
            def progress_callback(message: str, current: int, total: int):
                """Capture progress updates for Pro model reasoning."""
                progress_updates.append({
                    "message": message,
                    "current": current,
                    "total": total,
                    "timestamp": datetime.now().isoformat()
                })
                logger.info(f"Reasoning Progress ({current}/{total}): {message}")
            
            # Perform single-pass deep reasoning with routing metadata
            context_messages = [{"role": "user" if m.type == "human" else "assistant", "content": m.content} 
                               for m in state.messages]
            
            reasoning_result = await reasoning_engine.reason_about_query(
                query=user_query,
                context_messages=context_messages,
                api_key=reasoning_api_key,
                router_metadata=state.routing_metadata  # Pass routing metadata from router
            )

            # Log key reasoning results for observability
            parent_span.set_attribute("reasoning.confidence", reasoning_result.quality.confidence)
            parent_span.set_attribute("reasoning.emotion", reasoning_result.analysis.emotion)
            parent_span.set_attribute("reasoning.complexity", reasoning_result.analysis.complexity)
            parent_span.set_attribute("reasoning.clarity", reasoning_result.quality.clarity)
            parent_span.set_attribute("reasoning.completeness", reasoning_result.quality.completeness)
            # Note: emotional_alignment might not be present in quality metrics

            # Extract the final response
            final_response = reasoning_result.final_response_markdown
            
            if not final_response:
                logger.warning("Reasoning completed but no final response was generated")
                
                # Generate fallback response based on available analysis
                fallback_response = "I apologize, but I encountered an issue generating a response. Please try rephrasing your question."
                
                if reasoning_result.analysis:
                    fallback_response = f"I understand you're asking about {reasoning_result.analysis.intent}. Let me help you with this issue. Please provide any additional details about what specific problem you're experiencing."
                
                from langchain_core.messages import AIMessage
                return {"messages": [AIMessage(content=fallback_response)], "qa_retry_count": 0}

            # Create messages with reasoning UI
            from langchain_core.messages import AIMessage
            messages = []
            
            # Add final response message with reasoning UI metadata
            additional_kwargs = {
                "message_type": "final",
                "reasoning_ui": reasoning_result.reasoning_ui.model_dump(),  # Include reasoning UI for frontend
                "confidence": reasoning_result.quality.confidence,
            }
            
            # Add optional fields if they exist
            if hasattr(reasoning_result.reasoning_ui, 'model_effective'):
                additional_kwargs["model_effective"] = reasoning_result.reasoning_ui.model_effective
            if hasattr(reasoning_result.reasoning_ui, 'budget'):
                additional_kwargs["budget"] = reasoning_result.reasoning_ui.budget.model_dump()
                
            final_msg = AIMessage(
                content=final_response,
                additional_kwargs=additional_kwargs
            )
            messages.append(final_msg)
            
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
            return {
                "messages": messages,
                "qa_retry_count": 0
            }



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