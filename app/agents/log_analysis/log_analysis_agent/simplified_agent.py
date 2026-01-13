"""
Simplified Log Analysis Agent - Question-driven, focused responses.
Optimized for AI SDK integration with direct, actionable insights.
"""

import os
from typing import Dict, Any, List, Optional
from uuid import uuid4

import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.settings import settings
from app.core.config import find_bucket_for_model, find_model_config, get_models_config
from app.providers.limits import wrap_gemini_agent
from app.core.logging_config import get_logger
from app.core.user_context import get_current_user_context

from .simplified_schemas import (
    SimplifiedLogAnalysisOutput,
    SimplifiedAgentState,
    LogSection,
    SimplifiedIssue,
    SimplifiedSolution
)
from .utils import build_log_sections_from_ranges, extract_json_payload


class AgentConfig:
    """Configuration for the simplified log analysis agent."""
    
    def __init__(self):
        """Load configuration from environment with sensible defaults.

        Defaults come from models.yaml (internal helper for fast log analysis).
        """
        models_config = get_models_config()
        default_cfg = (
            models_config.internal.get("helper")
            or models_config.coordinators.get("google_with_subagents")
            or models_config.coordinators["google"]
        )
        override_model = os.getenv("SIMPLIFIED_LOG_MODEL")
        if override_model:
            match = find_model_config(models_config, override_model)
            self.model_name = match.model_id if match else default_cfg.model_id
        else:
            self.model_name = default_cfg.model_id

        temp_override = os.getenv("LOG_AGENT_TEMPERATURE")
        self.temperature = float(temp_override) if temp_override else default_cfg.temperature
        self.request_timeout = int(os.getenv("SIMPLIFIED_LOG_TIMEOUT_SECONDS", "120"))
        self.max_log_size = int(os.getenv("MAX_LOG_SIZE", "500000"))
        self.context_window = int(os.getenv("LOG_CONTEXT_WINDOW", "50"))
        self.max_sections = int(os.getenv("MAX_LOG_SECTIONS", "3"))
        self.max_issues = int(os.getenv("MAX_ISSUES", "5"))
        self.max_solutions = int(os.getenv("MAX_SOLUTIONS", "5"))
        self.bucket_name = find_bucket_for_model(models_config, self.model_name) or "internal.helper"
        
    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"AgentConfig(model={self.model_name}, "
            f"temp={self.temperature}, "
            f"max_log={self.max_log_size})"
        )


