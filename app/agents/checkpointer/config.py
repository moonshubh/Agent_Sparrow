"""Backward-compatible re-export for deprecated checkpointer module."""

from __future__ import annotations

from app.agents.harness.persistence.config import CheckpointerConfig

__all__ = ["CheckpointerConfig"]
