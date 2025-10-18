from __future__ import annotations

import asyncio
import json
import os
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
from app.api.v1.schemas.chat_stream import ChatStreamEvent
from app.core.logging_config import get_logger
from app.core.settings import settings
from app.core.transport.sse import format_sse_comment, format_sse_data
from app.core.user_context import create_user_context_from_user_id, user_context_scope

logger = get_logger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    messages: list[dict] | None = None
    session_id: str | None = None
    provider: str | None = None
    model: str | None = None
    # Optional image/file attachments from frontend (data URLs)
    attachments: list[dict] | None = None
    # Manual web search flags
    force_websearch: bool | None = None
    websearch_max_results: int | None = None
    websearch_profile: str | None = None


async def stream_text_by_characters(
    text: str,
    stream_id: str,
    *,
    emit_start: bool = False,
    emit_end: bool = False,
    chunk_size: int = 1,
    delay: float = 0.0,
    metrics: Optional[dict[str, int]] = None,
    trace_id: Optional[str] = None,
) -> AsyncIterable[str]:
    """Stream text content character by character for smooth animation."""
    if emit_start:
        if metrics is not None:
            metrics["events"] = metrics.get("events", 0) + 1
        yield format_sse_data(ChatStreamEvent(type="text-start", id=stream_id, trace_id=trace_id))
    for i in range(0, len(text), chunk_size):
        chunk = text[i : i + chunk_size]
        if not chunk:
            continue
        if metrics is not None:
            metrics["events"] = metrics.get("events", 0) + 1
            metrics["text_chars"] = metrics.get("text_chars", 0) + len(chunk)
        yield format_sse_data(ChatStreamEvent(type="text-delta", id=stream_id, delta=chunk, trace_id=trace_id))
        if delay > 0:
            await asyncio.sleep(delay)
    if emit_end:
        if metrics is not None:
            metrics["events"] = metrics.get("events", 0) + 1
        yield format_sse_data(ChatStreamEvent(type="text-end", id=stream_id, trace_id=trace_id))


