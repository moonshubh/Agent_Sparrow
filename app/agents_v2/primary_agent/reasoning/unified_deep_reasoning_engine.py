"""
Unified Single-Pass Deep Reasoning Engine (SP-DRE).

Implements a single-pass reasoning system with model-specific prompting,
smart caching, and optional polish pass for quality assurance.
"""

import logging
import json
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import asyncio

from pydantic import BaseModel, Field, ValidationError
from langchain_core.messages import HumanMessage, AIMessage
import numpy as np

from app.core.settings import settings
from app.core.rate_limiting.budget_manager import BudgetManager
from app.agents_v2.primary_agent.llm_registry import SupportedModel
from app.agents_v2.primary_agent.llm_factory import build_llm
from app.agents_v2.primary_agent.model_adapter import ModelAdapter
from app.tools.embeddings import embed_query, GeminiEmbeddings
from app.agents_v2.primary_agent.prompts.model_specific_factory import (
    ModelSpecificPromptFactory, PromptOptimizationLevel, ModelPromptConfig
)

logger = logging.getLogger(__name__)


class EmotionState(str, Enum):
    """User emotional states for adaptive response."""
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"
    URGENT = "urgent"
    NEUTRAL = "neutral"
    PROFESSIONAL = "professional"
    ANXIOUS = "anxious"
    DISAPPOINTED = "disappointed"
    EXCITED = "excited"


