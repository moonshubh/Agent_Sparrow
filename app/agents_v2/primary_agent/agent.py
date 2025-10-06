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
from app.agents_v2.primary_agent.adapter_bridge import get_primary_agent_model

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
        logger.warning(f"API key validation failed: empty or not string")
        return False
    # Google API keys typically start with 'AIza' and are 39 characters long
    if not api_key.startswith('AIza') or len(api_key) != 39:
        logger.warning(f"API key format validation failed: expected format with specific prefix and length")
        return False
    # Additional validation for valid characters (alphanumeric, underscore, hyphen)
    if not re.match(r'^[A-Za-z0-9_-]+$', api_key):
        logger.warning(f"API key contains invalid characters")
        return False
    logger.debug(f"API key validation successful")
    return True

@lru_cache(maxsize=128)
def _get_model_config() -> str:
    """Get the configured model name from settings with caching."""
    from app.core.settings import settings
    return settings.primary_agent_model

def create_user_specific_model(api_key: str, thinking_budget: Optional[int] = None, bind_tools: bool = True) -> ChatGoogleGenerativeAI:
    """Create a user-specific Gemini model with their API key and thinking budget.
    
    Features:
    - API key format validation
    - Configurable model name from settings
    - Caching mechanism to reuse models
    - Comprehensive error handling
    - Thinking budget support for Gemini 2.5 Flash
    
    Args:
        api_key: User's Google API key
        thinking_budget: Token budget for thinking mode (0-24576, or -1 for dynamic)
        bind_tools: Whether to bind tools to the model (default True)
    """
    if not _validate_api_key(api_key):
        raise ValueError("Invalid API key format. Expected Google API key starting with 'AIza' and 39 characters long.")
    
    # Check cache first (using a hash of the API key for security)
    cache_key = f"{hash(api_key)}_{_get_model_config()}_{thinking_budget}_{bind_tools}"
    if cache_key in _model_cache:
        logger.debug(f"Returning cached model for user with thinking_budget: {thinking_budget}, bind_tools: {bind_tools}")
        return _model_cache[cache_key]
    
    try:
        model_name = _get_model_config()
        logger.info(f"Creating new user-specific model with {model_name}, thinking_budget: {thinking_budget}")
        
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }
        
        # Create model configuration
        model_kwargs = {
            "model": model_name,
            "temperature": 0,
            "google_api_key": api_key,
            "safety_settings": safety_settings,
            "convert_system_message_to_human": True
        }
        
        # Add thinking budget for Gemini 2.5 Flash models
        if "2.5-flash" in model_name.lower() and thinking_budget is not None:
            model_kwargs["thinking_budget"] = thinking_budget
            logger.info(f"Using thinking budget: {thinking_budget} tokens")
        
        model_base = ChatGoogleGenerativeAI(**model_kwargs)
        
        # Bind tools if requested and then wrap for rate limiting
        if bind_tools:
            model_with_tools_base = model_base.bind_tools([mailbird_kb_search, tavily_web_search])
            wrapped_model = wrap_gemini_agent(model_with_tools_base, model_name)
        else:
            wrapped_model = wrap_gemini_agent(model_base, model_name)
        
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

            # Determine provider/model with request override via state
            from app.core.settings import settings as app_settings
            # Prefer provider/model from state if available; otherwise use env/settings defaults
            state_provider = getattr(state, "provider", None)
            state_model = getattr(state, "model", None)

            provider = (state_provider or os.getenv("PRIMARY_AGENT_PROVIDER") or getattr(app_settings, "primary_agent_provider", "google")).lower()
            model_name = (state_model or getattr(app_settings, "primary_agent_model", "gemini-2.5-flash"))
            logger.info(f"[primary_agent] selected provider={provider}, model={model_name}")

            # Branch per provider
            if provider == "google":
                logger.debug("[primary_agent] entering Google/Gemini branch")
                # Get user-specific API key (with env fallback when no user context)
                from app.core.user_context import get_user_gemini_key, get_current_user_context
                user_key = await get_user_gemini_key()
                env_key = os.getenv("GEMINI_API_KEY")
                selected_key = user_key or env_key

                # Log key source
                user_context = get_current_user_context()
                if selected_key:
                    is_fallback = (env_key and selected_key == env_key and (not user_key))
                    source = "fallback_env" if is_fallback else ("user" if user_key else "env")
                    logger.debug(f"[primary_agent] Gemini API key source: {source}")
                    parent_span.set_attribute("api_key_source", source)

                if not selected_key:
                    error_msg = "No Gemini API key available (user or env)"
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

                # Helper to detect auth errors that imply invalid/expired key
                def _is_auth_error(exc: Exception) -> bool:
                    msg = str(exc).lower()
                    keywords = [
                        "api key", "key invalid", "invalid api key", "permission denied",
                        "unauthorized", "401", "403", "forbidden", "expired", "authentication"
                    ]
                    return any(k in msg for k in keywords)

                # Try with selected key; on auth error, fallback to env key once if different
                used_key = selected_key
                try:
                    logger.debug("Creating Gemini model with tools and rate limiting")
                    model_with_tools = create_user_specific_model(selected_key)
                except Exception as e:
                    if _is_auth_error(e) and env_key and selected_key != env_key:
                        logger.warning(f"[primary_agent] Gemini auth error with user key, retrying with env key: {e}")
                        model_with_tools = create_user_specific_model(env_key)
                        used_key = env_key
                        parent_span.set_attribute("api_key_source_retry", "fallback_env_after_auth_error")
                    else:
                        raise

            elif provider == "openai":
                logger.debug("[primary_agent] entering OpenAI branch")
                # Prefer user context key with env fallback
                from app.core.user_context import get_user_openai_key
                openai_key = await get_user_openai_key()
                if not openai_key:
                    openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("OpenAI_API_KEY")
                if not openai_key:
                    error_msg = "OpenAI provider selected but OPENAI_API_KEY not configured (user/env)."
                    logger.warning(error_msg)
                    parent_span.set_attribute("error", error_msg)
                    parent_span.set_status(Status(StatusCode.ERROR, "No OpenAI API key"))
                    yield AIMessageChunk(content="OpenAI API key missing. Please set it in Settings or as OPENAI_API_KEY and try again.", role="error")
                    return

                # Load model via providers registry (tools binding is optional here)
                logger.debug(f"Loading OpenAI model via providers registry: {model_name}")
                model_with_tools = await get_primary_agent_model(api_key=openai_key, provider="openai", model=model_name)

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
                debug_mode=settings.reasoning_debug_mode,
                quality_level=getattr(settings, "primary_agent_quality_level", "balanced")
            )
            reasoning_engine = ReasoningEngine(
                model=model_with_tools,
                config=reasoning_config,
                provider=provider,
                model_name=model_name,
            )
            # Store API key for provider-specific reasoning models
            if provider == "google":
                reasoning_engine._api_key = used_key
            elif provider == "openai":
                reasoning_engine._api_key = openai_key

            # Perform comprehensive reasoning with optimized LLM calls
            reasoning_state = await reasoning_engine.reason_about_query(
                query=user_query,
                context={"messages": state.messages},
                session_id=getattr(state, 'session_id', 'default')
            )
            
            # Generate enhanced response with thinking budget (2nd LLM call)
            final_response = None
            if reasoning_state and reasoning_state.query_analysis:
                enhanced_response = await reasoning_engine.generate_enhanced_response(reasoning_state)
                
                # Optional: Refine response if confidence is low (3rd LLM call)
                refined_response = await reasoning_engine.refine_response_if_needed(reasoning_state)
                
                # Use refined response if available, otherwise use enhanced response
                final_response = refined_response if refined_response else enhanced_response

            # Log key reasoning results for observability
            parent_span.set_attribute("reasoning.confidence", reasoning_state.overall_confidence)
            if reasoning_state.query_analysis:
                parent_span.set_attribute("reasoning.emotion", reasoning_state.query_analysis.emotional_state.value)
                parent_span.set_attribute("reasoning.category", reasoning_state.query_analysis.problem_category.value)
            if reasoning_state.self_critique_result:
                parent_span.set_attribute("reasoning.critique_score", reasoning_state.self_critique_result.critique_score)
                parent_span.set_attribute("reasoning.critique_passed", reasoning_state.self_critique_result.passed_critique)

            # The final, critiqued response is now ready to be streamed.
            if not final_response:
                logger.warning("Reasoning completed but no final response was generated.")
                yield AIMessageChunk(content="I'm sorry, I was unable to generate a response. Please try again.", role="assistant")
                return

            # Generate follow-up questions based on the response
            follow_up_questions = []
            if reasoning_state and reasoning_state.query_analysis:
                from .prompts.response_formatter import ResponseFormatter
                follow_up_questions = ResponseFormatter.generate_follow_up_questions(
                    issue=user_query,
                    emotion=reasoning_state.query_analysis.emotional_state,
                    solution_provided=final_response
                )
            # Prepare metadata (thinking trace, follow-ups, tool decisions) before streaming
            metadata_to_send = {}

            if follow_up_questions:
                metadata_to_send["followUpQuestions"] = follow_up_questions[:5]
                metadata_to_send["followUpQuestionsUsed"] = 0

            if reasoning_state and reasoning_state.tool_reasoning:
                tool_reasoning = reasoning_state.tool_reasoning
                metadata_to_send["toolResults"] = {
                    "decision": tool_reasoning.decision_type.value,
                    "reasoning": tool_reasoning.reasoning,
                    "confidence": tool_reasoning.confidence,
                    "required_information": tool_reasoning.required_information,
                    "knowledge_gaps": tool_reasoning.knowledge_gaps,
                    "expected_sources": tool_reasoning.expected_sources,
                }

            if settings.should_enable_thinking_trace() and reasoning_state:
                logger.debug(
                    "[primary_agent] thinking trace enabled=%s, reasoning_steps=%d",
                    settings.should_enable_thinking_trace(),
                    len(getattr(reasoning_state, "reasoning_steps", []) or []),
                )
                thinking_trace = {
                    "confidence": reasoning_state.overall_confidence,
                    "thinking_steps": [],
                    "tool_decision": None,
                    "knowledge_gaps": []
                }

                for step in reasoning_state.reasoning_steps:
                    thinking_trace["thinking_steps"].append({
                        "phase": step.phase.value,
                        "thought": step.reasoning,
                        "confidence": step.confidence
                    })

                if reasoning_state.query_analysis:
                    thinking_trace["emotional_state"] = reasoning_state.query_analysis.emotional_state.value
                    thinking_trace["problem_category"] = reasoning_state.query_analysis.problem_category.value
                    thinking_trace["complexity"] = reasoning_state.query_analysis.complexity_score

                if reasoning_state.tool_reasoning:
                    thinking_trace["tool_decision"] = reasoning_state.tool_reasoning.decision_type.value
                    thinking_trace["tool_confidence"] = reasoning_state.tool_reasoning.confidence
                    thinking_trace["knowledge_gaps"] = reasoning_state.tool_reasoning.knowledge_gaps

                if reasoning_state.self_critique_result:
                    thinking_trace["critique_score"] = reasoning_state.self_critique_result.critique_score
                    thinking_trace["passed_critique"] = reasoning_state.self_critique_result.passed_critique

                metadata_to_send["thinking_trace"] = thinking_trace

            if metadata_to_send:
                preface_metadata_chunk = AIMessageChunk(
                    content="",
                    role="assistant",
                    additional_kwargs={
                        "metadata": metadata_to_send,
                        "metadata_stage": "reasoning_snapshot"
                    }
                )
                yield preface_metadata_chunk

            # Stream the final, cleaned response chunk by chunk to the client.
            chunk_size = 200  # Increased for better performance
            for i in range(0, len(final_response), chunk_size):
                chunk_content = final_response[i:i+chunk_size]
                yield AIMessageChunk(content=chunk_content, role="assistant")
                await anyio.sleep(0.005)  # Reduced delay for smoother streaming
            
            if metadata_to_send:
                metadata_chunk = AIMessageChunk(
                    content="",
                    role="assistant",
                    additional_kwargs={
                        "metadata": metadata_to_send,
                        "metadata_stage": "final_snapshot"
                    }
                )
                yield metadata_chunk

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
