from __future__ import annotations

from typing import Protocol, Any, List, Optional, Dict, Awaitable, runtime_checkable
from langchain_core.messages import BaseMessage

@runtime_checkable
class BaseChatModel(Protocol):
    """
    Minimal async chat model protocol expected by the reasoning engine.

    Implementations MUST provide:
    - ainvoke(messages): Awaitable response with `.content` (str)
    - Optionally `.bind_tools(tools)` returning a BaseChatModel
    """
    def bind_tools(self, tools: Any) -> "BaseChatModel": ...
    async def ainvoke(self, messages: List[BaseMessage]) -> Any: ...

class ProviderAdapter(Protocol):
    """
    Adapter interface for a provider+model combination.
    """
    provider: str
    model_name: str

    def get_system_prompt(self) -> str: ...
    async def load_model(self, *, api_key: Optional[str] = None, **kwargs) -> BaseChatModel: ...