class ComplexityLevel(str, Enum):
    """Query complexity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Pydantic models for structured output
class QueryAnalysis(BaseModel):
    """Analysis of the user query."""
    intent: str = Field(..., description="Primary intent of the query")
    emotion: EmotionState = Field(..., description="Detected emotional state")
    complexity: ComplexityLevel = Field(..., description="Query complexity level")
    root_cause_hypotheses: List[str] = Field(..., description="Potential root causes")


class SolutionStep(BaseModel):
    """Individual solution step."""
    step: int = Field(..., description="Step number")
    action: str = Field(..., description="Action to take")
    why: str = Field(..., description="Why this step works")
    verify: str = Field(..., description="How to verify success")


class FallbackStep(BaseModel):
    """Fallback solution step."""
    condition: str = Field(..., description="When to use this fallback")
    steps: List[str] = Field(..., description="Fallback steps to take")


class Solution(BaseModel):
    """Complete solution structure."""
    primary_steps: List[SolutionStep] = Field(..., description="Main solution steps")
    fallback_steps: List[FallbackStep] = Field(default_factory=list, description="Fallback options")
    prevention: List[str] = Field(default_factory=list, description="Prevention tips")


class UIDecisionStep(BaseModel):
    """UI-safe decision step for reasoning display."""
    label: str = Field(..., max_length=64)
    action: str = Field(..., max_length=180)
    evidence: Optional[str] = Field(None, max_length=140)


class UIReasoning(BaseModel):
    """User-facing reasoning explanation."""
    summary: str = Field(..., max_length=600, description="High-level rationale (70-120 words)")
    decision_path: List[UIDecisionStep] = Field(..., min_items=2, max_items=6)
    assumptions: List[str] = Field(default_factory=list, max_items=3)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    flags: List[str] = Field(default_factory=list)


class QualityMetrics(BaseModel):
    """Quality assessment metrics."""
    completeness: float = Field(..., ge=0.0, le=1.0)
    clarity: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)


class UnifiedReasoningOutput(BaseModel):
    """Complete reasoning output schema."""
    analysis: QueryAnalysis
    solution: Solution
    final_response_markdown: str = Field(..., description="User-facing response")
    reasoning_ui: UIReasoning = Field(..., description="UI reasoning display")
    quality: QualityMetrics


@dataclass
class UnifiedReasoningConfig:
    """Configuration for unified reasoning engine."""
    enable_caching: bool = True
    cache_ttl: int = 86400  # 24 hours
    enable_thinking_budget: bool = True
    thinking_budget: int = -1  # -1 for dynamic
    max_context_messages: int = 10
    enable_tool_intelligence: bool = True
    enable_polish_pass: bool = True
    polish_threshold: float = 0.75


class ReasoningCache:
    """Simple in-memory cache for reasoning results."""
    
    def __init__(self, ttl: int = 86400):
        self.cache: Dict[str, Tuple[UnifiedReasoningOutput, datetime]] = {}
        self.ttl = timedelta(seconds=ttl)
        self.max_size = 100
    
    def _generate_key(self, query: str, model: str, context_hash: str) -> str:
        """Generate cache key from query and context."""
        content = f"{query}:{model}:{context_hash}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def get(self, query: str, model: str, context_hash: str) -> Optional[UnifiedReasoningOutput]:
        """Get cached result if available and not expired."""
        key = self._generate_key(query, model, context_hash)
        
        if key in self.cache:
            result, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.ttl:
                logger.info(f"Cache hit for query pattern")
                return result
            else:
                # Expired, remove it
                del self.cache[key]
        
        return None
    
    def set(self, query: str, model: str, context_hash: str, result: UnifiedReasoningOutput):
        """Cache a reasoning result."""
        # Limit cache size
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
            oldest_key = min(self.cache.keys(), 
                           key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
        
        key = self._generate_key(query, model, context_hash)
        self.cache[key] = (result, datetime.now())


class UnifiedDeepReasoningEngine:
    """
    Single-Pass Deep Reasoning Engine with model-specific optimization.
    
    Features:
    - Single LLM call per message (with optional polish)
    - Model-specific prompting and parameters
    - Pattern caching for common queries
    - Empathy-first responses
    - Structured JSON output with UI reasoning
    """
    
    def __init__(self, model: SupportedModel, config: Optional[UnifiedReasoningConfig] = None):
        """Initialize reasoning engine with model and config."""
        self.model = model
        self.config = config or UnifiedReasoningConfig()
        self.cache = ReasoningCache(ttl=self.config.cache_ttl) if self.config.enable_caching else None
        self.prompt_factory = ModelSpecificPromptFactory()
        self.budget_manager: Optional[BudgetManager] = None
        
        # Model-specific parameters
        self._init_model_params()
        
        logger.info(f"Initialized UnifiedDeepReasoningEngine for {model.value}")
    
    def _init_model_params(self):
        """Initialize model-specific parameters."""
        if self.model == SupportedModel.GEMINI_PRO:
            self.temperature = 0.25
            self.max_output_tokens = 1800
            self.top_p = 0.9
            self.top_k = 50
            self.thinking_budget = -1  # Dynamic
        elif self.model == SupportedModel.GEMINI_FLASH:
            self.temperature = 0.3
            self.max_output_tokens = 900
            self.top_p = 0.95
            self.top_k = 40
            self.thinking_budget = 512
        elif self.model == SupportedModel.GEMINI_FLASH:
            self.temperature = 0.0
            self.max_output_tokens = 256
            self.top_p = 1.0
            self.top_k = 1
            self.thinking_budget = 0
        elif self.model == SupportedModel.KIMI_K2:
            self.temperature = 0.2
            self.max_output_tokens = 2000
            self.top_p = 0.9
            self.thinking_budget = 0
        else:
            # Default/fallback
            self.temperature = 0.3
            self.max_output_tokens = 1200
            self.top_p = 0.95
            self.top_k = 40
            self.thinking_budget = 0
    
    async def initialize(self):
        """Async initialization for budget manager."""
        self.budget_manager = BudgetManager()
        await self.budget_manager.initialize()
    
    def _extract_context(self, messages: List[Any], max_messages: int = 10) -> Tuple[str, List[Dict]]:
        """Extract recent context from message history."""
        # Take last N messages
        recent_messages = messages[-max_messages:] if len(messages) > max_messages else messages
        
        # Convert to simple format
        context_messages = []
        for msg in recent_messages:
            if hasattr(msg, 'content'):
                role = "user" if isinstance(msg, HumanMessage) else "assistant"
                context_messages.append({
                    "role": role,
                    "content": str(msg.content)
                })
        
        # Generate context hash for caching
        context_str = json.dumps(context_messages)
        context_hash = hashlib.sha256(context_str.encode()).hexdigest()[:8]
        
        return context_hash, context_messages
    
    def _build_system_prompt(self, optimization_level: PromptOptimizationLevel) -> str:
        """Build model-specific system prompt."""
        # Get base prompt from factory
        config = ModelPromptConfig(
            model=self.model,
            optimization_level=optimization_level,
            enable_empathy_amplification=True,
            enable_tool_intelligence=self.config.enable_tool_intelligence
        )
        base_prompt = self.prompt_factory.build_system_prompt(self.model, config)
        
        # Add unified output schema instructions
        schema_instructions = """
# OUTPUT CONTRACT (STRICT JSON)
Return only a JSON object matching this schema:
{
  "analysis": {
    "intent": "string describing user's main goal",
    "emotion": "frustrated|confused|anxious|professional|excited|urgent|disappointed|neutral",
    "complexity": "low|medium|high",
    "root_cause_hypotheses": ["hypothesis1", "hypothesis2"]
  },
  "solution": {
    "primary_steps": [
      {"step": 1, "action": "...", "why": "...", "verify": "..."}
    ],
    "fallback_steps": [
      {"condition": "If X happens", "steps": ["do Y", "then Z"]}
    ],
    "prevention": ["tip1", "tip2"]
  },
  "final_response_markdown": "Complete user-facing response with empathy, problem recognition, solution, tips, and closing",
  "reasoning_ui": {
    "summary": "70-120 word high-level explanation",
    "decision_path": [
      {"label": "Step label", "action": "What I did", "evidence": "Optional evidence"}
    ],
    "assumptions": ["assumption1", "assumption2"],
    "confidence": 0.8,
    "flags": []
  },
  "quality": {
    "completeness": 0.9,
    "clarity": 0.9,
    "confidence": 0.85
  }
}

