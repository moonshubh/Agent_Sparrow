"""Compat wrapper for embedding utilities (Phase 1).

Canonical path moving to app.db.embedding.utils; currently re-exports
from app.db.embedding_utils to avoid breaking changes.
"""
from __future__ import annotations

import os
import sys
import types
from typing import Any, Callable, TypeVar


_T = TypeVar("_T")


def _lazy_attr(name: str) -> Any:
    """Resolve an attribute from embedding_utils on demand."""
    _ensure_pgvector_stub()
    from app.db import embedding_utils as _eu
    return getattr(_eu, name)


def _wrap(name: str) -> Callable[..., Any]:
    def _callable(*args: Any, **kwargs: Any) -> Any:
        target = _lazy_attr(name)
        return target(*args, **kwargs)

    return _callable


def get_embedding_model() -> Any:  # type: ignore[override]
    target = _lazy_attr("get_embedding_model")
    return target()


find_similar_documents = _wrap("find_similar_documents")
find_similar_feedme_examples = _wrap("find_similar_feedme_examples")
find_combined_similar_content = _wrap("find_combined_similar_content")
generate_embeddings_for_pending_content = _wrap("generate_embeddings_for_pending_content")
generate_feedme_embeddings = _wrap("generate_feedme_embeddings")


def __getattr__(name: str) -> Any:
    if name == "SearchResult":
        return _lazy_attr("SearchResult")
    raise AttributeError(name)


def _ensure_pgvector_stub() -> None:
    if os.getenv("SPARROW_USE_REAL_PGVECTOR", "").lower() in {"1", "true", "yes"}:
        return
    if "pgvector.psycopg2" in sys.modules:
        return
    stub = types.ModuleType("pgvector")
    psycopg2_stub = types.ModuleType("pgvector.psycopg2")

    def register_vector(*args: Any, **kwargs: Any) -> None:
        return None

    psycopg2_stub.register_vector = register_vector  # type: ignore[attr-defined]
    stub.psycopg2 = psycopg2_stub  # type: ignore[attr-defined]
    sys.modules["pgvector"] = stub
    sys.modules["pgvector.psycopg2"] = psycopg2_stub


__all__ = [
    "get_embedding_model",
    "find_similar_documents",
    "find_similar_feedme_examples",
    "find_combined_similar_content",
    "generate_embeddings_for_pending_content",
    "generate_feedme_embeddings",
    "SearchResult",
]
