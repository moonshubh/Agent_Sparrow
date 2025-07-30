"""
MB-Sparrow - Primary Agent Model Adapter

This module provides a unified adapter layer for different LLM models,
ensuring consistent behavior across Gemini and OpenRouter models.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Union
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.outputs import ChatResult

from .llm_registry import SupportedModel, get_model_info

logger = logging.getLogger(__name__)


class ModelAdapter:
    """
    Adapter class that normalizes behavior across different LLM models.
    
    Ensures consistent:
    - Temperature settings (0.3 default)
    - Token limits (2048 default)
    - Response formatting (strip leading newlines)
    - Error handling
    - System message handling
    """
    
    def __init__(
        self,
        llm: BaseChatModel,
        model_type: Optional[SupportedModel] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048
    ):
        """
        Initialize the model adapter.
        
        Args:
            llm: The underlying LLM instance
            model_type: The type of model being adapted
            temperature: Temperature setting for generation (0.0-1.0)
            max_tokens: Maximum tokens to generate
        """
        self.llm = llm
        self.model_type = model_type
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Apply normalized settings
        self._apply_normalized_settings()
        
        logger.info(
            f"Model adapter initialized for {model_type.value if model_type else 'unknown'} "
            f"with temperature={temperature}, max_tokens={max_tokens}"
        )
    
    def _apply_normalized_settings(self) -> None:
        """Apply normalized settings to the underlying LLM."""
        # Try to set temperature and max_tokens if the model supports it
        if hasattr(self.llm, 'temperature'):
            self.llm.temperature = self.temperature
        
        if hasattr(self.llm, 'max_tokens'):
            self.llm.max_tokens = self.max_tokens
        elif hasattr(self.llm, 'max_output_tokens'):
            self.llm.max_output_tokens = self.max_tokens
    
    async def ainvoke(
        self,
        messages: List[BaseMessage],
        **kwargs: Any
    ) -> AIMessage:
        """
        Async invoke the model with normalized behavior.
        
        Args:
            messages: List of messages to send to the model
            **kwargs: Additional parameters
            
        Returns:
            AI response message with normalized formatting
        """
        try:
            # Preprocess messages for consistency
            processed_messages = self._preprocess_messages(messages)
            
            # Invoke the underlying model
            response = await self.llm.ainvoke(processed_messages, **kwargs)
            
            # Normalize the response
            return self._normalize_response(response)
            
        except Exception as e:
            logger.error(f"Error during model invocation: {str(e)}")
            raise
    
    def invoke(
        self,
        messages: List[BaseMessage],
        **kwargs: Any
    ) -> AIMessage:
        """
        Sync invoke the model with normalized behavior.
        
        Args:
            messages: List of messages to send to the model
            **kwargs: Additional parameters
            
        Returns:
            AI response message with normalized formatting
        """
        try:
            # Preprocess messages for consistency
            processed_messages = self._preprocess_messages(messages)
            
            # Invoke the underlying model
            response = self.llm.invoke(processed_messages, **kwargs)
            
            # Normalize the response
            return self._normalize_response(response)
            
        except Exception as e:
            logger.error(f"Error during model invocation: {str(e)}")
            raise
    
    def _preprocess_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Preprocess messages for consistent handling across models.
        
        Args:
            messages: Original messages
            
        Returns:
            Processed messages
        """
        processed = []
        
        # Some models handle system messages differently
        # Ensure consistent system message placement
        system_messages = [m for m in messages if isinstance(m, SystemMessage)]
        other_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        
        # Always put system messages first
        processed.extend(system_messages)
        processed.extend(other_messages)
        
        # Additional preprocessing based on model type
        if self.model_type == SupportedModel.KIMI_K2:
            # Kimi K2 needs enhanced empathy instructions
            processed = self._enhance_kimi_k2_messages(processed)
        
        return processed
    
    def _enhance_kimi_k2_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Enhance messages specifically for Kimi K2 to improve empathy and reduce sarcasm.
        
        Args:
            messages: List of messages to enhance
            
        Returns:
            Enhanced messages with Kimi K2-specific adjustments
        """
        enhanced_messages = []
        
        for message in messages:
            if isinstance(message, SystemMessage):
                # Add Kimi K2 specific empathy reminders to system messages
                enhanced_content = message.content + "\n\n" + self._get_kimi_k2_empathy_reminder()
                enhanced_messages.append(SystemMessage(content=enhanced_content))
            elif isinstance(message, HumanMessage):
                # Add context to human messages to encourage empathetic responses
                enhanced_content = self._add_empathy_context_to_human_message(message.content)
                enhanced_messages.append(HumanMessage(content=enhanced_content))
            else:
                enhanced_messages.append(message)
        
        return enhanced_messages
    
    def _get_kimi_k2_empathy_reminder(self) -> str:
        """Get Kimi K2 specific empathy reminder for system messages."""
        return """
