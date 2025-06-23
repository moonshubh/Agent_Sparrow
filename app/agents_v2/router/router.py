from __future__ import annotations
import os
from pathlib import Path
from typing import List, TYPE_CHECKING, Union  # Added Union for flexible message types
from langchain_core.messages import BaseMessage, HumanMessage # Added HumanMessage for clarity
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

if TYPE_CHECKING:
    from app.agents_v2.orchestration.state import GraphState # Import Pydantic GraphState
from app.agents_v2.router.schemas import RouteQueryWithConf

import logging

# Environment variable for the API key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Define the path to the prompt file
PROMPT_FILE_PATH = Path(__file__).parent / "prompts" / "router_prompt.md"

# Load the prompt from the external file
try:
    router_prompt_template_str = PROMPT_FILE_PATH.read_text()
    # Ensure valid template format
    router_prompt = ChatPromptTemplate.from_template(router_prompt_template_str, template_format="f-string")
except FileNotFoundError:
    # Fallback or error if prompt file is crucial
    print(f"ERROR: Router prompt file not found at {PROMPT_FILE_PATH}")
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

def query_router(state: 'GraphState' | dict) -> Union[dict, str]:
    """
    Routes the query to the appropriate agent based on LLM classification.
    Updates the 'destination' field in the GraphState.
    """
    print("---ROUTING QUERY---")

    # Support both GraphState objects and simple dicts for easier unit testing
    if isinstance(state, dict):
        messages = state.get("messages", [])
    else:
        messages = state.messages  # type: ignore[attr-defined]

    user_query = get_user_query(messages) # Access messages from Pydantic state

    if not user_query:
        print("---ROUTING ERROR: No user query found in state.messages---")
        # Default routing or error handling if query is missing
        return {"destination": "__end__"} # Or perhaps a default agent

    # Initialize the LLM, ensuring API key is passed
    # (Referencing MEMORY[213594e5-5a73-46c2-8086-b357bed82737])
    if not GEMINI_API_KEY:
        # This is a critical error, should be handled appropriately
        # For now, printing error and attempting to proceed without API key (will likely fail)
        print("CRITICAL ERROR: GEMINI_API_KEY not found in environment.")
        # Potentially raise an exception or route to an error handling node
    
    llm = ChatGoogleGenerativeAI(
        model="google/gemma-2b-it", # Model specified in task details
        temperature=0,
        google_api_key=GEMINI_API_KEY # Explicitly passing API key
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
        routing_decision = chain.invoke(prompt_input)
        destination = routing_decision.destination
        confidence = routing_decision.confidence
        logger.info("Router decision: dest=%s confidence=%.2f", destination, confidence)

        # Apply threshold fallback
        CONF_THRESHOLD = float(os.getenv("ROUTER_CONF_THRESHOLD", "0.6"))
        if confidence < CONF_THRESHOLD:
            logger.warning(
                "Low confidence (%.2f < %.2f). Falling back to primary_agent", confidence, CONF_THRESHOLD
            )
            destination = "primary_agent"
        print(f"---ROUTING TO: {destination}---")
    except Exception as e:
        logger.exception("Routing LLM error: %s", e)
        # Fallback routing in case of LLM error
        destination = "primary_agent" # Or '__end__' or a specific error handling agent
        print(f"---FALLBACK ROUTING TO: {destination}---")

    return {"destination": destination}