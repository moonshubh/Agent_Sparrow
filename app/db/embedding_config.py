"""Central embedding configuration for Gemini embeddings.

Single source of truth to avoid dimensionality mismatches across the codebase.
"""

from __future__ import annotations

from typing import List
import logging

logger = logging.getLogger(__name__)

# Model and dimension constants
MODEL_NAME = "models/gemini-embedding-001"
EXPECTED_DIM = 3072


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
