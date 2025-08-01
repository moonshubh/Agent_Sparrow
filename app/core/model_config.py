"""
Model Configuration Service for MB-Sparrow

Centralizes all model-specific configuration parameters, version strings,
and magic numbers to improve maintainability and reduce hardcoded values.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum
import os
import threading

logger = logging.getLogger(__name__)


class ModelType(Enum):
    """Supported model types with version information."""
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_FLASH = "gemini-2.5-flash" 
    KIMI_K2 = "kimi-k2"
    UNKNOWN = "unknown"


@dataclass
class ModelConfiguration:
    """Configuration for a specific model."""
    name: str
    version: str
    max_tokens: int
    default_temperature: float
    thinking_budget_default: Optional[int]
    supports_streaming: bool = True
    supports_function_calling: bool = True
    context_window: int = 128000
    cost_per_1k_tokens: float = 0.0
    recommended_use_cases: list[str] = field(default_factory=list)
    optimization_params: Dict[str, Any] = field(default_factory=dict)
    provider_config: Dict[str, Any] = field(default_factory=dict)  # Provider-specific settings


def _default_platforms() -> list[str]:
    """Default supported platforms."""
    return ["Windows 10/11", "macOS Catalina through Sequoia"]

def _default_ports() -> Dict[str, int]:
    """Default port configuration."""
    return {
        "imap_ssl": 993,
        "imap_starttls": 143,
        "smtp_starttls": 587,
        "smtp_ssl": 465
    }

def _default_thresholds() -> Dict[str, float]:
    """Default threshold configuration."""
    return {
        "confidence_threshold": 0.6,
        "similarity_threshold": 0.7,
        "content_length_minimum": 20.0
    }

@dataclass
class PromptConfiguration:
    """Configuration for prompt generation."""
    version: str = "v9.0"
    mailbird_version: str = "3.0+"
    supported_platforms: list[str] = field(default_factory=_default_platforms)
    default_ports: Dict[str, int] = field(default_factory=_default_ports)
    common_thresholds: Dict[str, float] = field(default_factory=_default_thresholds)


class ModelConfigurationService:
    """
    Service for managing model configurations and parameters.
    
    Provides centralized configuration management with environment variable
    support and runtime customization capabilities.
    """
    
    def __init__(self):
        """Initialize the configuration service."""
        self._model_configs = self._initialize_model_configs()
        self._prompt_config = self._initialize_prompt_config()
        self._config_lock = threading.Lock()  # Add instance-level lock for thread safety
    
    def _initialize_model_configs(self) -> Dict[ModelType, ModelConfiguration]:
        """Initialize model-specific configurations."""
        configs = {
            ModelType.GEMINI_2_5_PRO: ModelConfiguration(
                name="Gemini 2.5 Pro",
                version="2.5",
                max_tokens=self._safe_get_int("GEMINI_PRO_MAX_TOKENS", 4096),
                default_temperature=self._safe_get_float("GEMINI_PRO_TEMPERATURE", 0.2),
                thinking_budget_default=self._safe_get_int("GEMINI_PRO_THINKING_BUDGET", -1),
                context_window=self._safe_get_int("GEMINI_PRO_CONTEXT_WINDOW", 1000000),
                cost_per_1k_tokens=self._safe_get_float("GEMINI_PRO_COST_1K", 0.003),
                recommended_use_cases=[
                    "Complex technical troubleshooting",
                    "Multi-step problem analysis", 
                    "Advanced solution development",
                    "Comprehensive research tasks"
                ],
                optimization_params={
                    "top_p": 0.8,
                    "top_k": 40,
                    "max_thinking_depth": 5,
                    "enable_self_critique": True
                }
            ),
            
            ModelType.GEMINI_2_5_FLASH: ModelConfiguration(
                name="Gemini 2.5 Flash",
                version="2.5",
                max_tokens=self._safe_get_int("GEMINI_FLASH_MAX_TOKENS", 2048),
                default_temperature=self._safe_get_float("GEMINI_FLASH_TEMPERATURE", 0.3),
                thinking_budget_default=self._safe_get_int("GEMINI_FLASH_THINKING_BUDGET", 0),
                context_window=self._safe_get_int("GEMINI_FLASH_CONTEXT_WINDOW", 1000000),
                cost_per_1k_tokens=self._safe_get_float("GEMINI_FLASH_COST_1K", 0.001),
                recommended_use_cases=[
                    "Quick problem resolution",
                    "Standard troubleshooting",
                    "Routine customer queries",
                    "Fast response scenarios"
                ],
                optimization_params={
                    "top_p": 0.9,
                    "top_k": 40,
                    "response_speed_priority": True,
                    "enable_self_critique": False
                }
            ),
            
            ModelType.KIMI_K2: ModelConfiguration(
                name="Kimi K2",
                version="2.0",
                max_tokens=self._safe_get_int("KIMI_K2_MAX_TOKENS", 2048),
                default_temperature=self._safe_get_float("KIMI_K2_TEMPERATURE", 0.6),
                thinking_budget_default=None,  # Not supported
                context_window=self._safe_get_int("KIMI_K2_CONTEXT_WINDOW", 200000),
                cost_per_1k_tokens=self._safe_get_float("KIMI_K2_COST_1K", 0.002),
                recommended_use_cases=[
                    "Empathetic customer support",
                    "Emotional intelligence scenarios",
                    "Complex user interactions",
                    "Relationship building"
                ],
                optimization_params={
                    "frequency_penalty": 0.3,
                    "presence_penalty": 0.1,
                    "empathy_amplification": True,
                    "enable_self_critique": False
                },
                provider_config={
                    "provider": "openrouter",
                    "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                    "headers": {
                        "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://mailbird.com"),
                        "X-Title": os.getenv("OPENROUTER_TITLE", "MB-Sparrow Primary Agent")
                    },
                    "api_key_env": "OPENROUTER_API_KEY"
                }
            )
        }
        
        return configs
    
    def _safe_get_int(self, env_var: str, default: int) -> int:
        """Safely get integer from environment variable with error handling."""
        try:
            value = os.getenv(env_var)
            if value is None:
                return default
            return int(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid integer value for {env_var}: {os.getenv(env_var)}. Using default: {default}. Error: {e}")
            return default
    
    def _safe_get_float(self, env_var: str, default: float) -> float:
        """Safely get float from environment variable with error handling."""
        try:
            value = os.getenv(env_var)
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid float value for {env_var}: {os.getenv(env_var)}. Using default: {default}. Error: {e}")
            return default
    
    def _initialize_prompt_config(self) -> PromptConfiguration:
        """Initialize prompt configuration from environment variables."""
        return PromptConfiguration(
            version=os.getenv("AGENT_SPARROW_VERSION", "v9.0"),
            mailbird_version=os.getenv("MAILBIRD_VERSION", "3.0+"),
            supported_platforms=os.getenv(
                "SUPPORTED_PLATFORMS", 
                "Windows 10/11,macOS Catalina through Sequoia"
            ).split(","),
            default_ports={
                "imap_ssl": self._safe_get_int("IMAP_SSL_PORT", 993),
                "imap_starttls": self._safe_get_int("IMAP_STARTTLS_PORT", 143),
                "smtp_starttls": self._safe_get_int("SMTP_STARTTLS_PORT", 587),
                "smtp_ssl": self._safe_get_int("SMTP_SSL_PORT", 465)
            },
            common_thresholds={
                "confidence_threshold": self._safe_get_float("CONFIDENCE_THRESHOLD", 0.6),
                "similarity_threshold": self._safe_get_float("SIMILARITY_THRESHOLD", 0.7),
                "content_length_minimum": self._safe_get_float("CONTENT_LENGTH_MIN", 20.0)
            }
        )
    
    def get_model_config(self, model_type: ModelType) -> ModelConfiguration:
        """
        Get configuration for a specific model.
        
        Args:
            model_type: The model type to get configuration for
            
        Returns:
            ModelConfiguration for the specified model
            
        Raises:
            ValueError: If model type is not supported
        """
        if model_type not in self._model_configs:
            logger.warning(f"Unknown model type: {model_type}, using default config")
            return self._get_default_config(model_type)
        
        return self._model_configs[model_type]
    
    def get_prompt_config(self) -> PromptConfiguration:
        """Get prompt configuration."""
        return self._prompt_config
    
    def get_model_temperature(self, model_type: ModelType, optimization_level: str = "balanced") -> float:
        """
        Get optimal temperature for a model and optimization level.
        
        Args:
            model_type: The model type
            optimization_level: Optimization level (speed, balanced, quality, agentic)
            
        Returns:
            Optimal temperature value
        """
        config = self.get_model_config(model_type)
        base_temp = config.default_temperature
        
        # Adjust based on optimization level
        adjustments = {
            "speed": -0.1,
            "balanced": 0.0,
            "quality": -0.1,
            "agentic": 0.1
        }
        
        adjustment = adjustments.get(optimization_level.lower(), 0.0)
        return max(0.0, min(1.0, base_temp + adjustment))
    
    def get_model_max_tokens(self, model_type: ModelType, optimization_level: str = "balanced") -> int:
        """
        Get optimal max tokens for a model and optimization level.
        
        Args:
            model_type: The model type
            optimization_level: Optimization level
            
        Returns:
            Optimal max tokens value
        """
        config = self.get_model_config(model_type)
        base_tokens = config.max_tokens
        
        # Adjust based on optimization level
        if optimization_level.lower() == "speed":
            return min(base_tokens, 1500)  # Limit for speed
        elif optimization_level.lower() == "quality":
            return base_tokens  # Use full capacity
        
        return base_tokens
    
    def get_thinking_budget(self, model_type: ModelType, optimization_level: str = "balanced") -> Optional[int]:
        """
        Get thinking budget for models that support it.
        
        Args:
            model_type: The model type
            optimization_level: Optimization level
            
        Returns:
            Thinking budget value or None if not supported
        """
        config = self.get_model_config(model_type)
        
        if config.thinking_budget_default is None:
            return None
        
        # Adjust based on optimization level
        if optimization_level.lower() == "speed":
            return 0  # No thinking overhead
        elif optimization_level.lower() == "quality":
            return -1  # Dynamic thinking
        
        return config.thinking_budget_default
    
    def get_model_recommendations(self, use_case: str) -> list[ModelType]:
        """
        Get recommended models for a specific use case.
        
        Args:
            use_case: The use case description
            
        Returns:
            List of recommended models in order of preference
        """
        recommendations = []
        use_case_lower = use_case.lower()
        
        for model_type, config in self._model_configs.items():
            for recommended_case in config.recommended_use_cases:
                # Improved matching: check for phrase overlap rather than just individual keywords
                case_words = set(recommended_case.lower().split())
                query_words = set(use_case_lower.split())
                
                # Calculate overlap score
                overlap = len(case_words.intersection(query_words))
                if overlap > 0:
                    # Weight by relative overlap (overlap / total unique words)
                    specificity_score = overlap / len(case_words.union(query_words))
                    recommendations.append((model_type, specificity_score))
        
        # Sort by specificity score (higher is better)
        recommendations.sort(key=lambda x: x[1], reverse=True)
        return [model for model, _ in recommendations]
    
    def _get_default_config(self, model_type: ModelType) -> ModelConfiguration:
        """Get default configuration for unknown models."""
        return ModelConfiguration(
            name=model_type.value if model_type != ModelType.UNKNOWN else "Unknown Model",
            version="unknown",
            max_tokens=2048,
            default_temperature=0.3,
            thinking_budget_default=None,
            context_window=100000,
            cost_per_1k_tokens=0.005,
            recommended_use_cases=["General purpose"],
            optimization_params={}
        )
    
    def update_model_config(self, model_type: ModelType, **kwargs) -> None:
        """
        Update configuration for a model at runtime.
        
        Args:
            model_type: The model type to update
            **kwargs: Configuration parameters to update
        """
        with self._config_lock:  # Ensure thread-safe access to model configs
            if model_type not in self._model_configs:
                logger.warning(f"Cannot update config for unknown model: {model_type}")
                return
            
            config = self._model_configs[model_type]
            
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)
                    logger.info(f"Updated {model_type.value} config: {key} = {value}")
                else:
                    logger.warning(f"Unknown config parameter: {key} for model {model_type.value}")
    
    def get_all_supported_models(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all supported models.
        
        Returns:
            Dictionary with model information
        """
        result = {}
        
        for model_type, config in self._model_configs.items():
            result[model_type.value] = {
                "name": config.name,
                "version": config.version,
                "max_tokens": config.max_tokens,
                "context_window": config.context_window,
                "cost_per_1k_tokens": config.cost_per_1k_tokens,
                "recommended_use_cases": config.recommended_use_cases,
                "supports_thinking_budget": config.thinking_budget_default is not None
            }
        
        return result


