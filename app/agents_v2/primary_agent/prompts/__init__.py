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

# Backward compatibility shims for deprecated imports
try:
    # Import legacy classes if they exist
    from .deprecated_prompts import LegacyPromptSystem
except ImportError:
    # Create stub for backward compatibility
    class LegacyPromptSystem:
        def __init__(self):
            import warnings
            warnings.warn(
                "LegacyPromptSystem is deprecated. Use model-specific factory instead.",
                DeprecationWarning,
                stacklevel=2
            )

# Additional compatibility aliases
PromptSystem = LegacyPromptSystem  # Legacy alias

__all__ = [
    "EmotionTemplates",
    "ResponseFormatter",
    "AgentSparrowV9Prompts",
    # Legacy compatibility
    "LegacyPromptSystem",
    "PromptSystem"
]