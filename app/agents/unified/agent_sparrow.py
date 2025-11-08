"""Unified Agent Sparrow implementation built on LangGraph v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.config import RunnableConfig, get_stream_writer
from loguru import logger

# Import middleware classes from correct sources
try:
    # LangChain provides TodoList and Summarization middleware
    from langchain.agents.middleware import TodoListMiddleware
    from langchain.agents.middleware.summarization import SummarizationMiddleware

    # DeepAgents provides SubAgent and PatchToolCalls middleware
    from deepagents.middleware.subagents import SubAgentMiddleware
    from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware

    MIDDLEWARE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Middleware not available ({e}) - agent will run without middleware")
    MIDDLEWARE_AVAILABLE = False

from app.agents.orchestration.orchestration.state import GraphState
from app.core.settings import settings

from .tools import get_registered_tools
from .subagents import get_subagent_specs

SYSTEM_PROMPT = """You are Agent Sparrow, Mailbird's expert AI assistant.\n\n- Help users with friendly, direct guidance.\n- Prefer tool calls over speculation.\n- Cite sources when you rely on external material.\n- Ask clarifying questions if information is missing.\n- Keep responses natural; no rigid templates required.\n"""


@dataclass
class AgentRuntimeConfig:
    """Resolved runtime configuration for a single run."""

    provider: str
    model: str


def _resolve_runtime_config(state: GraphState) -> AgentRuntimeConfig:
    provider = (state.provider or settings.default_model_provider or "google").lower()
    model = state.model or settings.primary_agent_model
    return AgentRuntimeConfig(provider=provider, model=model)


def _build_chat_model(runtime: AgentRuntimeConfig):
    if runtime.provider != "google":
        logger.warning(
            "Unsupported provider '%s' requested; falling back to Google Gemini",
            runtime.provider,
        )
    from langchain_google_genai import ChatGoogleGenerativeAI
    from app.core.settings import settings
    return ChatGoogleGenerativeAI(
        model=runtime.model,
        temperature=0.3,
        google_api_key=settings.gemini_api_key,
    )


def _build_deep_agent(state: GraphState):
    runtime = _resolve_runtime_config(state)
    chat_model = _build_chat_model(runtime)
    tools = get_registered_tools()
    subagents = get_subagent_specs()

    # Build comprehensive middleware stack only if available
    agent_kwargs = {
        "model": chat_model,
        "tools": tools,
        "subagents": subagents,
        "system_prompt": SYSTEM_PROMPT,
    }

    if MIDDLEWARE_AVAILABLE:
        middleware = [
            # TodoListMiddleware for task tracking
            TodoListMiddleware(),

            # SubAgentMiddleware with its own middleware stack for subagents
            SubAgentMiddleware(
                default_model=chat_model,
                default_tools=tools,
                subagents=subagents,
                default_middleware=[
                    TodoListMiddleware(),
                    SummarizationMiddleware(
                        model=chat_model,
                        max_tokens_before_summary=170000,
                        messages_to_keep=6,
                    ),
                    PatchToolCallsMiddleware(),
                ],
                general_purpose_agent=False,  # We have specific subagents
            ),

            # SummarizationMiddleware for long conversations
            SummarizationMiddleware(
                model=chat_model,
                max_tokens_before_summary=170000,  # ~170K tokens before summarizing
                messages_to_keep=6,  # Keep last 6 messages for context
            ),

            # PatchToolCallsMiddleware to fix any tool call formatting issues
            PatchToolCallsMiddleware(),
        ]
        agent_kwargs["middleware"] = middleware
    else:
        logger.warning("Running unified agent without middleware - functionality may be limited")

    agent = create_deep_agent(**agent_kwargs)

    # Increase recursion limit for complex tasks
    return agent.with_config({"recursion_limit": 1000})


