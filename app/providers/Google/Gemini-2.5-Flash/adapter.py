from __future__ import annotations

import os
from typing import Optional, Any, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage
from app.providers.base import ProviderAdapter, BaseChatModel

class _GeminiModelWrapper(ChatGoogleGenerativeAI):
    """
    Thin wrapper to satisfy BaseChatModel Protocol.
    LangChain ChatGoogleGenerativeAI already supports ainvoke(messages).
    """
    pass

class GoogleGeminiFlashAdapter(ProviderAdapter):
    provider = "google"
    model_name = "gemini-2.5-flash"

    def get_system_prompt(self) -> str:
        # Load colocated system prompt
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
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        if not key:
            raise ValueError("Missing Google Gemini API key")
        temperature = float(os.getenv("PRIMARY_AGENT_TEMPERATURE", "0.2"))
        safety_settings = kwargs.get("safety_settings", None)
        model = _GeminiModelWrapper(
            model=self.model_name,
            temperature=temperature,
            google_api_key=key,
            safety_settings=safety_settings
        )
        return model

# Registration
from app.providers.registry import register_adapter
register_adapter("google", "gemini-2.5-flash", GoogleGeminiFlashAdapter)