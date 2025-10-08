"""
Agent Sparrow - Prompt Loading and Configuration System

This module provides a flexible system for loading, configuring, and
managing Agent Sparrow prompts with versioning and validation capabilities.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import logging
from pathlib import Path

from .agent_sparrow_prompts import AgentSparrowPrompts, PromptConfig, PromptComponent


class PromptVersion(Enum):
    """Available prompt versions for Agent Sparrow"""
    V1_BASIC = "v1.0-basic"
    V2_ENHANCED = "v2.0-enhanced" 
    V3_SPARROW = "v3.0-sparrow"  # Current sophisticated version
    LEGACY_MAILBIRD = "legacy-mailbird"  # Original Mailbird prompt


@dataclass
class PromptLoadConfig:
    """Configuration for prompt loading and assembly"""
    version: PromptVersion = PromptVersion.V3_SPARROW
    include_reasoning: bool = True
    include_emotions: bool = True
    include_technical: bool = True
    quality_enforcement: bool = True
    debug_mode: bool = False
    custom_components: Dict[str, str] = field(default_factory=dict)
    environment: str = "production"  # production, staging, development


@dataclass
class PromptMetadata:
    """Metadata about loaded prompt"""
    version: str
    token_count_estimate: int
    components_included: List[str]
    last_updated: str
    environment: str
    validation_status: str


class PromptLoader:
    """
    Sophisticated prompt loading and management system
    
    Provides version control, configuration management, and validation
    for Agent Sparrow prompts with support for A/B testing and
    environment-specific configurations.
    """
    
    # Maximum allowed prompt length in characters (~12.5k tokens at 4 chars/token)
    MAX_PROMPT_LENGTH = 50000  # characters
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize PromptLoader
        
        Args:
            config_path: Optional path to configuration file
        """
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path
        self._cached_prompts: Dict[str, str] = {}
        self._prompt_metadata: Dict[str, PromptMetadata] = {}
        
    def load_prompt(self, config: Optional[PromptLoadConfig] = None) -> str:
        """
        Load and assemble Agent Sparrow prompt based on configuration
        
        Args:
            config: PromptLoadConfig specifying how to build the prompt
            
        Returns:
            Complete system prompt string ready for LLM
        """
        if config is None:
            config = PromptLoadConfig()
            
        # Create cache key
        cache_key = self._generate_cache_key(config)
        
        # Check cache first
        if cache_key in self._cached_prompts:
            self.logger.debug(f"Retrieved prompt from cache: {cache_key}")
            return self._cached_prompts[cache_key]
        
        # Build prompt based on version and configuration
        if config.version == PromptVersion.V3_SPARROW:
            prompt = self._build_sparrow_prompt(config)
        elif config.version == PromptVersion.LEGACY_MAILBIRD:
            prompt = self._load_legacy_prompt()
        else:
            # Default to current sophisticated version
            prompt = self._build_sparrow_prompt(config)
            
        # Apply custom components if specified
        if config.custom_components:
            prompt = self._apply_custom_components(prompt, config.custom_components)
            
        # Validate prompt
        validation_result = self._validate_prompt(prompt, config)
        
        # Cache the result
        self._cached_prompts[cache_key] = prompt
        
        # Store metadata
        self._prompt_metadata[cache_key] = PromptMetadata(
            version=config.version.value,
            token_count_estimate=AgentSparrowPrompts.estimate_token_count(),
            components_included=self._get_included_components(config),
            last_updated=datetime.now().strftime("%Y-%m-%d"),  # Dynamic date in YYYY-MM-DD format
            environment=config.environment,
            validation_status=validation_result
        )
        
        self.logger.info(f"Loaded Agent Sparrow prompt: {cache_key}")
        return prompt
    
    def _build_sparrow_prompt(self, config: PromptLoadConfig) -> str:
        """Build the sophisticated Agent Sparrow prompt"""
        prompt_config = PromptConfig(
            include_reasoning=config.include_reasoning,
            include_emotions=config.include_emotions,
            include_technical=config.include_technical,
            quality_enforcement=config.quality_enforcement,
            debug_mode=config.debug_mode
        )
        
        return AgentSparrowPrompts.build_system_prompt(prompt_config)
    
    def _load_legacy_prompt(self) -> str:
        """Load the original Mailbird prompt from external file
        
        Returns:
            str: The full content of the legacy prompt
            
        Raises:
            FileNotFoundError: If the legacy prompt file is not found
            IOError: If there's an error reading the file
        """
        try:
            # Get the directory of the current file
            current_dir = Path(__file__).parent
            # Build the path to the legacy prompt file
            legacy_prompt_path = current_dir / 'templates' / 'legacy_prompt.txt'
            
            # Read and return the prompt content
            with open(legacy_prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
                
        except FileNotFoundError as e:
            self.logger.error(f"Legacy prompt file not found: {e}")
            raise
        except IOError as e:
            self.logger.error(f"Error reading legacy prompt file: {e}")
            raise
    
    def _apply_custom_components(self, prompt: str, custom_components: Dict[str, str]) -> str:
        """Apply custom prompt components for specific use cases"""
        enhanced_prompt = prompt
        
        for component_name, component_content in custom_components.items():
            # Insert custom components at appropriate locations
            if component_name == "custom_identity":
                enhanced_prompt = component_content + "\n\n" + enhanced_prompt
            elif component_name == "custom_instructions":
                enhanced_prompt = enhanced_prompt + "\n\n" + component_content
            elif component_name == "custom_examples":
                # Insert before quality checklist
                insert_point = enhanced_prompt.find("## Quality Assurance Checklist")
                if insert_point != -1:
                    enhanced_prompt = (
                        enhanced_prompt[:insert_point] + 
                        component_content + "\n\n" + 
                        enhanced_prompt[insert_point:]
                    )
        
        return enhanced_prompt
    
    def _validate_prompt(self, prompt: str, config: PromptLoadConfig) -> str:
        """Validate prompt structure and content"""
        validation_issues = []
        
        # Check required sections
        required_sections = [
            "Agent Identity & Mission",
            "Advanced Reasoning Framework", 
            "Emotional Intelligence",
            "Technical Troubleshooting Framework"
        ]
        
        for section in required_sections:
            if section not in prompt:
                validation_issues.append(f"Missing required section: {section}")
        
        # Check prompt length against maximum allowed
        if len(prompt) > self.MAX_PROMPT_LENGTH:
            validation_issues.append("Prompt may be too long for context window")
        
        # Check for mandatory formatting requirements
        if "## " not in prompt:
            validation_issues.append("Missing proper Markdown headers")
            
        if "```" not in prompt:
            validation_issues.append("Missing code blocks for examples")
        
        if validation_issues:
            self.logger.warning(f"Prompt validation issues: {validation_issues}")
            return "warning"
        else:
            return "valid"
    
    def _generate_cache_key(self, config: PromptLoadConfig) -> str:
        """Generate unique cache key for prompt configuration"""
        key_components = [
            config.version.value,
            str(config.include_reasoning),
            str(config.include_emotions),
            str(config.include_technical),
            str(config.quality_enforcement),
            str(config.debug_mode),
            config.environment,
            str(hash(str(sorted(config.custom_components.items()))))
        ]
        return "_".join(key_components)
    
    def _get_included_components(self, config: PromptLoadConfig) -> List[str]:
        """Get list of components included in the prompt"""
        components = ["base_identity", "response_templates"]
        
        if config.include_reasoning:
            components.append("reasoning_framework")
        if config.include_emotions:
            components.append("emotional_intelligence")
        if config.include_technical:
            components.append("technical_expertise")
        if config.quality_enforcement:
            components.append("quality_checklist")
        if config.debug_mode:
            components.append("debug_mode")
            
        return components
    
    def get_prompt_metadata(self, config: Optional[PromptLoadConfig] = None) -> PromptMetadata:
        """Get metadata about the loaded prompt"""
        if config is None:
            config = PromptLoadConfig()
            
        cache_key = self._generate_cache_key(config)
        
        # Load prompt if not already cached
        if cache_key not in self._prompt_metadata:
            self.load_prompt(config)
            
        return self._prompt_metadata[cache_key]
    
    def clear_cache(self) -> None:
        """Clear prompt cache"""
        self._cached_prompts.clear()
        self._prompt_metadata.clear()
        self.logger.info("Prompt cache cleared")
    
    def list_available_versions(self) -> List[str]:
        """List all available prompt versions"""
        return [version.value for version in PromptVersion]
    
    def compare_prompts(self, config1: PromptLoadConfig, config2: PromptLoadConfig) -> Dict[str, Any]:
        """Compare two prompt configurations"""
        prompt1 = self.load_prompt(config1)
        prompt2 = self.load_prompt(config2)
        
        metadata1 = self.get_prompt_metadata(config1)
        metadata2 = self.get_prompt_metadata(config2)
        
        return {
            "prompt1_length": len(prompt1),
            "prompt2_length": len(prompt2),
            "length_difference": len(prompt1) - len(prompt2),
            "token_count_diff": metadata1.token_count_estimate - metadata2.token_count_estimate,
            "components_diff": {
                "only_in_1": set(metadata1.components_included) - set(metadata2.components_included),
                "only_in_2": set(metadata2.components_included) - set(metadata1.components_included),
                "common": set(metadata1.components_included) & set(metadata2.components_included)
            },
            "versions": {
                "config1": metadata1.version,
                "config2": metadata2.version
            }
        }
    
    def export_prompt_config(self, config: PromptLoadConfig, output_path: Path) -> None:
        """Export prompt configuration to file for version control"""
        export_data = {
            "version": config.version.value,
            "configuration": {
                "include_reasoning": config.include_reasoning,
                "include_emotions": config.include_emotions,
                "include_technical": config.include_technical,
                "quality_enforcement": config.quality_enforcement,
                "debug_mode": config.debug_mode,
                "environment": config.environment
            },
            "custom_components": config.custom_components,
            "metadata": self.get_prompt_metadata(config).__dict__
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
            
        self.logger.info(f"Prompt configuration exported to: {output_path}")
    
    def import_prompt_config(self, input_path: Path) -> PromptLoadConfig:
        """Import prompt configuration from file"""
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        config = PromptLoadConfig(
            version=PromptVersion(data["version"]),
            include_reasoning=data["configuration"]["include_reasoning"],
            include_emotions=data["configuration"]["include_emotions"],
            include_technical=data["configuration"]["include_technical"],
            quality_enforcement=data["configuration"]["quality_enforcement"],
            debug_mode=data["configuration"]["debug_mode"],
            environment=data["configuration"]["environment"],
            custom_components=data.get("custom_components", {})
        )
        
        self.logger.info(f"Prompt configuration imported from: {input_path}")
        return config


# Global prompt loader instance
_global_prompt_loader = None


def get_prompt_loader() -> PromptLoader:
    """Get global prompt loader instance (singleton pattern)"""
    global _global_prompt_loader
    if _global_prompt_loader is None:
        _global_prompt_loader = PromptLoader()
    return _global_prompt_loader


def load_agent_sparrow_prompt(config: Optional[PromptLoadConfig] = None) -> str:
    """Convenience function to load Agent Sparrow prompt"""
    loader = get_prompt_loader()
    return loader.load_prompt(config)