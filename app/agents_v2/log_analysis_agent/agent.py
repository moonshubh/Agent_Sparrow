import os
import json
from typing import Dict, Any

from app.core.settings import settings
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.rate_limiting.agent_wrapper import wrap_gemini_agent
from uuid import uuid4
from app.core.logging_config import get_logger

# Enhanced imports
from .enhanced_schemas import EnhancedLogAnalysisAgentState, ComprehensiveLogAnalysisOutput
from .enhanced_agent import run_enhanced_log_analysis_agent

# Legacy imports for backward compatibility
from .schemas import LogAnalysisAgentState, StructuredLogAnalysisOutput
from .prompts import LOG_ANALYSIS_PROMPT_TEMPLATE
from .parsers import parse_log_content
from datetime import datetime
from app.core.user_context import get_current_user_context
from app.api_keys.schemas import APIKeyType

# GEMINI_API_KEY is now optional - will be retrieved from user context or database
# if not settings.gemini_api_key:
#     raise ValueError("GEMINI_API_KEY environment variable not set.")

async def _get_gemini_api_key() -> str:
    """
    Retrieve Gemini API key from settings, user context, or database.
    
    Returns:
        str: The Gemini API key
        
    Raises:
        ValueError: If no API key can be found from any source
    """
    # First try settings
    if settings.gemini_api_key:
        return settings.gemini_api_key
    
    # Try to get from user context if available
    user_context = get_current_user_context()
    if user_context:
        api_key = await user_context.get_gemini_api_key()
        if api_key:
            return api_key
    
    # If still no key, raise clear error
    raise ValueError(
        "Gemini API key not found. Please either:\n"
        "1. Set GEMINI_API_KEY environment variable\n"
        "2. Add your Gemini API key in Settings > API Keys\n"
        "3. Get a free key at: https://makersuite.google.com/app/apikey"
    )

async def run_log_analysis_agent(state: LogAnalysisAgentState) -> Dict[str, Any]:
    """
    Enhanced log analysis agent with comprehensive profiling and intelligent solutions.
    
    This function now uses the enhanced analysis engine while maintaining backward compatibility.
    """
    # Check if enhanced analysis is enabled (default: True for better results)
    use_enhanced_analysis = os.getenv("USE_ENHANCED_LOG_ANALYSIS", "true").lower() == "true"
    
    if use_enhanced_analysis:
        # Convert old state to enhanced state format
        # Handle both dict and list states properly
        if isinstance(state, dict):
            enhanced_state = {
                "messages": state.get("messages", []),
                "raw_log_content": state.get("raw_log_content", ""),
                "parsed_log_data": state.get("parsed_log_data"),
                "system_profile": None,  # Will be populated by enhanced agent
                "detected_issues": None,  # Will be populated by enhanced agent
                "generated_solutions": None,  # Will be populated by enhanced agent
                "final_report": state.get("final_report"),
                "analysis_metadata": None  # Will be populated by enhanced agent
            }
        else:
            # If state is not a dict, create a minimal state
            enhanced_state = {
                "messages": [],
                "raw_log_content": "",
                "parsed_log_data": None,
                "system_profile": None,
                "detected_issues": None,
                "generated_solutions": None,
                "final_report": None,
                "analysis_metadata": None
            }
        
        return await run_enhanced_log_analysis_agent(enhanced_state)
    else:
        return await run_legacy_log_analysis_agent(state)


