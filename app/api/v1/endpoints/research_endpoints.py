from __future__ import annotations

import json
import logging
from typing import AsyncIterable, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents_v2.research_agent.research_agent import get_research_graph, ResearchState
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
        return getattr(settings, 'development_user_id', 'dev-user-12345')


@router.post("/agent/research", response_model=ResearchResponse)
async def research_query(request: ResearchRequest, user_id: str = Depends(get_current_user_id)):
    if not request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        user_context = await create_user_context_from_user_id(user_id)
        tavily_key = await user_context.get_tavily_api_key()
        if not tavily_key:
            raise HTTPException(status_code=400, detail="Please configure your Tavily API key in Settings to use web research functionality.")
        async with user_context_scope(user_context):
            research_graph = get_research_graph()
            initial_graph_state: ResearchState = {
                "query": request.query,
                "urls": [],
                "documents": [],
                "answer": None,
                "citations": None,
            }
            result_state = await research_graph.ainvoke(initial_graph_state)

        answer = result_state.get("answer", "No answer provided.")
        citations = result_state.get("citations", [])

        transformed_results: List[ResearchItem] = []
        if citations:
            for citation in citations:
                transformed_results.append(
                    ResearchItem(
                        id=str(citation.get('id', '')),
                        url=citation.get('url', '#'),
                        title=f"Source [{citation.get('id', '')}]: {citation.get('url', 'N/A')}",
                        snippet=answer,
                        source_name="Web Research",
                        score=None,
                    )
                )
        if not transformed_results and answer not in ("No answer provided.", "I'm sorry, I couldn't find relevant information to answer your question."):
            transformed_results.append(
                ResearchItem(id="answer_summary", url="#", title="Synthesized Answer", snippet=answer, source_name="Synthesized by Agent", score=None)
            )
        response_data = {"results": [item.model_dump() for item in transformed_results], "trace_id": request.trace_id}
        return ResearchResponse(**response_data)
    except Exception as e:
        logger.error(f"Error in Research Agent endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing research request: {str(e)}")


async def research_agent_stream_generator(query: str, trace_id: str | None = None) -> AsyncIterable[str]:
    try:
        research_graph = get_research_graph()
        yield format_sse_data({'type': 'step', 'data': {'type': 'Starting Research', 'description': 'Initializing research query...', 'status': 'in-progress'}})
        initial_state: ResearchState = {"query": query, "urls": [], "documents": [], "answer": None, "citations": None}
        result = await research_graph.ainvoke(initial_state)
        yield format_sse_data({'type': 'step', 'data': {'type': 'Synthesize', 'description': 'Synthesizing answer from sources...', 'status': 'complete'}})
        final_payload = {'type': 'result', 'data': {'answer': result.get('answer', 'No answer provided.'), 'citations': result.get('citations', []), 'trace_id': trace_id}}
        yield format_sse_data(final_payload)
        yield format_sse_data({'type': 'done'})
    except Exception as e:
        logger.error(f"Error in research_agent_stream_generator: {e}", exc_info=True)
        err_payload = {'type': 'error', 'data': {'message': f'Error running research: {str(e)}', 'trace_id': trace_id}}
        yield format_sse_data(err_payload)
        yield format_sse_data({'type': 'step', 'data': {'type': 'Research Complete', 'description': 'Research analysis finished', 'status': 'completed'}})
        final_message = {"id": "research_result", "type": "agent", "content": result.get("answer", "No answer provided."), "timestamp": "now", "agentType": "research", "citations": result.get("citations", []), "feedback": None, "trace_id": trace_id}
        yield format_sse_data({'type': 'message', 'data': final_message})
        yield format_sse_data({'type': 'step', 'data': {"type": "Error", "description": f"Research failed: {str(e)}", "status": "error"}})


@router.post("/agent/research/stream")
async def research_agent_stream(request: ResearchRequest):
    if not request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    return StreamingResponse(
        research_agent_stream_generator(request.query, request.trace_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
