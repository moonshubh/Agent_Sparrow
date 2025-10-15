"""Zendesk integration: webhook capture + 30-minute batched posting.

Components:
- security.py: HMAC verification for Zendesk webhooks
- client.py: Minimal Zendesk REST client for adding internal notes
- endpoints.py: FastAPI routes (webhook, health, feature flag toggle)
- scheduler.py: Background loop that runs every N minutes and posts notes
"""

from .endpoints import router as router  # re-export for app include

__all__ = ["router"]
