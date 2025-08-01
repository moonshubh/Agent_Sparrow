"""
Advanced Token Estimation Service for MB-Sparrow

Provides model-specific token estimation with configurable ratios,
context-aware calculations, and performance optimization.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ModelFamily(Enum):
    """Model families with different tokenization characteristics."""
    GEMINI = "gemini"
    GPT = "gpt"
    CLAUDE = "claude"
    KIMI = "kimi"
    UNKNOWN = "unknown"


@dataclass
class TokenizationConfig:
    """Configuration for token estimation by model family."""
    chars_per_token: float
    input_overhead: int
    output_base: int
    context_multiplier: float
    max_context_length: int
    name: str


class TokenEstimationService:
    """
    Advanced token estimation service with model-specific calculations.
    
    Provides accurate token estimates for rate limiting and cost calculation
    with configurable parameters and context-aware adjustments.
    """
    
    # Model-specific tokenization configurations
    TOKENIZATION_CONFIGS: Dict[ModelFamily, TokenizationConfig] = {
        ModelFamily.GEMINI: TokenizationConfig(
            chars_per_token=3.5,  # Gemini has efficient tokenization
            input_overhead=50,    # System prompt overhead
            output_base=800,      # Conservative estimate for response length
            context_multiplier=1.1,  # Context increases token count slightly
            max_context_length=1000000,  # Gemini 2.5 context limit
            name="Gemini"
        ),
        ModelFamily.GPT: TokenizationConfig(
            chars_per_token=4.0,  # Standard GPT tokenization
            input_overhead=75,
            output_base=1000,
            context_multiplier=1.2,
            max_context_length=128000,
            name="GPT"
        ),
        ModelFamily.CLAUDE: TokenizationConfig(
            chars_per_token=3.8,  # Similar to GPT but slightly more efficient
            input_overhead=60,
            output_base=900,
            context_multiplier=1.15,
            max_context_length=200000,
            name="Claude"
        ),
        ModelFamily.KIMI: TokenizationConfig(
            chars_per_token=4.2,  # More tokens per character for Chinese models
            input_overhead=80,
            output_base=1200,
            context_multiplier=1.25,
            max_context_length=200000,
            name="Kimi"
        ),
        ModelFamily.UNKNOWN: TokenizationConfig(
            chars_per_token=4.0,  # Conservative fallback
            input_overhead=100,
            output_base=1500,
            context_multiplier=1.3,
            max_context_length=100000,
            name="Unknown"
        )
    }
    
    # Model name to family mapping
    MODEL_FAMILY_MAPPING = {
        "gemini-2.5-flash": ModelFamily.GEMINI,
        "gemini-2.5-pro": ModelFamily.GEMINI,
        "gemini-1.5-flash": ModelFamily.GEMINI,
        "gemini-1.5-pro": ModelFamily.GEMINI,
        "gpt-4": ModelFamily.GPT,
        "gpt-4-turbo": ModelFamily.GPT,
        "gpt-3.5-turbo": ModelFamily.GPT,
        "claude-3-opus": ModelFamily.CLAUDE,
        "claude-3-sonnet": ModelFamily.CLAUDE,
        "claude-3-haiku": ModelFamily.CLAUDE,
        "kimi-k2": ModelFamily.KIMI,
        "moonshot-v1": ModelFamily.KIMI,
    }

    def __init__(self, custom_configs: Optional[Dict[str, TokenizationConfig]] = None, max_cache_size: int = 1000):
        """
        Initialize token estimation service.
        
        Args:
            custom_configs: Optional custom tokenization configurations
            max_cache_size: Maximum cache size to prevent memory issues
        """
        self.custom_configs = custom_configs or {}
        self._char_count_cache: Dict[str, int] = {}
        self._max_cache_size = max_cache_size
        self._per_message_overhead = 10  # Default per-message overhead tokens
    
    def set_per_message_overhead(self, overhead: int) -> None:
        """Set configurable per-message overhead tokens."""
        self._per_message_overhead = max(0, overhead)  # Ensure non-negative
        
    def estimate_tokens(
        self, 
        args: tuple, 
        kwargs: dict,
        model_name: Optional[str] = None,
        include_context: bool = True
    ) -> int:
        """
        Estimate tokens for a request with model-specific calculations.
        
        Args:
            args: Function arguments 
            kwargs: Function keyword arguments
            model_name: Name of the model for specific estimation
            include_context: Whether to include context multiplier
            
        Returns:
            Estimated token count
        """
        try:
            # Get model family and configuration
            model_family = self._get_model_family(model_name)
            config = self.TOKENIZATION_CONFIGS[model_family]
            
            # Extract messages from arguments
            messages = self._extract_messages(args, kwargs)
            if not messages:
                return self._get_fallback_estimate(config)
            
            # Calculate character count with caching and size limit
            cache_key = self._generate_cache_key(messages)
            if cache_key in self._char_count_cache:
                total_chars = self._char_count_cache[cache_key]
            else:
                total_chars = self._count_characters(messages)
                # Check cache size limit
                if len(self._char_count_cache) >= self._max_cache_size:
                    # Remove oldest entries (simple FIFO eviction)
                    oldest_key = next(iter(self._char_count_cache))
                    del self._char_count_cache[oldest_key]
                self._char_count_cache[cache_key] = total_chars
                
            # Apply model-specific estimation
            estimated_tokens = self._calculate_tokens(
                total_chars, config, include_context, len(messages)
            )
            
            # Validate against context limits
            if estimated_tokens > config.max_context_length:
                logger.warning(
                    f"Estimated tokens ({estimated_tokens}) exceed model limit "
                    f"({config.max_context_length}) for {config.name}"
                )
                
            return estimated_tokens
            
        except Exception as e:
            logger.error(f"Error in token estimation: {e}")
            return self._get_emergency_fallback()
    
    def _get_model_family(self, model_name: Optional[str]) -> ModelFamily:
        """Get model family from model name."""
        if not model_name:
            return ModelFamily.UNKNOWN
            
        # Check exact matches first
        if model_name in self.MODEL_FAMILY_MAPPING:
            return self.MODEL_FAMILY_MAPPING[model_name]
        
        # Check partial matches
        model_lower = model_name.lower()
        for pattern, family in [
            ("gemini", ModelFamily.GEMINI),
            ("gpt", ModelFamily.GPT),
            ("claude", ModelFamily.CLAUDE),
            ("kimi", ModelFamily.KIMI),
            ("moonshot", ModelFamily.KIMI),
        ]:
            if pattern in model_lower:
                return family
                
        return ModelFamily.UNKNOWN
    
    def _extract_messages(self, args: tuple, kwargs: dict) -> Optional[List[Any]]:
        """Extract messages from function arguments."""
        # Try multiple extraction strategies
        
        # Strategy 1: Direct messages argument
        if 'messages' in kwargs:
            return kwargs['messages']
            
        # Strategy 2: First argument is iterable (but not string)
        if args and hasattr(args[0], '__iter__') and not isinstance(args[0], (str, bytes)):
            try:
                messages = list(args[0])
                if messages and hasattr(messages[0], 'content'):
                    return messages
            except (TypeError, IndexError):
                pass
        
        # Strategy 3: Look for message-like objects in kwargs
        for key in ['input', 'prompt', 'query', 'text']:
            if key in kwargs:
                value = kwargs[key]
                if isinstance(value, (list, tuple)):
                    return list(value)
                elif isinstance(value, str):
                    return [MockMessage(value)]
        
        # Strategy 4: Look in nested structures
        for arg in args:
            if isinstance(arg, dict):
                if 'messages' in arg:
                    return arg['messages']
                    
        return None
    
    def _count_characters(self, messages: List[Any]) -> int:
        """Count total characters in messages."""
        total_chars = 0
        
        for msg in messages:
            try:
                # Handle different message formats
                if hasattr(msg, 'content'):
                    content = str(msg.content)
                elif hasattr(msg, 'text'):
                    content = str(msg.text)
                elif isinstance(msg, dict):
                    content = str(msg.get('content', msg.get('text', str(msg))))
                else:
                    content = str(msg)
                
                total_chars += len(content)
                
            except Exception as e:
                logger.debug(f"Error processing message: {e}")
                total_chars += 100  # Conservative fallback
                
        return total_chars
    
    def _calculate_tokens(
        self, 
        char_count: int, 
        config: TokenizationConfig,
        include_context: bool,
        message_count: int
    ) -> int:
        """Calculate tokens using model-specific configuration."""
        # Base token calculation
        base_tokens = int(char_count / config.chars_per_token)
        
        # Add overhead for system prompts and formatting (configurable per-message overhead)
        per_message_overhead = getattr(self, '_per_message_overhead', 10)  # Default 10 tokens per message
        overhead_tokens = config.input_overhead + (message_count * per_message_overhead)
        
        # Calculate input tokens
        input_tokens = base_tokens + overhead_tokens
        
        # Apply context multiplier if requested
        if include_context:
            input_tokens = int(input_tokens * config.context_multiplier)
        
        # Add estimated output tokens
        total_tokens = input_tokens + config.output_base
        
        return max(total_tokens, 100)  # Minimum reasonable estimate
    
    def _generate_cache_key(self, messages: List[Any]) -> str:
        """Generate cache key for message list."""
        try:
            # Create a hash based on message content
            content_parts = []
            for msg in messages[:5]:  # Only use first 5 messages for key
                if hasattr(msg, 'content'):
                    content_parts.append(str(msg.content)[:50])
                else:
                    content_parts.append(str(msg)[:50])
            
            cache_key = '|'.join(content_parts)
            return cache_key[:200]  # Limit key length
            
        except Exception:
            return f"fallback_{len(messages)}"
    
    def _get_fallback_estimate(self, config: TokenizationConfig) -> int:
        """Get fallback estimate when messages can't be extracted."""
        return config.input_overhead + config.output_base
    
    def _get_emergency_fallback(self) -> int:
        """Emergency fallback when all estimation fails."""
        return 2000  # Conservative high estimate
    
    def get_model_info(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get tokenization information for a model.
        
        Args:
            model_name: Name of the model
            
        Returns:
            Dictionary with model tokenization info
        """
        family = self._get_model_family(model_name)
        config = self.TOKENIZATION_CONFIGS[family]
        
        return {
            "model_name": model_name,
            "family": family.value,
            "config": {
                "chars_per_token": config.chars_per_token,
                "input_overhead": config.input_overhead,
                "output_base": config.output_base,
                "context_multiplier": config.context_multiplier,
                "max_context_length": config.max_context_length,
                "name": config.name
            }
        }
    
    def clear_cache(self):
        """Clear the character count cache."""
        self._char_count_cache.clear()
        logger.debug("Token estimation cache cleared")


class MockMessage:
    """Mock message class for string content."""
    
    def __init__(self, content: str):
        self.content = content


# Global service instance
_token_service: Optional[TokenEstimationService] = None


def get_token_estimation_service() -> TokenEstimationService:
    """Get global token estimation service."""
    global _token_service
    if _token_service is None:
        _token_service = TokenEstimationService()
    return _token_service


def estimate_tokens(
    args: tuple, 
    kwargs: dict,
    model_name: Optional[str] = None,
    include_context: bool = True
) -> int:
    """
    Convenience function for token estimation.
    
    Args:
        args: Function arguments
        kwargs: Function keyword arguments  
        model_name: Name of the model
        include_context: Whether to include context multiplier
        
    Returns:
        Estimated token count
    """
    service = get_token_estimation_service()
    return service.estimate_tokens(args, kwargs, model_name, include_context)