import hashlib
import logging
import os
import anyio
import re
from pathlib import Path
from dotenv import load_dotenv
from typing import AsyncIterator, Dict, Optional, Any, List
from functools import lru_cache

from langchain_core.messages import AIMessageChunk, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI, HarmCategory, HarmBlockThreshold
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.providers.limits import wrap_gemini_agent
from app.agents.primary.primary_agent.schemas import (
    PrimaryAgentState,
    PrimaryAgentFinalResponse,
    GroundingMetadata,
    ToolResultMetadata,
)
from app.agents.primary.primary_agent.tools import mailbird_kb_search, tavily_web_search
from app.agents.primary.primary_agent.reasoning import ReasoningEngine, ReasoningConfig
# v10 prompt is selected inside ReasoningEngine; no direct prompt import needed here
from app.agents.primary.primary_agent.adapter_bridge import get_primary_agent_model
from app.core.settings import settings
from app.agents.primary.primary_agent.feedme_knowledge_tool import (
    enhanced_mailbird_kb_search_structured,
    SearchResultSummary,
)
from app.agents.primary.primary_agent.grounding_utils import (
    build_grounding_digest,
    kb_retrieval_satisfied,
    sanitize_model_response,
    summarize_kb_results,
    summarize_tavily_results,
)
try:
    from app.agents.log_analysis.log_analysis_agent.context.mailbird_settings_loader import (
        load_mailbird_settings,
    )
except Exception:  # pragma: no cover - optional dependency
    load_mailbird_settings = None  # type: ignore

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

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MAILBIRD_SETTINGS_PATH = PROJECT_ROOT / "MailbirdSettings.yml"


@lru_cache(maxsize=1)
def _load_default_mailbird_settings_cached() -> Optional[Dict[str, Any]]:
    if load_mailbird_settings is None:
        return None
    try:
        if not DEFAULT_MAILBIRD_SETTINGS_PATH.exists():
            return None
        return load_mailbird_settings(path=str(DEFAULT_MAILBIRD_SETTINGS_PATH))
    except Exception as exc:  # pragma: no cover - logging side-effect only
        logger.info("Default Mailbird settings not loaded (parse/path): %s", exc)
        return None


async def _tavily_is_configured() -> bool:
    try:
        from app.core.user_context import get_current_user_context

        user_context = get_current_user_context()
        if user_context:
            key = await user_context.get_tavily_api_key()
            if key:
                return True
    except Exception as exc:  # pragma: no cover - best effort
        logger.debug("Unable to resolve user Tavily key: %s", exc)

    return bool(os.getenv("TAVILY_API_KEY"))


async def _run_tavily_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    try:
        from app.tools import user_research_tools as research_tools

        return await research_tools.tavily_web_search(query, max_results=max_results)
    except Exception as exc:  # pragma: no cover
        logger.warning("Tavily search failed: %s", exc)
        return {"results": [], "error": str(exc)}


async def _gather_grounding_evidence(
    query: str,
    *,
    context: Optional[Dict[str, Any]],
    min_results: int,
    min_relevance: float,
    force_websearch: bool = False,
    websearch_max_results: Optional[int] = None,
) -> Dict[str, Any]:
    kb_payload = await anyio.to_thread.run_sync(
        enhanced_mailbird_kb_search_structured,
        query,
        context or {},
        6,
        ["knowledge_base", "feedme"],
        None,
    )

    summary: Optional[SearchResultSummary] = kb_payload.get("summary")
    kb_results: List[Dict[str, Any]] = kb_payload.get("results", [])
    kb_items = summarize_kb_results(kb_results)
    kb_satisfied = kb_retrieval_satisfied(
        summary,
        min_results=min_results,
        min_relevance=min_relevance,
    )
    try:
        if kb_payload.get("error"):
            trace.get_current_span().set_attribute("grounding.rpc_errors", 1)
    except Exception:
        pass

    tavily_payload: Optional[Dict[str, Any]] = None
    tavily_items: List[Dict[str, str]] = []
    used_tavily = False

    if settings.enable_websearch and ((force_websearch) or (not kb_satisfied)) and await _tavily_is_configured():
        max_res = None
        try:
            if websearch_max_results is not None:
                max_res = int(websearch_max_results)
        except Exception:
            max_res = None
        tavily_payload = await _run_tavily_search(query, max_results=max_res or 5)
        used_tavily = True and bool(tavily_payload)
        tavily_results = (tavily_payload or {}).get("results") or []
        tavily_items = summarize_tavily_results(tavily_results)
        try:
            if tavily_payload and tavily_payload.get("error"):
                trace.get_current_span().set_attribute("grounding.tavily_error", tavily_payload.get("error"))
                if tavily_payload.get("status") is not None:
                    trace.get_current_span().set_attribute("grounding.tavily_status", int(tavily_payload.get("status")))
        except Exception:
            pass

    digest = build_grounding_digest(kb_items, tavily_items)

    return {
        "kb": {
            "payload": kb_payload,
            "items": kb_items,
            "summary": summary,
            "satisfied": kb_satisfied,
        },
        "tavily": tavily_payload,
        "tavily_items": tavily_items,
        "used_tavily": used_tavily,
        "forced_websearch": bool(force_websearch),
        "digest": digest,
    }

