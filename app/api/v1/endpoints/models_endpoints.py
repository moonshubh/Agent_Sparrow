from __future__ import annotations

from typing import Dict, List, Literal
from fastapi import APIRouter, Query

router = APIRouter()

Provider = Literal["google", "openai"]
AgentType = Literal["primary", "log_analysis"]

# Simple static catalog with sensible defaults; can be replaced with dynamic lookup
FALLBACK_MODELS: Dict[Provider, List[str]] = {
    "google": ["gemini-2.5-flash-preview-09-2025", "gemini-2.5-flash"],
    "openai": ["gpt-5-mini", "gpt5-mini"],
}

@router.get("/models")
async def list_models(agent_type: AgentType = Query("primary")):
    """
    Returns available models by provider for the requested agent type.
    Frontend accepts either {providers: {google:[], openai:[]}} or flat {google:[], openai:[]}.
    """
    # TODO: Expand with per-agent logic if needed
    providers = FALLBACK_MODELS
    return {"providers": providers}
