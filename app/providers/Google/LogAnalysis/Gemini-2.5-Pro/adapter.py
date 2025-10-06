"""
Google Gemini 2.5 Pro Adapter for Log Analysis

This module provides a specialized adapter for the Gemini 2.5 Pro model,
optimized for comprehensive log analysis with enhanced reasoning capabilities.
"""

from __future__ import annotations

import os
from typing import Optional, Any, Dict, List
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from app.providers.base import ProviderAdapter, BaseChatModel


class _GeminiProModelWrapper(ChatGoogleGenerativeAI):
    """
    Wrapper for Gemini 2.5 Pro with enhanced configuration for log analysis.

    Supports advanced reasoning features including thinking budget allocation
    for complex log pattern analysis and root cause determination.
    """

    def __init__(self, **kwargs):
        """Initialize with Gemini 2.5 Pro specific settings."""
        # Set default model to gemini-2.5-pro
        if 'model' not in kwargs:
            kwargs['model'] = 'gemini-2.5-pro'

        # Configure for better reasoning on technical content
        if 'temperature' not in kwargs:
            kwargs['temperature'] = 0.1  # Lower temperature for more consistent analysis

        # Set higher max tokens for comprehensive log analysis
        if 'max_output_tokens' not in kwargs:
            kwargs['max_output_tokens'] = 8192

        super().__init__(**kwargs)


