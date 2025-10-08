"""Compat wrapper for embedding utilities (Phase 1).

Canonical path moving to app.db.embedding.utils; currently re-exports
from app.db.embedding_utils to avoid breaking changes.
"""
from __future__ import annotations

try:
    from app.db.embedding_utils import (
        find_similar_documents,  # noqa: F401
        find_similar_feedme_examples,  # noqa: F401
        find_combined_similar_content,  # noqa: F401
        generate_embeddings_for_pending_content,  # noqa: F401
        generate_feedme_embeddings,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

__all__ = [
    "find_similar_documents",
    "find_similar_feedme_examples",
    "find_combined_similar_content",
    "generate_embeddings_for_pending_content",
    "generate_feedme_embeddings",
]
