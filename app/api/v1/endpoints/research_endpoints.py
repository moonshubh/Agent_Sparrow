from __future__ import annotations

import logging
from typing import AsyncIterable, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.unified.agent_sparrow import run_unified_agent
from app.agents.orchestration.orchestration.state import GraphState
from langchain_core.messages import HumanMessage, AIMessage
from app.core.transport.sse import format_sse_data
from app.core.user_context import create_user_context_from_user_id, user_context_scope

logger = logging.getLogger(__name__)

router = APIRouter()


class ResearchItem(BaseModel):
    id: str
    url: str
    title: str
    snippet: str | None = None
    source_name: str | None = None
    score: float | None = None


class ResearchRequest(BaseModel):
    query: str
    top_k: int | None = None
    trace_id: str | None = None


class ResearchResponse(BaseModel):
    results: List[ResearchItem]
    trace_id: str | None = None


try:
    from app.api.v1.endpoints.auth import get_current_user_id
except ImportError:  # pragma: no cover

    async def get_current_user_id() -> str:  # type: ignore
        from app.core.settings import settings

        return getattr(settings, "development_user_id", "dev-user-12345")


@router.post("/agent/research", response_model=ResearchResponse)
async def research_query(
    request: ResearchRequest, user_id: str = Depends(get_current_user_id)
):
    if not request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        user_context = await create_user_context_from_user_id(user_id)
        tavily_key = await user_context.get_tavily_api_key()
        if not tavily_key:
            raise HTTPException(
                status_code=400,
                detail="Please configure your Tavily API key in Settings to use web research functionality.",
            )
        async with user_context_scope(user_context):
            # Use unified agent with research-focused query
            # The unified agent will use its research subagent which has web_search, kb_search, and firecrawl tools
            state = GraphState(
                messages=[
                    HumanMessage(
                        content=f"Research and provide a comprehensive answer with citations: {request.query}"
                    )
                ],
                session_id=f"research-{request.trace_id or 'default'}",
                forwarded_props={
                    "agent_type": "research",
                    "force_websearch": True,
                },
            )
            result = await run_unified_agent(state)

            # Extract answer from unified agent response
            result_messages = result.get("messages", [])
            answer = "No answer provided."
            citations = []

            # Find the final AI message
            for msg in reversed(result_messages):
                if isinstance(msg, AIMessage):
                    answer = str(msg.content) if msg.content else answer
                    # Extract citations from message metadata if available
                    if hasattr(msg, "additional_kwargs") and isinstance(
                        msg.additional_kwargs, dict
                    ):
                        metadata = msg.additional_kwargs.get("messageMetadata", {})
                        citations = metadata.get("citations", [])
                    break

        transformed_results: List[ResearchItem] = []
        if citations:
            for citation in citations:
                transformed_results.append(
                    ResearchItem(
                        id=str(citation.get("id", "")),
                        url=citation.get("url", "#"),
                        title=f"Source [{citation.get('id', '')}]: {citation.get('url', 'N/A')}",
                        snippet=answer,
                        source_name="Web Research",
                        score=None,
                    )
                )
        if not transformed_results and answer not in (
            "No answer provided.",
            "I'm sorry, I couldn't find relevant information to answer your question.",
        ):
            transformed_results.append(
                ResearchItem(
                    id="answer_summary",
                    url="#",
                    title="Synthesized Answer",
                    snippet=answer,
                    source_name="Synthesized by Agent",
                    score=None,
                )
            )
        return ResearchResponse(results=transformed_results, trace_id=request.trace_id)
    except Exception as e:
        logger.error(f"Error in Research Agent endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error processing research request: {str(e)}"
        )


async def research_agent_stream_generator(
    query: str, trace_id: str | None = None
) -> AsyncIterable[str]:
    try:
        yield format_sse_data(
            {
                "type": "step",
                "data": {
                    "type": "Starting Research",
                    "description": "Initializing research query...",
                    "status": "in-progress",
                },
            }
        )

        # Use unified agent with research-focused query
        state = GraphState(
            messages=[
                HumanMessage(
                    content=f"Research and provide a comprehensive answer with citations: {query}"
                )
            ],
            session_id=f"research-{trace_id or 'default'}",
            forwarded_props={
                "agent_type": "research",
                "force_websearch": True,
            },
        )
        result = await run_unified_agent(state)

        yield format_sse_data(
            {
                "type": "step",
                "data": {
                    "type": "Synthesize",
                    "description": "Synthesizing answer from sources...",
                    "status": "complete",
                },
            }
        )

        # Extract answer and citations from unified agent response
        result_messages = result.get("messages", [])
        answer = "No answer provided."
        citations = []

        for msg in reversed(result_messages):
            if isinstance(msg, AIMessage):
                answer = str(msg.content) if msg.content else answer
                if hasattr(msg, "additional_kwargs") and isinstance(
                    msg.additional_kwargs, dict
                ):
                    metadata = msg.additional_kwargs.get("messageMetadata", {})
                    citations = metadata.get("citations", [])
                break

        final_payload = {
            "type": "result",
            "data": {"answer": answer, "citations": citations, "trace_id": trace_id},
        }
        yield format_sse_data(final_payload)
        yield format_sse_data({"type": "done"})
    except Exception as e:
        logger.error(f"Error in research_agent_stream_generator: {e}", exc_info=True)
        err_payload = {
            "type": "error",
            "data": {
                "message": f"Error running research: {str(e)}",
                "trace_id": trace_id,
            },
        }
        yield format_sse_data(err_payload)
        yield format_sse_data(
            {
                "type": "step",
                "data": {
                    "type": "Research Complete",
                    "description": "Research analysis finished",
                    "status": "completed",
                },
            }
        )
        yield format_sse_data(
            {
                "type": "step",
                "data": {
                    "type": "Error",
                    "description": f"Research failed: {str(e)}",
                    "status": "error",
                },
            }
        )


@router.post("/agent/research/stream")
async def research_agent_stream(request: ResearchRequest):
    if not request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    return StreamingResponse(
        research_agent_stream_generator(request.query, request.trace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
