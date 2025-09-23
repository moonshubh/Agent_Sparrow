from __future__ import annotations

import os
from typing import Optional, Any, List
from langchain_core.messages import BaseMessage
from app.providers.base import ProviderAdapter, BaseChatModel

try:
    # Prefer langchain-openai if available
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:
    ChatOpenAI = None  # type: ignore

class _OpenAIModelWrapper:
    """
    Minimal wrapper to satisfy BaseChatModel using LangChain ChatOpenAI if available.
    """
    def __init__(self, model_name: str, api_key: str, temperature: float = 0.2):
        if ChatOpenAI is None:
            raise RuntimeError("langchain-openai not installed. Add 'langchain-openai' to requirements.txt")
        # Default medium reasoning effort for gpt5-mini if supported by OpenAI
        # We pass through via model_kwargs so newer SDKs can use it.
        reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT", "medium")
        model_kwargs = {"reasoning": {"effort": reasoning_effort}}
        self._inner = ChatOpenAI(model=model_name, temperature=temperature, api_key=api_key, model_kwargs=model_kwargs)

    def bind_tools(self, tools: Any) -> "BaseChatModel":
        return self  # Tool binding handled at caller level for now

    async def ainvoke(self, messages: List[BaseMessage]) -> Any:
        return await self._inner.ainvoke(messages)

class OpenAIGPT5MiniAdapter(ProviderAdapter):
    provider = "openai"
    # Use the official model ID by default
    model_name = "gpt-5-mini-2025-08-07"

    def get_system_prompt(self) -> str:
        prompt_path = os.path.join(os.path.dirname(__file__), "system-prompt.md")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return (
                "You are Agent Sparrow, a Mailbird support assistant. "
                "Be concise, accurate, and empathetic. Use tools when needed."
            )

    async def load_model(self, *, api_key: Optional[str] = None, **kwargs) -> BaseChatModel:
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("Missing OpenAI API key")
        temperature = float(os.getenv("PRIMARY_AGENT_TEMPERATURE", "0.2"))
        # If langchain-openai is not present, raise a clear error
        model = _OpenAIModelWrapper(model_name=self.model_name, api_key=key, temperature=temperature)
        return model

# Registration
from app.providers.registry import register_adapter
# Register both legacy and official IDs for compatibility
register_adapter("openai", "gpt5-mini", OpenAIGPT5MiniAdapter)
register_adapter("openai", "gpt-5-mini-2025-08-07", OpenAIGPT5MiniAdapter)
register_adapter("openai", "gpt-5-mini", OpenAIGPT5MiniAdapter)