def _validate_api_key(api_key: str) -> bool:
    """Validate API key format for Google Generative AI."""
    if not api_key or not isinstance(api_key, str):
        logger.warning(f"API key validation failed: empty or not string")
        return False
    # Google keys usually start with 'AIza', but newer formats may vary in length. Warn instead of blocking.
    if not api_key.startswith('AIza'):
        logger.warning("API key does not start with 'AIza'; continuing but downstream calls may fail.")
    # Additional validation for valid characters (alphanumeric, underscore, hyphen)
    if not re.match(r'^[A-Za-z0-9_-]+$', api_key):
        logger.warning(f"API key contains unexpected characters")
        return False
    if len(api_key) < 30 or len(api_key) > 120:
        logger.info("API key length is uncommon (len=%d) but will be accepted.", len(api_key))
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
        raise ValueError("Invalid API key format. Please verify your Google Generative AI key.")
    
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
                return {"messages": state.messages + [AIMessage(content="Your query is too long. Please shorten it and try again.")]}

            grounding_data: Dict[str, Any] = {}
            kb_summary_obj: Optional[SearchResultSummary] = None
            kb_summary: Dict[str, Any] = {}

            if settings.enable_grounded_responses:
                grounding_context_input: Dict[str, Any] = {
                    "session_id": getattr(state, "session_id", "default"),
                    "message_count": len(state.messages),
                }

                grounding_data = await _gather_grounding_evidence(
                    user_query,
                    context=grounding_context_input,
                    min_results=settings.primary_agent_min_kb_results,
                    min_relevance=settings.primary_agent_min_kb_relevance,
                    force_websearch=bool(getattr(state, 'force_websearch', False)),
                    websearch_max_results=getattr(state, 'websearch_max_results', None),
                )

                global_ctx = getattr(state, "global_knowledge_context", None) or {}
                retrieval_ctx = global_ctx.get("retrieval") if isinstance(global_ctx, dict) else None
                global_snippet = None
                if isinstance(global_ctx, dict):
                    global_snippet = global_ctx.get("memory_snippet") or (
                        retrieval_ctx.get("memory_snippet") if isinstance(retrieval_ctx, dict) else None
                    )
                if global_snippet:
                    existing_digest = grounding_data.get("digest") or ""
                    snippet_header = "Global knowledge highlights:\n" + global_snippet
                    combined_digest = "\n\n".join(filter(None, [existing_digest.strip(), snippet_header.strip()]))
                    grounding_data["digest"] = combined_digest.strip()
                    grounding_data["global_knowledge"] = {
                        "hits": len((retrieval_ctx or {}).get("items") or []),
                        "source": (retrieval_ctx or {}).get("source"),
                        "fallback_used": bool((retrieval_ctx or {}).get("fallback_used")),
                        "latency_ms": (retrieval_ctx or {}).get("latency_ms"),
                        "errors": (retrieval_ctx or {}).get("errors"),
                    }
                    parent_span.set_attribute("global_knowledge.hits", grounding_data["global_knowledge"]["hits"])
                    if grounding_data["global_knowledge"]["source"]:
                        parent_span.set_attribute("global_knowledge.source", grounding_data["global_knowledge"]["source"])
                    parent_span.set_attribute("global_knowledge.fallback", grounding_data["global_knowledge"]["fallback_used"])

                mailbird_settings = _load_default_mailbird_settings_cached()
                if mailbird_settings:
                    grounding_data["mailbird_settings"] = mailbird_settings
                    keys_preview = ", ".join(list(mailbird_settings.keys())[:5]) if isinstance(mailbird_settings, dict) else ""
                    addition = "- Mailbird Windows settings available"
                    if keys_preview:
                        addition += f" (keys: {keys_preview})"
                    digest_prefix = grounding_data.get("digest", "")
                    grounding_data["digest"] = f"{digest_prefix}\n{addition}".strip()
                    grounding_data["mailbird_settings_loaded"] = True
                else:
                    grounding_data["mailbird_settings_loaded"] = False

                kb_summary_obj = grounding_data.get("kb", {}).get("summary")
                kb_summary = kb_summary_obj.model_dump() if kb_summary_obj else {}

                parent_span.set_attribute("grounding.kb_results", kb_summary.get("total_results", 0))
                parent_span.set_attribute("grounding.avg_relevance", kb_summary.get("avg_relevance", 0.0))
                parent_span.set_attribute("grounding.used_tavily", grounding_data.get("used_tavily", False))
                parent_span.set_attribute("grounding.mailbird_settings", grounding_data.get("mailbird_settings_loaded", False))

                logger.info(
                    "Grounding summary: kb_results=%s avg_relevance=%.2f used_tavily=%s satisfied=%s",
                    kb_summary.get("total_results", 0),
                    kb_summary.get("avg_relevance", 0.0),
                    grounding_data.get("used_tavily", False),
                    grounding_data.get("kb", {}).get("satisfied", False),
                )

                # Safe Fallback gating: if evidence insufficient and no Tavily results, or billing intent with no solid KB
                try:
                    kb_ok = bool(grounding_data.get("kb", {}).get("satisfied", False))
                    tavily_count = len(grounding_data.get("tavily_items") or [])
                    no_evidence = (not kb_ok) and tavily_count == 0
                    ql = (user_query or "").lower()
                    billing_terms = ["billing", "refund", "renew", "subscription", "charge", "invoice", "license", "payment"]
                    billing_intent = any(t in ql for t in billing_terms)
                    need_safe_fallback = no_evidence or (billing_intent and not kb_ok)
                except Exception:
                    need_safe_fallback = False

                if need_safe_fallback:
                    parent_span.set_attribute("grounding.safe_fallback", True)
                    parent_span.set_attribute("grounding.safe_fallback_reason", "billing_no_evidence" if billing_intent and not kb_ok else "no_evidence")
                    safe_text = (
                        "Thanks for reaching out — I want to make sure we handle this correctly. "
                        "I don’t have enough verified evidence to confirm account or billing details here. "
                        "For secure help from our Billing team, please share:\n"
                        "• Your order ID (from your purchase receipt)\n"
                        "• The email address used to buy the license\n\n"
                        "Please don’t post any full payment details. Once I have those, I’ll route this to Billing or guide you to the right next step."
                    )
                    # Return safe fallback as final assistant message with metadata
                    metadata_snapshot = {
                        "grounding": {
                            "kbResults": kb_summary.get("total_results", 0),
                            "avgRelevance": kb_summary.get("avg_relevance", 0.0),
                            "usedTavily": grounding_data.get("used_tavily", False),
                            "fallbackUsed": bool(kb_summary.get("fallback_used", False)),
                            "mailbirdSettingsLoaded": grounding_data.get("mailbird_settings_loaded", False),
                        },
                        "safeFallback": True,
                    }
                    msg = AIMessage(content=safe_text, additional_kwargs={"messageMetadata": metadata_snapshot})
                    return {"messages": state.messages + [msg]}
            else:
                parent_span.set_attribute("grounding.kb_results", 0)
                parent_span.set_attribute("grounding.avg_relevance", 0.0)
                parent_span.set_attribute("grounding.used_tavily", False)
                parent_span.set_attribute("grounding.mailbird_settings", False)

            # Determine provider/model with request override via state
            # Prefer provider/model from state if available; otherwise use env/settings defaults
            state_provider = getattr(state, "provider", None)
            state_model = getattr(state, "model", None)

            provider = (state_provider or os.getenv("PRIMARY_AGENT_PROVIDER") or getattr(settings, "primary_agent_provider", "google")).lower()
            model_name = (state_model or getattr(settings, "primary_agent_model", "gemini-2.5-flash"))
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

            try:
                query_hash = hashlib.sha256(user_query.encode("utf-8")).hexdigest()
                parent_span.set_attribute("input.query_hash", query_hash)
            except Exception:  # pragma: no cover - hashing failure should not break flow
                parent_span.set_attribute("input.query_present", bool(user_query))
            parent_span.set_attribute("state.message_count", len(state.messages))

            # Initialize reasoning engine with self-critique enabled
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
                context={
                    "messages": state.messages,
                    "grounding": grounding_data,
                },
                session_id=getattr(state, 'session_id', 'default')
            )
            
            final_response: Optional[str] = None
            if reasoning_state and reasoning_state.query_analysis:
                try:
                    final_response = await reasoning_engine.generate_enhanced_response(
                        reasoning_state,
                    )
                except Exception as gen_exc:
                    logger.exception("Enhanced response generation failed: %s", gen_exc)
                    final_response = None

                if final_response:
                    try:
                        refined_response = await reasoning_engine.refine_response_if_needed(reasoning_state)
                        if refined_response:
                            final_response = refined_response
                    except Exception as refine_exc:
                        logger.warning("Refine response step failed: %s", refine_exc)

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
                fallback_text = (
                    "I'm sorry, I wasn't able to generate a response right now. "
                    "This can happen when the upstream model is unreachable in the current environment. "
                    "Please try again after verifying network access and API connectivity."
                )
                return {"messages": state.messages + [AIMessage(content=fallback_text)]}

            logger.info(
                "[primary_agent] final response len=%d preview=%r",
                len(final_response) if isinstance(final_response, str) else -1,
                final_response[:120] if isinstance(final_response, str) else type(final_response).__name__,
            )

            sanitized_response = sanitize_model_response(final_response)
            if sanitized_response:
                final_response = sanitized_response

            # Generate follow-up questions based on the response
            follow_up_questions = []
            if reasoning_state and reasoning_state.query_analysis:
                from .prompts.response_formatter import ResponseFormatter
                follow_up_questions = ResponseFormatter.generate_follow_up_questions(
                    issue=user_query,
                    emotion=reasoning_state.query_analysis.emotional_state,
                    solution_provided=final_response
                )
            # Prepare metadata (thinking trace, follow-ups, tool decisions) for message
            metadata_to_send = {}

            if grounding_data:
                summary_dict = kb_summary if 'kb_summary' in locals() else {}
                metadata_to_send["grounding"] = {
                    "kbResults": summary_dict.get("total_results", 0),
                    "avgRelevance": summary_dict.get("avg_relevance", 0.0),
                    "usedTavily": grounding_data.get("used_tavily", False),
                    "fallbackUsed": bool(summary_dict.get("fallback_used", False)),
                    "mailbirdSettingsLoaded": grounding_data.get("mailbird_settings_loaded", False),
                }
                # Emit a tool step when user forced web search
                if grounding_data.get("forced_websearch"):
                    try:
                        tav_count = len(grounding_data.get("tavily_items") or [])
                        metadata_to_send["toolResults"] = {
                            "id": "web_search",
                            "name": "tavily_web_search",
                            "summary": f"Fetched {tav_count} web results",
                            "reasoning": "Web search executed (user selected)",
                        }
                    except Exception:
                        pass

            final_text = final_response.strip()
            followup_confidence = getattr(reasoning_state, "overall_confidence", 0.0) if reasoning_state else 0.0
            if (
                follow_up_questions
                and len(final_text) >= 200
                and followup_confidence >= 0.6
                and not final_text.endswith("?")
            ):
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

            grounding_structured = None
            if "grounding" in metadata_to_send:
                grounding_raw = metadata_to_send.get("grounding") or {}
                grounding_structured = GroundingMetadata(
                    kb_results=int(grounding_raw.get("kbResults", 0) or 0),
                    avg_relevance=float(grounding_raw.get("avgRelevance", 0.0) or 0.0),
                    used_tavily=bool(grounding_raw.get("usedTavily", False)),
                    fallback_used=bool(grounding_raw.get("fallbackUsed", False)),
                    mailbird_settings_loaded=bool(grounding_raw.get("mailbirdSettingsLoaded", False)),
                )

            tool_structured = None
            if "toolResults" in metadata_to_send:
                tool_raw = metadata_to_send.get("toolResults") or {}
                tool_structured = ToolResultMetadata(
                    id=tool_raw.get("id"),
                    name=tool_raw.get("name"),
                    summary=tool_raw.get("summary"),
                    reasoning=tool_raw.get("reasoning"),
                    decision=tool_raw.get("decision"),
                    confidence=tool_raw.get("confidence"),
                    required_information=tool_raw.get("required_information"),
                    knowledge_gaps=tool_raw.get("knowledge_gaps"),
                    expected_sources=tool_raw.get("expected_sources"),
                )

            trace_id = getattr(state, "trace_id", None)
            session_id = getattr(state, "session_id", None)

            if trace_id:
                metadata_to_send.setdefault("traceId", trace_id)
            if session_id:
                metadata_to_send.setdefault("sessionId", session_id)

            structured_payload = PrimaryAgentFinalResponse(
                text=final_response,
                follow_up_questions=metadata_to_send.get("followUpQuestions") or [],
                grounding=grounding_structured,
                tool_results=tool_structured,
                thinking_trace=metadata_to_send.get("thinking_trace"),
            )

            preface_metadata = dict(metadata_to_send)
            preface_metadata["structured"] = structured_payload.model_dump(exclude={"text"})

            metadata_to_send["structured"] = structured_payload.model_dump()

            # Return a single assistant message with final text and metadata
            final_msg = AIMessage(
                content=final_response,
                additional_kwargs={
                    "messageMetadata": metadata_to_send,
                    "metadata_stage": "final_snapshot",
                    "preface": preface_metadata,
                },
            )
            parent_span.set_status(Status(StatusCode.OK))
            return {"messages": state.messages + [final_msg]}

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
            return {"messages": state.messages + [AIMessage(content=error_msg)]}
