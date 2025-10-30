import hashlib
import json
import logging
import os
import anyio
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
from typing import Dict, Optional, Any, List
from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.messages.tool import ToolCall
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
from app.agents.primary.primary_agent.reasoning.schemas import ToolDecisionType
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


def _extract_text_from_message_content(content: Any) -> str:
    """Best-effort extraction of textual content from a HumanMessage payload."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text" and isinstance(part.get("text"), str):
                    return str(part.get("text"))
                if "content" in part and isinstance(part["content"], str):
                    return part["content"]
        return ""
    return str(content or "")


def _augment_with_image_attachments(content: Any, attachments: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Return an updated multimodal payload when image attachments are present."""
    if not attachments:
        return None

    MAX_ATTACHMENTS = 4
    MAX_DATA_URL_SIZE = 5 * 1024 * 1024  # 5MB per image
    ALLOWED_PREFIXES = ("image/",)
    image_parts: List[Dict[str, Any]] = []
    for attachment in attachments[:MAX_ATTACHMENTS]:
        if not isinstance(attachment, dict):
            continue
        media_type = str(attachment.get("media_type") or "").lower()
        if not media_type.startswith(ALLOWED_PREFIXES):
            continue
        data_url = str(attachment.get("data_url") or "")
        if not data_url.startswith("data:"):
            continue
        if len(data_url) > MAX_DATA_URL_SIZE:
            logger.warning(f"Skipping oversized image attachment: {len(data_url)} bytes")
            continue
        image_parts.append({"type": "image_url", "image_url": {"url": data_url}})

    if not image_parts:
        return None

    # Avoid duplicating images if they are already present in the payload.
    if isinstance(content, list):
        if any(isinstance(part, dict) and part.get("type") == "image_url" for part in content):
            return None
        return [*content, *image_parts]

    base_text = _extract_text_from_message_content(content)
    return [{"type": "text", "text": base_text}, *image_parts]


def _find_last_human_message_index(messages: List[Any]) -> tuple[Optional[int], Optional[HumanMessage]]:
    """Return the index and value of the last HumanMessage in the list."""
    for idx in range(len(messages) - 1, -1, -1):
        message = messages[idx]
        if isinstance(message, HumanMessage):
            return idx, message
    return None, None


def _extract_trailing_tool_messages(messages: List[Any]) -> tuple[Optional[AIMessage], List[ToolMessage]]:
    """Collect trailing ToolMessage objects and their originating AIMessage if present."""
    tool_messages: List[ToolMessage] = []
    tool_invocation: Optional[AIMessage] = None
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            tool_messages.insert(0, message)
            continue
        if isinstance(message, AIMessage) and message.tool_calls:
            if tool_messages:
                tool_invocation = message
                continue
        break
    return tool_invocation, tool_messages


def _parse_tool_message_content(content: Any) -> Optional[Dict[str, Any]]:
    """Convert tool message content to a dictionary when possible."""
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.debug("Unable to decode tool message content as JSON")
            return None
    return None


