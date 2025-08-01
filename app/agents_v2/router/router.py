from __future__ import annotations

from pathlib import Path
from typing import List, TYPE_CHECKING, Union, Optional  # Added Union for flexible message types
from langchain_core.messages import BaseMessage, HumanMessage # Added HumanMessage for clarity
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
import asyncio
import re

from app.core.settings import settings
from app.agents_v2.router.patterns import get_pattern_matcher
from app.core.rate_limiting.budget_manager import BudgetManager
from app.agents_v2.router.routing_config import RouterPatterns, ComplexityPatterns, DEFAULT_ROUTER_CONFIG

if TYPE_CHECKING:
    from app.agents_v2.orchestration.state import GraphState # Import Pydantic GraphState
from app.agents_v2.router.schemas import RouteQueryWithConf

import logging

# Environment variable for the API key
GEMINI_API_KEY = settings.gemini_api_key

# Define the path to the prompt file
PROMPT_FILE_PATH = Path(__file__).parent / "prompts" / "router_prompt.md"

# Load the prompt from the external file
try:
    router_prompt_template_str = PROMPT_FILE_PATH.read_text()
    # Ensure valid template format
    router_prompt = ChatPromptTemplate.from_template(router_prompt_template_str)
except FileNotFoundError:
    # Fallback or error if prompt file is crucial
    print(f"ERROR: Router prompt file not found at {PROMPT_FILE_PATH}")
    # Using a basic fallback prompt to allow functionality, but this should be addressed.
    router_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a router. Classify the query: {{query}} into primary_agent, log_analyst, or researcher."),
        ("user", "{query}")
    ])

logger = logging.getLogger(__name__)

def _smart_bypass_router(query: str, compiled_patterns=None) -> str | None:
    """
    Smart router bypass for obvious queries to reduce LLM calls using regex patterns.
    
    Args:
        query: User query to analyze
        compiled_patterns: Pre-compiled regex patterns for efficiency
    
    Returns:
        str: Direct destination if obvious pattern detected, None otherwise
    """
    if compiled_patterns is None:
        compiled_patterns = RouterPatterns.compile_patterns()
    
    # HIGH PRIORITY: Obvious Mailbird technical issues -> primary_agent
    # These patterns take precedence over log analysis patterns
    for pattern in compiled_patterns['mailbird_technical']:
        if pattern.search(query):
            logger.debug(f"Mailbird technical pattern matched: {pattern.pattern}")
            return "primary_agent"
    
    # Log file keywords -> log_analyst  
    for pattern in compiled_patterns['log']:
        if pattern.search(query):
            logger.debug(f"Log pattern matched: {pattern.pattern}")
            return "log_analyst"
    
    # Research-type queries -> researcher
    for pattern in compiled_patterns['research']:
        if pattern.search(query):
            logger.debug(f"Research pattern matched: {pattern.pattern}")
            return "researcher"
    
    # General Mailbird questions with high confidence -> primary_agent
    if re.search(r'\bmailbird\b', query, re.IGNORECASE):
        for pattern in compiled_patterns['general_mailbird']:
            if pattern.search(query):
                logger.debug(f"General Mailbird pattern matched: {pattern.pattern}")
                return "primary_agent"
    
    return None  # No obvious pattern, use LLM router

def _calculate_query_complexity(query: str) -> float:
    """
    Calculate query complexity score (0.0 to 1.0) using configurable patterns.
    
    Considers:
    - Query length
    - Technical term density
    - Error/log patterns
    - Multiple issues mentioned
    - Complex scenario patterns
    """
    complexity = 0.0
    query_lower = query.lower()
    
    # Length factor (longer queries tend to be more complex)
    word_count = len(query.split())
    if word_count > 50:
        complexity += 0.2
    elif word_count > 20:
        complexity += 0.1
        
    # Technical complexity indicators
    tech_count = sum(1 for term in ComplexityPatterns.TECHNICAL_TERMS if term in query_lower)
    complexity += min(0.3, tech_count * 0.1)
    
    # Error/log pattern complexity
    error_count = sum(1 for pattern in ComplexityPatterns.ERROR_PATTERNS if pattern in query_lower)
    complexity += min(0.2, error_count * 0.1)
    
    # Multiple issues indicator
    if any(indicator in query_lower for indicator in ComplexityPatterns.MULTIPLE_ISSUE_INDICATORS):
        complexity += 0.1
        
    # Specific complex scenarios
    for scenario_name, (primary_term, secondary_terms) in ComplexityPatterns.COMPLEX_SCENARIOS.items():
        if primary_term in query_lower:
            if isinstance(secondary_terms, list):
                if any(term in query_lower for term in secondary_terms):
                    complexity += 0.15 if scenario_name == 'performance_issue' else 0.2
            elif secondary_terms in query_lower:
                complexity += 0.2
        
    return min(1.0, complexity)


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

