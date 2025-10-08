from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import AsyncIterable, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.agents.primary import run_primary_agent, PrimaryAgentState
from app.api.v1.endpoints.agent_common import (
    filter_system_text,
)
from app.core.transport.sse import format_sse_data
from app.core.user_context import create_user_context_from_user_id, user_context_scope

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    messages: list[dict] | None = None
    session_id: str | None = None
    provider: str | None = None
    model: str | None = None


def _resolve_provider_model(provider: Optional[str], model: Optional[str]) -> tuple[str, str]:
    try:
        from app.providers.registry import default_provider, default_model_for_provider
        req_provider = (provider or default_provider()).lower()
        req_model = (model or default_model_for_provider(req_provider)).lower()
    except Exception:
        req_provider = (provider or "google").lower()
        req_model = (model or "gemini-2.5-flash").lower()
    return req_provider, req_model


async def primary_agent_stream_generator(
    query: str,
    user_id: str,
    message_history: list[dict] | None = None,
    session_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> AsyncIterable[str]:
    try:
        user_context = await create_user_context_from_user_id(user_id)
        req_provider, req_model = _resolve_provider_model(provider, model)
        logger.info(
            f"[chat_stream] request provider={provider}, model={model} -> resolved provider={req_provider}, model={req_model}"
        )

        if req_provider == "google":
            gemini_key = await user_context.get_gemini_api_key()
            if not gemini_key:
                yield format_sse_data({
                    "type": "error",
                    "errorText": "API Key Required: Please add your Google Gemini API key in Settings.",
                })
                return
        elif req_provider == "openai":
            openai_key = None
            if hasattr(user_context, "get_openai_api_key"):
                try:
                    openai_key = await user_context.get_openai_api_key()
                except Exception:
                    openai_key = None
            import os
            openai_key = openai_key or os.getenv("OPENAI_API_KEY")
            if not openai_key:
                yield format_sse_data({
                    "type": "error",
                    "errorText": "OpenAI API key missing. Add it in Settings or set OPENAI_API_KEY.",
                })
                return
        else:
            yield format_sse_data({
                "type": "error",
                "errorText": f"Unsupported provider: {req_provider}",
            })
            return

        async with user_context_scope(user_context):
            messages = []
            if message_history:
                for msg in message_history:
                    if msg.get("type") == "user" or msg.get("role") == "user":
                        messages.append(HumanMessage(content=msg.get("content", "")))
                    elif msg.get("type") == "assistant" or msg.get("role") == "assistant":
                        messages.append(AIMessage(content=msg.get("content", "")))
            messages.append(HumanMessage(content=query))

            initial_state = PrimaryAgentState(
                messages=messages,
                session_id=session_id,
                provider=req_provider,
                model=req_model,
            )
            logger.info(
                f"[chat_stream] initial_state provider={initial_state.provider}, model={initial_state.model}"
            )

            stream_id = f"assistant-{uuid.uuid4().hex}"
            text_started = False

            async for chunk in run_primary_agent(initial_state):
                payloads: list[dict] = []

                def ensure_text_started() -> None:
                    nonlocal text_started
                    if not text_started:
                        payloads.append({"type": "text-start", "id": stream_id})
                        text_started = True

                if hasattr(chunk, "content") and chunk.content is not None:
                    content_piece = chunk.content
                    if not isinstance(content_piece, str):
                        try:
                            content_piece = json.dumps(content_piece, ensure_ascii=False)
                        except TypeError:
                            content_piece = str(content_piece)

                    content_piece = filter_system_text(content_piece)
                    if content_piece:
                        ensure_text_started()
                        payloads.append({"type": "text-delta", "id": stream_id, "delta": content_piece})

                metadata = getattr(chunk, "additional_kwargs", {}).get("metadata") if hasattr(chunk, "additional_kwargs") else None
                if metadata:
                    followups = metadata.get("followUpQuestions")
                    if followups:
                        ensure_text_started()
                        payloads.append({"type": "data-followups", "data": followups, "transient": True})

                    thinking_trace = metadata.get("thinking_trace")
                    if thinking_trace:
                        ensure_text_started()
                        payloads.append({"type": "data-thinking", "data": thinking_trace})

                    tool_results = metadata.get("toolResults")
                    if tool_results:
                        ensure_text_started()
                        payloads.append({"type": "data-tool-result", "data": tool_results})

                    leftover = {k: v for k, v in metadata.items() if k not in {"followUpQuestions", "thinking_trace", "toolResults"}}
                    if leftover:
                        ensure_text_started()
                        payloads.append({"type": "message-metadata", "messageMetadata": leftover})

                for payload in payloads:
                    yield format_sse_data(payload)

            if text_started:
                for payload in [{"type": "text-end", "id": stream_id}, {"type": "finish"}]:
                    yield format_sse_data(payload)

    except Exception as e:
        logger.error(
            f"Error in primary_agent_stream_generator calling run_primary_agent: {e}",
            exc_info=True,
        )
        yield format_sse_data({"type": "error", "errorText": f"An error occurred in the agent: {str(e)}"})


# Conditional import for authentication
try:
    from app.api.v1.endpoints.auth import get_current_user_id
    AUTH_AVAILABLE = True
except ImportError:  # pragma: no cover
    AUTH_AVAILABLE = False
    async def get_current_user_id() -> str:  # type: ignore
        from app.core.settings import settings
        return getattr(settings, 'development_user_id', 'dev-user-12345')


@router.post("/v2/agent/chat/stream")
async def chat_stream_v2_authenticated(request: ChatRequest, user_id: str = Depends(get_current_user_id)):
    if not request.message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    return StreamingResponse(
        primary_agent_stream_generator(
            request.message,
            user_id,
            message_history=request.messages,
            session_id=request.session_id,
            provider=request.provider,
            model=request.model,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-API-Version": "2.0"},
    )
