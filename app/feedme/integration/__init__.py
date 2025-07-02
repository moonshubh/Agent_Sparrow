"""
FeedMe v2.0 Integration Module

Integration components for connecting FeedMe with other systems,
specifically the Primary Agent knowledge retrieval system.
"""

from .knowledge_source import FeedMeKnowledgeSource
from .primary_agent_connector import PrimaryAgentConnector

__all__ = [
    'FeedMeKnowledgeSource',
    'PrimaryAgentConnector'
]