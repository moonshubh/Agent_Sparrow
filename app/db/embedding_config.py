"""Central embedding configuration for Gemini embeddings.

Single source of truth to avoid dimensionality mismatches across the codebase.
Now sources configuration from the centralized model registry.
"""

from __future__ import annotations

from typing import List
import logging

from app.core.config import get_models_config

logger = logging.getLogger(__name__)

# Model and dimension constants - sourced from registry
_config = get_models_config()
embedding_cfg = _config.internal["embedding"]
MODEL_NAME = embedding_cfg.model_id
if not MODEL_NAME:
    raise ValueError("Embedding model_id is empty")

_dims = embedding_cfg.embedding_dims
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