# Global configuration service instance with thread safety
_config_service: Optional[ModelConfigurationService] = None
_config_service_lock = threading.Lock()


def get_model_config_service() -> ModelConfigurationService:
    """
    Get global model configuration service instance (thread-safe).
    
    Returns:
        ModelConfigurationService instance
    """
    global _config_service
    if _config_service is None:
        with _config_service_lock:
            # Double-check locking pattern
            if _config_service is None:
                _config_service = ModelConfigurationService()
    return _config_service


def get_model_config(model_name: str) -> ModelConfiguration:
    """
    Convenience function to get model configuration by name.
    
    Args:
        model_name: Name of the model
        
    Returns:
        ModelConfiguration for the model
    """
    service = get_model_config_service()
    
    # Map model name to ModelType
    model_mapping = {
        "gemini-2.5-pro": ModelType.GEMINI_2_5_PRO,
        "gemini-2.5-flash": ModelType.GEMINI_2_5_FLASH,
        "kimi-k2": ModelType.KIMI_K2
    }
    
    model_type = model_mapping.get(model_name.lower(), ModelType.UNKNOWN)
    return service.get_model_config(model_type)


def get_prompt_config() -> PromptConfiguration:
    """
    Convenience function to get prompt configuration.
    
    Returns:
        PromptConfiguration instance
    """
    service = get_model_config_service()
    return service.get_prompt_config()