def _resolve_provider_model(provider: Optional[str], model: Optional[str]) -> tuple[str, str]:
    try:
        from app.providers.adapters import default_provider, default_model_for_provider
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
    attachments: list[dict] | None = None,
    *,
    force_websearch: bool | None = None,
    websearch_max_results: int | None = None,
    websearch_profile: str | None = None,
) -> AsyncIterable[str]:
    stream_closed = False
    generated_trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    stream_metrics: dict[str, int] = {"events": 0, "text_chars": 0, "heartbeats": 0}
    started_at = datetime.utcnow()
    heartbeat_interval = 15.0
    try:
        # Emit an initial heartbeat comment so intermediaries keep the connection open.
        stream_metrics["events"] += 1
        stream_metrics["heartbeats"] += 1
        yield format_sse_comment()
        user_context = await create_user_context_from_user_id(user_id)
        req_provider, req_model = _resolve_provider_model(provider, model)
        logger.info(
            "chat_stream_request_resolved",
            original_provider=provider,
            original_model=model,
            resolved_provider=req_provider,
            resolved_model=req_model,
            session_id=session_id,
            user_id=user_id,
            trace_id=generated_trace_id,
        )

        if req_provider == "google":
            gemini_key = await user_context.get_gemini_api_key()
            if not gemini_key:
                gemini_key = (
                    os.getenv("GEMINI_API_KEY")
                    or getattr(settings, "gemini_api_key", None)
                )
            if not gemini_key:
                logger.warning(
                    "chat_stream_missing_gemini_key",
                    user_id=user_id,
                    trace_id=generated_trace_id,
                )
                stream_metrics["events"] += 1
                yield format_sse_data(
                    ChatStreamEvent(
                        type="error",
                        errorText="API Key Required: Please add your Google Gemini API key in Settings.",
                        trace_id=generated_trace_id,
                    )
                )
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
                stream_metrics["events"] += 1
                yield format_sse_data(
                    ChatStreamEvent(
                        type="error",
                        errorText="OpenAI API key missing. Add it in Settings or set OPENAI_API_KEY.",
                        trace_id=generated_trace_id,
                    )
                )
                return
        else:
            stream_metrics["events"] += 1
            yield format_sse_data(
                ChatStreamEvent(
                    type="error",
                    errorText=f"Unsupported provider: {req_provider}",
                    trace_id=generated_trace_id,
                )
            )
            return

        async with user_context_scope(user_context):
            messages = []
            if message_history:
                for msg in message_history:
                    if msg.get("type") == "user" or msg.get("role") == "user":
                        messages.append(HumanMessage(content=msg.get("content", "")))
                    elif msg.get("type") == "assistant" or msg.get("role") == "assistant":
                        messages.append(AIMessage(content=msg.get("content", "")))
            # Attach images/files as multimodal parts if provided
            atts = attachments or []
            image_parts = []
            MAX_ATTACHMENTS = 4
            ALLOWED_MIME_PREFIXES = ("image/",)
            for att in atts[:MAX_ATTACHMENTS]:
                try:
                    mt = str(att.get("media_type") or "").lower()
                    if not any(mt.startswith(p) for p in ALLOWED_MIME_PREFIXES):
                        continue
                    data_url = str(att.get("data_url") or "")
                    if not data_url.startswith("data:"):
                        continue
                    # LangChain Google SDK accepts dicts {type: 'image_url', image_url: {url: ...}}
                    image_parts.append({"type": "image_url", "image_url": {"url": data_url}})
                except Exception:
                    continue

            if image_parts:
                messages.append(HumanMessage(content=[{"type": "text", "text": query}, *image_parts]))
            else:
                messages.append(HumanMessage(content=query))

            initial_state = PrimaryAgentState(
                messages=messages,
                session_id=session_id,
                trace_id=generated_trace_id,
                provider=req_provider,
                model=req_model,
                force_websearch=force_websearch,
                websearch_max_results=websearch_max_results,
                websearch_profile=websearch_profile,
            )
            logger.info(
                "chat_stream_state_initialized",
                provider=initial_state.provider,
                model=initial_state.model,
                trace_id=generated_trace_id,
                session_id=session_id,
            )

            stream_id = f"assistant-{uuid.uuid4().hex}"
            text_started = False
            reasoning_started = False

            logger.info(
                "chat_stream_ready",
                provider=req_provider,
                model=req_model,
                session_id=session_id,
                stream_id=stream_id,
                trace_id=generated_trace_id,
            )

            metrics = stream_metrics
            agent_stream = run_primary_agent(initial_state)
            agen = agent_stream.__aiter__()
            try:
                while True:
                    try:
                        chunk = await asyncio.wait_for(agen.__anext__(), heartbeat_interval)
                    except StopAsyncIteration:
                        logger.info(
                            "chat_stream_upstream_complete",
                            text_started=text_started,
                            reasoning_started=reasoning_started,
                            trace_id=generated_trace_id,
                        )
                        break
                    except asyncio.TimeoutError:
                        metrics["events"] = metrics.get("events", 0) + 1
                        metrics["heartbeats"] = metrics.get("heartbeats", 0) + 1
                        yield format_sse_comment("working")
                        continue

                    payloads: list[ChatStreamEvent] = []

                    if chunk is None:
                        logger.warning("chat_stream_none_chunk", trace_id=generated_trace_id)
                        continue

                    chunk_content = getattr(chunk, "content", None)
                    chunk_meta = getattr(chunk, "additional_kwargs", None)
                    logger.info(
                        "chat_stream_chunk_received",
                        chunk_type=type(chunk).__name__,
                        content_length=len(chunk_content) if isinstance(chunk_content, str) else (len(chunk_content) if hasattr(chunk_content, "__len__") else None),
                        has_metadata=bool(chunk_meta),
                        trace_id=generated_trace_id,
                    )
                    content_piece: Optional[str] = None

                    def ensure_text_started() -> None:
                        nonlocal text_started
                        if not text_started:
                            payloads.append(ChatStreamEvent(type="text-start", id=stream_id, trace_id=generated_trace_id))
                            text_started = True

                    if chunk_content is not None:
                        content_piece = chunk_content
                        if not isinstance(content_piece, str):
                            try:
                                content_piece = json.dumps(content_piece, ensure_ascii=False)
                            except TypeError:
                                content_piece = str(content_piece)

                        content_piece = filter_system_text(content_piece)
                    if content_piece:
                        logger.info(
                            "chat_stream_text_chunk",
                            length=len(content_piece),
                            preview=content_piece[:120],
                            trace_id=generated_trace_id,
                        )
                        async for char_chunk in stream_text_by_characters(
                            content_piece,
                            stream_id,
                            emit_start=not text_started,
                            metrics=metrics,
                            trace_id=generated_trace_id,
                        ):
                            yield char_chunk
                        text_started = True

                    metadata = None
                    if isinstance(chunk_meta, dict):
                        metadata = chunk_meta.get("metadata")
                    if metadata:
                        logger.info(
                            "chat_stream_metadata_received",
                            keys=list(metadata.keys()),
                            trace_id=generated_trace_id,
                        )
                        followups = metadata.get("followUpQuestions")
                        if followups:
                            ensure_text_started()
                            payloads.append(
                                ChatStreamEvent(
                                    type="data-followups",
                                    data=followups,
                                    transient=True,
                                    trace_id=generated_trace_id,
                                )
                            )

                        thinking_trace = metadata.get("thinking_trace")
                        if thinking_trace:
                            # Emit reasoning events in addition to legacy data-thinking for compatibility
                            if not reasoning_started:
                                payloads.append(ChatStreamEvent(type="reasoning-start", trace_id=generated_trace_id))
                                reasoning_started = True
                            # Try to pick the latest thought text if available
                            try:
                                latest_thought = None
                                if isinstance(thinking_trace, dict):
                                    steps = thinking_trace.get("thinking_steps")
                                    if isinstance(steps, list) and steps:
                                        last = steps[-1]
                                        if isinstance(last, dict):
                                            t = last.get("thought") or last.get("text")
                                            if isinstance(t, str):
                                                latest_thought = t
                                if isinstance(thinking_trace, str) and not latest_thought:
                                    latest_thought = thinking_trace
                            except Exception:
                                latest_thought = None
                            if latest_thought:
                                payloads.append(
                                    ChatStreamEvent(
                                        type="reasoning-delta",
                                        text=latest_thought,
                                        trace_id=generated_trace_id,
                                    )
                                )
                            # Keep sparse metadata event for downstream consumers
                            payloads.append(
                                ChatStreamEvent(
                                    type="data-thinking",
                                    data=thinking_trace,
                                    trace_id=generated_trace_id,
                                )
                            )

                        tool_results = metadata.get("toolResults")
                        if tool_results:
                            ensure_text_started()
                            payloads.append(
                                ChatStreamEvent(
                                    type="data-tool-result",
                                    data=tool_results,
                                    trace_id=generated_trace_id,
                                )
                            )

                        leftover = {k: v for k, v in metadata.items() if k not in {"followUpQuestions", "thinking_trace", "toolResults"}}
                        if leftover:
                            ensure_text_started()
                            payloads.append(
                                ChatStreamEvent(
                                    type="message-metadata",
                                    messageMetadata=leftover,
                                    trace_id=generated_trace_id,
                                )
                            )

                    for payload in payloads:
                        logger.info(
                            "chat_stream_emit_payload",
                            payload_type=payload.type,
                            trace_id=generated_trace_id,
                        )
                        metrics["events"] = metrics.get("events", 0) + 1
                        yield format_sse_data(payload)
            finally:
                if hasattr(agent_stream, "aclose"):
                    await agent_stream.aclose()

            if text_started:
                async for closing in stream_text_by_characters("", stream_id, emit_end=True, metrics=metrics, trace_id=generated_trace_id):
                    yield closing

            if reasoning_started:
                # Close reasoning stream
                metrics["events"] = metrics.get("events", 0) + 1
                yield format_sse_data(ChatStreamEvent(type="reasoning-end", trace_id=generated_trace_id))

            metrics["events"] = metrics.get("events", 0) + 1
            yield format_sse_data(
                ChatStreamEvent(
                    type="finish",
                    session_id=session_id,
                    stream_id=stream_id,
                    trace_id=generated_trace_id,
                )
            )
            stream_closed = True

    except Exception as e:
        logger.exception(
            "chat_stream_generator_error",
            trace_id=generated_trace_id,
        )
        stream_metrics["events"] += 1
        yield format_sse_data(
            ChatStreamEvent(
                type="error",
                errorText=f"An error occurred in the agent: {str(e)}",
                trace_id=generated_trace_id,
            )
        )
    finally:
        if not stream_closed:
            stream_metrics["events"] += 1
            yield format_sse_data(
                ChatStreamEvent(
                    type="finish",
                    session_id=session_id,
                    stream_id=locals().get("stream_id"),
                    trace_id=generated_trace_id,
                )
            )
        elapsed_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        logger.info(
            "chat_stream_complete",
            provider=req_provider if "req_provider" in locals() else provider,
            session_id=session_id,
            stream_id=locals().get("stream_id"),
            events=stream_metrics.get("events", 0),
            text_chars=stream_metrics.get("text_chars", 0),
            heartbeats=stream_metrics.get("heartbeats", 0),
            elapsed_ms=elapsed_ms,
            trace_id=generated_trace_id,
        )


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
            attachments=request.attachments,
            force_websearch=request.force_websearch,
            websearch_max_results=request.websearch_max_results,
            websearch_profile=request.websearch_profile,
        ),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream; charset=utf-8",
            "Pragma": "no-cache",
            "Vary": "Authorization, Accept-Encoding",
            "X-Accel-Buffering": "no",
            "X-API-Version": "2.0",
        },
    )
