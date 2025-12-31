"""Backward-compatible re-export for deprecated checkpointer module."""

from __future__ import annotations

from app.agents.harness.persistence.thread_manager import ThreadManager

__all__ = ["ThreadManager"]