def _grounding_from_tool_results(
    tool_messages: List[ToolMessage],
    *,
    query: str,
    min_results: int,
    min_relevance: float,
    force_websearch: bool,
) -> Optional[Dict[str, Any]]:
    """Translate ToolNode outputs into the grounding structure expected downstream."""
    if not tool_messages:
        return None

    kb_payload_raw: Optional[Dict[str, Any]] = None
    tavily_payload: Optional[Dict[str, Any]] = None

    for message in tool_messages:
        name = (message.name or "").strip()
        if name == "mailbird-kb-search":
            kb_payload_raw = _parse_tool_message_content(message.content)
        elif name == "tavily_web_search":
            tavily_payload = _parse_tool_message_content(message.content)

    if kb_payload_raw is None and tavily_payload is None:
        return None

    summary_obj: Optional[SearchResultSummary] = None
    kb_results: List[Dict[str, Any]] = []
    if kb_payload_raw:
        summary_raw = kb_payload_raw.get("summary")
        if isinstance(summary_raw, SearchResultSummary):
            summary_obj = summary_raw
        elif isinstance(summary_raw, dict):
            try:
                summary_obj = SearchResultSummary.model_validate(summary_raw)
            except Exception as exc:
                logger.debug("Failed to parse KB summary from tool output: %s", exc)
                summary_obj = None
        kb_results = list(kb_payload_raw.get("results") or [])

    kb_items = summarize_kb_results(kb_results) if kb_results else []
    kb_satisfied = False
    if summary_obj:
        try:
            kb_satisfied = kb_retrieval_satisfied(
                summary_obj,
                min_results=min_results,
                min_relevance=min_relevance,
            )
        except Exception as exc:
            logger.debug("kb_retrieval_satisfied failed for tool output: %s", exc)

    tavily_results = (tavily_payload or {}).get("results") or []
    tavily_items = summarize_tavily_results(tavily_results) if tavily_results else []
    digest = build_grounding_digest(kb_items, tavily_items)

    kb_payload_structured: Dict[str, Any] = {"results": []}
    if kb_payload_raw:
        kb_payload_structured = dict(kb_payload_raw)
    if summary_obj:
        kb_payload_structured["summary"] = summary_obj
    elif "summary" not in kb_payload_structured:
        kb_payload_structured["summary"] = None

    kb_payload_structured.setdefault("query", query)

    return {
        "kb": {
            "payload": kb_payload_structured,
            "items": kb_items,
            "summary": summary_obj,
            "satisfied": kb_satisfied,
        },
        "tavily": tavily_payload,
        "tavily_items": tavily_items,
        "used_tavily": bool(tavily_payload),
        "forced_websearch": bool(force_websearch),
        "digest": digest,
    }


def _build_tool_calls_for_decision(
    decision: ToolDecisionType,
    *,
    user_query: str,
    force_websearch: bool,
    context: Dict[str, Any],
    websearch_max_results: Optional[int],
    enable_websearch: bool,
) -> List[ToolCall]:
    """Create ToolCall payloads for the requested decision."""
    if not user_query or not user_query.strip():
        return []

    tool_calls: List[ToolCall] = []
    kb_required = decision in {
        ToolDecisionType.INTERNAL_KB_ONLY,
        ToolDecisionType.BOTH_SOURCES_NEEDED,
    }
    web_required = decision in {
        ToolDecisionType.WEB_SEARCH_REQUIRED,
        ToolDecisionType.BOTH_SOURCES_NEEDED,
    }

    if kb_required:
        kb_args = {
            "query": user_query,
            "context": context,
            "max_results": 6,
            "search_sources": ["knowledge_base", "feedme"],
        }
        tool_calls.append(
            ToolCall(
                name="mailbird-kb-search",
                args=kb_args,
                id=f"kb_{uuid4().hex}",
            )
        )

    if force_websearch:
        web_required = True

    if web_required and (enable_websearch or force_websearch):
        try:
            max_results = int(websearch_max_results) if websearch_max_results is not None else 5
        except Exception:
            max_results = 5
        if max_results <= 0:
            max_results = 5
        web_args = {
            "search_input": {
                "query": user_query,
                "max_results": max_results,
            }
        }
        tool_calls.append(
            ToolCall(
                name="tavily_web_search",
                args=web_args,
                id=f"web_{uuid4().hex}",
            )
        )

    return tool_calls