async def run_legacy_log_analysis_agent(state: LogAnalysisAgentState) -> Dict[str, Any]:
    """
    Asynchronous node that runs the specialized log analysis agent v2.

    This agent takes raw log content, uses a dedicated parser to structure it,
    invokes a GenAI model for deep analysis, and produces a structured report.
    It relies on LLM reasoning and does not use web search tools directly.

    Args:
        state: The current state of the agent graph.

    Returns:
        A dictionary containing the updated state, including the final report.
    """
    trace_id = state.get("trace_id") or str(uuid4())
    logger = get_logger("log_analysis_agent", trace_id=trace_id)
    logger.info("--- Running Log Analysis Agent v2 ---")

    try:
        raw_log_content = state.get("raw_log_content")
        if not raw_log_content:
            logger.error("validation_error", reason="'raw_log_content' is missing.")
            raise ValueError("'raw_log_content' is missing from the agent state.")

        logger.info("analysis_start", lines=len(raw_log_content.splitlines()))

        # 1. Parse log content
        logger.info("Parsing log content...")
        parsed_data = parse_log_content(raw_log_content)
        state['parsed_log_data'] = parsed_data
        logger.info("parsing_complete", entries=parsed_data["metadata"]["total_entries_parsed"])

        # 2. Initialize the Language Model for structured output with rate limiting
        gemini_api_key = await _get_gemini_api_key()
        llm_base = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",  # Use supported model for rate limiting
            temperature=0.1,
            google_api_key=gemini_api_key,
        )
        llm = wrap_gemini_agent(llm_base, "gemini-2.5-flash")
        llm_so = llm.with_structured_output(StructuredLogAnalysisOutput)

        # 3. Create and invoke the analysis chain
        analysis_chain = LOG_ANALYSIS_PROMPT_TEMPLATE | llm_so
        logger.info("Invoking LLM for deep analysis...")
        parsed_log_json = json.dumps(parsed_data, indent=2)
        final_report = await analysis_chain.ainvoke({"parsed_log_json": parsed_log_json})
        logger.info("analysis_complete")

        # 4. Validate and store the final report
        if isinstance(final_report, StructuredLogAnalysisOutput):
            state['final_report'] = final_report
        else:
            # This case should ideally not be reached with with_structured_output
            logger.error("UNEXPECTED_LLM_OUTPUT_TYPE", type=type(final_report).__name__)
            raise TypeError(f"LLM output was not the expected Pydantic model.")

        logger.info("--- Log Analysis Complete ---")

    except Exception as e:
        logger.error(f"Error in Log Analysis Agent: {e}")
        logger.error("analysis_failed", error=str(e), exc_info=True)

        # Create a robust, schema-compliant error report
        try:
            metadata = state.get('parsed_log_data', {}).get('metadata', {})
            error_report = StructuredLogAnalysisOutput(
                overall_summary=f"Agent failed to analyze logs. Error: {str(e)}",
                system_metadata={
                    "mailbird_version": metadata.get("mailbird_version", "Unknown"),
                    "database_size_mb": metadata.get("database_size_mb", "Unknown"),
                    "account_count": metadata.get("account_count", "Unknown"),
                    "folder_count": metadata.get("folder_count", "Unknown"),
                    "log_timeframe": metadata.get("log_timeframe", "Unknown"),
                    "analysis_timestamp": metadata.get("analysis_timestamp", datetime.utcnow().isoformat()),
                },
                identified_issues=[],
                proposed_solutions=[],
                supplemental_research=None
            )
            state['final_report'] = error_report
        except Exception as inner_e:
            logger.critical("CRITICAL_ERROR_CREATING_ERROR_REPORT", inner_error=str(inner_e), exc_info=True)
            # Final fallback to a dictionary if Pydantic model creation itself fails
            state['final_report'] = {
                "overall_summary": f"Critical error during error handling: {inner_e}. Original error: {e}",
                "system_metadata": {"mailbird_version": "Unknown", "database_size_mb": "Unknown", "account_count": "Unknown", "folder_count": "Unknown", "log_timeframe": "Unknown", "analysis_timestamp": "Unknown"},
                "identified_issues": [],
                "proposed_solutions": [],
                "supplemental_research": None,
            }

    return {
        'parsed_log_data': state.get('parsed_log_data'),
        'final_report': state.get('final_report'),
        'trace_id': trace_id,
    }
