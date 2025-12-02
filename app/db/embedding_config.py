"""Central embedding configuration for Gemini embeddings.

Single source of truth to avoid dimensionality mismatches across the codebase.
Now sources configuration from the centralized model registry.
"""

from __future__ import annotations

from typing import List
import logging

from app.core.config import get_registry

logger = logging.getLogger(__name__)

# Model and dimension constants - sourced from registry
_registry = get_registry()
if not hasattr(_registry, "embedding") or not getattr(_registry, "embedding", None):
    raise ValueError("Registry missing 'embedding' configuration")

MODEL_NAME = getattr(_registry.embedding, "id", None)
if not MODEL_NAME:
    raise ValueError("Registry embedding.id is empty")

_dims = getattr(_registry.embedding, "embedding_dims", None)
if not _dims:
    logger.warning("Registry embedding_dims missing; defaulting to 3072")
EXPECTED_DIM = _dims or 3072


def assert_dim(vec: List[float], context: str = "embedding") -> None:
    """Raise a ValueError if vector dimensionality is unexpected."""
    if len(vec) != EXPECTED_DIM:
        logger.error(
            "Embedding dimension mismatch in %s: got %s, expected %s",
            context,
            len(vec),
            EXPECTED_DIM,
        )
        raise ValueError(
            f"Embedding dimension mismatch in {context}: got {len(vec)}, expected {EXPECTED_DIM}"
        )