async def _embedding_route_check(query: str, config: RouterConfig = None) -> Optional[str]:
    """
    Check if query matches pre-computed patterns using embeddings.
    
    Args:
        query: User query to match
        config: Router configuration with thresholds and mappings
    
    Returns:
        str: Destination if match found with high confidence, None otherwise
    """
    if config is None:
        config = DEFAULT_ROUTER_CONFIG
        
    try:
        pattern_matcher = await get_pattern_matcher()
        category, confidence, matched_pattern = await pattern_matcher.match_query(query)
        
        if category and confidence >= config.embedding_confidence_threshold:
            logger.info(f"Embedding match: {category} (confidence: {confidence:.3f}, pattern: {matched_pattern})")
            
            return config.category_mappings.get(category, "primary_agent")
    except Exception as e:
        logger.error(f"Embedding route check failed: {e}")
    
    return None


def query_router(state: 'GraphState' | dict) -> Union[dict, str]:
    """
    Routes the query to the appropriate agent based on:
    1. Smart bypass rules (pattern matching)
    2. Embedding similarity matching 
    3. LLM classification (Gemma-3-IT)
    
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
    
    # Smart bypass: Direct route obvious queries to save LLM calls
    compiled_patterns = RouterPatterns.compile_patterns()
    bypass_destination = _smart_bypass_router(user_query, compiled_patterns)
    if bypass_destination:
        complexity = _calculate_query_complexity(user_query)
        logger.info(f"Smart bypass routing to {bypass_destination} with complexity {complexity:.2f}")
        print(f"---SMART BYPASS TO: {bypass_destination} (saved LLM call)---")
        return {
            "destination": bypass_destination,
            "routing_confidence": DEFAULT_ROUTER_CONFIG.smart_bypass_confidence,
            "query_complexity": complexity,
            "routing_metadata": {"routing_reason": "Smart pattern bypass"}
        }
    
    # Embedding-based routing check with proper event loop handling
    try:
        # Check if we're already in an async context
        try:
            current_loop = asyncio.get_running_loop()
            # We're in an async context, use asyncio.create_task or run in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _embedding_route_check(user_query))
                embedding_destination = future.result(timeout=5.0)
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            embedding_destination = asyncio.run(_embedding_route_check(user_query))
        
        if embedding_destination:
            complexity = _calculate_query_complexity(user_query)
            logger.info(f"Embedding routing to {embedding_destination} with complexity {complexity:.2f}")
            print(f"---EMBEDDING ROUTE TO: {embedding_destination} (saved LLM call)---")
            return {
                "destination": embedding_destination,
                "routing_confidence": DEFAULT_ROUTER_CONFIG.embedding_route_confidence,
                "query_complexity": complexity,
                "routing_metadata": {"routing_reason": "Embedding similarity match"}
            }
    except Exception as e:
        logger.warning(f"Embedding check failed, falling back to LLM: {e}")

    # Initialize the LLM, ensuring API key is passed
    # (Referencing MEMORY[213594e5-5a73-46c2-8086-b357bed82737])
    if not GEMINI_API_KEY:
        # This is a critical error, should be handled appropriately
        # For now, printing error and attempting to proceed without API key (will likely fail)
        print("CRITICAL ERROR: GEMINI_API_KEY not found in environment.")
        # Potentially raise an exception or route to an error handling node
    
    # Use Gemma-3-IT for better routing accuracy
    llm = ChatGoogleGenerativeAI(
        model="google/gemma-3-4b-it", # Upgraded to Gemma-3 4B IT model
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
        
        # Calculate complexity score based on query characteristics
        complexity = _calculate_query_complexity(user_query)
        
        logger.info("Router decision: dest=%s confidence=%.2f complexity=%.2f", 
                   destination, confidence, complexity)

        # Apply configurable threshold fallback
        conf_threshold = getattr(settings, 'router_conf_threshold', DEFAULT_ROUTER_CONFIG.confidence_threshold)
        if confidence < conf_threshold:
            logger.warning(
                "Low confidence (%.2f < %.2f). Falling back to primary_agent", confidence, conf_threshold
            )
            destination = "primary_agent"
            
        # Store routing metadata in state for downstream agents
        routing_metadata = {
            "confidence": confidence,
            "complexity": complexity,
            "routing_reason": f"LLM classification with Gemma-3-IT"
        }
        
        print(f"---ROUTING TO: {destination} (complexity: {complexity:.2f})---")
        
        # Return destination with metadata
        return {
            "destination": destination,
            "routing_confidence": confidence,
            "query_complexity": complexity,
            "routing_metadata": routing_metadata
        }
    except Exception as e:
        logger.exception("Routing LLM error: %s", e)
        # Fallback routing in case of LLM error
        destination = "primary_agent" # Or '__end__' or a specific error handling agent
        print(f"---FALLBACK ROUTING TO: {destination}---")
        
        return {
            "destination": destination,
            "routing_confidence": 0.5,
            "query_complexity": 0.5,
            "routing_metadata": {"routing_reason": "Fallback due to error"}
        }