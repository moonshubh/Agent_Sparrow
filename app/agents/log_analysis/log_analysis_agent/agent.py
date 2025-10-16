"""Log Analysis Agent Router.

Routes between simplified and comprehensive implementations based on configuration
and enriches the analysis with Mailbird Windows settings when available.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import uuid4

from app.core.logging_config import get_logger
from app.core.user_context import get_current_user_context  # noqa: F401

# Simplified implementation
from .simplified_agent import run_simplified_log_analysis
from .simplified_schemas import SimplifiedAgentState

# Comprehensive implementation (quality-first pipeline)
try:
    from .comprehensive_agent import LogAnalysisAgent
    _COMPREHENSIVE_AVAILABLE = True
except Exception:
    LogAnalysisAgent = None  # type: ignore
    _COMPREHENSIVE_AVAILABLE = False

# Optional Mailbird settings loader
try:
    from .context.mailbird_settings_loader import load_mailbird_settings
except Exception:
    load_mailbird_settings = None  # type: ignore


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MAILBIRD_SETTINGS_PATH = PROJECT_ROOT / "MailbirdSettings.yml"


@lru_cache(maxsize=1)
def _load_default_mailbird_settings_cached() -> Optional[Dict[str, Any]]:
    """Load the repo-default Mailbird settings file, when available."""

    if load_mailbird_settings is None:
        return None

    try:
        if not DEFAULT_MAILBIRD_SETTINGS_PATH.exists():
            return None
        return load_mailbird_settings(path=str(DEFAULT_MAILBIRD_SETTINGS_PATH))
    except Exception as exc:  # pragma: no cover - logging side-effect only
        logger = get_logger("log_analysis_agent")
        logger.info(
            "Default Mailbird settings file could not be loaded",
            path=str(DEFAULT_MAILBIRD_SETTINGS_PATH),
            error=str(exc),
        )
        return None


def _should_use_comprehensive() -> bool:
    """Decide whether to run the comprehensive pipeline.

    Priority:
    - Explicit env LOG_ANALYSIS_MODE=comprehensive/simplified
    - Fallback to comprehensive when available; else simplified
    """
    mode = os.getenv("LOG_ANALYSIS_MODE", "comprehensive").strip().lower()
    if mode in {"comprehensive", "simplified"}:
        if mode == "comprehensive" and _COMPREHENSIVE_AVAILABLE:
            return True
        if mode == "simplified":
            return False
    # Default path
    return _COMPREHENSIVE_AVAILABLE


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
    try:
        _raw_for_len = state.get("raw_log_content", "")
        log_size = len(_raw_for_len if isinstance(_raw_for_len, (str, bytes)) else str(_raw_for_len))
    except Exception:
        log_size = 0
    logger.info(
        "Starting log analysis",
        has_question=bool(state.get("question")),
        log_size=log_size,
        trace_id=trace_id,
    )
    
    raw_log = state.get("raw_log_content", "")
    if not isinstance(raw_log, str):
        # Normalize non-string payloads to string to avoid downstream type errors
        try:
            raw_log = raw_log.decode("utf-8", errors="ignore")  # type: ignore[attr-defined]
        except Exception:
            raw_log = str(raw_log)
    question = state.get("question")

    # Try comprehensive pipeline when enabled/available, else fallback
    if _should_use_comprehensive():
        try:
            # Optional Mailbird settings from request
            settings_dict: Optional[Dict[str, Any]] = None
            settings_source = "none"
            settings_content = state.get("settings_content")
            settings_path = state.get("settings_path")

            if load_mailbird_settings:
                if isinstance(settings_content, str) and settings_content.strip():
                    try:
                        settings_dict = load_mailbird_settings(content=settings_content)
                        settings_source = "request_content"
                    except (ValueError, FileNotFoundError, TypeError) as exc:
                        logger.warning(
                            "Failed to load Mailbird settings from provided content",
                            error=str(exc),
                        )
                        settings_dict = None
                elif isinstance(settings_path, str) and settings_path.strip():
                    try:
                        settings_dict = load_mailbird_settings(path=settings_path)
                        settings_source = "request_path"
                    except (ValueError, FileNotFoundError, TypeError) as exc:
                        logger.warning(
                            "Failed to load Mailbird settings from path",
                            provided_path=settings_path,
                            error=str(exc),
                        )
                        settings_dict = None

                if settings_dict is None:
                    default_settings = _load_default_mailbird_settings_cached()
                    if default_settings:
                        settings_dict = default_settings
                        settings_source = "default_repo_file"

            logger.info(
                "Mailbird settings context prepared",
                trace_id=trace_id,
                settings_loaded=bool(settings_dict),
                settings_source=settings_source,
            )

            # Initialize comprehensive agent (quality-first)
            agent = LogAnalysisAgent()
            # Pass manual web search override to agent if provided
            try:
                force_ws = state.get("force_websearch")
                if isinstance(force_ws, bool):
                    setattr(agent, "force_websearch", force_ws)
            except Exception:
                pass
            # Run comprehensive analysis and generate a conversational response
            analysis_result = await agent.analyze_log_content(
                log_content=raw_log,
                user_query=question,
                user_context_input=None,
                settings_dict=settings_dict,
                source_name=state.get("file_name") or "uploaded.log",
            )

            # Produce formatted conversational response similar to Primary Agent
            try:
                _, formatted_response = await agent._generate_response(
                    analysis_result, question, None, {}
                )
                # Defense-in-depth: sanitize any formatted response before returning
                try:
                    if isinstance(formatted_response, str):
                        if getattr(agent, "sanitizer", None) is not None:
                            formatted_response = agent.sanitizer.sanitize_for_display(formatted_response)  # type: ignore[attr-defined]
                        else:
                            # Fallback to a local sanitizer instance if agent wasn't initialized with one
                            from .privacy import LogSanitizer as _LS  # local import to avoid top-level dependency when unused
                            formatted_response = _LS().sanitize_for_display(formatted_response)  # type: ignore
                        # Normalize to a clean, non-empty string
                        formatted_response = formatted_response.strip() or None
                except Exception:
                    # Never fail the analysis due to sanitization
                    pass
            except Exception:
                formatted_response = None

            # Map comprehensive result to simplified schema for compatibility
            from .simplified_schemas import (
                SimplifiedLogAnalysisOutput,
                SimplifiedIssue,
                SimplifiedSolution,
            )

            issues = []
            for cause in (analysis_result.root_causes or [])[:5]:
                issues.append(
                    SimplifiedIssue(
                        title=cause.title or "Issue",
                        details=(cause.summary or ("; ".join(cause.evidence[:2]) if cause.evidence else "")) or "",
                        severity=getattr(cause.impact, "value", "Medium").title()
                        if hasattr(cause, "impact") else "Medium",
                    )
                )

            solutions = []
            for cause in (analysis_result.root_causes or [])[:3]:
                steps = cause.resolution_steps[:6] if getattr(cause, "resolution_steps", None) else []
                if steps:
                    solutions.append(
                        SimplifiedSolution(
                            title=f"Resolve: {cause.title}" if cause.title else "Resolution",
                            steps=steps,
                            expected_outcome="Issue will be resolved",
                        )
                    )

            priority_concerns = []
            if analysis_result.top_priority_cause and analysis_result.top_priority_cause.title:
                priority_concerns.append(analysis_result.top_priority_cause.title)

            meta = getattr(analysis_result, "metadata", None)
            total_entries = getattr(meta, "total_entries", 0) if meta else 0
            error_count = getattr(meta, "error_count", 0) if meta else 0
            overall_summary = analysis_result.executive_summary or (
                f"Analyzed {total_entries} entries with {error_count} errors."
            )

            # Health status heuristic
            if getattr(analysis_result, "has_critical_issues", False):
                health_status = "Critical"
            elif analysis_result.metadata and getattr(analysis_result.metadata, "error_rate", 0) > 20:
                health_status = "Degraded"
            else:
                health_status = "Healthy"

            simplified = SimplifiedLogAnalysisOutput(
                overall_summary=overall_summary,
                health_status=health_status,
                priority_concerns=priority_concerns,
                identified_issues=issues,
                proposed_solutions=solutions,
                question=question,
                relevant_log_sections=None,
                confidence_level=float(getattr(analysis_result, "confidence_score", 0.85) or 0.85),
                trace_id=trace_id,
                analysis_method="comprehensive",
            )

            logger.info(
                "Log analysis completed successfully",
                trace_id=trace_id,
                method="comprehensive",
            )
            return {
                "final_report": simplified,
                "trace_id": trace_id,
                "analysis_method": "comprehensive",
                "formatted_response": formatted_response,
            }

        except Exception as e:
            logger.error(
                f"Comprehensive analysis failed, falling back to simplified: {e}",
                trace_id=trace_id,
                error=str(e),
            )

    # Fallback: simplified analysis
    simplified_state = {
        "raw_log_content": raw_log,
        "question": question,
        "trace_id": trace_id,
    }
    try:
        result = await run_simplified_log_analysis(simplified_state)
        logger.info(
            "Log analysis completed successfully",
            trace_id=trace_id,
            method="simplified",
        )
        return result
    except Exception as e:
        logger.error(
            f"Log analysis failed: {e}",
            trace_id=trace_id,
            error=str(e),
        )
        raise
