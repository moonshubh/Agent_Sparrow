"""
MB-Sparrow Primary Agent Module.

This module provides the primary customer support agent with advanced
reasoning capabilities, structured troubleshooting, and comprehensive
error handling.
"""

def __getattr__(name: str):
    """Lazy imports for better startup performance."""
    if name == "run_primary_agent":
        from .agent import run_primary_agent
        return run_primary_agent
    elif name == "PrimaryAgentState":
        from .schemas import PrimaryAgentState
        return PrimaryAgentState
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

# Exception hierarchy - explicit imports for better IDE support and maintainability
from .exceptions import (
    AgentException,
    RateLimitException,
    InvalidAPIKeyException,
    TimeoutException,
    NetworkException,
    ConfigurationException,
    KnowledgeBaseException,
    ToolExecutionException,
    ReasoningException,
    ModelOverloadException,
    ErrorSeverity,
    create_exception_from_error
)

__all__ = (
    # Core functionality
    'run_primary_agent',
    'PrimaryAgentState',
    
    # Exceptions
    'AgentException',
    'RateLimitException',
    'InvalidAPIKeyException',
    'TimeoutException',
    'NetworkException',
    'ConfigurationException',
    'KnowledgeBaseException',
    'ToolExecutionException',
    'ReasoningException',
    'ModelOverloadException',
    'ErrorSeverity',
    'create_exception_from_error'
)