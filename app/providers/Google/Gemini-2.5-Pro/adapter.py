from __future__ import annotations

import os
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from app.providers.base import ProviderAdapter, BaseChatModel


class _GeminiProWrapper(ChatGoogleGenerativeAI):
    """Thin wrapper to satisfy BaseChatModel Protocol."""
    pass


class GoogleGeminiProAdapter(ProviderAdapter):
    provider = "google"
    model_name = "gemini-2.5-pro"

    async def load_model(self, *, api_key: Optional[str] = None, **kwargs) -> BaseChatModel:
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        if not key:
            raise ValueError("Missing Google Gemini API key")
        temperature = float(os.getenv("PRIMARY_AGENT_TEMPERATURE", "0.2"))
        safety_settings = kwargs.get("safety_settings", None)
        return _GeminiProWrapper(
            model=self.model_name,
            temperature=temperature,
            google_api_key=key,
            safety_settings=safety_settings,
            convert_system_message_to_human=True,
        )

    async def load_reasoning_model(
        self,
        *,
        api_key: Optional[str] = None,
        thinking_budget: Optional[int] = None,
        **kwargs,
    ) -> BaseChatModel:
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        if not key:
            raise ValueError("Missing Google Gemini API key")
        temperature = float(os.getenv("PRIMARY_AGENT_TEMPERATURE", "0.2"))
        safety_settings = kwargs.get("safety_settings", None)
        model_kwargs = {
            "model": self.model_name,
            "temperature": temperature,
            "google_api_key": key,
            "safety_settings": safety_settings,
            "convert_system_message_to_human": True,
        }
        if thinking_budget is not None:
            model_kwargs["thinking_budget"] = thinking_budget
        return _GeminiProWrapper(**model_kwargs)


# Register adapter
from app.providers.registry import register_adapter
register_adapter("google", "gemini-2.5-pro", GoogleGeminiProAdapter)
