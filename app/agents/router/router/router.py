from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, TYPE_CHECKING, Union

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.core.logging_config import get_logger
from app.core.rate_limiting.agent_wrapper import get_rate_limiter
from app.core.settings import settings
from app.providers.adapters import load_model
from app.core.rate_limiting.budget_limiter import enforce_budget

if TYPE_CHECKING:
    from app.agents.orchestration.orchestration.state import GraphState

from app.agents.router.router.schemas import RouteQueryWithConf
from app.core.user_context import get_current_user_id

# Define the path to the prompt file
PROMPT_FILE_PATH = Path(__file__).parent / "prompts" / "router_prompt.md"

# Load the prompt from the external file
try:
    router_prompt_template_str = PROMPT_FILE_PATH.read_text()
    # Ensure valid template format
    router_prompt = ChatPromptTemplate.from_template(router_prompt_template_str, template_format="f-string")
except FileNotFoundError:
    # Fallback or error if prompt file is crucial
    get_logger(__name__).error("router_prompt_missing", path=str(PROMPT_FILE_PATH))
    # Using a basic fallback prompt to allow functionality, but this should be addressed.
    router_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a router. Classify the query: {{query}} into primary_agent, log_analyst, or researcher."),
        ("user", "{query}")
    ])

tracer = trace.get_tracer(__name__)
logger = get_logger(__name__)

def get_user_query(messages: List[Union[BaseMessage, tuple, list, dict]]) -> str:
    """
    Extracts the content of the last human message.
    Assumes messages are ordered and the last one is typically the user's query.
    """
    if not messages:
        return ""
    # Iterate backwards to find the last HumanMessage or a `(user, "text")` tuple/list.
    for message in reversed(messages):
        # Standard LangChain message object
        if isinstance(message, HumanMessage):
            return str(message.content)

        # Handle minimal tuple / list representations frequently used in tests
        # e.g. ("user", "What is Mailbird?")
        if isinstance(message, (tuple, list)) and len(message) >= 2 and message[0] == "user":
            return str(message[1])

        # Handle dict representation {"role": "user", "content": "..."}
        if isinstance(message, dict) and message.get("role") == "user":
            return str(message.get("content", ""))

    # Fallback for unsupported structures
    try:
        if hasattr(messages[-1], "content") and messages[-1].content:
            return str(messages[-1].content)
    except Exception:
        pass
    return ""


def _get_state_attr(state: "GraphState" | dict, key: str, default: str | None = None):
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)

