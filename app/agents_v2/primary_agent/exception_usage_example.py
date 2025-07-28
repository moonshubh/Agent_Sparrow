"""
Example usage of the MB-Sparrow Primary Agent exception hierarchy.

This file demonstrates how to integrate the new exception system
into the existing agent code for better error handling and user experience.

Note: This is an example file showing best practices for exception usage.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import google.generativeai as genai
from langchain_core.messages import AIMessage

from app.agents_v2.primary_agent.exceptions import (
    InvalidAPIKeyException,
    RateLimitException,
    TimeoutException,
    NetworkException,
    ConfigurationException,
    KnowledgeBaseException,
    ToolExecutionException,
    ReasoningException,
    ModelOverloadException,
    create_exception_from_error
)

logger = logging.getLogger(__name__)

# Configuration constants
VALID_GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-pro"]


# Example 1: Enhanced API key validation
def create_user_model_with_enhanced_errors(api_key: str):
    """
    Example of how to replace the existing create_user_model function
    with enhanced exception handling.
    """
    # Validate API key format
    if not api_key or not api_key.startswith('AIza') or len(api_key) != 39:
        raise InvalidAPIKeyException(
            message=f"Invalid API key format: {api_key[:8]}... (length: {len(api_key) if api_key else 0})",
            key_type="Google API",
            expected_format="AIza... (39 characters total)"
        )
    
    try:
        # Attempt to create the model
        model = await create_model_logic(api_key) if asyncio.iscoroutinefunction(create_model_logic) else create_model_logic(api_key)
        return model
        
    except genai.errors.InvalidApiKeyError as e:
        # Handle invalid API key from Google
        raise InvalidAPIKeyException(
            message=str(e),
            key_type="Google Gemini API"
        )
    
    except genai.errors.QuotaError as e:
        # Handle quota/rate limit errors
        import re
        retry_match = re.search(r'retry after (\d+)', str(e))
        retry_after = int(retry_match.group(1)) if retry_match else 60
        
        raise RateLimitException(
            message=str(e),
            retry_after=retry_after,
            limit_type="API quota",
            current_usage={"status": "quota_exceeded"}
        )
    
    except Exception as e:
        # Use factory for unexpected errors
        raise create_exception_from_error(e, context={"operation": "model_creation"})


# Example 2: Enhanced tool execution with proper error handling
async def execute_tool_with_error_handling(tool_name: str, tool_func, *args, **kwargs):
    """
    Example wrapper for tool execution with comprehensive error handling.
    """
    try:
        logger.info(f"Executing tool: {tool_name}")
        result = await tool_func(*args, **kwargs)
        return result
        
    except TimeoutError as e:
        raise TimeoutException(
            message=str(e),
            operation=f"{tool_name} execution",
            timeout_seconds=kwargs.get('timeout', 30)
        )
    
    except ConnectionError as e:
        raise NetworkException(
            message=str(e),
            service=tool_name,
            url=kwargs.get('url', None)
        )
    
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        raise ToolExecutionException(
            message=f"Tool execution failed: {str(e)}",
            tool_name=tool_name,
            tool_error=str(e)
        )


# Example 3: Enhanced knowledge base search
async def search_knowledge_base_with_errors(query: str, kb_client):
    """
    Example of knowledge base search with proper exception handling.
    """
    try:
        results = await kb_client.search(query)
        
        if not results:
            logger.warning(f"No results found for query: {query}")
            # This is not an error, just return empty results
            return []
            
        return results
        
    except ConnectionError as e:
        raise KnowledgeBaseException(
            message=f"Failed to connect to knowledge base: {str(e)}",
            operation="search",
            query=query
        )
    
    except TimeoutError as e:
        raise KnowledgeBaseException(
            message=f"Knowledge base search timed out: {str(e)}",
            operation="search",
            query=query
        )
    
    except Exception as e:
        logger.error(f"KB search failed for query '{query}': {e}")
        raise KnowledgeBaseException(
            message=str(e),
            operation="search",
            query=query
        )


# Example 4: Enhanced agent response with error recovery
async def generate_agent_response_with_recovery(state: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    """
    Example of the main agent function with comprehensive error handling
    and recovery strategies.
    """
    try:
        # Primary response generation
        response = await generate_primary_response(state, api_key)
        return {"messages": [response]}
        
    except RateLimitException as e:
        # Handle rate limits with user-friendly message
        logger.warning(f"Rate limit hit: {e}")
        
        suggestions = [f"• {suggestion}" for suggestion in e.recovery_suggestions]
        fallback_message = (
            f"I apologize, but {e.user_message()} "
            f"Here's what you can do:\n"
            + "\n".join(suggestions) + "\n"
        )
        
        return {
            "messages": [AIMessage(content=fallback_message)],
            "error": e.to_dict()
        }
    
    except ModelOverloadException as e:
        logger.warning(f"Model overload: {e}")
        
        if e.fallback_available:
            # Try with fallback model
            try:
                response = await generate_fallback_response(state, api_key)
                return {"messages": [response]}
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
        
        # Return helpful message
        return {
            "messages": [AIMessage(content=e.user_message())],
            "error": e.to_dict()
        }
    
    except InvalidAPIKeyException as e:
        # This is critical - log and return clear instructions
        logger.error(f"Invalid API key: {e}")
        
        return {
            "messages": [AIMessage(
                content=(
                    "⚠️ Authentication Issue\n\n"
                    f"{e.user_message()}\n\n"
                    "Please ensure your API key is correctly configured."
                )
            )],
            "error": e.to_dict()
        }
    
    except (NetworkException, TimeoutException) as e:
        # Network issues - suggest retry
        logger.warning(f"Network/Timeout issue: {e}")
        
        return {
            "messages": [AIMessage(
                content=(
                    f"🌐 Connection Issue\n\n"
                    f"{e.user_message()}\n\n"
                    "This is usually temporary. Please try again in a moment."
                )
            )],
            "error": e.to_dict()
        }
    
    except Exception as e:
        # Unexpected error - use factory
        agent_exception = create_exception_from_error(e)
        logger.error(f"Unexpected error in agent: {agent_exception}")
        
        return {
            "messages": [AIMessage(
                content=(
                    "I encountered an unexpected issue while processing your request. "
                    "I'm logging this for our team to investigate. "
                    "Please try again, and if the issue persists, "
                    f"reference error code: {agent_exception.error_code}"
                )
            )],
            "error": agent_exception.to_dict()
        }


# Example 5: Configuration validation with proper exceptions
def validate_agent_configuration(config: Dict[str, Any]):
    """
    Example of configuration validation with clear exception messages.
    """
    required_configs = {
        "GEMINI_MODEL": "Model name (e.g., gemini-2.5-flash)",
        "KB_SEARCH_ENABLED": "Boolean flag for knowledge base",
        "WEB_SEARCH_ENABLED": "Boolean flag for web search",
        "MAX_RETRIES": "Integer for retry attempts"
    }
    
    for key, description in required_configs.items():
        if key not in config:
            raise ConfigurationException(
                message=f"Missing required configuration: {key}",
                config_key=key,
                expected_value=description
            )
    
    # Validate specific values
    if config.get("MAX_RETRIES", 0) < 1:
        raise ConfigurationException(
            message="MAX_RETRIES must be at least 1",
            config_key="MAX_RETRIES",
            expected_value="Integer >= 1",
            actual_value=str(config.get("MAX_RETRIES"))
        )
    
    model_name = config.get("GEMINI_MODEL", "")
    if model_name not in VALID_GEMINI_MODELS:
        raise ConfigurationException(
            message=f"Invalid model name: {model_name}",
            config_key="GEMINI_MODEL",
            expected_value=f"One of: {', '.join(VALID_GEMINI_MODELS)}",
            actual_value=model_name
        )


# Example 6: Reasoning engine with exception handling
async def perform_reasoning_with_errors(query: str, context: Dict[str, Any]):
    """
    Example of reasoning engine integration with proper error handling.
    """
    reasoning_phases = [
        "query_analysis",
        "context_recognition", 
        "solution_mapping",
        "tool_assessment",
        "response_strategy",
        "quality_assessment"
    ]
    
    current_phase = None
    
    try:
        for phase in reasoning_phases:
            current_phase = phase
            logger.debug(f"Reasoning phase: {phase}")
            
            # Simulate phase execution
            result = await execute_reasoning_phase(phase, query, context)
            
            if not result or result.get("confidence", 0) < 0.3:
                raise ReasoningException(
                    message=f"Low confidence in {phase}: {result.get('confidence', 0)}",
                    reasoning_phase=phase,
                    context={"query": query[:100], "phase_result": result}
                )
        
        return result
        
    except Exception as e:
        if isinstance(e, ReasoningException):
            raise
        
        # Wrap other exceptions
        raise ReasoningException(
            message=f"Reasoning failed during {current_phase}: {str(e)}",
            reasoning_phase=current_phase,
            context={"query": query[:100], "error": str(e)}
        )


# Placeholder functions for the examples
async def create_model_logic(api_key: str):
    """Placeholder for actual model creation logic."""
    pass

async def generate_primary_response(state: Dict[str, Any], api_key: str):
    """Placeholder for primary response generation."""
    pass

async def generate_fallback_response(state: Dict[str, Any], api_key: str):
    """Placeholder for fallback response generation."""
    pass

async def execute_reasoning_phase(phase: str, query: str, context: Dict[str, Any]):
    """Placeholder for reasoning phase execution."""
    return {"confidence": 0.9, "result": "phase_result"}


# Example usage in main agent flow
async def enhanced_agent_main():
    """
    Example of how the main agent flow would use the exception system.
    """
    try:
        # Validate configuration on startup
        config = load_configuration()
        validate_agent_configuration(config)
        
        # Create model with enhanced error handling  
        api_key = get_user_api_key()
        model = create_user_model_with_enhanced_errors(api_key)
        
        # Process user request
        state = {"messages": []}
        response = await generate_agent_response_with_recovery(state, api_key)
        
        return response
        
    except ConfigurationException as e:
        # Configuration errors should halt startup
        logger.critical(f"Configuration error: {e}")
        raise
        
    except Exception as e:
        # Log unexpected errors but try to continue
        logger.error(f"Unexpected error in agent main: {e}")
        agent_exception = create_exception_from_error(e)
        
        return {
            "error": agent_exception.to_dict(),
            "messages": [AIMessage(content=agent_exception.user_message())]
        }


def load_configuration():
    """Placeholder for configuration loading."""
    return {}

def get_user_api_key():
    """Placeholder for API key retrieval."""
    return "AIza" + "x" * 35  # Example key format


if __name__ == "__main__":
    # This file is for demonstration purposes
    print("MB-Sparrow Primary Agent Exception Usage Examples")
    print("=" * 50)
    print("This file demonstrates best practices for using the exception hierarchy.")
    print("\nKey patterns demonstrated:")
    print("1. API key validation with clear user messages")
    print("2. Tool execution with timeout and network handling")
    print("3. Knowledge base operations with connection handling")
    print("4. Main agent flow with comprehensive error recovery")
    print("5. Configuration validation at startup")
    print("6. Reasoning engine error handling")
    print("\nSee the code for detailed implementation examples.")