"""
MB-Sparrow Primary Agent Module.

This module provides the primary customer support agent with advanced
reasoning capabilities, structured troubleshooting, and comprehensive
error handling.
"""

from .agent import run_primary_agent
from .schemas import PrimaryAgentState

# Exception hierarchy
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

__all__ = [
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
]