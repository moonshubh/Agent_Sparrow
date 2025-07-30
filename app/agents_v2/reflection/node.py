"""LangGraph node implementing reflection evaluation using Gemini Flash."""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableLambda
from loguru import logger

from .schema import ReflectionFeedback, RUBRIC_MD

# We keep a single model instance for performance (no streaming needed here)
_reflection_model: ChatGoogleGenerativeAI | None = None


def _get_model() -> ChatGoogleGenerativeAI:
    global _reflection_model
    if _reflection_model is None:
        _reflection_model = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            top_p=0.95,
            google_api_key=os.environ.get("GEMINI_API_KEY"),
        ).with_config({"run_name": "reflection_node"})
    return _reflection_model


def _build_prompt(user_query: str, assistant_answer: str) -> list[Any]:
    """Constructs prompt/messages list for the reflection model."""
    system = SystemMessage(
        content=(
            f"{RUBRIC_MD}\n\nUser Query:\n{user_query}\n\nAssistant Answer:\n{assistant_answer}\n"
            "Remember: respond ONLY with valid JSON per schema."
        )
    )
    # Gemini function calling can be emulated via schema= arg but here we use explicit instruction
    return [system]


# ----------------------- LangGraph node callable ---------------------------

def reflection_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates answer and returns updated state diff with `reflection_feedback`."""

    try:
        user_query = state["messages"][-2].content  # last user msg before answer
        assistant_answer = state["messages"][-1].content
    except Exception as e:  # pragma: no cover
        logger.error("reflection_node: failed to extract messages: {}", e)
        # Return a no-op diff that still touches an allowed key to satisfy LangGraph
        return {"reflection_feedback": None}

    model = _get_model()

    messages = _build_prompt(user_query, assistant_answer)

    try:
        response = model.invoke(messages)
        parsed: ReflectionFeedback = ReflectionFeedback.model_validate_json(  # type: ignore[arg-type]
            response.content if hasattr(response, "content") else json.dumps(response)
        )
    except Exception as e:  # pragma: no cover
        logger.error("reflection_node: model or parse error: {}", e)
        # Return a no-op diff that still touches an allowed key to satisfy LangGraph
        return {"reflection_feedback": None}

    new_retry_count = state.get("qa_retry_count", 0) + 1
    logger.debug("reflection_node feedback: {}, retry {}", parsed, new_retry_count)
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