### KIMI K2 FINAL EMPATHY CHECK

Before responding, ensure:
1. Your response starts with genuine emotional acknowledgment
2. You show understanding of their feelings/situation  
3. No sarcasm, dismissiveness, or overly direct language
4. Warm, supportive tone throughout
5. Partnership language ("we'll", "let's", "together")

Remember: You are exceptionally intelligent - use that intelligence to be exceptionally caring and empathetic.
"""
    
    def _add_empathy_context_to_human_message(self, content: str) -> str:
        """Add empathy context to human messages for Kimi K2."""
        return f"""Customer message: {content}

Remember to respond with genuine empathy and warmth. This person needs your help and deserves to feel supported and understood."""
    
    def _normalize_response(self, response: Union[AIMessage, ChatResult]) -> AIMessage:
        """
        Normalize the model response.
        
        Args:
            response: Raw response from the model
            
        Returns:
            Normalized AI message
        """
        # Extract content based on response type
        if isinstance(response, AIMessage):
            content = response.content
        elif isinstance(response, ChatResult):
            content = response.generations[0].message.content
        else:
            content = str(response)
        
        # Strip leading newlines and normalize whitespace
        content = self._strip_leading_newlines(content)
        content = self._normalize_whitespace(content)
        
        # Apply Kimi K2 specific post-processing if needed
        if self.model_type == SupportedModel.KIMI_K2:
            content = self._post_process_kimi_k2_response(content)
        
        # Create normalized AI message
        return AIMessage(content=content)
    
    def _strip_leading_newlines(self, content: str) -> str:
        """
        Strip leading newlines from content.
        
        Args:
            content: Original content
            
        Returns:
            Content with leading newlines removed
        """
        return content.lstrip('\n')
    
    def _normalize_whitespace(self, content: str) -> str:
        """
        Normalize whitespace in content.
        
        Args:
            content: Original content
            
        Returns:
            Content with normalized whitespace
        """
        # Remove excessive blank lines (more than 2 consecutive)
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # Ensure proper spacing around headers
        content = re.sub(r'(\n?)#{1,3}\s+', r'\n\n\g<0>', content)
        content = re.sub(r'^\n\n', '', content)  # Remove leading double newline
        
        return content.strip()
    
    def _post_process_kimi_k2_response(self, content: str) -> str:
        """
        Post-process Kimi K2 responses to reduce sarcasm and enhance empathy.
        
        Args:
            content: Original response content
            
        Returns:
            Enhanced response content with reduced sarcasm and improved empathy
        """
        # Remove potentially sarcastic phrases
        sarcastic_patterns = [
            (r'\bobviously\b', 'of course'),
            (r'\bclearly\b', 'as you can see'),
            (r'\bsimply\b', ''),
            (r'\bjust\b(?=\s+(click|do|try|use))', ''),  # Remove "just" before instructions
            (r'\bwell,\s*', ''),  # Remove dismissive "well,"
            (r'you should (have )?know(n)?', 'you might not be aware'),
            (r'(it|this) is basic', 'this is straightforward'),
        ]
        
        for pattern, replacement in sarcastic_patterns:
            content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
        
        # Ensure empathetic opening if missing
        if not self._has_empathetic_opening(content):
            content = self._add_empathetic_opening(content)
        
        # Clean up any double spaces or awkward phrasing from replacements
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'\s+([,.!?])', r'\1', content)  # Remove spaces before punctuation
        
        return content.strip()
    
    def _has_empathetic_opening(self, content: str) -> bool:
        """Check if the response starts with empathetic language."""
        empathy_indicators = [
            'i understand', 'i can see', 'i know how', 'that sounds', 'i can tell',
            'you\'re right', 'i completely understand', 'that must be', 'i realize',
            'i hear you', 'i feel', 'this is frustrating', 'that\'s concerning'
        ]
        
        first_sentence = content.split('.')[0].lower()
        return any(indicator in first_sentence for indicator in empathy_indicators)
    
    def _add_empathetic_opening(self, content: str) -> str:
        """Add an empathetic opening to responses that lack one."""
        # Simple empathetic opening that works for most technical issues
        empathetic_opening = "I understand how frustrating email issues can be. "
        return empathetic_opening + content
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the adapted model.
        
        Returns:
            Dictionary with model information
        """
        info = {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "model_type": self.model_type.value if self.model_type else "unknown"
        }
        
        if self.model_type:
            info.update(get_model_info(self.model_type))
        
        return info
    
    # Proxy other methods to the underlying LLM
    def __getattr__(self, name: str) -> Any:
        """Proxy undefined attributes to the underlying LLM."""
        return getattr(self.llm, name)