"""LangGraph node implementing provider-agnostic reflection evaluation."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from typing import Any, Dict, Optional, Tuple

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableLambda
from loguru import logger

from app.core.settings import settings
from app.core.user_context import get_current_user_context
from app.providers.base import BaseChatModel
from app.providers.registry import (
    get_adapter,
    default_model_for_provider,
    default_provider,
)

from .schema import ReflectionFeedback, RUBRIC_MD

# Cache reflection models per provider/model/api-key hash for reuse
_REFLECTION_MODEL_CACHE: Dict[Tuple[str, str, str], BaseChatModel] = {}
_CACHE_LOCK = asyncio.Lock()


def _extract_state_value(state: Any, key: str, default: Any = None) -> Any:
    """Helper to read values from GraphState-like objects or plain dicts."""

    if hasattr(state, "get"):
        try:
            return state.get(key, default)  # type: ignore[call-arg]
        except TypeError:
            pass
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _resolve_provider_and_model(state: Any) -> Tuple[str, str]:
    """Determine which provider/model should be used for reflection."""

    provider = (
        _extract_state_value(state, "provider")
        or settings.reflection_default_provider
        or default_provider()
    )
    provider = str(provider).lower()

    model_name = (
        _extract_state_value(state, "model")
        or settings.reflection_default_model
        or default_model_for_provider(provider)
    )
    model_name = str(model_name).lower()

    return provider, model_name


def _hash_api_key(api_key: Optional[str]) -> str:
    if not api_key:
        return "no-key"
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


async def _resolve_api_key(provider: str) -> Optional[str]:
    """Resolve an API key for the given provider using user context or env vars."""

    provider = provider.lower()
    user_context = get_current_user_context()

    if provider == "google":
        if user_context:
            try:
                key = await user_context.get_gemini_api_key()
            except Exception:  # pragma: no cover - best effort
                key = None
        else:
            key = None
        return key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")

    if provider == "openai":
        key: Optional[str] = None
        if user_context and hasattr(user_context, "get_openai_api_key"):
            try:
                key = await user_context.get_openai_api_key()
            except Exception:  # pragma: no cover - best effort
                key = None
        return key or os.getenv("OPENAI_API_KEY") or os.getenv("OpenAI_API_KEY")

    # Generic fallback to PROVIDER_API_KEY naming
    env_var = f"{provider.upper()}_API_KEY"
    return os.getenv(env_var)


async def _load_reflection_model(
    provider: str,
    model_name: str,
    api_key: Optional[str],
) -> BaseChatModel:
    """Load (or reuse) a reflection model for the given provider/model."""

    cache_key = (provider.lower(), model_name.lower(), _hash_api_key(api_key))

    async with _CACHE_LOCK:
        cached = _REFLECTION_MODEL_CACHE.get(cache_key)
        if cached is not None:
            return cached

    adapter = get_adapter(provider, model_name)

    try:
        model = await adapter.load_reasoning_model(api_key=api_key)
    except TypeError:
        # Some adapters may not accept api_key in this method yet
        model = await adapter.load_reasoning_model()
    except Exception as exc:
        logger.warning(
            "Reflection adapter load failed for %s/%s: %s", provider, model_name, exc
        )
        model = await adapter.load_model(api_key=api_key)

    async with _CACHE_LOCK:
        _REFLECTION_MODEL_CACHE[cache_key] = model

    return model


def _build_prompt(user_query: str, assistant_answer: str) -> list[Any]:
    """Construct prompt/messages list for the reflection model."""

    system = SystemMessage(
        content=(
            f"{RUBRIC_MD}\n\nUser Query:\n{user_query}\n\nAssistant Answer:\n{assistant_answer}\n"
            "Remember: respond ONLY with valid JSON per schema."
        )
    )
    return [system]


# ----------------------- LangGraph node callable ---------------------------


async def reflection_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates answer and returns updated state diff with `reflection_feedback`."""

    try:
        user_query = state["messages"][-2].content  # last user msg before answer
        assistant_answer = state["messages"][-1].content
    except Exception as e:  # pragma: no cover
        logger.error("reflection_node: failed to extract messages: {}", e)
        return {}

    provider, model_name = _resolve_provider_and_model(state)
    api_key = await _resolve_api_key(provider)

    try:
        model = await _load_reflection_model(provider, model_name, api_key)
    except Exception as exc:  # pragma: no cover - fallback to defaults
        logger.error(
            "reflection_node: primary adapter load failed (%s/%s): %s",
            provider,
            model_name,
            exc,
        )
        fallback_provider = default_provider()
        fallback_model = default_model_for_provider(fallback_provider)
        fallback_key = await _resolve_api_key(fallback_provider)
        try:
            model = await _load_reflection_model(fallback_provider, fallback_model, fallback_key)
            provider, model_name, api_key = fallback_provider, fallback_model, fallback_key
        except Exception as fallback_exc:  # pragma: no cover
            logger.error("reflection_node: fallback adapter load failed: %s", fallback_exc)
            return {}

    messages = _build_prompt(user_query, assistant_answer)

    try:
        response = await model.ainvoke(messages)
        payload = response.content if hasattr(response, "content") else response
        parsed: ReflectionFeedback = ReflectionFeedback.model_validate_json(  # type: ignore[arg-type]
            payload if isinstance(payload, str) else json.dumps(payload)
        )
    except Exception as e:  # pragma: no cover
        logger.error("reflection_node: model or parse error: {}", e)
        return {}

    new_retry_count = _extract_state_value(state, "qa_retry_count", 0) + 1
    logger.debug(
        "reflection_node feedback: %s, retry %s (provider=%s, model=%s)",
        parsed,
        new_retry_count,
        provider,
        model_name,
    )
    return {
        "reflection_feedback": parsed,
        "qa_retry_count": new_retry_count,
    }


# ------------------------ Routing helper ----------------------------------


def reflection_route(state: Dict[str, Any]) -> str:
    """Decides next graph step based on feedback and retry count."""

    feedback: ReflectionFeedback | None = state.get("reflection_feedback")  # type: ignore[arg-type]
    retry_count: int = state.get("qa_retry_count", 0)
    MAX_RETRIES = int(os.getenv("QA_MAX_RETRIES", "1"))
    CONF_THRESHOLD = float(os.getenv("QA_CONFIDENCE_THRESHOLD", "0.7"))
    CRITICAL_THRESHOLD = float(os.getenv("QA_CRITICAL_THRESHOLD", "0.4"))

    if feedback is None:
        return "post_process"  # fallback – skip loop

    if feedback.confidence_score < CRITICAL_THRESHOLD:
        return "escalate"  # special end path

    if feedback.confidence_score < CONF_THRESHOLD and retry_count < MAX_RETRIES:
        return "refine"

    return "post_process"


# Expose as Runnable for LangGraph convenience
reflection_runnable = RunnableLambda(reflection_node)