class SimplifiedLogAnalysisAgent:
    """
    Streamlined log analysis agent focusing on question-driven responses.
    Provides direct answers instead of comprehensive reports.
    
    Supports async context manager for proper resource cleanup:
        async with SimplifiedLogAnalysisAgent() as agent:
            result = await agent.analyze(state)
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        """
        Initialize the simplified agent with configuration.
        
        Args:
            config: Optional configuration object. Creates default if not provided.
        """
        self.config = config or AgentConfig()
        self.logger = get_logger("simplified_log_agent")
        self._llm = None  # Cache LLM instance
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources."""
        self._llm = None  # Clear cached LLM
    
    async def _get_llm(self):
        """
        Get configured LLM with proper API key resolution and caching.
        
        Follows the precedence: cached > user context > settings > error.
        
        Returns:
            Wrapped LLM instance configured with appropriate API key.
            
        Raises:
            ValueError: When no API key is available from any source.
        """
        # Return cached instance if available
        if self._llm is not None:
            return self._llm
        
        # Early return pattern - cleaner than nested ifs
        user_context = get_current_user_context()
        if user_context:
            api_key = await user_context.get_gemini_api_key()
            if api_key:
                self._llm = self._create_llm_with_key(api_key)
                return self._llm
        
        # Fallback to settings
        if settings.gemini_api_key:
            self._llm = self._create_llm_with_key(settings.gemini_api_key)
            return self._llm
        
        # Explicit is better than implicit - provide actionable error message
        raise ValueError(
            "Gemini API key not found. Please either:\n"
            "1. Add your API key in Settings > API Keys\n"
            "2. Set GEMINI_API_KEY environment variable\n"
            "3. Get a free key at: https://makersuite.google.com/app/apikey"
        )
    
    def _create_llm_with_key(self, api_key: str):
        """Create and wrap LLM instance with given API key."""
        llm_base = ChatGoogleGenerativeAI(
            model=self.config.model_name,
            temperature=self.config.temperature,
            google_api_key=api_key,
            timeout=self.config.request_timeout,
        )
        return wrap_gemini_agent(llm_base, self.config.bucket_name, self.config.model_name)
    
    def _preprocess_log(self, log_content: str) -> str:
        """
        Preprocess log content: truncate, clean, and normalize.
        
        Args:
            log_content: Raw log content to process.
            
        Returns:
            Cleaned and normalized log content.
        """
        if not log_content:
            return ""
        
        # Truncate early to avoid processing unnecessarily large content
        truncated = (
            log_content[:self.config.max_log_size]
            if len(log_content) > self.config.max_log_size
            else log_content
        )

        # Some uploaded logs are UTF-16/UTF-8 mis-decoded and contain many NUL bytes.
        # Dropping NULs restores readable text and prevents the model from stalling.
        if "\x00" in truncated:
            truncated = truncated.replace("\x00", "")
        truncated = truncated.lstrip("\ufeff")
        
        # Use generator expression with filter for memory efficiency
        # This is more Pythonic than building a list with append
        cleaned_lines = (
            ' '.join(line.split())  # Normalize whitespace
            for line in truncated.splitlines()
            if line.strip()  # Filter empty lines
        )
        
        return '\n'.join(cleaned_lines)

    def _estimate_confidence(
        self,
        analysis: Dict[str, Any],
        *,
        question: Optional[str],
        issues: List[SimplifiedIssue],
        solutions: List[SimplifiedSolution],
        priority_concerns: List[str],
    ) -> float:
        """Estimate confidence based on output completeness and signal strength."""
        base = 0.7 if question else 0.75
        summary_text = str(
            analysis.get("answer")
            or analysis.get("summary")
            or analysis.get("overall_summary")
            or ""
        ).strip()

        if issues:
            base += 0.1
        if solutions:
            base += 0.1
        if priority_concerns:
            base += 0.05
        if summary_text and len(summary_text) > 40:
            base += 0.05

        lowered = summary_text.lower()
        if "unable to analyze" in lowered or "processing error" in lowered:
            base -= 0.35
        if not issues and not solutions and len(priority_concerns) == 0:
            base -= 0.2

        return max(0.1, min(float(base), 0.95))

    async def _extract_relevant_sections(self, log_content: str, question: str) -> List[LogSection]:
        """Extract log sections most relevant to the user's question."""
        if not question:
            # If no question, return overview sections
            lines = log_content.split('\n')
            if len(lines) <= 100:
                return [LogSection(
                    line_numbers="1-" + str(len(lines)),
                    content=log_content,
                    relevance_score=1.0
                )]
            
            # Return first and last sections for overview
            return [
                LogSection(
                    line_numbers="1-50",
                    content='\n'.join(lines[:50]),
                    relevance_score=0.8
                ),
                LogSection(
                    line_numbers=f"{len(lines)-50}-{len(lines)}",
                    content='\n'.join(lines[-50:]),
                    relevance_score=0.8
                )
            ]
        
        # Question-driven extraction
        llm = await self._get_llm()
        sections_schema: Dict[str, Any] = {
            "type": "array",
            "minItems": 1,
            "maxItems": self.config.max_sections,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "line_range": {
                        "type": "string",
                        "pattern": "^[0-9]+-[0-9]+$",
                        "description": "Approximate line range like '141-189'. Do not use timestamps.",
                    },
                    "relevance": {"type": "string"},
                    "key_info": {"type": "string"},
                },
                "required": ["line_range", "relevance", "key_info"],
            },
        }
        prompt = f"""Analyze this log file to find sections relevant to the user's question.

USER QUESTION: {question}

LOG FILE (first 10000 chars):
{log_content[:10000]}

Identify the most relevant sections. For each section, provide:
1. Line numbers (approximate)
2. Why it's relevant
3. Key information it contains

Return as JSON array with format:
[{{"line_range": "100-150", "relevance": "Contains error about X", "key_info": "Shows Y happening"}}]
"""
        
        for attempt in range(2):
            try:
                attempt_prompt = (
                    prompt
                    if attempt == 0
                    else (
                        prompt
                        + "\n\nIMPORTANT: Return ONLY the JSON array (no prose, no markdown)."
                    )
                )
                kwargs = {"temperature": 0} if attempt == 1 else {}
                response = await asyncio.wait_for(
                    llm.ainvoke(
                        attempt_prompt,
                        response_mime_type="application/json",
                        response_schema=sections_schema,
                        **kwargs,
                    ),
                    timeout=min(self.config.request_timeout, 45)
                    if attempt == 1
                    else self.config.request_timeout,
                )

                # Use shared JSON extraction and section builder utilities
                sections_data = extract_json_payload(
                    response.content,
                    pattern=r'\[.*?\]',
                    fallback=[],
                    logger_instance=self.logger,
                )

                if sections_data:
                    sections = build_log_sections_from_ranges(
                        sections_data,
                        log_content,
                        max_sections=self.config.max_sections,
                        logger_instance=self.logger,
                    )
                    if sections:
                        return sections

            except asyncio.TimeoutError:
                self.logger.warning(
                    "extract_relevant_sections_timeout",
                    timeout_seconds=min(self.config.request_timeout, 45)
                    if attempt == 1
                    else self.config.request_timeout,
                )
            except Exception as e:
                self.logger.warning(f"Failed to extract sections: {e}")
            
        # Fallback to simple extraction
        lines = log_content.split('\n')
        return [LogSection(
            line_numbers="1-100",
            content='\n'.join(lines[:100]),
            relevance_score=0.5
        )]
    
    async def _analyze_with_question(self, log_sections: List[LogSection], question: str) -> Dict[str, Any]:
        """Generate focused analysis based on the question."""
        llm = await self._get_llm()
        
        # Combine relevant sections
        combined_logs = '\n\n'.join([
            f"[Lines {s.line_numbers}]\n{s.content}" 
            for s in log_sections
        ])
        
        if question:
            prompt = f"""Analyze these log sections to answer the user's specific question.

USER QUESTION: {question}

RELEVANT LOG SECTIONS:
{combined_logs}

Provide:
1. DIRECT ANSWER: A clear, specific answer to the question
2. EVIDENCE: Specific log entries that support your answer
3. KEY ISSUES: Any critical problems found (if any)
4. RECOMMENDED ACTION: What the user should do next

Format your response as JSON:
{{
  "answer": "Direct answer to the question",
  "evidence": ["log line 1", "log line 2"],
  "issues": [{{"title": "Issue", "severity": "High", "details": "..."}}],
  "actions": [{{"title": "Action", "steps": ["step 1", "step 2"]}}]
}}"""
            response_schema: Dict[str, Any] = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "answer": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 8,
                    },
                    "issues": {
                        "type": "array",
                        "maxItems": self.config.max_issues,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string"},
                                "severity": {"type": "string"},
                                "details": {"type": "string"},
                            },
                            "required": ["title", "severity", "details"],
                        },
                    },
                    "actions": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": self.config.max_solutions,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string"},
                                "steps": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "maxItems": 10,
                                },
                            },
                            "required": ["title", "steps"],
                        },
                    },
                },
                "required": ["answer", "evidence", "issues", "actions"],
            }
        else:
            # No specific question - provide general analysis
            prompt = f"""Analyze these log sections to identify key issues and provide solutions.

LOG SECTIONS:
{combined_logs}

Provide:
1. SUMMARY: Brief overview of what's happening in the logs
2. KEY ISSUES: Critical problems that need attention
3. SOLUTIONS: Specific steps to resolve the issues

Format your response as JSON:
{{
  "summary": "Overview of the log analysis",
  "issues": [{{"title": "Issue", "severity": "High", "details": "..."}}],
  "solutions": [{{"title": "Solution", "steps": ["step 1", "step 2"]}}]
}}"""
            response_schema = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {"type": "string"},
                    "issues": {
                        "type": "array",
                        "maxItems": self.config.max_issues,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string"},
                                "severity": {"type": "string"},
                                "details": {"type": "string"},
                            },
                            "required": ["title", "severity", "details"],
                        },
                    },
                    "solutions": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": self.config.max_solutions,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string"},
                                "steps": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "maxItems": 10,
                                },
                            },
                            "required": ["title", "steps"],
                        },
                    },
                },
                "required": ["summary", "issues", "solutions"],
            }
        
        for attempt in range(2):
            try:
                attempt_prompt = (
                    prompt
                    if attempt == 0
                    else (
                        prompt
                        + "\n\nIMPORTANT: Return ONLY valid JSON (no prose, no markdown)."
                    )
                )
                kwargs = {"temperature": 0} if attempt == 1 else {}
                response = await asyncio.wait_for(
                    llm.ainvoke(
                        attempt_prompt,
                        response_mime_type="application/json",
                        response_schema=response_schema,
                        **kwargs,
                    ),
                    timeout=min(self.config.request_timeout, 60)
                    if attempt == 1
                    else self.config.request_timeout,
                )

                # Use robust JSON extraction with appropriate fallback
                analysis = extract_json_payload(
                    response.content,
                    pattern=r'\{.*?\}',
                    fallback=None,
                    logger_instance=self.logger,
                )

                if analysis:
                    return analysis

            except asyncio.TimeoutError:
                self.logger.warning(
                    "analyze_with_question_timeout",
                    timeout_seconds=min(self.config.request_timeout, 60)
                    if attempt == 1
                    else self.config.request_timeout,
                )
            except Exception as e:
                self.logger.error(f"Analysis failed: {e}")
        
        # Structured fallback response maintaining API contract
        return {
            "answer": "Unable to analyze logs due to processing error",
            "summary": "Log analysis encountered an error",
            "issues": [],
            "solutions": [],
            "evidence": [],
            "actions": []
        }
    
    async def analyze(self, state: SimplifiedAgentState) -> SimplifiedLogAnalysisOutput:
        """
        Main analysis function - streamlined for question-driven responses.
        
        Args:
            state: Agent state containing log content and optional question.
            
        Returns:
            SimplifiedLogAnalysisOutput with analysis results.
        """
        trace_id = state.trace_id or str(uuid4())
        self.logger = get_logger("simplified_log_agent", trace_id=trace_id)
        self.logger.info("Starting simplified log analysis")
        
        try:
            # Early validation with informative response
            cleaned_log = self._preprocess_log(state.raw_log_content)
            if not cleaned_log:
                return self._create_empty_response(trace_id)
            
            # Core analysis pipeline
            relevant_sections = await self._extract_relevant_sections(
                cleaned_log, 
                state.question
            )
            
            analysis = await self._analyze_with_question(
                relevant_sections,
                state.question
            )
            
            # Transform analysis to output format
            return self._build_output(
                analysis=analysis,
                sections=relevant_sections,
                question=state.question,
                trace_id=trace_id
            )
            
        except Exception as e:
            self.logger.error(f"Analysis failed: {e}", exc_info=True)
            return self._create_error_response(str(e), trace_id)
    
    def _create_empty_response(self, trace_id: str) -> SimplifiedLogAnalysisOutput:
        """Create response for empty log content."""
        return SimplifiedLogAnalysisOutput(
            overall_summary="No valid log content to analyze",
            health_status="Unknown",
            trace_id=trace_id,
            confidence_level=0.0
        )
    
    def _create_error_response(self, error: str, trace_id: str) -> SimplifiedLogAnalysisOutput:
        """Create response for analysis errors."""
        return SimplifiedLogAnalysisOutput(
            overall_summary=f"Analysis failed: {error}",
            health_status="Error",
            trace_id=trace_id,
            confidence_level=0.0
        )
    
    def _build_output(
        self,
        analysis: Dict[str, Any],
        sections: List[LogSection],
        question: Optional[str],
        trace_id: str
    ) -> SimplifiedLogAnalysisOutput:
        """
        Build structured output from analysis results.
        
        This method handles the transformation from raw analysis
        to the structured output expected by the AI SDK.
        """
        # Extract summary based on analysis type
        if question:
            overall_summary = analysis.get('answer', 'Analysis complete')
            priority_concerns = analysis.get('evidence', [])[:3]
        else:
            overall_summary = analysis.get('summary', 'Log analysis complete')
            priority_concerns = [
                issue.get('title', '') 
                for issue in analysis.get('issues', [])[:3]
                if issue.get('title')
            ]
        
        # Transform issues using list comprehension
        identified_issues = [
            SimplifiedIssue(
                title=issue.get('title', 'Issue'),
                details=issue.get('details', ''),
                severity=issue.get('severity', 'Medium')
            )
            for issue in analysis.get('issues', [])[:self.config.max_issues]
        ]
        
        # Transform solutions - handle both 'solutions' and 'actions' keys
        solutions_data = analysis.get('solutions') or analysis.get('actions', [])
        proposed_solutions = [
            SimplifiedSolution(
                title=solution.get('title', 'Solution'),
                steps=solution.get('steps', []),
                expected_outcome=solution.get('outcome', 'Issue will be resolved')
            )
            for solution in solutions_data[:self.config.max_solutions]
        ]

        confidence_level = self._estimate_confidence(
            analysis,
            question=question,
            issues=identified_issues,
            solutions=proposed_solutions,
            priority_concerns=[str(item) for item in priority_concerns if item],
        )
        
        # Determine health status using severity mapping
        health_status = self._compute_health_status(identified_issues)
        
        return SimplifiedLogAnalysisOutput(
            overall_summary=overall_summary,
            health_status=health_status,
            priority_concerns=priority_concerns,
            identified_issues=identified_issues,
            proposed_solutions=proposed_solutions,
            question=question,
            relevant_log_sections=sections if question else None,
            confidence_level=confidence_level,
            trace_id=trace_id,
            analysis_method="simplified"
        )
    
    def _compute_health_status(self, issues: List[SimplifiedIssue]) -> str:
        """
        Compute overall health status from issues.
        
        Uses severity levels to determine system health:
        - Critical issues → "Critical"
        - High issues → "Degraded"  
        - Otherwise → "Healthy"
        """
        severity_priority = {"Critical": 3, "High": 2, "Medium": 1, "Low": 0}
        max_severity = max(
            (severity_priority.get(issue.severity, 0) for issue in issues),
            default=0
        )
        
        return {
            3: "Critical",
            2: "Degraded",
            1: "Healthy",
            0: "Healthy"
        }[max_severity]


async def run_simplified_log_analysis(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entry point for the simplified log analysis agent.
    """
    # Convert dict state to SimplifiedAgentState
    agent_state = SimplifiedAgentState(
        raw_log_content=state.get('raw_log_content', ''),
        question=state.get('question'),
        trace_id=state.get('trace_id')
    )
    
    # Run analysis
    agent = SimplifiedLogAnalysisAgent()
    result = await agent.analyze(agent_state)
    
    # Return in expected format
    return {
        'final_report': result,
        'trace_id': result.trace_id,
        'analysis_method': 'simplified'
    }
