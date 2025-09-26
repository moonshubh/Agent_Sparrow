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

    def get_system_prompt(self, version: str = "latest") -> str: ...
    async def load_model(self, *, api_key: Optional[str] = None, **kwargs) -> BaseChatModel: ...
    async def load_reasoning_model(
        self,
        *,
        api_key: Optional[str] = None,
        thinking_budget: Optional[int] = None,
        **kwargs,
    ) -> BaseChatModel: ...