IMPORTANT: Include 'downgraded_model' in flags if using a fallback model.
"""
        
        return base_prompt + "\n\n" + schema_instructions
    
    async def reason_about_query(
        self, 
        query: str,
        context_messages: List[Dict],
        api_key: str,
        router_metadata: Optional[Dict] = None
    ) -> UnifiedReasoningOutput:
        """
        Perform single-pass deep reasoning about a query.
        
        Args:
            query: User query text
            context_messages: Recent conversation context
            api_key: User's API key for the model
            router_metadata: Metadata from router (complexity, confidence)
            
        Returns:
            UnifiedReasoningOutput with complete reasoning results
        """
        # Check cache first
        context_hash = hashlib.sha256(
            json.dumps(context_messages).encode()
        ).hexdigest()[:8]
        
        if self.cache:
            cached = self.cache.get(query, self.model.value, context_hash)
            if cached:
                return cached
        
        # Check budget and potentially downgrade model
        if self.budget_manager:
            allowed_model = await self.budget_manager.pick_allowed(self.model.value)
            if allowed_model != self.model.value:
                logger.warning(f"Budget manager downgraded from {self.model.value} to {allowed_model}")
                # Create a flag for UI
                downgraded = True
            else:
                downgraded = False
        else:
            allowed_model = self.model.value
            downgraded = False
        
        # Determine optimization level based on complexity
        complexity = router_metadata.get("query_complexity", 0.5) if router_metadata else 0.5
        if complexity >= 0.65:
            optimization_level = PromptOptimizationLevel.MAXIMUM
        elif complexity >= 0.35:
            optimization_level = PromptOptimizationLevel.BALANCED
        else:
            optimization_level = PromptOptimizationLevel.SPEED
        
        # Build system prompt
        system_prompt = self._build_system_prompt(optimization_level)
        
        # Build user prompt with context
        user_prompt = self._build_user_prompt(query, context_messages, router_metadata)
        
        try:
            # Create LLM with model-specific config
            llm_config = {
                "temperature": self.temperature,
                "max_tokens": self.max_output_tokens,
                "top_p": self.top_p,
            }
            
            if self.model in (SupportedModel.GEMINI_PRO, SupportedModel.GEMINI_FLASH):
                llm_config["top_k"] = self.top_k
                # Add thinking budget config if supported
                if self.thinking_budget != 0:
                    llm_config["thinking_config"] = {
                        "thinking_budget": self.thinking_budget
                    }
            
            # Build LLM
            llm = build_llm(
                SupportedModel(allowed_model),
                api_key=api_key,
                **llm_config
            )
            
            # Create messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Invoke LLM
            response = await asyncio.to_thread(llm.invoke, messages)
            
            # Parse response
            reasoning_output = self._parse_llm_response(response, downgraded)
            
            # Check quality and potentially polish
            if self.config.enable_polish_pass:
                if reasoning_output.quality.completeness < self.config.polish_threshold or \
                   reasoning_output.quality.clarity < self.config.polish_threshold:
                    logger.info("Quality below threshold, performing polish pass")
                    reasoning_output = await self._polish_response(
                        reasoning_output, query, api_key
                    )
            
            # Record usage if budget manager available
            if self.budget_manager:
                await self.budget_manager.record(allowed_model)
            
            # Cache result
            if self.cache:
                self.cache.set(query, self.model.value, context_hash, reasoning_output)
            
            return reasoning_output
            
        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            # Return a fallback response
            return self._create_fallback_response(query, str(e))
    
    def _build_user_prompt(
        self, 
        query: str, 
        context_messages: List[Dict],
        router_metadata: Optional[Dict]
    ) -> str:
        """Build user prompt with context."""
        prompt_parts = []
        
        # Add context if available
        if context_messages:
            prompt_parts.append("## Recent Conversation Context:")
            for msg in context_messages[-3:]:  # Last 3 messages
                role = msg.get("role", "user")
                content = msg.get("content", "")
                prompt_parts.append(f"{role.upper()}: {content}")
            prompt_parts.append("")
        
        # Add current query
        prompt_parts.append("## Current User Query:")
        prompt_parts.append(query)
        prompt_parts.append("")
        
        # Add router hints if available
        if router_metadata:
            if router_metadata.get("query_complexity", 0) > 0.65:
                prompt_parts.append("Note: This appears to be a complex technical issue.")
            
        return "\n".join(prompt_parts)
    
    def _parse_llm_response(self, response: Any, downgraded: bool) -> UnifiedReasoningOutput:
        """Parse LLM response into structured output."""
        try:
            # Extract content
            if hasattr(response, 'content'):
                content = response.content
            else:
                content = str(response)
            
            # Try to parse as JSON
            if content.strip().startswith("{"):
                data = json.loads(content)
            else:
                # Extract JSON from markdown code block if needed
                import re
                json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(1))
                else:
                    raise ValueError("No JSON found in response")
            
            # Add downgrade flag if needed
            if downgraded and "reasoning_ui" in data:
                if "flags" not in data["reasoning_ui"]:
                    data["reasoning_ui"]["flags"] = []
                data["reasoning_ui"]["flags"].append("downgraded_model")
            
            # Parse with Pydantic
            return UnifiedReasoningOutput(**data)
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            # Try to extract what we can
            return self._create_partial_response(content, str(e))
    
    async def _polish_response(
        self, 
        original: UnifiedReasoningOutput,
        query: str,
        api_key: str
    ) -> UnifiedReasoningOutput:
        """Polish response with Flash model for better quality."""
        polish_prompt = f"""
