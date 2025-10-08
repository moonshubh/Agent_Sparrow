from __future__ import annotations

import os
from typing import Optional
from app.providers.adapters import load_model, default_provider, default_model_for_provider

async def get_primary_agent_model(*, api_key: Optional[str] = None, provider: Optional[str] = None, model: Optional[str] = None):
    """
    Resolve the primary agent model using the providers registry.
    Falls back to env defaults if not specified.
    """
    p = (provider or default_provider()).lower()
    m = (model or default_model_for_provider(p)).lower()
    return await load_model(p, m, api_key=api_key)