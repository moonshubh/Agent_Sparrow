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
    def __init__(self, model_name: str, api_key: str, temperature: Optional[float] = None):
        if ChatOpenAI is None:
            raise RuntimeError("langchain-openai not installed. Add 'langchain-openai' to requirements.txt")
        # Default medium reasoning effort for gpt5-mini if supported by OpenAI
        # We pass through via model_kwargs so newer SDKs can use it.
        reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT", "medium")
        init_kwargs = {
            "model": model_name,
            "api_key": api_key,
            "reasoning": {"effort": reasoning_effort},
        }
        if temperature is not None:
            init_kwargs["temperature"] = temperature
        self._inner = ChatOpenAI(**init_kwargs)
        self.model = model_name
        self.model_name = model_name
        self.api_key = api_key
        self.temperature = temperature
        self.streaming = getattr(self._inner, "streaming", False)

    def bind_tools(self, tools: Any) -> "BaseChatModel":
        return self  # Tool binding handled at caller level for now

    async def ainvoke(self, messages: List[BaseMessage]) -> Any:
        return await self._inner.ainvoke(messages)

class OpenAIGPT5MiniAdapter(ProviderAdapter):
    provider = "openai"
    # Use the official model ID by default
    model_name = "gpt-5-mini-2025-08-07"

    def get_system_prompt(self, version: str = "latest") -> str:
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
        temp_env = os.getenv("PRIMARY_AGENT_TEMPERATURE")
        temperature = float(temp_env) if temp_env is not None else None
        # If langchain-openai is not present, raise a clear error
        model = _OpenAIModelWrapper(model_name=self.model_name, api_key=key, temperature=temperature)
        return model

    async def load_reasoning_model(
        self,
        *,
        api_key: Optional[str] = None,
        thinking_budget: Optional[int] = None,
        **kwargs,
    ) -> BaseChatModel:
        return await self.load_model(api_key=api_key, **kwargs)

# Registration
from app.providers.registry import register_adapter
# Register both legacy and official IDs for compatibility
register_adapter("openai", "gpt5-mini", OpenAIGPT5MiniAdapter)
register_adapter("openai", "gpt-5-mini-2025-08-07", OpenAIGPT5MiniAdapter)
register_adapter("openai", "gpt-5-mini", OpenAIGPT5MiniAdapter)
