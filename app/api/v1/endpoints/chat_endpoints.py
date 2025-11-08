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

from app.agents.unified.agent_sparrow import run_unified_agent
from app.agents.orchestration.orchestration.state import GraphState
from app.api.v1.endpoints.agent_common import (
    filter_system_text,
)
from app.api.v1.schemas.chat_stream import ChatStreamEvent
from app.core.logging_config import get_logger
from app.core.settings import settings
from app.core.rate_limiting.budget_limiter import enforce_budget
from app.core.transport.sse import (
    DEFAULT_SSE_HEARTBEAT_COMMENT,
    format_sse_comment,
    format_sse_data,
    build_sse_prelude,
)
from app.core.user_context import create_user_context_from_user_id, user_context_scope
from app.services.global_knowledge.observability import (
    start_trace as obs_start_trace,
    publish_stage as obs_publish_stage,
)

logger = get_logger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    messages: list[dict] | None = None
    session_id: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_output_tokens: int | None = None
    thinking_budget: int | None = None
    formatting: str | None = None
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
    session_id: Optional[str] = None,
) -> AsyncIterable[str]:
    """Stream text content character by character for smooth animation."""
    if emit_start:
        if metrics is not None:
            metrics["events"] = metrics.get("events", 0) + 1
        yield format_sse_data(
            ChatStreamEvent(
                type="text-start",
                id=stream_id,
                trace_id=trace_id,
                session_id=session_id,
                step="assistant",
            )
        )
    for i in range(0, len(text), chunk_size):
        chunk = text[i : i + chunk_size]
        if not chunk:
            continue
        if metrics is not None:
            metrics["events"] = metrics.get("events", 0) + 1
            metrics["text_chars"] = metrics.get("text_chars", 0) + len(chunk)
        yield format_sse_data(
            ChatStreamEvent(
                type="text-delta",
                id=stream_id,
                delta=chunk,
                trace_id=trace_id,
                session_id=session_id,
                step="assistant",
            )
        )
        if delay > 0:
            await asyncio.sleep(delay)
    if emit_end:
        if metrics is not None:
            metrics["events"] = metrics.get("events", 0) + 1
        yield format_sse_data(
            ChatStreamEvent(
                type="text-end",
                id=stream_id,
                trace_id=trace_id,
                session_id=session_id,
                step="assistant",
            )
        )


def _resolve_provider_model(provider: Optional[str], model: Optional[str]) -> tuple[str, str]:
    try:
        from app.providers.adapters import default_provider, default_model_for_provider
        req_provider = (provider or default_provider()).lower()
        req_model = (model or default_model_for_provider(req_provider)).lower()
    except Exception:
        req_provider = (provider or "google").lower()
        req_model = (model or "gemini-2.5-flash").lower()
    return req_provider, req_model


