from __future__ import annotations

from pathlib import Path
from typing import List, TYPE_CHECKING, Union  # Added Union for flexible message types
from langchain_core.messages import BaseMessage, HumanMessage # Added HumanMessage for clarity
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.settings import settings

if TYPE_CHECKING:
    from app.agents.orchestration.orchestration.state import GraphState # Import Pydantic GraphState
from app.agents.router.router.schemas import RouteQueryWithConf
from app.core.user_context import get_current_user_id

import logging

# Environment variable for the API key
GEMINI_API_KEY = settings.gemini_api_key

# Define the path to the prompt file
PROMPT_FILE_PATH = Path(__file__).parent / "prompts" / "router_prompt.md"

# Load the prompt from the external file
try:
    router_prompt_template_str = PROMPT_FILE_PATH.read_text()
    # Ensure valid template format
    router_prompt = ChatPromptTemplate.from_template(router_prompt_template_str, template_format="f-string")
except FileNotFoundError:
    # Fallback or error if prompt file is crucial
    logging.getLogger(__name__).error("Router prompt file not found at %s", PROMPT_FILE_PATH)
    # Using a basic fallback prompt to allow functionality, but this should be addressed.
    router_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a router. Classify the query: {{query}} into primary_agent, log_analyst, or researcher."),
        ("user", "{query}")
    ])

logger = logging.getLogger(__name__)

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

async def query_router(state: 'GraphState' | dict) -> Union[dict, str]:
    """
    Routes the query to the appropriate agent based on LLM classification.
    Updates the 'destination' field in the GraphState.
    """
    logger.debug("routing_query_start")

    # Support both GraphState objects and simple dicts for easier unit testing
    if isinstance(state, dict):
        messages = state.get("messages", [])
    else:
        messages = state.messages  # type: ignore[attr-defined]

    user_query = get_user_query(messages) # Access messages from Pydantic state

    if not user_query:
        logger.error("routing_error_no_user_query")
        # Default routing or error handling if query is missing
        return {"destination": "__end__"} # Or perhaps a default agent

    # Resolve user ID from context or settings fallback
    user_id = get_current_user_id() or settings.development_user_id

    # Get user-specific Gemini API key, fallback to env var
    from app.api_keys.supabase_service import get_api_key_service
    api_key_service = get_api_key_service()
    gemini_api_key = await api_key_service.get_decrypted_api_key(
        user_id=user_id,
        api_key_type="gemini",
        fallback_env_var="GEMINI_API_KEY"
    )
    
    if not gemini_api_key:
        logger.error("No Gemini API key available for user")
        return {"destination": "__end__"}
    
    llm = ChatGoogleGenerativeAI(
        model="google/gemma-2b-it",
        temperature=0,
        google_api_key=gemini_api_key
    )
    
    # Use with_structured_output with the RouteQuery schema
    # The prompt (from router_prompt.md) is designed to guide the LLM
    # to output one of the categories defined in RouteQuery.
    structured_llm = llm.with_structured_output(RouteQueryWithConf)

    # Prepare the prompt with the user query
    prompt_input = {"query": user_query}

    try:
        # Create a chain that pipes the prompt to the LLM
        chain = router_prompt | structured_llm

        # Invoke the LLM to get the routing decision
        routing_decision = await chain.ainvoke(prompt_input)
        destination = routing_decision.destination
        confidence = routing_decision.confidence
        logger.info("Router decision: dest=%s confidence=%.2f", destination, confidence)

        # Apply threshold fallback
        CONF_THRESHOLD = settings.router_conf_threshold
        if confidence < CONF_THRESHOLD:
            logger.warning(
                "Low confidence (%.2f < %.2f). Falling back to primary_agent", confidence, CONF_THRESHOLD
            )
            destination = "primary_agent"
        logger.info("routing_to=%s", destination)
    except Exception as e:
        logger.exception("Routing LLM error: %s", e)
        # Fallback routing in case of LLM error
        destination = "primary_agent" # Or '__end__' or a specific error handling agent
        logger.info("routing_fallback_to=%s", destination)

    return {"destination": destination}