async def query_router(state: 'GraphState' | dict) -> Union[dict, str]:
    """
    Routes the query to the appropriate agent based on LLM classification.
    Updates the 'destination' field in the GraphState.
    """
    session_id = _get_state_attr(state, "session_id")
    trace_id = _get_state_attr(state, "trace_id")
    bound_logger = logger.bind(session_id=session_id, trace_id=trace_id)

    bound_logger.debug("routing_query_start")

    # --------------------------------------------------------------
    # Phase 5: Respect explicit agent selection via state.agent_type
    # If a valid agent_type is provided, short-circuit LLM routing.
    # Accepted values map to router destinations as below.
    # --------------------------------------------------------------
    try:
        AGENT_TYPE_TO_DEST = {
            "primary": "primary_agent",
            "primary_agent": "primary_agent",
            "log_analysis": "log_analyst",
            "log_analyst": "log_analyst",
            "research": "researcher",
            "researcher": "researcher",
        }
        agent_type = _get_state_attr(state, "agent_type")
        if isinstance(agent_type, str):
            norm = agent_type.strip().lower()
            if norm in AGENT_TYPE_TO_DEST:
                dest = AGENT_TYPE_TO_DEST[norm]
                bound_logger.info("router_explicit_selection", agent_type=norm, destination=dest)
                return {"destination": dest}
    except Exception:
        # Defensive: ignore mapping errors and continue with normal routing
        pass

    # Support both GraphState objects and simple dicts for easier unit testing
    if isinstance(state, dict):
        messages = state.get("messages", [])
    else:
        messages = state.messages  # type: ignore[attr-defined]

    user_query = get_user_query(messages)

    node_timeout = getattr(settings, "node_timeout_sec", 30.0)

    with tracer.start_as_current_span("router.route") as span:
        if session_id:
            span.set_attribute("router.session_id", session_id)
        if trace_id:
            span.set_attribute("router.trace_id", trace_id)

        if not user_query:
            bound_logger.error("routing_error_no_user_query")
            span.set_status(Status(StatusCode.ERROR, "missing_user_query"))
            span.set_attribute("router.destination", "__end__")
            return {"destination": "__end__"}

        # Resolve user ID from context or settings fallback
        user_id = get_current_user_id() or settings.development_user_id
        span.set_attribute("router.user_id_fallback", bool(user_id == settings.development_user_id))

        if not await enforce_budget(
            "router",
            user_id,
            limit=settings.router_daily_budget,
        ):
            bound_logger.warning("router_budget_exhausted", user_id=user_id)
            span.set_status(Status(StatusCode.ERROR, "router_budget_exhausted"))
            span.set_attribute("router.destination", "primary_agent")
            return {"destination": "primary_agent"}

        # Get user-specific Gemini API key, fallback to env var
        from app.api_keys.supabase_service import get_api_key_service

        api_key_service = get_api_key_service()
        gemini_api_key = await api_key_service.get_decrypted_api_key(
            user_id=user_id,
            api_key_type="gemini",
            fallback_env_var="GEMINI_API_KEY",
        )

        if not gemini_api_key:
            bound_logger.error("router_missing_api_key", user_id=user_id)
            span.set_status(Status(StatusCode.ERROR, "missing_api_key"))
            span.set_attribute("router.destination", "__end__")
            return {"destination": "__end__"}

        model_name = (settings.router_model or "gemini-2.5-flash-lite").lower()
        span.set_attribute("router.model", model_name)

        try:
            llm = await load_model("google", model_name, api_key=gemini_api_key, temperature=0.0)
        except Exception as exc:  # pragma: no cover - defensive
            bound_logger.exception("router_model_load_failed", model=model_name)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, "model_load_failed"))
            span.set_attribute("router.destination", "primary_agent")
            return {"destination": "primary_agent"}

        structured_llm = llm.with_structured_output(RouteQueryWithConf)
        chain = router_prompt | structured_llm
        prompt_input = {"query": user_query}

        rate_limiter = get_rate_limiter()

        try:
            routing_decision = await asyncio.wait_for(
                rate_limiter.execute_with_protection(model_name, chain.ainvoke, prompt_input),
                timeout=node_timeout,
            )
        except asyncio.TimeoutError as exc:
            bound_logger.warning("router_timeout", timeout=node_timeout)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, "router_timeout"))
            span.set_attribute("router.destination", "primary_agent")
            return {"destination": "primary_agent"}
        except Exception as exc:  # pragma: no cover - fallthrough
            bound_logger.exception("router_llm_error", model=model_name)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, "router_llm_error"))
            span.set_attribute("router.destination", "primary_agent")
            return {"destination": "primary_agent"}

        destination = routing_decision.destination
        confidence = float(routing_decision.confidence)
        span.set_attribute("router.confidence", confidence)
        span.set_attribute("router.destination", destination)
        bound_logger.info("router_decision", destination=destination, confidence=confidence)

        threshold = settings.router_conf_threshold
        if confidence < threshold:
            bound_logger.warning(
                "router_low_confidence",
                confidence=confidence,
                threshold=threshold,
                fallback="primary_agent",
            )
            destination = "primary_agent"
            span.set_attribute("router.fallback_triggered", True)
        else:
            span.set_attribute("router.fallback_triggered", False)

        span.set_attribute("router.destination", destination)
        span.set_status(Status(StatusCode.OK))

        return {"destination": destination}