def _prepare_grounding_metadata(
    grounding_data: Dict[str, Any],
    *,
    state: PrimaryAgentState,
    user_query: str,
    parent_span,
) -> tuple[Optional[SearchResultSummary], Dict[str, Any], bool, Optional[str]]:
    """Enrich grounding metadata with global context, settings, and fallback detection."""
    if not grounding_data:
        return None, {}, False, None

    kb_section = grounding_data.get("kb") or {}
    summary_obj: Optional[SearchResultSummary] = None
    summary_raw = kb_section.get("summary")
    if isinstance(summary_raw, SearchResultSummary):
        summary_obj = summary_raw
    elif isinstance(summary_raw, dict):
        try:
            summary_obj = SearchResultSummary.model_validate(summary_raw)
            kb_section["summary"] = summary_obj
        except Exception as exc:
            logger.debug("Unable to coerce KB summary from grounding data: %s", exc)
            summary_obj = None
    if summary_obj is not None:
        kb_summary = summary_obj.model_dump()
    else:
        kb_summary = {}

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
        try:
            parent_span.set_attribute("global_knowledge.hits", grounding_data["global_knowledge"]["hits"])
            if grounding_data["global_knowledge"]["source"]:
                parent_span.set_attribute("global_knowledge.source", grounding_data["global_knowledge"]["source"])
            parent_span.set_attribute("global_knowledge.fallback", grounding_data["global_knowledge"]["fallback_used"])
        except Exception:
            pass

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
        grounding_data["mailbird_settings_loaded"] = grounding_data.get("mailbird_settings_loaded", False)

    if summary_obj is None:
        # Ensure consistent structure to avoid KeyError downstream
        kb_section["summary"] = summary_obj
    grounding_data.setdefault("kb", kb_section)
    grounding_data.setdefault("used_tavily", bool(grounding_data.get("tavily")))

    try:
        parent_span.set_attribute("grounding.kb_results", kb_summary.get("total_results", 0))
        parent_span.set_attribute("grounding.avg_relevance", kb_summary.get("avg_relevance", 0.0))
        parent_span.set_attribute("grounding.used_tavily", grounding_data.get("used_tavily", False))
        parent_span.set_attribute("grounding.mailbird_settings", grounding_data.get("mailbird_settings_loaded", False))
    except Exception:
        pass

    logger.info(
        "Grounding summary: kb_results=%s avg_relevance=%.2f used_tavily=%s satisfied=%s",
        kb_summary.get("total_results", 0),
        kb_summary.get("avg_relevance", 0.0),
        grounding_data.get("used_tavily", False),
        kb_section.get("satisfied", False),
    )

    try:
        kb_ok = bool(kb_section.get("satisfied", False))
        tavily_count = len(grounding_data.get("tavily_items") or [])
        no_evidence = (not kb_ok) and tavily_count == 0
        ql = (user_query or "").lower()
        billing_terms = [
            "billing",
            "refund",
            "renew",
            "subscription",
            "charge",
            "invoice",
            "license",
            "payment",
        ]
        billing_intent = any(term in ql for term in billing_terms)
        need_safe_fallback = no_evidence or (billing_intent and not kb_ok)
        if need_safe_fallback:
            fallback_reason = "billing_no_evidence" if billing_intent and not kb_ok else "no_evidence"
        else:
            fallback_reason = None
    except Exception:
        need_safe_fallback = False
        fallback_reason = None

    return summary_obj, kb_summary, need_safe_fallback, fallback_reason


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

