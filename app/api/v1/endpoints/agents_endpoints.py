from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.metadata import list_agents, get_agent_metadata

router = APIRouter()


class AgentMeta(BaseModel):
    id: str
    destination: str
    name: str
    description: str
    tools: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)
    icon: Optional[str] = None


@router.get("/agents", response_model=List[AgentMeta])
async def list_all_agents() -> List[AgentMeta]:
    agents = list_agents()
    # Pydantic coercion handles normalization
    return [
        AgentMeta(**{k: v for k, v in a.items() if k in AgentMeta.model_fields})
        for a in agents
    ]


@router.get("/agents/{agent_id}", response_model=AgentMeta)
async def get_agent(agent_id: str) -> AgentMeta:
    meta = get_agent_metadata(agent_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return AgentMeta(**{k: v for k, v in meta.items() if k in AgentMeta.model_fields})
