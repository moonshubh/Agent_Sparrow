from __future__ import annotations

import os
from typing import Optional, Any, Dict
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

    def get_system_prompt(self, version: str = "latest") -> str:
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

    def _build_model_kwargs(
        self,
        *,
        api_key: str,
        kwargs: Dict[str, Any],
        default_temperature_env: str = "PRIMARY_AGENT_TEMPERATURE",
    ) -> Dict[str, Any]:
        """Construct ChatGoogleGenerativeAI kwargs with safe overrides."""

        temperature_override = kwargs.get("temperature")
        safety_settings = kwargs.get("safety_settings")

        if temperature_override is None:
            temperature = float(os.getenv(default_temperature_env, "0.2"))
        else:
            temperature = float(temperature_override)

        model_kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "temperature": temperature,
            "google_api_key": api_key,
            "convert_system_message_to_human": True,
        }

        if safety_settings is not None:
            model_kwargs["safety_settings"] = safety_settings

        # Allow select LangChain generation kwargs to pass through
        passthrough_keys = {
            "top_p",
            "top_k",
            "max_output_tokens",
            "response_mime_type",
            "stop",
        }
        for key, value in kwargs.items():
            if key in passthrough_keys and value is not None:
                model_kwargs[key] = value

        return model_kwargs

    async def load_model(self, *, api_key: Optional[str] = None, **kwargs) -> BaseChatModel:
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        if not key:
            raise ValueError("Missing Google Gemini API key")

        model_kwargs = self._build_model_kwargs(api_key=key, kwargs=kwargs)
        return _GeminiModelWrapper(**model_kwargs)

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
        model_kwargs = self._build_model_kwargs(
            api_key=key,
            kwargs=kwargs,
            default_temperature_env="PRIMARY_AGENT_TEMPERATURE",
        )
        if thinking_budget is not None:
            model_kwargs["thinking_budget"] = thinking_budget
        return _GeminiModelWrapper(**model_kwargs)


class GoogleGeminiFlashPreviewAdapter(GoogleGeminiFlashAdapter):
    """Adapter for preview aliases that should call the preview model id."""

    model_name = "gemini-2.5-flash-preview-09-2025"


class GoogleGeminiFlashLiteAdapter(GoogleGeminiFlashAdapter):
    """Adapter for the flash-lite routing model variant."""

    model_name = "gemini-2.5-flash-lite"

# Registration
from app.providers.registry import register_adapter
register_adapter("google", "gemini-2.5-flash", GoogleGeminiFlashAdapter)
# Also register latest preview alias (September 2025)
register_adapter("google", "gemini-2.5-flash-preview-09-2025", GoogleGeminiFlashPreviewAdapter)
register_adapter("google", "gemini-2.5-flash-lite", GoogleGeminiFlashLiteAdapter)