def create_user_specific_model(
    api_key: str,
    *,
    thinking_budget: Optional[int] = None,
    bind_tools: bool = True,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    max_output_tokens: Optional[int] = None,
) -> ChatGoogleGenerativeAI:
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
    
    # Check cache first (using a deterministic hash of the API key for security)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    cache_key = (
        f"{api_key_hash}_{_get_model_config()}_{thinking_budget}_{bind_tools}_"
        f"{temperature}_{top_p}_{top_k}_{max_output_tokens}"
    )
    if cache_key in _model_cache:
        logger.debug(f"Returning cached model for user with thinking_budget: {thinking_budget}, bind_tools: {bind_tools}")
        return _model_cache[cache_key]
    
    try:
        model_name = _get_model_config()
        logger.info(
            "Creating new user-specific model with %s, thinking_budget=%s, temperature=%s, top_p=%s, top_k=%s, max_output_tokens=%s",
            model_name,
            thinking_budget,
            temperature if temperature is not None else getattr(settings, "primary_agent_temperature", 0.2),
            top_p,
            top_k,
            max_output_tokens,
        )
        
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }
        
        # Create model configuration
        resolved_temperature = (
            temperature if temperature is not None else getattr(settings, "primary_agent_temperature", 0.2)
        )
        model_kwargs = {
            "model": model_name,
            "temperature": resolved_temperature,
            "google_api_key": api_key,
            "safety_settings": safety_settings,
            "convert_system_message_to_human": True
        }
        if top_p is not None:
            model_kwargs["top_p"] = top_p
        if top_k is not None:
            model_kwargs["top_k"] = top_k
        if max_output_tokens is not None:
            model_kwargs["max_output_tokens"] = max_output_tokens
        
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
    Asynchronously processes a user query using the primary agent system and returns
    the updated conversation payload.

    This function orchestrates the reasoning engine to generate a comprehensive,
    self-critiqued answer. It handles input validation, calls the reasoning engine,
    logs telemetry, and packages the final response (including metadata) as an
    assistant message appended to the existing conversation state.

    Parameters:
        state (PrimaryAgentState): The current agent state, including user messages
        and session context.

    Returns:
        Dict[str, Any]: A dictionary containing the updated message history under
        the ``"messages"`` key. The last message is the assistant reply.
    """
    with tracer.start_as_current_span("primary_agent.run") as parent_span:
        try:
            logger.debug("Running primary agent")
            attachments = getattr(state, "attachments", None)
            tool_invocation, tool_messages = _extract_trailing_tool_messages(state.messages)
            has_tool_outputs = bool(tool_messages)

            last_human_index, last_human_message = _find_last_human_message_index(state.messages)
            user_query = ""
            if last_human_message is not None:
                if attachments and last_human_index is not None and last_human_index == len(state.messages) - 1:
                    try:
                        augmented = _augment_with_image_attachments(last_human_message.content, attachments)
                        if augmented is not None:
                            state.messages[last_human_index] = HumanMessage(
                                content=augmented,
                                additional_kwargs=getattr(last_human_message, "additional_kwargs", {}),
                                response_metadata=getattr(last_human_message, "response_metadata", {}),
                                name=getattr(last_human_message, "name", None),
                                id=getattr(last_human_message, "id", None),
                                example=getattr(last_human_message, "example", False),
                            )
                        setattr(state, "attachments", None)
                    except Exception as attachment_exc:  # pragma: no cover - defensive logging
                        logger.warning("attachment_processing_failed", exc_info=attachment_exc)
                user_query = _extract_text_from_message_content(last_human_message.content)
            elif state.messages:
                try:
                    user_query = _extract_text_from_message_content(state.messages[-1].content)
                except Exception:
                    user_query = str(getattr(state.messages[-1], "content", ""))

            # Input Validation: Query length
            MAX_QUERY_LENGTH = 4000
            if len(user_query) > MAX_QUERY_LENGTH:
                parent_span.set_attribute("input.query.error", "Query too long")
                parent_span.set_status(Status(StatusCode.ERROR, "Query too long"))
                logger.warning(
                    "primary_agent_query_too_long session=%s trace=%s length=%s",
                    getattr(state, "session_id", None),
                    getattr(state, "trace_id", None),
                    len(user_query),
                )
                error_payload = {
                    "type": "validation_error",
                    "code": "query_too_long",
                    "message": "Your query is too long. Please shorten it and try again.",
                    "maxLength": MAX_QUERY_LENGTH,
                    "actualLength": len(user_query),
                    "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                }
                error_message = AIMessage(
                    content=error_payload["message"],
                    additional_kwargs={
                        "messageMetadata": {"error": error_payload},
                        "metadata_stage": "final_snapshot",
                    },
                )
                return {
                    "messages": state.messages + [error_message],
                    "metadata": {"error": error_payload},
                }

            grounding_data: Dict[str, Any] = {}
            kb_summary_obj: Optional[SearchResultSummary] = None
            kb_summary: Dict[str, Any] = {}
            force_websearch_flag = bool(getattr(state, "force_websearch", False))
            websearch_max_results = getattr(state, "websearch_max_results", None)
            grounding_context_input: Dict[str, Any] = {
                "session_id": getattr(state, "session_id", "default"),
                "message_count": len(state.messages),
            }

            if has_tool_outputs and tool_messages:
                tool_grounding = _grounding_from_tool_results(
                    tool_messages,
                    query=user_query,
                    min_results=settings.primary_agent_min_kb_results,
                    min_relevance=settings.primary_agent_min_kb_relevance,
                    force_websearch=force_websearch_flag,
                )
                if tool_grounding:
                    grounding_data = tool_grounding.copy()
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
            parent_span.set_attribute("llm.provider", provider)
            parent_span.set_attribute("llm.model", model_name)

            state_temperature = getattr(state, "temperature", None)
            resolved_temperature = (
                state_temperature if state_temperature is not None else getattr(settings, "primary_agent_temperature", 0.2)
            )
            resolved_top_p = getattr(state, "top_p", None)
            resolved_top_k = getattr(state, "top_k", None)
            resolved_max_output_tokens = getattr(state, "max_output_tokens", None)
            state_thinking_budget = getattr(state, "thinking_budget", None)
            resolved_thinking_budget = (
                state_thinking_budget
                if state_thinking_budget is not None
                else getattr(settings, "primary_agent_thinking_budget", None)
            )
            default_formatting = getattr(settings, "primary_agent_formatting", "strict")
            formatting_candidate_obj = getattr(state, "formatting", None) or default_formatting
            if isinstance(formatting_candidate_obj, str):
                formatting_candidate = formatting_candidate_obj.strip().lower() or default_formatting
            else:
                formatting_candidate = default_formatting
            if formatting_candidate not in {"strict", "natural", "lean"}:
                resolved_formatting = default_formatting
            else:
                resolved_formatting = formatting_candidate

            logger.info(
                "[primary_agent] generation_settings temperature=%s top_p=%s top_k=%s max_output_tokens=%s thinking_budget=%s formatting=%s",
                resolved_temperature,
                resolved_top_p,
                resolved_top_k,
                resolved_max_output_tokens,
                resolved_thinking_budget,
                resolved_formatting,
            )
            parent_span.set_attribute("llm.temperature", resolved_temperature)
            if resolved_top_p is not None:
                parent_span.set_attribute("llm.top_p", resolved_top_p)
            if resolved_top_k is not None:
                parent_span.set_attribute("llm.top_k", resolved_top_k)
            if resolved_max_output_tokens is not None:
                parent_span.set_attribute("llm.max_output_tokens", resolved_max_output_tokens)
            if resolved_thinking_budget is not None:
                parent_span.set_attribute("llm.thinking_budget", resolved_thinking_budget)
            parent_span.set_attribute("llm.formatting_mode", resolved_formatting)

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
                    metadata_snapshot = {
                        "error": {
                            "type": "missing_api_key",
                            "provider": "google",
                            "message": error_msg,
                        }
                    }
                    guidance_msg = AIMessage(
                        content=detailed_guidance,
                        additional_kwargs={
                            "messageMetadata": metadata_snapshot,
                            "metadata_stage": "final_snapshot",
                        },
                    )
                    return {"messages": state.messages + [guidance_msg]}

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
                    model_with_tools = create_user_specific_model(
                        selected_key,
                        thinking_budget=resolved_thinking_budget,
                        bind_tools=True,
                        temperature=resolved_temperature,
                        top_p=resolved_top_p,
                        top_k=resolved_top_k,
                        max_output_tokens=resolved_max_output_tokens,
                    )
                except Exception as e:
                    if _is_auth_error(e) and env_key and selected_key != env_key:
                        logger.warning(f"[primary_agent] Gemini auth error with user key, retrying with env key: {e}")
                        model_with_tools = create_user_specific_model(
                            env_key,
                            thinking_budget=resolved_thinking_budget,
                            bind_tools=True,
                            temperature=resolved_temperature,
                            top_p=resolved_top_p,
                            top_k=resolved_top_k,
                            max_output_tokens=resolved_max_output_tokens,
                        )
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
                    metadata_snapshot = {
                        "error": {
                            "type": "missing_api_key",
                            "provider": "openai",
                            "message": error_msg,
                        }
                    }
                    guidance_msg = AIMessage(
                        content="OpenAI API key missing. Please set it in Settings or as OPENAI_API_KEY and try again.",
                        additional_kwargs={
                            "messageMetadata": metadata_snapshot,
                            "metadata_stage": "final_snapshot",
                        },
                    )
                    return {"messages": state.messages + [guidance_msg]}

                # Load model via providers registry (tools binding is optional here)
                logger.debug(f"Loading OpenAI model via providers registry: {model_name}")
                model_with_tools = await get_primary_agent_model(
                    api_key=openai_key,
                    provider="openai",
                    model=model_name,
                    temperature=resolved_temperature,
                    top_p=resolved_top_p,
                    top_k=resolved_top_k,
                    max_output_tokens=resolved_max_output_tokens,
                )

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
                quality_level=getattr(settings, "primary_agent_quality_level", "balanced"),
                thinking_budget_override=resolved_thinking_budget,
                formatting_mode=resolved_formatting,
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

            tool_decision = ToolDecisionType.NO_TOOLS_NEEDED
            if reasoning_state and reasoning_state.tool_reasoning:
                tool_decision = reasoning_state.tool_reasoning.decision_type

            tool_calls: List[ToolCall] = []
            if not has_tool_outputs:
                tool_calls = _build_tool_calls_for_decision(
                    tool_decision,
                    user_query=user_query,
                    force_websearch=force_websearch_flag,
                    context=grounding_context_input,
                    websearch_max_results=websearch_max_results,
                    enable_websearch=getattr(settings, "enable_websearch", False),
                )

            if tool_calls:
                metadata_snapshot = {
                    "reasoning": {
                        "decision": tool_decision.value,
                        "forcedWebsearch": force_websearch_flag,
                    }
                }
                tool_message = AIMessage(
                    content="Retrieving relevant knowledge…",
                    tool_calls=tool_calls,
                    additional_kwargs={
                        "messageMetadata": metadata_snapshot,
                        "metadata_stage": "tool_invocation",
                    },
                )
                return {"messages": state.messages + [tool_message]}

            if not grounding_data and settings.enable_grounded_responses:
                grounding_data = await _gather_grounding_evidence(
                    user_query,
                    context=grounding_context_input,
                    min_results=settings.primary_agent_min_kb_results,
                    min_relevance=settings.primary_agent_min_kb_relevance,
                    force_websearch=force_websearch_flag,
                    websearch_max_results=websearch_max_results,
                )

            if grounding_data:
                kb_summary_obj, kb_summary, need_safe_fallback, fallback_reason = _prepare_grounding_metadata(
                    grounding_data,
                    state=state,
                    user_query=user_query,
                    parent_span=parent_span,
                )
                if need_safe_fallback:
                    parent_span.set_attribute("grounding.safe_fallback", True)
                    if fallback_reason:
                        parent_span.set_attribute("grounding.safe_fallback_reason", fallback_reason)
                    safe_text = (
                        "Thanks for reaching out — I want to make sure we handle this correctly. "
                        "I don’t have enough verified evidence to confirm account or billing details here. "
                        "For secure help from our Billing team, please share:\n"
                        "• Your order ID (from your purchase receipt)\n"
                        "• The email address used to buy the license\n\n"
                        "Please don’t post any full payment details. Once I have those, I’ll route this to Billing or guide you to the right next step."
                    )
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
                kb_summary_obj = None
                kb_summary = {}

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
                error_payload = {
                    "type": "fallback_error",
                    "code": "final_response_missing",
                    "message": fallback_text,
                    "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "severity": "error",
                    "source": "primary_agent",
                }
                fallback_message = AIMessage(
                    content=fallback_text,
                    additional_kwargs={
                        "messageMetadata": {"error": error_payload},
                        "metadata_stage": "final_snapshot",
                    },
                )
                return {
                    "messages": state.messages + [fallback_message],
                    "metadata": {"error": error_payload},
                }

            logger.info(
                "[primary_agent] final response len=%d preview=%r",
                len(final_response) if isinstance(final_response, str) else -1,
                final_response[:120] if isinstance(final_response, str) else type(final_response).__name__,
            )

            sanitized_response = sanitize_model_response(final_response)
            if sanitized_response:
                final_response = sanitized_response

            # Prepare metadata (thinking trace, follow-ups, tool decisions) for message
            metadata_to_send = {}

            if grounding_data:
                summary_dict = kb_summary
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

            if reasoning_state and reasoning_state.tool_reasoning:
                tool_reasoning = reasoning_state.tool_reasoning
                tool_metadata = metadata_to_send.get("toolResults", {})
                tool_metadata.update(
                    {
                        "decision": tool_reasoning.decision_type.value,
                        "reasoning": tool_reasoning.reasoning,
                        "confidence": tool_reasoning.confidence,
                        "required_information": tool_reasoning.required_information,
                        "knowledge_gaps": tool_reasoning.knowledge_gaps,
                        "expected_sources": tool_reasoning.expected_sources,
                    }
                )
                if tool_invocation:
                    tool_metadata.setdefault("invocationId", tool_invocation.id)
                metadata_to_send["toolResults"] = tool_metadata

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
