from __future__ import annotations

from dataclasses import is_dataclass, replace
from typing import Any

from langchain_core.runnables import RunnableConfig

from langgraph.checkpoint.memory import InMemorySaver

from .postgres_checkpointer import _redact_data_urls  # reuse the same sanitizer


class SanitizingMemorySaver(InMemorySaver):
    """In-memory checkpointer that redacts inline data URLs.

    This prevents large base64 attachment payloads from accumulating in RAM when
    checkpointing is enabled without a database backend.
    """

    async def aput(  # type: ignore[override]
        self,
        config: RunnableConfig,
        checkpoint: Any,
        metadata: Any,
        new_versions: Any = None,
    ) -> RunnableConfig:
        try:
            if (
                is_dataclass(checkpoint)
                and not isinstance(checkpoint, type)
                and hasattr(checkpoint, "channel_values")
            ):
                channel_values = getattr(checkpoint, "channel_values")
                if isinstance(channel_values, dict):
                    checkpoint = replace(
                        checkpoint,
                        channel_values=_redact_data_urls(channel_values),
                    )
            if isinstance(metadata, dict):
                metadata = _redact_data_urls(metadata)
        except Exception:
            # Never fail checkpointing due to sanitization.
            pass
        return await super().aput(config, checkpoint, metadata, new_versions)
