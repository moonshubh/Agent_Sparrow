"""Compat wrapper for embedding utilities (Phase 1).

Canonical path moving to app.db.embedding.utils; currently re-exports
from app.db.embedding_utils to avoid breaking changes.
"""
from __future__ import annotations

# Dynamic forwarding for monkeypatch compatibility in tests
def get_embedding_model():
    from app.db import embedding_utils as _eu
    return _eu.get_embedding_model()

try:
    from app.db.embedding_utils import (
        get_embedding_model,  # noqa: F401
        find_similar_documents,  # noqa: F401
        find_similar_feedme_examples,  # noqa: F401
        find_combined_similar_content,  # noqa: F401
        generate_embeddings_for_pending_content,  # noqa: F401
        generate_feedme_embeddings,  # noqa: F401
        SearchResult,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

__all__ = [
    "get_embedding_model",
    "find_similar_documents",
    "find_similar_feedme_examples",
    "find_combined_similar_content",
    "generate_embeddings_for_pending_content",
    "generate_feedme_embeddings",
    "SearchResult",
]
