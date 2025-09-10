"""
Log Analysis Agent Router
Simplified implementation with question-driven analysis
"""

import os
from typing import Dict, Any
from uuid import uuid4

from app.core.logging_config import get_logger
from app.core.user_context import get_current_user_context

# Simplified implementation
from .simplified_agent import run_simplified_log_analysis
from .simplified_schemas import SimplifiedAgentState


async def run_log_analysis_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point for the log analysis agent.
    
    Uses the simplified, question-driven implementation by default.
    
    Args:
        state: Dictionary containing:
            - raw_log_content: The log file content to analyze
            - question: Optional specific question about the logs
            - trace_id: Optional trace ID for request tracking
    
    Returns:
        Dictionary containing:
            - final_report: SimplifiedLogAnalysisOutput with analysis results
            - trace_id: Request trace ID
            - analysis_method: 'simplified'
    """
    trace_id = state.get("trace_id") or str(uuid4())
    logger = get_logger("log_analysis_agent", trace_id=trace_id)
    
    # Log the analysis request
    logger.info("Starting log analysis", {
        "has_question": bool(state.get("question")),
        "log_size": len(state.get("raw_log_content", "")),
        "trace_id": trace_id
    })
    
    # Use simplified implementation
    simplified_state = {
        "raw_log_content": state.get("raw_log_content", ""),
        "question": state.get("question"),  # Will be None if not provided
        "trace_id": trace_id
    }
    
    try:
        result = await run_simplified_log_analysis(simplified_state)
        logger.info("Log analysis completed successfully", {
            "trace_id": trace_id,
            "method": "simplified"
        })
        return result
    except Exception as e:
        logger.error(f"Log analysis failed: {e}", {
            "trace_id": trace_id,
            "error": str(e)
        })
        raise