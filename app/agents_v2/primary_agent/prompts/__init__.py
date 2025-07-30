"""
Agent Sparrow - Modular Prompt System

This module provides a sophisticated, maintainable prompt system for the
Agent Sparrow customer success agent with emotional intelligence,
advanced reasoning, and structured troubleshooting capabilities.
"""

# Legacy prompt system removed - using model-specific factory instead
from .emotion_templates import EmotionTemplates
from .response_formatter import ResponseFormatter
from .agent_sparrow_v9_prompts import AgentSparrowV9Prompts

__all__ = [
    "EmotionTemplates",
    "ResponseFormatter", 
    "AgentSparrowV9Prompts"
]