def _build_runnable_config(state: GraphState, config: Optional[RunnableConfig]) -> Dict[str, Any]:
    base_config: Dict[str, Any] = dict(config or {})  # type: ignore[arg-type]
    configurable = dict(base_config.get("configurable") or {})
    configurable.setdefault("thread_id", state.session_id)
    configurable.setdefault("trace_id", state.trace_id)
    configurable.update({
        "provider": state.provider,
        "model": state.model,
        "use_server_memory": state.use_server_memory,
    })
    metadata = dict(configurable.get("metadata") or {})
    metadata.setdefault("session_id", state.session_id)
    metadata.setdefault("trace_id", state.trace_id)
    configurable["metadata"] = metadata

    tags = list(configurable.get("tags") or [])
    for tag in ("sparrow-unified", state.provider or None, state.model or None):
        if tag and tag not in tags:
            tags.append(tag)
    configurable["tags"] = tags

    if settings.langsmith_tracing_enabled:
        configurable.setdefault("name", "sparrow-unified-agent")
        if settings.langsmith_project:
            configurable.setdefault("project", settings.langsmith_project)
        if settings.langsmith_endpoint:
            configurable.setdefault("endpoint", settings.langsmith_endpoint)

    base_config["configurable"] = configurable
    return base_config


async def run_unified_agent(state: GraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Run the unified agent with comprehensive error handling."""
    try:
        agent = _build_deep_agent(state)
        run_config = _build_runnable_config(state, config)
        writer = get_stream_writer()

        final_output: Optional[Dict[str, Any]] = None

        if writer is not None:
            try:
                async for event in agent.astream_events(
                    {"messages": state.messages, "attachments": state.attachments, "scratchpad": state.scratchpad},
                    config=run_config,
                ):
                    event_type = event.get("event")
                    data = event.get("data", {})
                    if event_type == "on_chat_model_stream":
                        chunk = data.get("chunk")
                        if chunk is None:
                            continue
                        content = getattr(chunk, "content", None)
                        if not content and hasattr(chunk, "message"):
                            message_obj = getattr(chunk, "message")
                            content = getattr(message_obj, "content", None)
                        if isinstance(content, list):
                            content = "".join(str(part) for part in content if part)
                        if content:
                            writer({"type": "assistant-delta", "delta": content})
                    elif event_type in {"on_chain_end", "on_graph_end"}:
                        output = data.get("output")
                        if isinstance(output, dict):
                            final_output = output
            except Exception as e:
                logger.error(f"Error during agent streaming: {e}")
                # Try to get final output if streaming failed
                final_output = await agent.ainvoke(
                    {"messages": state.messages, "attachments": state.attachments, "scratchpad": state.scratchpad},
                    config=run_config,
                )

        if final_output is None:
            final_output = await agent.ainvoke(
                {"messages": state.messages, "attachments": state.attachments, "scratchpad": state.scratchpad},
                config=run_config,
            )

        updated_messages = final_output.get("messages") or []
        # DeepAgents returns BaseMessage objects; ensure we maintain list semantics.
        if not updated_messages or not isinstance(updated_messages[-1], BaseMessage):
            logger.error("Unified agent response missing AI message; returning original state")
            return {"messages": state.messages}

        scratchpad = final_output.get("scratchpad") or state.scratchpad
        forwarded_props = final_output.get("forwarded_props") or state.forwarded_props

        return {
            "messages": updated_messages,
            "scratchpad": scratchpad,
            "forwarded_props": forwarded_props,
        }

    except Exception as e:
        logger.error(f"Critical error in unified agent execution: {e}")
        # Return original state as fallback for graceful degradation
        return {
            "messages": state.messages,
            "scratchpad": state.scratchpad,
            "forwarded_props": state.forwarded_props,
            "error": str(e)
        }


def should_continue(state: GraphState) -> str:
    if not state.messages:
        return "end"
    last_message = state.messages[-1]
    if isinstance(last_message, AIMessage):
        tool_calls = getattr(last_message, "tool_calls", None)
        if tool_calls:
            return "continue"
    return "end"

