"""Playbooks module for issue-category playbook management.

This module provides:
- PlaybookExtractor: Extract playbooks from KB articles and macros
- PlaybookEnricher: Learn new playbook entries from resolved conversations

Usage:
    from app.agents.unified.playbooks import PlaybookExtractor, PlaybookEnricher

    # Extract playbook for a category
    extractor = PlaybookExtractor()
    playbook = await extractor.build_playbook_with_learned(category="account_setup")

    # Learn from a resolved conversation
    enricher = PlaybookEnricher()
    entry_id = await enricher.extract_from_conversation(
        conversation_id="session-123",
        messages=conversation_messages,
        category="account_setup",
    )
"""

from app.agents.unified.playbooks.extractor import (
    Playbook,
    PlaybookEntry,
    PlaybookExtractor,
)
from app.agents.unified.playbooks.enricher import PlaybookEnricher

__all__ = [
    "Playbook",
    "PlaybookEntry",
    "PlaybookExtractor",
    "PlaybookEnricher",
]
