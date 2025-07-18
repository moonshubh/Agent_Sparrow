import logging
import os
import anyio
from dotenv import load_dotenv
from typing import AsyncIterator

from langchain_core.messages import AIMessageChunk
from langchain_google_genai import ChatGoogleGenerativeAI, HarmCategory, HarmBlockThreshold
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.core.rate_limiting.agent_wrapper import wrap_gemini_agent
from app.agents_v2.primary_agent.schemas import PrimaryAgentState
from app.agents_v2.primary_agent.tools import mailbird_kb_search, tavily_web_search
from app.agents_v2.primary_agent.reasoning import ReasoningEngine, ReasoningConfig
from app.agents_v2.primary_agent.prompts import AgentSparrowV9Prompts

# Standard logger setup
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Get a tracer instance for OpenTelemetry
tracer = trace.get_tracer(__name__)

# Load environment variables from .env file
load_dotenv()

# Ensure the GEMINI_API_KEY is set, raising an error if not found
if "GEMINI_API_KEY" not in os.environ:
    logger.error("GEMINI_API_KEY not found in environment variables.")
    raise ValueError("GEMINI_API_KEY not found in environment variables.")

# Initialize the Gemini model for the primary agent
try:
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    }
    model_base = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        google_api_key=os.environ.get("GEMINI_API_KEY"),
        safety_settings=safety_settings,
        convert_system_message_to_human=True
    )
    # Bind tools and then wrap for rate limiting
    model_with_tools_base = model_base.bind_tools([mailbird_kb_search, tavily_web_search])
    model_with_tools = wrap_gemini_agent(model_with_tools_base, "gemini-2.5-flash")
    logger.info("Primary agent model initialized and wrapped successfully.")
except Exception as e:
    logger.exception("Fatal error during ChatGoogleGenerativeAI initialization: %s", e)
    raise

async def run_primary_agent(state: PrimaryAgentState) -> AsyncIterator[AIMessageChunk]:
    """
    Asynchronously processes a user query using the primary agent system, yielding AI message chunks as a streaming response.

    This function orchestrates the reasoning engine to generate a comprehensive, self-critiqued answer.
    It handles input validation, calls the reasoning engine, logs telemetry, and streams the final response.

    Parameters:
        state (PrimaryAgentState): The current agent state, including user messages and session context.

    Yields:
        AIMessageChunk: Streamed chunks of the AI assistant's response.
    """
    with tracer.start_as_current_span("primary_agent.run") as parent_span:
        try:
            logger.debug("Running primary agent")
            user_query = state.messages[-1].content if state.messages else ""

            # Input Validation: Query length
            MAX_QUERY_LENGTH = 4000
            if len(user_query) > MAX_QUERY_LENGTH:
                parent_span.set_attribute("input.query.error", "Query too long")
                parent_span.set_status(Status(StatusCode.ERROR, "Query too long"))
                yield AIMessageChunk(content="Your query is too long. Please shorten it and try again.", role="assistant")
                return

            parent_span.set_attribute("input.query", user_query)
            parent_span.set_attribute("state.message_count", len(state.messages))

            # Initialize reasoning engine with self-critique enabled
            from app.core.settings import settings
            reasoning_config = ReasoningConfig(
                enable_self_critique=True,
                enable_chain_of_thought=settings.reasoning_enable_chain_of_thought,
                enable_problem_solving_framework=settings.reasoning_enable_problem_solving,
                enable_tool_intelligence=settings.reasoning_enable_tool_intelligence,
                enable_quality_assessment=settings.reasoning_enable_quality_assessment,
                enable_reasoning_transparency=settings.reasoning_enable_reasoning_transparency,
                debug_mode=settings.reasoning_debug_mode
            )
            reasoning_engine = ReasoningEngine(model=model_with_tools, config=reasoning_config)

            # Perform comprehensive reasoning. This is a single, blocking call that includes self-critique.
            reasoning_state = await reasoning_engine.reason_about_query(
                query=user_query,
                context={"messages": state.messages},
                session_id=getattr(state, 'session_id', 'default')
            )

            # Log key reasoning results for observability
            parent_span.set_attribute("reasoning.confidence", reasoning_state.overall_confidence)
            if reasoning_state.query_analysis:
                parent_span.set_attribute("reasoning.emotion", reasoning_state.query_analysis.emotional_state.value)
                parent_span.set_attribute("reasoning.category", reasoning_state.query_analysis.problem_category.value)
            if reasoning_state.self_critique_result:
                parent_span.set_attribute("reasoning.critique_score", reasoning_state.self_critique_result.critique_score)
                parent_span.set_attribute("reasoning.critique_passed", reasoning_state.self_critique_result.passed_critique)

            # The final, critiqued response is now ready to be streamed.
            final_response = reasoning_state.response_orchestration.final_response_preview

            if not final_response:
                logger.warning("Reasoning completed but no final response was generated.")
                yield AIMessageChunk(content="I'm sorry, I was unable to generate a response. Please try again.", role="assistant")
                return

            # Stream the final, cleaned response chunk by chunk to the client.
            chunk_size = 200  # Increased for better performance
            for i in range(0, len(final_response), chunk_size):
                chunk_content = final_response[i:i+chunk_size]
                yield AIMessageChunk(content=chunk_content, role="assistant")
                await anyio.sleep(0.005)  # Reduced delay for smoother streaming

            parent_span.set_status(Status(StatusCode.OK))

        except Exception as e:
            logger.exception("Error in run_primary_agent: %s", e)
            if 'parent_span' in locals() and parent_span.is_recording():
                parent_span.record_exception(e)
                parent_span.set_status(Status(StatusCode.ERROR, str(e)))
            yield AIMessageChunk(content=f"I'm sorry, an unexpected error occurred. Please try again later.", role="assistant") 