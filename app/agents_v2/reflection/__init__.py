"""Reflection module exposing schema and node for quality assurance.

This module defines the `ReflectionFeedback` schema used to represent
quality evaluation results and provides `reflection_node`, which can be
plugged into a LangGraph workflow to evaluate agent responses and decide
whether further refinement or escalation is required.
"""

from .schema import ReflectionFeedback  # noqa: F401
from .node import reflection_node, reflection_route  # noqa: F401
