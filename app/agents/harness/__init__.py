"""Agent Harness package following DeepAgents patterns.

This package provides the harness adapter for creating Agent Sparrow
instances with proper middleware composition and backend abstractions.
"""

from __future__ import annotations

from .sparrow_harness import create_sparrow_agent, SparrowAgentConfig

__all__ = [
    "create_sparrow_agent",
    "SparrowAgentConfig",
]
