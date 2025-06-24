"""
Agent Sparrow - Prompt Loading and Configuration System

This module provides a flexible system for loading, configuring, and
managing Agent Sparrow prompts with versioning and validation capabilities.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
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
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initializes a PromptLoader instance with optional configuration file path.
        
        If a config path is provided, it is stored for later use. Initializes internal caches for prompts and their metadata.
        """
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path
        self._cached_prompts: Dict[str, str] = {}
        self._prompt_metadata: Dict[str, PromptMetadata] = {}
        
    def load_prompt(self, config: Optional[PromptLoadConfig] = None) -> str:
        """
        Loads and assembles an Agent Sparrow prompt according to the specified configuration.
        
        If a prompt matching the configuration is cached, returns the cached version; otherwise, builds the prompt based on the selected version, applies any custom components, validates the result, caches it, and stores associated metadata.
        
        Parameters:
            config (Optional[PromptLoadConfig]): Configuration specifying prompt version, included features, custom components, and environment.
        
        Returns:
            str: The fully assembled system prompt string ready for use with a language model.
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
            last_updated="2024-06-24",  # Would be dynamic in real implementation
            environment=config.environment,
            validation_status=validation_result
        )
        
        self.logger.info(f"Loaded Agent Sparrow prompt: {cache_key}")
        return prompt
    
    def _build_sparrow_prompt(self, config: PromptLoadConfig) -> str:
        """
        Constructs the Agent Sparrow system prompt based on the provided configuration.
        
        Parameters:
        	config (PromptLoadConfig): Configuration specifying which components and features to include in the prompt.
        
        Returns:
        	str: The assembled Agent Sparrow prompt string.
        """
        prompt_config = PromptConfig(
            include_reasoning=config.include_reasoning,
            include_emotions=config.include_emotions,
            include_technical=config.include_technical,
            quality_enforcement=config.quality_enforcement,
            debug_mode=config.debug_mode
        )
        
        return AgentSparrowPrompts.build_system_prompt(prompt_config)
    
    def _load_legacy_prompt(self) -> str:
        """
        Return the original Mailbird prompt string used as a legacy fallback or for comparison purposes.
        """
        # This would contain the original prompt from agent.py
        return """# Enhanced System Prompt for the Mailbird Customer Success Agent

You are the **Mailbird Customer Success Expert** – a highly skilled, empathetic, and knowledgeable assistant dedicated to delivering exceptional support experiences...

[Rest of original prompt would be here]"""
    
    def _apply_custom_components(self, prompt: str, custom_components: Dict[str, str]) -> str:
        """
        Inserts custom components into the prompt at designated locations based on component type.
        
        Custom components are added as follows:
        - "custom_identity" is prepended to the prompt.
        - "custom_instructions" is appended to the prompt.
        - "custom_examples" is inserted before the "Quality Assurance Checklist" section, if present.
        
        Parameters:
            prompt (str): The original prompt string.
            custom_components (Dict[str, str]): Mapping of component names to their content.
        
        Returns:
            str: The prompt with custom components inserted.
        """
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
        """
        Validates the structure and content of a prompt against required sections, length constraints, and formatting standards.
        
        Returns:
            str: "valid" if the prompt passes all checks, otherwise "warning".
        """
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
        
        # Check prompt length (should be reasonable for context window)
        if len(prompt) > 50000:  # ~12.5k tokens
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
        """
        Generate a unique string key representing the given prompt configuration for caching purposes.
        
        The key incorporates configuration attributes and a hash of the sorted custom components to ensure uniqueness for each distinct configuration.
        """
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
        """
        Return a list of component names that will be included in the prompt based on the provided configuration.
        
        Parameters:
        	config (PromptLoadConfig): The configuration specifying which prompt features to include.
        
        Returns:
        	List[str]: Names of the components included in the assembled prompt.
        """
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
        """
        Retrieve metadata for a prompt configuration, loading the prompt if necessary.
        
        Parameters:
        	config (Optional[PromptLoadConfig]): The configuration for which to retrieve prompt metadata. If not provided, the default configuration is used.
        
        Returns:
        	PromptMetadata: Metadata describing the loaded prompt, including version, token estimate, included components, environment, and validation status.
        """
        if config is None:
            config = PromptLoadConfig()
            
        cache_key = self._generate_cache_key(config)
        
        # Load prompt if not already cached
        if cache_key not in self._prompt_metadata:
            self.load_prompt(config)
            
        return self._prompt_metadata[cache_key]
    
    def clear_cache(self) -> None:
        """
        Clears all cached prompts and associated metadata from the loader.
        """
        self._cached_prompts.clear()
        self._prompt_metadata.clear()
        self.logger.info("Prompt cache cleared")
    
    def list_available_versions(self) -> List[str]:
        """
        Return a list of all available prompt version identifiers as strings.
        """
        return [version.value for version in PromptVersion]
    
    def compare_prompts(self, config1: PromptLoadConfig, config2: PromptLoadConfig) -> Dict[str, Any]:
        """
        Compares two prompt configurations and summarizes their differences.
        
        Parameters:
            config1 (PromptLoadConfig): The first prompt configuration to compare.
            config2 (PromptLoadConfig): The second prompt configuration to compare.
        
        Returns:
            Dict[str, Any]: A dictionary containing the lengths of both prompts, their length and token count differences, differences in included components, and their respective versions.
        """
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
        """
        Export the given prompt configuration and its metadata to a JSON file for version control.
        
        The exported file includes the prompt version, configuration options, custom components, and associated metadata.
        """
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
        """
        Imports a prompt configuration from a JSON file and returns a PromptLoadConfig instance.
        
        Parameters:
            input_path (Path): Path to the JSON file containing the prompt configuration.
        
        Returns:
            PromptLoadConfig: The imported prompt configuration object.
        """
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
    """
    Returns the global singleton instance of the PromptLoader, creating it if it does not already exist.
    """
    global _global_prompt_loader
    if _global_prompt_loader is None:
        _global_prompt_loader = PromptLoader()
    return _global_prompt_loader


def load_agent_sparrow_prompt(config: Optional[PromptLoadConfig] = None) -> str:
    """
    Loads and returns the Agent Sparrow prompt using the specified configuration.
    
    Parameters:
        config (Optional[PromptLoadConfig]): Configuration options for prompt assembly. If not provided, defaults are used.
    
    Returns:
        str: The assembled Agent Sparrow prompt string.
    """
    loader = get_prompt_loader()
    return loader.load_prompt(config)