Improve the clarity and completeness of this response while keeping the same solution steps:

Original response:
{original.final_response_markdown}

Requirements:
- Keep the same solution steps and technical accuracy
- Improve clarity and readability
- Ensure empathetic tone
- Make sure all steps have clear verification
- Keep the response concise

Return ONLY the improved markdown response.
"""
        
        try:
            # Use Flash for polish
            llm = build_llm(
                SupportedModel.GEMINI_FLASH,
                api_key=api_key,
                temperature=0.3,
                max_tokens=900
            )
            
            response = await asyncio.to_thread(
                llm.invoke,
                [{"role": "user", "content": polish_prompt}]
            )
            
            # Update the response
            polished = original.copy()
            polished.final_response_markdown = response.content
            
            # Update quality metrics
            polished.quality.clarity = min(1.0, original.quality.clarity + 0.1)
            polished.quality.completeness = min(1.0, original.quality.completeness + 0.1)
            
            return polished
            
        except Exception as e:
            logger.error(f"Polish pass failed: {e}")
            return original
    
    def _create_fallback_response(self, query: str, error: str) -> UnifiedReasoningOutput:
        """Create a fallback response when reasoning fails."""
        return UnifiedReasoningOutput(
            analysis=QueryAnalysis(
                intent="Error in processing query",
                emotion=EmotionState.NEUTRAL,
                complexity=ComplexityLevel.MEDIUM,
                root_cause_hypotheses=["System error occurred"]
            ),
            solution=Solution(
                primary_steps=[
                    SolutionStep(
                        step=1,
                        action="Please try rephrasing your question",
                        why="This helps our system better understand your needs",
                        verify="Submit your question again"
                    )
                ],
                fallback_steps=[],
                prevention=["Provide clear, specific details about your issue"]
            ),
            final_response_markdown=f"""
I apologize, but I encountered an issue processing your request. 

**What happened:** {error}

**What you can do:**
1. Try rephrasing your question with more specific details
2. If the issue persists, please contact support

I'm here to help once we resolve this technical issue.
""",
            reasoning_ui=UIReasoning(
                summary="Technical issue prevented proper analysis of the query.",
                decision_path=[
                    UIDecisionStep(
                        label="Error Detection",
                        action="Identified processing failure",
                        evidence=error[:100]
                    ),
                    UIDecisionStep(
                        label="Fallback Response",
                        action="Provided error guidance",
                        evidence=None
                    )
                ],
                assumptions=[],
                confidence=0.3,
                flags=["processing_error"]
            ),
            quality=QualityMetrics(
                completeness=0.3,
                clarity=0.7,
                confidence=0.3
            )
        )
    
    def _create_partial_response(self, content: str, error: str) -> UnifiedReasoningOutput:
        """Create partial response when parsing fails but we have content."""
        # Try to extract the final response at least
        final_response = content[:1500] if len(content) > 1500 else content
        
        return UnifiedReasoningOutput(
            analysis=QueryAnalysis(
                intent="Query processed with parsing issues",
                emotion=EmotionState.NEUTRAL,
                complexity=ComplexityLevel.MEDIUM,
                root_cause_hypotheses=["Partial response available"]
            ),
            solution=Solution(
                primary_steps=[],
                fallback_steps=[],
                prevention=[]
            ),
            final_response_markdown=final_response,
            reasoning_ui=UIReasoning(
                summary="Response generated but formatting issues occurred.",
                decision_path=[
                    UIDecisionStep(
                        label="Response Generation",
                        action="Generated response content",
                        evidence="Partial content available"
                    )
                ],
                assumptions=[],
                confidence=0.5,
                flags=["parsing_error"]
            ),
            quality=QualityMetrics(
                completeness=0.5,
                clarity=0.6,
                confidence=0.5
            )
        )