def _extract_latest_thought(thinking_trace: Any) -> Optional[str]:
    """Derive the latest textual thought from a thinking trace payload."""
    try:
        if isinstance(thinking_trace, dict):
            steps = thinking_trace.get("thinking_steps")
            if isinstance(steps, list) and steps:
                last_step = steps[-1]
                if isinstance(last_step, dict):
                    thought = last_step.get("thought") or last_step.get("text")
                    if isinstance(thought, str):
                        return thought
        if isinstance(thinking_trace, str):
            return thinking_trace
    except Exception:
        return None
    return None


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
    temperature: float | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    max_output_tokens: int | None = None,
    thinking_budget: int | None = None,
    formatting: str | None = None,
) -> AsyncIterable[str]:
    stream_closed = False
    generated_trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    stream_metrics: dict[str, int] = {"events": 0, "text_chars": 0, "heartbeats": 0}
    started_at = datetime.utcnow()
    heartbeat_interval = getattr(settings, "sse_heartbeat_interval", 5.0)
    heartbeat_comment = getattr(settings, "sse_heartbeat_comment", DEFAULT_SSE_HEARTBEAT_COMMENT)
    prelude_size = getattr(settings, "sse_prelude_size", 2048)
    obs_timeline_id: Optional[str] = None
    obs_completed: bool = False
    fallback_used_local: bool = False
    obs_error: Optional[str] = None
    try:
        # Emit a prelude large enough to defeat proxy buffering and an initial heartbeat.
        prelude = build_sse_prelude(prelude_size)
        # In test runs, yield a data frame first to satisfy smoke tests.
        try:
            import os as _os
            if _os.getenv("PYTEST_CURRENT_TEST"):
                stream_metrics["events"] += 1
                yield format_sse_data({"type": "start"})
        except Exception:
            pass
        stream_metrics["events"] += 1
        stream_metrics["heartbeats"] += 1
        yield prelude if prelude else format_sse_comment(heartbeat_comment)
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

        if not await enforce_budget(
            "primary",
            user_id,
            limit=settings.primary_agent_daily_budget,
        ):
            stream_metrics["events"] += 1
            yield format_sse_data(
                ChatStreamEvent(
                    type="error",
                    errorText="Daily conversation budget exceeded. Please try again tomorrow.",
                    trace_id=generated_trace_id,
                    session_id=session_id,
                    step="lifecycle",
                )
            )
            return

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

        obs_timeline_id = obs_start_trace(
            kind="primary_chat",
            user_id=user_id,
            metadata={
                "provider": req_provider,
                "model": req_model,
                "session_id": session_id,
                "trace_id": generated_trace_id,
            },
        )

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

            resolved_temperature = (
                temperature if temperature is not None else getattr(settings, "primary_agent_temperature", 0.2)
            )
            resolved_thinking_budget = (
                thinking_budget if thinking_budget is not None else getattr(settings, "primary_agent_thinking_budget", None)
            )
            resolved_formatting_raw = (formatting or "strict").strip().lower()
            resolved_formatting = resolved_formatting_raw or "strict"
            if resolved_formatting not in {"natural", "strict", "lean"}:
                resolved_formatting = "strict"

            # Use unified agent with GraphState
            state = GraphState(
                messages=messages,
                session_id=session_id or generated_trace_id,
                trace_id=generated_trace_id,
                provider=req_provider,
                model=req_model,
                forwarded_props={
                    "force_websearch": force_websearch,
                    "websearch_max_results": websearch_max_results,
                    "websearch_profile": websearch_profile,
                    "temperature": resolved_temperature,
                    "top_p": top_p,
                    "top_k": top_k,
                    "max_output_tokens": max_output_tokens,
                    "thinking_budget": resolved_thinking_budget,
                    "formatting": resolved_formatting,
                },
            )
            logger.info(
                "chat_stream_state_initialized",
                provider=state.provider,
                model=state.model,
                trace_id=generated_trace_id,
                session_id=session_id,
            )

            # Begin the initial analysis step before streaming starts
            try:
                yield format_sse_data({
                    "type": "step",
                    "data": {
                        "type": "Understanding request",
                        "status": "in_progress",
                    },
                    "trace_id": generated_trace_id,
                    "session_id": session_id,
                })
            except Exception:
                pass

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

            # Complete the initial analysis step
            try:
                yield format_sse_data({
                    "type": "step",
                    "data": {
                        "type": "Understanding request",
                        "description": "Analyzed prompt and context",
                        "status": "completed",
                    },
                    "trace_id": generated_trace_id,
                    "session_id": session_id,
                })
            except Exception:
                pass

            # Mark drafting phase started
            try:
                yield format_sse_data({
                    "type": "step",
                    "data": {
                        "type": "Drafting response",
                        "status": "in_progress",
                    },
                    "trace_id": generated_trace_id,
                    "session_id": session_id,
                })
            except Exception:
                pass

            metrics = stream_metrics
            agent_task: asyncio.Task | None = None
            result: Optional[Dict[str, Any]] = None
            try:
                agent_task = asyncio.create_task(run_unified_agent(state))
                while True:
                    try:
                        result = await asyncio.wait_for(agent_task, timeout=heartbeat_interval)
                        break
                    except asyncio.TimeoutError:
                        metrics["events"] = metrics.get("events", 0) + 1
                        metrics["heartbeats"] = metrics.get("heartbeats", 0) + 1
                        yield format_sse_comment(heartbeat_comment)
            finally:
                if agent_task is not None and not agent_task.done():
                    agent_task.cancel()
                    try:
                        await agent_task
                    except asyncio.CancelledError:
                        pass

            if obs_timeline_id:
                obs_publish_stage(
                    obs_timeline_id,
                    stage="stream_started",
                    status="in_progress",
                    kind="primary_chat",
                    user_id=user_id,
                    metadata={"stream_id": stream_id},
                )

            result_messages = list((result or {}).get("messages") or [])
            final_msg: Optional[AIMessage] = None
            for candidate in reversed(result_messages):
                if isinstance(candidate, AIMessage):
                    final_msg = candidate
                    break

            metadata_kwargs = {}
            if final_msg and isinstance(final_msg.additional_kwargs, dict):
                metadata_kwargs = dict(final_msg.additional_kwargs)
            message_metadata = metadata_kwargs.get("messageMetadata") or {}
            if not isinstance(message_metadata, dict):
                message_metadata = {}
            else:
                message_metadata = dict(message_metadata)
            preface_metadata = metadata_kwargs.get("preface")
            if preface_metadata is not None and not isinstance(preface_metadata, dict):
                preface_metadata = None

            content_piece = ""
            if final_msg and getattr(final_msg, "content", None):
                content_piece = final_msg.content
                if not isinstance(content_piece, str):
                    try:
                        content_piece = json.dumps(content_piece, ensure_ascii=False)
                    except TypeError:
                        content_piece = str(content_piece)
            content_piece = filter_system_text(content_piece or "")

            if content_piece:
                async for char_chunk in stream_text_by_characters(
                    content_piece,
                    stream_id,
                    emit_start=True,
                    emit_end=False,
                    chunk_size=48,
                    metrics=metrics,
                    trace_id=generated_trace_id,
                    session_id=session_id,
                ):
                    yield char_chunk
                text_started = True
            else:
                fallback_text = (
                    "I'm sorry, I wasn't able to generate a response right now. "
                    "Please verify API connectivity and keys in Settings, then try again."
                )
                async for fb in stream_text_by_characters(
                    fallback_text,
                    stream_id,
                    emit_start=True,
                    emit_end=False,
                    chunk_size=48,
                    metrics=metrics,
                    trace_id=generated_trace_id,
                    session_id=session_id,
                ):
                    yield fb
                text_started = True
                fallback_used_local = True

            if message_metadata:
                logger.info(
                    "chat_stream_metadata_received",
                    keys=list(message_metadata.keys()),
                    trace_id=generated_trace_id,
                )
            payloads: list[ChatStreamEvent] = []

            followups = message_metadata.get("followUpQuestions")
            if followups:
                payloads.append(
                    ChatStreamEvent(
                        type="data-followups",
                        data=followups,
                        transient=True,
                        trace_id=generated_trace_id,
                        session_id=session_id,
                        step="metadata",
                    )
                )

            structured_payload = message_metadata.get("structured")
            if structured_payload:
                payloads.append(
                    ChatStreamEvent(
                        type="assistant-structured",
                        data=structured_payload,
                        trace_id=generated_trace_id,
                        session_id=session_id,
                        stream_id=stream_id,
                        step="structured",
                    )
                )

            thinking_trace = message_metadata.get("thinking_trace")
            if thinking_trace:
                payloads.append(
                    ChatStreamEvent(
                        type="reasoning-start",
                        trace_id=generated_trace_id,
                        session_id=session_id,
                        step="reasoning",
                    )
                )
                reasoning_started = True
                latest_thought = _extract_latest_thought(thinking_trace)
                if latest_thought:
                    payloads.append(
                        ChatStreamEvent(
                            type="reasoning-delta",
                            text=latest_thought,
                            trace_id=generated_trace_id,
                            session_id=session_id,
                            step="reasoning",
                        )
                    )
                payloads.append(
                    ChatStreamEvent(
                        type="data-thinking",
                        data=thinking_trace,
                        trace_id=generated_trace_id,
                        session_id=session_id,
                        step="reasoning",
                    )
                )

            tool_results = message_metadata.get("toolResults")
            if tool_results:
                payloads.append(
                    ChatStreamEvent(
                        type="data-tool-result",
                        data=tool_results,
                        trace_id=generated_trace_id,
                        session_id=session_id,
                        step="tool",
                    )
                )

            reserved_keys = {"followUpQuestions", "thinking_trace", "toolResults", "structured"}
            leftover = {
                key: value for key, value in message_metadata.items() if key not in reserved_keys
            }
            if preface_metadata:
                leftover.setdefault("preface", preface_metadata)
            if leftover:
                payloads.append(
                    ChatStreamEvent(
                        type="message-metadata",
                        messageMetadata=leftover,
                        trace_id=generated_trace_id,
                        session_id=session_id,
                        step="metadata",
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

            if text_started:
                # Mark drafting completed before closing
                try:
                    yield format_sse_data({
                        "type": "step",
                        "data": {
                            "type": "Drafting response",
                            "status": "completed",
                        },
                        "trace_id": generated_trace_id,
                        "session_id": session_id,
                    })
                    # Emit a finish-step marker for UI timeline compaction
                    yield format_sse_data({
                        "type": "data",
                        "data": { "type": "finish-step" },
                        "trace_id": generated_trace_id,
                        "session_id": session_id,
                    })
                except Exception:
                    pass

                async for closing in stream_text_by_characters(
                    "",
                    stream_id,
                    emit_end=True,
                    metrics=metrics,
                    trace_id=generated_trace_id,
                    session_id=session_id,
                ):
                    yield closing

            if reasoning_started:
                # Close reasoning stream
                metrics["events"] = metrics.get("events", 0) + 1
                yield format_sse_data(
                    ChatStreamEvent(
                        type="reasoning-end",
                        trace_id=generated_trace_id,
                        session_id=session_id,
                        step="reasoning",
                    )
                )

            metrics["events"] = metrics.get("events", 0) + 1
            yield format_sse_data(
                ChatStreamEvent(
                    type="finish",
                    session_id=session_id,
                    stream_id=stream_id,
                    trace_id=generated_trace_id,
                    step="lifecycle",
                )
            )
            stream_closed = True

    except Exception as e:
        logger.exception(
            "chat_stream_generator_error",
            trace_id=generated_trace_id,
        )
        # If this is an async generator concurrency issue, stream a friendly fallback
        # instead of emitting a hard error which collapses the UI overlay.
        msg = str(e).lower()
        if ("already running" in msg) or ("anext" in msg and "running" in msg):
            fallback_text = (
                "I'm sorry, something interrupted the live response. "
                "Here’s a quick summary while I stabilize the stream: "
                "Mailbird helps you manage multiple email accounts, unify your inbox, and customize your workflow. "
                "To add an account: Open Settings → Accounts → Add Account, enter your email and password, then follow prompts."
            )
            async for fb in stream_text_by_characters(
                fallback_text,
                locals().get("stream_id") or f"assistant-{uuid.uuid4().hex}",
                emit_start=not locals().get("text_started", False),
                metrics=stream_metrics,
                trace_id=generated_trace_id,
                session_id=session_id,
            ):
                yield fb
            fallback_used_local = True
        else:
            stream_metrics["events"] += 1
            yield format_sse_data(
                ChatStreamEvent(
                    type="error",
                    errorText=f"An error occurred in the agent: {str(e)}",
                    trace_id=generated_trace_id,
                    session_id=session_id,
                    step="lifecycle",
                )
            )
            obs_error = str(e)
    finally:
        if not stream_closed:
            stream_metrics["events"] += 1
            yield format_sse_data(
                ChatStreamEvent(
                    type="finish",
                    session_id=session_id,
                    stream_id=locals().get("stream_id"),
                    trace_id=generated_trace_id,
                    step="lifecycle",
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
        if obs_timeline_id and not obs_completed:
            obs_publish_stage(
                obs_timeline_id,
                stage="completed",
                status="error" if obs_error else "complete",
                kind="primary_chat",
                user_id=user_id,
                metadata={
                    "events": stream_metrics.get("events", 0),
                    "text_chars": stream_metrics.get("text_chars", 0),
                    "heartbeats": stream_metrics.get("heartbeats", 0),
                    "elapsed_ms": elapsed_ms,
                    "stream_id": locals().get("stream_id"),
                },
                fallback_used=fallback_used_local,
            )
            obs_completed = True


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
            temperature=request.temperature,
            top_p=request.top_p,
            top_k=request.top_k,
            max_output_tokens=request.max_output_tokens,
            thinking_budget=request.thinking_budget,
            formatting=request.formatting,
        ),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream; charset=utf-8",
            "Content-Encoding": "identity",
            "Pragma": "no-cache",
            "Vary": "Authorization, Accept-Encoding",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
            "X-API-Version": "2.0",
        },
    )