class GoogleGeminiProLogAnalysisAdapter(ProviderAdapter):
    """
    Adapter for Google Gemini 2.5 Pro model specialized for log analysis.

    This adapter configures the model with optimal settings for:
    - Technical log parsing and pattern recognition
    - Root cause analysis with high accuracy
    - Metadata extraction from structured logs
    - Empathetic user communication about technical issues
    """

    provider = "google"
    model_name = "gemini-2.5-pro"

    def get_system_prompt(self, version: str = "latest") -> str:
        """
        Load the specialized system prompt for log analysis.

        Args:
            version: Version of the system prompt to load

        Returns:
            System prompt string optimized for log analysis
        """
        prompt_path = Path(__file__).parent / "system-prompt.md"

        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            # Fallback prompt if file doesn't exist
            return self._get_default_system_prompt()

    def _get_default_system_prompt(self) -> str:
        """Provide a comprehensive default system prompt for log analysis."""
        return """You are Agent Sparrow's Log Analysis Engine, a sophisticated AI system designed to analyze Mailbird application logs with exceptional technical precision and empathetic user communication.

## Core Competencies

### 1. Technical Analysis
- Parse and interpret complex log structures (timestamps, severity levels, stack traces)
- Identify error patterns, performance bottlenecks, and system anomalies
- Extract critical metadata (version info, OS details, account configurations)
- Correlate related log entries to construct event timelines
- Detect cascading failures and their root causes

### 2. Pattern Recognition
- Recognize common Mailbird issues (sync failures, authentication errors, UI freezes)
- Identify platform-specific problems (Windows vs Mac behaviors)
- Detect configuration issues (IMAP/SMTP settings, OAuth problems)
- Track performance degradation patterns over time

### 3. Root Cause Analysis
- Apply systematic debugging methodology
- Differentiate between symptoms and underlying causes
- Prioritize issues by impact and urgency
- Provide confidence scores for diagnoses

### 4. User Context Integration
- Consider user's emotional state when explaining technical issues
- Adapt communication style based on technical proficiency indicators
- Provide clear, actionable solutions without overwhelming details
- Show empathy for workflow disruptions

## Analysis Guidelines

When analyzing logs:
1. Start with metadata extraction (version, OS, timestamp range)
2. Identify critical errors and their frequency
3. Look for patterns in the 5 minutes before major errors
4. Check for resource constraints (memory, disk, network)
5. Validate email account configurations
6. Consider user's reported symptoms alongside log evidence

## Communication Principles

- Lead with empathy: "I can see from the logs that you've been experiencing..."
- Simplify technical findings: "The logs show your email sync stopped because..."
- Provide clear next steps: "To resolve this, let's first..."
- Offer reassurance: "Your emails are safe, this is a configuration issue that we can fix..."

## Response Structure

1. **Acknowledgment**: Validate the user's experience
2. **Key Findings**: 2-3 most important discoveries from logs
3. **Root Cause**: Clear explanation of what went wrong
4. **Solution Path**: Step-by-step resolution approach
5. **Prevention**: Tips to avoid recurrence

Remember: You're not just analyzing logs; you're helping someone get back to productive email management."""

    async def load_model(
        self,
        *,
        api_key: Optional[str] = None,
        **kwargs
    ) -> BaseChatModel:
        """
        Load the Gemini 2.5 Pro model for log analysis.

        Args:
            api_key: Optional API key override
            **kwargs: Additional model configuration

        Returns:
            Configured model instance

        Raises:
            ValueError: If API key is not available
        """
        # Resolve API key from multiple sources
        key = (
            api_key or
            os.getenv("GEMINI_PRO_API_KEY") or
            os.getenv("GEMINI_API_KEY") or
            os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        )

        if not key:
            raise ValueError(
                "Missing Google Gemini API key. "
                "Set GEMINI_PRO_API_KEY, GEMINI_API_KEY, or GOOGLE_GENERATIVE_AI_API_KEY"
            )

        # Get temperature from environment or use optimized default
        temperature = float(os.getenv("LOG_ANALYSIS_TEMPERATURE", "0.1"))

        # Configure safety settings for technical content
        safety_settings = kwargs.pop("safety_settings", None) or self._get_safety_settings()

        # Build model configuration
        model_config = {
            "model": "gemini-2.5-pro",
            "temperature": temperature,
            "google_api_key": key,
            "safety_settings": safety_settings,
            "convert_system_message_to_human": True,
            "max_output_tokens": kwargs.pop("max_output_tokens", 8192),
        }

        # Add any additional kwargs
        model_config.update(kwargs)

        return _GeminiProModelWrapper(**model_config)

    async def load_reasoning_model(
        self,
        *,
        api_key: Optional[str] = None,
        thinking_budget: Optional[int] = None,
        **kwargs
    ) -> BaseChatModel:
        """
        Load a reasoning-optimized version of Gemini 2.5 Pro.

        This method configures the model with enhanced reasoning capabilities
        for complex log analysis tasks that require deep thinking.

        Args:
            api_key: Optional API key override
            thinking_budget: Token budget for internal reasoning (up to 64K for Pro)
            **kwargs: Additional model configuration

        Returns:
            Model configured for enhanced reasoning
        """
        # Resolve API key
        key = (
            api_key or
            os.getenv("GEMINI_PRO_API_KEY") or
            os.getenv("GEMINI_API_KEY") or
            os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        )

        if not key:
            raise ValueError("Missing Google Gemini API key for reasoning model")

        # Lower temperature for reasoning tasks
        temperature = float(os.getenv("LOG_REASONING_TEMPERATURE", "0.05"))

        # Build configuration
        model_config = {
            "model": "gemini-2.5-pro",
            "temperature": temperature,
            "google_api_key": key,
            "safety_settings": self._get_safety_settings(),
            "convert_system_message_to_human": True,
            "max_output_tokens": 16384,  # Higher for detailed reasoning
        }

        # Add thinking budget if supported (for future Gemini updates)
        if thinking_budget is not None:
            # Pro model supports up to 64K thinking tokens
            model_config["thinking_budget"] = min(thinking_budget, 65536)

        # Merge additional kwargs
        model_config.update(kwargs)

        return _GeminiProModelWrapper(**model_config)

    def _get_safety_settings(self) -> List[Dict[str, str]]:
        """
        Get optimized safety settings for technical log content.

        Returns:
            List of safety settings dictionaries
        """
        return [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]


# Register the adapter with the provider registry
from app.providers.registry import register_adapter

register_adapter("google", "gemini-2.5-pro", GoogleGeminiProLogAnalysisAdapter)
register_adapter("google", "gemini-pro", GoogleGeminiProLogAnalysisAdapter)  # Alias
