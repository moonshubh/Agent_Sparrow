"""
Configuration management for OCR fallback functionality.
Provides configurable parameters for text confidence scoring and processing.
"""

import os
import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

@dataclass
class ConfidenceWeights:
    """Configuration for text confidence scoring weights."""
    
    # Primary weights for confidence calculation
    valid_word_ratio: float = 0.5     # Weight for dictionary word ratio
    alpha_ratio: float = 0.3          # Weight for alphabetic character ratio  
    space_ratio: float = 0.2          # Weight for whitespace ratio
    
    # Scaling factors for ratios
    alpha_ratio_scale: float = 2.0    # Scale factor for alpha ratio (max 1.0)
    space_ratio_scale: float = 5.0    # Scale factor for space ratio (max 1.0)
    
    # Penalty factors
    high_digit_threshold: float = 0.5 # Threshold for high digit ratio penalty
    high_digit_penalty: float = 0.7   # Penalty multiplier for high digit content
    
    def validate(self) -> bool:
        """Validate that weights sum to approximately 1.0 and are reasonable."""
        total_weight = self.valid_word_ratio + self.alpha_ratio + self.space_ratio
        
        if not (0.95 <= total_weight <= 1.05):
            logger.warning(f"Confidence weights sum to {total_weight:.3f}, should be close to 1.0")
        
        # Check individual weights are reasonable
        for field_name, value in asdict(self).items():
            if field_name.endswith('_ratio') and not field_name.endswith('_scale'):
                if not (0.0 <= value <= 1.0):
                    logger.warning(f"Weight {field_name}={value} should be between 0.0 and 1.0")
                    return False
        
        return True

@dataclass
class OCRFallbackConfig:
    """Complete configuration for OCR fallback functionality."""
    
    # Confidence scoring weights
    confidence_weights: ConfidenceWeights
    
    # Text processing thresholds
    min_word_count: int = 3           # Minimum words for reasonable confidence
    min_char_count: int = 10          # Minimum characters for reasonable confidence
    low_text_confidence: float = 0.3  # Confidence for very short text
    
    # Word corpus settings
    use_nltk_corpus: bool = True      # Whether to use NLTK word corpus
    min_word_length: int = 2          # Minimum word length for validation
    
    # Quality thresholds for OCR decision
    poor_extraction_threshold: int = 50          # Min chars to consider extraction adequate
    special_char_ratio_threshold: float = 0.3   # Max special char ratio before OCR
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.confidence_weights.validate():
            logger.warning("Invalid confidence weights configuration")

class OCRConfigManager:
    """Manages loading and updating OCR configuration from various sources."""
    
    def __init__(self, config_file: Optional[Path] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_file: Path to JSON configuration file. Defaults to ocr_config.json
        """
        if config_file is None:
            config_file = Path(__file__).parent / "ocr_config.json"
        
        self.config_file = config_file
        self._config: Optional[OCRFallbackConfig] = None
    
    def _create_default_config(self) -> OCRFallbackConfig:
        """Create default configuration."""
        return OCRFallbackConfig(
            confidence_weights=ConfidenceWeights()
        )
    
    def _load_from_file(self) -> Optional[OCRFallbackConfig]:
        """Load configuration from JSON file."""
        try:
            if not self.config_file.exists():
                logger.info(f"Config file {self.config_file} not found, using defaults")
                return None
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Parse confidence weights
            weights_data = config_data.get('confidence_weights', {})
            confidence_weights = ConfidenceWeights(**weights_data)
            
            # Parse main config
            config_data['confidence_weights'] = confidence_weights
            config = OCRFallbackConfig(**config_data)
            
            logger.info(f"Loaded OCR configuration from {self.config_file}")
            return config
            
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error(f"Failed to load OCR config from {self.config_file}: {e}")
            return None
    
    def _load_from_env(self, base_config: OCRFallbackConfig) -> OCRFallbackConfig:
        """Override configuration with environment variables."""
        
        # Environment variable mapping
        env_mappings = {
            'OCR_VALID_WORD_WEIGHT': ('confidence_weights', 'valid_word_ratio'),
            'OCR_ALPHA_WEIGHT': ('confidence_weights', 'alpha_ratio'),
            'OCR_SPACE_WEIGHT': ('confidence_weights', 'space_ratio'),
            'OCR_USE_NLTK': ('use_nltk_corpus', None),
            'OCR_MIN_WORD_LENGTH': ('min_word_length', None),
            'OCR_MIN_WORD_COUNT': ('min_word_count', None),
            'OCR_MIN_CHAR_COUNT': ('min_char_count', None),
        }
        
        config_dict = asdict(base_config)
        
        for env_var, (field_path, sub_field) in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                try:
                    # Convert to appropriate type
                    if 'WEIGHT' in env_var or field_path in ['low_text_confidence', 'special_char_ratio_threshold']:
                        converted_value = float(env_value)
                    elif field_path == 'use_nltk_corpus':
                        converted_value = env_value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        converted_value = int(env_value)
                    
                    # Set the value
                    if sub_field:
                        config_dict[field_path][sub_field] = converted_value
                    else:
                        config_dict[field_path] = converted_value
                    
                    logger.debug(f"Override {field_path}.{sub_field or ''} with {env_value}")
                    
                except ValueError as e:
                    logger.warning(f"Invalid environment variable {env_var}={env_value}: {e}")
        
        # Reconstruct config objects
        confidence_weights = ConfidenceWeights(**config_dict['confidence_weights'])
        config_dict['confidence_weights'] = confidence_weights
        
        return OCRFallbackConfig(**config_dict)
    
    def get_config(self, force_reload: bool = False) -> OCRFallbackConfig:
        """
        Get current configuration, loading if necessary.
        
        Args:
            force_reload: Force reload from file and environment
            
        Returns:
            Current OCR configuration
        """
        if self._config is None or force_reload:
            # Try to load from file first
            config = self._load_from_file()
            
            # Fall back to defaults if file loading failed
            if config is None:
                config = self._create_default_config()
            
            # Apply environment variable overrides
            config = self._load_from_env(config)
            
            self._config = config
        
        return self._config
    
    def save_config(self, config: Optional[OCRFallbackConfig] = None) -> bool:
        """
        Save configuration to file.
        
        Args:
            config: Configuration to save, uses current if None
            
        Returns:
            True if saved successfully
        """
        if config is None:
            config = self.get_config()
        
        try:
            # Convert to JSON-serializable format
            config_dict = asdict(config)
            
            # Ensure parent directory exists
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved OCR configuration to {self.config_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save OCR config to {self.config_file}: {e}")
            return False

# Global configuration manager instance
_config_manager = OCRConfigManager()

def get_ocr_config(force_reload: bool = False) -> OCRFallbackConfig:
    """Convenience function to get OCR configuration."""
    return _config_manager.get_config(force_reload=force_reload)

def get_confidence_weights() -> ConfidenceWeights:
    """Convenience function to get confidence weights."""
    return get_ocr_config().confidence_weights